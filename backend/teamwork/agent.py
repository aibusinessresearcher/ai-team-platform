"""Agent abstractions for multi-LLM teamwork experiments."""

from typing import Any, Dict

from .backends import LLMBackend
from .conversation import Trajectory, Turn
from .profiles import AgentProfile


class TeamAgent:
    """Encapsulates a single language-model agent."""

    def __init__(self, profile: AgentProfile, backend: LLMBackend):
        self.profile = profile
        self.backend = backend
        self.trajectory = Trajectory()

    def act(self) -> Turn:
        """Generate the next turn based on the agent's current trajectory."""

        response_text = self.backend.invoke(
            agent_profile=self.profile,
            trajectory=self.trajectory,
        )
        turn = Turn(speaker_id=self.profile.agent_id, content=response_text)
        self.trajectory.append(turn)
        return turn

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": {
                "agent_id": self.profile.agent_id,
                "name": self.profile.name,
                "role": self.profile.role,
                "system_prompt": self.profile.system_prompt,
                "persona": self.profile.persona,
                "hidden_context": self.profile.hidden_context,
                "metadata": self.profile.metadata,
            },
            "state": {
                "trajectory": self.trajectory.as_dict(),
            },
        }
