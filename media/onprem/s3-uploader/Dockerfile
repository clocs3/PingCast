FROM python:3.12.4-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN adduser -D -u 10001 appuser

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --no-compile -r /app/requirements.txt

COPY uploader.py /app/uploader.py

USER 10001

ENTRYPOINT ["python", "/app/uploader.py"]
