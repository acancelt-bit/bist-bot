"""
BİST 100 Sıralama Motoru (Türkçe haber destekli)
------------------------------------------------
Skorlama: TEKNİK (SMA50/200 + RSI) + ANALİST (yfinance) + HABER.
Haber ayağı artık turkish_news modülünden gelir: Google News RSS
(Türkçe) + Türkçe BERT duygu modeli. Böylece BİST'te haber gerçek
sinyal taşır (NASDAQ'taki İngilizce yfinance haberinin aksine).

Veri gerçeği:
  * Analist verisi yfinance'te Türk hisseleri için çoğu zaman yok;
    o yüzden ağırlığı düşük tuttum (tabloda "veri yok" olarak görünür).
  * Haber artık Türkçe kaynaktan geldiği için ağırlığı yükselttim.

İki profil (build_ranking(use_news=...) seçer):
  use_news=True  -> teknik .50 / analist .15 / haber .35   (günlük rapor)
  use_news=False -> teknik .75 / analist .25               (saatlik uyarı,
                    hız için haber kapalı — BERT her hisse için ağırdır)

Kurulum: pip install yfinance pandas feedparser transformers torch
Çalıştır: python bist100_ranker.py
Not: Eğitim amaçlıdır, yatırım tavsiyesi değildir.
"""

import yfinance as yf
import pandas as pd

# İki profil: haber AÇIK (Türkçe haber gerçek sinyal) ve haber KAPALI
# (hızlı teknik tarama; saatlik uyarı için). build_ranking(use_news=...)
# hangisini kullanacağını seçer.
WEIGHTS_WITH_NEWS = {"teknik": 0.50, "analist": 0.15, "haber": 0.35}
WEIGHTS_NO_NEWS = {"teknik": 0.75, "analist": 0.25}  # haber devre dışı
NEWS_LIMIT = 8

# Türkçe haber+duygu modülü (opsiyonel). Yoksa haber nötre düşer.
try:
    from turkish_news import turkish_news_score
    _TR_NEWS = True
except Exception as e:
    print(f"turkish_news modülü yüklenemedi ({type(e).__name__}), "
          f"haber nötr (50) olacak.")
    _TR_NEWS = False

# BİST 100 hisseleri (Yahoo Finance formatı: sembol + .IS).
# NOT: Endeks bileşimi 3 ayda bir revize edilir; listeyi periyodik
# olarak güncelle. Buradaki liste likit BİST isimlerinden derlenmiştir.
BIST100_SYMBOLS = [
    # Bankalar / finans
    "AKBNK", "GARAN", "ISCTR", "YKBNK", "HALKB", "VAKBN", "TSKB", "SKBNK", "ALBRK",
    # Holdingler
    "KCHOL", "SAHOL", "DOHOL", "AGHOL", "ENKAI", "ALARK", "TKFEN",
    # Ulaştırma / havacılık
    "THYAO", "PGSUS", "TAVHL", "CLEBI",
    # Telekom
    "TCELL", "TTKOM",
    # Enerji / rafineri / kimya
    "TUPRS", "PETKM", "SASA", "HEKTS", "GUBRF", "BAGFS", "ALKIM",
    "AKSEN", "ENJSA", "ZOREN", "ODAS", "AKSA", "GWIND", "BIOEN",
    "SMRTG", "KONTR", "ASTOR", "EUPWR", "AYDEM", "CWENE",
    # Demir-çelik / metal
    "EREGL", "KRDMD", "ISDMR", "KLMSN",
    # Otomotiv ve yan sanayi
    "FROTO", "TOASO", "ARCLK", "TTRAK", "OTKAR", "VESTL", "VESBE",
    "EGEEN", "BFREN", "KORDS", "BRISA",
    # Teknoloji / savunma
    "ASELS", "LOGO", "KAREL", "INDES", "ARENA", "ALCTL", "NETAS", "PKART", "PENTA",
    # Perakende / dağıtım
    "BIMAS", "MGROS", "SOKM", "BIZIM", "MAVI", "TKNSA", "SELEC",
    # Gıda / içecek
    "ULKER", "CCOLA", "AEFES", "PNSUT", "KRVGD", "TATGD",
    # Çimento
    "AKCNS", "CIMSA", "OYAKC", "NUHCM",
    # Cam
    "SISE", "TRKCM", "ANACM",
    # Madencilik
    "KOZAL", "KOZAA", "IPEKE", "PRKME",
    # GYO
    "EKGYO", "ISGYO", "TRGYO", "HLGYO",
    # Sağlık
    "MPARK", "LKMNH", "DEVA",
    # Kağıt / diğer sanayi
    "KARTN", "TIRE",
    # Medya / turizm / mobilya
    "HURGZ", "MAALT", "YATAS",
]

