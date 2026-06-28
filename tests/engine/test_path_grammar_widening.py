import pytest

from agent_composer.expr.template import parse_binding, _check_path
from agent_composer.expr.expressions import ExpressionError
from agent_composer.compose.cases import _CASE_OUTPUT_INTERIOR


def test_namespaced_path_parses():
    # a namespaced expansion ref: ${each#0/score.output.output} must parse (no ExpressionError)
    parse_binding("${each#0/score.output.output}")
    parse_binding("${a/b.output.output}")
    _check_path("each#0/score.output")
    _check_path("a/b.output")


def test_existing_dotted_paths_still_parse():
    parse_binding("${research.output.report}")
    _check_path("outputs.research.report")


def test_genuinely_bad_path_still_rejected_unchanged():
    with pytest.raises(ExpressionError, match="malformed reference path"):
        _check_path("a..b")          # empty segment still bad


def test_case_output_interior_accepts_separators():
    # the case-output regex accepts the new node-first
    # `<id>.output[.<seg>…]` shape with namespaced ids (`each#0/leaf`).
    assert _CASE_OUTPUT_INTERIOR.match("each#0/leaf.output")
    assert _CASE_OUTPUT_INTERIOR.match("research.output.report")
