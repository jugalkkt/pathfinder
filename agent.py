import os
import re
import json
import uuid
from typing import TypedDict, Annotated
from dotenv import load_dotenv
from ddgs import DDGS
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, convert_to_messages
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# Load environment variables from .env file (locally) - on Streamlit Cloud,
# root-level secrets are exposed as environment variables instead
load_dotenv()

# Groq retired llama-3.1-8b-instant on 2026-08-16; gpt-oss-20b is its official replacement.
# Override with the GROQ_MODEL env var / secret without touching code.
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
# reasoning_effort is only accepted by reasoning models
SUMMARY_KWARGS = {"reasoning_effort": "low"} if MODEL.startswith("openai/gpt-oss") else {}
DEFAULT_MAX_SEARCHES = 4
RESULTS_PER_SEARCH = 5

# ==========================================
# TOOLS
# ==========================================

# The @tool decorator converts a standard Python function into a tool
# that LangChain and the LLM can understand. The docstring acts as the
# tool description that teaches the LLM when to use this tool.
@tool
def web_search(query: str) -> str:
    """Searches the web using DuckDuckGo to get real-time information and answer questions."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=RESULTS_PER_SEARCH))
    except Exception as e:
        return f"Search error: {e}"

    if not results:
        return f"No results found for query: {query}"

    # Structured format the UI parses into source cards (see parse_search_results)
    formatted_results = []
    for r in results:
        title = r.get("title", "No Title")
        href = r.get("href", "")
        body = r.get("body", "")
        formatted_results.append(f"Title: {title}\nURL: {href}\nSnippet: {body}\n---")
    return "\n\n".join(formatted_results)

# Collect all tools in a list
tools = [web_search]


def parse_search_results(content: str) -> list[dict]:
    """Parse web_search output (Title/URL/Snippet blocks separated by ---) into dicts."""
    if not content:
        return []
    if "Title:" not in content or "URL:" not in content:
        return [{"title": "Web Search Result", "url": "", "snippet": content}]

    sources = []
    for block in content.split("---"):
        source = {"title": "", "url": "", "snippet": ""}
        for line in block.strip().split("\n"):
            for field, prefix in (("title", "Title:"), ("url", "URL:"), ("snippet", "Snippet:")):
                if line.startswith(prefix):
                    source[field] = line[len(prefix):].strip()
        if any(source.values()):
            sources.append(source)
    return sources


# Matches patterns like <tool_name>JSON</function> or <tool_name>JSON</tool_name>
TEXT_TOOL_CALL_PATTERN = re.compile(r"<(\w+)>(\{[\s\S]*?\})(?:</function>|</\1>)")

def parse_text_tool_calls(content: str) -> list[dict]:
    """Recover tool calls a model wrote into its text instead of native tool_calls."""
    parsed_tool_calls = []
    for match in TEXT_TOOL_CALL_PATTERN.finditer(content or ""):
        try:
            args = json.loads(match.group(2))
        except json.JSONDecodeError:
            continue
        parsed_tool_calls.append({
            "name": match.group(1),
            "args": args,
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "type": "tool_call",
        })
    return parsed_tool_calls

# ==========================================
# STATE & GRAPH
# ==========================================

# The state is what gets passed around the graph from node to node.
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    loop_count: int
    max_searches: int

def summary_context(messages: list) -> list:
    """Collapse the history for the forced-summary turn into a single user message: the
    question, the search results as plain text, and an explicit "answer now".

    gpt-oss was trained with a built-in browser tool. With tool-call history (or even the
    results as a separate message) it tries to call a tool although none are bound, and
    Groq rejects the request: 400 "Tool choice is none, but model called a tool"."""
    messages = convert_to_messages(messages)
    question = "\n\n".join(m.content for m in messages if isinstance(m, HumanMessage))
    results = [m.content for m in messages if isinstance(m, ToolMessage)]
    gathered = "\n\n".join(results) if results else "(no search results)"
    return [HumanMessage(content=f"{question}\n\nHere are web search results that were already gathered:\n\n{gathered}\n\n"
                                 f"Tools are unavailable. Write the final answer now, as plain text, citing URLs from the results.")]

# The "brain" node
def chatbot_node(state: AgentState):
    loop_count = state.get("loop_count", 0)
    max_searches = state.get("max_searches", DEFAULT_MAX_SEARCHES)

    # Check if the search threshold has been reached
    tools_bound = loop_count < max_searches
    if not tools_bound:
        # Force the agent to summarize without calling any tools. Low reasoning effort also
        # stops gpt-oss from reaching for its built-in browser tool (see summary_context).
        llm_to_call = ChatGroq(model=MODEL, temperature=0, **SUMMARY_KWARGS)
        system_prompt = SystemMessage(
            content=f"You are Pathfinder, an autonomous web research assistant. "
                    f"You have reached the maximum search limit ({max_searches} searches). DO NOT search anymore or call any tools. "
                    f"Analyze the information you have already gathered and write the final summary. "
                    f"Cite URLs from the search results in your response."
        )
        messages = summary_context(state["messages"])
    else:
        # temperature=0 for deterministic tool-calling
        llm_to_call = ChatGroq(model=MODEL, temperature=0).bind_tools(tools)
        system_prompt = SystemMessage(
            content="You are Pathfinder, an autonomous web research assistant. "
                    "Use the web_search tool to find real-time information and answer the user's questions. "
                    "Do not perform redundant or repeated searches if you already have the information needed. "
                    "When synthesizing findings, cite URLs from search results in your response."
        )
        messages = state["messages"]

    response = llm_to_call.invoke([system_prompt] + messages)

    # Some models write tool calls into the text instead of returning native tool_calls.
    # Only honoured while tools are bound - otherwise it would search past the budget.
    if tools_bound and not getattr(response, "tool_calls", None) and response.content:
        parsed_tool_calls = parse_text_tool_calls(response.content)
        if parsed_tool_calls:
            response.tool_calls = parsed_tool_calls
            # Clear response content to prevent it from displaying raw tag content
            response.content = ""

    # Each tool-calling turn consumes one unit of the search budget
    new_loop_count = loop_count
    if getattr(response, "tool_calls", None):
        new_loop_count += 1

    return {"messages": [response], "loop_count": new_loop_count}

# Build the graph
workflow = StateGraph(AgentState)
workflow.add_node("chatbot", chatbot_node)
workflow.add_node("tools", ToolNode(tools))
workflow.add_edge(START, "chatbot")

# tools_condition routes to "tools" if the chatbot returned tool_calls, otherwise to END
workflow.add_conditional_edges("chatbot", tools_condition)

# After tools node executes, route back to chatbot to evaluate the results (reflection loop)
workflow.add_edge("tools", "chatbot")

app = workflow.compile()

# Run the agent in the terminal (for testing)
if __name__ == "__main__":
    print("Pathfinder Initialized with Web Search! (Type 'exit' to quit)")

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            break

        initial_state = {"messages": [("user", user_input)], "loop_count": 0, "max_searches": DEFAULT_MAX_SEARCHES}

        for event in app.stream(initial_state):
            for node_name, node_state in event.items():
                latest_message = node_state["messages"][-1]

                if node_name == "chatbot":
                    if latest_message.tool_calls:
                        current_count = node_state.get("loop_count", 0)
                        for tool_call in latest_message.tool_calls:
                            print(f"\nPathfinder (Reasoning): I need to search the web for '{tool_call['args'].get('query')}' "
                                  f"(Search count: {current_count}/{DEFAULT_MAX_SEARCHES})")
                    elif latest_message.content:
                        print(f"\nPathfinder ({node_name}): {latest_message.content}")

                elif node_name == "tools":
                    print("\nPathfinder (Action): Executed Web Search!")
                    print(f"Results: {latest_message.content}")
