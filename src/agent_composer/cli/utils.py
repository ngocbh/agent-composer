"""Interactive CLI helpers for provider credentials and endpoints.

These are the integration points the `llm_clients` modules point at by name:

- `ensure_api_key` — the interactive key prompt referenced by
  `llm_clients/api_key_env.py`. Called pre-flight by `ac run` (see
  `cli/run.py`) so a missing key surfaces as an upfront prompt instead of a
  cryptic failure on the first API call.
- `confirm_ollama_endpoint` — referenced by `llm_clients/model_catalog.py`
  as the step that surfaces the resolved Ollama endpoint right after provider
  selection; the future provider-selection wizard is its caller.

Both are TTY-aware: they prompt only when attached to an interactive terminal
and otherwise fall back (return the ambient value, or raise for a hard-missing
required key) so non-interactive runs stay scriptable.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from agent_composer.llm_clients.api_key_env import get_api_key_env

# Mirror of `ollama_client._DEFAULT_BASE_URL`. Duplicated (not imported) so this
# module stays import-light — importing the ollama client pulls `langchain_ollama`
# at module top, which we don't want on the CLI's hot path.
_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"


def ensure_api_key(provider: str, *, interactive: bool = True) -> Optional[str]:
    """Return `provider`'s API key, prompting for it interactively if it is unset.

    The env var for the key is resolved via
    [`get_api_key_env`][agent_composer.llm_clients.api_key_env.get_api_key_env].
    A keyless provider (`ollama`) or an unknown one maps to no env var, so nothing
    is checked and `None` is returned. When the env var is set its value is
    returned unchanged. When it is unset and a TTY is attached, the user is
    prompted (the answer is exported into the process env so downstream clients
    read it); with no TTY (or `interactive=False`) a required-but-missing key
    raises rather than hanging on a prompt.

    Args:
        provider (`str`):
            The LLM provider name (e.g. `"anthropic"`, `"openai"`), matched
            case-insensitively against the provider → env-var table.
        interactive (`bool`, *optional*, defaults to `True`):
            Whether an interactive prompt is permitted. Set `False` to force the
            non-interactive path (return existing or raise) regardless of TTY.

    Returns:
        `Optional[str]`:
            The resolved API key, or `None` when the provider needs none (keyless
            or unknown).

    Raises:
        `RuntimeError`:
            The provider requires a key, none is set, and no interactive prompt
            is available (no TTY, or `interactive=False`, or the user entered an
            empty value).
    """
    env_var = get_api_key_env(provider)
    if env_var is None:
        return None  # keyless (e.g. ollama) or unknown provider — nothing to ensure
    existing = os.environ.get(env_var)
    if existing:
        return existing
    if not (interactive and sys.stdin.isatty()):
        raise RuntimeError(
            f"provider {provider!r} needs an API key but ${env_var} is not set "
            f"(set it in the environment, or run interactively to be prompted)"
        )
    import questionary

    key = questionary.password(f"Enter {env_var} for provider {provider!r}:").ask()
    if not key:
        raise RuntimeError(f"no API key provided for {provider!r} (${env_var})")
    os.environ[env_var] = key
    return key


def confirm_ollama_endpoint(*, interactive: bool = True) -> str:
    """Confirm (or override) the Ollama base URL, prompting when interactive.

    The current endpoint is `$OLLAMA_BASE_URL` if set, else the localhost default
    that mirrors `ollama_client`. When a TTY is attached the value is offered as an
    editable default and the confirmed answer is exported back into
    `$OLLAMA_BASE_URL` so the client resolves the same endpoint. Non-interactively
    (or `interactive=False`) the current value is returned unchanged.

    Args:
        interactive (`bool`, *optional*, defaults to `True`):
            Whether an interactive prompt is permitted. Set `False` to force the
            non-interactive path (return the current value) regardless of TTY.

    Returns:
        `str`:
            The resolved Ollama base URL.
    """
    current = os.environ.get("OLLAMA_BASE_URL") or _OLLAMA_DEFAULT_BASE_URL
    if not (interactive and sys.stdin.isatty()):
        return current
    import questionary

    answer = questionary.text("Ollama endpoint:", default=current).ask()
    endpoint = (answer or current).strip()
    os.environ["OLLAMA_BASE_URL"] = endpoint
    return endpoint
