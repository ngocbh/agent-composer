"""`ac run` interactive input prompt: a "Running flow" banner + per-input metadata labels.

At run start the CLI prints a `_flow_banner` (name/description/version); each prompt's
label carries the input's declared `type`, a required (`*`) / `optional` mark, and any
default (`_input_label`). `_prompt_missing` is exercised with a fake `questionary` so the
labels it builds are observable without a TTY. A runtime failure (`_render_run_error`)
boxes the `.yaml` at the node that raised, mirroring the compile-error frame.
"""

import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

import agent_composer.cli.run as climod
from agent_composer.cli.run import (
    _flow_banner,
    _input_label,
    _prompt_missing,
    _render_run_error,
)
from agent_composer.compose.loader import load_flow
from agent_composer.compose.run import RunResult, run_flow
from agent_composer.compose.shapes import read_flow_inputs

_ERRORS = Path(__file__).resolve().parents[2] / "tests" / "seeds" / "errors"


def _decls():
    return read_flow_inputs(
        {
            "topic": "str",
            "as_of": "Optional[date]",
            "window": "int = 30",
            "mode": 'Literal["fast", "slow"]',
        },
        {},
    )


# --- _flow_banner: the "Running flow" identity block ------------------------- #
def _plain(text) -> str:
    """Render a Rich Text to a plain (un-styled) string for substring assertions."""
    buf = StringIO()
    Console(file=buf, force_terminal=False, width=100).print(text)
    return buf.getvalue()


def test_flow_banner_name_and_description():
    out = _plain(_flow_banner("my_flow", "Does a useful thing."))
    assert "Running flow: my_flow" in out
    assert "Description: Does a useful thing." in out


def test_flow_banner_includes_version():
    out = _plain(_flow_banner("f", "d", version="v2"))
    assert "version: v2" in out


def test_flow_banner_none_when_no_metadata():
    assert _flow_banner(None, None, None) is None


# --- _input_label: name + type + required/optional/default -------------------- #
def test_input_label_required():
    topic = next(d for d in _decls() if d.name == "topic")
    assert _input_label(topic) == "topic (str) *"


def test_input_label_optional_no_default():
    as_of = next(d for d in _decls() if d.name == "as_of")
    assert _input_label(as_of) == "as_of (Optional[date]) [optional] e.g. 2026-05-21"


def test_input_label_optional_with_default():
    window = next(d for d in _decls() if d.name == "window")
    assert _input_label(window) == "window (int) [default: 30]"


def test_input_label_datetime_example():
    decls = read_flow_inputs({"at": "datetime"}, {})
    at = next(d for d in decls if d.name == "at")
    assert _input_label(at) == "at (datetime) * e.g. 2026-05-21T14:30"


def test_input_label_default_suppresses_example():
    # A date default already shows the accepted format, so no redundant `e.g.`.
    decls = read_flow_inputs({"as_of": "Optional[date] = 2026-01-01"}, {})
    as_of = next(d for d in decls if d.name == "as_of")
    assert _input_label(as_of) == "as_of (Optional[date]) [default: 2026-01-01]"


# --- _prompt_missing: header + labels via a fake questionary ------------------ #
class _FakeQuestionary:
    """Records the labels it is asked with; answers from `answers` (substr -> value)."""

    def __init__(self, answers):
        self.labels: list[str] = []
        self._answers = answers

    def _resolve(self, label):
        self.labels.append(label)
        for key, val in self._answers.items():
            if key in label:
                return val
        return ""

    def text(self, label, default=""):
        val = self._resolve(label)
        return SimpleNamespace(ask=lambda: val)

    def confirm(self, label, default=False):
        val = self._resolve(label)
        return SimpleNamespace(ask=lambda: val)

    def select(self, label, choices):
        val = self._resolve(label)
        return SimpleNamespace(ask=lambda: val)


def _sink(monkeypatch) -> StringIO:
    buf = StringIO()
    monkeypatch.setattr(climod, "err_console", Console(file=buf, force_terminal=False, width=100))
    return buf


def test_prompt_labels_carry_marks(monkeypatch):
    fake = _FakeQuestionary({"topic": "ACME", "mode": "fast"})
    monkeypatch.setitem(sys.modules, "questionary", fake)
    _sink(monkeypatch)
    _prompt_missing(_decls(), {})
    joined = " || ".join(fake.labels)
    assert "topic (str) *" in joined
    assert "as_of (Optional[date]) [optional]" in joined
    assert "window (int) [default: 30]" in joined


