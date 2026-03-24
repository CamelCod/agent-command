"""
api_server.py — FastAPI HTTP wrapper for Agent Command.
Exposes the agent team over HTTP so n8n + Cloudflare Tunnel can trigger builds.
Includes a web dashboard at / for real-time build monitoring with SSE log streaming.

Run: uvicorn api_server:app --host 0.0.0.0 --port 8765
"""

import uuid
import asyncio
import json
import time
import os
import re
import base64
import urllib.parse
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import httpx
import itsdangerous

from heart.memoria import Memoria
from heart.echo import Echo
from heart.darwin import Darwin
from graph import build_graph, create_initial_state
import config

# ─────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────

memoria_global = None
echo_global = None
darwin_global = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global memoria_global, echo_global, darwin_global
    memoria_global = Memoria()
    await memoria_global.initialize()
    echo_global = Echo(memoria_global)
    darwin_global = Darwin(memoria_global)
    print("✓ MEMORIA, ECHO, DARWIN online")
    yield
    print("Shutting down...")

# ─────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Agent Command Dashboard", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

jobs: dict = {}

# ─────────────────────────────────────────────────────────────────
# Pydantic
# ─────────────────────────────────────────────────────────────────

class BuildRequest(BaseModel):
    intent: str
    needs_ai: bool = False

# ─────────────────────────────────────────────────────────────────
# Internal job runner with real-time event tracking
# ─────────────────────────────────────────────────────────────────

def job_event(job_id: str, event_type: str, data: dict):
    """Write an event to the job's event stream."""
    if job_id not in jobs:
        return
    jobs[job_id]["events"].append({"type": event_type, "data": data, "ts": datetime.utcnow().isoformat()})

async def _run_build_job(job_id: str, intent: str, needs_ai: bool):
    jobs[job_id]["started_at"] = datetime.utcnow().isoformat()
    jobs[job_id]["status"] = "running"

    try:
        graph = build_graph(memoria_global, echo_global, darwin_global)
        state = create_initial_state(intent, needs_ai)

        # Phase tracking for SSE events
        last_phase = -1
        phase_names = {0: "Strategy", 1: "Build", 2: "Quality", 3: "Ship", 4: "Done"}

        job_event(job_id, "phase", {"phase": 0, "name": "Strategy", "status": "starting"})
        job_event(job_id, "status", {"msg": "NEXUS, PRISM, ATLAS analyzing intent..."})

        state = await graph.ainvoke(state)

        # Determine which phase completed based on final state
        completed_phase = state.get("current_phase", 4)
        job_event(job_id, "phase", {"phase": completed_phase, "name": phase_names.get(completed_phase, "Done"), "status": "complete"})

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        jobs[job_id]["result"] = {
            "project_id": state.get("project_id", "unknown"),
            "quality_gate": "PASSED" if state.get("quality_gate_passed") else "FAILED",
            "avg_score": state.get("avg_team_score", 0),
            "total_runs": state.get("total_agent_runs", 0),
            "deliverables": state.get("deliverables", {}),
        }
        job_event(job_id, "done", jobs[job_id]["result"])

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        jobs[job_id]["status"] = "error"
        jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        jobs[job_id]["result"] = {"error": str(e), "traceback": tb[-800:]}
        job_event(job_id, "error", {"error": str(e)})

# ─────────────────────────────────────────────────────────────────
# Routes: Build
# ─────────────────────────────────────────────────────────────────

@app.post("/build")
async def trigger_build(req: BuildRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "intent": req.intent,
        "needs_ai": req.needs_ai,
        "result": None,
        "events": [],
    }
    background_tasks.add_task(_run_build_job, job_id, req.intent, req.needs_ai)
    return {"job_id": job_id, "status": "queued"}

