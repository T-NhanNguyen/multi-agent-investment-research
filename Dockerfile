FROM python:3.11-slim

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./
COPY agent-definition-files/ ./agent-definition-files/
COPY scrapers/ ./scrapers/

# Create output and cache directories
RUN mkdir -p /app/output /app/cache

ENV PYTHONUNBUFFERED=1

# Run the FastAPI server
CMD ["python", "api_server.py"]