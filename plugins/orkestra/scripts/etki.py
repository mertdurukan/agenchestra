"""Etki ölçümü: onaylanan değişikliğin vaadini taban ve günlük izlemeyle ölç (G-069, E1).

Onay kaydına (sd/onaylar/O-nnn.json) iki alan işlenir:
  vaat  {metin, olculebilir, metrik, yon, esik{goreli, min_ornek}, kapsam}
  etki  {taban{zaman,deger,ornek}, uygulama_dogrulama{gecti,kanit,zaman}, uygulama_tarihi, gunluk[],
         izleme{durum,baslangic,kapanis,son_gidisat,ayni_gidisat_gun}, karar, durum, soru_bekliyor}
Olay günlüğü sd/onaylar/etki.jsonl yalnız sona eklenir (her satır: zaman, onay, olay, ayrıntılar).

Karar kuralı sayıdan gelir (gidisat); sabit süre/pencere yoktur: izleme uygulama gününden başlar,
yalnız kapat() ya da geri_al() ile durur. izle() idempotenttir: eksik günleri geriye dönük doldurur.
Eşzamanlılık: onay.py'nin tek kilidi (kilit yeniden girişli değil; herkese açık işlevler kilidi alır,
`_` önekliler ve kanca_* kilit altında çağrılır). Sır ve istem metni yazılmaz (yalnız sayılar ve kısa not).
"""
from __future__ import annotations

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpi  # noqa: E402
import onay  # noqa: E402
import ork_lib as L  # noqa: E402

YONLER = ("azalmali", "artmali", "degismemeli")
SONUCLAR = ("dogru-karar", "yanlis-karar", "belirsiz")
VARSAYILAN_ESIK = {"goreli": 0.10, "min_ornek": 20}
TABAN_GUN = 7        # taban: uygulamadan önceki son 7 gün (yalnız referans, izleme süresi değil)
SORU_GUN = 3         # 'kotu' üst üste bu kadar gün -> kullanıcıya geri al / sürdür sorusu


# ---------------------------------------------------------------- karar kuralı (saf)

def gidisat(taban_deger, birikim_deger, birikim_ornek, yon, esik) -> str:
    """'iyi' | 'kotu' | 'etkisiz' | 'yetersiz-veri'. Önce veri kontrolü, sonra göreli fark eşiği."""
    if yon not in YONLER:
        raise ValueError(f"geçersiz yön: {yon!r} ({', '.join(YONLER)})")
    esik = {**VARSAYILAN_ESIK, **(esik or {})}
    if not taban_deger or birikim_deger is None:
        return "yetersiz-veri"
    if (birikim_ornek or 0) < esik["min_ornek"]:
        return "yetersiz-veri"
    fark = (birikim_deger - taban_deger) / taban_deger
    if abs(fark) < esik["goreli"]:
        return "iyi" if yon == "degismemeli" else "etkisiz"
    if yon == "degismemeli":
        return "kotu"
    if yon == "azalmali":
        return "iyi" if fark < 0 else "kotu"
    return "iyi" if fark > 0 else "kotu"


# ---------------------------------------------------------------- yardımcılar

def _bugun(bugun) -> datetime.date:
    return bugun if isinstance(bugun, datetime.date) else datetime.date.today()


