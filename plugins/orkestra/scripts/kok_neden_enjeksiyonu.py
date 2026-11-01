"""Sorun anında kök neden önce yöntemini bağlama ekler (ADR-0101, P-042, K-006).

Metin tek kaynaktan okunur: `standartlar/kok_neden.md` bölümleri. Üç tetik:
- UserPromptSubmit: kullanıcı mesajında hata/sorun sinyali varsa ana ajana (`ana_ajan_metni`).
- SubagentStart: kartlı işçiye, denetçi hariç (`isci_metni`).
- PostToolUseFailure: araç başarısız olunca, oturum başına seyreltilmiş (`arac_metni`).
Model çağırmaz, engellemez; hata olursa boş metin döner. Her enjeksiyon `gunluk.jsonl`'a `kok_neden_enjekte` olarak
nokta alanıyla yazılır (mesaj metni yazılmaz). Ayar: `ayarlar/kok_neden_enjeksiyonu.json` + proje durum dizininde aynı
adlı dosya (anahtar bazında ezer); `ORKESTRA_KOK_NEDEN=0` hepsini kapatır.
"""
from __future__ import annotations

import json
import os
import re

import ork_lib as L
import standart

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "kok_neden_enjeksiyonu.json")
PROJE_DOSYA = "kok_neden_enjeksiyonu.json"
SAYAC_DOSYA = "kok_neden_sayac.json"
MODLAR = ("etkin", "kapali")
ANA_MAX = 900
ISCI_MAX = 600
ARAC_MAX = 400
TARAMA_MAX = 2000
SAYAC_OTURUM_MAX = 50


def _json_oku(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def ayar_oku(sd=None) -> dict:
    ayar = _json_oku(VARSAYILAN_YOL) or {}
    if sd:
        proje = _json_oku(os.path.join(sd, PROJE_DOSYA))
        if proje:
            ayar.update(proje)
    return ayar


def mod(ayar: dict) -> str:
    if os.environ.get("ORKESTRA_KOK_NEDEN") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def _tr_kucuk(metin: str) -> str:
    """Türkçe büyük/küçük harf: İ→i, I→ı (ASCII 'I' içeren İngilizce sözcükler ayrıca düz küçültmeyle eşleşir)."""
    return metin.replace("İ", "i").replace("I", "ı").lower()


def sinyal_var(metin, ayar: dict) -> bool:
    """Mesajda hata/sorun sinyali var mı: ayardaki desenlerden herhangi biri, hem düz hem Türkçe küçültmeyle."""
    desenler = [d for d in ayar.get("sinyaller") or [] if isinstance(d, str) and d]
    if not desenler or not isinstance(metin, str):
        return False
    try:
        rx = re.compile("|".join(f"(?:{d})" for d in desenler))
    except re.error:
        return False
    kesit = metin[:TARAMA_MAX]
    return bool(rx.search(kesit.lower()) or rx.search(_tr_kucuk(kesit)))


def _bolum(sd, baslik: str) -> str:
    """Standartta `## <baslik>` bölümünün gövdesi (sonraki `## ` başlığına kadar), tek satıra sıkıştırılmış."""
    metin = standart.oku("kok_neden", sd) or ""
    m = re.search(r"^##\s+" + re.escape(baslik) + r"\s*$(.*?)(?=^##\s|\Z)", metin, re.S | re.M)
    return " ".join(m.group(1).split()) if m else ""


def _kes(metin: str, sinir: int) -> str:
    if len(metin) <= sinir:
        return metin
    return metin[:sinir - 1].rsplit(" ", 1)[0] + "…"


def _gunluk(sd, oturum_id, nokta: str, ajan=None) -> None:
    try:
        kayit = {"zaman": L.simdi(), "oturum": oturum_id, "tur": "kok_neden_enjekte", "nokta": nokta}
        if ajan:
            kayit["ajan"] = ajan
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), kayit)
    except Exception:
        pass


