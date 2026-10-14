import os
import json
import time
from datetime import datetime
import streamlit as st
# The component behind streamlit_local_storage.LocalStorage. We call it directly with
# default=None so "browser hasn't replied yet" (None) is distinguishable from "storage
# is empty" - the LocalStorage class can't tell them apart and would let the first
# page load overwrite saved history with []. Pinned to 0.0.25 in requirements.txt.
from streamlit_local_storage import _st_local_storage
from agent import app as agent_app, parse_search_results, DEFAULT_MAX_SEARCHES
from report import build_markdown_report

MAX_QUERIES_PER_SESSION = 10
MAX_HISTORY = 20
HISTORY_KEY = "pathfinder_history"

st.set_page_config(page_title="Pathfinder", page_icon=":material/explore:")

# ==========================================
# SESSION STATE
# ==========================================
defaults = {
    "history": [],          # past runs, newest first (mirrored to browser localStorage)
    "hydrated": False,      # True once saved history has been read from the browser
    "queries_used": 0,      # per-session cap to protect the shared Groq key
    "result": None,         # the run currently on screen
    "query_input": "",
    "budget_input": DEFAULT_MAX_SEARCHES,
}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)


def escape_dollars(text: str) -> str:
    # st.markdown renders $...$ as LaTeX, which mangles prices like "$5 to $10"
    return (text or "").replace("$", "\\$")


# ==========================================
# HISTORY (browser localStorage)
# ==========================================
def load_saved_history(stored: dict) -> list[dict]:
    raw = stored.get(HISTORY_KEY)
    if not raw:
        return []
    try:
        saved = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return []
    return saved if isinstance(saved, list) else []


def add_to_history(entry: dict):
    # Newest first, one entry per query, capped at MAX_HISTORY
    others = [e for e in st.session_state.history if e["query"] != entry["query"]]
    st.session_state.history = [entry] + others[: MAX_HISTORY - 1]


def load_entry(entry: dict):
    st.session_state.result = entry
    st.session_state.query_input = entry["query"]
    st.session_state.budget_input = entry["max_searches"]


def delete_entry(entry_id: str):
    st.session_state.history = [e for e in st.session_state.history if e["id"] != entry_id]
    if st.session_state.result and st.session_state.result["id"] == entry_id:
        st.session_state.result = None


def clear_history():
    st.session_state.history = []


# ==========================================
# RENDERING
# ==========================================
def render_log_entry(log: dict, max_searches: int):
    if log["type"] == "search_start":
        st.markdown(f":material/psychology: **Reasoning** · search {log['loop_count']}/{max_searches}: "
                    f"`{log['query']}`")
    elif log["type"] == "search_result":
        sources = parse_search_results(log["content"])
        with st.expander(f"Web search · {len(sources)} sources", icon=":material/travel_explore:"):
            for source in sources:
                title = escape_dollars(source["title"] or source["url"] or "Source").replace("[", "(").replace("]", ")")
                heading = f"**[{title}]({source['url']})**" if source["url"] else f"**{title}**"
                st.markdown(f"{heading}  \n{escape_dollars(source['snippet'])}")
    elif log["type"] == "search_retry":
        st.caption(f":material/hourglass_top: Search for `{log['query']}` failed (DuckDuckGo may be rate-limiting). "
                   f"Retrying in {log['wait']}s, attempt {log['attempt']}/{log['attempts']}…")
    elif log["type"] == "chatbot_response":
        st.markdown(":material/edit_note: **Synthesizing** the final summary")
    elif log["type"] == "error":
        st.error(log["message"], icon=":material/error:")


def render_result(result: dict):
    errors = [log["message"] for log in result["logs"] if log["type"] == "error"]
    failed = bool(errors) and not result["final_answer"]

    with st.status("Research failed" if failed else "Research thought process",
                   state="error" if failed else "complete", expanded=False):
        for log in result["logs"]:
            render_log_entry(log, result["max_searches"])

    if failed:
        st.error(f"Research failed: {errors[-1]}", icon=":material/error:")
    if not result["final_answer"]:
        return

    st.subheader("Research summary")
    st.markdown(escape_dollars(result["final_answer"]))

    col_copy, col_export = st.columns([3, 1], vertical_alignment="top")
    with col_copy:
        with st.expander("Copy summary", icon=":material/content_copy:"):
            st.code(result["final_answer"], language=None, wrap_lines=True)
    with col_export:
        st.download_button(
            "Export .md",
            data=build_markdown_report(result["query"], result["max_searches"], result["final_answer"], result["logs"]),
            file_name=f"pathfinder_research_{result['id']}.md",
            mime="text/markdown",
            icon=":material/download:",
            width="stretch",
        )


