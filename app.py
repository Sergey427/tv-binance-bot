import os
from flask import Flask, request, jsonify
from binance.client import Client
import logging

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация Binance клиента
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
if not api_key or not api_secret:
    logger.error("BINANCE_API_KEY or BINANCE_SECRET_KEY not set")
    raise EnvironmentError("BINANCE_API_KEY or BINANCE_SECRET_KEY not set")
client = Client(api_key, api_secret, tld='com', testnet=False)

# Переменные для отслеживания состояния позиций
long_position_open = False
short_position_open = False
current_symbol = None

@app.route('/')
def home():
    logger.info("Home route accessed")
    return jsonify({'status': 'Server is running'})

# Функция для проверки открытых позиций
def check_open_position(symbol, position_side):
    try:
        positions = client.futures_position_information(symbol=symbol)
        for position in positions:
            if position['positionSide'] == position_side and float(position['positionAmt']) != 0:
                return True
        return False
    except Exception as e:
        logger.error(f"Failed to check open position for {symbol}: {str(e)}")
        return False

# Функция для получения доступного баланса
def get_futures_balance():
    try:
        balance_info = client.futures_account_balance()
        for asset in balance_info:
            if asset['asset'] == 'USDT':
                return float(asset['availableBalance'])
        return 0.0
    except Exception as e:
        logger.error(f"Failed to get futures balance: {str(e)}")
        return 0.0

