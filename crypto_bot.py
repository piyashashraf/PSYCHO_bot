import requests
import math
import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ✅ এখানে তোমার token বসাও
BOT_TOKEN = "8750364513:AAEg803P1uEBwjSjIxZZaTemT24rCsujYwk"

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return '🚀 CryptoSignal PRO Bot is running!'

@flask_app.route('/health')
def health():
    return 'OK', 200

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)

# ============================================================
# COINGECKO API (Render এ কাজ করে)
# ============================================================
COINGECKO = "https://api.coingecko.com/api/v3"

COIN_IDS = {
    'BTC': 'bitcoin', 'ETH': 'ethereum', 'BNB': 'binancecoin',
    'SOL': 'solana', 'XRP': 'ripple', 'ADA': 'cardano',
    'DOGE': 'dogecoin', 'DOT': 'polkadot', 'MATIC': 'matic-network',
    'LTC': 'litecoin', 'AVAX': 'avalanche-2', 'LINK': 'chainlink',
    'UNI': 'uniswap', 'ATOM': 'cosmos', 'TRX': 'tron',
    'NEAR': 'near', 'APT': 'aptos', 'OP': 'optimism',
    'ARB': 'arbitrum', 'SHIB': 'shiba-inu',
}

def get_coin_id(symbol):
    return COIN_IDS.get(symbol.upper(), symbol.lower())

def get_ticker(symbol):
    try:
        coin_id = get_coin_id(symbol)
        r = requests.get(f"{COINGECKO}/simple/price",
            params={
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_high_24h": "true",
                "include_low_24h": "true"
            }, timeout=15)
        if r.ok:
            d = r.json().get(coin_id, {})
            if d:
                return {
                    'lastPrice': str(d.get('usd', 0)),
                    'priceChangePercent': str(d.get('usd_24h_change', 0)),
                    'quoteVolume': str(d.get('usd_24h_vol', 0)),
                    'highPrice': str(d.get('usd_24h_high', 0)),
                    'lowPrice': str(d.get('usd_24h_low', 0)),
                }
        return None
    except Exception as e:
        print(f"Ticker error: {e}")
        return None

def get_klines(symbol, interval="1h", limit=100):
    try:
        coin_id = get_coin_id(symbol)
        days = 1 if interval in ['1m','5m','15m','30m','1h'] else 7 if interval == '4h' else 30
        r = requests.get(f"{COINGECKO}/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": days}, timeout=15)
        if r.ok:
            prices = r.json().get('prices', [])
            volumes = r.json().get('total_volumes', [])
            klines = []
            for i, p in enumerate(prices[-limit:]):
                v = volumes[i][1] if i < len(volumes) else 0
                klines.append({"c": p[1], "o": p[1], "h": p[1], "l": p[1], "v": v})
            return klines if klines else None
    except Exception as e:
        print(f"Klines error: {e}")
        return None

def get_top_coins(sort_by="volume"):
    try:
        order = "volume_desc" if sort_by == "volume" else \
                "price_change_percentage_24h_desc" if sort_by == "gainers" else \
                "price_change_percentage_24h_asc"
        r = requests.get(f"{COINGECKO}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": order,
                "per_page": 10,
                "page": 1,
                "sparkline": "false"
            }, timeout=15)
        if r.ok:
            return r.json()
        return []
    except Exception as e:
        print(f"Top coins error: {e}")
        return []

def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if r.ok:
            d = r.json()['data'][0]
            return int(d['value']), d['value_classification']
    except: pass
    return None, None

# ============================================================
# TECHNICAL ANALYSIS
# ============================================================
def calc_ema(closes, period):
    k = 2 / (period + 1)
    ema = closes[0]
    for c in closes[1:]: ema = c * k + ema * (1 - k)
    return ema

def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50
    gains = losses = 0
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0: gains += diff
        else: losses -= diff
    if losses == 0: return 100
    rs = (gains/period) / (losses/period)
    return 100 - (100 / (1 + rs))

def calc_bb(closes, period=20):
    if len(closes) < period:
        period = len(closes)
    sl = closes[-period:]
    mean = sum(sl) / len(sl)
    std = math.sqrt(sum((c-mean)**2 for c in sl) / len(sl))
    return mean + 2*std, mean - 2*std

