import asyncio
import os
import json
import redis.asyncio as redis
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL", "redis://platform-redis:6379")

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def main():
    redis_client = redis.from_url(REDIS_URL)
    print("Worker service started. Waiting for jobs...")
    
    while True:
        try:
            # BLPOP blocks until an item is available
            result = await redis_client.blpop("deployments", timeout=0)
            if not result:
                continue
                
            _, payload_str = result
            job = json.loads(payload_str)
            
            deployment_id = job["deployment_id"]
            print(f"Worker picked up deployment {deployment_id}")
            
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    # Update deployment
                    query = text("""
                        UPDATE deployments 
                        SET status = :status, started_at = :started_at, logs = :logs 
                        WHERE id = :id
                    """)
                    await session.execute(query, {
                        "status": "CLONING",
                        "started_at": datetime.utcnow(),
                        "logs": "Worker picked up deployment\n",
                        "id": deployment_id
                    })
        except Exception as e:
            print(f"Error processing job: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
