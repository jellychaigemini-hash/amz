# -*- coding: utf-8 -*-
"""
Rufus Chrome CDP 会话（Python 版，在 skill 的 MJS 基础上做了 5 项加固）
==================================================================
skill 里的 rufus-chrome-session.mjs 是半自动方案，但反爬能力是"及格线"。
本文件做了这些强化：

  ① 启动前注入 `navigator.webdriver = undefined` 等 Stealth 脚本
     (Page.addScriptToEvaluateOnNewDocument)
  ② 轮询"Rufus has completed generating"而不是固定 sleep 8 秒
  ③ 每题间隔随机 15-40 秒（不再固定 2 秒）
  ④ 全程检测 CAPTCHA / 人机校验页（id=captchacharacters / /errors/）
     命中 → 立刻停，返回已抓部分
  ⑤ 所有阶段有明确的 status 返回，便于前端 SSE 实时展示
"""
from __future__ import annotations

import asyncio
import json
import random
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable


# ── Stealth JS（隐藏自动化特征） ──────────────────────────────────
# 注：Amazon 的反爬团队远比这些补丁先进，本 patch 只对付"中级"检测。
# 不追求完全隐身，目标是"让普通 bot 探针扫不到 webdriver 特征"。
_STEALTH_JS = r"""
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'plugins', {
      get: () => [{name:'Chrome PDF Plugin'}, {name:'Chrome PDF Viewer'}]
    });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en']
    });
  } catch (e) {}
  // 屏蔽 chrome.runtime undefined 特征
  try {
    window.chrome = window.chrome || {};
    window.chrome.runtime = window.chrome.runtime || {};
  } catch (e) {}
})();
"""


@dataclass
class RufusProgress:
    """单题进度。"""
    question_index: int
    total_questions: int
    question: str
    stage: str           # "injecting" | "waiting_rufus" | "captured" | "error" | "captcha" | "rate_limit"
    answer_preview: str = ""
    error: str = ""
    elapsed_sec: float = 0.0
    wait_before_next_sec: int = 0


ProgressCallback = Callable[[RufusProgress], None]


@dataclass
class RufusRunResult:
    """整次采集结果。"""
    success: bool
    reason: str = ""
    question_results: list[dict] = field(default_factory=list)
    # 每个元素：{question, answer, stage, elapsed_sec, error}
    aborted_at: Optional[int] = None  # 从第几题中止（1-based）
    abort_reason: str = ""            # "captcha" / "network" / "rufus_not_found"
    captcha_detected: bool = False


# ── HTTP 小助手 ────────────────────────────────────────────────
def _http_get_json(url: str, timeout: float = 5.0) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _http_put_json(url: str, timeout: float = 5.0) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, method="PUT")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


# ── 对外接口：检测 Chrome 是否可被接管 ──────────────────────────
def probe_chrome_debug_port(port: int = 9222, timeout: float = 2.0) -> dict:
    """前端调用：Chrome 是否在 9222 端口上可用？可用则返回浏览器信息。"""
    info = _http_get_json(f"http://127.0.0.1:{port}/json/version", timeout=timeout)
    if not info:
        return {
            "available": False,
            "port": port,
            "message": (
                f"Chrome 未在端口 {port} 开启调试。请关闭所有 Chrome，"
                f'用这条命令启动：chrome.exe --remote-debugging-port={port} '
                f'--remote-allow-origins=*'
            ),
        }
    return {
        "available": True,
        "port": port,
        "browser": info.get("Browser"),
        "user_agent": info.get("User-Agent"),
        "webkit_version": info.get("WebKit-Version"),
    }


