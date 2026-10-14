from datetime import datetime


def build_markdown_report(query: str, max_searches: int, final_answer: str, logs: list[dict]) -> str:
    """Build the downloadable Markdown report: query, summary and the agent's thought-process log."""
    md = "# Pathfinder AI Research Report\n"
    md += f"*Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
    md += f"## Query\n> {query}\n\n"
    md += f"## Research Summary\n\n{final_answer}\n\n"
    md += "## Thought Process Logs\n\n"

    for log in logs:
        if log["type"] == "search_start":
            md += f"### [Reasoning Loop - Search {log['loop_count']}/{max_searches}]\n"
            md += f"Formulating query: `{log['query']}`\n\n"
        elif log["type"] == "search_result":
            md += "### [Action - Web Search Result]\n"
            md += f"```\n{log['content']}\n```\n\n"
        elif log["type"] == "error":
            md += f"*Error: {log['message']}*\n\n"

    return md
