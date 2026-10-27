"""Backend interfaces for invoking language models."""

import abc
import os
from typing import Optional
from dataclasses import dataclass

import anthropic
import openai

from .conversation import Trajectory, format_turn_content
from .profiles import AgentProfile


def _check_completion_status(reason: Optional[str], token_limit_name: str) -> None:
    if reason in {"length", "max_tokens", "model_context_window_exceeded"}:
        raise ValueError(
            f"Response was truncated (stop reason={reason}); increase {token_limit_name} "
            "to leave room for reasoning and the final answer, or reduce the prompt."
        )
    if reason in {"content_filter", "refusal"}:
        raise ValueError(f"Response was refused or filtered (stop reason={reason})")
    if reason in {"tool_calls", "function_call", "tool_use", "pause_turn"}:
        raise ValueError(
            f"Response requires continuation (stop reason={reason}); "
            "this backend supports text-only turns, not tool-calling loops."
        )


def _chat_response_text(response) -> str:
    if not response.choices:
        raise ValueError("API returned no response choices; no final answer is available")
    choice = response.choices[0]
    _check_completion_status(choice.finish_reason, "max_completion_tokens/max_tokens")
    message = choice.message
    if getattr(message, "refusal", None):
        raise ValueError("API refused the response; no final answer is available")
    if getattr(message, "tool_calls", None) or getattr(message, "function_call", None):
        raise ValueError("Tool calls are not supported by this text-only backend")
    if not isinstance(message.content, str) or not message.content.strip():
        raise ValueError(
            f"API returned no final answer text (finish_reason={choice.finish_reason}); "
            "reasoning-only output is not an agent answer."
        )
    return message.content.strip()


def _reasoning_token_count(usage, detail_name: str, token_name: str) -> int:
    details = getattr(usage, detail_name, None)
    if isinstance(details, dict):
        return details.get(token_name, 0) or 0
    return getattr(details, token_name, 0) or 0


@dataclass
class UsageStats:
    """Track provider-reported usage; reasoning counts are not added twice."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0

    def add_call(
        self, input_tokens: int, output_tokens: int, *,
        total_tokens: Optional[int] = None, reasoning_tokens: int = 0,
    ) -> None:
        """Add token counts from a single API call."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens if total_tokens is None else total_tokens
        self.reasoning_tokens += reasoning_tokens

    def add_chat_usage(self, usage) -> None:
        if usage is not None:
            # Some compatible endpoints include extra tokens only in total_tokens.
            self.add_call(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                total_tokens=getattr(usage, "total_tokens", None),
                reasoning_tokens=_reasoning_token_count(
                    usage, "completion_tokens_details", "reasoning_tokens"
                ),
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }


class LLMBackend(abc.ABC):
    """Abstract interface for LLM providers."""

    def __init__(self, seed: Optional[int] = None):
        """Initialize backend with optional seed for reproducibility.

        Args:
            seed: Random seed for deterministic outputs (if supported by provider)
        """
        self.seed = seed
        self.usage_stats = UsageStats()

    @abc.abstractmethod
    def invoke(
        self,
        *,
        agent_profile: AgentProfile,
        trajectory: Trajectory,
    ) -> str:
        """Perform a synchronous inference call and return the model response.

        Args:
            agent_profile: Agent metadata and configuration
            trajectory: The conversation history

        Returns:
            The model's response text
        """

    async def ainvoke(
        self,
        *,
        agent_profile: AgentProfile,
        trajectory: Trajectory,
    ) -> str:
        """Async wrapper calling the synchronous method by default."""

        return self.invoke(
            agent_profile=agent_profile, trajectory=trajectory
        )

    def _build_system_message(self, agent_profile: AgentProfile) -> str:
        """Build the system message from agent profile.
        
        This method unifies the logic for building system messages across all backends,
        ensuring consistency in how agent profile information is formatted.
        
        Args:
            agent_profile: Agent metadata and configuration
            
        Returns:
            A formatted system message string
        """
        system_parts = []
        if agent_profile.system_prompt:
            system_parts.append(agent_profile.system_prompt.strip())
        if agent_profile.persona:
            system_parts.append(f"Persona: {agent_profile.persona.strip()}")
        if agent_profile.role:
            system_parts.append(f"Role: {agent_profile.role.strip()}")
        if agent_profile.hidden_context:
            system_parts.append(f"Hidden context: {agent_profile.hidden_context.strip()}")
        
        return "\n".join(system_parts)

    def format_full_prompt(
        self,
        *,
        agent_profile: AgentProfile,
        trajectory: Trajectory,
    ) -> str:
        """Format the full prompt as the agent sees it, for logging/debugging.
        
        This method returns a human-readable representation of the complete prompt
        that would be sent to the model, including system prompt and all trajectory turns.
        
        Args:
            agent_profile: Agent metadata and configuration
            trajectory: The conversation history
            
        Returns:
            A formatted string representation of the full prompt
        """
        system_message = self._build_system_message(agent_profile)
        
        # Format conversation history
        conversation_lines = []
        for turn in trajectory.turns:
            formatted_content = format_turn_content(turn, agent_profile.agent_id)
            conversation_lines.append(formatted_content)
        
        # Assemble full prompt
        prompt_sections = [system_message] if system_message else []
        if conversation_lines:
            prompt_sections.append("Conversation so far:\n" + "\n".join(conversation_lines))
        prompt_sections.append("Your turn: Respond concisely yet helpfully.")
        
        return "\n\n".join(section for section in prompt_sections if section)


