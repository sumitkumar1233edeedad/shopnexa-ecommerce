from typing import Annotated, Any, Dict, List, Optional, Sequence
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Clean state representation for the dynamic LangGraph shopping assistant.

    Fields:
    - messages: Sequence of conversation messages (Human, AI, Tool, System).
      Uses add_messages reducer to naturally append and preserve conversation history.
    - user_request: The current user message or request string.
    - tool_results: Accumulated list of tool invocation results for reasoning context.
    - current_product: The active or most recently referenced product in context
      (e.g. {'name': '...', 'slug': '...', 'price': '...', 'variant_slug': '...'}),
      enabling seamless resolution of pronouns and references ('that one', 'it', 'the cheapest').
    - final_response: The final string response to be returned to the client.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_request: str
    tool_results: List[Dict[str, Any]]
    current_product: Optional[Dict[str, Any]]
    final_response: Optional[str]
