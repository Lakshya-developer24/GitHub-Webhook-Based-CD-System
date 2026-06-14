# System Architecture Document

# GitHub Webhook Driven Continuous Deployment Platform — Phase 1

-----

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DEVELOPER (Browser)                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP port 80 only
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     NGINX Reverse Proxy                          │
│                     (platform-nginx)                             │
│                                                                   │
│   /            →  frontend:3000                                  │
│   /api/        →  backend:8000                                   │
│   /repo-{id}/  →  platform-repo-{id} (path-based only)          │
└──────┬──────────────────────┬───────────────────────────────────┘
       │                      │
       ▼                      ▼
┌──────────────┐    ┌─────────────────────────────────────────────┐
│   Frontend   │    │          Internal Docker Network             │
│  (React/TS)  │    │          (platform-network)                  │
│  port 3000   │    │                                              │
└──────────────┘    │  ┌─────────────┐    ┌──────────────────┐   │
                    │  │   Backend   │    │     Worker       │   │
                    │  │  (FastAPI)  │    │   (Python)       │   │
                    │  │  port 8000  │    │                  │   │
                    │  └──────┬──────┘    └────────┬─────────┘   │
                    │         │                     │             │
                    │         │    ┌────────────────────────┐    │
                    │         │    │        Redis            │    │
                    │         │    │       port 6379         │    │
                    │         │    └────────────────────────┘    │
                    │                                              │
                    │  ┌───────────────────────────────────────┐  │
                    │  │      Deployed App Containers          │  │
                    │  │  platform-repo-1  (no public port)    │  │
                    │  │  platform-repo-2  (no public port)    │  │
                    │  └───────────────────────────────────────┘  │
                    └──────────────┬──────────────────────────────┘
                                   │ external connection
                                   ▼
                    ┌──────────────────────────────────┐
                    │      PostgreSQL (Supabase)        │
                    │   hosted — port 5432              │
                    │   *.supabase.co                   │
                    └──────────────────────────────────┘
```

Additionally, GitHub sends webhook POST requests directly to:

```
GitHub → http://EC2-IP/api/webhooks/github → NGINX → Backend
```

-----

## 2. Public Port Policy

Only these ports are exposed to the internet on the EC2 instance:

Port 22 — SSH access to the VM
Port 80 — NGINX HTTP traffic

All other ports are closed. App containers have zero public port bindings.

-----

## 3. Repository Requirements

Repositories deployed by this platform must meet the following requirements:

1. Repository must be publicly accessible on GitHub.
1. Repository must contain a Dockerfile in the root directory.
1. Dockerfile must expose port 80.
1. The application inside the container must listen on port 80.

The platform does NOT perform:

- Framework detection
- Language detection
- Dockerfile generation
- Buildpack generation

The developer is responsible for containerizing the application correctly.

-----

## 4. Docker Network: platform-network

All containers must be attached to this single bridge network.

```
platform-network (bridge)
├── platform-nginx          ← routes all inbound traffic
├── platform-frontend       ← serves React app
├── platform-backend        ← FastAPI API and webhook receiver
├── platform-worker         ← deployment execution engine
├── platform-redis          ← job queue
├── platform-repo-1         ← deployed user application
├── platform-repo-2         ← deployed user application
└── platform-repo-N         ← ...
```

Rules:

App containers use no -p flag. Zero public port binding.

NGINX reaches app containers by container name. Docker DNS resolves container names on the same network.

Only PostgreSQL (Supabase) is accessed externally over the internet.

-----

## 5. Component Descriptions

### 5.1 Frontend (React + TypeScript)

Serves the user interface only.

Communicates with backend exclusively via /api/ proxied through NGINX.

Polls GET /api/deployments/{id} every 3 seconds while a deployment is in a non-terminal state.

Stops polling when status is RUNNING or FAILED.

Never touches Docker, Redis, or PostgreSQL directly.

### 5.2 Backend (FastAPI)

Validates and processes webhook events from GitHub.

Handles repository registration API.

Serves all deployment and repository data via REST API.

Writes deployment records to PostgreSQL.

Pushes jobs to Redis queue.

Serves the /health endpoint.

Never runs docker, git, terraform, or any shell command. That responsibility belongs exclusively to the worker.

### 5.3 Worker (Python)

The core execution engine of the platform.

Runs an infinite loop using BLPOP on Redis. Zero CPU waste while idle.

Executes all deployment operations using subprocess calls.

Updates PostgreSQL at every status transition.

Appends logs to the deployment record throughout execution.

Mounts the Docker socket to control Docker on the host.

Mounts shared volumes for clone directories and NGINX config.

Handles all cleanup on failure.

### 5.4 Redis

Job queue between backend and worker.

Backend pushes jobs with LPUSH.

Worker consumes jobs with BLPOP (blocking pop — no busy loop, zero CPU waste while idle).

Queue name: deployments

Job payload:

- deployment_id
- repo_id
- repo_url
- commit_sha

### 5.5 PostgreSQL (Supabase — hosted)

Hosted PostgreSQL. No local container.

Backend and worker connect via SQLAlchemy connection string.

Stores all repository and deployment records.

Supabase dashboard allows visual inspection of records during development.

### 5.6 NGINX

The only public-facing component. All inbound traffic goes through NGINX.

Serves frontend at /

Proxies API calls to backend at /api/

Routes deployed app traffic at /repo-{repo_id}/

Worker dynamically generates one config file per repository after each successful deployment.

Main nginx.conf is never modified at runtime.

Worker reloads NGINX using docker exec after writing the config file.

-----

## 6. Event-Driven Flow (End to End)

```
1.  Developer pushes code to main branch on GitHub
2.  GitHub sends POST to http://EC2-IP/api/webhooks/github
3.  NGINX forwards request to backend:8000
4.  Backend validates HMAC signature
5.  Backend checks event type is push
6.  Backend checks branch is refs/heads/main
7.  Backend checks X-GitHub-Delivery is not a duplicate
8.  Backend checks repository is registered
9.  Backend creates deployment record with status PENDING
10. Backend pushes job to Redis queue
11. Backend returns 200 immediately
12. Worker picks up job from Redis (BLPOP)
13. Worker updates status to CLONING
14. Worker runs: git clone {repo_url} ./repos/platform-repo-{repo_id}/
15. Worker runs: git checkout {commit_sha}
16. Worker checks for Dockerfile in repository root
    ├── not found → status = FAILED, error = "No Dockerfile found in repository root", cleanup clone dir, STOP
