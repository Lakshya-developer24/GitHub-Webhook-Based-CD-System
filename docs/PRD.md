# Product Requirements Document (PRD)

# GitHub Webhook Driven Continuous Deployment Platform — Phase 1

-----

## 1. Overview

### Product Name

GitHub Webhook Driven Continuous Deployment Platform

### Inspiration

Simplified internal CD platform used by a small engineering team

### One-Line Description

A self-service continuous deployment platform that automatically redeploys a registered application whenever code is pushed to its main branch on GitHub.

### What This Is

A platform that demonstrates real DevOps engineering concepts:

- Event-driven architecture via GitHub webhooks
- HMAC signature validation and webhook security
- Asynchronous job processing via Redis
- Docker build and deployment pipelines
- Deployment lifecycle management
- Operational failure handling and cleanup
- Reverse proxy routing with NGINX

### What This Is NOT

- Not a GitHub Actions replacement
- Not a production-grade CI/CD platform
- Not a multi-tenant SaaS product
- Not a Jenkins clone
- Not a monitoring or observability platform

### Scope

Phase 1 only. No Kubernetes. No multi-environment deployments. No branch selection. No rollbacks. No authentication.

-----

## 2. Goals

Goal: Functional
Description: End-to-end automated deployment triggered by a GitHub push event works completely on a single VM

Goal: Architectural
Description: Demonstrates real event-driven DevOps engineering patterns

Goal: Resume-worthy
Description: Every architectural decision can be explained and defended in a technical interview

Goal: Deployable
Description: Entire platform runs on a single EC2 t2.micro instance with one docker compose up

-----
## 3. Repository Requirements

To be deployable by the platform, a repository must satisfy all of the following requirements:

1. Repository must be publicly accessible on GitHub.
2. Repository must contain a Dockerfile in the root directory.
3. The Dockerfile must expose port 80.
4. The application inside the container must listen on port 80.

Repositories that do not satisfy these requirements are rejected during deployment.

The platform does not perform:

- Framework detection
- Language detection
- Dockerfile generation
- Buildpack generation

The developer is responsible for containerizing the application correctly.

-----


## 4. MVP Success Criteria

The project is complete when ALL of the following are true:

- [ ] User can register a GitHub repository through the dashboard
- [ ] Platform generates a unique webhook secret per repository
- [ ] Platform displays the webhook URL and secret to the user
- [ ] GitHub push to main branch triggers a webhook to the platform
- [ ] Platform validates HMAC signature and rejects invalid requests with 401
- [ ] Platform ignores non-push events and non-main branch pushes with 200
- [ ] Platform deduplicates webhooks using X-GitHub-Delivery header
- [ ] Deployment job is queued in Redis asynchronously
- [ ] Worker clones the exact commit SHA from the webhook payload
- [ ] Worker builds a Docker image from the cloned repository
- [ ] Worker starts the container on the internal Docker network with no public port binding
- [ ] Worker runs a health check before marking deployment successful
- [ ] NGINX is updated with per-repository routing and reloaded
- [ ] Deployment status progresses through the full lifecycle and is visible on the dashboard
- [ ] Logs are stored and viewable per deployment
- [ ] Failed deployments clean up images, containers, and clone directories
- [ ] Everything runs on a single Linux VM with one docker compose up
- [ ] Repository contains a Dockerfile in the root directory
- [ ] Application exposes port 80

-----

## 5. Core User Story

A developer registers a GitHub repository on the platform dashboard.

The platform generates a webhook secret for that repository.

The platform displays the webhook URL and secret.

The developer manually adds the webhook inside GitHub settings.

From this point forward, whenever the developer pushes code to the main branch:

GitHub sends a webhook POST request to the platform.

The platform validates the request, creates a deployment record, and queues a job.

A worker picks up the job, clones the latest code at the exact pushed commit, builds a Docker image, replaces the running container, runs a health check, and updates NGINX routing.

The developer can monitor deployment status, view logs, and see the live URL from the dashboard.

-----

## 6. Repository Registration Flow

Step 1 — User opens dashboard and clicks Add Repository.

Step 2 — User enters:

