from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import engine, Base
from routers.auth_router import router as auth_router
from routers.agent_router import router as agent_router
from memory.chroma_client import init_chroma

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables, init ChromaDB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    init_chroma()
    yield
    # Shutdown: cleanup
    await engine.dispose()

app = FastAPI(
    title="FinAI Platform",
    description="Multi-Agent Investment & Trading Assistant",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:3000", "https://your-vercel-app.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(agent_router, prefix="/api/agents", tags=["agents"])
# app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
# app.include_router(market.router, prefix="/api/market", tags=["market"])
# app.include_router(news.router, prefix="/api/news", tags=["news"])

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}