def test_prompt_skips_already_supplied(monkeypatch):
    # Everything supplied -> nothing to prompt -> no prompt issued, empty gathered.
    fake = _FakeQuestionary({})
    monkeypatch.setitem(sys.modules, "questionary", fake)
    _sink(monkeypatch)
    have = {"topic": "x", "as_of": "2026-01-01", "window": 5, "mode": "fast"}
    gathered = _prompt_missing(_decls(), have)
    assert gathered == {}
    assert fake.labels == []          # no prompt issued


# --- _render_run_error: a runtime failure boxes the .yaml at the PRECISE line ------ #
def test_run_error_boxes_failing_node(monkeypatch):
    # e07 omits `as_of` -> the `report` node's `:?` fires at bind time -> NodeFailed
    # carrying an input locator -> the box points at the `as_of:` binding, not the header.
    flow = _ERRORS / "e07-required-missing.yaml"
    text = flow.read_text()
    result = run_flow(load_flow(text, search_paths=[flow.parent]), {"topic": "X"})
    assert result.status == "failed"
    buf = _sink(monkeypatch)
    _render_run_error(result, flow, text)
    out = buf.getvalue()
    assert "e07-required-missing.yaml:23" in out   # the as_of binding, not the node header
    assert "report" in out                         # still inside the source window
    assert "as_of is required for the report" in out


def test_run_error_kind_fallback_for_code_raise(monkeypatch):
    # e20's code callable raises -> NodeFailed with no precise locator -> the chain falls
    # back to the node-kind best sub-line: a code node's `code:` field (not the header, not plain).
    flow = _ERRORS / "e20-code-raises.yaml"
    text = flow.read_text()
    result = run_flow(load_flow(text, search_paths=[flow.parent]), {"topic": "X"})
    assert result.status == "failed"
    buf = _sink(monkeypatch)
    _render_run_error(result, flow, text)
    out = buf.getvalue()
    assert "╭" in out and "code:" in out           # boxed at the `code:` field


def test_run_error_boxes_boundary_assert_line(monkeypatch):
    # e18's boundary assert fails before any node runs; in phase 2 the RunFailed carries a
    # flow-level assert locator -> the failure is now BOXED at the `asserts:` line (was plain).
    flow = _ERRORS / "e18-false-boundary-assert.yaml"
    text = flow.read_text()
    result = run_flow(load_flow(text, search_paths=[flow.parent]), {"window": -5})
    assert result.status == "failed"
    buf = _sink(monkeypatch)
    _render_run_error(result, flow, text)
    out = buf.getvalue()
    assert "e18-false-boundary-assert.yaml:15" in out   # the `${input.window} > 0` line
    assert "assert failed" in out


def test_run_error_boxes_code_wrong_type_output(monkeypatch):
    # e21's code node returns a value that fails its declared `output: int` -> the typed write
    # boundary rejects it. The node-less RunFailed carries a `field` locator -> BOXED at the
    # node's `output:` declaration (not a plain message, not the node header).
    flow = _ERRORS / "e21-code-wrong-type.yaml"
    text = flow.read_text()
    result = run_flow(load_flow(text, search_paths=[flow.parent]), {"topic": "X"})
    assert result.status == "failed"
    buf = _sink(monkeypatch)
    _render_run_error(result, flow, text)
    out = buf.getvalue()
    assert "e21-code-wrong-type.yaml:12" in out   # the `output: int` field line
    assert "╭" in out


def test_run_error_boxes_input_decl_line(monkeypatch):
    # e08's `window` can't coerce to int -> input-coercion failure carries an input_decl
    # locator -> boxed at the `window:` declaration line.
    flow = _ERRORS / "e08-input-type-mismatch.yaml"
    text = flow.read_text()
    result = run_flow(load_flow(text, search_paths=[flow.parent]), {"topic": "X", "window": "soon"})
    assert result.status == "failed"
    buf = _sink(monkeypatch)
    _render_run_error(result, flow, text)
    out = buf.getvalue()
    assert "e08-input-type-mismatch.yaml:20" in out     # the `window: int` decl line
    assert "╭" in out


def test_run_error_plain_when_unlocatable(monkeypatch):
    # A failure with no NodeFailed AND no locator (e.g. a terminal-skipped run) has nowhere
    # to point -> the plain `run <status>: <message>` line, no frame.
    flow = _ERRORS / "e18-false-boundary-assert.yaml"
    text = flow.read_text()
    result = RunResult(input={}, status="failed", error="boom", locator=None, events=[])
    buf = _sink(monkeypatch)
    _render_run_error(result, flow, text)
    out = buf.getvalue()
    assert "run failed:" in out
    assert "╭" not in out                          # no boxed frame

