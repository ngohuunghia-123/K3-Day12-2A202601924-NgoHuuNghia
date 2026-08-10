"""Agent service — điểm ráp nối của cả lab (CP1, CP3, CP4).

Luồng một request tới /ask:

    client ──► verify_api_key ──► rate_limiter ──► cost_guard
                                                       │
                              store.get_history ◄──────┘
                                       │
                                    ask_llm
                                       │
                              store.append × 2 ──► cost_guard.record ──► log_event
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils.mock_llm import ask_llm

from .auth import verify_api_key
from .config import get_settings
from .cost_guard import CostGuard
from .lifecycle import lifecycle
from .logging_utils import log_event
from .rate_limiter import RateLimiter
from .store import ConversationStore, get_redis_client

SERVICE_NAME = "day12-agent"
SERVICE_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────
# Providers — CHO SẴN
# Tách ra thành hàm để test có thể thay bằng Redis giả qua
# app.dependency_overrides, và để kết nối Redis chỉ tạo khi thật sự cần.
# ─────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_store() -> ConversationStore:
    return ConversationStore(get_redis_client())


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    return RateLimiter(get_redis_client(), get_settings().rate_limit_per_minute)


@lru_cache(maxsize=1)
def get_cost_guard() -> CostGuard:
    return CostGuard(get_redis_client(), get_settings().monthly_budget_usd)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """CHO SẴN — chạy lúc app khởi động và lúc tắt."""
    lifecycle.install()
    log_event("service_started", service=SERVICE_NAME, version=SERVICE_VERSION)
    yield
    log_event("service_stopped", service=SERVICE_NAME)


app = FastAPI(title="Day 12 Production Agent", version=SERVICE_VERSION, lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


# ─────────────────────────────────────────────────────────────
# Health & readiness
# ─────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    import os
    env_keys = list(os.environ.keys())
    error_msg = None
    redis_client_status = "untested"
    redis_client_error = None
    try:
        settings = get_settings()
        config_status = "ok"
        try:
            client = get_redis_client()
            redis_client_status = "ok"
        except Exception as e_redis:
            redis_client_status = "error"
            redis_client_error = str(e_redis)
    except Exception as e:
        config_status = "error"
        error_msg = str(e)
    
    if lifecycle.shutting_down:
        return JSONResponse(status_code=503, content={"status": "shutting_down"})
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "config_status": config_status,
        "error_msg": error_msg,
        "redis_client_status": redis_client_status,
        "redis_client_error": redis_client_error,
        "env_keys": [k for k in env_keys if k.upper() in ["PORT", "AGENT_API_KEY", "REDIS_URL", "RATE_LIMIT_PER_MINUTE", "MONTHLY_BUDGET_USD", "LOG_LEVEL"]]
    }


@app.get("/ready")
def ready(store: ConversationStore = Depends(get_store)):
    """Readiness probe — đã sẵn sàng nhận traffic chưa?

    Khác /health: endpoint này ĐƯỢC PHÉP kiểm tra dependency.
    Load balancer dùng nó để quyết định có đẩy request vào instance này không.
    """
    if lifecycle.shutting_down:
        return JSONResponse(status_code=503, content={"status": "shutting_down"})
    redis_ok = store.ping()
    if not redis_ok:
        return JSONResponse(status_code=503, content={"status": "not ready", "redis": False})
    return {"status": "ready", "redis": True}


# ─────────────────────────────────────────────────────────────
# Endpoint chính
# ─────────────────────────────────────────────────────────────
@app.post("/ask")
def ask(
    payload: AskRequest,
    user_id: str = Depends(verify_api_key),
    store: ConversationStore = Depends(get_store),
    limiter: RateLimiter = Depends(get_rate_limiter),
    guard: CostGuard = Depends(get_cost_guard),
):
    """Hỏi agent một câu.

    Thứ tự: check trước rồi mới gọi LLM — vì tiền mất ở bước gọi LLM.
    Chặn sau khi đã gọi thì bạn vừa trả tiền vừa trả lỗi.
    """
    # 1. Kiểm tra rate limit
    limiter.check(user_id)
    # 2. Kiểm tra ngân sách
    guard.check(user_id)
    # 3. Đọc lịch sử hội thoại
    history = store.get_history(user_id)
    # 4. Gọi LLM (mock trong test)
    result = ask_llm(payload.question, history)
    # 5. Ghi vào lịch sử
    store.append(user_id, "user", payload.question)
    store.append(user_id, "assistant", result["answer"])
    # 6. Ghi nhọn chi phí
    guard.record(user_id, result["cost_usd"])
    # 7. Structured log
    log_event(
        "ask_completed",
        user_id=user_id,
        tokens_in=result["tokens_in"],
        tokens_out=result["tokens_out"],
        cost_usd=result["cost_usd"],
    )
    # 8. Trả response
    return {
        "answer": result["answer"],
        "user_id": user_id,
        "history_length": len(history),
        "cost_usd": result["cost_usd"],
        "tokens": {"in": result["tokens_in"], "out": result["tokens_out"]},
    }


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
