import json
import logging
import math
import threading
import time
from datetime import date, datetime
from multiprocessing import Process

from kiteconnect import KiteTicker

from expressoptionchain import helper
from expressoptionchain import redis_helper
from expressoptionchain.exceptions import OptionStreamValidationException
from expressoptionchain.instrument_manager import KiteInstrumentFetcher, KiteInstrumentManager
from expressoptionchain.kite_connector import KiteConnectionManager
from expressoptionchain.option_chain import OptionChainCreator
from expressoptionchain.redis_helper import RedisConfig

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s.%(msecs)03d %(name)s:%(funcName)s - %(processName)s -%(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger(__name__)
logging.getLogger("connectionpool").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


class OptionChainTicker:
    """
    This class implements kite connect lifecycle methods such as on_connect, on_ticks
    and handles the ticks received.
    """

    def __init__(self, tokens, redis_config):
        """
        :param tokens: tokens to subscribe to. It should be not more than 3000.
        """
        self.tokens = tokens
        # create instance on on_connect
        self.redis_config = redis_config

    def on_connect(self, ws, response):
        log.info('lifecycle: on_connect')
        self.db = redis_helper.get_redis_instance(self.redis_config)
        self.subscribe(ws)

    def subscribe(self, ws):
        """
        Subscribes the token in full mode.
        """
        log.debug(f'subscribing to tokens: {self.tokens}, size: {len(self.tokens)}')
        log.info(f'subscribing to tokens, size: {len(self.tokens)}')
        ws.subscribe(self.tokens)
        log.debug('setting mode')
        ws.set_mode(ws.MODE_FULL, self.tokens)
        log.info('finished subscribing to tokens')

    def on_ticks(self, ws, ticks):
        log.info(f'received {len(ticks)} ticks')
        if ticks[0]['mode'] != ws.MODE_FULL:
            # bug: web socket sent ticks in quote mode even though we subscribed in full mode
            # see `fix_processes` method for more info
            log.error('websocket sent ticks in quote mode.. closing connection and reopening another one')
            ws.stop()
            return
        threading.Thread(target=self.handle_ticks, args=(ticks,), daemon=True).start()

    def handle_ticks(self, ticks):
        # even though this method is called in the thread, make sure this method
        # doesn't take more than 2s. A subscription of about 9000 stocks, would surpass the
        # capability of 8 core Mac laptop.

        start_time = time.time()
        for tick in ticks:
            if 'last_trade_time' in tick:
                tick['last_trade_time'] = helper.get_time_in_str(tick['last_trade_time'])
            if 'exchange_timestamp' in tick:
                tick['exchange_timestamp'] = helper.get_time_in_str(tick['exchange_timestamp'])
            self.db.hset('ticks', tick['instrument_token'], json.dumps(tick))
        log.debug(f"size: {len(ticks)} thread took {(time.time() - start_time)} seconds")

    def on_close(self, ws, code, response):
        log.info(f'Closing the connection, code {code}, response: {response}')
        if ws.is_connected():
            log.info('closing websocket')
            ws.stop()
        else:
            log.error('websocket is already closed')

    def on_reconnect(self, ws, reconnect_count):
        log.debug(f'reconnecting to websocket, reconnect count: {reconnect_count}')

    def on_noreconnect(self, ws):
        log.error("reconnect failed")


class OptionStream:
    """
    This class establishes websocket connections in separate processes to capture the ticks,
    and subsequently constructs the option chain.
    """

    PROCESS_HEALTH_CHECK_WAIT_TIME = 8

    # these are the limits set in kite connect 3
    MAX_TOKENS_PER_WEBSOCKET = 3000
    MAX_WEBSOCKET_CONNECTIONS = 3

    def __init__(self, trading_symbols: list[str], secrets: dict[str, str], expiry: str,
                 criteria: dict[str, str] = None, max_connections=MAX_WEBSOCKET_CONNECTIONS,
                 update_instruments: bool = False, redis_config: RedisConfig = RedisConfig()):
        """
        :param trading_symbols: list of trading symbols in the format "exchange:trading_symbol".
        If it is equity, prefix the scrip name with 'NFO:' E.g. 'NFO:HDFCBANK'.
        CDS, BCD are exchange for currencies and MCX-OPT for commodities.
        E.g. ['BCD:EURINR', 'CDS:EURINR', 'MCX:CRUDEOIL', 'NFO:HDFCBANK', 'CDS:610GS2031']
        :param secrets: dict, e.g. secrets = {
                        'api_key': 'my_api_key',
                        'access_token': 'my_access_token'
                    }
        :param expiry: date of option expiry in dd-mm-yyy format
        :param criteria: Criteria to filter the options. Right now, only percentage criteria is supported.
        The percentage criteria filters out options with strike prices that are more than a specified value away
        from the current spot price. This helps to reduce the number of tokens while subscribing to all the equity options.
        E.g. {'name': 'percentage', 'properties': {'value': 12.5}}
        :param max_connections: maximum number of web socket connections that will be created to fetch the options.
        This value should not be greater than 3.
        :param update_instruments: Set this variable to True if you want to force refresh the kite instruments on this
        run. This will be mostly not necessary as kite instruments are refreshed every day on the first run anyway.
        :param redis_config: specify a different redis configuration
        """
        self.secrets = secrets
        self.redis_config = redis_config
        KiteConnectionManager(secrets).check_connection()
        self.db = redis_helper.get_redis_instance(redis_config)
        self.check_refresh_instruments(update_instruments)
        self.instrument_fetcher = KiteInstrumentFetcher(secrets, redis_config)
        self.trading_symbols = trading_symbols
        self.expiry = expiry
        self.criteria = criteria
        self.max_connections = max_connections
        self.expiry = expiry
        self.all_tokens = self.get_all_tokens()
        self.validate_and_fix()
        log.info(f'total number of instrument tokens: {len(self.all_tokens)}')

    def start(self, threaded=True):
        """
        This method starts the process to subscribe to the tokens and generate the option chain in background
        for all the subscribed stocks. This is a blocking method call.
        :param threaded: if it is true, the process runs in a background thread, otherwise, it will be a
        blocking method call
        :return: nothing
        """
        self.max_connections = min(self.max_connections,
                                   math.ceil(len(self.all_tokens) / OptionStream.MAX_TOKENS_PER_WEBSOCKET))

        pid_to_proc_map = {}
        for i in range(self.max_connections):
            tokens = self.all_tokens[
                     i * OptionStream.MAX_TOKENS_PER_WEBSOCKET: (i + 1) * OptionStream.MAX_TOKENS_PER_WEBSOCKET]
            ticker = OptionChainTicker(tokens, self.redis_config)
            kws = KiteTicker(self.secrets['api_key'], self.secrets['access_token'])
            kws.on_connect = ticker.on_connect
            kws.on_ticks = ticker.on_ticks
            kws.on_close = ticker.on_close
            p = Process(target=kws.connect)
            # this is used to check the health of the process and retry if the processes are not healthy
            pid_to_proc_map[f'Process {i}'] = (p, kws)
            p.start()

        self.fix_processes(pid_to_proc_map)

        # self.create_option_chain() runs forever
        if threaded:
            threading.Thread(target=self.create_option_chain, daemon=True).start()
        else:
            self.create_option_chain()

    def validate_and_fix(self):
        if not isinstance(self.secrets, dict):
            raise OptionStreamValidationException(f'Secrets should be of type dictionary.'
                                                  f' Valid keys are api_key and access_token.')
        if not self.secrets.get('api_key'):
            raise OptionStreamValidationException(f'Secrets does not contain api key')
        if not self.secrets.get('access_token'):
            raise OptionStreamValidationException(f'Secrets does not contain access token')

        if len(self.all_tokens) > self.max_connections * OptionStream.MAX_TOKENS_PER_WEBSOCKET:
            allowed_tokens_count = OptionStream.MAX_WEBSOCKET_CONNECTIONS * OptionStream.MAX_TOKENS_PER_WEBSOCKET
            error_msg = f'Instrument tokens exceeded: You have passed {len(self.trading_symbols)} trading symbols. ' \
                        f'{len(self.all_tokens)} instruments tokens must be subscribed to fetch this data ' \
                        f'which is greater than the allowed value of {allowed_tokens_count} tokens. ' \
                        f'Please lower the number of trading symbols(count: {len(self.trading_symbols)}) ' \
                        f'you are subscribing to or use a percentage criteria filter to filter out the tokens which ' \
                        f'are far from spot price by the specified value.'
            raise OptionStreamValidationException(error_msg)

        valid_keys = set(self.db.hkeys('option_token_info'))
        for trading_symbol in self.trading_symbols:
            if ':' not in trading_symbol:
                error_msg = '''Scrip name {} does not have a exchange name. 
                If it is equity, prefix the scrip name with 'NFO' and then ':'. 
                CDS, BCD are exchange for currencies and MCX-OPT for commodities.
                E.g. ['BCD:EURINR', 'CDS:EURINR', 'MCX:CRUDEOIL', 'NFO:HDFCBANK', 'CDS:610GS2031']
                '''
                log.error(error_msg.format(trading_symbol))
                raise OptionStreamValidationException(f'Trading symbol validation failed: '
                                                      f'{error_msg.format(trading_symbol)}')
            if trading_symbol not in valid_keys:
                raise OptionStreamValidationException(f'{trading_symbol} is not a valid trading symbol.')

        valid_expiry = self.db.smembers('valid_option_expiry')
        if self.expiry not in valid_expiry:
            raise OptionStreamValidationException(f'{self.expiry} is not a valid expiry date.')

    @staticmethod
    def fix_processes(pid_to_proc_map):
        """
        websocket sometimes subscribes to quote mode instead of full mode. This kws connection
        gives duplicate ticks in quote mode and full mode. I haven't figured out a way to get around this. Stopping the
        websocket using kws.stop() kills the entire kws connection. This is likely a bug in kite websockets implementation.

        As a workaround, if ticks come in quote mode, that particular web socket connection is stopped and the process
        will be terminated. The below code monitors the failed processes and creates a new process for the corresponding
        failed process with the right configuration.
        :param pid_to_proc_map: e.g. { 'Process1' : (process obj, web socket connection) }
        :return: returns when all processes are healthy
        """

        # this loop will be terminated once all the processes are healthy
        while True:
            # wait for 8s so that all the processes can receive their first tick
            time.sleep(OptionStream.PROCESS_HEALTH_CHECK_WAIT_TIME)
            all_process_running = True
            for pid, (process, kws) in pid_to_proc_map.items():
                if not process.is_alive():
                    log.error(f'Process {process.name} is terminated.. creating a new process')
                    p = Process(target=kws.connect)
                    pid_to_proc_map[pid] = (p, kws)
                    p.start()
                    all_process_running = False
                else:
                    log.info(f'Process {process.name} is healthy')
            if all_process_running:
                log.info('all the processes are healthy')
                return

    def get_all_tokens(self):
        return self.instrument_fetcher.get_tokens(self.trading_symbols, self.expiry, self.criteria)

    def create_option_chain(self):
        """
        This method creates the option chain for the trading symbols provided.
        :return: This method doesn't return. Use Ctrl + C to stop the current process.
        """
        option_chain_creator = OptionChainCreator(self.secrets)
        count = 0
        while True:
            if count % 30 == 0:
                log.info('Updating option chain in the background')
            for trading_symbol in self.trading_symbols:
                option_chain_creator.create_option_chain(trading_symbol, self.expiry)
            count += 1

            # when trading symbols are less, it takes less time to create the option chain
            # it doesn't make sense to create option chain using the ticks stored in db faster
            # than the option stream updating the ticks

            # ideally this number should be deduced from the speed with which option chain is getting created
            if len(self.trading_symbols) <= 50:
                # todo_low: 0.2s is not a fixed value
                time.sleep(0.2)

    def check_refresh_instruments(self, should_refresh_instruments):
        if should_refresh_instruments:
            self.refresh_instruments()
            return

        option_chain_config = self.db.get('option_chain_config')
        if not option_chain_config:
            self.refresh_instruments()
            return

        option_chain_config = json.loads(option_chain_config)
        last_fetch_time = option_chain_config['instrument_last_fetch_time']
        last_fetch_time = datetime.strptime(last_fetch_time, '%d-%m-%Y %H:%M:%S')
        if date.today() != last_fetch_time.date():
            self.refresh_instruments()
            return

    def refresh_instruments(self):
        log.info('Refreshing the instruments file for today, this may take a few secs')
        instrument_parser = KiteInstrumentManager(self.secrets, self.db)
        instrument_parser.process_instruments()
