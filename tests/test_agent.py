from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import agent


def tool_call_message(query="eu ai act"):
    return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": query}, "id": "call_1"}])


class FakeLLM:
    """Stands in for ChatGroq: searches while tools are bound, answers once they're not."""

    def __init__(self, bound_response=None, final_response="Final summary"):
        self.bound_response = bound_response or tool_call_message()
        self.final_response = final_response
        self.bind_calls = 0
        self.prompts = []
        self.calls = []

    def bind_tools(self, tools):
        self.bind_calls += 1
        bound = MagicMock()
        bound.invoke.side_effect = lambda messages: self._record(messages, self.bound_response.model_copy())
        return bound

    def invoke(self, messages):
        return self._record(messages, AIMessage(content=self.final_response))

    def _record(self, messages, response):
        self.prompts.append(messages[0].content)
        self.calls.append(messages)
        return response


@pytest.fixture
def fake_llm():
    llm = FakeLLM()
    with patch("agent.ChatGroq", return_value=llm) as chat_groq:
        llm.constructor = chat_groq
        yield llm


@pytest.fixture(autouse=True)
def no_sleep():
    # web_search waits between retries; never actually sleep in tests
    with patch("agent.time.sleep") as sleep:
        yield sleep


@pytest.fixture
def fake_ddgs():
    ddgs = MagicMock()
    ddgs.__enter__.return_value = ddgs
    ddgs.text.return_value = [{"title": "EU AI Act", "href": "https://example.eu/act", "body": "Rules for AI."}]
    with patch("agent.DDGS", return_value=ddgs):
        yield ddgs


# ---------- chatbot_node ----------

def test_under_budget_binds_tools_and_counts_search(fake_llm):
    result = agent.chatbot_node({"messages": [("user", "q")], "loop_count": 0, "max_searches": 2})

    assert fake_llm.bind_calls == 1
    assert result["messages"][0].tool_calls[0]["args"] == {"query": "eu ai act"}
    assert result["loop_count"] == 1


def test_budget_exhausted_unbinds_tools_and_forces_summary(fake_llm):
    result = agent.chatbot_node({"messages": [("user", "q")], "loop_count": 2, "max_searches": 2})

    assert fake_llm.bind_calls == 0
    assert "maximum search limit (2 searches)" in fake_llm.prompts[-1]
    assert result["messages"][0].content == "Final summary"
    assert result["loop_count"] == 2


def test_summary_turn_gets_single_plain_text_message(fake_llm):
    history = [
        HumanMessage(content="What are the EU AI Act fines?"),
        tool_call_message(),
        ToolMessage(content="Title: A\nURL: https://a.com\nSnippet: fines\n---", tool_call_id="call_1"),
    ]

    agent.chatbot_node({"messages": history, "loop_count": 1, "max_searches": 1})

    system, *rest = fake_llm.calls[-1]
    # No tool-call or tool-result messages: gpt-oss would try to call a tool and Groq returns 400
    assert len(rest) == 1 and isinstance(rest[0], HumanMessage)
    assert "What are the EU AI Act fines?" in rest[0].content
    assert "URL: https://a.com" in rest[0].content
    assert "Tools are unavailable" in rest[0].content
    fake_llm.constructor.assert_called_with(model=agent.MODEL, temperature=0, **agent.SUMMARY_KWARGS)


def test_summary_kwargs_only_for_gpt_oss():
    assert agent.SUMMARY_KWARGS == ({"reasoning_effort": "low"} if agent.MODEL.startswith("openai/gpt-oss") else {})


def test_text_tool_call_ignored_once_budget_is_used(fake_llm):
    fake_llm.final_response = '<web_search>{"query": "one more"}</function>'

    result = agent.chatbot_node({"messages": [("user", "q")], "loop_count": 2, "max_searches": 2})

    assert not result["messages"][0].tool_calls
    assert result["loop_count"] == 2


def test_answer_without_tool_call_does_not_count(fake_llm):
    fake_llm.bound_response = AIMessage(content="I already know this")

    result = agent.chatbot_node({"messages": [("user", "q")], "loop_count": 1, "max_searches": 4})

    assert result["loop_count"] == 1
    assert result["messages"][0].content == "I already know this"


def test_text_tool_call_is_recovered_and_counted(fake_llm):
    fake_llm.bound_response = AIMessage(content='<web_search>{"query": "groq models"}</function>')

    result = agent.chatbot_node({"messages": [("user", "q")], "loop_count": 0, "max_searches": 4})

    message = result["messages"][0]
    assert message.tool_calls[0]["name"] == "web_search"
    assert message.tool_calls[0]["args"] == {"query": "groq models"}
    assert message.content == ""
    assert result["loop_count"] == 1


def test_each_search_counts_against_budget(fake_llm):
    fake_llm.bound_response = AIMessage(content="", tool_calls=[
        {"name": "web_search", "args": {"query": q}, "id": f"call_{q}"} for q in ("a", "b")])

    result = agent.chatbot_node({"messages": [("user", "q")], "loop_count": 1, "max_searches": 4})

    assert result["loop_count"] == 3


