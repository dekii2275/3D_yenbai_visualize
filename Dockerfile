FROM python:3.12-alpine
WORKDIR /app
COPY web/ ./web/
EXPOSE 8000
USER 65534:65534
CMD ["python", "-m", "http.server", "8000", "--bind", "0.0.0.0", "--directory", "web"]
