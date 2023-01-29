from expressoptionchain.option_chain import OptionChainFetcher

option_chain_fetcher = OptionChainFetcher()

# option chain for each trading symbol can be fetched in 3 ms
option_chain = option_chain_fetcher.get_option_chain('NFO:HDFCBANK')

while True:
    option_chains = option_chain_fetcher.get_option_chains(
        ['NFO:HDFCBANK', 'NFO:INFY', 'NFO:RELIANCE', 'NFO:DRREDDY', 'NFO:EICHERMOT'])
    # do some processing on option chains
    break