"""Co-skip classifier: does a binding co-skip when all its producers are skipped?"""

from agent_composer.expr import binding_co_skips


def test_plain_ref_co_skips():
    assert binding_co_skips("${a.output}") is True


def test_ref_coalesce_co_skips():
    assert binding_co_skips("${a.output | b.output}") is True


def test_ref_default_co_skips():
    assert binding_co_skips("${a.output:-${b.output}}") is True  # default is a ref


def test_literal_default_does_not_co_skip():
    assert binding_co_skips("${a.output:-null}") is False


def test_literal_coalesce_operand_does_not_co_skip():
    assert binding_co_skips('${a.output | "fallback"}') is False


def test_required_does_not_co_skip():
    assert binding_co_skips("${a.output:?missing}") is False


def test_embedded_text_does_not_co_skip():
    assert binding_co_skips("got ${a.output} here") is False


def test_non_string_and_non_ref_do_not_co_skip():
    assert binding_co_skips(30) is False
    assert binding_co_skips("plain literal") is False
    assert binding_co_skips("${input.x}") is True  # whole-string ref still co-skips structurally