class EchoBackend(LLMBackend):
    """Simple backend that mirrors the prompt for local testing."""

    def __init__(self, seed: Optional[int] = None):
        super().__init__(seed)

    def invoke(
        self,
        *,
        agent_profile: AgentProfile,
        trajectory: Trajectory,
    ) -> str:
        prompt = self.format_full_prompt(
            agent_profile=agent_profile,
            trajectory=trajectory
        )
        seed_str = f" [seed={self.seed}]" if self.seed is not None else ""
        return f"[echo{seed_str}] {prompt}".strip()


class OpenAIBackend(LLMBackend):
    """Backend for OpenAI Chat Completions API."""

    def __init__(self, api_key: str, model: str = "gpt-4o", seed: Optional[int] = None, **kwargs):
        """Initialize OpenAI backend with API key and model configuration.

        Args:
            api_key: OpenAI API key
            model: Model name (e.g., "gpt-4o", "gpt-4o-mini")
            seed: Random seed for deterministic outputs
            **kwargs: Additional parameters to pass to the API
        """
        super().__init__(seed)
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.extra_params = kwargs

    def invoke(
        self,
        *,
        agent_profile: AgentProfile,
        trajectory: Trajectory,
    ) -> str:
        """Invoke OpenAI by building messages directly from structured data."""
        current_agent_id = agent_profile.agent_id

        # Build system message from agent profile using unified method
        system_message = self._build_system_message(agent_profile)
        messages = [{"role": "system", "content": system_message}]

        # Add conversation history
        for turn in trajectory.turns:
            if turn.speaker_id == current_agent_id:
                # Current agent's previous responses
                messages.append({"role": "assistant", "content": turn.content})
            else:
                # Other agents' messages (including system messages)
                formatted_content = format_turn_content(turn, current_agent_id)
                messages.append({"role": "user", "content": formatted_content})

        # Add instruction to respond
        messages.append({"role": "user", "content": "Respond concisely yet helpfully."})

        try:
            params = {"model": self.model, "messages": messages, **self.extra_params}
            if self.seed is not None:
                params["seed"] = self.seed

            response = self.client.chat.completions.create(**params)  # type: ignore[arg-type]

            # Track token usage
            self.usage_stats.add_chat_usage(response.usage)

            return _chat_response_text(response)
        except Exception as e:
            provider_name = "Google Gemini" if isinstance(self, GeminiDirectBackend) else "OpenAI"
            raise RuntimeError(f"{provider_name} API call failed: {e}") from e


class GeminiDirectBackend(OpenAIBackend):
    """Google Gemini API using its OpenAI-compatible chat endpoint."""

    def __init__(self, api_key: str, model: str, seed: Optional[int] = None, **kwargs):
        # Google does not support the seed parameter on this endpoint.
        LLMBackend.__init__(self, None)
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            max_retries=5,
        )
        self.model = model
        self.extra_params = kwargs


