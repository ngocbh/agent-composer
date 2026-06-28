"""Pure helper functions for agent modes (no shared state — that's in `common`)."""

from __future__ import annotations

from langchain_core.messages import BaseMessage


def text_of(message: BaseMessage) -> str:
    """Flatten a langchain message's content to plain text."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""
