FROM python:3.9.0

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# for installing libreoffice if in future a need for ppt or doc support or libreoffice is required (pptx and docx works without this libreoffice dependancy)
# RUN apt-get update && \
#     apt-get install -y --no-install-recommends libreoffice && \
#     rm -rf /var/lib/apt/lists/*

# nstall gdown to download from Google Drive
RUN pip install gdown

#Download the gzipped model files using gdown
RUN gdown "https://drive.google.com/uc?export=download&id=14Qt_Bldxsg_aNmdCNfPhau0DyrP4jkXm" -O whisper_local.tar.gz \
    && gdown "https://drive.google.com/uc?export=download&id=1_UYjykqoaZZ5W-C-KkrLsh_H_O9BqI6Z" -O embed_local.tar.gz

# unzip the model files and move them to their respective directories
RUN mkdir -p /app/whisper_local /app/embed_local \
    && tar -xvzf whisper_local.tar.gz -C /app/whisper_local --strip-components=1 \
    && tar -xvzf embed_local.tar.gz -C /app/embed_local --strip-components=1

# cleaning up the tar.gz files
RUN rm whisper_local.tar.gz embed_local.tar.gz

COPY . .

EXPOSE 5000

CMD ["gunicorn","--worker-class=gevent", "--workers=5", "--max-requests=200", "--max-requests-jitter=20", "--timeout", "550", "routes:app", "--bind", "0.0.0.0:5000"]
# Old command 18 Nov:
#CMD ["gunicorn", "--workers=4", "--timeout", "600", "routes:app", "--bind", "0.0.0.0:5000"]
