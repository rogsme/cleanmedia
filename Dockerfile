FROM python:3.10-alpine AS builder

WORKDIR /app

RUN apk add --no-cache \
    postgresql-dev \
    gcc \
    musl-dev \
    libffi-dev \
    curl \
    g++ \
    make \
    libxml2-dev \
    libxslt-dev \
    tzdata

RUN pip install --no-cache-dir poetry

RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-interaction --no-ansi --no-root

FROM python:3.10-alpine

WORKDIR /app

RUN apk add --no-cache \
    postgresql-libs \
    libffi \
    libxml2 \
    libxslt \
    tzdata \
    curl

ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=71b0d58cc53f6bd72cf2f293e09e294b79c666d8 \
    SUPERCRONIC=supercronic-linux-amd64

RUN curl -fsSLO "$SUPERCRONIC_URL" \
 && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
 && chmod +x "$SUPERCRONIC" \
 && mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" \
 && ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic

COPY --from=builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
COPY --from=builder /app /app

ENV PYTHONPATH=/usr/local/lib/python3.10/site-packages

COPY . .

CMD echo "${CRON:-0 0 * * *} python /app/cleanmedia.py ${CLEANMEDIA_OPTS:-c /etc/dendrite/dendrite.yaml -t 30 -n -l}" > /app/crontab && \
    /usr/local/bin/supercronic /app/crontab
