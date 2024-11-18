FROM python:3.9.0

WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn","--worker-class=gevent", "--workers=9", "--max-requests=150", "--max-requests-jitter=15", "--timeout", "550", "routes:app", "--bind", "0.0.0.0:5000"]
