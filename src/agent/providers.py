# -*- coding: utf-8 -*-
"""
多 LLM Provider 抽象
====================
用户可以在 config.json 的 `llm_providers` 数组里配多个 Provider。
Agent 运行时会挑出 `is_default=true` 的那条，或按 `name` 查找。

支持的 Provider type：
  · openai_compatible  — OpenAI / DeepSeek / Kimi / Qwen / Ollama / vLLM ...
                         都是 POST /v1/chat/completions，支持 tools
  · anthropic          — Claude messages API，tools 格式不同（手工适配）

其它（Gemini / Bedrock / Azure）后续可在这里加 class。
"""
from __future__ import annotations

import json
import http.client
import urllib.parse
import ssl
import time
from dataclasses import dataclass, asdict
from typing import Optional


# ── 配置访问 ─────────────────────────────────────────────────────
def _load_providers_from_config() -> list[dict]:
    # 延迟 import，避免 agent 包和 app 的循环依赖
    from app import load_config
    cfg = load_config()
    return cfg.get("llm_providers") or []


@dataclass
class LLMProvider:
    name: str                     # 唯一名字，如 "openai-main" / "deepseek-primary"
    type: str                     # "openai_compatible" | "anthropic"
    base_url: str
    api_key: str
    model: str                    # 默认模型名
    is_default: bool = False
    enabled: bool = True
    temperature: float = 0.2
    timeout: int = 90
    extra_headers: Optional[dict] = None   # 用于 Anthropic 的 anthropic-version 等
    # Agent 运行时限制
    max_iterations: int = 6

    @classmethod
    def from_dict(cls, d: dict) -> "LLMProvider":
        return cls(
            name=d.get("name", "default"),
            type=(d.get("type") or "openai_compatible").lower(),
            base_url=(d.get("base_url") or "").rstrip("/"),
            api_key=d.get("api_key") or "",
            model=d.get("model") or "gpt-4o-mini",
            is_default=bool(d.get("is_default")),
            enabled=bool(d.get("enabled", True)),
            temperature=float(d.get("temperature", 0.2)),
            timeout=int(d.get("timeout", 90)),
            extra_headers=d.get("extra_headers") or {},
            max_iterations=int(d.get("max_iterations", 6)),
        )

    def to_public_dict(self) -> dict:
        """前端展示用：掩码 api_key。"""
        d = asdict(self)
        k = d.get("api_key", "") or ""
        if k and len(k) > 8:
            d["api_key"] = k[:4] + "***" + k[-4:]
        return d


def list_providers() -> list[LLMProvider]:
    raw = _load_providers_from_config()
    return [LLMProvider.from_dict(d) for d in raw if isinstance(d, dict)]


def get_provider(name: str) -> Optional[LLMProvider]:
    for p in list_providers():
        if p.name == name and p.enabled:
            return p
    return None


def get_default_provider() -> Optional[LLMProvider]:
    providers = list_providers()
    # 1) 显式 is_default
    for p in providers:
        if p.is_default and p.enabled:
            return p
    # 2) 退回到第一个 enabled
    for p in providers:
        if p.enabled:
            return p
    return None


