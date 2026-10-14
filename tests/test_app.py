import os

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from streamlit.testing.v1 import AppTest

import agent

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
SEARCH_OUTPUT = "Title: EU AI Act\nURL: https://example.eu/act\nSnippet: Fines up to $35M.\n---"


class FakeGraph:
    """Replaces the compiled LangGraph app: one search round, then a summary."""

    def __init__(self, summary="The EU AI Act sets fines from $7.5M to $35M.", error=None):
        self.summary = summary
        self.error = error
        self.calls = []

    def stream(self, state):
        self.calls.append(state)
        if self.error:
            raise self.error
        tool_call = {"name": "web_search", "args": {"query": "eu ai act fines"}, "id": "call_1"}
        yield {"chatbot": {"messages": [AIMessage(content="", tool_calls=[tool_call])], "loop_count": 1}}
        yield {"tools": {"messages": [ToolMessage(content=SEARCH_OUTPUT, tool_call_id="call_1")]}}
        yield {"chatbot": {"messages": [AIMessage(content=self.summary)], "loop_count": 1}}


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph()
    # app.py does `from agent import app` on every script run, so patching the module attribute is enough
    monkeypatch.setattr(agent, "app", fake)
    return fake


def new_app():
    return AppTest.from_file(APP_PATH, default_timeout=30)


def submit(at, query, budget=None):
    at.text_area(key="query_input").input(query)
    if budget is not None:
        at.slider(key="budget_input").set_value(budget)
    research_button(at).click()
    return at.run()


def research_button(at):
    return next(b for b in at.button if b.label == "Research")


def all_markdown(at):
    return "\n".join(m.value for m in at.markdown)


def test_initial_render(graph):
    at = new_app().run()

    assert not at.exception
    assert at.title[0].value.endswith("Pathfinder")
    assert at.slider(key="budget_input").value == agent.DEFAULT_MAX_SEARCHES
    assert "10 of 10 queries left this session" in [c.value for c in at.caption]
    assert "No past research yet" in [c.value for c in at.sidebar.caption]
    assert not research_button(at).disabled


def test_missing_api_key_blocks_research(graph, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    at = new_app().run()

    assert "GROQ_API_KEY" in at.error[0].value
    assert research_button(at).disabled


def test_research_run_shows_log_summary_and_saves_history(graph):
    at = submit(new_app().run(), "What are the EU AI Act fines?", budget=2)

    assert not at.exception
    assert graph.calls[0]["max_searches"] == 2
    assert graph.calls[0]["messages"] == [("user", "What are the EU AI Act fines?")]

    md = all_markdown(at)
    assert "search 1/2: `eu ai act fines`" in md
    assert "[EU AI Act](https://example.eu/act)" in md
    assert at.subheader[0].value == "Research summary"
    # Dollar signs are escaped so Streamlit doesn't render them as LaTeX
    assert "fines from \\$7.5M to \\$35M." in md
    assert at.code[0].value == graph.summary  # copyable raw text keeps the real "$"

    assert "9 of 10 queries left this session" in [c.value for c in at.caption]
    history = at.session_state["history"]
    assert [e["query"] for e in history] == ["What are the EU AI Act fines?"]
    assert history[0]["final_answer"] == graph.summary
    assert [log["type"] for log in history[0]["logs"]] == ["search_start", "search_result", "chatbot_response"]
    assert any(b.label == "What are the EU AI Act fines?" for b in at.sidebar.button)


def test_repeat_query_replaces_history_entry(graph):
    at = submit(new_app().run(), "same question")
    at = submit(at, "other question")
    at = submit(at, "same question")

    assert [e["query"] for e in at.session_state["history"]] == ["same question", "other question"]


def test_history_capped_at_20(graph):
    at = new_app().run()
    for i in range(22):
        at.session_state["queries_used"] = 0  # lift the session cap for this test
        at = submit(at, f"question {i}")

    history = at.session_state["history"]
    assert len(history) == 20
    assert history[0]["query"] == "question 21"


def test_load_and_delete_history_entry(graph):
    at = submit(new_app().run(), "first question", budget=3)
    at = submit(at, "second question", budget=5)

    next(b for b in at.sidebar.button if b.label == "first question").click()
    at.run()
    assert at.text_area(key="query_input").value == "first question"
    assert at.slider(key="budget_input").value == 3
    assert at.session_state["result"]["query"] == "first question"

    first_id = at.session_state["result"]["id"]
    at.sidebar.button(key=f"delete_{first_id}").click()
    at.run()
    assert [e["query"] for e in at.session_state["history"]] == ["second question"]
    assert at.session_state["result"] is None


def test_clear_all_history(graph):
    at = submit(new_app().run(), "a question")

    next(b for b in at.button if b.label == "Yes, clear history").click()
    at.run()

    assert at.session_state["history"] == []
    assert "No past research yet" in [c.value for c in at.sidebar.caption]


def test_empty_query_is_rejected(graph):
    at = submit(new_app().run(), "   ")

    assert graph.calls == []
    assert at.session_state["queries_used"] == 0
    assert "Enter a question first." in [w.value for w in at.warning]


def test_session_query_cap(graph):
    at = new_app().run()
    at.session_state["queries_used"] = 10
    at.run()

    assert research_button(at).disabled
    assert "You've used all 10 research queries for this session." in [w.value for w in at.warning]


def test_agent_error_is_shown_and_recorded(monkeypatch):
    monkeypatch.setattr(agent, "app", FakeGraph(error=RuntimeError("Groq rate limit exceeded")))
    at = submit(new_app().run(), "will fail")

    assert not at.exception
    assert "Research failed: Groq rate limit exceeded" in [e.value for e in at.error]
    entry = at.session_state["history"][0]
    assert entry["final_answer"] == ""
    assert entry["logs"] == [{"type": "error", "message": "Groq rate limit exceeded"}]
