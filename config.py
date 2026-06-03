from pydantic_settings import BaseSettings
from functools import lru_cache
from dotenv import load_dotenv
import os

load_dotenv()  

class Settings(BaseSettings):
    # Database
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://PortfolioBuddy:Portfoliobuddy-2026@localhost:5432/PortfolioBuddy_DB")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Auth
    secret_key: str = os.getenv("SECRET_KEY", "change-me")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # AI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    # groq_api_key: str = ""

    # External APIs
    news_api_key: str = os.getenv("NEWS_API_KEY", "")
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")
    # youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")

    # LLM selection: "openai" or "groq"
    llm_provider: str = "openai"
    llm_model: str = "llama3-70b-8192"  # Groq default

    # class Config:
    #     env_file = ".env"

@lru_cache()
def get_settings():
    load_dotenv()  
    return Settings()

settings = get_settings()