# ── CDP 会话实现（用 websockets 异步库） ────────────────────────
class RufusChromeSession:
    """
    接管已启动的真人 Chrome，跑 N 个问题。
    使用流程：
        async with RufusChromeSession(port=9222) as sess:
            await sess.ensure_page("https://www.amazon.com/s?k=curtain")
            for i, q in enumerate(questions):
                r = await sess.ask_one(q, index=i, total=len(questions))
                ...
    """

    def __init__(self, port: int = 9222,
                 min_interval: int = 15, max_interval: int = 40,
                 answer_max_wait: int = 25,
                 progress_cb: Optional[ProgressCallback] = None):
        self.port = port
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.answer_max_wait = answer_max_wait
        self.progress_cb = progress_cb

        self._ws = None
        self._page_id = None
        self._msg_id = 1

    # ── 生命周期 ────────────────────────────────────────────────
    async def __aenter__(self):
        await self._connect()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def _connect(self):
        # 惰性导入：websockets 只有在真正要自动模式时才需要
        import websockets
        self._websockets = websockets

        # 1) 验证 Chrome 可达
        info = _http_get_json(f"http://127.0.0.1:{self.port}/json/version")
        if not info:
            raise RuntimeError(
                f"Chrome 不在 127.0.0.1:{self.port} 上运行。"
                f"请先启动：chrome.exe --remote-debugging-port={self.port}"
            )

        # 2) 找或创建页面
        tabs = _http_get_json(f"http://127.0.0.1:{self.port}/json") or []
        page_tab = None
        for t in tabs:
            if t.get("type") == "page":
                page_tab = t
                break
        if not page_tab:
            page_tab = _http_put_json(f"http://127.0.0.1:{self.port}/json/new")
            if not page_tab:
                raise RuntimeError("无法创建新 Chrome 标签页")

        self._page_id = page_tab["id"]
        ws_url = page_tab["webSocketDebuggerUrl"]

        # 3) 连 WebSocket
        self._ws = await websockets.connect(ws_url, max_size=10 * 1024 * 1024,
                                            open_timeout=10)

        # 4) 启用必要的 CDP domains
        await self._send("Runtime.enable")
        await self._send("Page.enable")
        await self._send("Network.enable")

        # 5) 注入 Stealth 脚本（对未来的每个 document 生效）
        await self._send("Page.addScriptToEvaluateOnNewDocument",
                         {"source": _STEALTH_JS})

    async def close(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ── 底层发送 ────────────────────────────────────────────────
    async def _send(self, method: str, params: Optional[dict] = None,
                    timeout: float = 30.0) -> dict:
        self._msg_id += 1
        mid = self._msg_id
        msg = {"id": mid, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(msg))
        # 等对应 id 的响应
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            except asyncio.TimeoutError:
                continue
            data = json.loads(raw)
            if data.get("id") == mid:
                if "error" in data:
                    raise RuntimeError(f"CDP error: {data['error']}")
                return data.get("result", {})
            # 其它 event 忽略掉
        raise TimeoutError(f"CDP {method} timed out")

    async def _eval(self, expression: str,
                    timeout: float = 20.0) -> Optional[object]:
        r = await self._send("Runtime.evaluate",
                             {"expression": expression, "returnByValue": True,
                              "awaitPromise": True},
                             timeout=timeout)
        result = r.get("result", {})
        if result.get("subtype") == "error":
            return None
        return result.get("value")

    # ── 高层操作 ────────────────────────────────────────────────
    async def ensure_page(self, url: str,
                          wait_after_sec: int = 6) -> dict:
        """导航到目标页，等待加载。返回 {ok, current_url, captcha}"""
        await self._send("Page.navigate", {"url": url})
        # 给页面加载时间 + 给 Rufus 面板加载时间
        await asyncio.sleep(wait_after_sec)
        # CAPTCHA 检测
        cap = await self.detect_captcha()
        if cap["detected"]:
            return {"ok": False, "captcha": True, **cap}
        # 当前 URL
        loc = await self._eval("document.location.href")
        return {"ok": True, "captcha": False, "current_url": str(loc or "")}

    async def detect_captcha(self) -> dict:
        """检测当前页面是否为 CAPTCHA / 错误页。"""
        checks = [
            # Amazon CAPTCHA
            ("captcha_field", 'document.getElementById("captchacharacters")'),
            # URL 特征
            ("errors_url", 'document.location.href.includes("/errors/")'),
            ("validatecaptcha",
             'document.location.href.includes("validateCaptcha")'),
            # 文本特征
            ("robot_check",
             '(document.body.textContent || "").includes("Enter the characters you see below")'),
            ("type_letters",
             '(document.body.textContent || "").includes("Type the characters")'),
        ]
        hits = []
        for name, expr in checks:
            try:
                v = await self._eval(f"!!({expr})")
                if v:
                    hits.append(name)
            except Exception:
                pass
        return {"detected": bool(hits), "hits": hits}

    async def _find_rufus_input(self) -> bool:
        """Rufus 输入框是否已加载。"""
        v = await self._eval(
            'document.getElementById("rufus-text-area") !== null'
        )
        return bool(v)

    async def _type_question(self, question: str) -> bool:
        """把问题写进 textarea 并按 Enter。"""
        # 用 JSON.stringify 的等价 encoding 来安全转义
        safe_q = json.dumps(question)
        js = f"""
        (function() {{
          var ta = document.getElementById("rufus-text-area");
          if (!ta) return "NOT_FOUND";
          ta.focus();
          ta.value = "";
          ta.dispatchEvent(new Event("input", {{ bubbles: true }}));
          ta.value = {safe_q};
          // 触发 React 的受控组件
          var setter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, {safe_q});
          ta.dispatchEvent(new Event("input", {{ bubbles: true }}));
          // 模拟"打完了"的小停顿
          return "TYPED";
        }})()
        """
        v = await self._eval(js)
        if v != "TYPED":
            return False

        # 稍等一下再按回车（模拟人类）
        await asyncio.sleep(random.uniform(0.5, 1.2))

        js_enter = """
        (function() {
          var ta = document.getElementById("rufus-text-area");
          if (!ta) return "NOT_FOUND";
          ta.dispatchEvent(new KeyboardEvent("keydown", {
            bubbles: true, cancelable: true, key: "Enter", code: "Enter"
          }));
          return "ENTER";
        })()
        """
        v2 = await self._eval(js_enter)
        return v2 == "ENTER"

    async def _poll_until_done(self, question: str,
                                max_wait: int) -> tuple[str, bool]:
        """
        轮询等待 Rufus 回答完成。
        返回 (raw_answer_text, completed_flag)
        """
        start = time.time()
        last_len = 0
        stable_count = 0
        completed = False
        while time.time() - start < max_wait:
            await asyncio.sleep(1.2)
            # 检查完成标记
            done = await self._eval(
                '(document.body.textContent || "").includes('
                '"Rufus has completed generating a response")'
            )
            # 再检查 CAPTCHA（万一中途跳）
            cap = await self.detect_captcha()
            if cap["detected"]:
                # 抓一下已有的内容，然后返回
                partial = await self._get_current_answer(question)
                return partial, False
            if done:
                completed = True
                break
            # 观察长度是否稳定（长度连续 3 次不增长 → 应该也完成了）
            current_len = await self._eval(
                '(document.querySelector(".nav-rufus-content") || {}).'
                'textContent?.length || 0'
            )
            try:
                current_len = int(current_len or 0)
            except Exception:
                current_len = 0
            if current_len == last_len and current_len > 0:
                stable_count += 1
                if stable_count >= 4:
                    completed = True
                    break
            else:
                stable_count = 0
                last_len = current_len
        answer = await self._get_current_answer(question)
        return answer, completed

    async def _get_current_answer(self, question: str) -> str:
        """抽取 Rufus 面板当前文字内容（从 question 关键词之后开始）。"""
        marker = question[:40].replace('"', '\\"').replace("\\", "\\\\")
        js = f"""
        (function() {{
          var panel = document.querySelector(".nav-rufus-content");
          if (!panel) return "";
          var text = panel.textContent || "";
          var marker = "{marker}";
          var pos = text.indexOf(marker);
          if (pos === -1) {{
            return text.substring(Math.max(0, text.length - 5000));
          }}
          return text.substring(pos, pos + 5000);
        }})()
        """
        v = await self._eval(js)
        return str(v or "")

    async def ask_one(self, question: str, index: int, total: int) -> dict:
        """问一个问题并抓回答。返回 {question, answer, stage, elapsed_sec, error}"""
        start = time.time()
        entry = {
            "index": index + 1,
            "question": question,
            "answer": "",
            "stage": "pending",
            "elapsed_sec": 0.0,
            "error": "",
        }

        def _report(stage: str, **kw):
            if not self.progress_cb:
                return
            self.progress_cb(RufusProgress(
                question_index=index + 1, total_questions=total,
                question=question, stage=stage,
                elapsed_sec=round(time.time() - start, 2),
                **kw,
            ))

        _report("injecting")

        # 0) 输入框必须存在
        if not await self._find_rufus_input():
            entry["stage"] = "error"
            entry["error"] = "Rufus 输入框未找到（面板未加载 / 已被反爬阻断）"
            _report("error", error=entry["error"])
            return entry

        # 1) 发送问题
        ok = await self._type_question(question)
        if not ok:
            entry["stage"] = "error"
            entry["error"] = "问题注入失败（textarea 不接受输入）"
            _report("error", error=entry["error"])
            return entry

        # 2) 轮询回答
        _report("waiting_rufus")
        answer, completed = await self._poll_until_done(question, self.answer_max_wait)

        # 3) 再查一次 CAPTCHA（保险）
        cap = await self.detect_captcha()

        entry["answer"] = answer
        entry["elapsed_sec"] = round(time.time() - start, 2)

        if cap["detected"]:
            entry["stage"] = "captcha"
            entry["error"] = "触发 CAPTCHA：" + ",".join(cap["hits"])
            _report("captcha", answer_preview=answer[:80], error=entry["error"])
            return entry

        entry["stage"] = "captured" if answer else "error"
        if not answer:
            entry["error"] = "回答为空（可能是超时或 Rufus 面板未响应）"
        _report(entry["stage"], answer_preview=answer[:120], error=entry["error"])
        return entry

    async def sleep_between(self, index: int, total: int):
        """题与题之间 15-40 秒随机停顿（最后一题不 sleep）。"""
        if index >= total - 1:
            return
        secs = random.randint(self.min_interval, self.max_interval)
        if self.progress_cb:
            self.progress_cb(RufusProgress(
                question_index=index + 1, total_questions=total,
                question="", stage="rate_limit",
                wait_before_next_sec=secs,
            ))
        await asyncio.sleep(secs)


# ── 便利函数：一把跑完所有问题 ──────────────────────────────────
async def run_auto_session(
    questions: list[str],
    amazon_url: str = "https://www.amazon.com/",
    port: int = 9222,
    min_interval: int = 15,
    max_interval: int = 40,
    answer_max_wait: int = 25,
    progress_cb: Optional[ProgressCallback] = None,
) -> RufusRunResult:
    """自动跑一批 Rufus 问题；遇 CAPTCHA 立即中止并返回已抓部分。"""
    result = RufusRunResult(success=False)

    try:
        async with RufusChromeSession(
            port=port, min_interval=min_interval,
            max_interval=max_interval,
            answer_max_wait=answer_max_wait,
            progress_cb=progress_cb,
        ) as sess:

            # 导航（已登录用户的 Chrome profile 里 Rufus 才会自动加载）
            nav = await sess.ensure_page(amazon_url, wait_after_sec=6)
            if nav.get("captcha"):
                result.captcha_detected = True
                result.abort_reason = "captcha_on_landing"
                result.reason = "进入 Amazon 首页即遇 CAPTCHA"
                return result

            if not await sess._find_rufus_input():
                result.abort_reason = "rufus_not_found"
                result.reason = "Rufus 输入框未加载（可能需要先点击 Rufus 按钮或未登录）"
                return result

            # 逐题问
            for i, q in enumerate(questions):
                entry = await sess.ask_one(q, index=i, total=len(questions))
                result.question_results.append(entry)
                if entry["stage"] == "captcha":
                    result.captcha_detected = True
                    result.aborted_at = i + 1
                    result.abort_reason = "captcha_mid_session"
                    result.reason = f"第 {i + 1} 题触发 CAPTCHA"
                    return result
                if entry["stage"] == "error" and not entry["answer"]:
                    # 单题错误不阻塞，继续（前端可以看到这条 error）
                    pass
                # 下一题前 sleep
                await sess.sleep_between(i, len(questions))

            # 全部完成
            captured = sum(1 for r in result.question_results if r["stage"] == "captured")
            result.success = captured > 0
            result.reason = f"已采集 {captured}/{len(questions)} 题"
            return result

    except RuntimeError as e:
        result.abort_reason = "connect_failed"
        result.reason = str(e)
        return result
    except Exception as e:
        result.abort_reason = "unknown"
        result.reason = f"{type(e).__name__}: {e}"
        return result
