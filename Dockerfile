ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:0.6-python${PYTHON_VERSION}-alpine AS builder
WORKDIR /app

RUN apk add --no-cache postgresql-dev

COPY uv.lock .
COPY pyproject.toml .

RUN uv sync --no-dev

FROM python:${PYTHON_VERSION}-alpine

WORKDIR /app

RUN apk add --no-cache postgresql-libs

ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=71b0d58cc53f6bd72cf2f293e09e294b79c666d8

RUN wget -qO /usr/local/bin/supercronic "$SUPERCRONIC_URL" \
 && echo "${SUPERCRONIC_SHA1SUM}  /usr/local/bin/supercronic" | sha1sum -c - \
 && chmod +x /usr/local/bin/supercronic

COPY --from=builder /app/.venv /app/.venv

ENV PATH=/app/.venv/bin:$PATH

COPY . .

CMD echo "${CRON:-0 0 * * *} /app/cleanmedia.py ${CLEANMEDIA_OPTS:-c /etc/dendrite/dendrite.yaml -t 30 -n -l}" > /app/crontab && \
    /usr/local/bin/supercronic /app/crontab
