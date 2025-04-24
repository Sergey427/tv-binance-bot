import os
from flask import Flask, request, jsonify
from binance.client import Client
import logging

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные для отслеживания состояния позиций
long_position_open = False
short_position_open = False
current_symbol = None

@app.route('/')
def home():
    logger.info("Home route accessed")
    return jsonify({'status': 'Server is running'})

# Временно закомментируем маршрут /get-outbound-ip
# @app.route('/get-outbound-ip')
# def get_outbound_ip():
#     try:
#         response = requests.get('https://api.ipify.org?format=json')
#         return jsonify(response.json())
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    global long_position_open, short_position_open, current_symbol
    logger.info("Received webhook request")
    try:
        # Инициализация Binance клиента внутри маршрута
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_SECRET_KEY')
        if not api_key or not api_secret:
            logger.error("BINANCE_API_KEY or BINANCE_SECRET_KEY not set")
            return jsonify({'error': 'BINANCE_API_KEY or BINANCE_SECRET_KEY not set'}), 500
        client = Client(api_key, api_secret, tld='com', testnet=False)

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
        take_profit = data.get('take_profit')  # Опционально: цена для Take Profit
        stop_loss = data.get('stop_loss')      # Опционально: цена для Stop Loss
        trailing_stop = data.get('trailing_stop')  # Опционально: процент для Trailing Stop

        logger.info(f"Processing order: market={market}, side={side}, amount={amount}, order_type={order_type}, contract_type={contract_type}, bot_type={bot_type}, action={action}, take_profit={take_profit}, stop_loss={stop_loss}, trailing_stop={trailing_stop}")

        if contract_type == 'futures':
            # Устанавливаем рычаг (leverage)
            try:
                client.futures_change_leverage(symbol=market, leverage=50)
                logger.info(f"Leverage set to 50 for {market}")
            except Exception as e:
                logger.error(f"Failed to set leverage: {str(e)}")
                return jsonify({'error': f'Failed to set leverage: {str(e)}'}), 500

            # Проверяем минимальный объём и точность цены для фьючерсов
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
                                break
                        else:
                            logger.error(f"LOT_SIZE filter not found for {market}")
                            return jsonify({'error': f'LOT_SIZE filter not found for {market}'}), 500

                        if amount < min_qty:
                            logger.warning(f"Amount {amount} is below minimum quantity {min_qty} for {market}")
                            return jsonify({'error': f'Amount {amount} is below minimum quantity {min_qty}'}), 400

                        price_precision = symbol['pricePrecision']  # Точность цены
                        break
                if not symbol_found:
                    logger.error(f"Symbol {market} not found in futures exchange info")
                    return jsonify({'error': f'Symbol {market} not found in futures exchange info'}), 400
            except Exception as e:
                logger.error(f"Failed to check futures symbol info: {str(e)}")
                return jsonify({'error': f'Failed to check futures symbol info: {str(e)}'}), 500

            # Логика для Longbot и Shortbot
            if bot_type == 'longbot' and side == 'buy' and action == 'open':
                # Longbot открывает Long-позицию
                if short_position_open and current_symbol == market:
                    # Закрываем Short-позицию
                    logger.info("Closing Short position before opening Long")
                    try:
                        close_order = client.futures_create_order(
                            symbol=market,
                            side='BUY',  # Покупаем, чтобы закрыть Short
                            type='MARKET',
                            quantity=amount,
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
                    quantity=amount
                )
                long_position_open = True
                current_symbol = market
                logger.info(f"Long position opened: {order}")

                # Устанавливаем Take Profit, если указан
                if take_profit:
                    try:
                        tp_price = round(float(take_profit), price_precision)
                        tp_order = client.futures_create_order(
                            symbol=market,
                            side='SELL',  # Продаём, чтобы зафиксировать прибыль
                            type='TAKE_PROFIT',
                            quantity=amount,
                            price=tp_price,
                            stopPrice=tp_price,
                            reduceOnly=True
                        )
                        logger.info(f"Take Profit set at {tp_price}: {tp_order}")
                    except Exception as e:
                        logger.error(f"Failed to set Take Profit: {str(e)}")
                        return jsonify({'error': f'Failed to set Take Profit: {str(e)}'}), 500

                # Устанавливаем Stop Loss, если указан
                if stop_loss:
                    try:
                        sl_price = round(float(stop_loss), price_precision)
                        sl_order = client.futures_create_order(
                            symbol=market,
                            side='SELL',  # Продаём, чтобы ограничить убытки
                            type='STOP',
                            quantity=amount,
                            price=sl_price,
                            stopPrice=sl_price,
                            reduceOnly=True
                        )
                        logger.info(f"Stop Loss set at {sl_price}: {sl_order}")
                    except Exception as e:
                        logger.error(f"Failed to set Stop Loss: {str(e)}")
                        return jsonify({'error': f'Failed to set Stop Loss: {str(e)}'}), 500

                # Устанавливаем Trailing Stop, если указан
                if trailing_stop:
                    try:
                        callback_rate = float(trailing_stop)
                        if not 0.1 <= callback_rate <= 5.0:
                            logger.warning(f"Trailing Stop callback rate {callback_rate} is out of range (0.1-5.0)")
                            return jsonify({'error': f'Trailing Stop callback rate {callback_rate} is out of range (0.1-5.0)'}), 400
                        ts_order = client.futures_create_order(
                            symbol=market,
                            side='SELL',
                            type='TRAILING_STOP_MARKET',
                            quantity=amount,
                            callbackRate=callback_rate,
                            reduceOnly=True
                        )
                        logger.info(f"Trailing Stop set with callback rate {callback_rate}%: {ts_order}")
                    except Exception as e:
                        logger.error(f"Failed to set Trailing Stop: {str(e)}")
                        return jsonify({'error': f'Failed to set Trailing Stop: {str(e)}'}), 500

            elif bot_type == 'shortbot' and side == 'sell' and action == 'open':
                # Shortbot открывает Short-позицию
                if long_position_open and current_symbol == market:
                    # Закрываем Long-позицию
                    logger.info("Closing Long position before opening Short")
                    try:
                        close_order = client.futures_create_order(
                            symbol=market,
                            side='SELL',  # Продаём, чтобы закрыть Long
                            type='MARKET',
                            quantity=amount,
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
                    quantity=amount
                )
                short_position_open = True
                current_symbol = market
                logger.info(f"Short position opened: {order}")

                # Устанавливаем Take Profit, если указан
                if take_profit:
                    try:
                        tp_price = round(float(take_profit), price_precision)
                        tp_order = client.futures_create_order(
                            symbol=market,
                            side='BUY',  # Покупаем, чтобы зафиксировать прибыль
                            type='TAKE_PROFIT',
                            quantity=amount,
                            price=tp_price,
                            stopPrice=tp_price,
                            reduceOnly=True
                        )
                        logger.info(f"Take Profit set at {tp_price}: {tp_order}")
                    except Exception as e:
                        logger.error(f"Failed to set Take Profit: {str(e)}")
                        return jsonify({'error': f'Failed to set Take Profit: {str(e)}'}), 500

                # Устанавливаем Stop Loss, если указан
                if stop_loss:
                    try:
                        sl_price = round(float(stop_loss), price_precision)
                        sl_order = client.futures_create_order(
                            symbol=market,
                            side='BUY',  # Покупаем, чтобы ограничить убытки
                            type='STOP',
                            quantity=amount,
                            price=sl_price,
                            stopPrice=sl_price,
                            reduceOnly=True
                        )
                        logger.info(f"Stop Loss set at {sl_price}: {sl_order}")
                    except Exception as e:
                        logger.error(f"Failed to set Stop Loss: {str(e)}")
                        return jsonify({'error': f'Failed to set Stop Loss: {str(e)}'}), 500

                # Устанавливаем Trailing Stop, если указан
                if trailing_stop:
                    try:
                        callback_rate = float(trailing_stop)
                        if not 0.1 <= callback_rate <= 5.0:
                            logger.warning(f"Trailing Stop callback rate {callback_rate} is out of range (0.1-5.0)")
                            return jsonify({'error': f'Trailing Stop callback rate {callback_rate} is out of range (0.1-5.0)'}), 400
                        ts_order = client.futures_create_order(
                            symbol=market,
                            side='BUY',
                            type='TRAILING_STOP_MARKET',
                            quantity=amount,
                            callbackRate=callback_rate,
                            reduceOnly=True
                        )
                        logger.info(f"Trailing Stop set with callback rate {callback_rate}%: {ts_order}")
                    except Exception as e:
                        logger.error(f"Failed to set Trailing Stop: {str(e)}")
                        return jsonify({'error': f'Failed to set Trailing Stop: {str(e)}'}), 500

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
