import os
import threading
from flask import Flask
import urllib.request
import urllib.parse
import json
import time
import csv
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

SYMBOL = 'BTCUSDT'
TIMEFRAME = '15m'
RSI_PERIOD = 14
STATE_FILE = 'bot_state.json'
HISTORY_FILE = 'trades_history.csv'

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '9210395285:AAHeK0_4j-ik5AfoDzoWkmIVpNiT4kHTCIY')
TELEGRAM_CHAT_ID = '8985343596'

last_binance_check = 0 
AUTO_TRADE_ENABLED = False 

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'usdt': 1000.0, 'btc': 0.0, 'entry_price': 0.0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def log_trade(action, price, amount, profit_usdt=0.0):
    file_exists = os.path.isfile(HISTORY_FILE)
    with open(HISTORY_FILE, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['Date', 'Action', 'Price', 'Amount', 'Profit_USDT'])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([now, action, round(price, 2), round(amount, 6), round(profit_usdt, 2)])

def get_main_keyboard():
    return {"inline_keyboard": [[{"text": "🟢 КУПИТЬ", "callback_data": "btn_buy"}, {"text": "🔴 ПРОДАТЬ", "callback_data": "btn_sell"}], [{"text": "💼 БАЛАНС", "callback_data": "btn_balance"}, {"text": "📊 СТАТУС", "callback_data": "btn_status"}], [{"text": "📈 ГРАФИК", "callback_data": "btn_chart"}, {"text": "⚙️ АВТО", "callback_data": "btn_toggle_auto"}]]}

def send_telegram_message(text, show_keyboard=False):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {'chat_id': TELEGRAM_CHAT_ID, 'text': text}
        if show_keyboard: data['reply_markup'] = json.dumps(get_main_keyboard())
        data = urllib.parse.urlencode(data).encode('utf-8')
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
    except Exception as e: print(f"Ошибка: {e}")

def send_telegram_photo(photo_url, caption=""):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        data = {'chat_id': TELEGRAM_CHAT_ID, 'photo': photo_url, 'caption': caption, 'reply_markup': json.dumps(get_main_keyboard())}
        data = urllib.parse.urlencode(data).encode('utf-8')
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
    except: pass

def answer_callback(callback_id, text=""):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
        data = urllib.parse.urlencode({'callback_query_id': callback_id, 'text': text}).encode('utf-8')
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
    except: pass

def get_telegram_updates(offset=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        if offset: url += f"?offset={offset}"
        return json.loads(urllib.request.urlopen(url, timeout=10).read().decode()).get('result', [])
    except: return []

def get_prices():
    url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={TIMEFRAME}&limit=50"
    return [float(c[4]) for c in json.loads(urllib.request.urlopen(url, timeout=10).read().decode())]

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain, avg_loss = sum(gains[-period:]) / period, sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + (avg_gain / avg_loss)))

def run_bot():
    global last_binance_check, AUTO_TRADE_ENABLED
    state = load_state()
    send_telegram_message("🤖 Бот в облаке запущен!", show_keyboard=True)
    last_update_id, current_price, current_rsi = None, 0, 50
    closes = []

    while True:
        try:
            if current_price == 0:
                closes = get_prices()
                current_price = closes[-2]
                current_rsi = calculate_rsi(closes[:-1], RSI_PERIOD)

            for update in get_telegram_updates(offset=last_update_id):
                last_update_id = update['update_id'] + 1
                if 'callback_query' in update:
                    action = update['callback_query']['data']
                    cid = update['callback_query']['id']
                    if action == "btn_chart":
                        answer_callback(cid, "Рисуем...")
                        config = {"type": "line", "data": {"labels": [str(i) for i in range(1, 31)], "datasets": [{"label": "BTC/USDT", "data": closes[-30:], "borderColor": "#00ff00", "fill": True, "pointRadius": 0}]}, "options": {"title": {"display": True, "text": "BTC/USDT", "fontColor": "white"}, "legend": {"display": False}, "scales": {"xAxes": [{"ticks": {"fontColor": "white"}}], "yAxes": [{"ticks": {"fontColor": "white"}}]}}}
                        chart_url = f"https://quickchart.io/chart?c={urllib.parse.quote(json.dumps(config))}&backgroundColor=%23111111"
                        send_telegram_photo(chart_url, f"📈 {current_price}$ | RSI: {current_rsi:.2f}")
                    elif action == "btn_buy" and state['usdt'] > 10:
                        answer_callback(cid, "Покупаем...")
                        btc = state['usdt'] / current_price
                        log_trade('BUY', current_price, btc)
                        state.update({'btc': btc, 'entry_price': current_price, 'usdt': 0})
                        save_state(state)
                        send_telegram_message(f"🛒 Куплено {btc:.6f} BTC", show_keyboard=True)
                    elif action == "btn_sell" and state['btc'] > 0:
                        answer_callback(cid, "Продаем...")
                        usdt = state['btc'] * current_price
                        log_trade('SELL', current_price, state['btc'], usdt - (state['btc'] * state['entry_price']))
                        state.update({'usdt': usdt, 'btc': 0, 'entry_price': 0})
                        save_state(state)
                        send_telegram_message(f"💸 Продано за {usdt:.2f} USDT", show_keyboard=True)
                    elif action == "btn_balance":
                        answer_callback(cid, "Считаем...")
                        send_telegram_message(f"💼 {state['usdt']:.2f} USDT\n🪙 {state['btc']:.6f} BTC", show_keyboard=True)
                    elif action == "btn_status":
                        answer_callback(cid, "Смотрим...")
                        send_telegram_message(f"📊 {current_price}$\nRSI: {current_rsi:.2f}\nАвто: {'ВКЛ' if AUTO_TRADE_ENABLED else 'ВЫКЛ'}", show_keyboard=True)
                    elif action == "btn_toggle_auto":
                        AUTO_TRADE_ENABLED = not AUTO_TRADE_ENABLED
                        answer_callback(cid, "ОК")
                        send_telegram_message(f"Авто: {'ВКЛ ✅' if AUTO_TRADE_ENABLED else 'ВЫКЛ 🛑'}", show_keyboard=True)

            if time.time() - last_binance_check > 60:
                last_binance_check = time.time()
                closes = get_prices()
                current_price = closes[-2]
                current_rsi = calculate_rsi(closes[:-1], RSI_PERIOD)
                if AUTO_TRADE_ENABLED and current_rsi < 35 and state['usdt'] > 10:
                    btc = state['usdt'] / current_price
                    log_trade('BUY (AUTO)', current_price, btc)
                    state.update({'btc': btc, 'entry_price': current_price, 'usdt': 0})
                    save_state(state)
                    send_telegram_message(f"🟢 АВТО-КУПИТЬ!", show_keyboard=True)
            time.sleep(3)
        except Exception as e:
            time.sleep(5)

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
