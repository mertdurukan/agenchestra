"""Orkestra iş yönlendirme: yeni görev satırı, kapanış/bayat tespiti.

Sınıflandırmayı (görev hangi işe ait, yoksa yeni iş) ana ajan yapar; modül ona yalnız açık işleri
ve karar kuralını tek satırda gösterir. Saf Python, yalnız standart kütüphane; dosya, ağ ve alt süreç
kullanmaz; yan etkisi yoktur.
"""
from datetime import datetime, timedelta

BAYAT_GUN = 14
SATIR_SINIR = 500
MAX_IS = 6
BASLIK_SINIR = 28


def _tek_satir(metin, sinir):
    s = " ".join(str(metin).split())
    return s if len(s) <= sinir else s[: sinir - 1].rstrip() + "…"


def yonlendir(isler, bagli_id):
    """Yeni görev için tek satır: bağlı iş, açık işler ve karar kuralı."""
    liste = []
    bagli_baslik = ""
    for is_ in isler if isinstance(isler, (list, tuple)) else []:
        if not isinstance(is_, dict) or is_.get("id") is None:
            continue
        baslik = _tek_satir(is_.get("baslik") or "", BASLIK_SINIR)
        if bagli_id is not None and str(is_["id"]) == str(bagli_id):
            bagli_baslik = baslik
        if len(liste) < MAX_IS:
            liste.append("%s %s" % (_tek_satir(is_["id"], 20), baslik))
    bagli = ("bağlı iş %s %s" % (bagli_id, bagli_baslik)).strip() if bagli_id is not None else "bağlı iş yok"
    kural = ("Yeni görev (%s): bağlı işin parçasıysa devam; başka açık işe aitse `orkestra is devam <id>`; "
             "hiçbirine uymuyorsa `orkestra is ac \"<başlık>\" --klasor <klasör>`." % bagli)
    if liste:
        kural += " Açık işler: " + "; ".join(liste)
    return _tek_satir(kural, SATIR_SINIR)


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
