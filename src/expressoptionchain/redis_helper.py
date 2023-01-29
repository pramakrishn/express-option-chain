import redis


class RedisConfig:
    def __init__(self, port=6379, db=0):
        self.db = db
        self.port = port


def get_redis_instance(redis_config: RedisConfig = RedisConfig()):
    r = redis.StrictRedis(decode_responses=True, port=redis_config.port, db=redis_config.db)
    try:
        r.ping()
    except:
        raise Exception(f'Redis is not running port {redis_config.port} ')
    return r
