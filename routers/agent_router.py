"""
Agents Router — POST /api/agents/chat
Streams LangGraph agent responses as Server-Sent Events (SSE).
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import json
import uuid

from database import get_db, AsyncSessionLocal
from core.auth import get_current_user
from models.users import User
from models.conversation import Conversation, Message, AgentType
from models.portfolio import Holding, Portfolio
from agents.orchisteration import run_agent

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    agent_type: str
    conversation_id: str | None = None


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate agent type
    try:
        agent_type_enum = AgentType(request.agent_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid agent_type: {request.agent_type}")

    # Get or create conversation
    conversation = None
    if request.conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == request.conversation_id,
                Conversation.user_id == current_user.id,
            )
        )
        conversation = result.scalar_one_or_none()

    if not conversation:
        conversation = Conversation(
            user_id=current_user.id,
            agent_type=agent_type_enum,
            title=request.message[:60],
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

    # Fetch conversation history (last 10 turns)
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in history_result.scalars().all()
    ]

    # Save user message now
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
    )
    db.add(user_msg)
    await db.commit()

    # Build user context injected into agent state
    user_context: dict = {"user_name": current_user.name}

    if request.agent_type in ("investment", "trading"):
        port_result = await db.execute(
            select(Portfolio).where(Portfolio.user_id == current_user.id)
        )
        portfolio = port_result.scalar_one_or_none()
        if portfolio:
            holdings_result = await db.execute(
                select(Holding).where(Holding.portfolio_id == portfolio.id)
            )
            user_context["holdings"] = [
                {"symbol": h.symbol, "qty": h.quantity, "buy_price": h.buy_price}
                for h in holdings_result.scalars().all()
            ]

    conv_id = str(conversation.id)

    async def stream_response():
        full_response = ""

        # Send conversation ID as first event
        yield f"data: {json.dumps({'type': 'conversation_id', 'id': conv_id})}\n\n"

        try:
            async for event in run_agent(
                agent_type=request.agent_type,
                message=request.message,
                conversation_history=history,
                user_context=user_context,
            ):
                kind = event.get("event")

                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        full_response += chunk.content
                        yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name})}\n\n"

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    tool_output = event.get("data", {}).get("output")
                    if tool_name in ("get_candlestick_data",):
                        yield f"data: {json.dumps({'type': 'chart_data', 'tool': tool_name, 'data': tool_output})}\n\n"
                    elif tool_name in ("get_technical_analysis",):
                        yield f"data: {json.dumps({'type': 'technical_data', 'tool': tool_name, 'data': tool_output})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            full_response = f"Error: {str(e)}"

        # Persist AI response
        async with AsyncSessionLocal() as save_db:
            ai_msg = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=full_response,
            )
            save_db.add(ai_msg)
            await save_db.commit()

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
async def get_conversations(
    agent_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's conversation history."""
    query = select(Conversation).where(Conversation.user_id == current_user.id)
    if agent_type:
        try:
            query = query.where(Conversation.agent_type == AgentType(agent_type))
        except ValueError:
            pass
    query = query.order_by(Conversation.created_at.desc()).limit(20)
    result = await db.execute(query)
    convs = result.scalars().all()
    return [
        {"id": str(c.id), "title": c.title, "agent_type": c.agent_type, "created_at": str(c.created_at)}
        for c in convs
    ]


# from fastapi import APIRouter, Depends, HTTPException
# from fastapi.responses import StreamingResponse
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select
# from pydantic import BaseModel
# import json
# import uuid
# from database import get_db,  AsyncSessionLocal
# from core.auth import get_current_user
# from models.users import User
# from models.conversation import Conversation, Message, AgentType
# from models.portfolio import Holding, Portfolio
# from agents.orchisteration import run_agent

# router = APIRouter()

# class ChatRequest(BaseModel):
#     message: str
#     agent_type: str          # "investment" | "trading" | "forex" | "news" | "education"
#     conversation_id: str | None = None

# @router.post("/chat")
# async def chat(
#     request: ChatRequest,
#     current_user: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     # Validate agent type
#     try:
#         agent_type_enum = AgentType(request.agent_type)
#     except ValueError:
#         raise HTTPException(status_code=400, detail=f"Invalid agent_type: {request.agent_type}")

