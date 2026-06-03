from sentence_transformers import SentenceTransformer
from functools import lru_cache

@lru_cache(maxsize=1)
def get_embedder():
    # All-MiniLM runs locally, no API cost, good enough for news similarity
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_and_store_articles(articles: list[dict]):
    """
    Called by background job or news router to embed + store articles.
    """
    from memory.chroma_client import get_collection
    collection = get_collection("financial_news")
    embedder = get_embedder()

    docs, embeddings, metadatas, ids = [], [], [], []

    for i, article in enumerate(articles):
        text = f"{article.get('title', '')} {article.get('description', '')}"
        if not text.strip():
            continue

        emb = embedder.encode(text).tolist()
        docs.append(text)
        embeddings.append(emb)
        metadatas.append({
            "title": article.get("title", ""),
            "source": article.get("source", ""),
            "date": article.get("published_at", ""),
            "url": article.get("url", ""),
            "sentiment": article.get("sentiment_label", "NEUTRAL"),
        })
        ids.append(f"article_{hash(text)}")

    if docs:
        collection.upsert(documents=docs, embeddings=embeddings, metadatas=metadatas, ids=ids)