import os
from typing import TypedDict, Annotated
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

# Load environment variables from .env file
load_dotenv()

# ==========================================
# PHASE 1: CORE LANGGRAPH AGENT
# ==========================================

# 1. Define the State
# The state is what gets passed around the graph from node to node.
# We use `add_messages` so that instead of overwriting the messages, 
# new messages are appended to the list, creating a conversation history.
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

# 2. Define the Node (The "Brain")
# A node is just a Python function that receives the current state and returns an updated state.
def chatbot_node(state: AgentState):
    # Initialize the LLM (using Groq via LangChain)
    # Make sure you have GROQ_API_KEY set in your .env file
    llm = ChatGroq(model="llama-3.3-70b-versatile")
    
    # Get the latest messages from the state
    messages = state["messages"]
    
    # Call the LLM
    response = llm.invoke(messages)
    
    # Return the new message to be appended to the state
    return {"messages": [response]}

# 3. Build the Graph
# StateGraph is the blueprint of our agent's workflow
workflow = StateGraph(AgentState)

# Add our single node to the graph
workflow.add_node("chatbot", chatbot_node)

# Add edges to define the flow
# In this simple Phase 1 graph, it just goes START -> chatbot -> END
workflow.add_edge(START, "chatbot")
workflow.add_edge("chatbot", END)

# Compile the graph into an executable application
app = workflow.compile()

# 4. Run the Agent (For Testing)
if __name__ == "__main__":
    print("Pathfinder Initialized! (Type 'exit' to quit)")
    
    # This is a simple interactive loop to test our basic agent
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            break
            
        # Invoke the graph with the initial state
        initial_state = {"messages": [("user", user_input)]}
        
        # We stream the output to see the results dynamically
        for event in app.stream(initial_state):
            # event is a dictionary with the node name as the key
            for node_name, node_state in event.items():
                # Get the latest message added to the state
                latest_message = node_state['messages'][-1].content
                print(f"\nPathfinder ({node_name}): {latest_message}")
