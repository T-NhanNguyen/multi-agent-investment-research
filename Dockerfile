FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and Docker CLI
RUN apt-get update && apt-get install -y \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Copy application code
COPY multi_agent_investment.py .
COPY api_server.py .
COPY monitoring_wrapper.py .
COPY agent-definition-files/ ./agent-definition-files/

# Create output directory
RUN mkdir -p /app/output

ENV PYTHONUNBUFFERED=1

CMD ["python", "multi_agent_investment.py"]