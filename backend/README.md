# Phyto-Autoscopy backend

This directory is the API-only FastAPI hardware backend. It contains camera and motor control, scheduling, settings, records, local storage, and the authenticated status WebSocket.

It is not a browser entry point and deliberately contains no templates, static assets, Jinja routes, or frontend JavaScript. Start the full stack from the repository root with `start.bat`; the Next.js BFF in `../frontend` is the only browser-facing service. This backend never starts, stops, or monitors the frontend.

Helper scripts remain available from either directory, for example:

```bash
python backend/scripts/validate_config.py
```
