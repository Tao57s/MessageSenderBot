FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 app \
	&& mkdir -p /app/data /app/logs \
	&& chown -R app:app /app

COPY --chown=app:app . .
USER app

CMD ["python", "Run.py"]
