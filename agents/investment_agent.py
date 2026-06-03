from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, SystemMessage
from typing import TypedDict, Annotated, Sequence
import operator
from agents.llm_client import get_llm
from tools.market_tool import get_stock_info, get_technical_analysis
from tools.news_tools import get_financial_news, get_market_sentiment_summary
from tools.vector_tools import search_financial_knowledge

# ── State ───────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[Sequence, operator.add]
    user_context: dict   # portfolio, watchlist injected here

# ── Tools this agent can use ────────────────────────────
TOOLS = [
    get_stock_info,
    get_technical_analysis,
    get_financial_news,
    get_market_sentiment_summary,
    search_financial_knowledge,
]

SYSTEM_PROMPT = """You are an expert Investment Intelligence Analyst specializing in Indian and global markets.

Your expertise includes:
- Fundamental analysis (P/E, P/B, dividend yield, market cap)
- Long-term portfolio construction
- Mutual fund and ETF analysis
- Risk assessment

When analyzing stocks, always:
1. Fetch current fundamental data using get_stock_info
2. Check market sentiment using get_market_sentiment_summary
3. Search for recent analyst opinions using search_financial_knowledge
4. Provide structured recommendations with clear reasoning

Format your final response with:
- Summary recommendation (BUY/HOLD/SELL)
- Key metrics with values
- Risk factors
- Time horizon suggestion

User's current portfolio context: {user_context}

Always ground your analysis in real data. Never fabricate numbers."""

def create_investment_agent():
    llm = get_llm(temperature=0.2)
    llm_with_tools = llm.bind_tools(TOOLS)
    tool_node = ToolNode(TOOLS)

    def agent_node(state: AgentState):
        messages = state["messages"]
        user_context = state.get("user_context", {})

        # Inject system prompt with user context
        system = SystemMessage(content=SYSTEM_PROMPT.format(
            user_context=str(user_context)
        ))
        response = llm_with_tools.invoke([system] + list(messages))
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    # Build graph
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")  # loop back after tool use

    return workflow.compile()