"""Görev listesi açık adım kapısı (Stop).

Görev listesini hook değiştiremez; yalnız ajan değiştirir. İş bittiği halde açık adım kalırsa kullanıcı listeyi "yapılmadı"
görür. Stop anında liste gorev_listesi.durum_kur ile kurulur; açık adım varsa, tur kullanıcıdan soru/onay beklemiyorsa ve arka
plan görevi yoksa tur bir kez durdurulur (stop_hook_active döngüyü keser), ajan listeyi aynı turda kapatır.

Uygulama turu normal bitince son in_progress adımı kendisi işaretler; listenin son adımı in_progress ise açık sayılmaz.
Ayar: ayarlar/gorev_listesi_kapisi.json (proje durum dizinindeki aynı adlı dosya anahtar bazında ezer).
ORKESTRA_GOREV_LISTESI_KAPISI=0 kapatır. Model çağrısı yok.
"""
import json
import os

import gorev_listesi as GL

KAPI = "gorev_listesi"
DOSYA = "gorev_listesi_kapisi.json"
VARSAYILAN_YOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", DOSYA)
MODLAR = ("block", "golge", "kapali")


def _json_oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def ayar_oku(sd=None) -> dict:
    ayar = _json_oku(VARSAYILAN_YOL) or {}
    if sd:
        ayar.update(_json_oku(os.path.join(sd, DOSYA)) or {})
    return ayar


def mod(ayar: dict) -> str:
    """'block' (tur başına bir kez durdur), 'golge' (yalnız günlük) ya da 'kapali'."""
    if os.environ.get("ORKESTRA_GOREV_LISTESI_KAPISI") == "0":
        return "kapali"
    m = ayar.get("mod", "block")
    return m if m in MODLAR else "kapali"


def acik_adimlar(maddeler: list) -> list:
    """(sıra no, metin, durum): tamamlanmamış adımlar; son adım in_progress ise uygulama işaretler, sayılmaz."""
    son = len(maddeler) - 1
    return [(i + 1, m["icerik"], m["durum"]) for i, m in enumerate(maddeler)
            if m["durum"] != "completed" and not (m["durum"] == "in_progress" and i == son)]


def degerlendir(transkript, son_mesaj, ofset: int, inp: dict):
    """Tetiklenirse {"acik": [...], "arac": ad}, yoksa None."""
    if inp.get("background_tasks"):
        return None  # çalışma sürüyor: açık adım meşru
    maddeler, arac = GL.durum_kur(transkript)
    acik = acik_adimlar(maddeler)
    if not acik:
        return None
    try:
        import niyet
        if niyet.bekleme_nedeni(transkript, ofset, son_mesaj):
            return None  # kullanıcıdan soru/onay bekleniyor: açık adım meşru
    except Exception:
        pass
    return {"acik": acik, "arac": arac}


def hatirlatma_metni(bulgu: dict, ayar: dict) -> str:
    acik = bulgu["acik"][:8]
    liste = "; ".join(f"{n}. {c[:60]} [{s}]" for n, c, s in acik)
    if bulgu.get("arac") == GL.TODO_ARACI:
        nasil = "TodoWrite ile biten adımları completed yap"
    else:
        nasil = "update_plan ile biten adımları işaretle ({\"done\": [" + ", ".join(str(n) for n, _, _ in acik) + "]})"
    sablon = ayar.get("hatirlatma") or ("Orkestra: görev listesinde açık adım kaldı → {liste}. Turu bitirmeden {nasil}; "
                                        "yapılmayan adım varsa listeyi güncel planla yeniden yaz ya da kullanıcıya neyin kaldığını söyle.")
    return sablon.format(liste=liste, nasil=nasil)
