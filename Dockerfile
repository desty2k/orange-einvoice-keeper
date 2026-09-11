# syntax=docker/dockerfile:1.7
FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

WORKDIR /app

# This layer changes only when pinned runtime dependencies change. The BuildKit cache
# speeds a cold dependency-layer rebuild without adding pip files to the final image.
COPY requirements.txt ./
RUN --mount=type=cache,id=orange-einvoice-pip,target=/root/.cache/pip \
    pip install --cache-dir /root/.cache/pip -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
# Dependencies were installed above; source-only changes therefore avoid resolution/downloads.
RUN --mount=type=cache,id=orange-einvoice-pip,target=/root/.cache/pip \
    pip install --no-build-isolation --no-deps .

ENV PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8080
ENTRYPOINT ["orange-einvoice"]
CMD ["run"]
