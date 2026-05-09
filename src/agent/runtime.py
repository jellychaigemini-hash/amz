# -*- coding: utf-8 -*-
"""
Agent Runtime — ReAct 循环
==========================

流程：
  1) system prompt + 用户 prompt → LLM
  2) LLM 返回 content + tool_calls
     · 无 tool_calls → 终止，把 content 给用户
     · 有 tool_calls → 逐个跑 run_tool，结果作为 tool-role 消息喂回
  3) 最多循环 max_iterations 次

输出一份「trace」，里面记录每一轮 LLM 说了什么、调了哪些工具、拿到什么结果。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .providers import (
    LLMProvider, get_provider, get_default_provider,
    chat_completion,
)
from .tools_registry import TOOLS, get_tool_schemas, run_tool


DEFAULT_SYSTEM_PROMPT = """You are an Amazon listing optimization assistant.

You have a toolbox of Skill functions that can:
  · analyze an ASIN end-to-end (SIF + Sorftime MCP data, COSMO title/bullet/QA,
    GEO static audit)
  · generate "Rufus probe questions" tailored to a listing's weakest dimensions
  · run automatic Rufus collection via Chrome CDP, OR accept manually pasted answers
  · analyze SQP Brand View weekly CSVs (WoW, high-conv terms, market deviation)
  · list recently analyzed ASINs

Decision rules:
  1) Always call `analyze_asin` FIRST when the user gives an ASIN — everything
     else depends on the context it produces.
  2) For Rufus research: FIRST try `rufus_check_chrome`; if Chrome is available,
     use `rufus_auto_run`; if not or if it returns should_fallback_to_manual,
     tell the user to paste answers and call `rufus_paste_submit` instead.
  3) When showing results, prefer the Rufus-evidence-based GEO audit over the
     static one — but note that the static one is available even without Rufus data.
  4) Be direct. Numbers and action items are more useful than general advice.
  5) Respect user language: Chinese in, Chinese out. English in, English out.
  6) NEVER fabricate tool results — if a tool returns error, say so.
  7) Tool results may be truncated ([TRUNCATED] marker); if you need the full
     output, tell the user where to find it (usually `prompts/<ASIN>_*.json`).

