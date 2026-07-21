"""
BİST 100 Günlük Telegram Raporu
---------------------------------
Her sabah (piyasa açılmadan önce) tüm BİST 100 hisselerini sıralar
ve Telegram'a gönderir. 4096 karakter sınırı yüzünden rapor parçalar
halinde (her mesajda ~20 hisse) gider.

Ortam değişkenleri: TG_TOKEN, TG_CHAT_ID
Çalıştır: python bist100_daily.py
"""

import os
import time
import requests
from bist100_ranker import build_ranking

TOKEN = os.environ.get("TG_TOKEN")
CHAT_ID = os.environ.get("TG_CHAT_ID")
CHUNK_SIZE = 20


def format_chunk(rows, part, total_parts) -> str:
    lines = [f"📊 BİST 100 Günlük Sıralama ({part}/{total_parts})", ""]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for row in rows:
        badge = medals.get(int(row["Sıra"]), f"{int(row['Sıra'])}.")
        lines.append(f"{badge} {row['Hisse']} — {row['SKOR']}")
        lines.append(f"    T:{row['Teknik']}")
        lines.append(f"    A:{row['Analist']}")
        lines.append(f"    H:{row['Haber']}")
    if part == total_parts:
        lines.append("")
        lines.append("Skor esasen teknik momentuma dayanır. "
                     "Yatırım tavsiyesi değildir.")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=30)
    resp.raise_for_status()


def main():
    if not TOKEN or not CHAT_ID:
        raise SystemExit("TG_TOKEN ve TG_CHAT_ID ortam değişkenlerini tanımla.")

    table = build_ranking(use_news=True)  # Türkçe haber duygusu dahil
    rows = table.to_dict("records")
    chunks = [rows[i:i + CHUNK_SIZE] for i in range(0, len(rows), CHUNK_SIZE)]
    total = len(chunks)

    for i, chunk in enumerate(chunks, start=1):
        send_telegram(format_chunk(chunk, i, total))
        print(f"Mesaj {i}/{total} gönderildi ✓")
        time.sleep(1)


if __name__ == "__main__":
    main()
