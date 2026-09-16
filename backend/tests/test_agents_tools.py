"""Tests for the web_search payload trimming (no network)."""

from __future__ import annotations

from cadence.agents.tools import (
    MAX_ORGANIC_RESULTS,
    _trim_serp_payload,
    note_web_search,
    record_web_searches,
)


def _raw_result(i: int) -> dict[str, object]:
    return {
        "position": i,
        "title": f"Result {i}",
        "link": f"https://example.com/{i}",
        "snippet": f"Snippet {i}",
        "displayed_link": f"example.com/{i}",
        "sitelinks": {"inline": [{"title": "x", "link": "y"}]},
    }


def test_trim_caps_organic_results_and_keeps_useful_fields() -> None:
    raw = {
        "search_metadata": {"id": "abc", "status": "Success"},
        "pagination": {"next": "..."},
        "organic_results": [_raw_result(i) for i in range(10)],
    }

    trimmed = _trim_serp_payload(raw)

    assert set(trimmed) == {"organic_results"}  # bulky sections dropped
    assert len(trimmed["organic_results"]) == MAX_ORGANIC_RESULTS
    assert trimmed["organic_results"][0] == {
        "title": "Result 0",
        "link": "https://example.com/0",
        "snippet": "Snippet 0",
    }


def test_trim_includes_answer_box_and_knowledge_graph_when_present() -> None:
    raw = {
        "organic_results": [],
        "answer_box": {"type": "organic_result", "answer": "42", "extra": "drop"},
        "knowledge_graph": {
            "title": "Acme Corp",
            "type": "Company",
            "description": "A company.",
            "image": "drop-me",
        },
    }

    trimmed = _trim_serp_payload(raw)

    assert trimmed["answer_box"] == {"answer": "42"}
    assert trimmed["knowledge_graph"] == {
        "title": "Acme Corp",
        "type": "Company",
        "description": "A company.",
    }


def test_trim_surfaces_serpapi_error() -> None:
    trimmed = _trim_serp_payload({"error": "Invalid API key."})
    assert trimmed["error"] == "Invalid API key."


def test_record_web_searches_captures_each_note() -> None:
    with record_web_searches() as research:
        note_web_search("query one", {"organic_results": [{"title": "a"}]})
        note_web_search("query two", None, error="boom")

    assert research == [
        {
            "query": "query one",
            "results": {"organic_results": [{"title": "a"}]},
            "error": None,
        },
        {"query": "query two", "results": None, "error": "boom"},
    ]


def test_recorder_keeps_partial_research_when_body_raises() -> None:
    # The yielded list is bound at ``with`` entry, so research captured before an
    # exception is still available to the caller after the block unwinds.
    captured: list[dict[str, object]] = []
    try:
        with record_web_searches() as research:
            captured = research
            note_web_search("before failure", {"organic_results": []})
            raise RuntimeError("mid-run failure")
    except RuntimeError:
        pass

    assert [entry["query"] for entry in captured] == ["before failure"]


def test_note_web_search_is_a_noop_without_a_recorder() -> None:
    # No active recorder → the call must not raise (tools/fakes call it blindly).
    note_web_search("no recorder installed", {"organic_results": []})
