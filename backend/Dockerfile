FROM conzilla/acestream:latest

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    ffmpeg curl ca-certificates procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /backend

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

COPY app/ app/

EXPOSE 8001 6878

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