def get_signal(symbol, tf="1h"):
    klines = get_klines(symbol, tf, 100)
    if not klines or len(klines) < 10: return None
    closes = [k['c'] for k in klines]
    volumes = [k['v'] for k in klines]
    last = closes[-1]
    rsi = calc_rsi(closes)
    macd = calc_ema(closes, min(12, len(closes))) - calc_ema(closes, min(26, len(closes)))
    ema50 = calc_ema(closes, min(50, len(closes)))
    ema200 = calc_ema(closes, min(200, len(closes)))
    bb_upper, bb_lower = calc_bb(closes)
    avg_vol = sum(volumes[-10:]) / max(len(volumes[-10:]), 1)
    last_vol = volumes[-1] if volumes else 0
    rsi_sig = "BUY" if rsi < 30 else "SELL" if rsi > 70 else "NEUTRAL"
    macd_sig = "BUY" if macd > 0 else "SELL"
    ema_sig = "BUY" if ema50 > ema200 else "SELL"
    bb_sig = "BUY" if last < bb_lower else "SELL" if last > bb_upper else "NEUTRAL"
    vol_sig = "BUY" if last_vol > avg_vol * 1.2 else "NEUTRAL"
    sigs = [rsi_sig, macd_sig, ema_sig, bb_sig, vol_sig]
    buy_c = sigs.count("BUY")
    sell_c = sigs.count("SELL")
    overall = "🟢 BUY" if buy_c >= 3 else "🔴 SELL" if sell_c >= 3 else "🟡 HOLD"
    return {
        "overall": overall, "rsi": rsi, "rsi_sig": rsi_sig,
        "macd": macd, "macd_sig": macd_sig, "ema_sig": ema_sig,
        "bb_sig": bb_sig, "vol_sig": vol_sig,
        "buy_count": buy_c, "sell_count": sell_c, "last_price": last
    }

# ============================================================
# FORMAT
# ============================================================
def fp(p):
    try:
        p = float(p)
        if p >= 1000: return f"${p:,.2f}"
        if p >= 1: return f"${p:.4f}"
        return f"${p:.6f}"
    except: return "$0"

def fv(v):
    try:
        v = float(v)
        if v >= 1e9: return f"${v/1e9:.2f}B"
        if v >= 1e6: return f"${v/1e6:.2f}M"
        return f"${v:,.0f}"
    except: return "$0"

def ie(s): return "🟢" if s=="BUY" else "🔴" if s=="SELL" else "🟡"

# ============================================================
# COMMANDS
# ============================================================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📊 BTC Price", callback_data="price_BTC"),
         InlineKeyboardButton("📊 ETH Price", callback_data="price_ETH")],
        [InlineKeyboardButton("🔥 Gainers", callback_data="gainers"),
         InlineKeyboardButton("📉 Losers", callback_data="losers")],
        [InlineKeyboardButton("⚡ BTC Signal", callback_data="signal_BTC"),
         InlineKeyboardButton("⚡ ETH Signal", callback_data="signal_ETH")],
        [InlineKeyboardButton("🌡️ Fear & Greed", callback_data="feargreed"),
         InlineKeyboardButton("💰 Top Volume", callback_data="topvolume")],
    ]
    await update.message.reply_text(
        "🚀 *CryptoSignal PRO Bot*\n━━━━━━━━━━━━━━━\n\n"
        "Commands:\n"
        "`/price BTC` — Live price\n"
        "`/signal BTC` — Buy/Sell signal\n"
        "`/signal ETH 4h` — 4H signal\n"
        "`/top` — Top 10 volume\n"
        "`/gainers` — Top gainers\n"
        "`/losers` — Top losers\n"
        "`/risk 1000 2 3 6` — Risk calc\n"
        "`/fg` — Fear & Greed\n\n"
        "শুধু coin name লিখলেও কাজ করবে: `BTC` `ETH` `SOL`",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def price_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    coin = ctx.args[0].upper() if ctx.args else "BTC"
    await update.message.reply_text(f"⏳ `{coin}` price আনছি...", parse_mode="Markdown")
    t = get_ticker(coin)
    if not t or not t.get('lastPrice') or float(t.get('lastPrice', 0)) == 0:
        await update.message.reply_text(f"❌ `{coin}` পাওয়া যায়নি। BTC ETH SOL BNB XRP DOGE এগুলো try করো।", parse_mode="Markdown")
        return
    p = float(t['lastPrice'])
    chg = float(t['priceChangePercent'])
    e = "🟢" if chg >= 0 else "🔴"
    await update.message.reply_text(
        f"*{coin}/USD*\n━━━━━━━━━━━━━━━\n"
        f"💰 Price: `{fp(p)}`\n{e} Change: `{chg:+.2f}%`\n"
        f"📈 High: `{fp(float(t['highPrice']))}` | 📉 Low: `{fp(float(t['lowPrice']))}`\n"
        f"📊 Volume: `{fv(float(t['quoteVolume']))}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(f"⚡ Signal", callback_data=f"signal_{coin}"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"price_{coin}")]]))

async def signal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    coin = ctx.args[0].upper() if ctx.args else "BTC"
    tf = ctx.args[1].lower() if len(ctx.args) > 1 else "1h"
    await update.message.reply_text(f"⏳ `{coin}` ({tf}) analyze করছি...", parse_mode="Markdown")
    sig = get_signal(coin, tf)
    if not sig:
        await update.message.reply_text(f"❌ `{coin}` data পাওয়া যায়নি।", parse_mode="Markdown")
        return
    await update.message.reply_text(
        f"⚡ *{coin} Signal* ({tf.upper()})\n━━━━━━━━━━━━━━━\n"
        f"🎯 Overall: *{sig['overall']}*\n💰 Price: `{fp(sig['last_price'])}`\n\n"
        f"*Indicators:*\n"
        f"{ie(sig['rsi_sig'])} RSI: `{sig['rsi']:.1f}` → {sig['rsi_sig']}\n"
        f"{ie(sig['macd_sig'])} MACD → {sig['macd_sig']}\n"
        f"{ie(sig['ema_sig'])} EMA 50/200 → {sig['ema_sig']}\n"
        f"{ie(sig['bb_sig'])} Bollinger Bands → {sig['bb_sig']}\n"
        f"{ie(sig['vol_sig'])} Volume → {sig['vol_sig']}\n\n"
        f"📊 Buy: {sig['buy_count']}/5 | Sell: {sig['sell_count']}/5\n"
        f"━━━━━━━━━━━━━━━\n⚠️ _Not financial advice._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1H", callback_data=f"sig_{coin}_1h"),
             InlineKeyboardButton("4H", callback_data=f"sig_{coin}_4h"),
             InlineKeyboardButton("1D", callback_data=f"sig_{coin}_1d")],
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"signal_{coin}")]]))

