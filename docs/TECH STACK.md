# Tech Stack Document

# GitHub Webhook Driven Continuous Deployment Platform — Phase 1

-----

## 1. Stack Overview

Layer: Frontend
Technology: React 18 + TypeScript
Purpose: User interface for repository management and deployment visibility

Layer: Frontend Styling
Technology: Tailwind CSS 3
Purpose: Utility-first styling, no custom CSS

Layer: Frontend HTTP
Technology: Axios
Purpose: API calls to backend

Layer: Backend
Technology: FastAPI (Python)
Purpose: REST API, webhook receiver, job dispatcher

Layer: Backend ORM
Technology: SQLAlchemy 2.x with asyncpg
Purpose: Async database access layer

Layer: Backend Validation
Technology: Pydantic v2
Purpose: Request and response schema validation

Layer: Database
Technology: Supabase (hosted PostgreSQL)
Purpose: Persistent storage for repositories and deployments

Layer: Queue
Technology: Redis 7
Purpose: Async job queue between backend and worker

Layer: Queue Client
Technology: redis-py
Purpose: Python Redis client used by both backend and worker

Layer: Worker
Technology: Python 3.11
Purpose: Deployment execution engine

Layer: System Calls
Technology: subprocess (Python stdlib)
Purpose: git and docker commands — no Docker SDK

Layer: Containerization
Technology: Docker (latest stable)
Purpose: Container runtime for platform services and deployed apps

Layer: Orchestration
Technology: Docker Compose v2
Purpose: Multi-service orchestration with single command startup

Layer: Reverse Proxy
Technology: NGINX (alpine)
Purpose: Path-based routing, single public entry point

Layer: Database Migrations
Technology: Alembic
Purpose: Schema migrations against Supabase PostgreSQL

Layer: Backend Server
Technology: Uvicorn
Purpose: ASGI server for FastAPI

Layer: Deployment Environment
Technology: AWS EC2 t2.micro
Purpose: Single Linux VM hosting the entire platform

-----

## 2. Frontend

### React 18 + TypeScript

Component-based UI with type safety.

useState and useEffect for state management and polling.

React Router v6 for client-side navigation between pages.

TypeScript prevents runtime type errors in API response handling.

### Tailwind CSS 3

Utility classes only. No custom CSS files.

Status badge colors:

- PENDING: yellow
- CLONING: blue
- BUILDING: blue
- DEPLOYING: blue
- RUNNING: green
- FAILED: red

### Axios

All API calls go through /api proxied by NGINX.

Used for all REST endpoints: repository registration, webhook config display, deployment status polling.

### Polling Strategy

```typescript
useEffect(() => {
  const interval = setInterval(async () => {
    const res = await axios.get(`/api/deployments/${id}`);
    setDeployment(res.data);
    if (["running", "failed"].includes(res.data.status)) {
      clearInterval(interval);
    }
  }, 3000);
  return () => clearInterval(interval);
}, [id]);
```

Polling stops immediately when a terminal state (RUNNING or FAILED) is reached.

### Frontend Dependencies

react: 18
react-dom: 18
react-router-dom: 6
axios: latest
tailwindcss: 3
typescript: 5

-----

## 3. Backend

### FastAPI

Async REST API server.

CORS enabled for local development.

Auto-generates OpenAPI documentation at /docs — useful for testing webhook endpoints manually.

### SQLAlchemy 2.x with asyncpg

Async ORM sessions prevent blocking the event loop during database operations.

Connection string identical in structure to local PostgreSQL — Supabase is a drop-in replacement.

### Pydantic v2

RepositoryCreate: validates name and github_url on registration
RepositoryResponse: serializes repository data, excludes webhook_secret from list responses
DeploymentResponse: serializes all deployment fields including logs and error
WebhookPayload: validates incoming GitHub webhook structure

### HMAC Validation

```python
import hmac
import hashlib

def validate_signature(payload_body: bytes, secret: str, signature_header: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

Raw request body must be read before Pydantic parses the JSON. FastAPI requires reading body as bytes first for signature validation.

### Backend Python Dependencies

fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
pydantic
pydantic-settings
redis
python-dotenv
alembic
httpx

-----

## 4. Worker

### Python 3.11 — Subprocess Approach

Worker uses subprocess only. No Docker SDK.

Why subprocess over Docker SDK:
Output capture is straightforward — stdout and stderr go directly into deployment logs.
No SDK abstraction hiding what commands actually run.
Easier to debug — every command is a readable list of strings.
More educational — you understand exactly what executes at each step.

### Subprocess Pattern

```python
import subprocess

