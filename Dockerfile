FROM python:3.11.9-slim

WORKDIR /app

COPY . /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev libpq5 \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc libc6-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && python -c "import psycopg2; print('psycopg2', psycopg2.__version__)" \
    && python -m unittest -q test_runtime_security

EXPOSE 10000

CMD ["sh", "-c", "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0"]
