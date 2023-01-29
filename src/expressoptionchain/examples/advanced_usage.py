from expressoptionchain.option_stream import OptionStream
from expressoptionchain.helper import get_secrets
from expressoptionchain.redis_helper import RedisConfig

# the option stream start should be in main module
if __name__ == '__main__':
    secrets = get_secrets()

    symbols = ['NFO:HDFCBANK', 'NFO:INFY', 'NFO:RELIANCE', 'NFO:DRREDDY', 'NFO:EICHERMOT']

    # The percentage criteria filters out options with strike prices that are more than a specified value away
    # from the current spot price. In this example, percentage value is set to 12.5%.
    # By adding this criteria filter, it resolves to 262 tokens instead of 438 tokens if no filter was
    # applied
    criteria = {'name': 'percentage', 'properties': {'value': 12.5}}

    stream = OptionStream(symbols, secrets,
                          expiry='23-02-2023',
                          criteria=criteria,
                          redis_config=RedisConfig(db=1)
                          )
    stream.start()