def run_cmd(cmd: list[str], log_prefix: str = "") -> tuple[str, int]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    return output, result.returncode
```

### Redis Consumption Pattern

```python
# Blocking pop — zero CPU waste, no busy loop
_, raw = redis_client.blpop("deployments", timeout=0)
job = json.loads(raw)
```

timeout=0 means block indefinitely until a job is available. Worker uses no CPU while idle.

### Log Accumulation Pattern

Logs are appended to the deployment record throughout execution. Never overwritten.

```python
def append_log(deployment_id: int, new_log: str):
    # Fetch current logs
    # Append new content
    # Write back to database
```

### Worker Python Dependencies

redis
sqlalchemy[asyncio]
asyncpg
python-dotenv

-----

## 5. Database — Supabase (Hosted PostgreSQL)

### Why Supabase

Free hosted PostgreSQL — no local container needed.

Removes one service from docker-compose, reducing platform complexity.

Dashboard for visual inspection of deployment records during development and debugging.

SQLAlchemy connection string is identical to local PostgreSQL — Supabase is a transparent replacement.

### Setup

Step 1 — Create a free project at supabase.com
Step 2 — Go to Settings → Database → Connection String → URI
Step 3 — Copy connection string into .env as DATABASE_URL
Step 4 — Run: alembic upgrade head to create tables

### Connection String Format

postgresql+asyncpg://postgres:{password}@{project-ref}.supabase.co:5432/postgres

### Supabase Network Settings

During development: allow all IPs in Supabase Settings → Database → Network

On EC2: add EC2 public IP to allowlist only

-----

## 6. Queue — Redis 7

### Queue Design

Backend pushes job:

```python
redis_client.lpush("deployments", json.dumps({
    "deployment_id": 12,
    "repo_id": 3,
    "repo_url": "https://github.com/user/repo",
    "commit_sha": "a1b2c3d4e5f6..."
}))
```

Worker consumes job:

```python
_, raw = redis_client.blpop("deployments", timeout=0)
job = json.loads(raw)
```

### Why BLPOP

BLPOP blocks until a job is available. No polling loop. Zero CPU usage while idle. One worker handles one job at a time with no race conditions.

### Why Redis over RabbitMQ

Simpler setup. List-based queue is sufficient for this volume. BLPOP gives efficient blocking consume with no additional configuration overhead. RabbitMQ introduces AMQP protocol complexity that is not needed here.

-----

## 7. Docker Compose

### Services (5 platform services — no local postgres)

```yaml
services:
  nginx:      # platform-nginx — public entry point
  frontend:   # platform-frontend — React app
  backend:    # platform-backend — FastAPI
  worker:     # platform-worker — deployment engine
  redis:      # platform-redis — job queue

networks:
  platform-network:
    driver: bridge

volumes:
  nginx_conf:   # shared nginx conf.d between worker and nginx
  repos_data:   # shared clone directories
```

### Worker Volume Mounts

```yaml
worker:
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock  # Docker socket — required for subprocess docker commands
    - ./repos:/app/repos                          # Cloned repositories
    - ./nginx/conf.d:/app/nginx/conf.d            # Write per-repo NGINX configs
```

### NGINX Volume Mounts

```yaml
nginx:
  volumes:
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro  # Static base config — read only
    - ./nginx/conf.d:/etc/nginx/conf.d              # Dynamic per-repo configs from worker
