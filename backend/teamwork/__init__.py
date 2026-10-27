"""Toolkit for experimenting with multi-agent LLM teamwork."""

from .agent import AgentProfile, TeamAgent
from .backends import AnthropicBackend, EchoBackend, LLMBackend, OpenAIBackend, OpenRouterBackend, create_backend
from .conversation import Trajectory, Turn, format_turn_content

__all__ = [
    "AgentProfile",
    "AnthropicBackend",
    "EchoBackend",
    "LLMBackend",
    "OpenAIBackend",
    "OpenRouterBackend",
    "TeamAgent",
    "Trajectory",
    "Turn",
    "create_backend",
    "format_turn_content",
]