BIST100_TICKERS = [f"{s}.IS" for s in BIST100_SYMBOLS]


REC_MAP = {
    "strong_buy": 100, "buy": 80, "hold": 50,
    "underperform": 25, "sell": 0,
}


def rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return float((100 - 100 / (1 + rs)).iloc[-1])


def technical_score(ticker: str) -> tuple[float, str]:
    df = yf.download(ticker, period="1y", interval="1d",
                     progress=False, auto_adjust=True)
    close = df["Close"].squeeze()
    price = float(close.iloc[-1])
    s50 = float(close.rolling(50).mean().iloc[-1])
    s200 = float(close.rolling(200).mean().iloc[-1])
    r = rsi(close)

    score = 0.0
    score += 30 if price > s200 else 0
    score += 30 if s50 > s200 else 0
    if r < 30:
        score += 40
    elif r > 70:
        score += 5
    else:
        score += 40 * (70 - r) / 40

    detail = f"RSI {r:.0f}, {'↑trend' if s50 > s200 else '↓trend'}"
    return min(score, 100), detail


def analyst_score(ticker: str) -> tuple[float, str]:
    info = yf.Ticker(ticker).info
    price = info.get("currentPrice")
    target = info.get("targetMeanPrice")
    rec = info.get("recommendationKey", "hold")

    upside = (target / price - 1) * 100 if price and target else 0
    upside_score = max(0, min(100, (upside + 20) * 2))
    rec_score = REC_MAP.get(rec, 50)

    score = 0.6 * upside_score + 0.4 * rec_score
    # Veri yoksa bunu açıkça belli et ki tabloya bakınca anlaşılsın.
    if not target:
        detail = "veri yok"
    else:
        detail = f"hedef %{upside:+.0f}, {rec}"
    return score, detail


def news_score(ticker: str) -> tuple[float, str]:
    """Türkçe haber duygu skoru (turkish_news modülü). Yoksa nötr döner."""
    if not _TR_NEWS:
        return 50.0, "modül yok"
    symbol = ticker.replace(".IS", "")
    return turkish_news_score(symbol, NEWS_LIMIT)


def build_ranking(tickers: list[str] | None = None,
                  use_news: bool = True) -> pd.DataFrame:
    """
    BİST100 hisselerini analiz eder, skora göre sıralar.
    use_news=True  -> Türkçe haber duygusu dahil (günlük rapor için).
    use_news=False -> hızlı teknik tarama (saatlik uyarı için).
    """
    if tickers is None:
        tickers = BIST100_TICKERS
    weights = WEIGHTS_WITH_NEWS if use_news else WEIGHTS_NO_NEWS

    rows = []
    for t in tickers:
        print(f"Analiz ediliyor: {t} ...")
        try:
            tek, tek_d = technical_score(t)
            ana, ana_d = analyst_score(t)
            if use_news:
                hab, hab_d = news_score(t)
            else:
                hab, hab_d = 0.0, "kapalı"
        except Exception as e:
            print(f"  {t} atlandı: {type(e).__name__}: {e}")
            continue

        toplam = weights["teknik"] * tek + weights["analist"] * ana
        if use_news:
            toplam += weights["haber"] * hab

        rows.append({
            "Hisse": t.replace(".IS", ""),   # mesajda .IS'siz göster
            "SKOR": round(toplam, 1),
            "Teknik": f"{tek:.0f} ({tek_d})",
            "Analist": f"{ana:.0f} ({ana_d})",
            "Haber": (f"{hab:.0f} ({hab_d})" if use_news else "—"),
        })

    table = pd.DataFrame(rows).sort_values("SKOR", ascending=False)
    table.insert(0, "Sıra", range(1, len(table) + 1))
    return table


def main():
    table = build_ranking(use_news=True)
    print("\n=== BİST 100 — Alınabilirlik Sıralaması ===\n")
    print(table.to_string(index=False))
    print("\nSkor 0-100: yüksek = alım koşulları güçlü, düşük = zayıf.")
    print("Not: Teknik momentum + Türkçe haber duygusu. Analist verisi "
          "BİST'te zayıftır. Eğitim amaçlıdır, yatırım tavsiyesi değildir.")


if __name__ == "__main__":
    main()
