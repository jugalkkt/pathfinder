from report import build_markdown_report


def test_report_contains_query_summary_and_log():
    logs = [
        {"type": "search_start", "query": "eu ai act", "loop_count": 1},
        {"type": "search_result", "content": "Title: A\nURL: https://a.com\nSnippet: s\n---", "loop_count": 1},
        {"type": "chatbot_response", "content": "The summary"},
        {"type": "error", "message": "rate limited"},
    ]

    md = build_markdown_report("What is the EU AI Act?", 3, "The summary", logs)

    assert md.startswith("# Pathfinder AI Research Report\n")
    assert "## Query\n> What is the EU AI Act?" in md
    assert "## Research Summary\n\nThe summary" in md
    assert "### [Reasoning Loop - Search 1/3]\nFormulating query: `eu ai act`" in md
    assert "```\nTitle: A\nURL: https://a.com\nSnippet: s\n---\n```" in md
    assert "*Error: rate limited*" in md


def test_report_with_no_logs():
    md = build_markdown_report("q", 1, "answer", [])
    assert md.rstrip().endswith("## Thought Process Logs")