class AnthropicBackend(LLMBackend):
    """Backend for Anthropic Claude API."""

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022", seed: Optional[int] = None, **kwargs):
        """Initialize Anthropic backend with API key and model configuration.

        Args:
            api_key: Anthropic API key
            model: Model name (e.g., "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022")
            seed: Random seed for deterministic outputs (not supported by Anthropic)
            **kwargs: Additional parameters to pass to the API
        """
        super().__init__(seed)
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.extra_params = kwargs

    def invoke(
        self,
        *,
        agent_profile: AgentProfile,
        trajectory: Trajectory,
    ) -> str:
        """Invoke Anthropic API by building messages from structured data."""
        current_agent_id = agent_profile.agent_id

        # Build system message from agent profile using unified method
        system_message = self._build_system_message(agent_profile)

        # Build conversation messages (Anthropic uses user/assistant alternation)
        messages = []
        for turn in trajectory.turns:
            if turn.speaker_id == current_agent_id:
                # Current agent's previous responses
                messages.append({"role": "assistant", "content": turn.content})
            else:
                # Other agents' messages (including system messages)
                formatted_content = format_turn_content(turn, current_agent_id)
                messages.append({"role": "user", "content": formatted_content})

        # Add instruction to respond
        messages.append({"role": "user", "content": "Respond concisely yet helpfully."})

        try:
            params = {
                "model": self.model,
                "system": system_message,
                "messages": messages,
                "max_tokens": 4096,
                **self.extra_params
            }

            response = self.client.messages.create(**params)

            # Track token usage
            if response.usage:
                self.usage_stats.add_call(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    reasoning_tokens=_reasoning_token_count(
                        response.usage, "output_tokens_details", "thinking_tokens"
                    ),
                )

            _check_completion_status(response.stop_reason, "max_tokens")
            response_text = "\n".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            if not response_text:
                raise ValueError(f"Anthropic returned no text (stop_reason={response.stop_reason})")
            return response_text
        except Exception as e:
            raise RuntimeError(f"Anthropic API call failed: {e}") from e


class OpenRouterBackend(LLMBackend):
    """Backend for Open Router API (supports Gemini and other models)."""

    def __init__(self, api_key: str, model: str, seed: Optional[int] = None, **kwargs):
        """Initialize OpenRouter backend with API key and model configuration.

        Args:
            api_key: OpenRouter API key
            model: Model name in provider/model format (e.g., "google/gemini-2.0-flash", "google/gemini-3-pro-preview")
            seed: Random seed for deterministic outputs (if supported by the model)
            **kwargs: Additional parameters to pass to the API
        """
        super().__init__(seed)
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )
        self.model = model
        self.extra_params = kwargs

    def invoke(
        self,
        *,
        agent_profile: AgentProfile,
        trajectory: Trajectory,
    ) -> str:
        """Invoke OpenRouter API by building messages directly from structured data."""
        current_agent_id = agent_profile.agent_id

        # Build system message from agent profile using unified method
        system_message = self._build_system_message(agent_profile)
        messages = [{"role": "system", "content": system_message}]

        # Add conversation history
        for turn in trajectory.turns:
            if turn.speaker_id == current_agent_id:
                # Current agent's previous responses
                messages.append({"role": "assistant", "content": turn.content})
            else:
                # Other agents' messages (including system messages)
                formatted_content = format_turn_content(turn, current_agent_id)
                messages.append({"role": "user", "content": formatted_content})

        # Add instruction to respond
        messages.append({"role": "user", "content": "Respond concisely yet helpfully."})

        try:
            params = {"model": self.model, "messages": messages, **self.extra_params}
            if self.seed is not None:
                params["seed"] = self.seed

            response = self.client.chat.completions.create(**params)  # type: ignore[arg-type]

            # Track token usage
            self.usage_stats.add_chat_usage(response.usage)

            return _chat_response_text(response)
        except Exception as e:
            raise RuntimeError(f"OpenRouter API call failed: {e}") from e

# ===================================

def _print_prompt(messages):
    for m in messages:
        print(m)

