import logging

from kiteconnect import KiteConnect

log = logging.getLogger(__name__)


class KiteConnectionManager:
    __kite_client = None

    def __init__(self, secrets):
        log.info('Creating kite client')
        kite_client = KiteConnect(api_key=secrets['api_key'])
        kite_client.set_access_token(secrets['access_token'])
        KiteConnectionManager.__kite_client = kite_client
        self.secrets = secrets

    @staticmethod
    def get_kite_client(secrets):
        if not KiteConnectionManager.__kite_client:
            KiteConnectionManager(secrets)
        return KiteConnectionManager.__kite_client

    @staticmethod
    def check_connection():
        KiteConnectionManager.__kite_client.profile()


class KiteConnector:
    def __init__(self, secrets: dict) -> None:
        self.kite_client = KiteConnectionManager.get_kite_client(secrets)

    def get_ltp(self, trading_symbols: list[str]) -> dict[str, dict[str, float]]:
        '''
        :param trading_symbols: list of trading symbols of format exchange:trading_symbol e.g. NSE:ACC
        :return: map of trading symbol to the ltp quote e.g. {'NSE:ACC': {'instrument_token': 5633, 'last_price': 1880.4}}
        '''
        return self.kite_client.ltp(trading_symbols)
