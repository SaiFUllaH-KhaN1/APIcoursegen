# Dockerfile example
FROM python:3.9.0
ARG OPENAI_API_KEY
ARG GOOGLE_API_KEY
ARG BASIC_AUTH_USERNAME
ARG BASIC_AUTH_PASSWORD
ARG SECRET_KEY

ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ENV GOOGLE_API_KEY=${GOOGLE_API_KEY}
ENV BASIC_AUTH_USERNAME=${BASIC_AUTH_USERNAME}
ENV BASIC_AUTH_PASSWORD=${BASIC_AUTH_PASSWORD}
ENV SECRET_KEY=${SECRET_KEY}

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "--worker-class=gevent", "--worker-connections=1000", "--workers=4", "--timeout", "600", "routes:app", "--bind", "0.0.0.0:5000"]
