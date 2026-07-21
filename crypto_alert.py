"""
Kripto Saatlik Uyarı Botu (dedup'lı)
-------------------------------------
Saat başı çalışır (kripto 7/24), skoru eşiği geçen coinleri Telegram'a
listeler. Aynı coini günde BİR kez uyarır (crypto_alerted_state.json).

EŞİK 80: Kripto çok sayıda coin içerdiğinden yüksek tutuldu; sadece
güçlü kurulumlar geçsin. Gerçek dağılımı görünce aşağıdan ayarla.

Ortam değişkenleri: TG_TOKEN, TG_CHAT_ID, (opsiyonel) COINGECKO_API_KEY
Çalıştır: python crypto_alert.py
"""

import os
import json
import datetime
import requests
from crypto_ranker import build_ranking, market_mood_line

TOKEN = os.environ.get("TG_TOKEN")
# Kripto için ayrı grup: TG_CHAT_ID_CRYPTO varsa onu kullan,
# yoksa ortak TG_CHAT_ID'ye düş.
CHAT_ID = os.environ.get("TG_CHAT_ID_CRYPTO") or os.environ.get("TG_CHAT_ID")
THRESHOLD = 80
STATE_FILE = "crypto_alerted_state.json"


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    today = datetime.date.today().isoformat()
    pruned = {k: v for k, v in state.items() if v == today}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2)


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=30)
    resp.raise_for_status()


def main():
    if not TOKEN or not CHAT_ID:
        raise SystemExit("TG_TOKEN ve TG_CHAT_ID ortam değişkenlerini tanımla.")

    today = datetime.date.today().isoformat()
    state = load_state()

    mood = market_mood_line()
    table = build_ranking()
    hits = table[table["SKOR"] >= THRESHOLD]

    new_hits = [row for _, row in hits.iterrows()
                if state.get(row["Coin"]) != today]

    if not new_hits:
        print("Yeni uyarı yok (eşik altı ya da hepsi bugün zaten uyarıldı).")
        save_state(state)
        return

    lines = [f"🚨 {THRESHOLD}+ Kripto Fırsatları ({len(new_hits)} adet)", mood, ""]
    for row in new_hits:
        lines.append(f"{row['Coin']} — {row['SKOR']}")
        lines.append(f"    T:{row['Trend']}")
        lines.append(f"    R:{row['RSI']}  L:{row['Likidite']}  V:{row['Volatilite']}")
        state[row["Coin"]] = today

    send_telegram("\n".join(lines))
    save_state(state)
    print(f"Gönderildi: {len(new_hits)} yeni coin.")


if __name__ == "__main__":
    main()
