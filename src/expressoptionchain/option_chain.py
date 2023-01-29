import json
import logging
from collections import defaultdict

from expressoptionchain import helper, redis_helper
from expressoptionchain.kite_connector import KiteConnector
from expressoptionchain.redis_helper import RedisConfig

log = logging.getLogger(__name__)


class OptionChainFetcher:
    """
    This class is used to fetch the option chain and is exposed to the clients.
    """

    def __init__(self, redis_config: RedisConfig = RedisConfig()):
        self.db = redis_helper.get_redis_instance(redis_config)
        pass

    def get_option_chain(self, trading_symbol: str) -> dict:
        """
        gets the option chain of a trading symbol
        :param trading_symbol: in the format exchange:trading symbol
        :return: option chain
        """
        option_chain = helper.get_hash_value(self.db, 'option_chain', trading_symbol)
        if not option_chain:
            raise Exception(f'Option chain of {trading_symbol} not found')
        return option_chain

    def get_option_chains(self, trading_symbols: list[str]) -> list[dict]:
        """
        gets the list of option chain of the trading symbols passed
        :param trading_symbols: list of trading symbols in the format exchange:trading symbol
        :return: list of option chain
        """
        option_chain_list = []
        for trading_symbol in trading_symbols:
            option_chain_list.append(self.get_option_chain(trading_symbol))
        return option_chain_list


class OptionChainCreator:
    def __init__(self, kite_secrets, redis_config: RedisConfig = RedisConfig()):
        self.db = redis_helper.get_redis_instance(redis_config)
        self.kite_connector = KiteConnector(kite_secrets)

    def create_option_chain(self, trading_symbol: str, expiry: str) -> None:
        """
        Creates an option chain for the given trading symbol with the specified expiry date and stores it in
        the database.

        :param trading_symbol: trading symbol of format 'exchange:trading_symbol' E.g NFO:HDFCBANK, MCX:SILVER
        :param expiry: date of option expiry in dd-mm-yyy format
        :return: None
        """
        # option token info will be created in the instrument manager for all the options
        option_token_info = helper.get_hash_value(self.db, 'option_token_info', trading_symbol)
        if not option_token_info:
            log.error(f'Option token info of {trading_symbol} not found. Is instrument manager updated? ')
            return
        if not expiry in option_token_info:
            log.error(f'Expiry {expiry} of {trading_symbol} not found in option token info')
            return

        '''
        Option token info looks like this
        {
            "23-02-2023": [
                {
                    "token": 20592386,
                    "exchange_token": "80439",
                    "exchange": "NFO",
                    "trading_symbol": "HDFCBANK23FEB1360CE",
                    "name": "HDFCBANK",
                    "expiry": "23-02-2023",
                    "strike_price": 1360.0,
                    "tick_size": 0.05,
                    "lot_size": 550,
                    "instrument_type": "CE",
                    "segment": "NFO"
                },.. ]}
        '''
        list_of_token_info = option_token_info[expiry]
        if not list_of_token_info:
            log.error(f'Token info not found inside hash of {trading_symbol}:{expiry}')
            return

        # strike_price_instrument_type_map is a map of strike price to the map of instrument type
        # E.g. m = {150: {'ce': tick1, 'pe': tick2 }}
        strike_price_instrument_type_map = defaultdict(dict)
        option_chain = {}
        for token_info in list_of_token_info:
            if not option_chain:
                option_chain = self.get_option_chain_base(token_info, expiry)

            token = token_info['token']
            tick = helper.get_hash_value(self.db, 'ticks', str(token))
            if not tick:
                # tick could be missing because of criteria filters
                # hence error is not being thrown here
                # log.debug(f'tick not found for {token_info}')
                continue

            instrument_type = token_info['instrument_type'].lower()
            strike_price = token_info['strike_price']
            strike_price_instrument_type_map[strike_price][instrument_type] = self.get_option_detail(tick)

        list_of_options = []
        for strike_price, instrument_type_to_tick_map in strike_price_instrument_type_map.items():
            option = {
                'strike_price': strike_price
            }
            if instrument_type_to_tick_map.get('ce'):
                option['ce'] = instrument_type_to_tick_map.get('ce')
            if instrument_type_to_tick_map.get('pe'):
                option['pe'] = instrument_type_to_tick_map.get('pe')
            list_of_options.append(option)

        option_chain['expiry'][expiry] = sorted(list_of_options, key=lambda x: x['strike_price'])
        self.db.hset('option_chain', trading_symbol, json.dumps(option_chain))

    @staticmethod
    def get_option_detail(tick):
        bid = tick['depth']['buy']
        ask = tick['depth']['sell']
        # Option detail object returned contains all the attributes present in the tick
        # sent by websocket
        return {
            'bid_quantity': bid[0]['quantity'],
            'bid_price': bid[0]['price'],
            'ask_quantity': ask[0]['quantity'],
            'ask_price': ask[0]['price'],
            'premium': tick['last_price'],
            'last_trade_time': tick['last_trade_time'],
            'exchange_timestamp': tick['exchange_timestamp'],
            'last_traded_quantity': tick['last_traded_quantity'],
            'change': tick['change'],
            'oi': tick['oi'],
            'oi_day_high': tick['oi_day_high'],
            'oi_day_low': tick['oi_day_low'],
            'total_buy_quantity': tick['total_buy_quantity'],
            'ohlc': tick['ohlc'],
            'total_sell_quantity': tick['total_sell_quantity'],
            'volume': tick['volume_traded'],
            'bid': bid,
            'ask': ask,
            'tradable': tick['tradable'],
            'depth': tick['depth'],
            'instrument_token': tick['instrument_token']
        }

    def get_option_chain_base(self, token_info, expiry):
        # todo add underlying_value
        exchange = token_info['exchange']
        trading_symbol = token_info['name']
        return {
            'trading_symbol': trading_symbol,
            'exchange': exchange,
            'segment': token_info['segment'],
            'underlying_value': self.get_underlying_value(exchange, trading_symbol),
            'expiry': {expiry: []},
            'source': 'kite_api',
            'lot_size': token_info['lot_size'],
            # 'strike_price_gap': -1,
            # 'atm_option_strike_price': -1
        }

    def get_underlying_value(self, exchange, trading_symbol):
        # fetch the underlying asset value of non index equity assets
        if exchange != 'NFO' or 'NIFTY' in trading_symbol:
            return None
        key = f'NSE:{trading_symbol}'
        ltp = self.db.hget('ltp', key)
        if not ltp:
            log.error(f'could not fetch ltp of symbol {key}')
            return None
        return float(ltp)

