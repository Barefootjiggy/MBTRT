from redis_client import get_redis_client

r = get_redis_client()
print("Session keys in Redis:")
for key in r.keys():
    print("-", key)