17. Worker updates status to BUILDING
18. Worker runs: docker build -t platform-image-{repo_id}-{sha} ./repos/platform-repo-{repo_id}/
19. Worker updates status to DEPLOYING
20. Worker runs: docker rm -f platform-repo-{repo_id}  (removes old container if exists)
21. Worker runs: docker run -d --name platform-repo-{repo_id} --network platform-network platform-image-{repo_id}-{sha}
22. Worker runs health checks (3 retries, 5s apart)
23. On success: worker writes nginx/conf.d/platform-repo-{repo_id}.conf
24. Worker runs: docker exec platform-nginx nginx -s reload
25. Worker updates deployment status to RUNNING and stores deployed URL
26. Frontend polling detects RUNNING status and displays live URL
```

-----

## 7. Worker Execution Flow (Detailed)

```
Redis BLPOP → job: { deployment_id, repo_id, repo_url, commit_sha }
    │
    ▼
Update PostgreSQL: status = CLONING
    │
    ▼
subprocess: git clone {repo_url} ./repos/platform-repo-{repo_id}/
    ├── fail → cleanup clone dir, status = FAILED, log error, STOP
    │
    ▼
subprocess: git -C ./repos/platform-repo-{repo_id}/ checkout {commit_sha}
    ├── fail → cleanup clone dir, status = FAILED, log error, STOP
    │
    ▼
Check for Dockerfile in ./repos/platform-repo-{repo_id}/Dockerfile
    ├── not found → status = FAILED, error = "No Dockerfile found in repository root", cleanup clone dir, STOP
    │
    ▼
Update PostgreSQL: status = BUILDING
    │
    ▼
subprocess: docker build -t platform-image-{repo_id}-{sha_short} ./repos/platform-repo-{repo_id}/
    ├── fail → cleanup clone dir, status = FAILED, log error, STOP
    │
    ▼
Update PostgreSQL: status = DEPLOYING
    │
    ▼
subprocess: docker rm -f platform-repo-{repo_id}  (ignore error if no old container exists)
    │
    ▼
subprocess: docker run -d --name platform-repo-{repo_id} --network platform-network platform-image-{repo_id}-{sha_short}
    ├── fail → docker rmi image, cleanup clone dir, status = FAILED, STOP
    │
    ▼
Health check loop (3 retries, 5s apart):
subprocess: docker exec platform-repo-{repo_id} wget -q --spider http://localhost:80
    ├── fail after all retries → docker rm -f container, docker rmi image, cleanup clone dir, status = FAILED, STOP
    │
    ▼
Write nginx/conf.d/platform-repo-{repo_id}.conf
    │
    ▼
subprocess: docker exec platform-nginx nginx -s reload
    │
    ▼
