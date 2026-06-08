FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd -r coreengine \
    && useradd -r -g coreengine -d /app -s /usr/sbin/nologin coreengine

COPY pyproject.toml README.md ./
COPY src/ src/
COPY migrations/ migrations/
COPY dashboard/ dashboard/
COPY onboarding/ onboarding/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

USER coreengine
EXPOSE 8000

CMD ["fgos", "api"]
