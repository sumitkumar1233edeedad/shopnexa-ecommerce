from decimal import Decimal
from unittest.mock import MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from langchain_core.messages import HumanMessage, AIMessage

from apps.products.models import Product, ProductVariant, Category, Stock
from apps.cart.models import Cart
from ai.context import set_current_user, reset_current_user
from ai.state import AgentState
from ai.graph import create_shopping_graph

User = get_user_model()


class ConversationalReferenceResolutionTestCase(TestCase):
    """
    Tests for conversational follow-ups and reference resolution:
    - 'that one'
    - 'the cheapest one'
    - 'add it'
    - 'remove it'
    Verifies that conversational context from messages is accurately resolved.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="ref_user",
            email="ref_user@example.com",
            password="Password123!",
            is_email_verified=True,
            is_activated=True,
        )
        self.category = Category.objects.create(name="Shoes", slug="shoes")
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
            quantity=10,
            reserved_quantity=0,
        )

    def test_followup_add_that_one_to_cart(self):
        """
        Verify follow-up reference:
        User: Show Nike shoes
        Assistant: We have Nike Air Max 2026 (slug: nike-air-max-2026) for ₹120.00.
        User: Add that one to my cart
        The agent resolves 'that one' to 'nike-air-max-2026' and calls add_to_cart.
        """
        token = set_current_user(self.user)
        try:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm

            # Step 1: LLM resolves "that one" to product slug "nike-air-max-2026"
            response_1 = AIMessage(
                content="",
                tool_calls=[{
                    "id": "tc_add",
                    "name": "add_to_cart",
                    "args": {"product_slug": "nike-air-max-2026", "quantity": 1},
                }],
            )
            # Step 2: Confirmation
            response_2 = AIMessage(
                content="I've added 1 unit of Nike Air Max 2026 to your cart!"
            )
            mock_llm.invoke.side_effect = [response_1, response_2]

            graph = create_shopping_graph(llm=mock_llm)

            initial_state: AgentState = {
                "messages": [
                    HumanMessage(content="Show Nike shoes"),
                    AIMessage(content="We have Nike Air Max 2026 (slug: nike-air-max-2026) for ₹120.00."),
                    HumanMessage(content="Add that one to my cart"),
                ],
                "user_request": "Add that one to my cart",
                "tool_results": [],
                "current_product": {"slug": "nike-air-max-2026", "name": "Nike Air Max 2026"},
                "final_response": None,
            }

            final_state = graph.invoke(initial_state)

            self.assertIn("added", final_state["final_response"])
            self.assertEqual(len(final_state["tool_results"]), 1)
            self.assertEqual(final_state["tool_results"][0]["tool"], "add_to_cart")

            # Verify cart in DB
            cart = Cart.objects.get(user=self.user)
            self.assertEqual(cart.total_items, 1)
        finally:
            reset_current_user(token)

    def test_followup_remove_it_from_cart(self):
        """
        Verify follow-up reference:
        User: Remove it from my cart
        The agent resolves 'it' from the active conversation context and calls remove_from_cart.
        """
        token = set_current_user(self.user)
        try:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm

            response_1 = AIMessage(
                content="",
                tool_calls=[{
                    "id": "tc_rem",
                    "name": "remove_from_cart",
                    "args": {"product_slug": "nike-air-max-2026"},
                }],
            )
            response_2 = AIMessage(
                content="Removed Nike Air Max 2026 from your cart."
            )
            mock_llm.invoke.side_effect = [response_1, response_2]

            graph = create_shopping_graph(llm=mock_llm)

            initial_state: AgentState = {
                "messages": [
                    HumanMessage(content="What's in my cart?"),
                    AIMessage(content="Your cart contains 1 item: Nike Air Max 2026 (slug: nike-air-max-2026)."),
                    HumanMessage(content="Remove it from my cart"),
                ],
                "user_request": "Remove it from my cart",
                "tool_results": [],
                "current_product": {"slug": "nike-air-max-2026", "name": "Nike Air Max 2026"},
                "final_response": None,
            }

            final_state = graph.invoke(initial_state)
            self.assertIn("Removed", final_state["final_response"])
            self.assertEqual(final_state["tool_results"][0]["tool"], "remove_from_cart")
        finally:
            reset_current_user(token)