async def top_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Top coins আনছি...", parse_mode="Markdown")
    coins = get_top_coins("volume")
    if not coins:
        await update.message.reply_text("❌ Data পাওয়া যায়নি।"); return
    lines = ["📊 *Top 10 by Volume*\n━━━━━━━━━━━━━━━"]
    for i, c in enumerate(coins, 1):
        sym = c.get('symbol','').upper()
        chg = c.get('price_change_percentage_24h', 0) or 0
        price = c.get('current_price', 0) or 0
        lines.append(f"{i}. *{sym}* `{fp(price)}` {'🟢' if chg>=0 else '🔴'} `{chg:+.2f}%`")
    await update.message.reply_text('\n'.join(lines), parse_mode="Markdown")

async def gainers_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Top gainers আনছি...", parse_mode="Markdown")
    coins = get_top_coins("gainers")
    lines = ["🔥 *Top 10 Gainers*\n━━━━━━━━━━━━━━━"]
    for i, c in enumerate(coins, 1):
        sym = c.get('symbol','').upper()
        chg = c.get('price_change_percentage_24h', 0) or 0
        price = c.get('current_price', 0) or 0
        lines.append(f"{i}. *{sym}* `{fp(price)}` 🟢 `+{chg:.2f}%`")
    await update.message.reply_text('\n'.join(lines), parse_mode="Markdown")

async def losers_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Top losers আনছি...", parse_mode="Markdown")
    coins = get_top_coins("losers")
    lines = ["📉 *Top 10 Losers*\n━━━━━━━━━━━━━━━"]
    for i, c in enumerate(coins, 1):
        sym = c.get('symbol','').upper()
        chg = c.get('price_change_percentage_24h', 0) or 0
        price = c.get('current_price', 0) or 0
        lines.append(f"{i}. *{sym}* `{fp(price)}` 🔴 `{chg:.2f}%`")
    await update.message.reply_text('\n'.join(lines), parse_mode="Markdown")

