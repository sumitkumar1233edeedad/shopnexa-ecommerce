import contextvars
from typing import Any

# ContextVar to safely inject and scope the authenticated user per execution thread/task
_current_user_var: contextvars.ContextVar[Any] = contextvars.ContextVar("current_user", default=None)


def set_current_user(user: Any) -> contextvars.Token:
    """
    Set the current authenticated Django user in contextvars.
    Returns a token that MUST be used to reset the context later.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionError("Cannot set unauthenticated user in AI context.")
    return _current_user_var.set(user)


def get_current_user() -> Any:
    """
    Retrieve the current authenticated Django user from contextvars.
    Rejects unauthenticated requests or calls outside user context.
    """
    user = _current_user_var.get()
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionError("User is not authenticated or AI user context is missing.")
    return user


def reset_current_user(token: contextvars.Token) -> None:
    """
    Reset the current user context using the token returned by set_current_user.
    """
    if token is not None:
        _current_user_var.reset(token)
