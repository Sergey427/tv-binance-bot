from binance.client import Client

client = Client(api_key, api_secret, tld='com', testnet=False)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data['passphrase'] != 'Stargate.2025':
        return jsonify({'error': 'Invalid passphrase'}), 401

    market = data['market']
    side = data['side']
    amount = float(data['amount'])
    order_type = data['order_type']
    contract_type = data.get('contract_type', 'spot')  # По умолчанию спот, если не указано

    try:
        if contract_type == 'futures':
            # Установи плечо для фьючерсов
            client.futures_change_leverage(symbol=market, leverage=5)  # Плечо 5x (настрой по усмотрению)
            # Создай фьючерсный ордер
            order = client.futures_create_order(
                symbol=market,
                side=side.upper(),  # BUY или SELL
                type=order_type.upper(),  # MARKET
                quantity=amount
            )
        else:
            # Спотовая торговля (оставь для совместимости)
            order = client.create_order(
                symbol=market,
                side=side.upper(),
                type=order_type.upper(),
                quantity=amount
            )
        return jsonify({'status': 'success', 'order': order})
    except Exception as e:
        return jsonify({'error': f'binance {str(e)}'}), 500