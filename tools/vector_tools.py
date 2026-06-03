from langchain_core.tools import tool
from memory.chroma_client import get_collection
from memory.embeddings import get_embedder

@tool
def search_financial_knowledge(query: str, n_results: int = 5) -> list[dict]:
    """
    Semantic search over stored financial news and research documents.
    Use this when the user asks about recent events, trends, or analyst opinions.
    """
    embedder = get_embedder()
    collection = get_collection("financial_news")

    query_embedding = embedder.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    return [
        {
            "content": doc,
            "source": meta.get("source", "unknown"),
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "relevance": round(1 - dist, 3),
        }
        for doc, meta, dist in zip(docs, metas, distances)
    ]