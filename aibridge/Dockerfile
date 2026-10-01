FROM python:3.13-slim
COPY app.py /app/app.py
ENV AIBRIDGE_BASE_DIR=/data \
    AIBRIDGE_BIND=0.0.0.0 \
    AIBRIDGE_PORT=8097
VOLUME ["/data"]
EXPOSE 8097
CMD ["python3", "/app/app.py"]
