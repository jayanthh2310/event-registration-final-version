FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY app.py .
COPY static ./static
ENV DB_PATH=/data/registrations.db
RUN mkdir -p /data
VOLUME /data
EXPOSE 8000
# A single worker keeps this small SQLite demo simple; the DB transaction protects seat allocation.
CMD ["gunicorn", "-w", "1", "--threads", "8", "-b", "0.0.0.0:8000", "app:app"]
