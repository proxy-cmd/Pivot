# Running Verdant locally

Start the analytics API in one terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
npm run api
```

Start the web application in another terminal:

```powershell
npm install
npm run dev
```

The API is available at `http://localhost:8000/docs`. The dashboard uses it automatically at `http://localhost:5173`.

Add `GEMINI_API_KEY` only to `backend/.env`. It is never sent to the browser. Without it, the chat endpoint gives a safe local fallback answer.

## Delivery

```powershell
docker compose up --build
```

This production container serves the API on port 8000. Place a reverse proxy such as Caddy, Nginx, or a cloud load balancer in front of it for TLS and static-file delivery.
