import asyncio
import os
import json
import shutil
import subprocess
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

def run_cmd(cmd: list[str], cwd: str = None):
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return result.stdout, result.stderr, result.returncode
    except Exception as e:
        return "", str(e), 1

async def append_deployment_log(deployment_id: int, log_entry: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            query = text("""
                UPDATE deployments 
                SET logs = COALESCE(logs, '') || :new_log 
                WHERE id = :id
            """)
            await session.execute(query, {"new_log": log_entry, "id": deployment_id})

async def update_deployment_status(deployment_id: int, status: str, error: str = None, image_name: str = None, container_name: str = None, deployment_url: str = None, completed_at: datetime = None):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            set_clauses = ["status = :status"]
            params = {"status": status, "id": deployment_id}
            
            if error is not None:
                set_clauses.append("error = :error")
                params["error"] = error
            if image_name is not None:
                set_clauses.append("image_name = :image_name")
                params["image_name"] = image_name
            if container_name is not None:
                set_clauses.append("container_name = :container_name")
                params["container_name"] = container_name
            if deployment_url is not None:
                set_clauses.append("deployment_url = :deployment_url")
                params["deployment_url"] = deployment_url
            if completed_at is not None:
                set_clauses.append("completed_at = :completed_at")
                params["completed_at"] = completed_at
                
            query_str = "UPDATE deployments SET " + ", ".join(set_clauses) + " WHERE id = :id"
            await session.execute(text(query_str), params)

async def main():
    redis_client = redis.from_url(REDIS_URL)
    print("Worker service started. Waiting for jobs...")
    
    os.makedirs("/app/repos", exist_ok=True)
    
    while True:
        try:
            result = await redis_client.blpop("deployments", timeout=0)
            if not result:
                continue
                
            _, payload_str = result
            job = json.loads(payload_str)
            
            deployment_id = job["deployment_id"]
            repo_id = job["repo_id"]
            repo_url = job["repo_url"]
            commit_sha = job["commit_sha"]
            
            print(f"Worker picked up deployment {deployment_id}")
            
            # 2. Update status to CLONING
            async with AsyncSessionLocal() as session:
                async with session.begin():
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
                    
            # 3. Create clone directory
            clone_dir = f"/app/repos/platform-repo-{repo_id}"
            
            # 4. If directory exists, remove it first
            if os.path.exists(clone_dir):
                shutil.rmtree(clone_dir, ignore_errors=True)
                
            # 5. Execute git clone
            await append_deployment_log(deployment_id, f"Cloning repository {repo_url} into {clone_dir}...\n")
            stdout, stderr, code = run_cmd(["git", "clone", repo_url, clone_dir])
            
            if stdout:
                await append_deployment_log(deployment_id, stdout + "\n")
            if stderr:
                await append_deployment_log(deployment_id, stderr + "\n")
                
            if code != 0:
                await update_deployment_status(deployment_id, "FAILED", error="Git clone failed")
                await append_deployment_log(deployment_id, f"Clone failed with exit code {code}.\n")
                if os.path.exists(clone_dir):
                    shutil.rmtree(clone_dir, ignore_errors=True)
                continue
                
            await append_deployment_log(deployment_id, "Clone completed successfully.\n")
            
            # 6. Checkout exact commit SHA
            await append_deployment_log(deployment_id, f"Checking out commit {commit_sha}...\n")
            stdout, stderr, code = run_cmd(["git", "-C", clone_dir, "checkout", commit_sha])
            
            if stdout:
                await append_deployment_log(deployment_id, stdout + "\n")
            if stderr:
                await append_deployment_log(deployment_id, stderr + "\n")
                
            if code != 0:
                await update_deployment_status(deployment_id, "FAILED", error="Git checkout failed")
                await append_deployment_log(deployment_id, f"Checkout failed with exit code {code}.\n")
                if os.path.exists(clone_dir):
                    shutil.rmtree(clone_dir, ignore_errors=True)
                continue
                
            await append_deployment_log(deployment_id, "Checkout completed successfully.\n")
            
            # 7. Both operations succeed: status = BUILDING
            await update_deployment_status(deployment_id, "BUILDING")
            await append_deployment_log(deployment_id, "Status updated to BUILDING.\n")
            
            # --- STAGE 6 EXTENSION ---
            # 1. Verify Dockerfile exists
            dockerfile_path = os.path.join(clone_dir, "Dockerfile")
            if not os.path.exists(dockerfile_path):
                await update_deployment_status(deployment_id, "FAILED", error="Dockerfile not found")
                await append_deployment_log(deployment_id, "Dockerfile not found in the repository root.\n")
                shutil.rmtree(clone_dir, ignore_errors=True)
                continue
                
            # 2. Build image
            sha_short = commit_sha[:7]
            image_name = f"platform-image-{repo_id}-{sha_short}"
            await append_deployment_log(deployment_id, f"Building Docker image {image_name}...\n")
            
            stdout, stderr, code = run_cmd(["docker", "build", "-t", image_name, clone_dir])
            
            if stdout:
                await append_deployment_log(deployment_id, stdout + "\n")
            if stderr:
                await append_deployment_log(deployment_id, stderr + "\n")
                
            if code != 0:
                await update_deployment_status(deployment_id, "FAILED", error="Docker build failed")
                await append_deployment_log(deployment_id, f"Docker build failed with exit code {code}.\n")
                # Remove partially built image if it exists
                run_cmd(["docker", "rmi", "-f", image_name])
                shutil.rmtree(clone_dir, ignore_errors=True)
                continue
                
            await append_deployment_log(deployment_id, "Docker build completed successfully.\n")
            
            # 3. Build succeeds: status = DEPLOYING
            await update_deployment_status(deployment_id, "DEPLOYING", image_name=image_name)
            await append_deployment_log(deployment_id, "Status updated to DEPLOYING.\n")
            
            # --- STAGE 7 EXTENSION ---
            port = 5000 + deployment_id
            container_name = f"platform-app-{deployment_id}"
            
            await append_deployment_log(deployment_id, f"Running container {container_name} on port {port}...\n")
            stdout, stderr, code = run_cmd([
                "docker", "run", "-d",
                "--name", container_name,
                "-p", f"{port}:80",
                image_name
            ])
            
            if stdout:
                await append_deployment_log(deployment_id, stdout + "\n")
            if stderr:
                await append_deployment_log(deployment_id, stderr + "\n")
                
            if code != 0:
                await update_deployment_status(deployment_id, "FAILED", error="Docker run failed")
                await append_deployment_log(deployment_id, f"Docker run failed with exit code {code}.\n")
                run_cmd(["docker", "rm", "-f", container_name])
                continue
                
            await append_deployment_log(deployment_id, "Container started successfully.\n")
            
            await update_deployment_status(
                deployment_id, 
                "RUNNING", 
                container_name=container_name, 
                deployment_url=f"http://localhost:{port}",
                completed_at=datetime.utcnow()
            )
            await append_deployment_log(deployment_id, "Status updated to RUNNING.\n")
            
        except Exception as e:
            print(f"Error processing job: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
