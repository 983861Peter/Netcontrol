# Deployment Guide

This project includes a FastAPI backend in `router_sim/router_api.py` and a static frontend in `router_sim/ui/`.

## 1. Deploy the backend

### Local run
```bash
cd "c:\Users\X1 CARBON\Downloads\ACS 400 PROJECT"
python -m uvicorn router_sim.router_api:app --host 0.0.0.0 --port 8080 --reload
```

Open:
- `http://127.0.0.1:8080/static/index.html`
- `http://127.0.0.1:8080/docs`

### Docker
```bash
docker build -t netcontrol-backend .
docker run -p 8080:8080 netcontrol-backend
```

## 2. Configure the frontend

The UI now uses `window.location.origin` by default. If you host the frontend together with the backend, the UI will call the same origin automatically.

If you host the UI separately, set `window.API_BASE` to the backend URL before the UI script loads.

Example in HTML:
```html
<script>
  window.API_BASE = "https://your-backend.example.com";
</script>
<script src="main.js"></script>
```

## 3. Recommended hosting options

- Railway
- Render
- Fly.io
- Azure App Service
- AWS App Runner / ECS
- DigitalOcean App Platform

## 4. GitHub deployment strategy

- Keep GitHub as the code repository
- Deploy the backend using a server or container host
- Serve the UI from the backend via `/static`
- Or host the UI separately and configure `window.API_BASE`