@app.route('/webhook', methods=['POST'])
def webhook():
    global long_position_open, short_position_open, current_symbol
    logger.info("Received webhook request")
    try:
        # Проверяем, что запрос содержит JSON
        if not request.is_json:
            logger.warning("Request does not contain JSON")
            return jsonify({'error': 'Request must be JSON'}), 415

        data = request.get_json()
        logger.info(f"Received data: {data}")

        # Проверка обязательных полей
        required_fields = ['passphrase', 'market', 'side', 'amount', 'order_type', 'bot_type', 'action']
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
        bot_type = data['bot_type']
        action = data['action']

        logger.info(f"Processing order: market={market}, side={side}, amount={amount}, order_type={order_type}, contract_type={contract_type}, bot_type={bot_type}, action={action}")

        if contract_type == 'futures':
            # Проверяем баланс перед операцией
            balance = get_futures_balance()
            logger.info(f"Futures available balance: ${balance}")
            if balance < 0.1:  # Минимальный порог для тестов
                logger.warning(f"Insufficient balance: ${balance}")
                return jsonify({'error': f'Insufficient balance: ${balance}'}), 400

            # Устанавливаем рычаг (leverage)
            try:
                client.futures_change_leverage(symbol=market, leverage=50)
                logger.info(f"Leverage set to 50 for {market}")
            except Exception as e:
                logger.error(f"Failed to set leverage: {str(e)}")
                return jsonify({'error': f'Failed to set leverage: {str(e)}'}), 500

            # Проверяем минимальный объём для фьючерсов
            try:
                symbol_info = client.futures_exchange_info()
                symbol_found = False
                for symbol in symbol_info['symbols']:
                    if symbol['symbol'] == market:
                        symbol_found = True
                        # Получаем минимальный объём из фильтров
                        for filt in symbol['filters']:
                            if filt['filterType'] == 'LOT_SIZE':
                                min_qty = float(filt['minQty'])
                                logger.info(f"Minimal quantity (minQty) for {market}: {min_qty}")
                                break
                        else:
                            logger.error(f"LOT_SIZE filter not found for {market}")
                            return jsonify({'error': f'LOT_SIZE filter not found for {market}'}), 500

                        if amount < min_qty:
                            logger.warning(f"Amount {amount} is below minimum quantity {min_qty} for {market}")
                            return jsonify({'error': f'Amount {amount} is below minimum quantity {min_qty}'}), 400

                        break
                if not symbol_found:
                    logger.error(f"Symbol {market} not found in futures exchange info")
                    return jsonify({'error': f'Symbol {market} not found in futures exchange info'}), 400
            except Exception as e:
                logger.error(f"Failed to check futures symbol info: {str(e)}")
                return jsonify({'error': f'Failed to check futures symbol info: {str(e)}'}), 500

            # Логика для Longbot и Shortbot
            if bot_type == 'longbot' and side == 'buy' and action == 'open':
                # Проверяем, есть ли уже открытая Long-позиция
                if check_open_position(market, 'LONG'):
                    logger.warning(f"Long position already open for {market}")
                    return jsonify({'error': f'Long position already open for {market}'}), 400

                # Longbot открывает Long-позицию
                if short_position_open and current_symbol == market:
                    # Закрываем Short-позицию
                    logger.info("Closing Short position before opening Long")
                    try:
                        close_order = client.futures_create_order(
                            symbol=market,
                            side='BUY',
                            type='MARKET',
                            quantity=amount,
                            positionSide='SHORT',
                            reduceOnly=True
                        )
                        logger.info(f"Short position closed: {close_order}")
                        short_position_open = False
                    except Exception as e:
                        logger.error(f"Failed to close Short position: {str(e)}")
                        return jsonify({'error': f'Failed to close Short position: {str(e)}'}), 500

                # Открываем Long-позицию
                logger.info("Opening Long position")
                order = client.futures_create_order(
                    symbol=market,
                    side='BUY',
                    type='MARKET',
                    quantity=amount,
                    positionSide='LONG'
                )
                long_position_open = True
                current_symbol = market
                logger.info(f"Long position opened: {order}")

            elif bot_type == 'longbot' and side == 'sell' and action == 'close':
                # Longbot закрывает Long-позицию
                if not check_open_position(market, 'LONG'):
                    logger.warning("No Long position to close")
                    return jsonify({'error': 'No Long position to close'}), 400

                logger.info("Closing Long position")
                order = client.futures_create_order(
                    symbol=market,
                    side='SELL',
                    type='MARKET',
                    quantity=amount,
                    positionSide='LONG',
                    reduceOnly=True
                )
                long_position_open = False
                current_symbol = None
                logger.info(f"Long position closed: {order}")

            elif bot_type == 'shortbot' and side == 'sell' and action == 'open':
                # Проверяем, есть ли уже открытая Short-позиция
                if check_open_position(market, 'SHORT'):
                    logger.warning(f"Short position already open for {market}")
                    return jsonify({'error': f'Short position already open for {market}'}), 400

                # Shortbot открывает Short-позицию
                if long_position_open and current_symbol == market:
                    # Закрываем Long-позицию
                    logger.info("Closing Long position before opening Short")
                    try:
                        close_order = client.futures_create_order(
                            symbol=market,
                            side='SELL',
                            type='MARKET',
                            quantity=amount,
                            positionSide='LONG',
                            reduceOnly=True
                        )
                        logger.info(f"Long position closed: {close_order}")
                        long_position_open = False
                    except Exception as e:
                        logger.error(f"Failed to close Long position: {str(e)}")
                        return jsonify({'error': f'Failed to close Long position: {str(e)}'}), 500

                # Открываем Short-позицию
                logger.info("Opening Short position")
                order = client.futures_create_order(
                    symbol=market,
                    side='SELL',
                    type='MARKET',
                    quantity=amount,
                    positionSide='SHORT'
                )
                short_position_open = True
                current_symbol = market
                logger.info(f"Short position opened: {order}")

            elif bot_type == 'shortbot' and side == 'buy' and action == 'close':
                # Shortbot закрывает Short-позицию
                if not check_open_position(market, 'SHORT'):
                    logger.warning("No Short position to close")
                    return jsonify({'error': 'No Short position to close'}), 400

                logger.info("Closing Short position")
                order = client.futures_create_order(
                    symbol=market,
                    side='BUY',
                    type='MARKET',
                    quantity=amount,
                    positionSide='SHORT',
                    reduceOnly=True
                )
                short_position_open = False
                current_symbol = None
                logger.info(f"Short position closed: {order}")

            else:
                logger.warning("Invalid bot_type, side, or action combination")
                return jsonify({'error': 'Invalid bot_type, side, or action combination'}), 400

            return jsonify({'status': 'success', 'order': order})

        else:
            logger.warning("Spot trading not implemented")
            return jsonify({'error': 'Spot trading not implemented'}), 400

    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}", exc_info=True)
        return jsonify({'error': f'binance {str(e)}'}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application")
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))