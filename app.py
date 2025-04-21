import os
import json
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import ccxt

logging.basicConfig(filename='logs/bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

load_dotenv()
BINANCE_API_KEY = os.getenv(5rtVvkdPFTEELRdcbR7w7s8FEGbWIvO5ulbwpvn5H1U3rm8ZBrejnMHlhizto5nv)
BINANCE_SECRET_KEY = os.getenv(r8NbiZoh47oY9dmlbgd7shVTTCtSxLxcgG8PkVWdxCTIqp6GBF3c4p6DM4H6MkBc)
PASSPHRASE = os.getenv(Stargrad.2025)

exchange = ccxt.binance({'apiKey': BINANCE_API_KEY, 'secret': BINANCE_SECRET_KEY, 'enableRateLimit': True})

@app.route('/', methods=['GET'])
def home():
    return jsonify({'status': 'Server is running'})

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data:
            logger.error('No JSON data')
            return jsonify({'error': 'No JSON data'}), 400
        if data.get('passphrase') != PASSPHRASE:
            logger.error('Invalid passphrase')
            return jsonify({'error': 'Invalid passphrase'}), 403
        symbol = data.get('market', 'BTC/USDT')
        side = data.get('side', '').lower()
        amount = float(data.get('amount', 0.001))
        order_type = data.get('order_type', 'market')
        logger.info(f'Signal: {data}')
        if side not in ['buy', 'sell']:
            logger.error('Invalid side')
            return jsonify({'error': 'Invalid side'}), 400
        if amount <= 0:
            logger.error('Invalid amount')
            return jsonify({'error': 'Invalid amount'}), 400
        if order_type == 'market':
            if side == 'buy':
                order = exchange.create_market_buy_order(symbol, amount)
            else:
                order = exchange.create_market_sell_order(symbol, amount)
        else:
            logger.error('Unsupported order type')
            return jsonify({'error': 'Unsupported order type'}), 400
        logger.info(f'Order: {order}')
        return jsonify({'status': 'success', 'order': order}), 200
    except Exception as e:
        logger.error(f'Error: {str(e)}')
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
