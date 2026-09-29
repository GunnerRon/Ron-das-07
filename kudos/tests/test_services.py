"""Unit tests for pure business-rule helpers."""

from app.services import find_blocked_terms, normalize_for_duplicate, sanitize_message


def test_sanitize_trims_and_strips_control_chars():
    assert sanitize_message("  hi\x00 there\x07  ") == "hi there"


def test_sanitize_collapses_blank_lines_and_normalises_newlines():
    assert sanitize_message("a\r\n\r\n\r\n\r\nb") == "a\n\nb"


def test_sanitize_non_string_is_empty():
    assert sanitize_message(None) == ""
    assert sanitize_message(123) == ""


def test_normalize_for_duplicate():
    assert normalize_for_duplicate("Great  JOB\n team") == "great job team"


def test_blocked_terms_match_whole_words_only():
    terms = ["hate", "dumb"]
    assert find_blocked_terms("I HATE mondays", terms) == ["hate"]
    assert find_blocked_terms("Whatever, thanks!", terms) == []  # 'hate' inside 'whatever'
    assert find_blocked_terms("Thanks for the dumbbell tips", terms) == []