#     # Get or create conversation
#     conversation = None
#     if request.conversation_id:
#         result = await db.execute(
#             select(Conversation).where(
#                 Conversation.id == request.conversation_id,
#                 Conversation.user_id == current_user.id
#             )
#         )
#         conversation = result.scalar_one_or_none()

#     if not conversation:
#         conversation = Conversation(
#             user_id=current_user.id,
#             agent_type=agent_type_enum,
#             title=request.message[:60],
#         )
#         db.add(conversation)
#         await db.commit()
#         await db.refresh(conversation)

#     # Fetch conversation history
#     history_result = await db.execute(
#         select(Message).where(Message.conversation_id == conversation.id)
#         .order_by(Message.created_at)
#     )
#     history = [
#         {"role": m.role, "content": m.content}
#         for m in history_result.scalars().all()
#     ]

#     # Save user message
#     user_msg = Message(
#         conversation_id=conversation.id,
#         role="user",
#         content=request.message,
#     )
#     db.add(user_msg)
#     await db.commit()

#     # Build user context (portfolio for investment agent)
#     user_context = {}
#     if request.agent_type == "investment":
#         portfolio_result = await db.execute(
#             select(Portfolio).where(Portfolio.user_id == current_user.id)
#         )
#         portfolio = portfolio_result.scalar_one_or_none()
#         if portfolio:
#             holdings_result = await db.execute(
#                 select(Holding).where(Holding.portfolio_id == portfolio.id)
#             )
#             holdings = holdings_result.scalars().all()
#             user_context["holdings"] = [
#                 {"symbol": h.symbol, "qty": h.quantity, "buy_price": h.buy_price}
#                 for h in holdings
#             ]

#     async def stream_response():
#         full_response = ""
#         conv_id = str(conversation.id)

#         # Send conversation ID first so frontend can track it
#         yield f"data: {json.dumps({'type': 'conversation_id', 'id': conv_id})}\n\n"

#         async for event in run_agent(
#             agent_type=request.agent_type,
#             message=request.message,
#             conversation_history=history,
#             user_context=user_context,
#         ):
#             kind = event.get("event")

#             # Stream LLM tokens
#             if kind == "on_chat_model_stream":
#                 chunk = event.get("data", {}).get("chunk")
#                 if chunk and hasattr(chunk, "content") and chunk.content:
#                     full_response += chunk.content
#                     yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"

#             # Notify frontend which tool is being called (the "thinking" UI)
#             elif kind == "on_tool_start":
#                 tool_name = event.get("name", "")
#                 yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name})}\n\n"

#             # Tool result (optional: send structured data for chart rendering)
#             elif kind == "on_tool_end":
#                 tool_output = event.get("data", {}).get("output")
#                 tool_name = event.get("name", "")
#                 if tool_name in ("get_candlestick_data", "get_technical_analysis"):
#                     yield f"data: {json.dumps({'type': 'chart_data', 'tool': tool_name, 'data': tool_output})}\n\n"

#         # Save complete assistant response to DB
#         # (done in background to not block streaming)
#         async with AsyncSessionLocal() as save_db:
#             ai_msg = Message(
#                 conversation_id=conversation.id,
#                 role="assistant",
#                 content=full_response,
#             )
#             save_db.add(ai_msg)
#             await save_db.commit()

#         yield f"data: {json.dumps({'type': 'done'})}\n\n"

#     return StreamingResponse(
#         stream_response(),
#         media_type="text/event-stream",
#         headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
#     )



# @router.get("/conversations")
# async def get_conversations(
#     agent_type: str | None = None,
#     current_user: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     """Get user's conversation history."""
#     query = select(Conversation).where(Conversation.user_id == current_user.id)
#     if agent_type:
#         try:
#             query = query.where(Conversation.agent_type == AgentType(agent_type))
#         except ValueError:
#             pass
#     query = query.order_by(Conversation.created_at.desc()).limit(20)
#     result = await db.execute(query)
#     convs = result.scalars().all()
#     return [
#         {"id": str(c.id), "title": c.title, "agent_type": c.agent_type, "created_at": str(c.created_at)}
#         for c in convs
#     ]
 