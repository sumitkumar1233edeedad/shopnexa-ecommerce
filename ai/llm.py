import os
from django.conf import settings
from langchain_core.language_models.chat_models import BaseChatModel


def get_llm(provider: str | None = None) -> BaseChatModel:
    """
    Instantiate and return the configured LangChain chat model.
    Supports 'groq', 'openai', and 'nvidia'.
    Reads credentials from Django settings or environment variables.
    Raises RuntimeError if no provider is properly configured.
    """
    openai_api_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "").strip()
    openai_model_name = getattr(settings, "OPENAI_MODEL_NAME", "") or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini").strip()

    groq_api_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "").strip()
    groq_model_name = getattr(settings, "GROQ_MODEL_NAME", "") or os.getenv("GROQ_MODEL_NAME", "openai/gpt-oss-120b").strip()

    nvidia_api_key = getattr(settings, "NVIDIA_API_KEY", "") or os.getenv("NVIDIA_API_KEY", "").strip()
    nvidia_model_name = (getattr(settings, "NVIDIA_MODEL_NAME", "") or os.getenv("NVIDIA_MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b")).strip()
    

    # Normalize provider request (defaults to 'groq')
    configured_provider = getattr(settings, "AI_PROVIDER", "") or os.getenv("AI_PROVIDER", "groq")
    selected_provider = (provider or configured_provider or "groq").strip().lower()

    if selected_provider == "groq" or (not selected_provider and groq_api_key):
        if not groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured in Django settings or environment.")
        from langchain_groq import ChatGroq
        return ChatGroq(
            api_key=groq_api_key,
            model_name=groq_model_name,
            temperature=0.0,
            max_retries=2,
            request_timeout=60.0,
        )

    if selected_provider == "openai" or (not selected_provider and openai_api_key):
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured in Django settings or environment.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=openai_api_key,
            model_name=openai_model_name,
            temperature=0.0,
            max_retries=2,
            request_timeout=60.0,
        )

    if selected_provider in ("nvidia", "navidia") or (not selected_provider and nvidia_api_key):
        if not nvidia_api_key:
            raise RuntimeError("NVIDIA_API_KEY is not configured in Django settings or environment.")
        
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        return ChatNVIDIA(
            api_key=nvidia_api_key,
            model=nvidia_model_name,
            temperature=0.0,
        )
         
        

    raise RuntimeError(
        "No AI model provider configured. Please set either OPENAI_API_KEY, GROQ_API_KEY, or NVIDIA_API_KEY in your environment or Django settings."
    )