async def fg_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val, label = get_fear_greed()
    if not val:
        await update.message.reply_text("❌ Data পাওয়া যায়নি।"); return
    e = "😱" if val < 25 else "😨" if val < 45 else "😐" if val < 55 else "😄" if val < 75 else "🤑"
    bar = "█" * (val//10) + "░" * (10 - val//10)
    await update.message.reply_text(
        f"🌡️ *Fear & Greed Index*\n━━━━━━━━━━━━━━━\n"
        f"{e} Score: *{val}/100*\nLabel: *{label}*\n`[{bar}]`\n\n"
        f"_0=Extreme Fear | 100=Extreme Greed_", parse_mode="Markdown")

async def risk_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 4:
        await update.message.reply_text("Usage: `/risk 1000 2 3 6`\n(Capital Risk% SL% TP%)", parse_mode="Markdown"); return
    cap, rp, slp, tpp = float(ctx.args[0]), float(ctx.args[1]), float(ctx.args[2]), float(ctx.args[3])
    loss = cap * rp / 100
    pos = loss / (slp / 100)
    rr = tpp / slp
    await update.message.reply_text(
        f"🛡️ *Risk Calculator*\n━━━━━━━━━━━━━━━\n"
        f"💼 Capital: `${cap:,.2f}`\n⚠️ Max Loss: `${loss:.2f}`\n"
        f"📍 Position: `${pos:,.2f}`\n🔴 SL: `-{slp}%` | 🟢 TP: `+{tpp}%`\n"
        f"⚖️ R:R: `1:{rr:.1f}` {'✅ Good!' if rr>=2 else '⚠️ কম'}",
        parse_mode="Markdown")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.upper().strip()
    if 2 <= len(text) <= 10 and text.isalpha():
        ctx.args = [text]
        await price_cmd(update, ctx)
    else:
        await update.message.reply_text("Coin name লিখো: `BTC` `ETH` `SOL` `BNB` `DOGE`", parse_mode="Markdown")

async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    if d.startswith("price_"):
        coin = d.split("_")[1]
        t = get_ticker(coin)
        if t and float(t.get('lastPrice', 0)) > 0:
            p = float(t['lastPrice'])
            chg = float(t['priceChangePercent'])
            await q.edit_message_text(
                f"*{coin}/USD* — `{fp(p)}` {'🟢' if chg>=0 else '🔴'} `{chg:+.2f}%`\n"
                f"High: `{fp(float(t['highPrice']))}` | Low: `{fp(float(t['lowPrice']))}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚡ Signal", callback_data=f"signal_{coin}"),
                    InlineKeyboardButton("🔄", callback_data=f"price_{coin}")]]))

    elif d.startswith("signal_"):
        coin = d.split("_")[1]
        sig = get_signal(coin)
        if sig:
            await q.edit_message_text(
                f"⚡ *{coin}* → *{sig['overall']}*\n"
                f"{ie(sig['rsi_sig'])} RSI:`{sig['rsi']:.0f}` "
                f"{ie(sig['macd_sig'])} MACD:{sig['macd_sig']}\n"
                f"{ie(sig['ema_sig'])} EMA:{sig['ema_sig']} "
                f"{ie(sig['bb_sig'])} BB:{sig['bb_sig']}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"signal_{coin}")]]))

    elif d.startswith("sig_"):
        parts = d.split("_"); coin, tf = parts[1], parts[2]
        sig = get_signal(coin, tf)
        if sig:
            await q.edit_message_text(
                f"⚡ *{coin}* ({tf.upper()}) → *{sig['overall']}*\n"
                f"Buy:{sig['buy_count']}/5 | Sell:{sig['sell_count']}/5",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("1H", callback_data=f"sig_{coin}_1h"),
                    InlineKeyboardButton("4H", callback_data=f"sig_{coin}_4h"),
                    InlineKeyboardButton("1D", callback_data=f"sig_{coin}_1d")]]))

    elif d == "gainers":
        coins = get_top_coins("gainers")
        lines = ["🔥 *Top Gainers*"]
        for c in coins[:5]:
            sym = c.get('symbol','').upper()
            chg = c.get('price_change_percentage_24h', 0) or 0
            lines.append(f"*{sym}* 🟢 `+{chg:.2f}%`")
        await q.edit_message_text('\n'.join(lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄", callback_data="gainers")]]))

    elif d == "losers":
        coins = get_top_coins("losers")
        lines = ["📉 *Top Losers*"]
        for c in coins[:5]:
            sym = c.get('symbol','').upper()
            chg = c.get('price_change_percentage_24h', 0) or 0
            lines.append(f"*{sym}* 🔴 `{chg:.2f}%`")
        await q.edit_message_text('\n'.join(lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄", callback_data="losers")]]))

    elif d == "feargreed":
        val, label = get_fear_greed()
        e = "😱" if val and val<25 else "😨" if val and val<45 else "😐" if val and val<55 else "🤑"
        await q.edit_message_text(
            f"🌡️ Fear & Greed: *{val}/100* {e}\n_{label}_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄", callback_data="feargreed")]]))

    elif d == "topvolume":
        coins = get_top_coins("volume")
        lines = ["📊 *Top Volume*"]
        for c in coins[:5]:
            sym = c.get('symbol','').upper()
            chg = c.get('price_change_percentage_24h', 0) or 0
            lines.append(f"*{sym}* {'🟢' if chg>=0 else '🔴'} `{chg:+.2f}%`")
        await q.edit_message_text('\n'.join(lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄", callback_data="topvolume")]]))

# ============================================================
# MAIN
# ============================================================
def main():
    print("🚀 CryptoSignal PRO starting...")
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ Web server started!")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("signal", signal_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("gainers", gainers_cmd))
    app.add_handler(CommandHandler("losers", losers_cmd))
    app.add_handler(CommandHandler("fg", fg_cmd))
    app.add_handler(CommandHandler("risk", risk_cmd))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("✅ Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
