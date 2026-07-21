"""
Türkçe Haber Duygu Modülü (BİST için)
--------------------------------------
Bir BİST hissesi için Türkçe haber başlıklarını Google News RSS'ten
çeker ve Türkçe bir BERT duygu modeliyle skorlar.

Haber kaynağı : Google News RSS (hl=tr, gl=TR) — API anahtarı gerektirmez,
                şirket adına göre son 7 günün Türkçe haberlerini getirir.
                (Önemli KAP açıklamaları da haber olarak buraya düşer.)
Duygu modeli  : savasy/bert-base-turkish-sentiment-cased (HuggingFace).
                İlk çalıştırmada ~model iner, sonra cache'ten hızlı gelir.

Kurulum: pip install feedparser transformers torch requests
Test    : python turkish_news.py

Dürüstlük notu: Bu modeli/RSS'i sandbox'tan test EDEMEDİM (ağ kısıtı).
Etiket isimleri modele göre değişebilir; ilk çalıştırmada modül ham
etiketi bir kez ekrana basar — beklenmedik bir şey görürsen _label_to_signed
içindeki eşlemeyi ona göre güncelle.
"""

import time
import urllib.parse
import requests

NEWS_LIMIT = 8
RSS_TIMEOUT = 15
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# Ticker -> daha isabetli arama için şirket adı. Listede olmayanlar için
# "{ticker} hisse borsa" sorgusuna düşülür. İstediğin kadar genişlet.
NAME_MAP = {
    "THYAO": "Türk Hava Yolları", "GARAN": "Garanti BBVA", "AKBNK": "Akbank",
    "ISCTR": "İş Bankası", "YKBNK": "Yapı Kredi", "HALKB": "Halkbank",
    "VAKBN": "VakıfBank", "KCHOL": "Koç Holding", "SAHOL": "Sabancı Holding",
    "ASELS": "Aselsan", "TUPRS": "Tüpraş", "BIMAS": "BİM", "FROTO": "Ford Otosan",
    "TOASO": "Tofaş", "ARCLK": "Arçelik", "EREGL": "Ereğli Demir Çelik",
    "KRDMD": "Kardemir", "SASA": "Sasa Polyester", "PGSUS": "Pegasus",
    "TCELL": "Turkcell", "TTKOM": "Türk Telekom", "SISE": "Şişecam",
    "PETKM": "Petkim", "KOZAL": "Koza Altın", "KOZAA": "Koza Anadolu",
    "MGROS": "Migros", "ULKER": "Ülker", "CCOLA": "Coca-Cola İçecek",
    "AEFES": "Anadolu Efes", "TTRAK": "Türk Traktör", "OTKAR": "Otokar",
    "TAVHL": "TAV Havalimanları", "ENKAI": "Enka İnşaat", "HEKTS": "Hektaş",
    "GUBRF": "Gübretaş", "EKGYO": "Emlak Konut", "ALARK": "Alarko Holding",
    "VESTL": "Vestel", "AKSEN": "Aksa Enerji", "ENJSA": "Enerjisa",
    "ODAS": "Odaş Elektrik", "SOKM": "Şok Marketler", "MAVI": "Mavi Giyim",
    "LOGO": "Logo Yazılım", "MPARK": "MLP Sağlık Medical Park",
    "ASTOR": "Astor Enerji", "SMRTG": "Smart Güneş", "KONTR": "Kontrolmatik",
    "CIMSA": "Çimsa", "AKCNS": "Akçansa", "TKFEN": "Tekfen Holding",
    "DOHOL": "Doğan Holding", "SELEC": "Selçuk Ecza", "BRISA": "Brisa",
}

# --- Duygu modeli: tembel yükleme (ilk çağrıda) ------------------------
_PIPE = None
_MODEL_NAME = "savasy/bert-base-turkish-sentiment-cased"
_LABEL_PRINTED = False


def _get_pipe():
    """Duygu modelini bir kez yükler; transformers/torch yoksa None döner."""
    global _PIPE
    if _PIPE is not None:
        return _PIPE
    try:
        from transformers import pipeline
        _PIPE = pipeline("text-classification", model=_MODEL_NAME,
                         truncation=True, max_length=512)
        print(f"Türkçe duygu modeli yüklendi: {_MODEL_NAME}")
    except Exception as e:
        print(f"Türkçe model yüklenemedi ({type(e).__name__}: {e}). "
              f"Haber skoru nötr (50) dönecek.")
        _PIPE = None
    return _PIPE


def _label_to_signed(label: str, score: float) -> float:
    """Model etiketini -1..+1 işaretli skora çevirir (etiket-toleranslı)."""
    l = str(label).lower()
    if "pos" in l or "olumlu" in l or l in ("label_1", "1"):
        return score
    if "neg" in l or "olumsuz" in l or l in ("label_0", "0"):
        return -score
    if "notr" in l or "nötr" in l or "neutral" in l or l in ("label_2", "2"):
        return 0.0
    return 0.0  # bilinmeyen etiket -> nötr say


def _build_query(ticker: str) -> str:
    base = NAME_MAP.get(ticker.upper(), f"{ticker} hisse borsa")
    # Son 7 günle sınırla; şirket adını tırnakla sabitle.
    return f'"{base}" when:7d'


def _fetch_headlines(ticker: str, limit: int = NEWS_LIMIT) -> list[str]:
    """Google News RSS'ten Türkçe başlıkları çeker."""
    import feedparser
    q = urllib.parse.quote(_build_query(ticker))
    url = (f"https://news.google.com/rss/search?q={q}"
           f"&hl=tr&gl=TR&ceid=TR:tr")
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=RSS_TIMEOUT)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        return [e.title for e in feed.entries[:limit] if getattr(e, "title", "")]
    except Exception as e:
        print(f"  {ticker} haber çekilemedi: {type(e).__name__}: {e}")
        return []


def turkish_news_score(ticker: str, limit: int = NEWS_LIMIT) -> tuple[float, str]:
    """
    BİST hissesi için 0-100 haber duygu skoru + özet döner.
    Veri/model yoksa (50.0, 'haber yok') ile zarifçe düşer, pipeline'ı kırmaz.
    """
    global _LABEL_PRINTED
    headlines = _fetch_headlines(ticker, limit)
    if not headlines:
        return 50.0, "haber yok"

    pipe = _get_pipe()
    if pipe is None:
        return 50.0, f"model yok ({len(headlines)} haber)"

    try:
        results = pipe(headlines)  # toplu çıkarım (daha hızlı)
    except Exception as e:
        print(f"  {ticker} duygu çıkarımı hata: {type(e).__name__}: {e}")
        return 50.0, f"çıkarım hatası ({len(headlines)} haber)"

    if not _LABEL_PRINTED and results:
        print(f"[DOĞRULAMA] Örnek ham model çıktısı: {results[0]} "
              f"— başlık: {headlines[0][:60]!r}")
        _LABEL_PRINTED = True

    signed = [_label_to_signed(r.get("label"), r.get("score", 0.0))
              for r in results]
    avg = sum(signed) / len(signed)          # -1..+1
    score = (avg + 1) * 50                    # 0..100
    pos = sum(1 for s in signed if s > 0.05)
    neg = sum(1 for s in signed if s < -0.05)
    return score, f"{pos}+ / {neg}- ({len(signed)} haber)"


if __name__ == "__main__":
    for tk in ["THYAO", "ASELS", "GARAN"]:
        s, d = turkish_news_score(tk)
        print(f"{tk}: {s:.1f}  ({d})")
        time.sleep(1)