def run_research(query: str, max_searches: int) -> dict:
    """Stream the agent graph, rendering each step live, and return the finished run."""
    logs = []
    final_answer = ""
    state = {"messages": [("user", query)], "loop_count": 0, "max_searches": max_searches}

    with st.status("Researching…", expanded=True) as status:
        progress = st.progress(0.0, text=f"Searches used: 0/{max_searches}")
        try:
            # "updates" yields each node's state update; "custom" yields progress events the
            # search tool emits while it waits to retry
            for mode, chunk in agent_app.stream(state, stream_mode=["updates", "custom"]):
                new_logs = [chunk] if mode == "custom" else []
                for node_name, update in (chunk.items() if mode == "updates" else []):
                    if node_name == "chatbot":
                        message = update["messages"][-1]
                        loop_count = update.get("loop_count", 0)
                        if message.tool_calls:
                            # Number each search: loop_count already includes this turn's searches
                            first = loop_count - len(message.tool_calls) + 1
                            new_logs = [{"type": "search_start", "query": call["args"].get("query", ""),
                                         "loop_count": first + i} for i, call in enumerate(message.tool_calls)]
                            progress.progress(min(loop_count / max_searches, 1.0),
                                              text=f"Searches used: {loop_count}/{max_searches}")
                        elif message.content:
                            final_answer = message.content
                            new_logs = [{"type": "chatbot_response", "content": message.content}]
                    elif node_name == "tools":
                        # One ToolMessage per tool call made in the previous chatbot turn
                        new_logs = [{"type": "search_result", "content": m.content} for m in update["messages"]]

                for log in new_logs:
                    logs.append(log)
                    render_log_entry(log, max_searches)

            status.update(label="Research complete", state="complete", expanded=False)
        except Exception as e:
            logs.append({"type": "error", "message": str(e)})
            st.error(str(e), icon=":material/error:")
            status.update(label="Research failed", state="error")

    return {
        "id": str(int(time.time() * 1000)),
        "query": query,
        "max_searches": max_searches,
        "logs": logs,
        "final_answer": final_answer,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ==========================================
# SIDEBAR: HISTORY
# ==========================================
with st.sidebar:
    st.header(":material/history: Research history")
    history_slot = st.container()   # filled below, after saved history has been read
    stored = _st_local_storage(method="getAll", key="ls_read", default=None)

if stored is not None and not st.session_state.hydrated:
    # Merge, so a run finished before the browser replied isn't lost
    session_ids = {e["id"] for e in st.session_state.history}
    saved = [e for e in load_saved_history(stored) if e.get("id") not in session_ids]
    st.session_state.history = (st.session_state.history + saved)[:MAX_HISTORY]
    st.session_state.hydrated = True

with history_slot:
    if not st.session_state.history:
        st.caption("No past research yet")
    for entry in st.session_state.history:
        col_load, col_delete = st.columns([4, 1], vertical_alignment="center")
        col_load.button(entry["query"], key=f"load_{entry['id']}", help=f"{entry['timestamp']} · limit {entry['max_searches']}",
                        on_click=load_entry, args=(entry,), width="stretch")
        col_delete.button(":material/delete:", key=f"delete_{entry['id']}", help="Delete", type="tertiary",
                          on_click=delete_entry, args=(entry["id"],))
    if st.session_state.history:
        with st.popover("Clear all", icon=":material/delete_sweep:"):
            st.write("Delete all saved research?")
            st.button("Yes, clear history", on_click=clear_history, type="primary")

# ==========================================
# MAIN
# ==========================================
st.title(":material/explore: Pathfinder")
st.caption("Autonomous web research assistant with a live view of the agent's thought process")

has_api_key = bool(os.getenv("GROQ_API_KEY"))
queries_left = MAX_QUERIES_PER_SESSION - st.session_state.queries_used

if not has_api_key:
    st.error("`GROQ_API_KEY` isn't set. Add it to `.env` locally or to the app's secrets on Streamlit Cloud.")

with st.form("research_form"):
    query = st.text_area("Ask Pathfinder", key="query_input", placeholder="e.g. Summarize the latest AI safety guidelines in the EU")
    max_searches = st.slider("Search limit budget", min_value=1, max_value=8, key="budget_input",
                             help="When the agent reaches this many searches it stops searching and writes its summary.")
    submitted = st.form_submit_button("Research", icon=":material/auto_awesome:", type="primary",
                                      disabled=not has_api_key or queries_left <= 0)

if queries_left <= 0:
    st.warning(f"You've used all {MAX_QUERIES_PER_SESSION} research queries for this session.")
else:
    st.caption(f"{queries_left} of {MAX_QUERIES_PER_SESSION} queries left this session")

if submitted and query.strip():
    st.session_state.queries_used += 1
    result = run_research(query.strip(), max_searches)
    st.session_state.result = result
    add_to_history(result)
    st.rerun()
elif submitted:
    st.warning("Enter a question first.")

if st.session_state.result:
    render_result(st.session_state.result)

# Mirror history to the browser - only after it has been read, so we never overwrite it with []
if st.session_state.hydrated:
    with st.sidebar:
        _st_local_storage(method="setItem", itemKey=HISTORY_KEY,
                          itemValue=json.dumps(st.session_state.history), key="ls_write")