def _metin(sd, oturum_id, baslik_anahtari: str, varsayilan_baslik: str, sinir: int, nokta: str, ajan=None) -> str:
    try:
        ayar = ayar_oku(sd)
        if mod(ayar) == "kapali":
            return ""
        govde = _bolum(sd, ayar.get(baslik_anahtari, varsayilan_baslik))
        if not govde:
            return ""
        _gunluk(sd, oturum_id, nokta, ajan)
        return _kes(ayar.get("onek", "") + govde, sinir)
    except Exception:
        return ""


def ana_ajan_metni(metin, sd=None, oturum_id=None) -> str:
    """Hata/sorun sinyali taşıyan kullanıcı mesajında yöntem metni, değilse boş."""
    try:
        if mod(ayar_oku(sd)) == "kapali" or not sinyal_var(metin, ayar_oku(sd)):
            return ""
    except Exception:
        return ""
    return _metin(sd, oturum_id, "mesaj_basligi", "Hata anı", ANA_MAX, "ana")


def isci_metni(agent_type, sd=None, oturum_id=None) -> str:
    """Kartlı işçi için yöntem metni; denetçi için boş (bağımsız denetim kendi tanımından çalışır)."""
    if str(agent_type or "").endswith("denetci"):
        return ""
    return _metin(sd, oturum_id, "isci_basligi", "İşçi görevi anı", ISCI_MAX, "isci", agent_type)


def _sayac_artir(sd, oturum_id) -> int:
    """Oturumun araç başarısızlığı sayısını bir artırır ve yeni değeri döner; yazılamazsa 1 (ipucu verilir)."""
    yol = os.path.join(sd, SAYAC_DOSYA)
    veri = _json_oku(yol) or {}
    anahtar = str(oturum_id or "?")
    n = int(veri.get(anahtar, 0) or 0) + 1
    veri.pop(anahtar, None)
    veri[anahtar] = n  # en son kullanılan sona
    while len(veri) > SAYAC_OTURUM_MAX:
        veri.pop(next(iter(veri)))
    try:
        gecici = yol + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f)
        os.replace(gecici, yol)
    except Exception:
        return 1
    return n


def tekrar_notu(inp, sd) -> str:
    """Aynı araç hatası imzası son 7 günde eşik (hata_en_cok.UYARI_ESIK) ve üzerindeyse tek satır: sayı ve kök neden
    durumu (ADR-0141); eşiğin altında boş. İmza, yazıcıyla aynı biçimde (araç adı + maskeli ileti) hesaplanır."""
    try:
        import hata_en_cok as HE
        import hata_kayit as HK
        ileti = f"{inp.get('tool_name') or '?'}: {L.maskele(str(inp.get('error') or ''))}"[:HK.ILETI_EN_COK]
        im = HE.imza_goster("arac-hatasi", ileti)
        for r in HE.birlestir(sd, HE.UYARI_GUN, "arac"):
            if r["imza"] == im and r["sayi"] >= HE.UYARI_ESIK:
                return (f"Tekrar eden araç hatası: {r['sayi']} kez / {HE.UYARI_GUN} gün, kök neden durumu "
                        f"{HE.DURUM_ETIKET.get(r['durum'], r['durum'])} (orkestra hata en-cok --kaynak arac).")
    except Exception:
        pass
    return ""


def arac_metni(inp, sd=None) -> str:
    """Araç başarısızlığında ipucu: oturumun 1. başarısızlığında, sonra her `arac_hatasi_her`. başarısızlıkta.
    Tekrar eşiği aşılmışsa imzanın sayısı ve kök neden durumu ayrıca eklenir (seyreltmeden bağımsız)."""
    try:
        if not sd or not isinstance(inp, dict) or inp.get("is_interrupt"):
            return ""
        ayar = ayar_oku(sd)
        if mod(ayar) == "kapali":
            return ""
        her = max(1, int(ayar.get("arac_hatasi_her", 3) or 3))
        n = _sayac_artir(sd, inp.get("session_id"))
        ipucu = ""
        if n == 1 or n % her == 0:
            ipucu = _metin(sd, inp.get("session_id"), "arac_basligi", "Araç hatası anı", ARAC_MAX, "arac")
        return " ".join(x for x in (ipucu, tekrar_notu(inp, sd)) if x)
    except Exception:
        return ""
