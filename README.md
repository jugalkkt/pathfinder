# Pathfinder: Autonomous Web Research Agent

**Pathfinder** is a task-oriented AI research agent built with LangGraph and Streamlit. Give it a research question (e.g. *"Summarize the latest AI safety guidelines in the EU"*) and it plans search queries, searches the web, reflects on what it found, decides whether it needs more, and writes a summary with cited sources. You watch every step happen live.

Rather than producing a single, immediate LLM response, Pathfinder runs as a cyclic agent: reason → search → reflect → repeat, until it has enough information or runs out of search budget.

---

## Key Features

* **Live thought process**: Each reasoning step and web search streams into the page as it happens, with an expandable list of sources (title, link, snippet) for every search.
* **Adjustable search budget**: A slider (1–8) caps how many search rounds the agent may run. Once the budget is used up, its tools are unbound and it is forced to write the summary.
* **Copy & Markdown export**: Copy the summary, or download a `.md` report containing the query, the summary and the full reasoning log.
* **Search history**: The last 20 runs are kept in the sidebar and saved in your browser's `localStorage`, so they survive page reloads and can be reopened without calling the LLM again.
* **Shared-key protection**: The public demo allows 10 queries per browser session.

---

## Tech Stack

* **Agent**: Python 3.11, LangGraph, LangChain, Groq API (`openai/gpt-oss-20b`)
* **Search**: DuckDuckGo via `ddgs`
* **UI**: Streamlit, `streamlit-local-storage`
* **Testing**: pytest, Streamlit AppTest
* **Hosting**: Streamlit Community Cloud

---

## System Architecture & Graph Flow

Pathfinder is a stateful, cyclic graph built with **LangGraph**: two nodes joined by a conditional edge.

```mermaid
graph TD
    Start([User Query]) --> Init[Initialize Agent State]
    Init --> Chatbot[Chatbot Node]
    Chatbot --> Check{Tools Condition}
    Check -- Calls Tool --> Tools[Tools Node: DuckDuckGo Search]
    Tools --> Chatbot
    Check -- No Tool / Budget Limit --> End([Generate Final Summary & Terminate])
```

1. **State**: Holds the conversation `messages`, the number of search rounds so far (`loop_count`) and the user's budget (`max_searches`).
2. **Chatbot node**: While `loop_count < max_searches` it binds the search tool to the LLM. Once the budget is used up, it calls the LLM without tools and instructs it to summarize. If the model writes a tool call as text instead of a native `tool_calls` entry, a regex fallback recovers it.
3. **Tools node**: Runs `web_search` (DuckDuckGo, 5 results per call) and appends the results to the state.
4. **Conditional edge**: Goes to the tools node if the chatbot requested a tool, otherwise ends the run.

The Streamlit app calls `app.stream(...)` on the compiled graph and renders each node's update as it arrives. There is no separate backend.

---

## Repository Structure

```
├── app.py                 # Streamlit UI: live log, budget slider, summary, export, history
├── agent.py               # LangGraph agent: state, nodes, search tool, parsers
├── report.py              # Markdown report builder for the export button
├── tests/                 # pytest + Streamlit AppTest suite (LLM and search mocked)
├── requirements.txt       # Runtime dependencies (what Streamlit Cloud installs)
├── requirements-dev.txt   # + test dependencies
├── .env.example           # Local environment variables
└── .streamlit/
    └── secrets.toml.example   # Streamlit secrets template
```

---

## Getting Started

### 1. Install
```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
```

### 2. Add your Groq API key
Create a `.env` file in the project root (see `.env.example`):
```env
GROQ_API_KEY=your_groq_api_key_here
```
Optionally set `GROQ_MODEL` to use a different Groq model.

### 3. Run
```bash
streamlit run app.py
```
The app opens at `http://localhost:8501`. You can also chat with the agent in the terminal with `python agent.py`.

### 4. Test
```bash
pytest
```
The tests mock the LLM, the web search and the agent graph, so they need no API key or network access.

---

## Deploying to Streamlit Community Cloud

1. Push the repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), create a new app and choose this repo, branch `main`, main file `app.py`.
3. In **Advanced settings**, pick Python 3.11 and paste into **Secrets**:
   ```toml
   GROQ_API_KEY = "your_groq_api_key_here"
   ```
4. Deploy. Streamlit exposes root-level secrets as environment variables, so no code changes are needed.

---

## Design Notes

### LangGraph vs. linear LangChain chains
A linear chain runs each step once, in order. An autonomous agent needs loops, e.g. "search again if the results weren't enough". LangGraph models the agent as a stateful graph with cyclic edges, which allows repeated rounds of reasoning, tool calls and self-correction.

### The ReAct (Reasoning + Acting) pattern
* **Reasoning**: The model decides *what* it needs to search for.
* **Acting**: It calls the search tool.
* **Reflection**: It reads the results and decides whether they are enough to answer the question.

### Bounding cost with a search budget
`max_searches` lives in the graph state. When it's reached, the chatbot node stops binding tools, so the model *cannot* call another search and has to synthesize an answer. This prevents runaway loops and keeps token use predictable.

### The forced-summary turn and gpt-oss
`gpt-oss` was trained with a built-in browser tool. On the forced-summary turn no tools are bound, but if the history contains tool calls, the model still tries to call one (even `browser.open`), and Groq rejects the request with `400: Tool choice is none, but model called a tool`. So the summary turn rewrites the history into one plain-text message (question + gathered results + "tools are unavailable, answer now") and uses low reasoning effort. In live testing, the old approach failed 5/5 times on the same input and the new one succeeded 5/5.

### Why Streamlit calls the graph directly
The original version used a FastAPI backend streaming Server-Sent Events to a React frontend. Streamlit can iterate over `app.stream(...)` itself and render each update as it arrives, so the backend and the API contract between the two halves aren't needed. That leaves one process and one deploy.

### Persisting history without a database
Streamlit Cloud's filesystem is wiped on restart and shared by every visitor, so history lives in each visitor's browser `localStorage` instead. The app only writes history after the browser has returned what's already saved. Otherwise the first page load would overwrite saved history with an empty list.