If the user's request is ambiguous, ask one short clarifying question before
calling any tools.
"""


@dataclass
class AgentTrace:
    iterations: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    tool_calls_count: int = 0
    elapsed_sec: float = 0.0


def _extract_usage_tokens(usage: Optional[dict]) -> int:
    if not isinstance(usage, dict):
        return 0
    # OpenAI 格式
    if "total_tokens" in usage:
        return int(usage.get("total_tokens", 0))
    # Anthropic 格式
    it = usage.get("input_tokens") or 0
    ot = usage.get("output_tokens") or 0
    return int(it) + int(ot)


def run_agent_turn(
    user_message: str,
    provider_name: Optional[str] = None,
    provider: Optional[LLMProvider] = None,
    system_prompt: Optional[str] = None,
    history: Optional[list[dict]] = None,
    max_iterations: Optional[int] = None,
) -> dict:
    """
    跑一轮完整的 agent 循环，直到 LLM 不再调用工具。

    Args:
        user_message: 用户本轮输入
        provider_name: 指定用哪个 Provider（name 匹配 config）。不填用默认
        provider:      直接传 LLMProvider 对象（优先级高于 provider_name）
        system_prompt: 覆盖默认系统提示
        history:       多轮上下文 [{role, content, tool_calls?}, ...]
        max_iterations: 覆盖 provider.max_iterations

    Returns:
      {
        "answer": str,              # 最终回答
        "trace": AgentTrace,        # 详细过程
        "messages": list,           # 完整对话历史（含 tool 消息）
        "provider": str,            # 实际用了哪个 provider
        "model": str,
      }
    """
    # 选 Provider
    if provider is None:
        provider = get_provider(provider_name) if provider_name else None
    if provider is None:
        provider = get_default_provider()
    if provider is None:
        return {
            "error": "未配置 LLM Provider。请先在 Settings 里添加至少一个 provider",
            "answer": "",
        }

    # 组装 messages
    messages: list[dict] = []
    messages.append({"role": "system",
                     "content": system_prompt or DEFAULT_SYSTEM_PROMPT})
    if history:
        for m in history:
            if m.get("role") in ("user", "assistant", "tool"):
                messages.append(m)
    messages.append({"role": "user", "content": user_message})

    # Tool schemas
    tool_schemas = get_tool_schemas(for_type=provider.type)
    max_iter = max_iterations or provider.max_iterations

    trace = AgentTrace()
    start = time.time()

    final_content = ""
    for it in range(max_iter):
        try:
            resp = chat_completion(provider, messages, tools=tool_schemas)
        except Exception as e:
            trace.iterations.append({
                "iter": it + 1,
                "error": f"{type(e).__name__}: {e}",
            })
            return {
                "answer": "",
                "error": str(e),
                "provider": provider.name,
                "model": provider.model,
                "trace": _trace_to_dict(trace),
                "messages": messages,
            }

        tokens = _extract_usage_tokens(resp.get("usage"))
        trace.total_tokens += tokens

        content     = resp.get("content", "") or ""
        tool_calls  = resp.get("tool_calls") or []
        finish      = resp.get("finish_reason", "")

        iter_rec = {
            "iter": it + 1,
            "finish_reason": finish,
            "content_preview": content[:200] if content else "",
            "tool_calls": [{"name": t["name"],
                             "args_preview": json.dumps(t["arguments"],
                                                         ensure_ascii=False)[:200]}
                           for t in tool_calls],
            "tokens": tokens,
        }
        trace.iterations.append(iter_rec)

        # 把 assistant 的这一轮消息记进去（含 tool_calls）
        assistant_msg = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": t.get("id") or f"call_{it}_{i}",
                 "type": "function",
                 "function": {
                     "name": t["name"],
                     "arguments": json.dumps(t["arguments"], ensure_ascii=False)
                 }} for i, t in enumerate(tool_calls)
            ]
        messages.append(assistant_msg)

        # 没调工具，流程结束
        if not tool_calls:
            final_content = content
            break

        # 执行工具
        tool_results = []
        for i, tc in enumerate(tool_calls):
            call_id = tc.get("id") or f"call_{it}_{i}"
            name    = tc["name"]
            args    = tc.get("arguments") or {}
            result  = run_tool(name, args)
            trace.tool_calls_count += 1
            tool_results.append({
                "tool_call_id": call_id,
                "name": name,
                "result_preview": json.dumps(result, ensure_ascii=False,
                                              default=str)[:500],
                "ok": result.get("ok"),
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })
        iter_rec["tool_results"] = tool_results

    else:
        # 跑满 iter 仍有 tool_calls 要执行 → 用最后一次 content
        final_content = (final_content
                         or (trace.iterations[-1].get("content_preview", "") if trace.iterations else ""))

    trace.elapsed_sec = round(time.time() - start, 2)

    return {
        "answer": final_content,
        "provider": provider.name,
        "model": provider.model,
        "trace": _trace_to_dict(trace),
        "messages": messages,
    }


def _trace_to_dict(t: AgentTrace) -> dict:
    return {
        "iterations": t.iterations,
        "total_tokens": t.total_tokens,
        "tool_calls_count": t.tool_calls_count,
        "elapsed_sec": t.elapsed_sec,
        "iter_count": len(t.iterations),
    }


class AgentRuntime:
    """可复用的多轮会话容器（可选，方便以后做持续对话）。"""

    def __init__(self, provider: Optional[LLMProvider] = None,
                 system_prompt: Optional[str] = None):
        self.provider = provider or get_default_provider()
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.history: list[dict] = []

    def chat(self, user_message: str) -> dict:
        result = run_agent_turn(
            user_message=user_message,
            provider=self.provider,
            system_prompt=self.system_prompt,
            history=self.history,
        )
        # 追加到 history（只保留 user / assistant 摘要，不带工具中间轮）
        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant",
                              "content": result.get("answer", "")})
        return result
