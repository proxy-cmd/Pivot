FROM node:22-alpine AS web
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 pivot && mkdir -p /tmp/pivot && chown -R pivot:pivot /app /tmp/pivot
COPY --chown=pivot:pivot backend ./backend
COPY --chown=pivot:pivot alembic ./alembic
COPY --chown=pivot:pivot alembic.ini ./alembic.ini
COPY --chown=pivot:pivot --from=web /app/dist ./public
USER pivot
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
