"""Agent profile data structures."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentProfile:
    """Static metadata describing an agent."""

    agent_id: int
    name: str
    role: str
    system_prompt: str
    persona: Optional[str] = None
    hidden_context: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)