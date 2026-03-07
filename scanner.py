import requests
import pandas as pd
import numpy as np
import os

# GitHub Secrets verileri
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# STRATEJİ LİMİTLERİN
RSI_LIMIT = 70
CHANGE_24H_LIMIT = 8
WHALE_WALL_RATIO = 2.5

def send_telegram(msg):
    if TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            res = requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        except Exception as e:
            print(f"Bağlantı Hatası: {e}")

def get_data(endpoint, params={}):
    base = "https://www.okx.com"
    try:
        res = requests.get(base + endpoint, params=params, timeout=10).json()
        return res.get('data', [])
    except: return []

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_market_trend():
    btc = get_data("/api/v5/market/tickers", {"instId": "BTC-USDT-SWAP"})
    if btc:
        change = (float(btc[0]['last']) / float(btc[0]['open24h']) - 1) * 100
        return f"%{round(change, 2)} {'📉' if change < 0 else '📈'}"
    return "BELİRSİZ"

def check_whale_walls(symbol):
    depth = get_data("/api/v5/market/books", {"instId": symbol, "sz": "100"}) # Derinlik artırıldı
    if not depth: return 1, 0
    asks = sum([float(a[1]) for a in depth[0]['asks']])
    bids = sum([float(b[1]) for b in depth[0]['bids']])
    return (asks / bids if bids > 0 else 1), asks

def check_reversal_15m(symbol):
    """15 dakikalıkta kapanış onayı: Son tepeyi geçememe durumu"""
    m15 = get_data("/api/v5/market/candles", {"instId": symbol, "bar": "15m", "limit": "5"})
    if not m15: return False
    
    # 0:güncel, 1:önceki mum | Indexler -> 2:High, 4:Close
    curr_close = float(m15[0][4])
    prev_high = float(m15[1][2])
    
    # Eğer güncel kapanış önceki tepenin altındaysa 'Güç Kaybı' vardır
    return curr_close < prev_high

def scan():
    print("Tarama başlatıldı (📉 [SHORT BOTU])...")
    trend = get_market_trend()
    tickers = get_data("/api/v5/market/tickers", {"instType": "SWAP"})
    tickers = sorted(tickers, key=lambda x: float(x['vol24h']), reverse=True)
    
    signals = []
    for t in tickers:
        symbol = t['instId']
        if "-USDT-" not in symbol: continue
        
        change = (float(t['last']) / float(t['open24h']) - 1) * 100
        if change > CHANGE_24H_LIMIT:
            candles = get_data("/api/v5/market/candles", {"instId": symbol, "bar": "1H", "limit": "50"})
            if not candles: continue
            
            df = pd.DataFrame(candles, columns=['ts','o','h','l','c','v','vc','vq','conf'])
            df['c'] = df['c'].astype(float)
            df['v'] = df['v'].astype(float)
            
            # RSI ve Hacim Onayı (Tükeniş kontrolü)
            rsi_series = calculate_rsi(df['c'][::-1]).reset_index(drop=True)
            rsi = rsi_series.iloc[-1]
            avg_vol = df['v'].iloc[1:21].mean()
            curr_vol = df['v'].iloc[0]
            
            # ANA FİLTRELER + 15M TREND KIRILIMI ONAYI
            if (rsi > RSI_LIMIT or curr_vol > avg_vol * 2.5):
                if check_reversal_15m(symbol): # İŞTE KRİTİK ONAY BURASI
                    funding = get_data("/api/v5/public/funding-rate", {"instId": symbol})
                    f_rate = float(funding[0]['fundingRate']) * 100 if funding else 0
                    wall_ratio, _ = check_whale_walls(symbol)
                    
                    msg = (f"📉 [SHORT BOTU]\n"
                           f"🚨 *SİNYAL: {symbol}*\n"
                           f"🌍 BTC 24s: {trend}\n"
                           f"📈 Değişim: %{round(change, 2)}\n"
                           f"📊 RSI (1H): {round(rsi, 2)}\n"
                           f"💸 Funding: %{round(f_rate, 4)}\n"
                           f"🧱 Balina: {round(wall_ratio, 1)}x\n"
                           f"✅ *15M Güç Kaybı Onaylandı*")
                    signals.append(msg)
                    if len(signals) >= 5: break # Telegram limitine takılmamak için

    if signals:
        for s in signals: # Tek tek gönderim (Garanti yöntem)
            send_telegram(s)
        print(f"Başarılı! {len(signals)} sinyal gönderildi.")
    else:
        print("Uygun kriterlerde ve dönüş onayı almış coin bulunamadı.")

if __name__ == "__main__":
    scan()
