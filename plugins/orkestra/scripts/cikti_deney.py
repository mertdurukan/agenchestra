"""Çıktı bütçesi geri bildirim deneyi (I-319 P6; rapor 149 §4): üç kollu, eşzamanlı, oturum düzeyinde atama.

Kollar: `kontrol` (davranış değişmez, ek bağlam yok), `geri_bildirim` (önceki tur `cikti_butce` sınırını aştıysa
UserPromptSubmit'te tek kısa satır), `kalibre` (her istekte tur tipine göre sınır satırı). Atama oturum kimliğinin
sha256 özetinden deterministiktir; aynı oturum her zaman aynı kola düşer. Model çağrılmaz, hiçbir tur engellenmez.

Ayar `ayarlar/cikti_butce_deney.json` (proje ezmesi durum dizininde aynı ad). `ORKESTRA_CIKTI_DENEY=0` kapatır.
Bildirim metni yalnız sayı ve sabit metin taşır (sır ya da ad girmez); hatada sessiz geçer.
"""
from __future__ import annotations

import hashlib
import json
import os

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "cikti_butce_deney.json")
PROJE_DOSYA = "cikti_butce_deney.json"
KOLLAR = ("kontrol", "geri_bildirim", "kalibre")
_KALIBRE_VARSAYILAN = {"soru": 700, "gorev": 800, "kutu_oncesi": 400, "kapanis": 300}


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


def acik(ayar: dict) -> bool:
    """Deney koşuyor mu: env kapatmadıysa ve mod 'golge' ise (başka kip tanımlı değil; ret hiçbir kipte yok)."""
    return os.environ.get("ORKESTRA_CIKTI_DENEY") != "0" and ayar.get("mod", "kapali") == "golge"


def kol(oid, ayar: dict) -> str | None:
    """Oturumun kolu; deney kapalıysa ya da oturum kimliği yoksa None. Oranlar ağırlıktır (varsayılan eşit)."""
    if not oid or not acik(ayar):
        return None
    oranlar = ayar.get("oranlar") or {}
    agirlik = [(k, int(oranlar.get(k, 1))) for k in KOLLAR if int(oranlar.get(k, 1)) > 0]
    toplam = sum(a for _, a in agirlik)
    if not toplam:
        return None
    ozet = hashlib.sha256(f"{ayar.get('tuz', 'cikti_deney_v1')}:{oid}".encode("utf-8")).hexdigest()
    n = int(ozet[:16], 16) % toplam
    for k, a in agirlik:
        if n < a:
            return k
        n -= a
    return None


def _durum_yolu(sd: str, oid) -> str:
    ad = hashlib.sha256(str(oid).encode("utf-8")).hexdigest()[:24]
    return os.path.join(sd, "oturumlar", f"cikti_deney_{ad}.json")


def tur_tipi(mesaj: str, sd=None) -> str:
    """Kalibre sınırı için tip: bilgi sorusu 'soru', diğerleri 'gorev' (soru_sinif kuralı; model yok)."""
    try:
        import soru_sinif
        return "soru" if soru_sinif.tur(mesaj or "", sd) == "soru" else "gorev"
    except Exception:
        return "gorev"


def kalibre_asim(olcum: dict, tip: str, ayar: dict) -> bool:
    """Tur kalibre sınırını aştı mı: kutulu turda kutu öncesi ve kapanış ayrı, kutusuzda tipe göre tek sınır."""
    s = {**_KALIBRE_VARSAYILAN, **(ayar.get("kalibre_sinirlari") or {})}
    if olcum.get("kapanis") is not None:
        return olcum["toplam"] - olcum["kapanis"] > s["kutu_oncesi"] or olcum["kapanis"] > s["kapanis"]
    return olcum["toplam"] > s.get(tip, s["gorev"])


def stop_kaydet(sd: str, oid, olcum: dict, butce_ayar: dict, ayar: dict) -> None:
    """Stop: geri_bildirim kolunda önceki turun aşımını sonraki istek için saklar; aşım yoksa eski kaydı siler."""
    if kol(oid, ayar) != "geri_bildirim":
        return
    yol = _durum_yolu(sd, oid)
    ts, ks = butce_ayar.get("tur_siniri") or 800, butce_ayar.get("kapanis_siniri") or 300
    asim = olcum["toplam"] > ts or (olcum.get("kapanis") is not None and olcum["kapanis"] > ks)
    if not asim:
        try:
            os.remove(yol)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"toplam": int(olcum["toplam"]), "kapanis": olcum.get("kapanis"), "ts": int(ts), "ks": int(ks)}, f)


def bildirim(sd: str, oid, mesaj: str, ayar: dict) -> str:
    """UserPromptSubmit ek bağlamı: kontrol kolunda ve deney kapalıyken daima boş. Metin `bildirim_azami` karakteri geçmez."""
    k = kol(oid, ayar)
    azami = int(ayar.get("bildirim_azami") or 200)
    if k == "geri_bildirim":
        yol = _durum_yolu(sd, oid)
        d = _json_oku(yol)
        if not d:
            return ""
        try:
            os.remove(yol)  # tek sefer: bildirim tüketilir
        except OSError:
            pass
        parca = f"tur {int(d['toplam'])}/{int(d['ts'])}"
        if d.get("kapanis") is not None and int(d["kapanis"]) > int(d["ks"]):
            parca += f", kutudan sonra {int(d['kapanis'])}/{int(d['ks'])}"
        return f"Orkestra (P-001): önceki yanıt çıktı bütçesini aştı ({parca} karakter). Bu yanıtı kısa tut."[:azami]
    if k == "kalibre":
        s = {**_KALIBRE_VARSAYILAN, **(ayar.get("kalibre_sinirlari") or {})}
        tip = tur_tipi(mesaj, sd)
        return (f"Orkestra (P-001): bu tur bütçesi ≤{int(s[tip])} karakter ({tip}); wrap_up kullanırsan kutu öncesi "
                f"≤{int(s['kutu_oncesi'])}, kutudan sonra ≤{int(s['kapanis'])}.")[:azami]
    return ""
