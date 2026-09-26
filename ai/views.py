from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .services import run_ai_chat, arun_ai_chat


@login_required(login_url="login")
def ai_assistant_view(request):
    """
    Renders the dedicated interactive web view for the STORE AI Shopping Assistant.
    """
    groq_model = getattr(settings, "GROQ_MODEL_NAME", "openai/gpt-oss-120b")
    context = {
        "title": "AI Shopping Assistant — STORE AI",
        "groq_model": groq_model,
        "username": request.user.username,
        "first_name": request.user.first_name or request.user.username,
    }
    return render(request, "ai/assistant.html", context)



class AIChatAPIView(APIView):
    """
    REST API endpoint for interacting with the LangChain AI Shopping Assistant.
    Requires authentication via Token or Session.
    POST /api/ai/chat/
    Body:
    {
        "message": "Show me Nike running shoes",
        "chat_history": [] (optional)
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = request.data.get("message")
        if not message or not str(message).strip():
            return Response(
                {"error": "The 'message' field is required and cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        chat_history = request.data.get("chat_history")
        if chat_history is not None and not isinstance(chat_history, list):
            return Response(
                {"error": "'chat_history' must be a list if provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ai_response = run_ai_chat(
                user=request.user,
                message=str(message).strip(),
                chat_history=chat_history,
            )
            return Response(
                {"response": ai_response},
                status=status.HTTP_200_OK,
            )
        except RuntimeError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except PermissionError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            err_msg = str(e)
            if "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
                return Response(
                    {
                        "error": (
                            "The AI model provider timed out while generating a response. "
                            "Please check your API key, ensure the model name is valid, "
                            "or switch to AI_PROVIDER=groq."
                        )
                    },
                    status=status.HTTP_504_GATEWAY_TIMEOUT,
                )
            if "authorization failed" in err_msg.lower() or "403" in err_msg or "unauthorized" in err_msg.lower():
                return Response(
                    {
                        "error": (
                            "AI model provider authorization failed (403 Forbidden). "
                            "Your NVIDIA_API_KEY is either expired, has 0 remaining credits, "
                            "or requires accepting terms on build.nvidia.com for this model. "
                            "Please generate a fresh key on build.nvidia.com or switch to Groq (AI_PROVIDER=groq)."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            return Response(
                {"error": f"An unexpected error occurred while processing your request: {err_msg}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
