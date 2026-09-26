import json
from decimal import Decimal
from unittest.mock import MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from apps.products.models import Product, ProductVariant, Category, Stock
from apps.cart.models import Cart
from ai.context import set_current_user, reset_current_user
from ai.state import AgentState
from ai.nodes import agent_node, execute_tools_node, respond_node, should_continue
from ai.graph import create_shopping_graph

User = get_user_model()


class LangGraphDynamicAgentTestCase(TestCase):
    """
    Test suite for the dynamic LangGraph shopping agent.
    Verifies:
    - State initialization and maintenance
    - Dynamic tool decision loop
    - Sequential execution (no parallel/asyncio.gather)
    - Multi-step tool chaining
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="graph_user",
            email="graph_user@example.com",
            password="Password123!",
            is_email_verified=True,
            is_activated=True,
        )
        self.category = Category.objects.create(name="Footwear", slug="footwear")
        self.product = Product.objects.create(
            name="Nike Air Max 2026",
            slug="nike-air-max-2026",
            brand="Nike",
            description="Athletic shoes",
            is_active=True,
        )
        self.product.cat.add(self.category)

        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="NK-AIR26",
            slug="nike-air-max-2026-black",
            price=Decimal("120.00"),
            is_active=True,
        )
        self.stock = Stock.objects.create(
            variant=self.variant,
            quantity=8,
            reserved_quantity=0,
        )

    def test_state_structure(self):
        """Verify AgentState schema fields."""
        state: AgentState = {
            "messages": [HumanMessage(content="Hello")],
            "user_request": "Hello",
            "tool_results": [],
            "current_product": None,
            "final_response": None,
        }
        self.assertEqual(state["user_request"], "Hello")
        self.assertEqual(len(state["messages"]), 1)
        self.assertIsNone(state["current_product"])
        self.assertIsNone(state["final_response"])

    def test_should_continue_routing(self):
        """Verify conditional router detects tool calls vs final response."""
        # Message with tool calls -> execute_tools
        msg_with_tools = AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "get_cart", "args": {}}],
        )
        state_tools: AgentState = {
            "messages": [msg_with_tools],
            "user_request": "Check cart",
            "tool_results": [],
            "current_product": None,
            "final_response": None,
        }
        self.assertEqual(should_continue(state_tools), "execute_tools")

        # Message without tool calls -> respond
        msg_no_tools = AIMessage(content="Here is your answer.")
        state_no_tools: AgentState = {
            "messages": [msg_no_tools],
            "user_request": "Hello",
            "tool_results": [],
            "current_product": None,
            "final_response": None,
        }
        self.assertEqual(should_continue(state_no_tools), "respond")

    def test_execute_tools_node_sequential_execution(self):
        """
        Verify execute_tools_node executes multiple tool calls sequentially,
        updates tool_results and current_product in state.
        """
        token = set_current_user(self.user)
        try:
            aimsg = AIMessage(
                content="",
                tool_calls=[
                    {"id": "call_1", "name": "search_by_brand", "args": {"brand": "Nike"}},
                    {"id": "call_2", "name": "check_stock", "args": {"product_slug": "nike-air-max-2026"}},
                ],
            )
            state: AgentState = {
                "messages": [HumanMessage(content="Find Nike and check stock"), aimsg],
                "user_request": "Find Nike and check stock",
                "tool_results": [],
                "current_product": None,
                "final_response": None,
            }

            updates = execute_tools_node(state)
            self.assertEqual(len(updates["messages"]), 2)
            self.assertIsInstance(updates["messages"][0], ToolMessage)
            self.assertIsInstance(updates["messages"][1], ToolMessage)
            self.assertEqual(len(updates["tool_results"]), 2)

            # Check that current_product was populated from tool execution
            self.assertIsNotNone(updates["current_product"])
            self.assertEqual(updates["current_product"]["slug"], "nike-air-max-2026")
        finally:
            reset_current_user(token)

    def test_respond_node_extracts_final_response(self):
        """Verify respond_node populates final_response cleanly."""
        state: AgentState = {
            "messages": [AIMessage(content="Your cart contains 2 items totaling ₹240.00.")],
            "user_request": "What's in my cart?",
            "tool_results": [],
            "current_product": None,
            "final_response": None,
        }
        updates = respond_node(state)
        self.assertEqual(updates["final_response"], "Your cart contains 2 items totaling ₹240.00.")

    def test_dynamic_multi_step_tool_chaining(self):
        """
        Test the dynamic LangGraph execution loop with a mocked LLM.
        Scenario:
        1. User asks: "Find Nike shoes under ₹5000 that are in stock"
        2. LLM Step 1: dynamically calls search_by_brand(brand="Nike")
        3. LangGraph runs execute_tools_node sequentially -> returns ToolMessage
        4. LLM Step 2: inspects Nike shoes, dynamically calls check_stock(product_slug="nike-air-max-2026")
        5. LangGraph runs execute_tools_node sequentially -> returns ToolMessage
        6. LLM Step 3: has all required info, outputs final text response
        7. LangGraph terminates at respond_node -> END.
        """
        token = set_current_user(self.user)
        try:
            mock_llm = MagicMock()
            # Simulate multi-step dynamic decision making
            mock_llm.bind_tools.return_value = mock_llm

            # Call sequence:
            # 1st call -> returns tool_call for search_by_brand
            # 2nd call -> returns tool_call for check_stock
            # 3rd call -> returns final AIMessage with text
            response_1 = AIMessage(
                content="",
                tool_calls=[{"id": "tc1", "name": "search_by_brand", "args": {"brand": "Nike"}}],
            )
            response_2 = AIMessage(
                content="",
                tool_calls=[{"id": "tc2", "name": "check_stock", "args": {"product_slug": "nike-air-max-2026"}}],
            )
            response_3 = AIMessage(
                content="Found Nike Air Max 2026 at ₹120.00 with 8 units in stock."
            )

            mock_llm.invoke.side_effect = [response_1, response_2, response_3]

            graph = create_shopping_graph(llm=mock_llm)

            initial_state: AgentState = {
                "messages": [HumanMessage(content="Find Nike shoes under ₹5000 that are in stock")],
                "user_request": "Find Nike shoes under ₹5000 that are in stock",
                "tool_results": [],
                "current_product": None,
                "final_response": None,
            }

            final_state = graph.invoke(initial_state)

            self.assertEqual(
                final_state["final_response"],
                "Found Nike Air Max 2026 at ₹120.00 with 8 units in stock.",
            )
            self.assertEqual(len(final_state["tool_results"]), 2)
            self.assertEqual(final_state["tool_results"][0]["tool"], "search_by_brand")
            self.assertEqual(final_state["tool_results"][1]["tool"], "check_stock")
            self.assertEqual(mock_llm.invoke.call_count, 3)
        finally:
            reset_current_user(token)

    def test_single_tool_dynamic_execution(self):
        """
        Scenario: "What's in my cart?"
        Agent dynamically calls ONLY get_cart, then produces final response.
        """
        token = set_current_user(self.user)
        try:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm

            response_1 = AIMessage(
                content="",
                tool_calls=[{"id": "tc_cart", "name": "get_cart", "args": {}}],
            )
            response_2 = AIMessage(
                content="Your cart is currently empty."
            )
            mock_llm.invoke.side_effect = [response_1, response_2]

            graph = create_shopping_graph(llm=mock_llm)

            initial_state: AgentState = {
                "messages": [HumanMessage(content="What's in my cart?")],
                "user_request": "What's in my cart?",
                "tool_results": [],
                "current_product": None,
                "final_response": None,
            }

            final_state = graph.invoke(initial_state)
            self.assertEqual(final_state["final_response"], "Your cart is currently empty.")
            self.assertEqual(len(final_state["tool_results"]), 1)
            self.assertEqual(final_state["tool_results"][0]["tool"], "get_cart")
        finally:
            reset_current_user(token)