def _gun_basi(d: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(d, datetime.time.min).astimezone()


def _tarih(s) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _yol(sd: str) -> str:
    return os.path.join(sd, "onaylar", "etki.jsonl")


def _ekle(sd: str, oid: str, olay: str, **ayrinti) -> None:
    """Olay günlüğüne tek satır ekler (append-only; mevcut satıra dokunmaz)."""
    satir = {"zaman": L.simdi(), "onay": oid, "olay": olay}
    satir.update({a: v for a, v in ayrinti.items() if v is not None})
    os.makedirs(os.path.dirname(_yol(sd)), exist_ok=True)
    with open(_yol(sd), "ab") as f:
        f.write((json.dumps(satir, ensure_ascii=False) + "\n").encode("utf-8"))


def _kpi_adi(metrik) -> str | None:
    """'kpi:<ad>' desteklenen bir KPI ise adı; betik:/sayac: (yer tutucu) ve bilinmeyenler için None."""
    if isinstance(metrik, str) and metrik.startswith("kpi:") and metrik[4:] in kpi.KPILER:
        return metrik[4:]
    return None


def _olculebilir(k: dict) -> bool:
    v = k.get("vaat")
    return isinstance(v, dict) and bool(v.get("olculebilir")) and _kpi_adi(v.get("metrik")) is not None


def _olc(sd: str, metrik: str, bas: datetime.date, son: datetime.date):
    """[bas, son] (ikisi dahil) takvim günleri için (değer, örnek). Kaynak: kpi.olcum(aralik=...)."""
    ad = _kpi_adi(metrik)
    if ad is None:  # betik:<ad> / sayac:<ad> yer tutucu: henüz desteklenmiyor
        raise ValueError(f"desteklenmeyen metrik: {metrik!r}")
    s = kpi.olcum(sd, aralik=(_gun_basi(bas), _gun_basi(son + datetime.timedelta(days=1))))
    return s["genel"].get(ad), int((s.get("ornek") or {}).get(ad) or 0)


def _gerekli(sd: str, oid: str) -> dict:
    return onay._gerekli(sd, oid)


def _etki(k: dict) -> dict:
    e = k.get("etki")
    if e is None:
        e = k["etki"] = {}
    if not isinstance(e, dict):
        raise ValueError(f"{k.get('id')} etki alanı bozuk")
    return e


def _islem(sd: str):
    os.makedirs(onay._onay_dizini(sd), exist_ok=True)
    return L.kilit(onay._kilit_yolu(sd))


# ---------------------------------------------------------------- vaat

def vaat_ayarla(sd: str, oid: str, vaat: dict) -> dict:
    """Vaadi yazar; eşik/metrik/yön uygulamadan sonra değiştirilemez."""
    if not isinstance(vaat, dict):
        raise ValueError("vaat sözlük olmalı.")
    onay._kayit_yolu(sd, oid)  # kimlik biçimi
    metrik = vaat.get("metrik")
    olculebilir = vaat.get("olculebilir")
    if olculebilir is None:
        olculebilir = bool(metrik)
    yon = vaat.get("yon")
    if yon is not None and yon not in YONLER:
        raise ValueError(f"geçersiz yön: {yon!r} ({', '.join(YONLER)})")
    if olculebilir and not yon:
        raise ValueError("ölçülebilir vaatte yön zorunlu.")
    esik = {**VARSAYILAN_ESIK, **(vaat.get("esik") or {})}
    if not (isinstance(esik["goreli"], (int, float)) and esik["goreli"] > 0
            and isinstance(esik["min_ornek"], int) and esik["min_ornek"] >= 1):
        raise ValueError("eşik geçersiz: goreli > 0 ve min_ornek >= 1 olmalı.")
    yeni = {"metin": L.maskele(onay._tek_satir(vaat.get("metin") or "")), "olculebilir": bool(olculebilir),
            "metrik": metrik, "yon": yon, "esik": esik, "kapsam": vaat.get("kapsam") or "genel"}
    with _islem(sd):
        k = _gerekli(sd, oid)
        eski = k.get("vaat")
        e = k.get("etki")
        uygulanmis = k.get("durum") in ("uygulaniyor", "uygulandi") or (isinstance(e, dict) and e.get("uygulama_tarihi"))
        if uygulanmis and isinstance(eski, dict):
            for a in ("esik", "metrik", "yon"):
                if eski.get(a) != yeni[a]:
                    raise ValueError(f"{oid}: uygulamadan sonra vaadin {a} alanı değiştirilemez.")
        k["vaat"] = yeni
        onay._kayit_yaz(sd, k)
        _ekle(sd, oid, "vaat-yazildi", metrik=metrik, yon=yon, esik=esik, olculebilir=yeni["olculebilir"])
        return k


# ---------------------------------------------------------------- taban

def _taban_ic(sd: str, k: dict, bugun: datetime.date) -> bool:
    """Taban yoksa alır ve k'ye yazar (kayıt yazımı çağıranın işi). Donar: varsa dokunmaz."""
    if not _olculebilir(k):
        return False
    e = _etki(k)
    if isinstance(e.get("taban"), dict):
        return False
    deger, ornek = _olc(sd, k["vaat"]["metrik"], bugun - datetime.timedelta(days=TABAN_GUN),
                        bugun - datetime.timedelta(days=1))
    e["taban"] = {"zaman": L.simdi(), "deger": deger, "ornek": ornek}
    _ekle(sd, k["id"], "taban-alindi", metrik=k["vaat"]["metrik"], deger=deger, ornek=ornek)
    return True


def taban_al(sd: str, oid: str, bugun=None):
    """Uygulamadan önceki son 7 günün değerini dondurur; ikinci çağrıda değişmez. Dönüş: taban ya da None."""
    bugun = _bugun(bugun)
    with _islem(sd):
        k = _gerekli(sd, oid)
        if _taban_ic(sd, k, bugun):
            onay._kayit_yaz(sd, k)
        e = k.get("etki")
        return e.get("taban") if isinstance(e, dict) else None


# ---------------------------------------------------------------- uygulama doğrulama

def uygulama_dogrula(sd: str, oid: str, gecti: bool, kanit: str) -> dict:
    """'Uygulandı mı?' sorusunun kaydı (dosyada satır var/yok, test geçiyor); 'işe yaradı mı' ayrıdır."""
    with _islem(sd):
        k = _gerekli(sd, oid)
        e = _etki(k)
        e["uygulama_dogrulama"] = {"gecti": bool(gecti), "kanit": L.maskele(onay._tek_satir(kanit or "")),
                                   "zaman": L.simdi()}
        onay._kayit_yaz(sd, k)
        _ekle(sd, oid, "uygulama-dogrulandi", gecti=bool(gecti))
        return k


# ---------------------------------------------------------------- günlük izleme

def _karisik(sd: str, oid: str, tarih: str) -> list[str]:
    """Aynı uygulama gününde uygulanan DİĞER onay kayıtları (confound işareti)."""
    out = []
    for o in onay._hepsi(sd):
        e = o.get("etki")
        if o.get("id") != oid and isinstance(e, dict) and e.get("uygulama_tarihi") == tarih:
            out.append(o["id"])
    return sorted(out)


def _seri_say(gunluk: list[dict]) -> int:
    """Sondan geriye aynı gidişatın üst üste gün sayısı."""
    if not gunluk:
        return 0
    son = gunluk[-1]["gidisat"]
    n = 0
    for s in reversed(gunluk):
        if s["gidisat"] != son:
            break
        n += 1
    return n


def _izle_kayit(sd: str, k: dict, bugun: datetime.date) -> bool:
    """Tek kaydı günceller (kilit altında). Değişiklik olduysa True; kayıt yazımı çağıranın işi."""
    e = k.get("etki")
    if not isinstance(e, dict):
        return False
    bas = _tarih(e.get("uygulama_tarihi"))
    if bas is None:
        return False
    oid = k["id"]
    if not _olculebilir(k):
        if e.get("durum") == "olculemez":
            return False
        e["durum"] = "olculemez"
        return True
    iz = e.get("izleme")
    if isinstance(iz, dict) and iz.get("durum") in ("kapandi", "geri-alindi"):
        return False
    gunluk = e.setdefault("gunluk", [])
    vaat = k["vaat"]
    taban = (e.get("taban") or {}).get("deger")
    olaylar = []
    degisti = False
    # Son iki satır her koşuda yeniden ölçülür: bugünün satırı gün içinde kısmi veriyle yazılır (dün kesinleşir);
    # yeniden ölçmeden satır ilk ölçümde donar ve birikim/gidişat eski veriye dayanır.
    for i in range(max(0, len(gunluk) - 2), (bugun - bas).days + 1):
        gun = bas + datetime.timedelta(days=i)
        g_deger, g_ornek = _olc(sd, vaat["metrik"], gun, gun)
        b_deger, b_ornek = _olc(sd, vaat["metrik"], bas, gun)
        g = gidisat(taban, b_deger, b_ornek, vaat["yon"], vaat.get("esik"))
        fark = (b_deger - taban) / taban if taban and b_deger is not None else None
        satir = {"gun": i + 1, "tarih": gun.isoformat(), "gunluk_deger": g_deger, "gunluk_ornek": g_ornek,
                 "birikim_deger": b_deger, "birikim_ornek": b_ornek, "fark_goreli": fark, "gidisat": g,
                 "karisik": _karisik(sd, oid, e["uygulama_tarihi"])}
        if i < len(gunluk):  # var olan satırın yeniden ölçümü: değer değişmediyse dokunma, olay üretme
            eski = gunluk[i]
            if eski == satir:
                continue
            gunluk[i] = satir
            degisti = True
            if eski.get("gidisat") != g:
                olaylar.append(("gidisat-degisti", {"gun": satir["gun"], "onceki": eski.get("gidisat"), "yeni": g}))
            continue
        onceki = gunluk[-1]["gidisat"] if gunluk else None
        gunluk.append(satir)
        olaylar.append(("gunluk-olcum", {"gun": satir["gun"], "tarih": satir["tarih"], "gidisat": g,
                                         "birikim_deger": b_deger, "birikim_ornek": b_ornek}))
        if onceki is not None and onceki != g:
            olaylar.append(("gidisat-degisti", {"gun": satir["gun"], "onceki": onceki, "yeni": g}))
        degisti = True
    if degisti:
        sayi = _seri_say(gunluk)
        iz = e.get("izleme") if isinstance(e.get("izleme"), dict) else {
            "durum": "suruyor", "baslangic": bas.isoformat(), "kapanis": None}
        iz["son_gidisat"] = gunluk[-1]["gidisat"]
        iz["ayni_gidisat_gun"] = sayi
        e["izleme"] = iz
        e.setdefault("karar", None)
        if iz["son_gidisat"] == "kotu" and sayi >= SORU_GUN:
            e["soru_bekliyor"] = True
        else:
            e.setdefault("soru_bekliyor", False)
    k["_olaylar"] = olaylar
    return degisti


def izle(sd: str, oid: str | None = None, bugun=None) -> list[str]:
    """Eksik her günü uygulama gününden bugüne geriye dönük doldurur; idempotent. Dönüş: güncellenen kimlikler."""
    bugun = _bugun(bugun)
    guncel = []
    with _islem(sd):
        kayitlar = [_gerekli(sd, oid)] if oid else onay._hepsi(sd)
        for k in kayitlar:
            try:
                degisti = _izle_kayit(sd, k, bugun)
            except Exception:
                k.pop("_olaylar", None)
                if oid:
                    raise
                continue  # toplu izlemede bozuk bir kayıt diğerlerini durdurmaz
            olaylar = k.pop("_olaylar", [])
            if degisti:
                onay._kayit_yaz(sd, k)
                for olay, ayr in olaylar:
                    _ekle(sd, k["id"], olay, **ayr)
                guncel.append(k["id"])
    return guncel


# ---------------------------------------------------------------- kapatma / geri alma

def _durdur(sd: str, oid: str, durum: str, olay: str, karar: dict | None, **ayrinti) -> dict:
    with _islem(sd):
        k = _gerekli(sd, oid)
        e = _etki(k)
        iz = e.get("izleme") if isinstance(e.get("izleme"), dict) else {
            "durum": "suruyor", "baslangic": e.get("uygulama_tarihi"), "kapanis": None,
            "son_gidisat": None, "ayni_gidisat_gun": 0}
        if iz.get("durum") != "suruyor":
            raise ValueError(f"{oid} izlemesi zaten durmuş ({iz.get('durum')}).")
        simdi = L.simdi()
        iz["durum"] = durum
        iz["kapanis"] = simdi
        e["izleme"] = iz
        e["soru_bekliyor"] = False
        if karar is not None:
            e["karar"] = dict(karar, zaman=simdi)
        onay._kayit_yaz(sd, k)
        _ekle(sd, oid, olay, **ayrinti)
        return k


def kapat(sd: str, oid: str, sonuc: str, not_: str = "") -> dict:
    """İzlemeyi kullanıcı kapatır: doğru/yanlış karar kararı kullanıcınındır, sistem yalnız veriyi gösterir."""
    if sonuc not in SONUCLAR:
        raise ValueError(f"geçersiz sonuç: {sonuc!r} ({', '.join(SONUCLAR)})")
    not_ = L.maskele(onay._tek_satir(not_ or ""))
    return _durdur(sd, oid, "kapandi", "izleme-kapandi", {"sonuc": sonuc, "not": not_}, sonuc=sonuc)


def geri_al(sd: str, oid: str, neden: str = "") -> dict:
    """Değişiklik geri alındı: izleme durur (geri almanın kendisini yapmaz, yalnız kaydeder)."""
    return _durdur(sd, oid, "geri-alindi", "geri-alindi", None, neden=L.maskele(onay._tek_satir(neden or "")))


# ---------------------------------------------------------------- sorgu

def liste(sd: str) -> list[dict]:
    return [k for k in onay._hepsi(sd) if k.get("vaat") or k.get("etki")]


def dogru_karar_orani(sd: str) -> dict:
    """Yalnız kapatılmış izlemelerden. oran = dogru / (dogru + yanlis); payda 0 ise None."""
    sayi = {"dogru-karar": 0, "yanlis-karar": 0, "belirsiz": 0}
    for k in liste(sd):
        e = k.get("etki")
        kr = e.get("karar") if isinstance(e, dict) else None
        if isinstance(kr, dict) and kr.get("sonuc") in sayi:
            sayi[kr["sonuc"]] += 1
    d, y, b = sayi["dogru-karar"], sayi["yanlis-karar"], sayi["belirsiz"]
    return {"dogru": d, "yanlis": y, "belirsiz": b, "kapatilan": d + y + b,
            "oran": d / (d + y) if d + y else None}


# ---------------------------------------------------------------- onay.py kancaları (kilit altında çağrılır)

def kanca_al(sd: str, k: dict) -> None:
    """onay.al(): vaatli kayıtta taban snapshot'ı (uygulamadan önce)."""
    _taban_ic(sd, k, datetime.date.today())


def kanca_uygulandi(k: dict) -> None:
    """onay.uygulandi(): uygulama tarihini yazar (izleme bu günden başlar)."""
    e = _etki(k)
    e.setdefault("uygulama_tarihi", datetime.date.today().isoformat())
