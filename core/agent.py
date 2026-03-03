# -*- coding: utf-8 -*-
"""
core/agent.py — 通用 Agent Loop 运行时
======================================

从 research/researcher.py 提炼而来的通用 tool-calling 循环。
任何 bot 都可以用 AgentLoop 让 LLM 在生成过程中主动调用工具。

使用示例：
  >>> from core.agent import AgentLoop, ToolDef
  >>>
  >>> def my_search(query: str, max_results: int = 5) -> list[dict]:
  ...     return [{"title": "...", "content": "..."}]
  >>>
  >>> agent = AgentLoop(provider="deepseek", system="你是内容策划师")
  >>> agent.add_tool(ToolDef(
  ...     name="web_search",
  ...     description="搜索网页获取信息",
  ...     parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
  ...     fn=my_search,
  ... ))
  >>> result = agent.run("帮我找小红书最近的爆款话题")

设计原则：
  - chat_completion() 保持不变（向后兼容）
  - tool 定义复用 OpenAI function calling 标准
  - 每个 bot 按需注册 tools，不全局加载
  - max_rounds 防止无限循环
  - 支持 response_format 做结构化输出
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from core.llm import _get_client, MAX_RETRIES, BASE_DELAY

log = logging.getLogger("agent")


@dataclass
class ToolDef:
    """一个可被 LLM 调用的工具定义。"""
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]

    def to_openai(self) -> dict:
        """转为 OpenAI function calling 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class AgentResult:
    """AgentLoop 的运行结果。"""
    content: str
    tool_calls_made: list[dict] = field(default_factory=list)
    rounds_used: int = 0


class AgentLoop:
    """
    通用 tool-calling agent 循环。

    LLM 可以在生成过程中调用注册的工具，获取结果后继续思考，
    直到给出最终回答或达到 max_rounds 上限。
    """

    def __init__(
        self,
        *,
        provider: str = "deepseek",
        system: str = "",
        model_override: Optional[str] = None,
        temperature: float = 0.7,
        max_rounds: int = 10,
        response_format: Optional[dict] = None,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
    ):
        """
        参数:
          provider        : LLM 服务商 ("deepseek" / "doubao" / "kimi")
          system          : 系统提示词
          model_override  : 覆盖默认模型
          temperature     : 创造力 (0-1)
          max_rounds      : 最大工具调用轮数
          response_format : 结构化输出 (如 {"type": "json_object"})
          on_tool_call    : 工具调用时的回调 (name, args)，用于 UI 反馈
        """
        self.provider = provider
        self.client, self._default_model = _get_client(provider)
        self.model = model_override or self._default_model
        self.temperature = temperature
        self.max_rounds = max_rounds
        self.response_format = response_format
        self.on_tool_call = on_tool_call

        self._system = system
        self._tools: dict[str, ToolDef] = {}
        self._messages: list[dict] = []
        if system:
            self._messages.append({"role": "system", "content": system})

    def add_tool(self, tool: ToolDef) -> "AgentLoop":
        """注册一个工具。支持链式调用。"""
        self._tools[tool.name] = tool
        return self

    def add_tools(self, tools: list[ToolDef]) -> "AgentLoop":
        """批量注册工具。"""
        for t in tools:
            self._tools[t.name] = t
        return self

    def _openai_tools(self) -> Optional[list[dict]]:
        if not self._tools:
            return None
        return [t.to_openai() for t in self._tools.values()]

    def _execute_tool(self, name: str, args_json: str) -> str:
        """执行工具并返回结果字符串。"""
        tool = self._tools.get(name)
        if not tool:
            return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
        try:
            args = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError:
            args = {}

        if self.on_tool_call:
            try:
                self.on_tool_call(name, args)
            except Exception:
                pass

        try:
            result = tool.fn(**args)
            if isinstance(result, (list, dict)):
                text = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                text = str(result)
            if len(text) > 8000:
                text = text[:8000] + "\n...(结果已截断)"
            return text
        except Exception as e:
            log.warning("Tool %s execution failed: %s", name, e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def _call_llm(self, **extra_kwargs):
        """带重试的 LLM 调用。"""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._messages,
            "temperature": self.temperature,
        }
        tools = self._openai_tools()
        if tools:
            kwargs["tools"] = tools
        if self.response_format:
            kwargs["response_format"] = self.response_format
        kwargs.update(extra_kwargs)

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:
                last_error = e
                is_timeout = "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower()
                status = getattr(e, "status_code", None) or getattr(e, "code", None)
                if attempt < MAX_RETRIES and (status in (429, 500, 502, 503) or is_timeout):
                    time.sleep(BASE_DELAY * (2 ** attempt))
                    continue
                raise
        raise last_error  # type: ignore[misc]

    def run(self, user_message: str) -> AgentResult:
        """
        执行 agent 循环：发送消息 → LLM 可能调用工具 → 执行工具 → 继续，
        直到 LLM 给出最终回答或达到 max_rounds。

        返回 AgentResult，包含最终文本和工具调用记录。
        """
        self._messages.append({"role": "user", "content": user_message})
        tool_log: list[dict] = []

        for round_num in range(self.max_rounds):
            resp = self._call_llm()
            choice = resp.choices[0]
            msg = choice.message

            if not msg.tool_calls:
                answer = msg.content or ""
                self._messages.append({"role": "assistant", "content": answer})
                return AgentResult(
                    content=answer,
                    tool_calls_made=tool_log,
                    rounds_used=round_num + 1,
                )

            self._messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = tc.function.arguments
                log.debug("Tool call: %s(%s)", fn_name, fn_args[:100])

                result_text = self._execute_tool(fn_name, fn_args)
                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })
                tool_log.append({
                    "round": round_num,
                    "tool": fn_name,
                    "args": fn_args[:200],
                    "result_len": len(result_text),
                })

        self._messages.append({
            "role": "user",
            "content": "工具调用轮次已达上限。请根据已收集到的所有信息给出最终回答。",
        })
        resp = self._call_llm()
        answer = resp.choices[0].message.content or ""
        self._messages.append({"role": "assistant", "content": answer})
        return AgentResult(
            content=answer,
            tool_calls_made=tool_log,
            rounds_used=self.max_rounds,
        )

    def run_json(self, user_message: str) -> tuple[Any, AgentResult]:
        """
        run() 的 JSON 版：自动设 response_format 并解析结果。
        返回 (parsed_json, agent_result)。解析失败时 parsed_json 为 None。
        """
        old_fmt = self.response_format
        self.response_format = {"type": "json_object"}
        try:
            result = self.run(user_message)
        finally:
            self.response_format = old_fmt

        try:
            parsed = json.loads(result.content)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        return parsed, result

    @property
    def messages(self) -> list[dict]:
        """当前完整的消息历史（只读视图）。"""
        return list(self._messages)

    def reset(self) -> None:
        """重置对话历史。"""
        self._messages = []
        if self._system:
            self._messages.append({"role": "system", "content": self._system})
