# Pathfinder: The Autonomous Web Research Assistant

**Pathfinder** is a Task-Oriented AI Agent built using modern AI orchestration frameworks and web technologies. This project demonstrates the ability to build, monitor, and deploy an autonomous AI system capable of multi-step reasoning, self-correction, and tool usage.

## Project Overview
Pathfinder is designed to accept a high-level research query (e.g., "Find the latest news on AI regulations in the EU and summarize the key points"). Instead of answering immediately, Pathfinder breaks down the problem, searches the web, reads the results, reflects on whether it has enough information, and then formulates a comprehensive response.

### Tech Stack
- **AI Orchestration & Logic**: Python, LangGraph, LangChain
- **Backend**: FastAPI
- **Frontend**: React.js
- **LLM Provider**: Free tier APIs (e.g., Groq / Gemini)

---

## Core Theoretical Concepts (Interview Prep Guide)

If asked about this project in an interview, here are the key concepts you need to explain:

### 1. Autonomous AI Agent (like AutoGPT)
Unlike a standard chatbot (like ChatGPT) where the interaction is a simple query-response, an autonomous agent is given an overarching goal. The agent acts as its own "brain"—it plans its steps, decides which tools to use, executes those tools, and evaluates its progress until the goal is met.

### 2. LangGraph vs. Standard LangChain
* **LangChain Chains** are linear. You go from Step A -> Step B -> Step C.
* **LangGraph** introduces *cyclic graphs* (loops). Real-world agents need loops. If an agent searches the web and gets a broken link, it needs to loop back, realize the mistake, and search again. LangGraph models this as nodes (functions) and edges (conditional routing), allowing for complex self-reflection and retry logic.

### 3. Multi-Step Reasoning & Self-Reflection (ReAct)
Pathfinder uses the **ReAct** (Reasoning and Acting) paradigm. The agent doesn't just act blindly; it:
1. **Reasons**: "I need to find out about X. I should use the web search tool."
2. **Acts**: Calls the web search tool.
3. **Reflects**: Analyzes the search output. "Did I get the right info? Yes. Now I will summarize it."

### 4. Tool-Calling (Function Calling)
LLMs are essentially text-prediction engines. To interact with the real world, we give them "Tools" (Python functions). Tool-calling is the LLM's ability to output a structured JSON response specifying the tool name and arguments it wants to run. We parse that JSON, run the Python function (e.g., a web scraper), and feed the result back to the LLM.

### 5. State Management
When an agent runs across multiple loops, it needs to remember what happened previously. LangGraph manages a persistent `State` dictionary that gets passed from node to node. This maintains the context across long-running workflows so the agent never forgets its original goal or past steps.

### 6. FastAPI & React.js Integration
- **FastAPI** acts as the robust backend server that exposes endpoints to trigger agent runs and retrieve the current state.
- **React.js** provides a sleek UI to monitor the agent. Because agents can take a long time to think and act, the React frontend gives the user real-time visual feedback on what the agent is currently doing (e.g., "Searching Google...", "Reading article...").

---

## Implementation Plan & Development Roadmap

We will build Pathfinder incrementally to ensure a deep understanding of every component.

### Phase 1: Core LangGraph Agent (Python Backend)
- [ ] Initialize Python environment and install dependencies (`langgraph`, `langchain`, LLM SDK).
- [ ] Connect to a free LLM API (like Groq or Gemini).
- [ ] Create the basic LangGraph setup: Define the `State` schema and setup a simple agent node.

### Phase 2: Adding Tools & Self-Reflection
- [ ] Build the `Web Search` tool (using a free API like Tavily or DuckDuckGo).
- [ ] Bind the tool to the LLM so it knows it can search the web.
- [ ] Add conditional edges in LangGraph to create the "Self-Reflection" loop (route back to tool-calling if the goal isn't met).

### Phase 3: Advanced State Management & Checkpointing
- [ ] Add persistence (checkpointers) to LangGraph.
- [ ] Allow the agent to pause execution so a human can review its progress (Human-in-the-loop).

### Phase 4: The FastAPI Backend
- [ ] Wrap the LangGraph agent inside a FastAPI application.
- [ ] Create endpoints for starting research tasks (`POST /research`).
- [ ] Create endpoints for streaming the agent's thought process back to the client.

### Phase 5: The React.js Frontend
- [ ] Bootstrap a React app (Vite + TailwindCSS/Vanilla CSS).
- [ ] Build a modern chat/monitoring interface.
- [ ] Connect the frontend to the FastAPI backend to visualize Pathfinder's reasoning steps in real-time.

---
