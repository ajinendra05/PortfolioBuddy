import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from langchain_core.tools import tool
# from backend.config import settings
# from backend.services.cache_service import get_cached, set_cached

analyzer = SentimentIntensityAnalyzer()

@tool
def get_financial_news(query: str, page_size: int = 10) -> list[dict]:
    """
    Fetch financial news articles for a query (company name, topic, etc.)
    Returns title, description, url, source, sentiment_score.
    """
    cache_key = f"news:{query}:{page_size}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "apiKey": settings.news_api_key,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
    }
    response = requests.get(url, params=params, timeout=10)
    articles_raw = response.json().get("articles", [])

    articles = []
    for a in articles_raw:
        text = f"{a.get('title', '')} {a.get('description', '')}"
        sentiment = analyzer.polarity_scores(text)
        compound = sentiment["compound"]

        articles.append({
            "title": a.get("title"),
            "description": a.get("description"),
            "url": a.get("url"),
            "source": a.get("source", {}).get("name"),
            "published_at": a.get("publishedAt"),
            "sentiment_score": round(compound, 3),
            "sentiment_label": (
                "BULLISH" if compound > 0.05
                else "BEARISH" if compound < -0.05
                else "NEUTRAL"
            ),
        })

    set_cached(cache_key, articles, ttl=600)  # 10-min cache
    return articles


@tool
def get_market_sentiment_summary(symbol: str) -> dict:
    """
    Get aggregate sentiment for a stock/company from recent news.
    Returns overall sentiment score and breakdown.
    """
    # Get company name from yfinance for better news search
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    name = ticker.info.get("shortName", symbol.replace(".NS", ""))

    articles = get_financial_news.invoke({"query": name, "page_size": 20})

    if not articles:
        return {"symbol": symbol, "sentiment": "NEUTRAL", "score": 0, "articles_analyzed": 0}

    scores = [a["sentiment_score"] for a in articles]
    avg_score = sum(scores) / len(scores)
    bullish = sum(1 for s in scores if s > 0.05)
    bearish = sum(1 for s in scores if s < -0.05)
    neutral = len(scores) - bullish - bearish

    return {
        "symbol": symbol,
        "company": name,
        "sentiment": "BULLISH" if avg_score > 0.05 else "BEARISH" if avg_score < -0.05 else "NEUTRAL",
        "score": round(avg_score, 3),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "articles_analyzed": len(scores),
        "top_headlines": [a["title"] for a in articles[:3]],
    }