- Repository Name
- GitHub Repository URL (must be <https://github.com/>*)

Step 3 — Platform generates a cryptographically random webhook secret.

Step 4 — Repository record is stored in the database.

Step 5 — Platform displays to user:

- Webhook URL: POST /api/webhooks/github
- Webhook Secret: the generated secret

Step 6 — User manually configures the GitHub webhook:

- Payload URL: <http://EC2-IP/api/webhooks/github>
- Content type: application/json
- Secret: the secret shown by the platform
- Events: Push events only

Only registered repositories can trigger deployments.

-----

## 7. Webhook Processing Flow

Step 1 — Receive POST /api/webhooks/github

Step 2 — Validate HMAC signature

- Read X-Hub-Signature-256 header
- Compute HMAC-SHA256 of raw request body using the repository’s webhook secret
- Compare using hmac.compare_digest for constant-time comparison
- If invalid: return 401 immediately. No database write. No job push.

Step 3 — Verify event type

- Read X-GitHub-Event header
- If not push: return 200 immediately. No deployment created.

Step 4 — Verify branch

- Read ref field from payload
- If ref is not refs/heads/main: return 200 immediately. No deployment created.

Step 5 — Deduplicate

- Read X-GitHub-Delivery header
- Attempt to create a deployment record using triggered_by as a UNIQUE field.
- If a unique constraint violation occurs, return 200 immediately and stop processing.
- This guarantees deduplication even under concurrent webhook delivery.

Step 6 — Verify repository registration

- Extract repository URL from payload
- Check database for matching registered repository
- If not registered: return 200 immediately. No deployment created.

Step 7 — Create deployment record with status PENDING

Step 8 — Push job to Redis queue with deployment_id and commit_sha

Step 9 — Return 200 immediately

The API must never execute deployment operations directly.

-----

## 8. Deployment Status Lifecycle

PENDING — Deployment record created, job pushed to Redis, waiting for worker to pick up

CLONING — Worker has picked up job, updating status, running git clone and checkout

BUILDING — Clone complete, running docker build

DEPLOYING — Image built successfully, starting container

RUNNING — Container started, health check passed, NGINX updated

FAILED — Error occurred at any stage, error field populated, cleanup executed

Flow:

PENDING → CLONING → BUILDING → DEPLOYING → RUNNING

FAILED can occur at any stage after PENDING.

No QUEUED status.
No rollback states.
No approval states.

-----

## 9. Worker Responsibilities

The worker runs an infinite loop consuming jobs from Redis using BLPOP.

For each job:

Step 1 — Pull job from Redis queue

Step 2 — Update deployment status to CLONING

Step 3 — Clone the registered repository into a local directory

Step 4 — Checkout the exact commit SHA from the webhook payload
Step 4.5 — Verify Dockerfile exists in repository root

If Dockerfile does not exist:

- Mark deployment FAILED
- Store error:
  "No Dockerfile found in repository root"
- Clean up clone directory
- Stop processing

Step 5 — Update deployment status to BUILDING

Step 6 — Build Docker image from the cloned directory

Step 7 — Update deployment status to DEPLOYING

Step 8 — Remove old container for this repository if one exists

Step 9 — Start new container on platform-network with no public port binding

Step 10 — Run health checks (3 retries, 5 seconds apart, 15 seconds maximum)

Step 11 — If health checks pass: write NGINX config, reload NGINX, update status to RUNNING

Step 12 — If health checks fail: remove container, remove image, clean up clone directory, update status to FAILED

The worker must store logs throughout all steps. Logs must be appended, not overwritten, as execution progresses.

-----

## 10. Deployment Strategy

Step 1 — Remove old container if it exists
docker rm -f platform-repo-{repo_id}

Step 2 — Start new container
docker run -d –name platform-repo-{repo_id} –network platform-network {image_name}
No -p flag. No public port binding.

Step 3 — Health check loop
3 retries. 5 seconds apart. Maximum 15 seconds.
docker exec platform-repo-{repo_id} wget -q –spider <http://localhost:80>

Step 4 — If health check passes
Write NGINX config file for this repository.
Reload NGINX: docker exec platform-nginx nginx -s reload
Update deployment status to RUNNING.
Store deployed URL in deployment record.

Step 5 — If health check fails
docker rm -f platform-repo-{repo_id}
docker rmi {image_name}
Remove clone directory.
Update deployment status to FAILED.
Store error in deployment record.

-----

## 11. NGINX Routing

Path-based routing only. No subdomains. No wildcard DNS.

Routes:

/ routes to React frontend container

/api/ routes to FastAPI backend container

/repo-{repo_id}/ routes to deployed application container for that repository

Worker generates one NGINX config file per repository after a successful deployment.

Main nginx.conf is never modified at runtime.

Worker reloads NGINX after writing the config file.

Stored deployment path:
/repo-{repo_id}/

The frontend constructs the final URL using the current application origin and the stored route path.

-----

## 12. Failure Handling

Invalid webhook signature

- Return 401
- No database write
- No job pushed

Non-push event type

- Return 200
- No deployment created

Non-main branch push

- Return 200
- No deployment created

Duplicate delivery ID

- Return 200
- No deployment created

Repository not registered

- Return 200
- No deployment created

Git clone failure

- Mark deployment FAILED
- Store error logs
- Clean up clone directory

Docker build failure

- Mark deployment FAILED
- Store error logs
- Clean up clone directory

Docker run failure

- Mark deployment FAILED
- Store error logs
- Remove image
- Clean up clone directory

Health check failure

- Mark deployment FAILED
- Remove container
- Remove image
- Clean up clone directory

Redis outage

- API returns 500
- Deployment record may have been created but job cannot be queued
- Acceptable known limitation for Phase 1

PostgreSQL outage

- API returns 500
- Nothing persisted

-----

## 13. Cleanup Strategy

Disk growth is a real operational problem on a t2.micro instance with limited storage.

On every failure the worker must:

Remove the clone directory: rm -rf ./repos/platform-repo-{repo_id}/

Remove the failed Docker image: docker rmi {image_name}

Remove the failed Docker container if running: docker rm -f {container_name}

On every successful redeployment the worker must:

Remove the previous clone directory after the new deployment is confirmed RUNNING.

Never use docker system prune or docker image prune as these affect all containers and images on the host including platform services.

Always use targeted cleanup by name.

-----

## 14. Security Considerations

HMAC validation is mandatory. Every webhook must be validated before any processing occurs.

Constant-time comparison must be used. Python’s hmac.compare_digest prevents timing attacks.

Webhook secrets must be stored as environment variables and in the database per repository. Never hardcoded.

Repository validation ensures only registered repositories can trigger deployments.

Deduplication via X-GitHub-Delivery prevents replay attacks and duplicate processing.

Known limitation: The worker executes docker build on code cloned from public GitHub repositories. A malicious repository could contain a Dockerfile that executes arbitrary commands inside the build container. This is an acceptable risk for a portfolio project running on an isolated EC2 instance. In production this would require sandboxed build environments such as rootless builds or isolated build VMs. This limitation should be acknowledged in the README and is a strong interview discussion point demonstrating security awareness.

-----

## 15. Frontend Pages

### Page 1 — Dashboard

List of all registered repositories.
Each row shows: Repository Name, GitHub URL, last deployment status, last deployment time.
Button to add a new repository.
Click a repository row to go to repository details.

### Page 2 — Repository Registration

Input: Repository Name
Input: GitHub Repository URL
Submit button.
On success: display webhook URL and webhook secret with copy buttons.
Display instruction to configure the webhook in GitHub.

### Page 3 — Repository Details

Repository name and GitHub URL.
Last deployment status badge.
Deployed URL as clickable link (shown only when last deployment is RUNNING).
Button to view full deployment history.

### Page 4 — Deployment History

Table of all deployments for a repository.
Columns: ID, Commit SHA (first 7 characters), Status, Started At, Completed At.
Click a row to go to deployment details.

### Page 5 — Deployment Details

Deployment ID.
Commit SHA.
Status badge (auto-refreshes every 3 seconds via polling until terminal state).
Deployed URL as clickable link (shown only when status is RUNNING).
Started At and Completed At timestamps.
Logs in a scrollable box.
Error message if status is FAILED.

-----

## 16. Database Schema

### repositories

- id
- name
- github_url
- webhook_secret
- registered_at

### deployments

- id
- repo_id
- commit_sha
- triggered_by (UNIQUE)
- status
- image_name
- container_name
- deployment_url
- logs
- error
- started_at
- completed_at

## 17. API Endpoints

POST /api/repositories
Request: name, github_url
Response: id, name, github_url, webhook_url, webhook_secret, registered_at

GET /api/repositories
Response: array of repository records without webhook_secret

GET /api/repositories/{id}
Response: single repository record without webhook_secret

GET /api/repositories/{id}/deployments
Response: array of deployment records for that repository

GET /api/deployments/{id}
Response: full deployment record including logs

POST /api/webhooks/github
GitHub webhook receiver. Processes push events only.

GET /health
Response: status, database connectivity, Redis connectivity

-----

## 18. Deterministic Naming Rules

All resource names are derived from repository ID. No random strings.

Docker container name: platform-repo-{repo_id}
Example: platform-repo-3

Docker image name: platform-image-{repo_id}-{commit_sha_short}
Example: platform-image-3-a1b2c3d

Clone directory: ./repos/platform-repo-{repo_id}/
Example: ./repos/platform-repo-3/

NGINX config file: nginx/conf.d/platform-repo-{repo_id}.conf
Example: nginx/conf.d/platform-repo-3.conf

Deployed URL path: /repo-{repo_id}/
Example: /repo-3/

-----

## 19. Explicit Scope Limitations

Authentication and login: Out of scope
Private GitHub repositories: Out of scope
Branch selection per repository: Out of scope — main branch only, hardcoded
Multi-environment deployments: Out of scope
Rollback to previous deployment: Out of scope
Automatic retries on failure: Out of scope
Prometheus or Grafana monitoring: Out of scope
Kubernetes: Out of scope
Terraform: Out of scope
Ansible: Out of scope
GitHub Actions: Out of scope
HTTPS and SSL: Out of scope
Subdomain-based routing: Out of scope
Manual deployment trigger from dashboard: Out of scope — webhook only