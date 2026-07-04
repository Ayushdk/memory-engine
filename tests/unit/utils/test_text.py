from app.utils.text import summarize


def test_multi_sentence_keeps_first():
    assert (
        summarize("We chose FastAPI. It has great typing support. Also fast.")
        == "We chose FastAPI."
    )


def test_single_short_sentence_yields_none():
    # no gain over content → builder falls back to content
    assert summarize("We chose FastAPI.") is None


def test_long_sentence_is_capped_with_ellipsis():
    result = summarize("We decided " + "x" * 300 + " end.")
    assert len(result) <= 140
    assert result.endswith("…")


def test_whitespace_is_collapsed():
    assert summarize("We chose\n  FastAPI.\nBecause typing.") == "We chose FastAPI."


def test_question_and_exclamation_are_sentence_ends():
    assert summarize("Which store should we pick? I lean toward Chroma.") == (
        "Which store should we pick?"
    )
