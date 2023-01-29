# Express Option Chain - Option Chain Stream for Indian Stock Market built with Kite APIs

This library utilizes Kite Connect APIs to fetch the Option Chain of all the derivatives traded in the Indian stock market. With support for all exchanges, including NFO, MCX, CDS, and BCD, comprehensive option chain data can be streamed effortlessly in real-time. The library provides a convenient API to fetch the option chain of the assets.

Some major features are

* ✅ Light weight
* ⚡️ Optimized for speed - Uses parallel connections through Python Multiprocessing
* 📈 Supports subscribing to all the derivatives across all exchanges (NFO for equity, MCX, CDS, BCD) in a single API
* ⏱️ No considerable difference in execution time even when subscribed to all the symbols present in Indian exchanges -
  Uses cache wherever possible to eliminate network calls
* 📊 Filters to remove unwanted options
* 💡 Option chain is enriched by additional data like underlying asset price, lot size etc.
* 🔧 Installable via pip

## Prerequisites

This tool requires basic understanding
of [the working of kite websockets](https://kite.trade/docs/connect/v3/websocket/).

You will also need

1. Working [redis database](https://redis.io/)
2. [Kite developer account](https://developers.kite.trade/) and application secrets (api_key and api_secret)

## Installation

Express option chain library can be installed with pip.

```shell
pip install --no-cache-dir --upgrade express-option-chain
```

or just clone this repo. 

## Usage

There are 2 main classes in this library. `OptionStream` to fetch and store the option chain in the database. `OptionChainFetcher` retrieves the stored option chain from the database.

Subscribing to the option chain stream requires you to pass the trading symbols you want to monitor and expiry date.
Trading symbol must be prefixed with the exchange to which the derivative belongs.
E.g. NFO:HDFCBANK, NFO:RELIANCE, MCX:CRUDEOIL, CDS:EURINR. 
By adding the symbol NFO:HDFCBANK, all the call and put options of NSE:HDFCBANK will be added to the option chain.

Note that All equity derivatives are present in NFO exchange.


## Basic example

Redis service should be running in your machine before following the next steps.

Running this code requires kite developer app secrets (API key, API secret and Access token).

Secrets can be provided

1. By placing the secrets json in the filepath `$HOME/.kite/secrets` by default or pass any filename to the get_secrets() method.
   The secrets json looks like this

```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "access_token": "generated_access_token"
}
```


2. By hard coding the secrets in the file

Here's a simple code snippet to get started: 

```python
from expressoptionchain.option_stream import OptionStream
from expressoptionchain.helper import get_secrets
from expressoptionchain.option_chain import OptionChainFetcher

# the option stream start should be in main module
if __name__ == '__main__':
    # by default secrets are fetched from ~/.kite/secrets
    secrets = get_secrets()  # or get_secrets(filename)

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

    # By default, threaded is False. This allows you to run this process in foreground while you fetch the option chain 
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
```

`start` method on the `OptionStream` class starts the process which subscribes to websockets, stores the quotes received and
creates the option chain.
By default, this is a blocking method call. This allows you to fetch the option chain in another process.

You can pass `threaded=True` to run the option stream in the background.

Ideally you don't want to fetch the option chain the same python module that you use to start the option stream.

### Fetching the option chain

Make sure you start the option stream process before you fetch the option chain to avoid receiving the outdated data. You can only get the option chain for the trading symbols subscribed to the `OptionStream`.

```python
from expressoptionchain.option_chain import OptionChainFetcher

option_chain_fetcher = OptionChainFetcher()

# option chain for each trading symbol can be fetched in 3 ms
option_chain = option_chain_fetcher.get_option_chain('NFO:HDFCBANK')

while True:
    option_chains = option_chain_fetcher.get_option_chains(
        ['NFO:HDFCBANK', 'NFO:INFY', 'NFO:RELIANCE', 'NFO:DRREDDY', 'NFO:EICHERMOT'])
    # do some processing on option chains
    break
```

**Option Chain Response:**

Example of option chain could be found [here](resources/hdfcbank_option_chain.json).

<details>
<summary>See the shortened response here. </summary>

```json
{
  "trading_symbol": "HDFCBANK",
  "segment": "NFO-OPT",
  "underlying_value": "1658.1",
  "expiry": {
    "23-02-2023": [
      {
        "strike_price": 1600.0,
        "ce": {
          "bid_quantity": 1650,
          "bid_price": 63.4,
          "ask_quantity": 550,
          "ask_price": 65.2,
          "premium": 65.0,
          "last_trade_time": "13-02-2023 10:59:43",
          "exchange_timestamp": "13-02-2023 12:57:46",
          "last_traded_quantity": 550,
          "change": 3.916866506794569,
          "oi": 398750,
          "oi_day_high": 430100,
          "oi_day_low": 398750,
          "total_buy_quantity": 73700,
          "ohlc": {
            "open": 60.0,
            "high": 66.4,
            "low": 52.6,
            "close": 62.55
          },
          "total_sell_quantity": 47300,
          "volume": 202400,
          "bid": [
            {
              "quantity": 1650,
              "price": 63.4,
              "orders": 3
            },
            {
              "quantity": 550,
              "price": 63.35,
              "orders": 1
            },
            {
              "quantity": 1100,
              "price": 63.3,
              "orders": 2
            },
            {
              "quantity": 550,
              "price": 63.15,
              "orders": 1
            },
            {
              "quantity": 550,
              "price": 62.7,
              "orders": 1
            }
          ],
          "ask": [
            {
              "quantity": 550,
              "price": 65.2,
              "orders": 1
            },
            {
              "quantity": 550,
              "price": 65.25,
              "orders": 1
            },
            {
              "quantity": 550,
              "price": 65.3,
              "orders": 1
            },
            {
              "quantity": 550,
              "price": 68.25,
              "orders": 1
            },
            {
              "quantity": 550,
              "price": 69.0,
              "orders": 1
            }
          ],
          "tradable": true,
          "depth": {
            "buy": [
              {
                "quantity": 1650,
                "price": 63.4,
                "orders": 3
              },
              {
                "quantity": 550,
                "price": 63.35,
                "orders": 1
              },
              {
                "quantity": 1100,
                "price": 63.3,
                "orders": 2
              },
              {
                "quantity": 550,
                "price": 63.15,
                "orders": 1
              },
              {
                "quantity": 550,
                "price": 62.7,
                "orders": 1
              }
            ],
            "sell": [
              {
                "quantity": 550,
                "price": 65.2,
                "orders": 1
              },
              {
                "quantity": 550,
                "price": 65.25,
                "orders": 1
              },
              {
                "quantity": 550,
                "price": 65.3,
                "orders": 1
              },
              {
                "quantity": 550,
                "price": 68.25,
                "orders": 1
              },
              {
                "quantity": 550,
                "price": 69.0,
                "orders": 1
              }
            ]
          },
          "instrument_token": 20601602
        },
        "pe": {
          "bid_quantity": 550,
          "bid_price": 4.55,
          "ask_quantity": 550,
          "ask_price": 4.7,
          "premium": 4.55,
          "last_trade_time": "13-02-2023 10:59:55",
          "exchange_timestamp": "13-02-2023 12:57:46",
          "last_traded_quantity": 550,
          "change": -12.500000000000005,
          "oi": 1410200,
          "oi_day_high": 1499850,
          "oi_day_low": 1408000,
          "total_buy_quantity": 151250,
          "ohlc": {
            "open": 5.05,
            "high": 6.0,
            "low": 4.25,
            "close": 5.2
          },
          "total_sell_quantity": 191950,
          "volume": 2049300,
          "bid": [
            {
              "quantity": 550,
              "price": 4.55,
              "orders": 1
            },
            {
              "quantity": 550,
              "price": 4.35,
              "orders": 1
            },
            {
              "quantity": 11550,
              "price": 4.3,
              "orders": 2
            },
            {
              "quantity": 2200,
              "price": 4.25,
              "orders": 3
            },
            {
              "quantity": 1100,
              "price": 4.2,
              "orders": 2
            }
          ],
          "ask": [
            {
              "quantity": 550,
              "price": 4.7,
              "orders": 1
            },
            {
              "quantity": 1100,
              "price": 4.75,
              "orders": 2
            },
            {
              "quantity": 550,
              "price": 4.8,
              "orders": 1
            },
            {
              "quantity": 1100,
              "price": 4.9,
              "orders": 1
            },
            {
              "quantity": 1100,
              "price": 5.0,
              "orders": 2
            }
          ],
          "tradable": true,
          "depth": {
            "buy": [
              {
                "quantity": 550,
                "price": 4.55,
                "orders": 1
              },
              {
                "quantity": 550,
                "price": 4.35,
                "orders": 1
              },
              {
                "quantity": 11550,
                "price": 4.3,
                "orders": 2
              },
              {
                "quantity": 2200,
                "price": 4.25,
                "orders": 3
              },
              {
                "quantity": 1100,
                "price": 4.2,
                "orders": 2
              }
            ],
            "sell": [
              {
                "quantity": 550,
                "price": 4.7,
                "orders": 1
              },
              {
                "quantity": 1100,
                "price": 4.75,
                "orders": 2
              },
              {
                "quantity": 550,
                "price": 4.8,
                "orders": 1
              },
              {
                "quantity": 1100,
                "price": 4.9,
                "orders": 1
              },
              {
                "quantity": 1100,
                "price": 5.0,
                "orders": 2
              }
            ]
          },
          "instrument_token": 20601858
        }
      },
      {
        "strike_price": 1650.0,
        "another_key": "and so on.. see the full response above"
      }
    ]
  },
  "source": "kite_api",
  "lot_size": 550
}
```

</details>

**Fields**

* Underlying value - Last day's market price of the underlying asset. This value is available only for non index equity
  options as of now.
* Rest of the fields - are self-explanatory

## Advanced Usage

### Filter out unwanted options

As of today, there are 217 underlying assets in Indian stock market across all the exchanges. It means we need to
subscribe to approximately 16,000 instrument tokens to fetch the data of all the options.

Kite websocket API
restricts the parallel connections to 3 and there could be a maximum of 3000 tokens per connection. Only 9000
tokens could be subscribed with a single access token. Hence, it's not possible to fetch quotes of all the tokens with the access token of just one application in Kite Connect.   

But most of the times, we will not be interested in deep ITM/OTM options which are
15% to 30% away from the spot price of the underlying asset as these options are highly illiquid or have no open
interest.

With the percentage filter, you can filter out these options. You can specify value in percentage. Any option whose
strike price is farther from the spot price by specified value will be filtered out.
Consider an example where the underlying asset say RELIANCE has a spot price of 1000 INR. If the percentage filter of
value 20 is applied, all the options whose strike price is greater than 1200 and lesser than 800 are removed from the option chain.

### Other features

- By default, db=0 (Database index) is selected in redis. You can change it by passing the RedisConfig instance. Make
  sure you pass the same configuration to OptionChainFetcher APIs if you use this configuration.

## Code describing the advanced usage

```python
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
```

## How does it work internally?

Kite Connect APIs provides Websockets API. It enables us to subscribe to individual options of the underlying asset.
Maximum of 3 websockets connections can be established and each connection can subscribe upto 3000 instrument tokens.

KiteInstrumentManager runs once a day during the first run of the option stream to fetch the instruments. Once the
OptionStream is instantiated with the underlying assets, the corresponding tokens are calculated.
Number of websocket connections are determined based on the size of the tokens with a limit of 3. Connections are
created within separate python processes. Quotes/ticks are obtained after the websocket connection is established. Ticks
are stored in redis hash. Storage of ticks is handled by separate worker threads. Another worker thread calculates the
option chain using the stored ticks.

OptionChainFetcher class provides an interface to fetch the quotes stored in the database.

## Contact

Feel free to contact me if you need any support regarding the usage of this library. If there are bugs, please create an
issue in GitHub.  