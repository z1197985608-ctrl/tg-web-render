FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY main.py ./

EXPOSE 10000

# This is a Pyrogram userbot plus HTTP health server, not a WSGI app.
# Do not replace this with gunicorn.
CMD ["python", "main.py"]
