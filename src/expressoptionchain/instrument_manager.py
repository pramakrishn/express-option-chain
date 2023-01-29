import datetime
import functools
import json
import logging
from datetime import date, datetime

import redis

from expressoptionchain import helper
from expressoptionchain import redis_helper
from expressoptionchain.exceptions import KiteInstrumentManagerException
from expressoptionchain.kite_connector import KiteConnector

log = logging.getLogger(__name__)


class KiteInstrumentManager:
    """
    This class parses the all the instruments, processes it and stores it in the database
    """
    # redis db initialization
    db = None

    def __init__(self, secrets: dict, redis_instance):
        KiteInstrumentManager.db = redis_instance
        self.connector = KiteConnector(secrets)
        self.fetch_instruments()
        self.fetch_ltp()
        self.save_last_fetch_time()

    def fetch_instruments(self) -> None:
        log.info('Fetching instruments')
        self.instruments = self.connector.kite_client.instruments()

    def fetch_ltp(self):
        """
        Fetch ltp of the underlying non index equity options. It can be used for filtering the options and also
        setting the underlying price in the option chain.
        :return:
        """
        nse_symbols = set()
        for item in self.instruments:
            segment = item['segment']
            # filter non index equity options only
            if 'NFO' in segment and 'NIFTY' not in item['name']:
                nse_symbols.add(f'NSE:{item["name"]}')
        log.info(f'Found {len(nse_symbols)} nse symbols')
        ltp_map = self.fetch_ltp_map(list(nse_symbols), throw_exception_on_symbols_mismatch=False)
        for trading_symbol, ltp in ltp_map.items():
            KiteInstrumentManager.db.hset('ltp', trading_symbol, ltp['last_price'])
        log.info('Finished updating ltp')

    def fetch_ltp_map(self, trading_symbols, throw_exception_on_symbols_mismatch=True):
        ltp_map = self.connector.get_ltp(trading_symbols)
        symbols_without_otp = set(trading_symbols) - set(ltp_map.keys())
        if symbols_without_otp:
            if symbols_without_otp:
                # index options will not have ltp
                error_msg = f'Could not fetch ltp of symbols {symbols_without_otp}'
                if throw_exception_on_symbols_mismatch:
                    raise KiteInstrumentManagerException(error_msg)
                else:
                    log.debug(error_msg)
        return ltp_map

    def process_instruments(self) -> None:
        """
        This method
        1. Creates a redis has option_token_info that maps the `exchange:trading_symbol` to the list of its
        Option token info looks like this
        'NSE:HDFCBANK': {
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
                    },
                    .. ],
                   "25-03-2023": [..]
                }
        2. Stores the ltp of underlying equity stocks in the hash ltp
        'NSE:HDFCBANK': 1653
        3. Stores the valid expiry dates in the set 'valid_option_expiry'
        :return: None
        """

        # map of trading_symbol to its option token info
        trading_symbol_to_expiry_map = {}
        # 'NFO:HDFCBANK' : {"23-02-2023": [ { "token": 20592386, .. }],
        # "25-03-2023": [ { "token": 20592386, .. }] }

        valid_expiry = set()
        for item in self.instruments:
            exchange = item['exchange']
            segment = item['segment']
            trading_symbol = item['name']
            key = f'{exchange}:{trading_symbol}'
            instrument_info = KiteInstrumentManager.get_instrument_info(item)

            if 'OPT' in segment:
                expiry = KiteInstrumentManager.get_expiry(item['expiry'])
                valid_expiry.add(expiry)
                expiry_to_info_list_map = trading_symbol_to_expiry_map.get(
                    key)  # "23-02-2023": [ { "token": 20592386, .. }]
                if not expiry_to_info_list_map:
                    expiry_to_info_list_map = {expiry: [instrument_info]}
                    trading_symbol_to_expiry_map[key] = expiry_to_info_list_map
                else:
                    instrument_info_list = expiry_to_info_list_map.get(
                        expiry)  # [ { "token": 20592386, .. }, { "token": 20592388, .. }]
                    if not instrument_info_list:
                        expiry_to_info_list_map[expiry] = [instrument_info]
                    else:
                        instrument_info_list.append(instrument_info)

        # save the valid expiry dates for future validation checks
        KiteInstrumentManager.db.delete('valid_option_expiry')
        KiteInstrumentManager.db.sadd('valid_option_expiry', *map(str, valid_expiry))

        KiteInstrumentManager.db.delete('option_token_info')
        for key, expiry_to_info_list_map in trading_symbol_to_expiry_map.items():
            for expiry, instrument_info_list in expiry_to_info_list_map.items():
                # sort the option token list based on the strike price
                expiry_to_info_list_map[expiry] = sorted(instrument_info_list, key=functools.cmp_to_key(
                    KiteInstrumentManager.strike_price_comparator))
            KiteInstrumentManager.db.hset('option_token_info', key, json.dumps(expiry_to_info_list_map))

    @staticmethod
    def strike_price_comparator(x1, x2):
        # if strike prices are same, ce comes prior to pe
        if x1['strike_price'] == x2['strike_price']:
            if x1['instrument_type'].lower() == 'ce':
                return -1
            else:
                return 1
        return x1['strike_price'] - x2['strike_price']

    @staticmethod
    def get_instrument_info(item):
        """
        E.g. {
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
                }
        """
        return {'token': int(item['instrument_token']),
                'exchange_token': item['exchange_token'],
                'exchange': item['exchange'],
                'trading_symbol': item['tradingsymbol'],
                'name': item['name'],
                'expiry': KiteInstrumentManager.get_expiry(item['expiry']),
                'strike_price': item['strike'],
                'tick_size': item['tick_size'],
                'lot_size': item['lot_size'],
                'instrument_type': item['instrument_type'],
                'segment': item['segment'],
                }

    @staticmethod
    def get_expiry(expiry):
        if isinstance(expiry, date):
            return expiry.strftime('%d-%m-%Y')

    def save_last_fetch_time(self):
        current_time = datetime.now()
        last_fetch_time = current_time.strftime("%d-%m-%Y %H:%M:%S")
        config = {
            'instrument_last_fetch_time': last_fetch_time
        }
        self.db.set('option_chain_config', json.dumps(config))

