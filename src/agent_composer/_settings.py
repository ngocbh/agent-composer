"""Global LLM defaults for the standalone package, read from the environment.

`model_from_config` falls back to these when an `LLMConfig` leaves `provider` /
`model` unset. They are read from environment variables so the package needs no
host-supplied settings object:

- ``AGENT_COMPOSER_DEFAULT_PROVIDER`` — provider name (default ``"anthropic"``).
- ``AGENT_COMPOSER_DEFAULT_MODEL``    — model id   (default ``"claude-sonnet-4-5"``).

Provider API keys themselves are read by each provider client from its own
conventional env var (see ``llm_clients/api_key_env.py``); this module only
carries the *which provider / which model* defaults.
"""

from __future__ import annotations

import os

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-sonnet-4-5"


def default_llm_provider() -> str:
    """Provider used when an ``LLMConfig`` leaves ``provider`` unset."""
    return os.environ.get("AGENT_COMPOSER_DEFAULT_PROVIDER", DEFAULT_PROVIDER)


def default_llm_model() -> str:
    """Model used when an ``LLMConfig`` leaves ``model`` unset."""
    return os.environ.get("AGENT_COMPOSER_DEFAULT_MODEL", DEFAULT_MODEL)