Update PostgreSQL:
    status = RUNNING
    deployed_url = /repo-{repo_id}/
    completed_at = now()
    │
    ▼
Cleanup previous clone directory (remove old repo files after successful redeploy)
    │
    ▼
DONE — worker returns to BLPOP loop
```

-----

## 8. NGINX Configuration

### Base Config (static — never modified at runtime)

nginx/nginx.conf

```nginx
events {}

http {
    include /etc/nginx/conf.d/*.conf;

    server {
        listen 80;

        location / {
            proxy_pass http://platform-frontend:3000;
        }

        location /api/ {
            proxy_pass http://platform-backend:8000/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
```

### Per-Repository Config (generated by worker after each successful deployment)

nginx/conf.d/platform-repo-{repo_id}.conf

```nginx
location /repo-3/ {
    proxy_pass http://platform-repo-3:80/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

Worker writes this file and reloads NGINX. The main nginx.conf is never touched.

-----

## 9. Database Schema

### Hosted on: Supabase (free tier PostgreSQL)

### Table: repositories

id — INTEGER PRIMARY KEY
name — TEXT — display name of the repository
github_url — TEXT — full GitHub repository URL
webhook_secret — TEXT — per-repository HMAC secret generated at registration
registered_at — TIMESTAMP — when the repository was registered

### Table: deployments

id — INTEGER PRIMARY KEY
repo_id — INTEGER FOREIGN KEY references repositories(id)
commit_sha — TEXT — full commit SHA from webhook payload
triggered_by — TEXT UNIQUE — X-GitHub-Delivery header value used for deduplication
status — TEXT — current deployment status
image_name — TEXT — Docker image name built for this deployment
container_name — TEXT — Docker container name running this deployment
deployment_url — TEXT — /repo-{repo_id}/ populated on RUNNING; frontend constructs the full URL
logs — TEXT — accumulated logs from all worker steps, appended throughout
error — TEXT — error detail if status is FAILED
started_at — TIMESTAMP — when worker picked up the job
completed_at — TIMESTAMP — when status reached RUNNING or FAILED

No additional tables are required for Phase 1.

-----

## 10. Deterministic Naming Rules

Docker container name: platform-repo-{repo_id}
Example: platform-repo-3

Docker image name: platform-image-{repo_id}-{commit_sha_short}
Example: platform-image-3-a1b2c3

Clone directory: ./repos/platform-repo-{repo_id}/
Example: ./repos/platform-repo-3/

NGINX config file: nginx/conf.d/platform-repo-{repo_id}.conf
Example: nginx/conf.d/platform-repo-3.conf

Deployed URL path: /repo-{repo_id}/
Example: /repo-3/

All names derived from repository ID. No random strings. Fully deterministic.

-----

## 11. Worker Subprocess Rules

Worker uses subprocess only. No Docker SDK.

```python
import subprocess

def run_cmd(cmd: list[str]) -> tuple[str, int]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    return output, result.returncode
```

Example calls:

run_cmd([“git”, “clone”, repo_url, clone_dir])
run_cmd([“git”, “-C”, clone_dir, “checkout”, commit_sha])
run_cmd([“docker”, “build”, “-t”, image_name, clone_dir])
run_cmd([“docker”, “rm”, “-f”, container_name])
run_cmd([“docker”, “run”, “-d”, “–name”, container_name, “–network”, “platform-network”, image_name])
run_cmd([“docker”, “exec”, container_name, “wget”, “-q”, “–spider”, “http://localhost:80”])
run_cmd([“docker”, “rmi”, image_name])
run_cmd([“docker”, “exec”, “platform-nginx”, “nginx”, “-s”, “reload”])

Why subprocess over Docker SDK:
Direct output capture makes logging straightforward.
No SDK abstraction hiding what commands actually execute.
Easier debugging — commands are readable as plain strings.
More educational — you understand exactly what runs.

-----

## 12. Service Communication Summary

Frontend to Backend: HTTP via /api/ proxied through NGINX

Backend to PostgreSQL: SQLAlchemy async connection to Supabase

Backend to Redis: redis-py LPUSH on POST /api/webhooks/github

Worker to Redis: redis-py BLPOP — blocking consume, zero CPU waste while idle

Worker to PostgreSQL: SQLAlchemy — status and log updates throughout execution

Worker to Docker: subprocess — git, docker build, docker run, docker rm, docker rmi, docker exec

Worker to NGINX: subprocess docker exec platform-nginx nginx -s reload

NGINX to Frontend: proxy_pass to platform-frontend:3000

NGINX to Backend: proxy_pass to platform-backend:8000

NGINX to Deployed Apps: proxy_pass to platform-repo-{id}:80

GitHub to Platform: HTTP POST to /api/webhooks/github (public EC2 IP)

-----

## 13. Folder Structure

```
gitops-cd-platform/
│
├── docker-compose.yml
├── PRD.md
├── SYSTEM_ARCHITECTURE.md
├── TECH_STACK.md
├── .env.example
├── README.md
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── App.tsx
│       ├── api/
│       │   └── client.ts
│       └── pages/
│           ├── Dashboard.tsx
│           ├── RepositoryRegistration.tsx
│           ├── RepositoryDetails.tsx
│           ├── DeploymentHistory.tsx
│           └── DeploymentDetails.tsx
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   └── routes/
│       ├── repositories.py
│       ├── deployments.py
│       ├── webhooks.py
│       └── health.py
│
├── worker/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── worker.py          ← infinite Redis BLPOP loop
│   ├── deployer.py        ← full deployment execution flow
│   ├── cleanup.py         ← targeted cleanup logic
│   ├── nginx_manager.py   ← per-repo NGINX config write and reload
│   └── database.py        ← worker database connection
│
├── nginx/
│   ├── nginx.conf         ← static base config, never modified at runtime
│   └── conf.d/
│       └── .gitkeep       ← worker writes per-repo configs here
│
└── repos/                 ← cloned repositories (gitignored)
    └── .gitkeep
```

-----

## 14. Failure Scenarios and Expected Behavior

Invalid webhook signature
Expected: Return 401. No database write. No Redis push.
Why: Invalid signature means the request did not come from GitHub or the secret is wrong. Reject immediately.

Non-push event type
Expected: Return 200. No action.
Why: GitHub sends many event types. Returning 200 prevents GitHub from retrying endlessly.

Non-main branch push
Expected: Return 200. No action.
Why: Phase 1 only deploys main. Feature branch pushes are ignored by design.

Duplicate delivery ID
Expected: Return 200. No action.
Why: GitHub occasionally delivers the same webhook twice. Deduplication prevents double deployments.

Repository not registered
Expected: Return 200. No action.
Why: Webhooks from unregistered repositories are silently ignored.

No Dockerfile found
Expected: Mark FAILED. error = “No Dockerfile found in repository root”. Remove clone directory.
Cause: Developer did not include a Dockerfile in the repository root.

Git clone failure
Expected: Mark FAILED. Log error output. Remove clone directory.
Cause: Invalid URL, repo deleted, network error.

Docker build failure
Expected: Mark FAILED. Log error output. Remove clone directory.
Cause: Syntax error in Dockerfile, missing dependencies, build command fails.

Docker run failure
Expected: Mark FAILED. Remove image. Remove clone directory.
Cause: Port conflict, resource exhaustion, invalid image.

Health check failure
Expected: Mark FAILED. Remove container. Remove image. Remove clone directory.
Cause: Application crashes on startup, wrong port, misconfiguration.

Redis outage
Expected: API returns 500. Deployment record may exist but job was never queued.
Mitigation for Phase 1: None. Acceptable known limitation.

PostgreSQL outage
Expected: API returns 500. Nothing persisted.
Mitigation for Phase 1: None. Acceptable known limitation.

-----

## 15. Why This Architecture Is Interview-Worthy

Why is the API asynchronous?

If the API executed deployment operations synchronously, the HTTP request would hang for minutes while git clone, docker build, and container startup complete. Clients would time out. Multiple simultaneous deployments would block each other. The Redis queue allows the API to return immediately while the worker handles execution independently. This is the standard pattern for any long-running background operation.

Why Redis over a simple database queue?

Redis BLPOP provides true blocking behavior with zero CPU usage while idle. A database-based queue would require polling on a timer, wasting CPU and database connections. Redis is purpose-built for this use case.

Why subprocess over Docker SDK?

subprocess captures stdout and stderr directly, making log accumulation straightforward. The Docker SDK abstracts away the actual commands, which makes debugging harder and hides what is really happening. For an educational project, being able to see exactly what commands run is more valuable.

Why path-based routing over subdomains?

Subdomains require DNS configuration and wildcard SSL certificates. Path-based routing works on any public IP with zero DNS setup, which makes it suitable for a single EC2 instance without a domain name.

Why targeted cleanup over docker system prune?

docker system prune removes all unused images and containers on the host, which would destroy platform services and other running deployments. Targeted cleanup by name is safe and predictable.

Why constant-time comparison for HMAC?

Standard string comparison short-circuits on the first mismatched character, leaking timing information that could be exploited to reconstruct the secret byte by byte. hmac.compare_digest always takes the same amount of time regardless of where the mismatch occurs.