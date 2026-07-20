FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY kalshi_agent/ kalshi_agent/
COPY scheduler.py profit_check.py ./

ENV KALSHI_DATA_DIR=/data
CMD ["python", "-u", "scheduler.py"]
