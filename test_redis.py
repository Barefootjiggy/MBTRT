# test_redis.py
import os
import ssl
import redis
from redis.connection import SSLConnection, ConnectionPool
from urllib.parse import urlparse
from pathlib import Path

# 1) Grab & parse the REDIS_URL (or REDIS_TLS_URL)
redis_url = os.getenv("REDIS_TLS_URL", os.getenv("REDIS_URL"))
if not redis_url:
    raise RuntimeError("Set REDIS_URL or REDIS_TLS_URL in your shell")

u = urlparse(redis_url)

# 2) Point at the PEM chain you exported earlier
ca_file = Path(__file__).parent / "certs" / "heroku-redis-server.pem"

# 3) Build an SSLContext that trusts system CAs + your server cert
ssl_ctx = ssl.create_default_context()  
ssl_ctx.load_verify_locations(cafile=str(ca_file))

# 4) Build a ConnectionPool that uses SSLConnection
pool = ConnectionPool(
    host=u.hostname,
    port=u.port or 6379,
    db=int(u.path.lstrip("/")) if u.path else 0,
    password=u.password,
    connection_class=SSLConnection,
    # **no** ssl=True here
    ssl_cert_reqs=ssl.CERT_REQUIRED,
    ssl_ca_certs=str(ca_file),
    decode_responses=True,
)

# 5) Spin up a client & ping
client = redis.Redis(connection_pool=pool)
print("Ping response:", client.ping())
