import json
import string

import requests
import rlp
from pywallet.utils import HDPrivateKey, HDKey
from rest_framework.decorators import api_view
from rest_framework.response import Response
from two1.bitcoin.utils import bytes_to_str

from gnosis_funding.api.ethereum.transactions import Transaction
from gnosis_funding.api.ethereum.utils import parse_int_or_hex, int_to_hex, parse_as_bin, is_numeric
from gnosis_funding.settings import FUNDING_ACCOUNT_PHRASE, SEND_TOKEN_AMOUNT, SEND_ETH_AMOUNT

master_key = HDPrivateKey.master_key_from_mnemonic(FUNDING_ACCOUNT_PHRASE)
root_key = HDKey.from_path(master_key, "m/44'/60'/0'/0/0")
sender = root_key[-1].public_key.address()

tokens = [
    ("0x975be7f72cea31fd83d0cb2a197f9136f38696b7", SEND_TOKEN_AMOUNT * 10000),
    ("0xb3a4bc89d8517e0e2c9b66703d09d3029ffa1e6d", SEND_TOKEN_AMOUNT * 1000000),
    ("0x5f92161588c6178130ede8cbdc181acec66a9731", SEND_TOKEN_AMOUNT * 1000000000000000000),
]


def _request_headers():
    return {
        "Content-Type": "application/json; UTF-8",
    }


def rpc_call(method, params):
    data = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": method,
        "params": params
    }
    return requests.post(u'https://rinkeby.infura.io', data=json.dumps(data)).json()


def rpc_result(method, param):
    response = rpc_call(method, param)
    result = response.get("result")
    if not result:
        raise Exception(response.get("error", "Unknown error"))
    return result


def estimate_tx(sender, address, value, data):
    data = {
        "from": sender,
        "to": address,
        "value": "0x0" if value == 0 else int_to_hex(value),
        "data": data
    }
    return parse_int_or_hex(rpc_result("eth_estimateGas", [data]))


def _send_transaction(address, value=0, data="", gas=None):
    nonce = parse_int_or_hex(rpc_result("eth_getTransactionCount", [sender, "pending"]))
    if not gas:
        gas = estimate_tx(sender, address, value, data)
    tx = Transaction(nonce, 100000000, gas, address, value, parse_as_bin(data)).sign(
        bytes_to_str(bytes(root_key[-1])[-32:]))
    return rpc_result("eth_sendRawTransaction", ["0x" + bytes_to_str(rlp.encode(tx))])


def _build_token_data(address, value):
    return "0xa9059cbb" + address[2:].zfill(64) + int_to_hex(value)[2:].zfill(64)


def _build_etherscan_url(tx_hash):
    return "https://rinkeby.etherscan.io/tx/" + tx_hash


@api_view(["POST"])
def fund_account(request):
    address = request.data.get("text")
    if not address or len(address) != 42 or not address.startswith("0x") or not all(
            c in string.hexdigits for c in address[2:]):
        return Response({"error": "invalid safe address (format: <40 hex chars>)"}, 400)
    return Response("Watch on " + _build_etherscan_url(_send_transaction(address, value=SEND_ETH_AMOUNT, gas=30000)))


@api_view(["POST"])
def fund_safe(request):
    input = request.data.get("text")
    if not input:
        return Response({"error": "invalid params"}, 400)

    params = input.split(" ")
    if len(params) != 2:
        return Response({"error": "invalid param number"}, 400)

    address = params[0]
    if not address or len(address) != 42 or not address.startswith("0x") or not all(
            c in string.hexdigits for c in address[2:]):
        return Response({"error": "invalid safe address (format: <40 hex chars>)"}, 400)

    token_index = None
    try:
        token_index = int(params[1])
    except ValueError:
        pass
    if not token_index or not token_index or token_index < 0 or token_index >= len(tokens):
        return Response({"error": "invalid token index"}, 400)
    (token, value) = tokens[token_index]
    result = _send_transaction(token, value=0, data=_build_token_data(address, value))
    return Response("Watch on " + _build_etherscan_url(result))
