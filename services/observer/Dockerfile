FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY observer_backend ./observer_backend
COPY frontend ./frontend
ENV PYTHONPATH=/app

CMD ["uvicorn", "observer_backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
