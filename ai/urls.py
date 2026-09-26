from django.urls import path
from .views import AIChatAPIView, ai_assistant_view

urlpatterns = [
    path("ai/", ai_assistant_view, name="ai_assistant"),
    path("ai/assistant/", ai_assistant_view, name="ai_assistant_alias"),
    path("api/ai/chat/", AIChatAPIView.as_view(), name="ai_chat"),
]
