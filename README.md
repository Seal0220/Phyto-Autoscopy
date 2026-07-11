# Phyto-Autoscopy

**Phyto-Autoscopy 綠色自視症** is the local control system for the CHLOROCULUS multi-view plant capture device.

## Architecture

```text
Browser
  ↓ HTTPS / WSS (when deployed behind a gateway)
Next.js BFF — 127.0.0.1:22223
  ↓ private server-to-server requests / WebSocket rewrite
FastAPI hardware backend — 127.0.0.1:22222
  ↓
Cameras, motor, experiments, settings, sessions, local files
```

The browser connects only to Next.js. It never receives the FastAPI port, a backend credential, or a hardware API URL. Next.js exposes constrained same-origin routes under `/api/*` and proxies the authenticated WebSocket path `/ws/status`.

```text
frontend/  Next.js App Router, JavaScript, Tailwind CSS v4, BFF route handlers
backend/   FastAPI API, hardware services, config, data, tests, audit records
start.bat  Starts and supervises both processes
```

FastAPI is API-only: the former Jinja page is not mounted. Its `/api/*` endpoints require a private BFF credential, carry an authenticated actor/role, apply permission checks and rate limits, validate inputs, and write state-changing operations to `backend/data/logs/audit.jsonl`. WebSocket connections use one-use short-lived tickets issued only through the authenticated BFF.

## Start

From the repository root:

```bash
.\start.bat
```

On the first run, `start.bat` copies `.env.example` to the ignored root `.env` and stops. Replace the three placeholder values there, then run it again. It installs frontend dependencies when needed.

For safe mock-hardware development:

```bash
.\start.bat --mock
```

Development mode is the default and runs `next dev` plus FastAPI with `uvicorn --reload`. For a production-style local run:

```bash
.\start.bat --mode production
```

That command runs `next build`, then `next start`, and starts FastAPI without reload. `start.bat` is the only supervisor: it starts two separate process trees, checks their PIDs, and terminates the remaining tree if either process exits. Neither FastAPI nor Next.js starts, stops, or monitors the other.

Open only:

```text
http://127.0.0.1:22223
```

Do not browse to FastAPI directly. Port `22222` is loopback-only and is the private BFF-to-hardware boundary.

## Environment

Shared hardware paths and private credentials belong in the root `.env`. FastAPI and the Next.js server each load that file independently; `start.bat` never injects it from one service into the other. `frontend/.env.example` documents optional server-only frontend overrides. Do not put backend addresses, hardware paths, credentials, or secrets in a `NEXT_PUBLIC_*` variable.

## Remote operation

Do not expose port 22223 or 22222 directly to the internet. Publish a single HTTPS/WSS entry point such as `https://phyto.example.com` through a reverse proxy or security gateway, with VPN or Zero Trust access, strong user authentication, TLS, permission management, and audit review. Keep both local application ports bound to `127.0.0.1` behind that gateway.

## Hardware safety

The motor starts disengaged. Movement commands remain subject to the backend's software limits for angle, velocity, acceleration, current, and timeout. Use `--mock` until the physical CHLOROCULUS ARM and wiring have been checked.
