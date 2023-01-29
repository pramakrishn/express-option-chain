from expressoptionchain.option_stream import OptionStream
from expressoptionchain.helper import get_secrets
from expressoptionchain.option_chain import OptionChainFetcher

# the option stream start should be in main module
if __name__ == '__main__':

    # by default secrets are fetched from ~/.kite/secrets
    secrets = get_secrets() # or get_secrets(filename)

    # or
    # secrets = {
    #     'api_key': 'your_api_key',
    #     'api_secret': 'your_api_secret',
    #     'access_token': 'generated_access_token'
    # }

    # there is no limit on the number of symbols to subscribe to
    symbols = ['NFO:HDFCBANK', 'NFO:INFY', 'NFO:RELIANCE', 'NFO:DRREDDY', 'NFO:EICHERMOT']
    # symbols = ['CDS:EURINR', 'CDS:GBPINR', 'CDS:JPYINR', 'CDS:USDINR', 'BCD:EURINR']
    # symbols = ['MCX:GOLD', 'MCX:GOLDM', 'MCX:NATURALGAS', 'MCX:NICKEL', 'MCX:SILVER', 'MCX:SILVERM']

    stream = OptionStream(symbols, secrets, expiry='23-02-2023')

    # start the stream in a background thread
    # start will return once the subscription is started and the first ticks are received
    # this usually takes 20 sec.

    # By default, threaded=False. This allows you to run this process in foreground while you fetch the option chain
    # somewhere else.
    stream.start(threaded=True)

    # start fetching option chain
    option_chain_fetcher = OptionChainFetcher()

    # option chain for each trading symbol can be fetched in 3 ms
    option_chain = option_chain_fetcher.get_option_chain('NFO:HDFCBANK')

    # fetch option chain in bulk
    option_chains = option_chain_fetcher.get_option_chains(
        ['NFO:HDFCBANK', 'NFO:INFY', 'NFO:RELIANCE', 'NFO:DRREDDY', 'NFO:EICHERMOT'])
    # do some processing here
    pass
