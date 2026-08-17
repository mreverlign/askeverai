FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir -r requirements.txt


RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

ENV HF_HUB_OFFLINE=1

COPY main.py llm_client.py user_database.py app_rag_enhanced.py ./
COPY src ./src
COPY scripts ./scripts

RUN mkdir -p /app/data/indices/rag_indices

EXPOSE 8000

CMD ["python", "main.py"]
