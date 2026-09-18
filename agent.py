import os
from typing import TypedDict, Annotated
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# Load environment variables from .env file
load_dotenv()

# ==========================================
# PHASE 2: TOOLS & SELF-REFLECTION
# ==========================================

# 1. Define the Search Tool
# The @tool decorator converts a standard Python function into a tool 
# that LangChain and the LLM can understand. The docstring acts as the 
# tool description that teaches the LLM when to use this tool.
@tool
def web_search(query: str) -> str:
    """Searches the web using DuckDuckGo to get real-time information and answer questions."""
    search = DuckDuckGoSearchRun()
    return search.run(query)

# Collect all tools in a list
tools = [web_search]

# 2. Define the State
# The state is what gets passed around the graph from node to node.
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

# 3. Define the Node (The "Brain")
def chatbot_node(state: AgentState):
    # Initialize the LLM (using Groq via LangChain) with temperature=0 for deterministic tool-calling.
    # We use llama-3.1-8b-instant because it has robust, stable native tool-calling support on Groq.
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
    
    # "Bind" the tools to the model. This tells the LLM that these tools exist 
    # and describes their arguments.
    llm_with_tools = llm.bind_tools(tools)
    
    # Prepend a guiding SystemMessage to define Pathfinder's persona and objective
    from langchain_core.messages import SystemMessage
    system_prompt = SystemMessage(
        content="You are Pathfinder, an autonomous web research assistant. "
                "Use the web_search tool to find real-time information and answer the user's questions."
    )
    
    # Combine the system prompt with the conversation history
    messages = [system_prompt] + state["messages"]
    
    # Call the LLM (which can now decide to call tools)
    response = llm_with_tools.invoke(messages)
    
    # Return the new message to be appended to the state
    return {"messages": [response]}

# 4. Build the Graph
workflow = StateGraph(AgentState)

# Add our active nodes: chatbot and tools
workflow.add_node("chatbot", chatbot_node)
workflow.add_node("tools", ToolNode(tools))

# Define the routing
workflow.add_edge(START, "chatbot")

# Add a conditional edge from chatbot.
# LangGraph's tools_condition checks if the chatbot returned any tool_calls.
# - If yes: routes to "tools"
# - If no: routes to END
workflow.add_conditional_edges(
    "chatbot",
    tools_condition,
)

# After tools node executes, route back to chatbot to evaluate the results (reflection loop)
workflow.add_edge("tools", "chatbot")

# Compile the graph into an executable application
app = workflow.compile()

# 5. Run the Agent (For Testing)
if __name__ == "__main__":
    print("Pathfinder Initialized with Web Search! (Type 'exit' to quit)")
    
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            break
            
        initial_state = {"messages": [("user", user_input)]}
        
        # Stream the execution of nodes in the graph
        for event in app.stream(initial_state):
            for node_name, node_state in event.items():
                latest_message = node_state['messages'][-1]
                
                # Check if it is the chatbot node responding
                if node_name == "chatbot":
                    # If chatbot decided to call tools, show the tool call details
                    if latest_message.tool_calls:
                        for tool_call in latest_message.tool_calls:
                            print(f"\nPathfinder (Reasoning): I need to search the web for '{tool_call['args'].get('query')}'")
                    # If it's a normal message, print it
                    elif latest_message.content:
                        print(f"\nPathfinder ({node_name}): {latest_message.content}")
                
                # Check if it is the tools node executing
                elif node_name == "tools":
                    print(f"\nPathfinder (Action): Executed Web Search!")
                    print(f"Results: {latest_message.content}")

