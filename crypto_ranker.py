"""
Kripto Sıralama Motoru (CoinGecko + Korku&Açgözlülük)
------------------------------------------------------
İlk 100 coini (piyasa değerine göre) tek CoinGecko çağrısıyla çeker,
teknik + piyasa yapısı sinyalleriyle 0-100 puanlar. Analist ayağı YOK
(kriptoda karşılığı yok).

Sinyaller (coin başına):
  TREND      %40 : 24s/7g/30g yön hizası + ÖLÇÜLÜ 7g momentum
                   (parabolik/pompa hareket cezalı, tükenmiş yükseliş değil)
  RSI        %20 : 7 günlük mini grafikten kısa RSI (aşırı satım bonus)
  VOLATİLİTE %25 : mini grafikten oynaklık (aşırı uçuk = ceza)
  LİKİDİTE   %15 : wash-trade/pump şüphesi cezası (hacim > piyasa değeri)
                   + SERT FİLTRE (düşük mutlak hacim = elenir)
Korku&Açgözlülük: piyasa geneli (coin başına değil), rapor başlığında.

Sert filtre (sıralamadan ELENİR): stablecoin/peg/wrapped tokenlar,
düşük hacimli (gürültü) coinler.

Veri: CoinGecko Demo API (anahtarsız çalışır; COINGECKO_API_KEY
ortam değişkeni verilirse limit 100 çağrı/dk'ya çıkar).
Korku&Açgözlülük: alternative.me ücretsiz API.

Kurulum: pip install requests pandas
Çalıştır: python crypto_ranker.py
Not: Eğitim amaçlıdır, yatırım tavsiyesi değildir.
"""

import os
import time
import statistics
import requests
import pandas as pd

CG_BASE = "https://api.coingecko.com/api/v3"
CG_KEY = os.environ.get("COINGECKO_API_KEY")  # opsiyonel
TOP_N = 100
VS = "usd"

WEIGHTS = {"trend": 0.40, "rsi": 0.20, "likidite": 0.15, "volatilite": 0.25}

# Sert filtre eşikleri
MIN_VOLUME_USD = 3_000_000
MIN_MCAP_USD = 30_000_000

# Momentum taşımayan / tekrarlı coinler: stablecoin + altın-peg + wrapped
EXCLUDE_SYMBOLS = {
    "usdt", "usdc", "dai", "usde", "usds", "fdusd", "pyusd", "tusd", "usdd",
    "usd1", "busd", "gusd", "frax", "lusd", "usdp", "eurt", "eurc", "usdg",
    "xaut", "paxg",
    "wbtc", "weth", "wsteth", "steth", "wbeth", "weeth", "reth", "cbeth",
}


def _headers() -> dict:
    return {"x-cg-demo-api-key": CG_KEY} if CG_KEY else {}


def fetch_markets(top_n: int = TOP_N) -> list:
    """İlk N coini tek çağrıda piyasa verisiyle çeker (429'da yeniden dener)."""
    url = f"{CG_BASE}/coins/markets"
    params = {
        "vs_currency": VS, "order": "market_cap_desc",
        "per_page": top_n, "page": 1, "sparkline": "true",
        "price_change_percentage": "1h,24h,7d,30d",
    }
    for attempt in range(3):
        r = requests.get(url, params=params, headers=_headers(), timeout=30)
        if r.status_code == 429:
            print("CoinGecko 429 (rate limit), 15sn bekleniyor...")
            time.sleep(15)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return []


def fetch_fear_greed() -> tuple:
    """Piyasa geneli Korku&Açgözlülük (0-100) + sınıf. Hata olursa (None, None)."""
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=15)
        r.raise_for_status()
        d = r.json()["data"][0]
        return int(d["value"]), d["value_classification"]
    except Exception as e:
        print(f"Korku&Açgözlülük alınamadı: {type(e).__name__}")
        return None, None


