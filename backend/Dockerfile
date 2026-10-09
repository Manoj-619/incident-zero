FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home incident && mkdir /state && chown incident /state
COPY app ./app
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 DATABASE_PATH=/state/incident-zero.sqlite3
USER incident
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--limit-concurrency", "32"]
