from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    database_url: str
    redis_url: str

    # Auth
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # AI
    openai_api_key: str = ""
    groq_api_key: str = ""

    # External APIs
    news_api_key: str = ""
    finnhub_api_key: str = ""
    youtube_api_key: str = ""

    # LLM selection: "openai" or "groq"
    llm_provider: str = "groq"
    llm_model: str = "llama3-70b-8192"  # Groq default

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()