from langchain_openai import ChatOpenAI
# from langchain_groq import ChatGroq
from config import settings

def get_llm(temperature: float = 0.3, streaming: bool = True):
    """
    Returns configured LLM. Prefers Groq (free) over OpenAI.
    Swap llm_provider in .env to switch instantly.
    """
    # if settings.llm_provider == "groq":
    #     return ChatGroq(
    #         api_key=settings.groq_api_key,
    #         model=settings.llm_model,      # "llama3-70b-8192"
    #         temperature=temperature,
    #         streaming=streaming,
    #     )
    # else:
        # return ChatOpenAI(
        #     api_key=settings.openai_api_key,
        #     model="gpt-4o-mini",           # cheapest OpenAI option
        #     temperature=temperature,
        #     streaming=streaming,
        # )
    return ChatOpenAI(
            api_key=settings.openai_api_key,
            model="gpt-4o-mini",           # cheapest OpenAI option
            temperature=temperature,
            streaming=streaming,
        )