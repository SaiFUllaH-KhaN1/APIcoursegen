FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# unzip the model files and move them to their respective directories
RUN mkdir -p /app/whisper_local /app/embed_local

COPY . .

EXPOSE 5000

CMD ["gunicorn","--worker-class=uvicorn.workers.UvicornWorker","--workers=5","--timeout=550","--max-requests=200","--max-requests-jitter=20","--bind","0.0.0.0:5000","routes:app"]
# Old command 18 Nov:
#CMD ["gunicorn", "--workers=4", "--timeout", "600", "routes:app", "--bind", "0.0.0.0:5000"]