# ── HTTP 小工具 ───────────────────────────────────────────────────
def _http_post_json(url: str, headers: dict, payload: dict,
                    timeout: int) -> tuple[int, dict, str]:
    parsed = urllib.parse.urlparse(url)
    path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    hdrs.update(headers or {})
    body = json.dumps(payload).encode("utf-8")
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                           timeout=timeout,
                                           context=ssl.create_default_context())
    else:
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80,
                                          timeout=timeout)
    try:
        conn.request("POST", path, body=body, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        data: dict = {}
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        return resp.status, data, raw
    finally:
        conn.close()


# ── 健康探测（后端 "测试连接" 用）──────────────────────────────────
def probe_provider(p: LLMProvider) -> dict:
    """用最小化请求测 provider 是否可达、key 是否有效、模型是否存在。"""
    if not p.base_url:
        return {"ok": False, "message": "base_url 未填写"}
    if not p.api_key or "***" in p.api_key:
        return {"ok": False, "message": "API Key 未填写或被掩码"}

    if p.type == "openai_compatible":
        url = p.base_url + "/v1/models"
        headers = {"Authorization": f"Bearer {p.api_key}"}
        try:
            conn_url = urllib.parse.urlparse(url)
            if conn_url.scheme == "https":
                conn = http.client.HTTPSConnection(conn_url.hostname,
                                                    conn_url.port or 443,
                                                    timeout=p.timeout,
                                                    context=ssl.create_default_context())
            else:
                conn = http.client.HTTPConnection(conn_url.hostname,
                                                   conn_url.port or 80,
                                                   timeout=p.timeout)
            conn.request("GET", conn_url.path or "/v1/models", headers=headers)
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8", errors="replace")
            conn.close()
            if resp.status == 200:
                try:
                    data = json.loads(raw)
                    models = [m.get("id") for m in (data.get("data") or [])]
                    has_target = p.model in models
                    msg = f"鉴权通过 · {len(models)} 个模型可用"
                    if not has_target and models:
                        msg += f" · 注意：默认模型 `{p.model}` 不在列表中"
                    return {"ok": True, "message": msg,
                            "models_count": len(models),
                            "has_target_model": has_target,
                            "models_sample": models[:10]}
                except Exception:
                    return {"ok": True, "message": "鉴权通过（/v1/models 返回非标准）"}
            elif resp.status in (401, 403):
                return {"ok": False, "message": f"API Key 无效（HTTP {resp.status}）"}
            elif resp.status == 404:
                # /v1/models 不存在 → 退回到 minimal chat completions probe
                return _probe_openai_via_chat(p)
            else:
                return {"ok": False, "message": f"HTTP {resp.status}: {raw[:180]}"}
        except Exception as e:
            return {"ok": False, "message": f"连接失败: {e}"}

    elif p.type == "anthropic":
        # 最小 messages 请求
        url = p.base_url + "/v1/messages"
        headers = {
            "x-api-key": p.api_key,
            "anthropic-version": (p.extra_headers or {}).get(
                "anthropic-version", "2023-06-01"),
        }
        payload = {
            "model": p.model,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "hi"}],
        }
        try:
            status, data, raw = _http_post_json(url, headers, payload, p.timeout)
            if status == 200:
                return {"ok": True, "message": f"Claude 鉴权通过 · {p.model}"}
            if status in (401, 403):
                return {"ok": False, "message": f"API Key 无效（HTTP {status}）"}
            return {"ok": False, "message": f"HTTP {status}: {raw[:200]}"}
        except Exception as e:
            return {"ok": False, "message": f"连接失败: {e}"}

    return {"ok": False, "message": f"未知 provider type: {p.type}"}


def _probe_openai_via_chat(p: LLMProvider) -> dict:
    """某些 OpenAI 兼容服务不实现 /v1/models（比如 Kimi 早期）。
    退回到发一个 1 token 的 chat completions 验证 key。"""
    url = p.base_url + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {p.api_key}"}
    payload = {
        "model": p.model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }
    try:
        status, data, raw = _http_post_json(url, headers, payload, p.timeout)
        if status == 200:
            return {"ok": True, "message": "鉴权通过（通过 chat/completions 验证）"}
        if status in (401, 403):
            return {"ok": False, "message": f"API Key 无效（HTTP {status}）"}
        return {"ok": False, "message": f"HTTP {status}: {raw[:180]}"}
    except Exception as e:
        return {"ok": False, "message": f"连接失败: {e}"}


