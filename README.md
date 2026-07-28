# NetControl Router Simulation

## Overview

NetControl is a router simulation and network management platform built with:
- FastAPI backend in `router_sim/router_api.py`
- SQLite database for persistence in `router_sim/db.py`
- Static frontend UI under `router_sim/ui/`
- Authentication, device management, station and sector management, and audit logging

This README is intended for new users and developers who want to run, test, and understand the system.

## Key Features

- Company and user authentication
- Station creation and management
- Device and sector management for stations
- Gateway and router configuration simulation
- Audit logging and admin functionality
- UI and API integration via a shared origin or explicit API base URL

## Project Structure

- `router_sim/` — backend code and API server logic
- `router_sim/ui/` — frontend static files and JavaScript
- `router_sim/models.py` — ORM models and database schema
- `router_sim/db.py` — database setup and session management
- `README_DEPLOYMENT.md` — deployment-specific instructions
- `requirements.txt` — Python dependencies

## Prerequisites

- Python 3.11+ (project is tested against Python 3.11)
- `pip` for installing dependencies
- Optionally: Docker for container deployment

## Setup

1. Clone the repository:

```bash
git clone https://github.com/983861Peter/Netcontrol.git
cd "ACS 400 PROJECT"
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Initialize the database if needed:

```bash
python init_db.py
```

## Running the Project Locally

### Start the backend

Use Uvicorn to run the FastAPI app:

```bash
python -m uvicorn router_sim.router_api:app --host 0.0.0.0 --port 8080 --reload
```

Then open the frontend at:

```text
http://127.0.0.1:8080/static/index.html
```

### Open API docs

FastAPI auto-generated documentation is available at:

```text
http://127.0.0.1:8080/docs
```

## Frontend Configuration

The frontend is designed to call the backend automatically when served from the same origin.

- If you serve the UI from the backend, no extra configuration is required.
- If you host the UI separately, set `window.API_BASE` before loading `main.js`.

Example:

```html
<script>
  window.API_BASE = "https://your-backend.example.com";
</script>
<script src="main.js"></script>
```

## Deploying from GitHub

For new users, the easiest flow is:

1. Clone the repo from GitHub.
2. Create and activate a Python virtual environment.
3. Install dependencies from `requirements.txt`.
4. Start the backend with Uvicorn.
5. Browse to `/static/index.html`.

Optional Docker deployment is also described in `README_DEPLOYMENT.md`.

## Important Notes

- The system currently uses dynamic API URL detection in `router_sim/ui/main.js`.
- Local developer tools or test scripts may still contain references to `127.0.0.1:8080`.
- If the backend is hosted on a different host or port, update `window.API_BASE` accordingly.

## Troubleshooting

- If the UI shows `POST http://127.0.0.1:8080/... 500`, ensure the backend is running and accessible.
- If the frontend is served from another domain, always configure `window.API_BASE`.
- Use `uvicorn` logs and browser console errors to identify missing API endpoints.

## Contribution

New contributors should:

- Review existing API routes in `router_sim/router_api.py`
- Check model definitions in `router_sim/models.py`
- Confirm frontend calls in `router_sim/ui/*.js`
- Keep the UI and API host behavior consistent with `window.location.origin`

## Contact

For questions about this repository, use the GitHub issue tracker or contact the project owner.
