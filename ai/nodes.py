import json
import uuid
from typing import Any, Dict, List, Optional
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from langchain_core.language_models.chat_models import BaseChatModel

from .state import AgentState
from .prompts import SHOPPING_ASSISTANT_SYSTEM_PROMPT
from .tools import ALL_TOOLS, TOOL_MAP
from .llm import get_llm


def _extract_product_from_result(tool_name: str, result_data: Any) -> Optional[Dict[str, Any]]:
    """
    Helper to detect and extract product context from tool output
    to populate state['current_product'].
    """
    if not isinstance(result_data, dict):
        return None

    # 1. Single product result (e.g., get_product_details, check_stock, get_product_price)
    if "slug" in result_data or "product_slug" in result_data:
        slug = result_data.get("slug") or result_data.get("product_slug")
        name = result_data.get("name") or result_data.get("product_name") or slug
        return {
            "slug": slug,
            "name": name,
            "price": result_data.get("price") or result_data.get("min_price"),
            "variant_slug": result_data.get("variant_slug"),
            "in_stock": result_data.get("in_stock") or result_data.get("is_in_stock"),
        }

    # 2. List of product results (e.g., search_products, search_by_brand, search_by_price, search_category)
    results_list = result_data.get("results")
    if isinstance(results_list, list) and results_list:
        first = results_list[0]
        if isinstance(first, dict) and "slug" in first:
            return {
                "slug": first["slug"],
                "name": first.get("name"),
                "price": first.get("price") or first.get("min_price"),
                "brand": first.get("brand"),
                "in_stock": first.get("in_stock"),
            }

    # 3. Cart / Wishlist items
    items_list = result_data.get("items")
    if isinstance(items_list, list) and items_list:
        first = items_list[0]
        if isinstance(first, dict) and ("product_slug" in first or "slug" in first):
            return {
                "slug": first.get("product_slug") or first.get("slug"),
                "name": first.get("product_name") or first.get("name"),
                "price": first.get("price"),
                "variant_slug": first.get("variant_slug"),
            }

    return None


def agent_node(state: AgentState, llm: Optional[BaseChatModel] = None) -> Dict[str, Any]:
    """
    Reasoning Node:
    Prepares conversation messages with system prompt and context,
    invokes the LLM bound with tools, and dynamically decides next action.
    """
    active_llm = llm if llm is not None else get_llm()
    llm_with_tools = active_llm.bind_tools(ALL_TOOLS)

    raw_messages = list(state.get("messages") or [])

    # Ensure system prompt is present at the start of conversation
    has_system = any(isinstance(m, SystemMessage) for m in raw_messages)
    messages_to_send: List[BaseMessage] = []

    if not has_system:
        messages_to_send.append(SystemMessage(content=SHOPPING_ASSISTANT_SYSTEM_PROMPT))

    # Add active context hint if current_product is tracked
    current_product = state.get("current_product")
    if current_product and isinstance(current_product, dict):
        context_hint = (
            f"[System Context]: The active product currently discussed or viewed is "
            f"'{current_product.get('name')}' (slug: '{current_product.get('slug')}'). "
            f"If the user refers to 'that one', 'it', or 'the cheapest one', use this context."
        )
        messages_to_send.append(SystemMessage(content=context_hint))

    messages_to_send.extend(raw_messages)

    response = llm_with_tools.invoke(messages_to_send)

    updates: Dict[str, Any] = {"messages": [response]}
    tool_calls = getattr(response, "tool_calls", None)

    # If no tool calls were generated, this is the final response
    if not tool_calls:
        content = response.content
        if isinstance(content, list):
            text_parts = [
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            ]
            updates["final_response"] = "".join(text_parts)
        else:
            updates["final_response"] = str(content or "")

    return updates


def execute_tools_node(state: AgentState) -> Dict[str, Any]:
    """
    Sequential Tool Execution Node:
    Strictly executes tool calls one-by-one in sequence (no parallel execution / no asyncio.gather).
    Inspects each result, updates state (tool_results and current_product),
    and appends ToolMessages.
    """
    messages = state.get("messages") or []
    if not messages:
        return {}

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    if not tool_calls:
        return {}

    tool_messages: List[ToolMessage] = []
    new_results: List[Dict[str, Any]] = []
    current_product = state.get("current_product")

    # Strictly sequential execution loop
    for tc in tool_calls:
        tool_name = tc.get("name", "")
        tool_args = tc.get("args") or {}
        call_id = tc.get("id") or str(uuid.uuid4())

        tool_instance = TOOL_MAP.get(tool_name)
        if not tool_instance:
            result_str = json.dumps({
                "success": False,
                "error": f"Tool '{tool_name}' not found.",
            })
            parsed_result = {"success": False, "error": f"Tool '{tool_name}' not found."}
        else:
            try:
                raw_result = tool_instance.invoke(tool_args)
                result_str = raw_result if isinstance(raw_result, str) else json.dumps(raw_result)
                try:
                    parsed_result = json.loads(result_str)
                except Exception:
                    parsed_result = {"raw": result_str}
            except Exception as exc:
                result_str = json.dumps({
                    "success": False,
                    "error": f"Error executing tool '{tool_name}': {str(exc)}",
                })
                parsed_result = {"success": False, "error": str(exc)}

        # Update product context from result if detected
        extracted_prod = _extract_product_from_result(tool_name, parsed_result)
        if extracted_prod:
            current_product = extracted_prod

        new_results.append({
            "tool": tool_name,
            "args": tool_args,
            "result": parsed_result,
        })

        tool_messages.append(
            ToolMessage(
                content=result_str,
                tool_call_id=call_id,
                name=tool_name,
            )
        )

    accumulated_results = list(state.get("tool_results") or []) + new_results

    return {
        "messages": tool_messages,
        "tool_results": accumulated_results,
        "current_product": current_product,
    }


def should_continue(state: AgentState) -> str:
    """
    Conditional routing function:
    Inspects whether the agent requested tool calls.
    - If yes -> route to 'execute_tools'
    - If no -> route to 'respond'
    """
    messages = state.get("messages") or []
    if not messages:
        return "respond"

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None)
    if tool_calls and len(tool_calls) > 0:
        return "execute_tools"

    return "respond"


def respond_node(state: AgentState) -> Dict[str, Any]:
    """
    Final Response Node:
    Extracts the clean final text response from the last message in state.
    """
    final_resp = state.get("final_response")
    if final_resp:
        return {"final_response": final_resp}

    messages = state.get("messages") or []
    if messages:
        last_message = messages[-1]
        content = getattr(last_message, "content", "")
        if isinstance(content, list):
            text_parts = [
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            ]
            final_resp = "".join(text_parts)
        else:
            final_resp = str(content or "")

    return {"final_response": final_resp or "I have processed your request."}
