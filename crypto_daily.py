"""
Kripto Günlük Telegram Özeti
-----------------------------
crypto_ranker'ı çalıştırır, tüm sıralamayı (piyasa ruhu başlıkta) parçalar
halinde Telegram'a gönderir.

Ortam değişkenleri: TG_TOKEN, TG_CHAT_ID, (opsiyonel) COINGECKO_API_KEY
Çalıştır: python crypto_daily.py
"""

import os
import time
import requests
from crypto_ranker import build_ranking, market_mood_line

TOKEN = os.environ.get("TG_TOKEN")
# Kripto için ayrı grup: TG_CHAT_ID_CRYPTO varsa onu kullan,
# yoksa ortak TG_CHAT_ID'ye düş.
CHAT_ID = os.environ.get("TG_CHAT_ID_CRYPTO") or os.environ.get("TG_CHAT_ID")
CHUNK_SIZE = 20


def format_chunk(rows, part, total, mood) -> str:
    lines = [f"🪙 Kripto Günlük Sıralama ({part}/{total})"]
    if part == 1:
        lines.append(mood)
    lines.append("")
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for row in rows:
        badge = medals.get(int(row["Sıra"]), f"{int(row['Sıra'])}.")
        lines.append(f"{badge} {row['Coin']} — {row['SKOR']}")
        lines.append(f"    T:{row['Trend']}")
        lines.append(f"    R:{row['RSI']}  L:{row['Likidite']}  V:{row['Volatilite']}")
    if part == total:
        lines.append("")
        lines.append("Skor 0-100. Yatırım tavsiyesi değildir.")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=30)
    resp.raise_for_status()


def main():
    if not TOKEN or not CHAT_ID:
        raise SystemExit("TG_TOKEN ve TG_CHAT_ID ortam değişkenlerini tanımla.")

    mood = market_mood_line()
    table = build_ranking()
    rows = table.to_dict("records")
    chunks = [rows[i:i + CHUNK_SIZE] for i in range(0, len(rows), CHUNK_SIZE)]
    total = len(chunks)

    for i, chunk in enumerate(chunks, start=1):
        send_telegram(format_chunk(chunk, i, total, mood))
        print(f"Mesaj {i}/{total} gönderildi ✓")
        time.sleep(1)


if __name__ == "__main__":
    main()
