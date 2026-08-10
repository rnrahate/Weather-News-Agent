import os
import certifi
import requests
import streamlit as st
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage

# Handle different Tavily import patterns based on library version
try:
    from langchain_tavily import TavilySearch as TavilySearchResults
except ImportError:
    try:
        from langchain_tavily import TavilySearchResults
    except ImportError:
        from langchain_community.tools.tavily_search import TavilySearchResults

# Define Pydantic Schema for the Tool (satisfying the pydantic requirement)
class WeatherInput(BaseModel):
    city: str = Field(description="The city to get the weather for")

@tool("get_weather_data", args_schema=WeatherInput)
def get_weather_data(city: str) -> str:
    """Get the current weather for a city."""
    WEATHER_API = os.getenv("WEATHERSTACK_API_KEY")
    url = "https://api.weatherstack.com/current"
    params = {
        "access_key": WEATHER_API,
        "query": city
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            return f"Weather API error: {data['error'].get('info', 'Unknown error')}"
        if "current" not in data:
            return f"Could not fetch weather data for {city}"
        current = data["current"]
        return (
            f"Weather in {city}: "
            f"{current.get('temperature')}°C, "
            f"{current.get('weather_descriptions', ['Unknown'])[0]}, "
            f"humidity {current.get('humidity')}%, "
            f"wind speed {current.get('wind_speed')} km/h."
        )
    except Exception as e:
        return f"Error fetching weather: {str(e)}"

DEFAULT_SYSTEM_PROMPT = """
You are an intelligent AI agent that can reason about a user's request
and use available tools to accomplish the task.

Follow this general process:
1. Understand the user's request and determine what information or action is required.
2. Decide whether you can answer using your existing knowledge or whether you need to use one of the available tools.
3. If a tool is necessary:
   - Select the most appropriate tool.
   - Determine the correct arguments for the tool.
   - Call the tool.
   - Examine the returned result.
   - Use the result to continue solving the user's request.
4. If additional tool calls are necessary, repeat the process.
5. Once you have sufficient information, provide a clear and concise final answer to the user.

Important rules:
- Do not fabricate information.
- Do not claim that you used a tool if you did not.
- Use tools when they are necessary to obtain accurate or current information.
- Do not use a tool when it is unnecessary.
- Treat tool results as evidence and evaluate them before giving the final answer.
- If a tool fails or does not provide sufficient information, clearly state the limitation rather than inventing an answer.
- Keep the final answer focused on the user's request.

You are responsible for deciding when to use tools and when to provide the final answer.
"""

def init_agent(system_prompt):
    # Setup LLM
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        temperature=0.7,
        api_key=os.getenv("GEMINI_API_KEY")
    )
    
    search_tool = TavilySearchResults(
        max_results=5,
        topic="news",
        search_depth="advanced"
    )
    
    tools = [search_tool, get_weather_data]
    
    agent = create_react_agent(llm, tools, prompt=system_prompt)
    return agent

# --- Streamlit UI ---
def main():
    st.set_page_config(page_title="Agentic AI Chatbot", page_icon="🤖")
    st.title("Weather & News Agent")
    
    # Load Environment Variables
    os.environ["SSL_CERT_FILE"] = certifi.where()
    # Assuming .env is one level up based on notebook structure
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
        
    with st.sidebar:
        st.header("Agent Settings")
        
        if st.button("Clear Chat History", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
            
        st.subheader("System Prompt")
        custom_system_prompt = st.text_area(
            "Edit the AI's core instructions:", 
            value=DEFAULT_SYSTEM_PROMPT, 
            height=300
        )
        
        if len(st.session_state.messages) > 0:
            st.subheader("Edit Chat History")
            with st.expander("Expand to edit previous messages"):
                for i, msg in enumerate(st.session_state.messages):
                    new_content = st.text_area(f"{msg['role'].capitalize()} message {i+1}", value=msg["content"], key=f"edit_msg_{i}")
                    if new_content != msg["content"]:
                        st.session_state.messages[i]["content"] = new_content
                        st.success("Saved!")

        st.subheader("Input Mode")
        use_multiline_input = st.toggle("Use Multi-line Text Area Input", value=False)
        
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # Input Area Logic
    prompt = None
    if use_multiline_input:
        st.markdown("---")
        with st.form("chat_form", clear_on_submit=True):
            form_prompt = st.text_area("Your message (multi-line supported):", height=100)
            submitted = st.form_submit_button("Send")
            if submitted and form_prompt:
                prompt = form_prompt
    else:
        prompt = st.chat_input("Ask me something...")
            
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        agent = init_agent(custom_system_prompt)
        
        with st.chat_message("assistant"):
            st_callback = st.empty()
            
            inputs = {"messages": [HumanMessage(content=prompt)]}
            
            with st.spinner("Thinking..."):
                final_response = ""
                for step in agent.stream(inputs, stream_mode="updates"):
                    for node, data in step.items():
                        if node in ["model", "agent"]:
                            msg = data["messages"][-1]
                            if getattr(msg, 'tool_calls', None):
                                for call in msg.tool_calls:
                                    st.toast(f"🤖 Agent: Using {call['name']} tool...")
                            elif getattr(msg, 'content', None):
                                if isinstance(msg.content, list):
                                    # Extract text from the list of dicts returned by Gemini
                                    texts = [item['text'] for item in msg.content if isinstance(item, dict) and 'text' in item]
                                    final_response = "".join(texts)
                                else:
                                    final_response = str(msg.content)
                                st_callback.markdown(final_response)
                        elif node == "tools":
                            st.toast("🔧 Tool execution completed.")
                            
                st.session_state.messages.append({"role": "assistant", "content": final_response})
                st.rerun()

if __name__ == "__main__":
    main()
