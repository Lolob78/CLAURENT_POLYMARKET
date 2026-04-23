FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl git gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry config virtualenvs.create false && poetry install --no-root

RUN playwright install chromium --with-deps

COPY . .

VOLUME ["/app/data"]

CMD ["python", "scripts/run_24_7_paper_bot.py"]