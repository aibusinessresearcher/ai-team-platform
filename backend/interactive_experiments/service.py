"""Run the research engine from the web app without the command-line runner.

The Hydra script in run_experiment.py is unchanged. This module is what the
GUI imports so a browser study launches the same scored task.
"""

from __future__ import annotations

import json
import os
import random
import sys
import threading
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any, Callable, Optional

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
for _path in (str(_BACKEND), str(_HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from teamwork.agent import TeamAgent
from teamwork.backends import LLMBackend
from teamwork.backend_utils import create_backend_from_config, get_api_key
from teamwork.conversation import Turn
from teamwork.profiles import AgentProfile

from run_experiment import BackendConfig, MyTaskConfig, save_convo, save_results
import execute

PROMPT_FILE = _HERE / "prompts" / "student_body_president.json"
OUTPUT_ROOT = _BACKEND / "outputs" / "web"
_RUN_LOCK = threading.Lock()
_MAX_L1 = 8.0  # four candidates, even count: n*n/2

_ENV_FOR_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini_direct": "GEMINI_API_KEY",
    "gemini": "OPENROUTER_API_KEY",
    "rcgenai": "RCGENAI_API_KEY",
}

_STRUCTURES = {
    "pooled": "pooled",
    "sequential": "sequential",
    "reciprocal": "reciprocal_chain",
    "reciprocal_chain": "reciprocal_chain",
    "reciprocal_subgroups": "reciprocal_subgroups",
    "reciprocal_comprehensive": "team",
    "team": "team",
    "parallel": "team",
    "hierarchical": "sequential",
}


class MockRankingBackend(LLMBackend):
    """Offline stand-in so a study can be scored without an API key."""

    def invoke(self, *, agent_profile, trajectory) -> str:
        return (
            f"{agent_profile.name} uses the shared evidence and ranks Candidate D first.\n\n"
            "MY RANKING:\n"
            "1. Candidate D\n"
            "2. Candidate C\n"
            "3. Candidate A\n"
            "4. Candidate B"
        )


def resolve_model(model_slug: str) -> tuple[str, str]:
    """Map a GUI model slug to a research-engine provider and model id."""
    slug = (model_slug or "mock").strip()
    low = slug.lower()
    if low in {"mock", "echo"}:
        return "mock", "mock"
    if low.startswith("gemini/"):
        return "gemini_direct", slug.split("/", 1)[1]
    if low.startswith("gemini"):
        return "gemini_direct", slug
    if low.startswith("claude"):
        return "anthropic", slug
    if low.startswith("gpt") or low.startswith(("o1", "o3", "o4")):
        return "openai", slug
    if "kimi" in low:
        return "rcgenai", slug
    raise ValueError(
        f"The research engine cannot run '{slug}'. "
        "Choose Mock, OpenAI, Anthropic, or Gemini."
    )


def map_structure(team_structure: str) -> str:
    key = (team_structure or "team").strip().lower()
    if key not in _STRUCTURES:
        raise ValueError(
            f"Unknown team structure '{team_structure}'. "
            "Use pooled, sequential, reciprocal, or team."
        )
    return _STRUCTURES[key]


def _load_prompts(num_agents: int, max_rounds: int, small_group_rounds: int) -> dict:
    dynamic = {
        "num_agents_minus_one": max(num_agents - 1, 0),
        "num_rounds": max_rounds,
        "small_group_rounds": small_group_rounds,
    }
    text = Template(PROMPT_FILE.read_text(encoding="utf-8")).substitute(dynamic)
    prompts = json.loads(text)
    private = list(prompts.get("agent_private_info") or [])
    while len(private) < num_agents:
        private.append("")
    prompts["agent_private_info"] = private[:num_agents]
    return prompts


def _groups_for(num_agents: int) -> tuple[list[list[int]], list[int]]:
    groups: list[list[int]] = []
    index = 0
    while index < num_agents:
        if index + 1 < num_agents:
            groups.append([index, index + 1])
            index += 2
        elif groups:
            groups[-1].append(index)
            index += 1
        else:
            groups.append([index])
            index += 1
    reps = [group[0] for group in groups]
    return groups, reps


def _build_agents(config: MyTaskConfig, prompts: dict, api_key: Optional[str]) -> list[TeamAgent]:
    agents: list[TeamAgent] = []
    provider = config.backend.provider
    for agent_id in range(config.num_agents):
        others = [aid for aid in range(config.num_agents) if aid != agent_id]
        others_str = ", ".join(f"Agent {aid}" for aid in others) or "no other members"
        role = (
            f"Committee Member.  You are Agent {agent_id}.  "
            f"You are working with {config.num_agents - 1} other committee members "
            f"({others_str}) on this task."
        )
        profile = AgentProfile(
            agent_id=agent_id,
            name=f"Agent-{agent_id}-{provider}-{config.backend.model}",
            role=role,
            system_prompt=prompts["system_prompt"],
            metadata={"backend_provider": provider, "backend_model": config.backend.model},
        )
        agent_seed = config.seed + agent_id if config.seed is not None else None
        if provider == "mock":
            backend = MockRankingBackend(seed=agent_seed)
        else:
            backend = create_backend_from_config(
                backend_cfg=config.backend,
                api_key=api_key or "",
                seed=agent_seed,
            )
        agent = TeamAgent(profile=profile, backend=backend)
        agent.trajectory.append(Turn(speaker_id=-1, content=prompts["task_prompt"]))
        private = prompts["agent_private_info"][agent_id]
        if private:
            agent.trajectory.append(Turn(speaker_id=-1, content=private))
        agents.append(agent)
    return agents


class _KeyConfig:
    def __init__(self, provider: str, api_key: Optional[str]):
        self.openai_api_key = api_key if provider == "openai" else None
        self.anthropic_api_key = api_key if provider == "anthropic" else None
        self.gemini_api_key = api_key if provider == "gemini_direct" else None
        self.openrouter_api_key = api_key if provider == "gemini" else None
        self.rcgenai_api_key = api_key if provider == "rcgenai" else None


def run_study(
    *,
    num_agents: int = 4,
    max_rounds: int = 2,
    team_structure: str = "team",
    model_slug: str = "mock",
    api_key: Optional[str] = None,
    temperature: Optional[float] = 0.7,
    seed: Optional[int] = None,
    human_interaction: bool = False,
    on_between_rounds: Optional[Callable[[], str]] = None,
    on_turn: Optional[Callable[[dict], None]] = None,
    save: bool = True,
) -> dict[str, Any]:
    """Run one student-body-president study and return transcripts plus L1 scores."""
    with _RUN_LOCK:
        return _run_study_locked(
            num_agents=num_agents,
            max_rounds=max_rounds,
            team_structure=team_structure,
            model_slug=model_slug,
            api_key=api_key,
            temperature=temperature,
            seed=seed,
            human_interaction=human_interaction,
            on_between_rounds=on_between_rounds,
            on_turn=on_turn,
            save=save,
        )


def _run_study_locked(
    *,
    num_agents: int,
    max_rounds: int,
    team_structure: str,
    model_slug: str,
    api_key: Optional[str],
    temperature: Optional[float],
    seed: Optional[int],
    human_interaction: bool,
    on_between_rounds: Optional[Callable[[], str]],
    on_turn: Optional[Callable[[dict], None]],
    save: bool,
) -> dict[str, Any]:
    if not 1 <= int(num_agents) <= 7:
        raise ValueError("The research task supports 1 to 7 agents.")
    num_agents = int(num_agents)
    max_rounds = max(1, int(max_rounds))
    structure = map_structure(team_structure)
    provider, model = resolve_model(model_slug)
    small_group_rounds = max(1, min(2, max_rounds))
    groups, reps = _groups_for(num_agents)

    backend_cfg = BackendConfig(
        provider=provider,
        model=model,
        temperature=None if provider == "mock" else temperature,
    )
    config = MyTaskConfig(
        max_rounds=max_rounds,
        team_interdependence_type=structure,
        input_prompt_file=str(PROMPT_FILE),
        randomize_speaking_order=True,
        randomize_final_submitter=True,
        seed=seed,
        task_type="ranking",
        human_interaction=bool(human_interaction or on_between_rounds),
        backend=backend_cfg,
        num_agents=num_agents,
        small_groups=groups,
        small_group_reps=reps,
        small_group_rounds=small_group_rounds,
    )
    prompts = _load_prompts(num_agents, max_rounds, small_group_rounds)

    previous_env = None
    env_name = _ENV_FOR_PROVIDER.get(provider)
    supplied = (api_key or "").strip()
    if provider != "mock" and supplied and env_name:
        previous_env = os.environ.get(env_name)
        os.environ[env_name] = supplied

    try:
        resolved_key = None
        if provider != "mock":
            env_key = os.environ.get(env_name, "") if env_name else ""
            resolved_key = get_api_key(_KeyConfig(provider, supplied or env_key or None), provider)
        if seed is not None:
            random.seed(seed)
        agents = _build_agents(config, prompts, resolved_key)
        transcript: list[dict] = []

        def emit(agent_id: int, text: str, kind: str) -> None:
            record = {
                "agent": "Human" if kind == "human" else f"Agent_{agent_id + 1}",
                "actor_type": kind,
                "turn": len(transcript),
                "text": text,
                "model": "mock" if provider == "mock" else model,
            }
            transcript.append(record)
            if on_turn is not None and kind == "agent":
                on_turn(record)

        for agent in agents:
            original = agent.act

            def act(original=original, agent=agent):
                turn = original()
                emit(agent.profile.agent_id, turn.content, "agent")
                return turn

            agent.act = act

        def between() -> str:
            text = ""
            if on_between_rounds is not None:
                text = on_between_rounds() or ""
            cleaned = str(text).strip()
            if cleaned:
                emit(-1, cleaned, "human")
            return cleaned

        runner = {
            "pooled": execute.pooled_task,
            "sequential": execute.sequential_task,
            "reciprocal_chain": execute.reciprocal_chain_task,
            "reciprocal_subgroups": execute.reciprocal_subgroups_task,
            "team": execute.team_task,
        }[structure]
        answers, scores = runner(
            agents,
            prompts,
            config,
            on_between_rounds=between if (human_interaction or on_between_rounds) else None,
        )
    finally:
        if provider != "mock" and supplied and env_name:
            if previous_env is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = previous_env

    input_tokens = 0
    output_tokens = 0
    for agent in agents:
        stats = getattr(agent.backend, "usage_stats", None)
        if stats is not None:
            input_tokens += stats.input_tokens
            output_tokens += stats.output_tokens

    numeric_scores = [float(score) for score in scores]
    if structure == "pooled" and numeric_scores:
        l1_error = sum(numeric_scores) / len(numeric_scores)
    elif numeric_scores:
        l1_error = numeric_scores[-1]
    else:
        l1_error = None
    agreement = None if l1_error is None else round(max(0.0, min(1.0, 1.0 - (l1_error / _MAX_L1))), 3)

    save_dir = None
    if save:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        save_dir = OUTPUT_ROOT / stamp
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            save_convo(agents, save_dir)
            save_results(config, answers, numeric_scores, save_dir)
        except OSError:
            save_dir = None

    return {
        "research_task": "student_body_president",
        "provider": provider,
        "model": model,
        "team_structure": structure,
        "num_agents": num_agents,
        "max_rounds": max_rounds,
        "transcript": transcript,
        "answers": answers,
        "scores": numeric_scores,
        "l1_error": l1_error,
        "agreement_score": agreement,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "save_dir": str(save_dir) if save_dir else None,
    }
