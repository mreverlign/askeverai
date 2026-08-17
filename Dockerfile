FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py llm_client.py user_database.py app_rag_enhanced.py ./
COPY src ./src
COPY scripts ./scripts

RUN mkdir -p /app/data/indices/rag_indices

EXPOSE 8000

CMD ["python", "main.py"]
