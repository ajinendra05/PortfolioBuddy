from pydantic_settings import BaseSettings
from functools import lru_cache
from dotenv import load_dotenv
import os

load_dotenv()  

class Settings(BaseSettings):
    # Database
    database_url: str
    redis_url: str

    # Auth
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # AI
    openai_api_key: str = os.getenv("openai_api_key", "")
    # groq_api_key: str = ""

    # External APIs
    news_api_key: str = os.getenv("news_api_key", "")
    finnhub_api_key: str = os.getenv("finnhub_api_key", "")
    # youtube_api_key: str = os.getenv("youtube_api_key", "")

    # LLM selection: "openai" or "groq"
    llm_provider: str = "openai"
    llm_model: str = "llama3-70b-8192"  # Groq default

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    load_dotenv()  
    return Settings()

settings = get_settings()