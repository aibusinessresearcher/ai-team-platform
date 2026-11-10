"""Launch the research engine from a GUI study and shape the result for the dashboard."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Optional

_REPO = Path(__file__).resolve().parents[2]
_EXPERIMENTS = _REPO / "backend" / "interactive_experiments"
for _path in (str(_REPO / "backend"), str(_EXPERIMENTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def engine_status() -> tuple[bool, str]:
    try:
        import service  # type: ignore
        return True, str(service.PROMPT_FILE.name)
    except Exception as exc:
        return False, str(exc)


def _model_slug(params: dict) -> str:
    models = params.get("selected_models") or []
    slug = models[0] if models else params.get("provider_model") or "mock"
    return str(slug or "mock")


def _temperature(params: dict) -> Optional[float]:
    raw = params.get("temperature")
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _seed(params: dict, sim_id: int) -> Optional[int]:
    raw = params.get("random_seed")
    if raw is None or raw == "":
        return None
    try:
        return int(raw) + max(sim_id - 1, 0)
    except (TypeError, ValueError):
        return None


def run_gui_simulation(
    sim_id: int,
    params: dict,
    on_between_rounds: Optional[Callable[[], str]] = None,
    on_turn: Optional[Callable[[dict], None]] = None,
) -> dict[str, Any]:
    """Run one replication of the student-body-president task."""
    import service  # type: ignore

    model_slug = _model_slug(params)
    study = service.run_study(
        num_agents=int(params.get("num_agents") or 4),
        max_rounds=int(params.get("num_rounds") or params.get("max_rounds") or 2),
        team_structure=str(params.get("team_structure") or "team"),
        model_slug=model_slug,
        api_key=str(params.get("api_key") or ""),
        temperature=_temperature(params),
        seed=_seed(params, sim_id),
        human_interaction=on_between_rounds is not None,
        on_between_rounds=on_between_rounds,
        on_turn=on_turn,
    )
    transcript = study["transcript"]
    agent_turns = [turn for turn in transcript if turn.get("actor_type") != "human"]
    human_turns = [turn for turn in transcript if turn.get("actor_type") == "human"]
    agreement = study["agreement_score"] if study["agreement_score"] is not None else 0
    summary = {
        "num_turns": len(transcript),
        "num_agent_turns": len(agent_turns),
        "num_human_events": len(human_turns),
        "total_input_tokens": study["input_tokens"],
        "total_output_tokens": study["output_tokens"],
        "total_tokens": study["input_tokens"] + study["output_tokens"],
        "avg_latency_ms": 0,
        "models_used": [study["model"]],
        "agreement_score": agreement,
        "toy_agreement_score": agreement,
        "l1_error": study["l1_error"],
        "round_scores": study["scores"],
        "research_task": study["research_task"],
        "research_provider": study["provider"],
    }
    return {
        "sim_id": sim_id,
        "config": {
            "num_agents": study["num_agents"],
            "num_rounds": study["max_rounds"],
            "team_structure": study["team_structure"],
            "provider_model": study["model"],
            "selected_models": [study["model"]],
            "research_task": study["research_task"],
            "research_engine": True,
        },
        "transcript": transcript,
        "answers": study["answers"],
        "summary": summary,
        "save_dir": study["save_dir"],
    }
