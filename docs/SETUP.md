# Running Verdant locally

Start the analytics API in one terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
npm run api
```

For a working local workspace, set `DATABASE_URL` in `backend/.env` to a PostgreSQL database and add the Google OAuth values plus a long `JWT_SECRET`. The API intentionally returns a configuration error instead of allowing unauthenticated data access.

Start the web application in another terminal:

```powershell
npm install
npm run dev
```

The API is available at `http://localhost:8000/docs`. The dashboard uses it automatically at `http://localhost:5173`.

The development server proxies `/api` to port 8000. For a separately hosted API,
set `VITE_API_URL` before running `npm run build`; otherwise the packaged app uses
same-origin API requests.

Add `GEMINI_API_KEY` only to `backend/.env`. It is never sent to the browser. Without it, the chat endpoint gives a safe local fallback answer.

## Delivery

```powershell
docker compose up --build
```

Run Compose with an environment file containing `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and a `DATABASE_URL` that uses the Compose hostname `postgres` (not `localhost`). This production container serves the API on port 8000. Place a reverse proxy such as Caddy, Nginx, or a cloud load balancer in front of it for TLS and static-file delivery.
