FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Спочатку метадані проєкту — для кешування шару із залежностями.
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install .

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY ui/ ./ui/
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
