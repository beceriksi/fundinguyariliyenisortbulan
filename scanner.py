import requests
import pandas as pd
import os
import time

# Ayarlar
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
BYBIT_BASE = "https://api.bybit.com"

def send_telegram(msg):
    if TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        except: pass

def get_data(endpoint, params={}):
    try:
        res = requests.get(BYBIT_BASE + endpoint, params=params, timeout=10).json()
        return res['result'].get('list', []) if res['retCode'] == 0 else []
    except: return []

def get_orderbook_liquidity(symbol, current_price):
    """
    Emir defterindeki (Asks) yığılmayı kaldıraç patlama noktalarına göre ölçer.
    """
    depth = get_data("/v5/market/orderbook", {"category": "linear", "symbol": symbol, "limit": "200"})
    if not depth or 'a' not in depth[0]: return None
    
    asks = depth[0]['a'] # [Fiyat, Miktar]
    
    # Kaldıraç Patlama Hesapları (Shortlar için yukarı yönlü)
    # 50x likidasyon genelde %1.8 - %2.0 yukarıdadır
    # 25x likidasyon genelde %3.8 - %4.0 yukarıdadır
    levels = {
        "50x": current_price * 1.02,
        "25x": current_price * 1.04
    }
    
    analysis = {}
    for label, price in levels.items():
        # Belirlenen fiyat seviyesine kadar olan toplam satış emri (stop-loss) hacmi
        total_vol = sum([float(a[1]) for a in asks if float(a[0]) <= price])
        analysis[label] = {"price": round(price, 4), "vol": round(total_vol, 2)}
        
    return analysis

def scan():
    print("Likidasyon taraması başladı...")
    tickers = get_data("/v5/market/tickers", {"category": "linear"})
    
    for t in tickers:
        symbol = t['symbol']
        if not symbol.endswith("USDT"): continue
        
        last_price = float(t['lastPrice'])
        funding = float(t['fundingRate']) * 100
        change = float(t['price24hPcnt']) * 100
        
        # KRİTER: Fonlama negatifse ve fiyat hareketliyse mercek altına al
        if funding < -0.04:
            liq = get_orderbook_liquidity(symbol, last_price)
            if not liq: continue
            
            # Eğer 50x patlama noktasında ciddi birikmiş hacim varsa bildir
            msg = (
                f"🚨 *LİKİDASYON ANALİZİ: {symbol}*\n"
                f"💰 Fiyat: `{last_price}`\n"
                f"💸 Funding: `% {round(funding, 4)}`\n"
                f"📈 24s Değişim: `% {round(change, 2)}`\n\n"
                f"🔥 *SHORT PATLATMA NOKTALARI (Liq):*\n"
                f"• *50x:* `{liq['50x']['price']}` seviyesine kadar `{liq['50x']['vol']}` adet birikme var.\n"
                f"• *25x:* `{liq['25x']['price']}` seviyesine kadar `{liq['25x']['vol']}` adet birikme var.\n\n"
                f"⚠️ *Strateji:* Fiyat `{liq['50x']['price']}` üzerine iğne atıp dönerse, shortçular temizlenmiş olur."
            )
            
            send_telegram(msg)
            print(f"Sinyal Gönderildi: {symbol}")
            time.sleep(1) # Telegram limitlerine takılmamak için

if __name__ == "__main__":
    scan()
