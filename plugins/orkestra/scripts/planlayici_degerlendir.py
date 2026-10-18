"""Haftalık planlayıcı değerlendirmesi (040 P7): `orkestra kpi planlayici-degerlendir`.

kpi.py planlayıcı tablosu (analitik._planlayici) planlayıcı modeline göre ilk geçiş, kabul başına USD ve süre verir.
Bu modül tabloyu haftada bir değerlendirir:
- Dönem: ana ajan modeli sürümü (ayarlar/model_politikasi.json ana_ajan.varsayilan) değişirse dönem sıfırlanır;
  yalnız dönem başından sonra oluşan kartlar sayılır (eski sürümün verisi yeni sürümün karnesine karışmaz).
- Eşik: karar.min_n kartı dolduran en az iki planlayıcı arasında ilk geçiş farkı `ilk_gecis_fark`, kabul başına USD farkı
  `usd_fark` (göreli) ya da süre medyanı farkı `dk_fark` (göreli) eşiğini aşarsa `orkestra onay iste` önerisi açılır.
- Durum: .claude/orkestra/planlayici_degerlendirme.json (sürüm, dönem başı, son değerlendirme, son öneri anahtarı).
Öneri otomatik uygulanmaz; karar panelde kullanıcıdadır.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analitik as A  # noqa: E402
import ork_lib as L  # noqa: E402

HAFTA_GUN = 7
DURUM_DOSYASI = "planlayici_degerlendirme.json"


def _politika() -> dict:
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ayarlar", "model_politikasi.json")
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def model_surumu() -> str:
    """Ana ajan modeli sürümü (ör. claude-sonnet-5-5); okunamazsa 'bilinmiyor'."""
    return str((_politika().get("ana_ajan") or {}).get("varsayilan") or "bilinmiyor")


def _durum_yolu(sd: str) -> str:
    return os.path.join(sd, DURUM_DOSYASI)


def _oku(sd: str) -> dict:
    try:
        with open(_durum_yolu(sd), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _yaz(sd: str, d: dict) -> None:
    L.atomik_yaz(_durum_yolu(sd), json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def _zaman(s):
    try:
        z = datetime.datetime.fromisoformat(str(s))
        return z if z.tzinfo else z.astimezone()
    except (TypeError, ValueError):
        return None


def farklar(toplam: list[dict], esik: dict) -> list[dict]:
    """Yeterli veriye (yeterli=True) sahip planlayıcılar arasında eşiği aşan her çift için bir fark kaydı.
    Çift: n'i büyük olan referans, diğeri aday. Aday ilk geçişte `ilk_gecis_fark` kadar iyiyse, kabul başına USD'de
    ya da süre medyanında göreli `usd_fark`/`dk_fark` kadar düşükse (daha ucuz/hızlı) kayıt üretir."""
    yeterli = sorted((r for r in toplam if r.get("yeterli") and r.get("planlayici") != "bilinmiyor"), key=lambda r: -r["n"])
    out = []
    for i, ref in enumerate(yeterli):
        for aday in yeterli[i + 1:]:
            nedenler = []
            if ref.get("ilk_gecis") is not None and aday.get("ilk_gecis") is not None:
                d = aday["ilk_gecis"] - ref["ilk_gecis"]
                if abs(d) >= esik["ilk_gecis_fark"]:
                    nedenler.append(f"ilk geçiş {aday['planlayici']} {aday['ilk_gecis']:.2f} / {ref['planlayici']} {ref['ilk_gecis']:.2f}")
            for alan, anahtar, ad in (("kabul_usd", "usd_fark", "kabul başına USD"), ("dk_medyan", "dk_fark", "süre medyanı (dk)")):
                a, r = aday.get(alan), ref.get(alan)
                if a is not None and r and abs(a - r) / r >= esik[anahtar]:
                    nedenler.append(f"{ad} {aday['planlayici']} {a:.3g} / {ref['planlayici']} {r:.3g}")
            if nedenler:
                out.append({"referans": ref["planlayici"], "aday": aday["planlayici"],
                            "n": [ref["n"], aday["n"]], "nedenler": nedenler})
    return out


def degerlendir(sd: str, simdi: datetime.datetime | None = None, zorla: bool = False, kuru: bool = False,
                surum: str | None = None, kartlar: list | None = None, kayitlar: list | None = None) -> dict:
    """Haftalık değerlendirme. Dönüş: {durum: 'sifirlandi'|'bekliyor'|'degerlendirildi', ...}.
    'sifirlandi': model sürümü değişti, dönem bugünden başlar, değerlendirme yapılmaz.
    'bekliyor': son değerlendirmeden bu yana 7 gün dolmadı. 'degerlendirildi': tablo ölçüldü; `oneri` varsa onay istendi."""
    simdi = simdi or datetime.datetime.now().astimezone()
    surum = surum or model_surumu()
    d = _oku(sd)
    if d.get("model_surumu") != surum:
        eski = d.get("model_surumu")
        if eski is not None or not d:  # ilk kurulumda da dönem başı yazılır
            yeni = {"model_surumu": surum, "donem_basi": simdi.isoformat(timespec="seconds"),
                    "son_degerlendirme": None, "son_oneri": None}
            if not kuru:
                _yaz(sd, yeni)
            return {"durum": "sifirlandi", "onceki_surum": eski, "model_surumu": surum, "donem_basi": yeni["donem_basi"]}
    son = _zaman(d.get("son_degerlendirme"))
    if not zorla and son and (simdi - son).days < HAFTA_GUN:
        return {"durum": "bekliyor", "model_surumu": surum, "son_degerlendirme": d.get("son_degerlendirme"),
                "kalan_gun": HAFTA_GUN - (simdi - son).days}
    donem = _zaman(d.get("donem_basi"))
    kartlar = L.kartlar(sd) if kartlar is None else kartlar
    kayitlar = L.maliyet_kayitlari(sd) if kayitlar is None else kayitlar
    if donem:
        kartlar = [k for k in kartlar if (_zaman(k.get("olusturma")) or donem) >= donem]
    tablo = A._planlayici(kartlar, kayitlar)
    pol = _politika().get("karar") or {}
    esik = {"ilk_gecis_fark": float(pol.get("ilk_gecis_fark", 0.05)), "usd_fark": float(pol.get("usd_fark", 0.10)),
            "dk_fark": float(pol.get("dk_fark", 0.10))}
    fark = farklar(tablo["toplam"], esik)
    sonuc = {"durum": "degerlendirildi", "model_surumu": surum, "donem_basi": d.get("donem_basi"), "min_n": tablo["min_n"],
             "planlayicilar": [{"planlayici": r["planlayici"], "n": r["n"], "yeterli": r["yeterli"], "ilk_gecis": r["ilk_gecis"],
                                "kabul_usd": r["kabul_usd"], "dk_medyan": r["dk_medyan"]} for r in tablo["toplam"]],
             "esik": esik, "farklar": fark, "oneri": None}
    if fark and not kuru:
        import onay
        anahtar = f"planlayici:{surum}:{simdi.strftime('%G-W%V')}"
        metin = ("Planlayıcı modelleri arasında eşik aşıldı (dönem başı " + str(d.get("donem_basi")) + ", model sürümü " + surum + "):\n"
                 + "\n".join(f"- {x['referans']} (n={x['n'][0]}) ile {x['aday']} (n={x['n'][1]}): " + "; ".join(x["nedenler"]) for x in fark)
                 + "\nÖlçüm: `orkestra kpi planlayici-degerlendir`; tablo: `orkestra maliyet rapor`.")
        secenekler = ["Planlayıcı modelini gözden geçir", "Değiştirme"]
        k = onay.iste(sd, "Planlayıcı modeli farkı eşiği aştı", metin, secenekler=secenekler, tur="karar", kaynak="kpi", anahtar=anahtar)
        sonuc["oneri"] = {"onay_id": k.get("id"), "anahtar": anahtar}
        d["son_oneri"] = anahtar
    if not kuru:
        d.update(model_surumu=surum, donem_basi=d.get("donem_basi") or simdi.isoformat(timespec="seconds"),
                 son_degerlendirme=simdi.isoformat(timespec="seconds"))
        _yaz(sd, d)
    return sonuc
