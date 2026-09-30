FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/.hf FASTEMBED_CACHE_PATH=/app/.fastembed
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# bake the embedding model into the image -> fast, offline cold start
RUN python -c "import os; from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir=os.environ['FASTEMBED_CACHE_PATH'])"
COPY app ./app
COPY data ./data
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=40s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
