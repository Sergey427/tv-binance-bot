from fastapi import FastAPI, Request
import ccxt

app = FastAPI()

# Настройки Binance API (замени своими ключами позже)
binance = ccxt.binance({
    'apiKey': 'ТВОЙ_API_KEY',
    'secret': 'ТВОЙ_SECRET'
})

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("Сигнал получен:", data)
    
    if data.get("signal") == "buy":
        symbol = data.get("symbol", "BTC/USDT")
        amount = 0.001
        order = binance.create_market_buy_order(symbol, amount)
        return {"status": "BUY выполнен", "order": order}
    
    elif data.get("signal") == "sell":
        symbol = data.get("symbol", "BTC/USDT")
        amount = 0.001
        order = binance.create_market_sell_order(symbol, amount)
        return {"status": "SELL выполнен", "order": order}
    
    return {"status": "Сигнал не распознан"}
