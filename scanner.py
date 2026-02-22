import requests
import pandas as pd
import os
import time

# Ayarlar
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
OKX_BASE = "https://www.okx.com"

def send_telegram(msg):
    if TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        except: pass

def get_okx_data(endpoint, params={}):
    try:
        res = requests.get(OKX_BASE + endpoint, params=params, timeout=10).json()
        return res.get('data', [])
    except: return []

def get_orderbook_analysis(symbol, current_price):
    """
    OKX Orderbook üzerinden likidasyon seviyelerindeki hacmi hesaplar.
    """
    # sz: 100 ile derin bir tahta okuyoruz
    depth = get_okx_data("/api/v5/market/books", {"instId": symbol, "sz": "100"})
    if not depth: return None
    
    asks = depth[0]['asks'] # [Fiyat, Miktar, ...]
    
    # Kaldıraç Patlama Hesapları (Shortlar için yukarı yönlü)
    # 50x likidasyon: %2 yukarıda | 25x likidasyon: %4 yukarıda
    levels = {
        "50x": current_price * 1.02,
        "25x": current_price * 1.04
    }
    
    analysis = {}
    for label, target_price in levels.items():
        # Belirlenen fiyata kadar olan toplam kontrat miktarı
        total_vol = sum([float(a[1]) for a in asks if float(a[0]) <= target_price])
        analysis[label] = {"price": round(target_price, 4), "vol": round(total_vol, 2)}
        
    return analysis

def scan():
    print("OKX Tarama Başlatıldı (Likidasyon Analizi)...")
    # Tüm SWAP (Vadeli) pariteleri çek
    tickers = get_okx_data("/api/v5/market/tickers", {"instType": "SWAP"})
    
    for t in tickers:
        symbol = t['instId']
        if "-USDT-SWAP" not in symbol: continue
        
        last_price = float(t['last'])
        open_24h = float(t['open24h'])
        change = ((last_price / open_24h) - 1) * 100
        
        # 1. Aşama: Funding Oranını Çek
        funding_data = get_okx_data("/api/v5/public/funding-rate", {"instId": symbol})
        if not funding_data: continue
        funding = float(funding_data[0]['fundingRate']) * 100
        
        # STRATEJİ: Sert yükselen VE fonlaması negatif koinlere bak
        # (Shortçuların kapana kısıldığı yerler)
        if change > 5 and funding < -0.03:
            
            # 2. Aşama: Matematiksel Likidite Analizi
            liq = get_orderbook_analysis(symbol, last_price)
            if not liq: continue
            
            msg = (
                f"🚨 *OKX LİKİDASYON ANALİZİ: {symbol}*\n"
                f"💰 Fiyat: `{last_price}`\n"
                f"📈 24s Değişim: `% {round(change, 2)}`\n"
                f"💸 Funding: `% {round(funding, 4)}` (Negatif!)\n\n"
                f"🔥 *SHORT PATLATMA NOKTALARI (Liq):*\n"
                f"• *50x:* `{liq['50x']['price']}` seviyesine kadar `{liq['50x']['vol']}` kontrat yığılmış.\n"
                f"• *25x:* `{liq['25x']['price']}` seviyesine kadar `{liq['25x']['vol']}` kontrat yığılmış.\n\n"
                f"⚠️ *Strateji:* Fiyat `{liq['50x']['price']}` üzerine iğne atarsa shortçular likit olur. İğne ucu dönüşünü bekle!"
            )
            
            send_telegram(msg)
            print(f"Sinyal Bulundu: {symbol}")
            time.sleep(1) # Telegram limitleri için

if __name__ == "__main__":
    scan()
