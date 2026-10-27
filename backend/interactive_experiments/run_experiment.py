"""Launch script for my test task experiments.

Example Usage:

# Single backend mode (all agents use same provider/model):
python interactive_experiments/run_experiment.py task=student_body_president

# Override config parameters:
python interactive_experiments/run_experiment.py task.num_agents=4 task.max_rounds=5 task.seed=100

"""

import os
import sys
import re
import json
from datetime import datetime
from typing import Any, Optional, List, Dict
import random
from string import Template
#import logging

from dotenv import load_dotenv

import hydra  # type: ignore
from omegaconf import DictConfig, OmegaConf  # type: ignore
from pydantic import BaseModel, Field

from teamwork.backend_utils import (
    create_backend_from_config,
    get_api_key,
    get_model_name_from_backend,
)
from teamwork.agent import TeamAgent
from teamwork.conversation import Turn, format_turn_content
from teamwork.profiles import AgentProfile

from collections import Counter
import execute


# Load environment variables from .env file
load_dotenv()


def _configure_console_output() -> None:
    """Escape unsupported display characters without altering stored responses."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="backslashreplace")


# =========================
# CONFIGS
# =========================

class BackendConfig(BaseModel):
    """Configuration for a single backend."""

    provider: str = Field(description="Backend provider (openai, anthropic, gemini, rcgenai)")
    model: Optional[str] = Field(default=None, description="Model name (uses provider default if None)")
    temperature: Optional[float] = Field(default=None, description="Sampling temperature")

class MyTaskConfig(BaseModel):
    """Configuration for my task experiment."""

    max_rounds: int = Field(ge=1, description="Maximum collaboration rounds")
    team_interdependence_type: str = Field(default='pooled', description="Team interdependence type: pooled, sequential, reciprocal_chain, reciprocal_subgroups, team.")    
    input_prompt_file: str = Field(default=None, description="File path for input prompts json.")
    randomize_speaking_order: bool = Field(default=True, description="If True, randomize the speaking order in each round. If False, agents speak in fixed order (agent_ids order).")
    randomize_final_submitter: bool = Field(default=True, description="If True, randomly select an agent to submit the final ranking. If False, always use agent 0.")
    seed: Optional[int] = Field(default=None, description="Random seed for reproducibility")
    task_type: str = Field(default=None, description="Task type: ranking, multiple_choice, short_answer, math")
    human_interaction: bool = Field(default=False, description="If True, allow a human agent to add information during the experiment.")
    
    # Single backend mode
    backend: Optional[BackendConfig] = Field(default=None, description="Single backend config (all agents)")
    num_agents: Optional[int] = Field(default=None, ge=1, le=7, description="Number of agents (single backend mode, max 7 for this task)")
    small_groups: Optional[list[list[int]]] = Field(default=None, description="Agent small groups for recriprocal interdependence type")
    small_group_reps: Optional[list[int]] = Field(default=None, description="Representative agents for recriprocal interdependence type.  Start small group discussions.")
    small_group_rounds: Optional[int] = Field(default=None, description="Number of rounds for small group discussion")

    # API keys
    rcgenai_api_key: Optional[str] = Field(default=None, description="RC GenAI API key")

    def generate_run_name(self, backend_summary: str) -> str:
        """Generate unique experiment run name from config and timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        seed_str = f"_s{self.seed}" if self.seed is not None else ""
        return f"my_task_n{self.num_agents}_r{self.max_rounds}_{self.team_interdependence_type}_{backend_summary}{seed_str}_{timestamp}"

# -------------------
# AGENT CREATION
# -----------------
def create_agents(config: Any, input_prompts: Any) -> list[TeamAgent]: 
    
    # Determine mode and create agents
    agents: list[TeamAgent] = []

    # Get API key
    api_key = get_api_key(config, config.backend.provider)
    
    #initial_system_prompt = input("Enter the initial system prompt.  All agents receive this.\n")
    initial_system_prompt = input_prompts["system_prompt"]
    
    # Create all agents with same backend type but unique instances
    for agent_id in range(config.num_agents):

        # Each agent has 1) profile (creates system prompt), 2) backend, 3) chat trajectory (default: initially empty)
        
        # Set up agent profile     
        other_agent_ids = [aid for aid in range(config.num_agents) if aid != agent_id]
        other_agents_str = ", ".join(f"Agent {aid}" for aid in other_agent_ids)
        role = f"Committee Member.  You are Agent {agent_id}.  You are working with {config.num_agents-1} other committee members ({other_agents_str}) on this task."
        
        profile = AgentProfile(
                    agent_id=agent_id,
                    name=f"Agent-{agent_id}-{config.backend.provider}-{config.backend.model}",
                    role=role,
                    system_prompt=initial_system_prompt,
                    metadata={"backend_provider": config.backend.provider, "backend_model": config.backend.model}
                )

        # Set up agent backend
        agent_seed = config.seed + agent_id if config.seed is not None else None
        backend = create_backend_from_config(
            backend_cfg=config.backend,
            api_key=api_key,
            seed=agent_seed
        )

        # add agent to list
        agents.append(
            TeamAgent(
                profile=profile,
                backend=backend
            )
        )

    # Task Prompt - generic info for all agents (For example, initial ranking prompt)
    #initial_task_prompt = input("Enter the initial task prompt.  All agents receive this.\n")
    initial_task_prompt = input_prompts["task_prompt"]
    
    for i, agent in enumerate(agents):
        # add initial task prompt to each agent trajectory
        agent.trajectory.append(Turn(speaker_id=-1, content=initial_task_prompt))

        # add private info to agent trajectory
        #priv_info = input(f"Enter any private information for agent {agent.profile.agent_id}.  If none, hit enter.\n")
        priv_info = input_prompts["agent_private_info"][i]
        if priv_info:
            agent.trajectory.append(Turn(speaker_id=-1, content=priv_info))
        
    return agents

