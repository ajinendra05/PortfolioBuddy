from agents.investment_agent import create_investment_agent
# from agents.trading_agent import create_trading_agent
# from agents.forex_agent import create_forex_agent
# from agents.news_agent import create_news_agent
# from agents.education_agent import create_education_agent
from langchain_core.messages import HumanMessage

# Compile agents once at startup
_agents = {
    "investment": create_investment_agent(),
    # "trading": create_trading_agent(),
    # "forex": create_forex_agent(),
    # "news": create_news_agent(),
    # "education": create_education_agent(),
}

async def run_agent(
    agent_type: str,
    message: str,
    conversation_history: list[dict],
    user_context: dict,
):
    """
    Run the appropriate agent and stream results.
    conversation_history: list of {"role": "user"|"assistant", "content": "..."}
    """
    agent = _agents.get(agent_type)
    if not agent:
        raise ValueError(f"Unknown agent type: {agent_type}")

    # Build message list from history
    from langchain_core.messages import HumanMessage, AIMessage
    messages = []
    for msg in conversation_history[-10:]:  # last 10 messages for context window
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=message))

    state = {
        "messages": messages,
        "user_context": user_context,
    }

    # Stream events from LangGraph
    async for event in agent.astream_events(state, version="v2"):
        yield event