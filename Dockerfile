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
RUN poetry install --only main --no-interaction --no-ansi

FROM python:3.10-alpine

WORKDIR /app

RUN apk add --no-cache \
    postgresql-libs \
    libffi \
    libxml2 \
    libxslt \
    tzdata \
    dcron

COPY --from=builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
COPY --from=builder /app /app

ENV PYTHONPATH=/usr/local/lib/python3.10/site-packages

COPY . .

RUN echo -e "SHELL=/bin/sh\nPATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin\n" > /etc/crontabs/root

CMD echo "${CRON:-0 0 * * *} python /app/cleanmedia.py ${CLEANMEDIA_OPTS:--t 30}" >> /etc/crontabs/root && crond -f -l 2
