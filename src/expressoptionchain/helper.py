import json
import os

from expressoptionchain.exceptions import ExpressOptionChainException


def get_time_in_str(dt):
    if not dt:
        return dt
    return dt.strftime("%d-%m-%Y %H:%M:%S")


def get_secrets(filename=f'{os.environ["HOME"]}/.kite/secrets'):
    try:
        with open(filename, 'r') as f:
            secrets = json.load(f)
            return secrets
    except FileNotFoundError:
        message = f'''{filename} not found. Please put the secrets in {filename} or execute the the command till 
        cat > {filename} << EOF
        {
            "api_key": "your_api_key",
            "api_secret": "your_api_secret",
            "access_token": "generated_access_token"
        }
        EOF
        '''
        raise ExpressOptionChainException(message)


def get_hash_value(r, hash_name, key):
    val = r.hget(hash_name, key)
    if val:
        return json.loads(val)
    return val
