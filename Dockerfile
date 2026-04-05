FROM python:3.11-slim

# Install system dependencies for Chromium
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

COPY tracker.py .

CMD ["python", "tracker.py"]