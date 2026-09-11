FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8080
ENTRYPOINT ["orange-einvoice"]
CMD ["run"]
