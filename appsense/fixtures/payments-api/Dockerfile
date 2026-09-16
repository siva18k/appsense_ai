FROM python:3.12-slim
WORKDIR /app
COPY . .
EXPOSE 8080
CMD ["uvicorn", "payments.api:app", "--host", "0.0.0.0", "--port", "8080"]
