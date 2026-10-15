"""Orkestra iş yönlendirme: konu skoru, yönlendirme kararı, kapanış/bayat tespiti.

Saf Python, yalnız standart kütüphane. Dosya, ağ ve alt süreç kullanmaz; yan etkisi yoktur.
"""
import re
from datetime import datetime, timedelta

BAYAT_GUN = 14
ESIK = 3
SATIR_SINIR = 200
KOK_UZUNLUK = 5

_KATLA = str.maketrans({
    "İ": "i", "I": "i", "ı": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})


def _katla(metin):
    return str(metin).translate(_KATLA).lower()


_DURAK_HAM = """
bir bu su şu ve ile için icin ama fakat gibi daha çok cok en de da mi mı mu mü
ben sen biz siz onlar var yok olarak olan olsun şimdi simdi bunu şunu onu
bana sana ona yap yapıl yapil etmek et lütfen lutfen şey sey her hem ya
ki ise ne nasıl nasil neden the and for with
"""
_DURAK = {_katla(s) for s in _DURAK_HAM.split()}


def tokenler(metin):
    """Metni kaba köklere (ilk 5 karakter) ayrılmış kümeye çevirir."""
    if not isinstance(metin, str):
        return set()
    out = set()
    for s in re.findall(r"[^\W_]+", _katla(metin)):
        if len(s) < 3 or s in _DURAK:
            continue
        out.add(s[:KOK_UZUNLUK])
    return out


def _metin(v):
    return v if isinstance(v, str) else ""


def _skor_bir(istek_t, is_):
    baslik_klasor = tokenler(_metin(is_.get("baslik")) + " " + _metin(is_.get("klasor_adi")))
    puan = 2 * len(istek_t & baslik_klasor)
    todo_t = set()
    todolar = is_.get("acik_todolar")
    if isinstance(todolar, (list, tuple)):
        for t in todolar:
            todo_t |= tokenler(_metin(t))
    puan += len((istek_t & todo_t) - baslik_klasor)
    return puan


def skorla(istek, isler):
    """[(is_id, skor)] skora göre azalan (eşitlikte giriş sırası korunur)."""
    istek_t = tokenler(istek)
    sonuc = []
    if not isinstance(isler, (list, tuple)):
        return sonuc
    for is_ in isler:
        if not isinstance(is_, dict) or is_.get("id") is None:
            continue
        sonuc.append((is_["id"], _skor_bir(istek_t, is_)))
    sonuc.sort(key=lambda x: -x[1])
    return sonuc


def _tek_satir(metin, sinir):
    s = " ".join(str(metin).split())
    return s if len(s) <= sinir else s[: sinir - 1].rstrip() + "…"


def _satir_yeni(istek):
    kisa = _tek_satir(istek, 60)
    return _tek_satir(
        "Bu istek açık işlerle eşleşmiyor; yeni iş için: orkestra is ac \"%s\" --klasor <klasör>" % kisa,
        SATIR_SINIR)


def _satir_degistir(is_id, baslik):
    kisa = _tek_satir(baslik, 60)
    return _tek_satir(
        "Bu istek \"%s\" işine daha yakın: orkestra is devam %s" % (kisa, _tek_satir(is_id, 40)),
        SATIR_SINIR)


def yonlendir(istek, isler, bagli_id):
    """None ya da {tur: 'yeni'|'degistir', is: id|None, satir: str}."""
    skorlar = skorla(istek, isler)
    en_iyi_id, en_iyi = skorlar[0] if skorlar else (None, 0)

    if en_iyi < ESIK:
        if bagli_id is None:
            return {"tur": "yeni", "is": None, "satir": _satir_yeni(istek)}
        return None

    baslik = ""
    for is_ in isler:
        if isinstance(is_, dict) and is_.get("id") == en_iyi_id:
            baslik = _metin(is_.get("baslik"))
            break
    oneri = {"tur": "degistir", "is": en_iyi_id,
             "satir": _satir_degistir(en_iyi_id, baslik)}

    if bagli_id is None:
        return oneri
    if bagli_id == en_iyi_id:
        return None
    bagli = dict(skorlar).get(bagli_id, 0)
    if bagli * 2 >= en_iyi or en_iyi - bagli < ESIK:
        return None
    return oneri


def _tarih(deger, simdi):
    if not isinstance(deger, str):
        return None
    try:
        dt = datetime.fromisoformat(deger.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if simdi.tzinfo is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=simdi.tzinfo)
    elif simdi.tzinfo is None and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def _sayi(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def kapanis_adaylari(ozetler, simdi):
    """{'kapat': [id], 'bayat': [id]}; hatalı girişler atlanır."""
    sonuc = {"kapat": [], "bayat": []}
    if not isinstance(ozetler, (list, tuple)) or not isinstance(simdi, datetime):
        return sonuc
    for o in ozetler:
        try:
            if not isinstance(o, dict) or o.get("id") is None:
                continue
            toplam, biten, acik = _sayi(o.get("toplam")), _sayi(o.get("biten")), _sayi(o.get("acik_kart"))
            if toplam is not None and biten is not None and acik is not None \
                    and toplam > 0 and biten == toplam and acik == 0:
                sonuc["kapat"].append(o["id"])
                continue
            dt = _tarih(o.get("son_dokunus"), simdi)
            if dt is not None and simdi - dt >= timedelta(days=BAYAT_GUN):
                sonuc["bayat"].append(o["id"])
        except Exception:
            continue
    return sonuc
