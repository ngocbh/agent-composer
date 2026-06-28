"""`ac run` — load a flow, gather inputs, drive it to a terminal, render the output.

Inputs come from flags (`--input k=v`, repeatable; `--inputs file.json`); any declared
input still missing is prompted for interactively (required ones are starred). A run that
suspends on a HUMAN_INPUT / WAIT effect is resumed interactively — each pause prompts for
the awaited value and the run continues to a terminal. The answer's type is enforced at
the engine boundary; an invalid one fails the run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer
from rich.console import Console
from rich.markdown import Markdown

from agent_composer.compose.loader import load_flow
from agent_composer.compose.run import RunResult, resume_command, resume_flow, run_flow
from agent_composer.state.segments import SegmentType

console = Console()
err_console = Console(stderr=True)


def _parse_kv(pairs: List[str]) -> Dict[str, Any]:
    """Parse repeated `--input k=v` flags into a dict (values stay strings; the engine
    coerces them against each input's declared type at the run boundary)."""
    out: Dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise typer.BadParameter(f"--input must be k=v (got {pair!r})")
        key, value = pair.split("=", 1)
        out[key.strip()] = value
    return out


def _prompt_missing(decls: List[Any], have: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Prompt for each declared input not already supplied. Returns the gathered values,
    or None if the user cancels (Ctrl-C / Esc). The widget follows the declared type: a
    boolean is a confirm, a `Literal[...]` enum is a select, everything else is free text."""
    import questionary

    gathered: Dict[str, Any] = {}
    for decl in decls:
        if decl.name in have:
            continue
        label = decl.name + (" *" if decl.required else "")
        shape = decl.shape
        if shape.seg_type == SegmentType.BOOLEAN:
            value = questionary.confirm(label, default=bool(decl.default)).ask()
        elif shape.tags:  # a Literal[...] enum
            value = questionary.select(label, choices=sorted(shape.tags)).ask()
        else:
            default = "" if decl.default is None else str(decl.default)
            value = questionary.text(label, default=default).ask()

        if value is None:  # Ctrl-C / Esc
            return None
        if isinstance(value, str) and value.strip() == "" and not decl.required:
            continue
        gathered[decl.name] = value
    return gathered


def _resume_to_terminal(loaded: Any, result: RunResult, on_event: Any) -> RunResult:
    """Drive a paused run to a terminal, prompting for each pause's awaited value.

    A HUMAN_INPUT pause prompts for the answer; a timed WAIT asks to release it now; an
    external-event pause can't be satisfied here and stays paused. Cancelling a prompt
    leaves the run paused (not an error)."""
    import questionary

    while result.status == "paused":
        answered: List[Tuple[Any, Any]] = []
        for reason in result.pause_reasons:
            if reason.type == "human_input_required":
                label = reason.prompt or f"input for {reason.node_id}"
                answer = questionary.text(label).ask()
                if answer is None:
                    return result  # cancelled — stay paused
                answered.append((reason, answer))
            elif reason.type == "scheduled_pause":
                if not questionary.confirm(
                    f"{reason.node_id}: release the wait now?", default=True
                ).ask():
                    return result
                answered.append((reason, None))  # release: value=None
            else:
                err_console.print(
                    "[yellow]awaiting an external event — can't release it here[/yellow]"
                )
        if not answered:
            return result
        commands = [resume_command(loaded, reason, value) for reason, value in answered]
        result = resume_flow(loaded, engine=result.engine, commands=commands, on_event=on_event)
    return result


def run(
    flow: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="Path to a flow .yaml"),
    input: List[str] = typer.Option(  # noqa: A002 - matches the user-facing flag name
        None, "--input", "-i", help="An input as k=v (repeatable)."
    ),
    inputs: Optional[Path] = typer.Option(
        None, "--inputs", exists=True, dir_okay=False, readable=True, help="A JSON file of inputs."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress per-node progress."),
) -> None:
    """Run a flow to completion and print its output."""
    text = flow.read_text()
    loaded = load_flow(text, search_paths=[flow.parent])

    supplied: Dict[str, Any] = {}
    if inputs is not None:
        supplied.update(json.loads(inputs.read_text()))
    if input:
        supplied.update(_parse_kv(input))

    prompted = _prompt_missing(loaded.input, supplied)
    if prompted is None:
        err_console.print("[yellow]run cancelled[/yellow]")
        raise typer.Exit(code=1)
    supplied.update(prompted)

    def on_event(event: Any) -> None:
        if not quiet and type(event).__name__ == "NodeStarted":
            err_console.print(f"[dim]  → {event.node_id}[/dim]")

    result = run_flow(loaded, supplied, on_event=on_event)
    if result.status == "paused":
        result = _resume_to_terminal(loaded, result, on_event)

    if result.status == "succeeded":
        out = result.output
        if isinstance(out, str) and out.strip():
            console.print(Markdown(out))
        else:
            console.print(out)
    elif result.status == "paused":
        err_console.print("[yellow]run paused (resume cancelled)[/yellow]")
        raise typer.Exit(code=1)
    else:
        err_console.print(f"[red]run {result.status}: {result.error or '(no detail)'}[/red]")
        raise typer.Exit(code=1)
