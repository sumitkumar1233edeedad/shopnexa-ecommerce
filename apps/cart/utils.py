from django.db.models import Sum
from .models import CartItem


def get_cart_count(request):
    """
    Calculate and return the total quantity of items in the cart.
    - For authenticated users: Aggregates total quantity from CartItem database records.
    - For guest users: Sums up quantities from session-stored cart.
    """
    if request.user.is_authenticated:
        return (
            CartItem.objects
            .filter(cart__user=request.user)
            .aggregate(total=Sum("quantity"))["total"] or 0
        )

    cart = request.session.get("cart", {})

    return sum(
        item.get("quantity", 0)
        for item in cart.values()
    )
