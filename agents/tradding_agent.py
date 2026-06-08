"""
Trading Agent — LangGraph ReAct agent
Handles: technical analysis, candlestick patterns, options insight, swing/intraday setups
"""

import operator
from typing import TypedDict, Annotated, Sequence

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage

from agents.llm_client import get_llm
from tools.market_tool import (
    get_stock_info,
    get_technical_analysis,
    get_candlestick_data,
)
from tools.news_tools import get_financial_news, get_market_sentiment_summary
from tools.vector_tools import search_financial_knowledge


# ── State ─────────────────────────────────────────────────
class AgentState(TypedDict):
    messages:     Annotated[Sequence, operator.add]
    user_context: dict


# ── Tools ─────────────────────────────────────────────────
TOOLS = [
    get_stock_info,
    get_technical_analysis,
    get_candlestick_data,
    get_financial_news,
    get_market_sentiment_summary,
    search_financial_knowledge,
]

SYSTEM_PROMPT = """You are an expert F&O and Stock Trading Analyst for Indian markets (NSE/BSE).

Your expertise:
- Technical analysis: RSI, MACD, EMA, Bollinger Bands, volume
- Candlestick pattern recognition: Doji, Hammer, Engulfing, Morning/Evening Star
- Options chain reading: PCR, Max Pain, OI analysis
- Intraday and swing trade setups with entry, target, stop-loss
- Nifty 50, Bank Nifty, Midcap index analysis

How to analyze a stock:
1. Call get_technical_analysis to get RSI, MACD, EMAs, Bollinger
2. Call get_candlestick_data for pattern recognition  
3. Call get_market_sentiment_summary for news bias
4. Synthesize into a clear trade setup

Always provide:
- Current Signal (STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL)
- Entry zone (price range to enter)
- Target 1 and Target 2
- Stop Loss
- Time horizon (intraday / swing 3-5 days / positional 2-4 weeks)
- Risk:Reward ratio

Use NSE format: append .NS for yfinance (RELIANCE.NS, HDFCBANK.NS, NIFTY_50.NS)

User portfolio context: {user_context}

Be specific with numbers. Never give vague advice."""


def create_trading_agent():
    llm = get_llm(temperature=0.2)
    llm_with_tools = llm.bind_tools(TOOLS)
    tool_node = ToolNode(TOOLS)

    def agent_node(state: AgentState):
        system = SystemMessage(
            content=SYSTEM_PROMPT.format(user_context=str(state.get("user_context", {})))
        )
        response = llm_with_tools.invoke([system] + list(state["messages"]))
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()