class RCGenAIBackend(LLMBackend):
    """Backend for RCGenAI Chat Completions API.  Uses openai API."""

    def __init__(self, api_key: str, model: str = "Kimi K2.5", seed: Optional[int] = None, **kwargs):
        """Initialize RCGenAI backend with API key and model configuration.

        Args:
            api_key: RCGenAI API key
            model: Model name (e.g., "gpt-4o", "gpt-4o-mini")
            seed: Random seed for deterministic outputs
            **kwargs: Additional parameters to pass to the API
        """
        super().__init__(seed)
        base_url = os.environ.get("RCGENAI_BASE_URL", "").strip()
        if not base_url:
            raise ValueError("Set RCGENAI_BASE_URL to your gateway's OpenAI-compatible API base URL")
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.extra_params = kwargs

    def invoke(
        self,
        *,
        agent_profile: AgentProfile,
        trajectory: Trajectory,
    ) -> str:
        """Invoke RCGenAI by building messages directly from structured data."""
        current_agent_id = agent_profile.agent_id

        # Build system message from agent profile using unified method
        system_message = self._build_system_message(agent_profile)
        messages = [{"role": "system", "content": system_message}]

        # Add conversation history
        for turn in trajectory.turns:
            if turn.speaker_id == current_agent_id:
                # Current agent's previous responses
                messages.append({"role": "assistant", "content": turn.content})
            else:
                # Other agents' messages (including system messages)
                formatted_content = format_turn_content(turn, current_agent_id)
                messages.append({"role": "user", "content": formatted_content})

        # Add instruction to respond
        messages.append({"role": "user", "content": "Respond concisely yet helpfully."})

        print("\n=====================\n")
        _print_prompt(messages)

        try:
            params = {"model": self.model, "messages": messages, "stream": True, "stream_options": {"include_usage": True}, 
                      **self.extra_params}
            if self.seed is not None:
                params["seed"] = self.seed

            response = self.client.chat.completions.create(**params)  # type: ignore[arg-type]

            # collect streaming response
            answer = ""
            finish_reason = None
            refused = False
            tool_calls = False
            for chunk in response:
            
                if chunk.choices:
                    choice = chunk.choices[0]
                    if choice.finish_reason is not None:
                        finish_reason = choice.finish_reason
                    refused = refused or bool(getattr(choice.delta, "refusal", None))
                    tool_calls = tool_calls or bool(
                        getattr(choice.delta, "tool_calls", None)
                        or getattr(choice.delta, "function_call", None)
                    )
                    if choice.delta.content:
                        answer += choice.delta.content

                # Track token usage - last chunk in stream
                self.usage_stats.add_chat_usage(chunk.usage)

            _check_completion_status(finish_reason, "max_completion_tokens/max_tokens")
            if refused:
                raise ValueError("API refused the response; no final answer is available")
            if tool_calls:
                raise ValueError("Tool calls are not supported by this text-only backend")
            if not answer.strip():
                raise ValueError("API returned no final answer text; reasoning-only output is not an agent answer")
            if finish_reason is None:
                raise ValueError("Stream ended without completion status; no complete answer is available")
            print(f"RESPONSE: {answer.strip()}")
            print("=====================\n")
            
            return answer.strip() 
        except Exception as e:
            raise RuntimeError(f"RCGenAI API call failed: {e}") from e



# ====================================

def create_backend(
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    seed: Optional[int] = None,
    **kwargs
) -> LLMBackend:
    """Create a backend instance for the specified provider.

    Args:
        provider: Backend provider name ("openai", "anthropic", "gemini", or "rcgenai")
        api_key: API key for the provider
        model: Model name (uses provider default if None)
        seed: Random seed for deterministic outputs
        **kwargs: Additional provider-specific parameters (temperature, top_p, etc.)

    Returns:
        Configured LLMBackend instance

    Raises:
        ValueError: If provider is not supported
    """
    provider = provider.lower()

    if provider == "openai":
        if model is None:
            return OpenAIBackend(api_key=api_key, seed=seed, **kwargs)
        return OpenAIBackend(api_key=api_key, model=model, seed=seed, **kwargs)

    elif provider == "anthropic":
        if model is None:
            return AnthropicBackend(api_key=api_key, seed=seed, **kwargs)
        return AnthropicBackend(api_key=api_key, model=model, seed=seed, **kwargs)

    elif provider == "gemini_direct":
        if not model:
            raise ValueError("Specify a Google Gemini model ID for gemini_direct")
        return GeminiDirectBackend(api_key=api_key, model=model, seed=seed, **kwargs)

    elif provider == "gemini":
        default_model = "google/gemini-2.0-flash"
        model_to_use = model if model is not None else default_model
        return OpenRouterBackend(api_key=api_key, model=model_to_use, seed=seed, **kwargs)

    elif provider == "rcgenai":
        default_model = "Kimi K2.5"
        model_to_use = model if model is not None else default_model
        return RCGenAIBackend(api_key=api_key, model=model_to_use, seed=seed, **kwargs)

    else:
        raise ValueError(
            f"Unsupported provider: {provider}. "
            f"Supported providers are: openai, anthropic, gemini, gemini_direct, rcgenai"
        )
