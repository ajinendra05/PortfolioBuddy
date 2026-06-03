import chromadb
from chromadb.config import Settings

_client = None

def init_chroma():
    global _client
    _client = chromadb.PersistentClient(
        path="./chroma_data",
        settings=Settings(anonymized_telemetry=False)
    )
    # Ensure collection exists
    _client.get_or_create_collection("financial_news")
    print("ChromaDB initialized")

def get_collection(name: str):
    return _client.get_or_create_collection(name)

def get_client():
    return _client