def rsi_from_prices(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        ch = prices[i] - prices[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def trend_score(c: dict) -> tuple:
    p24 = c.get("price_change_percentage_24h_in_currency") or 0.0
    p7 = c.get("price_change_percentage_7d_in_currency") or 0.0
    p30 = c.get("price_change_percentage_30d_in_currency") or 0.0
    pos = sum(1 for x in (p24, p7, p30) if x > 0)
    base = pos / 3 * 50                       # yön hizası: 0-50
    # 7g momentumu: ölçülü yükseliş iyi, parabolik hareket cezalı
    if p7 <= 0:
        mom = 0.0
    elif p7 <= 15:
        mom = p7 / 15 * 50                    # 0..15% -> 0..50 (sağlıklı ivme)
    elif p7 <= 40:
        mom = 50.0                            # sağlıklı bölge
    else:
        mom = max(0.0, 50 - (p7 - 40))        # aşırı ısınma: 40%->50, 90%->0
    return min(100.0, base + mom), f"24s{p24:+.0f} 7g{p7:+.0f} 30g{p30:+.0f}"


def rsi_score(c: dict) -> tuple:
    spark = (c.get("sparkline_in_7d") or {}).get("price") or []
    r = rsi_from_prices(spark)
    if r < 30:
        s = 100.0
    elif r > 70:
        s = 25.0
    else:
        s = 100 - (r - 30) * (75 / 40)       # 30->100, 70->25 doğrusal
    return s, f"RSI {r:.0f}"


def liquidity_score(c: dict) -> tuple:
    # Mutlak hacim zaten sert filtrede elendiği için burada sadece
    # wash-trade/pump şüphesini (hacim > piyasa değeri) cezalıyoruz.
    # Büyük-cap'in düşük devir hızı normaldir, cezalandırılmaz.
    vol = c.get("total_volume") or 0
    mcap = c.get("market_cap") or 0
    turnover = vol / mcap if mcap else 0
    if turnover > 1.0:
        s = 40.0                              # hacim > mcap: wash/pump şüphesi
    elif turnover > 0.5:
        s = 70.0
    else:
        s = 100.0                             # normal (büyük-cap düşük devir dahil)
    return s, f"devir %{turnover*100:.0f}"


def volatility_score(c: dict) -> tuple:
    spark = (c.get("sparkline_in_7d") or {}).get("price") or []
    if len(spark) < 3:
        return 50.0, "oyn ?"
    rets = [(spark[i] - spark[i - 1]) / spark[i - 1]
            for i in range(1, len(spark)) if spark[i - 1]]
    vol = statistics.pstdev(rets) if rets else 0
    if vol <= 0.01:
        s = 100.0
    elif vol >= 0.06:
        s = 20.0
    else:
        s = 100 - (vol - 0.01) * (80 / 0.05)
    return s, f"oyn %{vol*100:.1f}"


def passes_filter(c: dict) -> bool:
    sym = (c.get("symbol") or "").lower()
    if sym in EXCLUDE_SYMBOLS:
        return False
    if (c.get("total_volume") or 0) < MIN_VOLUME_USD:
        return False
    if (c.get("market_cap") or 0) < MIN_MCAP_USD:
        return False
    return True


def build_ranking(top_n: int = TOP_N) -> pd.DataFrame:
    coins = fetch_markets(top_n)
    rows = []
    for c in coins:
        if not passes_filter(c):
            continue
        tr, tr_d = trend_score(c)
        rs, rs_d = rsi_score(c)
        lq, lq_d = liquidity_score(c)
        vo, vo_d = volatility_score(c)
        total = (WEIGHTS["trend"] * tr + WEIGHTS["rsi"] * rs
                 + WEIGHTS["likidite"] * lq + WEIGHTS["volatilite"] * vo)
        rows.append({
            "Coin": (c.get("symbol") or "").upper(),
            "SKOR": round(total, 1),
            "Trend": f"{tr:.0f} ({tr_d})",
            "RSI": f"{rs:.0f} ({rs_d})",
            "Likidite": f"{lq:.0f} ({lq_d})",
            "Volatilite": f"{vo:.0f} ({vo_d})",
        })

    table = pd.DataFrame(rows).sort_values("SKOR", ascending=False)
    table.insert(0, "Sıra", range(1, len(table) + 1))
    return table


def market_mood_line() -> str:
    val, cls = fetch_fear_greed()
    if val is None:
        return "Piyasa ruhu: (alınamadı)"
    tr = {"Extreme Fear": "Aşırı Korku", "Fear": "Korku", "Neutral": "Nötr",
          "Greed": "Açgözlülük", "Extreme Greed": "Aşırı Açgözlülük"}.get(cls, cls)
    return f"Piyasa ruhu: {val}/100 ({tr})"


def main():
    print(market_mood_line())
    table = build_ranking()
    print(f"\n=== Kripto — İlk {TOP_N}'de Filtreyi Geçen {len(table)} Coin ===\n")
    print(table.to_string(index=False))
    print("\nSkor 0-100. Teknik + piyasa yapısı. "
          "Eğitim amaçlıdır, yatırım tavsiyesi değildir.")


if __name__ == "__main__":
    main()
