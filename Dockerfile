FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Release verification (Session 6): deploy.yml passes the just-pulled SHA;
# /api/v1/health reports it so the deploy can assert the NEW code is serving.
ARG GIT_SHA=unknown
ENV RELEASE_SHA=$GIT_SHA
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 curl && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 statmind
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=statmind:statmind . .
RUN mkdir -p /app/data /tmp/statmind_reports && chown -R statmind:statmind /app/data /tmp/statmind_reports
USER statmind
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 CMD curl -f http://localhost:8000/api/v1/health || exit 1
CMD ["python", "-m", "gunicorn", "main:app", "--workers", "2", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info"]