class KiteInstrumentFetcher:

    def __init__(self, secrets, redis_config: redis_helper.RedisConfig = redis_helper.RedisConfig()):
        self.db = redis_helper.get_redis_instance(redis_config)

    def get_tokens(self, trading_symbols, expiry, criteria) -> list[int]:
        '''
        this method returns all the instrument tokens available for the underlying trading symbol after applying the
        criteria filter
        :param trading_symbols: trading symbol in the format exchange:trading_symbol
        :param expiry: format is dd-mm-yyyy
        :param criteria: Criteria to filter the options. Right now, only percentage criteria is supported.
        The percentage criteria filters out options with strike prices that are more than a specified value away
        from the current spot price. This helps to reduce the number of tokens while subscribing to all the equity options.
        E.g. {'name': 'percentage', 'properties': {'value': 12.5}}
        :return:
        '''
        if not criteria:
            log.debug('No criteria found. Returning all tokens.')
            all_tokens = []
            for trading_symbol in trading_symbols:
                all_tokens.extend(self.get_token_info_for_trading_symbol(trading_symbol, expiry))
            return all_tokens

        if criteria['name'] == 'percentage':
            '''
            The percentage criteria filters out options with strike prices that are more than a specified value away
            from the current spot price. This helps to reduce the number of tokens while subscribing to 
            all the equity options. Currently, only the equity options are supported. Indices are not supported. 
            E.g. criteria = {'name': 'percentage', 'properties': {'value': 10}}
            Here all the options which are 10% away from the spot price of the underlying stock are filtered out. 
            '''
            log.info(f'Found percentage criteria: criteria {criteria}')
            all_tokens = []
            percent_value = criteria['properties']['value']
            for trading_symbol in trading_symbols:
                if 'NFO' not in trading_symbol:
                    # non equity options are not supported yet
                    all_tokens.extend(
                        self.get_token_info_for_trading_symbol(trading_symbol, expiry))
                    log.debug('trading symbol does not have nfo, hence adding all tokens')
                    continue

                expiry_to_token_info_map = helper.get_hash_value(self.db, 'option_token_info', trading_symbol)
                if expiry not in expiry_to_token_info_map:
                    raise KiteInstrumentManagerException(
                        f'Expiry {expiry} token info not found for symbol {trading_symbol}')
                nse_symbol = trading_symbol.replace('NFO', 'NSE')
                ltp = self.db.hget('ltp', nse_symbol)
                if not ltp:
                    # index options won't have ltp
                    if 'NIFTY' not in nse_symbol.upper():
                        log.error(
                            f'trading symbol {nse_symbol} does not have ltp, len: {len(self.get_token_info_for_trading_symbol(trading_symbol, expiry))}')
                    all_tokens.extend(
                        self.get_token_info_for_trading_symbol(trading_symbol, expiry))
                    continue
                ltp = float(ltp)
                token_info_list = expiry_to_token_info_map[expiry]
                otm_strike_price = KiteInstrumentFetcher.first_otm_strike_price(token_info_list, ltp)
                new_tokens = []
                for token_info in token_info_list:
                    # gap indicates how much away is the strike price from underlying spot price
                    gap = abs(otm_strike_price - token_info['strike_price']) / otm_strike_price * 100
                    if gap <= percent_value:
                        new_tokens.append(token_info['token'])
                log.debug(
                    f'%criteria: {trading_symbol}: added {len(new_tokens)} instead of {len(self.get_token_info_for_trading_symbol(trading_symbol, expiry))}')
                all_tokens.extend(new_tokens)

            return all_tokens

    def get_token_info_for_trading_symbol(self, trading_symbol, expiry) -> list[int]:
        """
        This method fetches the instrument tokens of all the options of the trading symbol
        :param trading_symbol: format is i.e. exchange:trading symbol
        :param expiry: format is dd-mm-yyyy
        :return: returns a list of option tokens of the trading symbol
        """
        expiry_to_token_info_map = helper.get_hash_value(self.db, 'option_token_info', trading_symbol)
        if not expiry_to_token_info_map:
            log.error(f'option token not found for {trading_symbol}')
            if 'NSE' in trading_symbol:
                raise KiteInstrumentManagerException(f'{trading_symbol} should be prefixed with NSE and not NFO')
            else:
                raise KiteInstrumentManagerException(f'option token not found for {trading_symbol}. Is the trading'
                                                     f'symbol right?')
        if not expiry in expiry_to_token_info_map:
            log.error(f'expiry {expiry} not found in option token info of {trading_symbol}')
            raise KiteInstrumentManagerException(f'expiry {expiry} does not exist for {trading_symbol}, '
                                                 f'Valid options are {list(expiry_to_token_info_map.keys())}')
        list_of_options = expiry_to_token_info_map[expiry]

        tokens = []
        for option in list_of_options:
            tokens.append(option['token'])
        return tokens

    @staticmethod
    def first_otm_strike_price(token_info_list, ltp):
        for token_info in token_info_list:
            if token_info['strike_price'] >= ltp:
                return token_info['strike_price']
        return token_info_list[-1]['strike_price']


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s.%(msecs)03d %(name)s:%(funcName)s - %(processName)s -%(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    log = logging.getLogger(__name__)

    secrets = helper.get_secrets()
    redis_instance = redis.StrictRedis(decode_responses=True, db=0)
    instrument_parser = KiteInstrumentManager(secrets, redis_instance)
    instrument_parser.process_instruments()