# ------------------------------------
# SAVE AGENT CONVERSATION AND RESULTS
# ------------------------------------

def save_convo(agents, save_dir):
    
    # save each agent's conversation 
    conversation = {}
    for agent in agents:

        agent_conv = []
        for i, turn in enumerate(agent.trajectory.turns):

            # Determine round number based on turn index
            if i == 0:
                # Turn 0: system prompt
                round_num = "Instructions"
            else:
                # Next turn: this agent's rankings
                round_num = "Stating"
    
            agent_conv.append({
                "turn_number": i,
                "round": round_num,
                "speaker_id": turn.speaker_id,
                "content": format_turn_content(turn, agent.profile.agent_id)
            })
        conversation[f"agent_{agent.profile.agent_id}"] = agent_conv
        
    # Save conversation
    with open(f"{save_dir}/conversation.json", "w", encoding="utf-8") as f:
        json.dump(conversation, f, indent=4)
    
def save_results(config, answers, scores, save_dir):

    results = {}
    
    for i in range(len(scores)):
        round_res = {
            "answer": answers[i],
            "score": scores[i]
        }
        if config.team_interdependence_type == 'pooled':
            results[f"agent_{i}"] = round_res
        else:
            results[f"round_{i+1}"] = round_res

    with open(f"{save_dir}/results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)
    
# ======================
# MAIN
# ======================

@hydra.main(version_base=None, config_path="configs", config_name="config")
def main(cfg: DictConfig) -> None:
    
    """Run my task experiment with specified configuration."""
    
    # ---------------------------
    #  SET UP - config, logging, etc.
    # ----------------------------
    
    config = MyTaskConfig(**cfg.task)  # type: ignore
    save_dir = hydra.core.hydra_config.HydraConfig.get().runtime.output_dir    
    
    # Suppress httpx INFO and DEBUG logs
    #logging.getLogger("httpx").setLevel(logging.WARNING)
   
    # Single backend mode
    print("Running in SINGLE BACKEND mode")
 
    # Get model and run name
    backend_summary = f"{config.backend.provider}-{config.backend.model}" 
    run_name = config.generate_run_name(backend_summary)

    # Get prompts and fill dynamic info
    dynamic_prompt_values = {
        "num_agents_minus_one": config.num_agents-1,
        "num_rounds": config.max_rounds,
        "small_group_rounds": config.small_group_rounds
    }
    with open(config.input_prompt_file, "r", encoding="utf-8") as f:
        prompt_text = f.read()
    prompt_text_with_dyn_vals = Template(prompt_text).substitute(dynamic_prompt_values)
    input_prompts = json.loads(prompt_text_with_dyn_vals)
    
    #with open(config.input_prompt_file, 'r') as f:
    #    input_prompts = json.load(f)
    
    print(f"\nExperiment: {run_name}")
    print(f"Agents: {config.num_agents} | Rounds: {config.max_rounds} | Team Interdependence: {config.team_interdependence_type}")
    print(f"Backend: {backend_summary} | Seed: {config.seed}")

    if config.seed is not None:
        random.seed(config.seed)

    # ---------------------------
    #  CREATE AGENTS
    # ---------------------------

    agents = create_agents(config, input_prompts)

    # Print agent details
    print("\nAgent configuration:")
    for agent in agents:
        print(f"  {agent.profile.name}")

    # ============================
    # COMPLETE TASK - using a team interdependence type
    # ============================        

    print("\nExecuting task...")
    
    #prompt = input("Enter the prompt for each agent to work on: ")
    
    if config.team_interdependence_type == "pooled":
        answers, scores = execute.pooled_task(agents, input_prompts, config)
    elif config.team_interdependence_type == "sequential":
        answers, scores = execute.sequential_task(agents, input_prompts, config)
    elif config.team_interdependence_type == "reciprocal_chain":
        answers, scores = execute.reciprocal_chain_task(agents, input_prompts, config)
    elif config.team_interdependence_type == "reciprocal_subgroups":
        answers, scores = execute.reciprocal_subgroups_task(agents, input_prompts, config)
    elif config.team_interdependence_type == "team":
        answers, scores = execute.team_task(agents, input_prompts, config)    
        
    print("Task Complete!")

    print(answers)
    print(scores)

    # ---------------------
    # Save artifacts
    # ---------------------
    
    print("\nSaving conversation and results...")
    save_convo(agents, save_dir)  
    save_results(config, answers, scores, save_dir)
    
    
if __name__ == "__main__":
    _configure_console_output()
    main()  # type: ignore



# add prompt format answer instructions into code??
