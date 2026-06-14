import os
from fastapi import FastAPI
from dotenv import load_dotenv
import redis.asyncio as redis
from sqlalchemy import text
from database import engine

load_dotenv()

app = FastAPI(title="GitOps CD Platform")

@app.get("/health")
async def health_check():
    health_status = {
        "status": "healthy",
        "database": "disconnected",
        "redis": "disconnected"
    }

    # Check Database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health_status["database"] = "connected"
    except Exception as e:
        print(f"Database health check failed: {e}")
        health_status["status"] = "unhealthy"

    # Check Redis
    redis_url = os.getenv("REDIS_URL", "redis://platform-redis:6379")
    try:
        redis_client = redis.from_url(redis_url)
        await redis_client.ping()
        health_status["redis"] = "connected"
        await redis_client.aclose()
    except Exception as e:
        print(f"Redis health check failed: {e}")
        health_status["status"] = "unhealthy"

    return health_status
