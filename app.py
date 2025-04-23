import os
from flask import Flask, request, jsonify
from binance.client import Client
import requests
import logging

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    logger.info("Received webhook request")
    try:
        # Проверяем, что запрос содержит JSON
        if not request.is_json:
            logger.warning("Request does not contain JSON")
            return jsonify({'error': 'Request must be JSON'}), 415

        data = request.get_json()
        logger.info(f"Received data: {data}")

        # Проверка обязательных полей
        required_fields = ['passphrase', 'market', 'side', 'amount', 'order_type']
        for field in required_fields:
            if field not in data:
                logger.warning(f"Missing required field: {field}")
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Проверка passphrase
        if data['passphrase'] != os.getenv('PASSPHRASE'):
            logger.warning("Invalid passphrase")
            return jsonify({'error': 'Invalid passphrase'}), 401

        market = data['market']
        side = data['side']
        amount = float(data['amount'])
        order_type = data['order_type']
        contract_type = data.get('contract_type', 'spot')

        logger.info(f"Processing order: market={market}, side={side}, amount={amount}, order_type={order_type}, contract_type={contract_type}")

        if contract_type == 'futures':
            logger.info("Setting up futures order")
            # Устанавливаем рычаг (leverage)
            try:
                client.futures_change_leverage(symbol=market, leverage=75)
                logger.info(f"Leverage set to 5 for {market}")
            except Exception as e:
                logger.error(f"Failed to set leverage: {str(e)}")
                return jsonify({'error': f'Failed to set leverage: {str(e)}'}), 500

            # Проверяем минимальный объём для фьючерсов
            try:
                symbol_info = client.futures_exchange_info()
                for symbol in symbol_info['symbols']:
                    if symbol['symbol'] == market:
                        min_qty = float(symbol['quantityPrecision'])
                        if amount < min_qty:
                            logger.warning(f"Amount {amount} is below minimum quantity {min_qty} for {market}")
                            return jsonify({'error': f'Amount {amount} is below minimum quantity {min_qty}'}), 400
                        break
            except Exception as e:
                logger.error(f"Failed to check futures symbol info: {str(e)}")
                return jsonify({'error': f'Failed to check futures symbol info: {str(e)}'}), 500

            # Создаём фьючерсный ордер
            logger.info("Creating futures order")
            order = client.futures_create_order(
                symbol=market,
                side=side.upper(),
                type=order_type.upper(),
                quantity=amount
            )
        else:
            logger.info("Creating spot order")
            order = client.create_order(
                symbol=market,
                side=side.upper(),
                type=order_type.upper(),
                quantity=amount
            )
        logger.info(f"Order successful: {order}")
        return jsonify({'status': 'success', 'order': order})
    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}", exc_info=True)
        return jsonify({'error': f'binance {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))
