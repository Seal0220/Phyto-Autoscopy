# Phyto-Autoscopy

**Phyto-Autoscopy 綠色自視症** is the Python control system for **CHLOROCULUS v0.1**, a local multi-view plant capture and rotation-control device.

The first implementation is intentionally local-first:

- FastAPI backend with Jinja2 templates
- Vanilla JavaScript and a local copy of the Tailwind CDN runtime
- JSON-only configuration
- SQLite and local file storage
- USB camera abstraction with mock mode
- PhidgetStepper motor abstraction with hardware safety checks

## Manual Start

Install dependencies, then start the system manually:

```bash
python run.py --mock
```

The default local address is:

```text
http://127.0.0.1:22222
```

The UI loads Tailwind locally from `app/web/static/js/tailwindcss-3.4.1.js`, which is a local copy of `https://cdn.tailwindcss.com/3.4.1`.

The repository guideline says automated agents must not start `run.py`, background processes, or servers. Start and stop the interface yourself when you are ready.

## Project Layout

```text
app/        FastAPI app, APIs, services, hardware abstractions, web templates
config/     JSON configuration
data/       Local captures, SQLite database, logs, temp files
scripts/    Manual helper scripts
tests/      Unit and integration tests
goals/      Project goal documents
```

## Hardware Safety

The motor starts disengaged. Movement commands pass through software limits for angle, velocity, acceleration, current limit, and movement timeout. Use mock mode until the physical CHLOROCULUS ARM and wiring have been checked.
