import os
import ssl
import redis
from redis.connection import SSLConnection, ConnectionPool
from urllib.parse import urlparse
from pathlib import Path

def get_redis_client():
    redis_url = os.getenv("REDIS_TLS_URL", os.getenv("REDIS_URL"))
    if not redis_url:
        raise RuntimeError("REDIS_TLS_URL or REDIS_URL must be set")

    u = urlparse(redis_url)
    ca_file = Path(__file__).parent / "certs" / "heroku-redis-server.pem"

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.load_verify_locations(cafile=str(ca_file))

    pool = ConnectionPool(
        host=u.hostname,
        port=u.port or 6379,
        db=int(u.path.lstrip("/")) if u.path else 0,
        password=u.password,
        connection_class=SSLConnection,
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        ssl_ca_certs=str(ca_file),
        decode_responses=False,
    )

    return redis.Redis(connection_pool=pool)
