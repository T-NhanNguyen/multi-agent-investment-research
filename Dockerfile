FROM python:3.11-slim

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y wget ca-certificates && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and Firefox
RUN playwright install firefox && playwright install-deps firefox

# Copy application code
COPY *.py ./
COPY agent-definition-files/ ./agent-definition-files/
COPY scrapers/ ./scrapers/
COPY browser_automation/ ./browser_automation/

# Create output and cache directories
RUN mkdir -p /app/output /app/cache /app/scraped_data /app/scrapers/browser_profile/firefox

ENV PYTHONUNBUFFERED=1

# Run the FastAPI server
CMD ["python", "api_server.py"]