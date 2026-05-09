"""
Agent 层：底层 Skill → Tool Registry → LLM Provider → Runtime。

用户把自然语言问题丢给 agent，agent 让 LLM 自己选择调用哪个工具（SQP / GEO
审计 / Rufus 调研 / 标题分析等），执行后把结果喂回去，直到产出最终答案。
"""
from .providers import (
    LLMProvider, list_providers, get_provider,
    get_default_provider, probe_provider,
)
from .tools_registry import TOOLS, get_tool_schemas, run_tool
from .runtime import AgentRuntime, run_agent_turn
