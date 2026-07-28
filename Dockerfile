FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency definitions first for faster rebuilds
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Expose the backend port
EXPOSE 8080

# Run the FastAPI app
CMD ["uvicorn", "router_sim.router_api:app", "--host", "0.0.0.0", "--port", "8080"]
