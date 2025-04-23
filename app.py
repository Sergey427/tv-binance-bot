import os
from flask import Flask, request, jsonify
from binance.client import Client
import requests

app = Flask(__name__)

api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
client = Client(api_key, api_secret, tld='com', testnet=False)

@app.route('/')
def home():
    return jsonify({'status': 'Server is running'})

@app.route('/get-outbound-ip')
def get_outbound_ip():
    try:
        response = requests.get('https://api.ipify.org?format=json')
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data['passphrase'] != os.getenv('PASSPHRASE'):
        return jsonify({'error': 'Invalid passphrase'}), 401

    market = data['market']
    side = data['side']
    amount = float(data['amount'])
    order_type = data['order_type']
    contract_type = data.get('contract_type', 'spot')

    try:
        if contract_type == 'futures':
            client.futures_change_leverage(symbol=market, leverage=5)
            order = client.futures_create_order(
                symbol=market,
                side=side.upper(),
                type=order_type.upper(),
                quantity=amount
            )
        else:
            order = client.create_order(
                symbol=market,
                side=side.upper(),
                type=order_type.upper(),
                quantity=amount
            )
        return jsonify({'status': 'success', 'order': order})
    except Exception as e:
        return jsonify({'error': f'binance {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))