def test_searches_beyond_budget_are_dropped(fake_llm):
    fake_llm.bound_response = AIMessage(content="", tool_calls=[
        {"name": "web_search", "args": {"query": q}, "id": f"call_{q}"} for q in ("a", "b", "c")])

    result = agent.chatbot_node({"messages": [("user", "q")], "loop_count": 2, "max_searches": 4})

    assert [c["args"]["query"] for c in result["messages"][0].tool_calls] == ["a", "b"]
    assert result["loop_count"] == 4


def test_default_budget_used_when_missing(fake_llm):
    agent.chatbot_node({"messages": [("user", "q")], "loop_count": agent.DEFAULT_MAX_SEARCHES})
    assert fake_llm.bind_calls == 0


# ---------- full graph ----------

def test_graph_stops_searching_at_budget(fake_llm, fake_ddgs):
    final_state = agent.app.invoke({"messages": [("user", "q")], "loop_count": 0, "max_searches": 3})

    assert fake_llm.bind_calls == 3
    assert fake_ddgs.text.call_count == 3
    assert final_state["loop_count"] == 3
    assert final_state["messages"][-1].content == "Final summary"


def test_graph_ends_early_when_model_answers(fake_llm, fake_ddgs):
    fake_llm.bound_response = AIMessage(content="Direct answer")

    final_state = agent.app.invoke({"messages": [("user", "q")], "loop_count": 0, "max_searches": 5})

    assert fake_ddgs.text.call_count == 0
    assert final_state["messages"][-1].content == "Direct answer"


# ---------- web_search tool ----------

def test_web_search_formats_results(fake_ddgs):
    output = agent.web_search.invoke({"query": "eu ai act"})

    fake_ddgs.text.assert_called_once_with("eu ai act", max_results=agent.RESULTS_PER_SEARCH)
    assert output == "Title: EU AI Act\nURL: https://example.eu/act\nSnippet: Rules for AI.\n---"


def test_web_search_no_results(fake_ddgs):
    fake_ddgs.text.return_value = []
    assert agent.web_search.invoke({"query": "zzz"}) == "No results found for query: zzz"


def test_web_search_retries_then_returns_error(fake_ddgs, no_sleep):
    fake_ddgs.text.side_effect = RuntimeError("No results found.")

    assert agent.web_search.invoke({"query": "x"}) == "Search error after 4 attempts: No results found."
    assert fake_ddgs.text.call_count == 4
    assert [c.args[0] for c in no_sleep.call_args_list] == list(agent.SEARCH_RETRY_WAITS)


def test_web_search_recovers_on_retry(fake_ddgs, no_sleep):
    good = fake_ddgs.text.return_value
    fake_ddgs.text.side_effect = [RuntimeError("No results found."), good]

    assert agent.web_search.invoke({"query": "x"}).startswith("Title: EU AI Act")
    assert fake_ddgs.text.call_count == 2
    no_sleep.assert_called_once_with(agent.SEARCH_RETRY_WAITS[0])


def test_retry_progress_is_streamed_to_ui(fake_llm, fake_ddgs):
    good = fake_ddgs.text.return_value
    fake_ddgs.text.side_effect = [RuntimeError("No results found."), good]

    chunks = list(agent.app.stream({"messages": [("user", "q")], "loop_count": 0, "max_searches": 1},
                                   stream_mode=["updates", "custom"]))

    custom = [chunk for mode, chunk in chunks if mode == "custom"]
    assert custom == [{"type": "search_retry", "query": "eu ai act", "wait": agent.SEARCH_RETRY_WAITS[0],
                       "attempt": 2, "attempts": len(agent.SEARCH_RETRY_WAITS) + 1}]


def test_web_search_output_round_trips_through_parser(fake_ddgs):
    fake_ddgs.text.return_value = [
        {"title": "A", "href": "https://a.com", "body": "first"},
        {"title": "B", "href": "https://b.com", "body": "second"},
    ]
    sources = agent.parse_search_results(agent.web_search.invoke({"query": "x"}))
    assert sources == [
        {"title": "A", "url": "https://a.com", "snippet": "first"},
        {"title": "B", "url": "https://b.com", "snippet": "second"},
    ]


# ---------- parsers ----------

@pytest.mark.parametrize("text", [
    '<web_search>{"query": "x"}</function>',
    '<web_search>{"query": "x"}</web_search>',
])
def test_parse_text_tool_calls_both_tag_styles(text):
    calls = agent.parse_text_tool_calls(text)
    assert [(c["name"], c["args"], c["type"]) for c in calls] == [("web_search", {"query": "x"}, "tool_call")]
    assert calls[0]["id"].startswith("call_")


def test_parse_text_tool_calls_multiple_and_invalid_json():
    text = '<web_search>{"query": "a"}</function> <web_search>{not json}</function> <web_search>{"query": "b"}</web_search>'
    assert [c["args"]["query"] for c in agent.parse_text_tool_calls(text)] == ["a", "b"]


@pytest.mark.parametrize("text", ["", None, "Plain answer with no tags", "<b>{\"x\": 1}</i>"])
def test_parse_text_tool_calls_no_match(text):
    assert agent.parse_text_tool_calls(text) == []


def test_parse_search_results_unstructured_fallback():
    assert agent.parse_search_results("Search error: boom") == [
        {"title": "Web Search Result", "url": "", "snippet": "Search error: boom"}
    ]


def test_parse_search_results_empty():
    assert agent.parse_search_results("") == []
