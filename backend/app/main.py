import os
from fastapi import FastAPI, HTTPException
from psycopg import connect
from redis import Redis

app = FastAPI(title='Tourgull API', version='0.1.0')

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'tourgull-api'}

@app.get('/ready')
def ready():
    try:
        with connect(os.environ['DATABASE_URL'], connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
                cur.fetchone()
        client = Redis.from_url(os.environ['REDIS_URL'], socket_connect_timeout=3)
        client.ping()
    except (Exception, KeyError) as exc:
        raise HTTPException(status_code=503, detail='Dependencies unavailable') from exc
    return {'status': 'ready'}
