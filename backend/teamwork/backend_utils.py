"""Shared utilities for backend setup across experiment run scripts."""

import os
from typing import Any, Optional

from teamwork.backends import LLMBackend, create_backend


def get_api_key(config: Any, provider: str) -> str:
    """Get API key for the specified provider from config object.

    Args:
        config: Config object with openai_api_key, anthropic_api_key, openrouter_api_key attributes
        provider: Provider name (openai, anthropic, gemini)

    Returns:
        API key string for the provider

    Raises:
        ValueError: If provider is unknown or API key not found
    """
    provider = provider.lower()

    if provider == "openai":
        api_key = getattr(config, "openai_api_key", None) or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in config or environment")
        return api_key
    elif provider == "anthropic":
        api_key = getattr(config, "anthropic_api_key", None) or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in config or environment")
        return api_key
    elif provider == "gemini_direct":
        api_key = getattr(config, "gemini_api_key", None) or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in config or environment")
        return api_key
    elif provider == "gemini":
        if not hasattr(config, "openrouter_api_key") or not config.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY not found in config or environment")
        return config.openrouter_api_key
    elif provider == "rcgenai":
        if not hasattr(config, "rcgenai_api_key") or not config.rcgenai_api_key:
            raise ValueError("RCGENAI_API_KEY not found in config or environment")
        return config.rcgenai_api_key
    else:
        raise ValueError(f"Unknown provider: {provider}")


def create_backend_from_config(
    backend_cfg: Any,
    api_key: str,
    seed: Optional[int] = None,
    **extra_params: Any
) -> LLMBackend:
    """Create a backend from a BackendConfig or AgentBackendConfig object.

    Args:
        backend_cfg: Backend config object with provider, model, temperature attributes
        api_key: API key for the provider
        seed: Random seed for deterministic outputs
        **extra_params: Additional parameters to pass to the backend

    Returns:
        Configured LLMBackend instance
    """
    backend_params: dict[str, Any] = {}
    if hasattr(backend_cfg, "temperature") and backend_cfg.temperature is not None:
        backend_params["temperature"] = backend_cfg.temperature
    backend_params.update(extra_params)

    return create_backend(
        provider=backend_cfg.provider,
        api_key=api_key,
        model=backend_cfg.model,
        seed=seed,
        **backend_params
    )


def get_model_name_from_backend(backend: LLMBackend, provider: str) -> str:
    """Extract model name from backend for agent naming.

    Args:
        backend: LLMBackend instance
        provider: Provider name as fallback

    Returns:
        Model name string
    """
    return getattr(backend, "model", None) or getattr(backend, "model_name", provider)


def sanitize_model_name_for_summary(model_name: str) -> str:
    """Sanitize model names for backend summary strings.

    Replaces dots, dashes, and colons with underscores for readability.

    Args:
        model_name: Raw model name

    Returns:
        Sanitized model name
    """
    return model_name.replace(".", "_").replace("-", "_").replace(":", "_")


def build_backend_summary(agent_backends: list[Any]) -> str:
    """Build backend summary string from agent_backends config.

    Args:
        agent_backends: List of AgentBackendConfig objects

    Returns:
        Backend summary string (e.g., "openai_gpt_4o_mini-anthropic_claude_3_5_haiku")
    """
    summary_parts = []
    for backend_cfg in agent_backends:
        provider = backend_cfg.provider
        if backend_cfg.model:
            sanitized_model = sanitize_model_name_for_summary(backend_cfg.model)
            summary_parts.append(f"{provider}_{sanitized_model}")
        else:
            summary_parts.append(provider)
    return "-".join(summary_parts)

