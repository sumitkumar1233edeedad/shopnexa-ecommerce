from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.customer_chat, name="customer_chat"),
    path("new/", views.start_new_conversation, name="start_new_conversation"),
    path("<slug:conversation_slug>/", views.customer_chat, name="customer_chat_detail"),
]
