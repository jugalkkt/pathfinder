import json
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from agent import app

app_server = FastAPI(title="Pathfinder AI Backend")

# Enable CORS for frontend integration
app_server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app_server.get("/api/research")
async def research(query: str):
    async def event_generator():
        # Initialize state
        state = {"messages": [("user", query)], "loop_count": 0}
        
        try:
            # Stream the execution of nodes in the graph asynchronously
            async for event in app.astream(state):
                for node_name, node_state in event.items():
                    latest_message = node_state['messages'][-1]
                    loop_count = node_state.get('loop_count', 0)
                    
                    if node_name == "chatbot":
                        if latest_message.tool_calls:
                            # Search started
                            for tool_call in latest_message.tool_calls:
                                yield {
                                    "event": "message",
                                    "data": json.dumps({
                                        "type": "search_start",
                                        "query": tool_call['args'].get('query'),
                                        "loop_count": loop_count
                                    })
                                }
                        elif latest_message.content:
                            # Chatbot text response (final response or summarization)
                            yield {
                                "event": "message",
                                "data": json.dumps({
                                    "type": "chatbot_response",
                                    "content": latest_message.content,
                                    "loop_count": loop_count
                                })
                            }
                    elif node_name == "tools":
                        # Search tool completed, return result
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "search_result",
                                "content": latest_message.content,
                                "loop_count": loop_count
                            })
                        }
            # Notify frontend that research loop is done
            yield {
                "event": "message",
                "data": json.dumps({"type": "done"})
            }
        except Exception as e:
            yield {
                "event": "message",
                "data": json.dumps({"type": "error", "message": str(e)})
            }
            
    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app_server", host="127.0.0.1", port=8000, reload=True)
