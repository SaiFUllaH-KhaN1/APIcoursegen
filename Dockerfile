# Dockerfile example
FROM python:3.9.0

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "--worker-class=gevent", "--worker-connections=1000", "--workers=4", "--timeout", "600", "routes:app", "--bind", "0.0.0.0:5000"]
