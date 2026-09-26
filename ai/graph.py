from functools import partial
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import agent_node, execute_tools_node, respond_node, should_continue
from .llm import get_llm


def create_shopping_graph(llm: Optional[BaseChatModel] = None):
    r"""
    Constructs and compiles the dynamic LangGraph shopping agent.

    Graph Architecture:
    [START] -> [agent] <----------------+
                  |                     |
          (should_continue?)            |
            /            \              |
      [execute_tools]    [respond]      |
            |                |          |
            +----------------+----------+
                             |
                           [END]

    - Agent dynamically reasons, selects tools, and inspects results.
    - Tools are executed strictly sequentially (no asyncio.gather / no parallel execution).
    - Results are evaluated iteratively until the agent determines it has enough info.
    """
    active_llm = llm if llm is not None else get_llm()
    bound_agent_node = partial(agent_node, llm=active_llm)

    workflow = StateGraph(AgentState)

    # Register Nodes
    workflow.add_node("agent", bound_agent_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.add_node("respond", respond_node)

    # Set Entry Point
    workflow.set_entry_point("agent")

    # Dynamic Conditional Routing from Agent
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "execute_tools": "execute_tools",
            "respond": "respond",
        },
    )

    # Sequential Loop: after executing tools, return to agent for dynamic reasoning
    workflow.add_edge("execute_tools", "agent")

    # From respond to finish
    workflow.add_edge("respond", END)

    return workflow.compile()
