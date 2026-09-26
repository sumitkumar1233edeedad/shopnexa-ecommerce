from typing import Any, List, Optional
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from .context import set_current_user, reset_current_user
from .agent import get_shopping_agent
from .state import AgentState


def _format_chat_history(chat_history: Optional[List[Any]]) -> List[BaseMessage]:
    """Helper to convert various chat history formats into LangChain BaseMessage objects."""
    messages: List[BaseMessage] = []
    if not chat_history:
        return messages

    for item in chat_history:
        if isinstance(item, BaseMessage):
            messages.append(item)
        elif isinstance(item, dict):
            role = item.get("role", "").lower()
            content = item.get("content", "")
            if role in ("user", "human"):
                messages.append(HumanMessage(content=content))
            elif role in ("assistant", "ai"):
                messages.append(AIMessage(content=content))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            human_text, ai_text = item
            if human_text:
                messages.append(HumanMessage(content=str(human_text)))
            if ai_text:
                messages.append(AIMessage(content=str(ai_text)))

    return messages


def _extract_response_text(result: Any) -> str:
    """Helper to extract clean text content from the compiled agent graph output."""
    if isinstance(result, dict):
        final_resp = result.get("final_response")
        if final_resp and isinstance(final_resp, str) and final_resp.strip():
            return final_resp.strip()

        if "messages" in result and result["messages"]:
            last_message = result["messages"][-1]
            content = getattr(last_message, "content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                text_parts = [
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                ]
                return "".join(text_parts).strip()
            return str(content).strip()

    if isinstance(result, str):
        return result.strip()
    return str(result).strip()


def run_ai_chat(
    user: Any,
    message: str,
    chat_history: Optional[List[Any]] = None,
    agent: Optional[Any] = None,
) -> str:
    """
    Synchronously execute AI chat interaction for an authenticated user.
    Sets ContextVar for user-scoped tool execution, invokes LangGraph agent with clean state,
    and guarantees cleanup with try/finally.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionError("User is not authenticated. AI chat requires an authenticated user.")

    if not message or not message.strip():
        raise ValueError("Message cannot be empty.")

    token = set_current_user(user)
    try:
        active_agent = agent if agent is not None else get_shopping_agent()
        messages = _format_chat_history(chat_history)
        messages.append(HumanMessage(content=message.strip()))

        initial_state: AgentState = {
            "messages": messages,
            "user_request": message.strip(),
            "tool_results": [],
            "current_product": None,
            "final_response": None,
        }

        result = active_agent.invoke(initial_state)
        return _extract_response_text(result)
    finally:
        reset_current_user(token)


async def arun_ai_chat(
    user: Any,
    message: str,
    chat_history: Optional[List[Any]] = None,
    agent: Optional[Any] = None,
) -> str:
    """
    Asynchronously execute AI chat interaction for an authenticated user.
    Sets ContextVar for user-scoped tool execution, invokes LangGraph agent with clean state,
    and guarantees cleanup with try/finally.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionError("User is not authenticated. AI chat requires an authenticated user.")

    if not message or not message.strip():
        raise ValueError("Message cannot be empty.")

    token = set_current_user(user)
    try:
        active_agent = agent if agent is not None else get_shopping_agent()
        messages = _format_chat_history(chat_history)
        messages.append(HumanMessage(content=message.strip()))

        initial_state: AgentState = {
            "messages": messages,
            "user_request": message.strip(),
            "tool_results": [],
            "current_product": None,
            "final_response": None,
        }

        result = await active_agent.ainvoke(initial_state)
        return _extract_response_text(result)
    finally:
        reset_current_user(token)