```

-----

## 8. NGINX

### Why NGINX

Industry standard reverse proxy. Path-based routing is well-documented. Dynamic reload with nginx -s reload has zero downtime. Lightweight alpine image. Core DevOps skill that interviewers expect.

### Why NGINX over Traefik

NGINX configuration is a fundamental DevOps skill. Traefik auto-discovery hides how routing actually works. Writing NGINX configs manually is more educational and more explainable in interviews.

### Routing

/ routes to frontend container
/api/ routes to backend container
/repo-{repo_id}/ routes to deployed application container

### Dynamic Config Strategy

Base nginx.conf is static and never modified at runtime.

Worker writes one config file per repository to conf.d/ after each successful deployment.

Worker reloads NGINX after writing: docker exec platform-nginx nginx -s reload

NGINX picks up new config without restarting, with zero downtime.

### Container Port Convention

Phase 1 enforces a platform convention that all deployable repositories must expose port 80 and listen on port 80.

The platform does not perform:

- Port discovery
- Port detection
- Port configuration

Health checks always target:

<http://localhost:80>

NGINX always proxies to:

container_name:80

Repositories that do not expose and listen on port 80 are not considered deployable by the platform.

-----

## 9. Deployment URL Storage

The database stores only the route path for each deployed application:

```
/repo-{repo_id}/
```

The full URL is never stored in the database. The frontend constructs the full URL at display time using the current application origin.

Examples:

Local:
<http://localhost/repo-{id}/>

Production:
http://{EC2-IP}/repo-{id}/

This approach means the stored path is environment-agnostic and requires no updates when moving between local development and production.

-----

## 10. Environment Variables

### Backend and Worker .env

```env
DATABASE_URL=postgresql+asyncpg://postgres:{password}@{ref}.supabase.co:5432/postgres
REDIS_URL=redis://platform-redis:6379
REPOS_DIR=/app/repos
NGINX_CONF_DIR=/app/nginx/conf.d
NGINX_CONTAINER_NAME=platform-nginx
```

-----

## 11. Development vs Production

Concern: Start command
Local Dev: docker compose up
Production EC2: docker compose up -d

Concern: Deployed URL format
Local Dev: <http://localhost/repo-{id}/>
Production EC2: http://{EC2-IP}/repo-{id}/

Concern: Supabase allowlist
Local Dev: Allow all IPs
Production EC2: EC2 IP only

Concern: Webhook URL
Local Dev: Use ngrok or similar tunnel for local testing
Production EC2: http://{EC2-IP}/api/webhooks/github

Concern: HTTPS
Local Dev: No
Production EC2: Optional with Certbot — not Phase 1

-----

## 12. Why These Choices — Interview Answers

Why FastAPI over Flask?
Async-native, Pydantic validation built in, auto-generates OpenAPI docs. Modern Python API standard. Better suited for async database operations with SQLAlchemy.

Why Redis over a database queue?
Redis BLPOP provides true blocking with zero CPU usage while idle. A database queue requires polling on a timer, wasting CPU and connections. Redis is purpose-built for this use case.

Why Supabase over local PostgreSQL?
Removes one container from compose. Free managed hosting. Dashboard for visibility. SQLAlchemy usage is identical — Supabase is a transparent drop-in.

Why subprocess over Docker SDK?
Direct output capture for log accumulation. No abstraction hiding the real commands. Easier to debug. More educational — every operation is a readable command string.

Why path-based routing over subdomains?
Subdomains require DNS configuration and wildcard SSL certificates. Path routing works on any IP with zero DNS setup. Suitable for a single EC2 instance without a domain name.

Why NGINX over Traefik?
NGINX config is a core DevOps skill. Traefik auto-discovery hides how routing works. Writing and managing NGINX configs manually is more educational and explainable.

Why constant-time comparison for HMAC?
Standard string comparison leaks timing information. hmac.compare_digest always takes the same time regardless of where mismatch occurs, preventing timing-based secret reconstruction attacks.

Why deduplication via X-GitHub-Delivery?
GitHub occasionally delivers the same webhook twice under network instability. Without deduplication, two workers would race to deploy the same commit simultaneously. Storing the delivery ID and rejecting duplicates is the correct production pattern.

Why store only the route path for deployment URLs?
Storing the full URL would couple the database to the deployment environment. Storing only /repo-{id}/ keeps the record environment-agnostic. The frontend constructs the full URL from its own origin, which is always correct regardless of whether the platform is running locally or on EC2.

Why enforce port 80 as a platform convention?
Port discovery and detection add complexity with no benefit at this scale. A single enforced convention — all deployed apps expose and listen on port 80 — keeps NGINX config generation simple, health check logic trivial, and the deployment pipeline predictable.

-----

## 13. Phase 2 Additions (Future — Not Phase 1)

Kubernetes (minikube or k3s) to replace docker run in worker
kubectl apply to replace subprocess docker commands
Kubernetes Ingress Controller to replace NGINX dynamic config
GitHub Actions for automated testing before deployment
HTTPS with Certbot and Let’s Encrypt
Authentication for the dashboard
Private repository support via GitHub App or deploy keys