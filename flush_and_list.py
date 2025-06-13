from redis_client import get_redis_client

r = get_redis_client()

print("Before flush:", r.keys())
r.flushall()
print("After flush:", r.keys())