# ── Chat Completion 统一调用 ───────────────────────────────────────
def chat_completion(
    provider: LLMProvider,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    model_override: Optional[str] = None,
    temperature_override: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> dict:
    """
    统一入口：输入 [{role, content}, ...] + tools，返回
        {
          "content": str,        # 助手文字回复（可能为空，说明 LLM 要调工具）
          "tool_calls": [{id, name, arguments: dict}, ...],
          "finish_reason": str,
          "raw": 原始响应
        }
    """
    if provider.type == "openai_compatible":
        return _chat_openai(provider, messages, tools,
                             model_override, temperature_override, max_tokens)
    if provider.type == "anthropic":
        return _chat_anthropic(provider, messages, tools,
                                model_override, temperature_override, max_tokens)
    raise RuntimeError(f"未知 provider type: {provider.type}")


def _chat_openai(p: LLMProvider, messages: list[dict],
                 tools: Optional[list[dict]],
                 model_override: Optional[str],
                 temperature_override: Optional[float],
                 max_tokens: Optional[int]) -> dict:
    url = p.base_url + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {p.api_key}"}
    if p.extra_headers:
        headers.update(p.extra_headers)
    payload: dict = {
        "model": model_override or p.model,
        "messages": messages,
        "temperature": (temperature_override if temperature_override is not None
                        else p.temperature),
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    status, data, raw = _http_post_json(url, headers, payload, p.timeout)
    if status >= 400:
        raise RuntimeError(f"LLM HTTP {status}: {raw[:400]}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM 返回空 choices: {raw[:200]}")
    msg = choices[0].get("message", {})
    tc_raw = msg.get("tool_calls") or []
    tcs: list[dict] = []
    for t in tc_raw:
        fn = t.get("function", {})
        args = fn.get("arguments", "{}")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"_raw": args}
        tcs.append({
            "id": t.get("id"),
            "name": fn.get("name"),
            "arguments": args,
        })
    return {
        "content": msg.get("content") or "",
        "tool_calls": tcs,
        "finish_reason": choices[0].get("finish_reason"),
        "usage": data.get("usage"),
        "raw": data,
    }


def _chat_anthropic(p: LLMProvider, messages: list[dict],
                    tools: Optional[list[dict]],
                    model_override: Optional[str],
                    temperature_override: Optional[float],
                    max_tokens: Optional[int]) -> dict:
    """
    Claude 的 messages API 结构和 OpenAI 不一样：
    - system 单独放在外面
    - tool_use / tool_result 是 content 里的 block
    这里做一次格式转换。
    """
    sys_parts = []
    conv_msgs = []
    for m in messages:
        if m["role"] == "system":
            sys_parts.append(m.get("content", ""))
        else:
            conv_msgs.append(m)
    system_str = "\n\n".join(s for s in sys_parts if s)

    # Anthropic tools: [{name, description, input_schema}]
    anth_tools = []
    if tools:
        for t in tools:
            fn = t.get("function", {})
            anth_tools.append({
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object"}),
            })

    # conv_msgs 转换：OpenAI 的 tool msg → Anthropic 的 user 含 tool_result
    anth_msgs = []
    for m in conv_msgs:
        r = m["role"]
        if r == "user":
            anth_msgs.append({"role": "user",
                               "content": m.get("content", "")})
        elif r == "assistant":
            # assistant 可能带 tool_calls
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in (m.get("tool_calls") or []):
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id") or f"tooluse_{len(blocks)}",
                    "name": tc.get("name"),
                    "input": tc.get("arguments") or {},
                })
            if blocks:
                anth_msgs.append({"role": "assistant", "content": blocks})
            else:
                anth_msgs.append({"role": "assistant",
                                   "content": m.get("content", "")})
        elif r == "tool":
            # 合并连续 tool 消息到一条 user tool_result block
            block = {
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id"),
                "content": m.get("content", ""),
            }
            # 如果上一条已是 user，就并进去
            if anth_msgs and anth_msgs[-1]["role"] == "user" \
                    and isinstance(anth_msgs[-1]["content"], list):
                anth_msgs[-1]["content"].append(block)
            else:
                anth_msgs.append({"role": "user", "content": [block]})

    url = p.base_url + "/v1/messages"
    headers = {
        "x-api-key": p.api_key,
        "anthropic-version": (p.extra_headers or {}).get(
            "anthropic-version", "2023-06-01"),
    }
    payload = {
        "model": model_override or p.model,
        "max_tokens": max_tokens or 4096,
        "messages": anth_msgs,
        "temperature": (temperature_override if temperature_override is not None
                        else p.temperature),
    }
    if system_str:
        payload["system"] = system_str
    if anth_tools:
        payload["tools"] = anth_tools

    status, data, raw = _http_post_json(url, headers, payload, p.timeout)
    if status >= 400:
        raise RuntimeError(f"Claude HTTP {status}: {raw[:400]}")

    content_blocks = data.get("content") or []
    text_parts: list[str] = []
    tcs: list[dict] = []
    for blk in content_blocks:
        if blk.get("type") == "text":
            text_parts.append(blk.get("text", ""))
        elif blk.get("type") == "tool_use":
            tcs.append({
                "id": blk.get("id"),
                "name": blk.get("name"),
                "arguments": blk.get("input") or {},
            })
    return {
        "content": "\n".join(text_parts).strip(),
        "tool_calls": tcs,
        "finish_reason": data.get("stop_reason"),
        "usage": data.get("usage"),
        "raw": data,
    }