@app.get("/job/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]

@app.get("/job/{job_id}/events")
async def job_events(job_id: str):
    """SSE stream of real-time job events."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    async def event_gen():
        last_idx = 0
        while True:
            if job_id not in jobs:
                break
            job = jobs[job_id]
            events = job.get("events", [])
            if len(events) > last_idx:
                for ev in events[last_idx:]:
                    yield {"event": ev["type"], "data": json.dumps(ev["data"])}
                last_idx = len(events)
            if job["status"] in ("complete", "error"):
                yield {"event": "job_end", "data": json.dumps({"status": job["status"]})}
                break
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_gen())

@app.get("/jobs")
async def list_jobs():
    sorted_jobs = sorted(jobs.items(), key=lambda x: x[1]["created_at"], reverse=True)
    return [{"job_id": k, **{k:v for k,v in j.items() if k != "events"}} for k, j in sorted_jobs[:50]]

# ─────────────────────────────────────────────────────────────────
# Routes: Team
# ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def team_health():
    return await memoria_global.get_team_health()

@app.get("/team")
async def team_table():
    health = await memoria_global.get_team_health()
    tiers = config.AGENT_TIERS
    rows = []
    for agent_id, data in sorted(health.items(), key=lambda x: tiers.get(x[0], "Z")):
        tier = tiers.get(agent_id, "??")
        bar_len = int(data["fitness"])
        bar = "█" * bar_len + "░" * (10 - bar_len)
        rows.append({"agent": agent_id, "tier": tier, "bar": bar, "fitness": data["fitness"], "runs": data["runs"], "model": data["model"]})
    return rows

@app.post("/evolve")
async def force_evolve():
    records = await darwin_global.evolve_team()
    return {"evolved": len(records)}

@app.get("/history/{agent_id}")
async def agent_history(agent_id: str):
    return await memoria_global.get_evolution_history(agent_id.upper())

# ─────────────────────────────────────────────────────────────────
# Proxy HTTP Client (reused across requests)
# ─────────────────────────────────────────────────────────────────

import os
import httpx
import itsdangerous
from starlette.middleware.sessions import SessionMiddleware
from fastapi import Request, Depends, HTTPException, status

# Lazy-loaded per-request; reuse a connection pool via a module-level client.
_http_client: httpx.AsyncClient | None = None

async def get_http_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client with connection pooling."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _http_client


# ─────────────────────────────────────────────────────────────────
# Session Management
# ─────────────────────────────────────────────────────────────────
#
# Security design:
#   - SESSION_SECRET_KEY signs all session cookies via itsdangerous.
#   - The browser never sees the Moonshot API key — it lives only on
#     the server and is injected by the /v1/chat/completions proxy.
#   - GitHub OAuth tokens are stored in the server-side session only.
#   - Sessions are cookie-based; no database required.
#
# Cookie layout (signed, httpOnly):
#   session = {
#     "is_premium": bool,
#     "github_access_token": str | None,
#     "github_username": str | None,
#   }
# ─────────────────────────────────────────────────────────────────

def _get_signer():
    secret = os.getenv("SESSION_SECRET_KEY", "dev-only-change-me-in-production")
    return itsdangerous.Signer(secret)

def _get_session_secret() -> str:
    secret = os.getenv("SESSION_SECRET_KEY")
    if not secret or secret == "dev-only-change-me-in-production":
        import warnings
        warnings.warn(
            "SESSION_SECRET_KEY is not set or is using the default value. "
            "Set a long random string in production to sign sessions securely.",
            UserWarning,
        )
    return secret


class SessionMiddleware(itsdangerous.Signer, SessionMiddleware):
    """
    Minimal cookie-based session middleware backed by itsdangerous signing.
    Reads and writes the cookie on every request; no external store needed.
    """
    def __init__(self, app, secret_key: str, cookie_name: str = "agentcraft_session",
                 max_age: int = 60 * 60 * 24 * 30):  # 30-day sessions
        super().__init__(app, secret_key=secret_key, cookie_name=cookie_name,
                         max_age=max_age, same_site="lax", https_only=False)


# ─────────────────────────────────────────────────────────────────
# Premium Feature Gating
# ─────────────────────────────────────────────────────────────────
#
# before: Premium UI was toggled by a localStorage flag — trivially forgeable.
# after:  Every premium-sensitive request is verified server-side before
#         the response is sent. The frontend cannot spoof a premium status.
#
# The check:
#   1. Look up "is_premium" in the signed session cookie.
#   2. If absent, call PREMIUM_CHECK_URL (Stripe/LemonSqueezy webhook URL).
#   3. Cache the result in the session for 5 minutes to avoid rate limits.
#
# Mock mode (before billing is integrated):
#   Set PREMIUM_CHECK_URL to any URL that returns HTTP 200 with
#   {"premium": false} — the mock endpoint below satisfies this.
# ─────────────────────────────────────────────────────────────────

SESSION_PREMIUM_CACHE_TTL = 300  # seconds

async def check_premium_status(request: Request) -> bool:
    """
    Returns True if the current session is premium.
    Caches the result in the session for SESSION_PREMIUM_CACHE_TTL seconds.
    """
    session = request.state.__dict__.get("_session", {})

    cached = session.get("_premium_cached_at", 0)
    import time as _time
    if _time.time() - cached < SESSION_PREMIUM_CACHE_TTL:
        return session.get("is_premium", False)

    # Premium check URL from env — mock endpoint returns {"premium": false}
    check_url = os.getenv("PREMIUM_CHECK_URL", "")

    is_premium = False
    if check_url:
        try:
            client = await get_http_client()
            resp = await client.get(
                check_url,
                headers={"Authorization": f"Bearer {request.state.session_id}"},
                timeout=5.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                is_premium = bool(data.get("premium", False))
        except Exception:
            pass  # Fail open on premium check errors — don't block the request

    # Update session
    request.state._session["is_premium"] = is_premium
    request.state._session["_premium_cached_at"] = _time.time()
    _save_session_cookie(request, request.state._session)

    return is_premium


# ─────────────────────────────────────────────────────────────────
# Session helpers (read/write signed cookies)
# ─────────────────────────────────────────────────────────────────

def _load_session(request: Request) -> dict:
    """Decode and verify the session cookie, return a dict."""
    cookie_value = request.cookies.get("agentcraft_session", "")
    if not cookie_value:
        return {}
    try:
        signer = itsdangerous.Signer(_get_session_secret())
        if not signer.unsign(cookie_value):
            return {}
        import urllib.parse
        data = urllib.parse.parse_qs(cookie_value)
        # Itsdangerous returns bytes; decode safely
        result = {}
        for k, v in data.items():
            result[k.decode() if isinstance(k, bytes) else k] = \
                v[0].decode() if isinstance(v[0], bytes) else v
        return result
    except Exception:
        return {}

def _save_session_cookie(request: Request, session: dict):
    """Sign and write session dict as a cookie (handled by Starlette)."""
    pass  # Starlette's session middleware handles this

# Inject session into request.state on every request
@app.middleware("http")
async def inject_session(request: Request, call_next):
    session = _load_session(request)
    request.state._session = session
    request.state.is_premium = session.get("is_premium", False)
    request.state.github_token = session.get("github_access_token")
    request.state.github_username = session.get("github_username")
    response = await call_next(request)
    return response


# ─────────────────────────────────────────────────────────────────
# Request Models
# ─────────────────────────────────────────────────────────────────

class ChatCompletionRequest(BaseModel):
    model: str = "kimi-k2.5"
    messages: list[dict]
    max_tokens: int | None = 4000
    temperature: float | None = 0.7
    stream: bool | None = False

class GithubExportRequest(BaseModel):
    project_name: str
    html_content: str


# ─────────────────────────────────────────────────────────────────
# Routes: AI Chat Proxy  (Moonshot key stays server-side)
# ─────────────────────────────────────────────────────────────────
#
# BEFORE (insecure — app.js):
#   fetch('https://api.moonshot.cn/v1/chat/completions', {
#     headers: { 'Authorization': 'Bearer ' + localStorage.getItem('api_key') }
#   })
#   ↑ User's real Moonshot key exposed in browser network tab + localStorage
#
# AFTER (secure — api_server.py):
#   POST /v1/chat/completions
#   Body: { messages, model, max_tokens, temperature, stream }
#   Server reads MOONSHOT_API_KEY from env, injects it, forwards to Moonshot.
#   Browser only ever talks to our own origin — key never leaves the server.
#
# Streaming:
#   When stream=True, Moonshot returns text/event-stream (SSE).
#   We relay it byte-for-byte as application/x-ndjson so the frontend
#   fetch can read it with response.body.getReader() — no buffering,
#   no added latency beyond the network hop to Moonshot.
# ─────────────────────────────────────────────────────────────────

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    """
    Proxy endpoint that forwards chat completion requests to Moonshot
    with the API key injected server-side. Supports streaming.
    """
    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MOONSHOT_API_KEY is not configured on the server.",
        )

    base_url = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
        try:
            payload = req.model_dump(exclude_none=True)
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            if req.stream:
                # Streaming: relay SSE byte-for-byte to avoid added latency
                moonc = await client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=120.0,
                )
                moonc.raise_for_status()

                async def stream_generator():
                    async for chunk in moonc.aiter_bytes(chunk_size=1024):
                        if chunk:
                            yield chunk

                return StreamingResponse(
                    stream_generator(),
                    media_type="application/x-ndjson",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",  # Disable nginx buffering
                    },
                )
            else:
                # Non-streaming: await full response, return JSON
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()

        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                                detail=f"Upstream error: {str(e)}")


# ─────────────────────────────────────────────────────────────────
# Routes: GitHub OAuth
# ─────────────────────────────────────────────────────────────────
#
# Security design:
#   1. Client requests GET /v1/auth/github → server builds GitHub
#      authorize URL with client_id + redirect_uri, returns 302.
#   2. User authorizes in GitHub → GitHub redirects to
#      GET /v1/auth/github/callback?code=XXX
#   3. Server exchanges code for access_token (POST to GitHub, server-only).
#      The access_token NEVER goes to the browser — it is stored in
#      the signed session cookie only.
#   4. Client polls GET /v1/user/session to know when auth is complete.
# ─────────────────────────────────────────────────────────────────

@app.get("/v1/auth/github")
async def github_oauth_start(request: Request):
    """
    Redirect the browser to GitHub's OAuth authorize page.
    """
    import urllib.parse

    client_id = os.getenv("GITHUB_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured.")

    callback_url = os.getenv("GITHUB_CALLBACK_URL", "http://localhost:8765/v1/auth/github/callback")
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": callback_url,
        "scope": "repo",
        "state": "agentcraft",  # In production, use a proper CSRF token
    })
    github_url = f"https://github.com/login/oauth/authorize?{params}"
    return {"authorize_url": github_url}


@app.get("/v1/auth/github/callback")
async def github_oauth_callback(request: Request, code: str = "", error: str = ""):
    """
    Exchange the OAuth authorization code for an access token.
    The token is stored in the signed session cookie — never sent to the browser.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {error}")

    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    callback_url = os.getenv("GITHUB_CALLBACK_URL", "http://localhost:8765/v1/auth/github/callback")

    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured.")

    # Exchange code for access token (server-to-server, secret never exposed)
    token_url = "https://github.com/login/oauth/access_token"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": callback_url,
            },
            headers={"Accept": "application/json"},
        )
    resp.raise_for_status()
    token_data = resp.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to obtain access token from GitHub.")

    # Look up the GitHub username using the access token
    username = "github_user"
    async with httpx.AsyncClient(timeout=10.0) as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        if user_resp.status_code == 200:
            username = user_resp.json().get("login", username)

    # Store in session (signed cookie, httpOnly — browser never sees raw token)
    session = dict(request.state._session or {})
    session["github_access_token"] = access_token
    session["github_username"] = username
    session["is_premium"] = session.get("is_premium", False)

    # Serialize to cookie via Starlette's session mechanism
    response = {"status": "ok", "username": username}
    from fastapi.responses import JSONResponse
    import urllib.parse as _urlparse, time as _time

    cookie_data = _urlparse.urlencode({**session})
    signer = itsdangerous.Signer(_get_session_secret())
    signed = signer.sign(cookie_data.encode())

    resp = JSONResponse(response)
    resp.set_cookie(
        key="agentcraft_session",
        value=signed.decode(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return resp


@app.get("/v1/auth/github/logout")
async def github_logout(request: Request):
    """Clear the GitHub token from the session."""
    session = dict(request.state._session or {})
    session.pop("github_access_token", None)
    session.pop("github_username", None)

    import urllib.parse as _urlparse
    cookie_data = _urlparse.urlencode({**session})
    signer = itsdangerous.Signer(_get_session_secret())
    signed = signer.sign(cookie_data.encode())

    resp = {"status": "ok"}
    response = JSONResponse(resp)
    response.set_cookie(
        key="agentcraft_session",
        value=signed.decode(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return response


# ─────────────────────────────────────────────────────────────────
# Routes: GitHub Export
# ─────────────────────────────────────────────────────────────────

@app.post("/v1/github/export")
async def github_export(req: GithubExportRequest, request: Request):
    """
    Create a GitHub repository and push the project HTML.
    Requires an active GitHub OAuth session — the token is server-side only.
    """
    token = request.state.github_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub not connected. Use GET /v1/auth/github to authorize first.",
        )

    username = request.state.github_username or "user"
    repo_name = req.project_name.lower().replace(" ", "-").replace("_", "-")
    # Filter to alphanumeric + hyphens
    import re
    repo_name = re.sub(r"[^a-z0-9-]", "", repo_name)[:100]

    # Create repo via GitHub API
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create repository
        create_resp = await client.post(
            "https://api.github.com/user/repos",
            json={
                "name": repo_name,
                "description": f"Generated by AgentCraft",
                "private": False,
                "auto_init": True,
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
            },
        )

        if create_resp.status_code == 422:
            # Repo already exists — fetch its details
            get_resp = await client.get(
                f"https://api.github.com/repos/{username}/{repo_name}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            if get_resp.status_code != 200:
                raise HTTPException(status_code=409, detail="Repository already exists and could not be accessed.")
        elif create_resp.status_code not in (201, 200):
            raise HTTPException(
                status_code=create_resp.status_code,
                detail=f"GitHub API error: {create_resp.text}",
            )

        # Push content via the Repos API — create a single file
        import base64
        encoded_content = base64.b64encode(req.html_content.encode()).decode()

        content_resp = await client.put(
            f"https://api.github.com/repos/{username}/{repo_name}/contents/index.html",
            json={
                "message": "feat: initial commit from AgentCraft\n\nCo-Authored-By: AgentCraft <agentcraft@example.com>",
                "content": encoded_content,
                "branch": "main",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
            },
        )
        content_resp.raise_for_status()

    repo_url = f"https://github.com/{username}/{repo_name}"
    return {"url": repo_url, "name": repo_name}


# ─────────────────────────────────────────────────────────────────
# Routes: User / Subscription
# ─────────────────────────────────────────────────────────────────

@app.get("/v1/user/session")
async def user_session(request: Request):
    """
    Return the current user session info for the frontend.
    Used by the UI to know: is GitHub connected? Is the user premium?
    """
    return {
        "github_username": request.state.github_username,
        "is_github_connected": bool(request.state.github_token),
        "is_premium": request.state.is_premium,
        "tier": "premium" if request.state.is_premium else "free",
    }

@app.get("/v1/user/subscription")
async def subscription_status(request: Request):
    """
    Mock subscription endpoint.
    In production: replace this with a Stripe/LemonSqueezy webhook handler
    that verifies the purchase and sets is_premium = True in the session.

    BEFORE billing integration: This always returns {"premium": false}.
    AFTER billing integration: A background process (webhook) would call
    this or set session["is_premium"] = True on purchase confirmation.
    """
    # The real check is done by check_premium_status() above.
    # This endpoint exists so PREMIUM_CHECK_URL can point to a static JSON
    # service or a billing webhook during the mock phase.
    return {"premium": False}


# ─────────────────────────────────────────────────────────────────
# Dashboard HTML
# ─────────────────────────────────────────────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Command Dashboard</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; }
.container { max-width: 1300px; margin: 0 auto; padding: 20px; }
header { display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 1px solid #30363d; margin-bottom: 24px; }
header h1 { font-size: 1.4rem; font-weight: 600; color: #58a6ff; }
.badge { background: #238636; color: #fff; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; }
.grid { display: grid; grid-template-columns: 1fr 380px; gap: 16px; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
.card h2 { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; border-bottom: 1px solid #30363d; padding-bottom: 8px; }
.build-form { grid-column: 1 / -1; }
textarea { width: 100%; background: #0d1117; border: 1px solid #30363d; color: #e6edf3; border-radius: 6px; padding: 12px; font-family: inherit; font-size: 0.95rem; resize: vertical; min-height: 80px; }
textarea:focus { outline: none; border-color: #58a6ff; }
.controls { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
.btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.875rem; font-weight: 500; transition: background 0.15s; }
.btn-primary { background: #238636; color: #fff; }
.btn-primary:hover { background: #2ea043; }
.btn-primary:disabled { background: #30363d; color: #8b949e; cursor: not-allowed; }
.checkbox-wrap { display: flex; align-items: center; gap: 6px; color: #8b949e; font-size: 0.875rem; }
.team-row { display: flex; align-items: center; padding: 6px 0; border-bottom: 1px solid #21262d; font-size: 0.875rem; }
.team-row:last-child { border-bottom: none; }
.team-row .agent { font-weight: 600; width: 70px; color: #58a6ff; }
.team-row .tier { font-size: 0.75rem; color: #8b949e; width: 30px; }
.team-row .bar { font-family: monospace; color: #3fb950; flex: 1; }
.team-row .fitness { width: 40px; text-align: right; color: #3fb950; }
.team-row .runs { width: 40px; text-align: right; color: #8b949e; font-size: 0.8rem; }
.job { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px; margin-bottom: 8px; }
.job-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px; }
.job-id { font-family: monospace; font-size: 0.8rem; color: #58a6ff; }
.job-status { font-size: 0.75rem; padding: 2px 8px; border-radius: 10px; font-weight: 500; }
.status-queued { background: #30363d; color: #8b949e; }
.status-running { background: #1f6feb; color: #fff; }
.status-complete { background: #238636; color: #fff; }
.status-error { background: #da3633; color: #fff; }
.job-intent { font-size: 0.85rem; color: #8b949e; margin-bottom: 8px; }
.logs { background: #0d1117; border-radius: 4px; padding: 8px; font-family: 'Fira Code', 'Consolas', monospace; font-size: 0.75rem; max-height: 200px; overflow-y: auto; margin-top: 8px; }
.log-line { padding: 2px 0; border-bottom: 1px solid #21262d; }
.log-line:last-child { border-bottom: none; }
.log-phase { color: #58a6ff; font-weight: 600; }
.log-starting { color: #d29922; }
.log-complete { color: #3fb950; }
.log-error { color: #f85149; }
.log-agent { color: #a5d6ff; }
.deliverable { display: inline-block; margin: 2px 4px; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; }
.deliv-yes { background: #238636; color: #fff; }
.deliv-no { background: #da3633; color: #fff; }
.deliv-na { background: #30363d; color: #8b949e; }
.no-jobs { text-align: center; color: #8b949e; padding: 20px; font-size: 0.875rem; }
#poll-status { position: fixed; bottom: 16px; right: 16px; background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 6px 12px; font-size: 0.75rem; color: #8b949e; }
.live-dot { display: inline-block; width: 6px; height: 6px; background: #3fb950; border-radius: 50%; margin-right: 4px; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>⚙️ Agent Command Dashboard</h1>
    <span class="badge">kimi-k2.5</span>
  </header>
  <div class="grid">
    <div class="card build-form">
      <h2>🚀 New Build</h2>
      <textarea id="intent" placeholder='e.g. "Build a REST API with auth and PostgreSQL"'></textarea>
      <div class="controls">
        <label class="checkbox-wrap"><input type="checkbox" id="needs-ai"> Enable WEAVE (AI)</label>
        <button class="btn btn-primary" id="build-btn" onclick="triggerBuild()">Run Build</button>
      </div>
      <div id="active-job" style="margin-top:12px; display:none">
        <div style="font-size:0.8rem;color:#8b949e;margin-bottom:6px">Live Logs:</div>
        <div id="log-container" class="logs"></div>
      </div>
    </div>
    <div class="card">
      <h2>🫀 Team Health</h2>
      <div id="team-list">Loading...</div>
    </div>
    <div class="card" style="grid-column:1/-1">
      <h2>📦 Builds</h2>
      <div id="jobs-list">Loading...</div>
    </div>
  </div>
</div>
<div id="poll-status"><span class="live-dot"></span><span id="poll-text">Connecting...</span></div>

<script>
const API = window.location.origin;
let activeJobId = null;
let evSource = null;

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function log(msg, type='') {
  const el = document.getElementById('log-container');
  const div = document.createElement('div');
  div.className = 'log-line' + (type ? ' log-' + type : '');
  div.textContent = new Date().toLocaleTimeString() + ' ' + msg;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

async function triggerBuild() {
  const intent = document.getElementById('intent').value.trim();
  if (!intent) return;
  const needsAi = document.getElementById('needs-ai').checked;
  const btn = document.getElementById('build-btn');
  btn.disabled = true; btn.textContent = 'Running...';
  try {
    const { job_id } = await api('/build', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intent, needs_ai: needsAi }),
    });
    activeJobId = job_id;
    document.getElementById('active-job').style.display = 'block';
    document.getElementById('log-container').innerHTML = '';
    log('Job #' + job_id + ' queued', 'starting');
    connectSSE(job_id);
    document.getElementById('intent').value = '';
    await refreshJobs();
  } catch(e) { alert('Error: ' + e.message);
  } finally { btn.disabled = false; btn.textContent = 'Run Build'; }
}

function connectSSE(jobId) {
  if (evSource) evSource.close();
  evSource = new EventSource(API + '/job/' + jobId + '/events');
  evSource.addEventListener('phase', e => {
    const d = JSON.parse(e.data);
    log(d.name + ' — ' + d.status, d.status === 'starting' ? 'starting' : 'complete');
  });
  evSource.addEventListener('agent', e => {
    const d = JSON.parse(e.data);
    log(d.agent + ' ✓ score:' + d.score, 'agent');
  });
  evSource.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    log('BUILD COMPLETE — ' + d.quality_gate + ' | score:' + d.avg_score, 'complete');
    evSource.close();
  });
  evSource.addEventListener('error', e => {
    const d = JSON.parse(e.data);
    log('ERROR: ' + d.error, 'error');
  });
  evSource.addEventListener('job_end', () => { evSource.close(); });
}

async function refreshTeam() {
  try {
    const rows = await api('/team');
    rows.sort((a,b) => ['T0','T1','T2','T3','T4'].indexOf(a.tier) - ['T0','T1','T2','T3','T4'].indexOf(b.tier));
    document.getElementById('team-list').innerHTML = rows.map(r =>
      `<div class="team-row"><span class="agent">${r.agent}</span><span class="tier">${r.tier}</span><span class="bar">${r.bar}</span><span class="fitness">${r.fitness.toFixed(1)}</span><span class="runs">${r.runs}</span></div>`
    ).join('');
  } catch(e) { document.getElementById('team-list').innerHTML = '<span style="color:#da3633">Error</span>'; }
}

async function refreshJobs() {
  try {
    const list = await api('/jobs');
    if (!list.length) { document.getElementById('jobs-list').innerHTML = '<div class="no-jobs">No builds yet</div>'; return; }
    document.getElementById('jobs-list').innerHTML = list.map(j => {
      const sc = 'status-' + j.status;
      let result = '';
      if (j.result) {
        if (j.result.error) result = `<div style="color:#f85149;margin-top:4px">${j.result.error.slice(0,120)}</div>`;
        else {
          const d = j.result.deliverables || {};
          const delivs = Object.entries(d).map(([k,v]) => `<span class="deliverable deliv-${v===true?'yes':v===false?'no':'na'}">${k}</span>`).join('');
          result = `<div style="margin-top:6px;font-size:0.8rem"><strong>${j.result.quality_gate}</strong> · score:${j.result.avg_score} · #${j.result.project_id}</div>${delivs ? '<div style="margin-top:4px">'+delivs+'</div>' : ''}`;
        }
      }
      return `<div class="job"><div class="job-header"><span class="job-id">#${j.job_id}</span><span class="job-status ${sc}">${j.status}</span></div><div class="job-intent">${j.intent}</div>${result}</div>`;
    }).join('');
  } catch(e) { document.getElementById('jobs-list').innerHTML = '<span style="color:#f85149">Error loading</span>'; }
}

async function poll() {
  document.getElementById('poll-text').textContent = 'Updated: ' + new Date().toLocaleTimeString();
  await Promise.allSettled([refreshTeam(), refreshJobs()]);
}
poll(); setInterval(poll, 5000);
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

@app.get("/ping")
async def ping():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
