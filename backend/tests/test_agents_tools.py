"""Tests for the web_search payload trimming (no network)."""

from __future__ import annotations

from cadence.agents.tools import (
    MAX_ORGANIC_RESULTS,
    MAX_TOP_STORIES,
    _trim_serp_payload,
    _trim_serper_payload,
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


def _raw_story(i: int, source: object = "Reuters") -> dict[str, object]:
    return {
        "title": f"Story {i}",
        "link": f"https://news.example.com/{i}",
        "source": source,
        "date": f"{i + 1} hours ago",
        "thumbnail": "drop-me",
    }


def test_trim_keeps_top_stories_and_result_dates() -> None:
    raw = {
        "organic_results": [{**_raw_result(0), "date": "Nov 12, 2026"}],
        "top_stories": [_raw_story(i) for i in range(8)],
    }

    trimmed = _trim_serp_payload(raw)

    assert trimmed["organic_results"][0]["date"] == "Nov 12, 2026"
    assert len(trimmed["top_stories"]) == MAX_TOP_STORIES
    assert trimmed["top_stories"][0] == {
        "title": "Story 0",
        "link": "https://news.example.com/0",
        "source": "Reuters",
        "date": "1 hours ago",
    }


def test_trim_flattens_sectioned_top_stories() -> None:
    raw = {"top_stories": {"latest": [_raw_story(0)], "more": [_raw_story(1)]}}
    assert [s["title"] for s in _trim_serp_payload(raw)["top_stories"]] == [
        "Story 0",
        "Story 1",
    ]


def test_trim_omits_absent_top_stories() -> None:
    assert "top_stories" not in _trim_serp_payload({"organic_results": [], "top_stories": []})


def test_trim_surfaces_serpapi_error() -> None:
    trimmed = _trim_serp_payload({"error": "Invalid API key."})
    assert trimmed["error"] == "Invalid API key."


def _raw_serper_result(i: int) -> dict[str, object]:
    return {
        "position": i,
        "title": f"Result {i}",
        "link": f"https://example.com/{i}",
        "snippet": f"Snippet {i}",
        "sitelinks": [{"title": "x", "link": "y"}],
    }


def test_trim_serper_normalises_to_the_shared_shape() -> None:
    # Serper uses organic / answerBox / knowledgeGraph; the trimmed output must
    # match what _trim_serp_payload produces so downstream consumers see one shape.
    raw = {
        "searchParameters": {"q": "x"},
        "organic": [_raw_serper_result(i) for i in range(10)],
        "answerBox": {"title": "t", "answer": "42", "extra": "drop"},
        "knowledgeGraph": {
            "title": "Acme Corp",
            "type": "Company",
            "description": "A company.",
            "imageUrl": "drop-me",
        },
    }

    trimmed = _trim_serper_payload(raw)

    assert set(trimmed) == {"organic_results", "answer_box", "knowledge_graph"}
    assert len(trimmed["organic_results"]) == MAX_ORGANIC_RESULTS
    assert trimmed["organic_results"][0] == {
        "title": "Result 0",
        "link": "https://example.com/0",
        "snippet": "Snippet 0",
    }
    assert trimmed["answer_box"] == {"title": "t", "answer": "42"}
    assert trimmed["knowledge_graph"] == {
        "title": "Acme Corp",
        "type": "Company",
        "description": "A company.",
    }


def test_trim_serper_top_stories_match_the_serpapi_shape() -> None:
    serper = _trim_serper_payload(
        {
            "organic": [{**_raw_serper_result(0), "date": "Nov 12, 2026"}],
            "topStories": [_raw_story(0, source={"name": "Reuters"})],
        }
    )
    serp = _trim_serp_payload(
        {
            "organic_results": [{**_raw_result(0), "date": "Nov 12, 2026"}],
            "top_stories": [_raw_story(0)],
        }
    )
    assert serper == serp


def test_trim_serper_surfaces_error() -> None:
    trimmed = _trim_serper_payload({"error": "Unauthorized."})
    assert trimmed["error"] == "Unauthorized."


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
