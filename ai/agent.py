from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from .graph import create_shopping_graph


def get_shopping_agent(llm: Optional[BaseChatModel] = None):
    """
    Constructs and returns the dynamic LangGraph Shopping Assistant agent.
    Orchestrated with LangGraph state, dynamic tool routing, and sequential tool execution.
    """
    return create_shopping_graph(llm=llm)
