"""
BİST 100 Saatlik Uyarı Botu
-----------------------------
Piyasa saatlerinde saat başı çalışır, skoru eşiği geçen TÜM hisseleri
Telegram'a listeler.

NEDEN EŞİK 70 (NASDAQ'ta 90'dı)?
  BİST'te analist/haber verisi zayıf olduğu için skorlar ~40-75
  bandına SIKIŞIR; 90 eşiği pratikte hiç tetiklenmez. 70, BİST'in
  gerçek skor dağılımına göre "güçlü teknik momentum" seviyesidir.
  İstersen aşağıdan oynat.

Hafıza/tekrar kontrolü yoktur: bir hisse üst üste eşiği geçerse her
saat tekrar listelenir. (Tekrarları istemezsen söyle, gün-içi dedup
ekleriz.)

Ortam değişkenleri: TG_TOKEN, TG_CHAT_ID
Çalıştır: python bist100_alert.py
"""

import os
import requests
from bist100_ranker import build_ranking

TOKEN = os.environ.get("TG_TOKEN")
CHAT_ID = os.environ.get("TG_CHAT_ID")
THRESHOLD = 70


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=30)
    resp.raise_for_status()


def main():
    if not TOKEN or not CHAT_ID:
        raise SystemExit("TG_TOKEN ve TG_CHAT_ID ortam değişkenlerini tanımla.")

    # Saatlik uyarıda haber KAPALI: 100 hisse için Türkçe BERT çıkarımı
    # her saat çok ağır olurdu. Hızlı teknik tarama yapılır.
    table = build_ranking(use_news=False)
    hits = table[table["SKOR"] >= THRESHOLD]

    if hits.empty:
        print(f"Şu an {THRESHOLD} üstünde hisse yok, mesaj gönderilmedi.")
        return

    lines = [f"🚨 {THRESHOLD} Üstü BİST Hisseleri ({len(hits)} adet)", ""]
    for _, row in hits.iterrows():
        lines.append(f"{row['Hisse']} — {row['SKOR']}")
        lines.append(f"    T:{row['Teknik']}")
        lines.append(f"    A:{row['Analist']}")
        lines.append(f"    H:{row['Haber']}")

    send_telegram("\n".join(lines))
    print(f"Gönderildi: {len(hits)} hisse.")


if __name__ == "__main__":
    main()
