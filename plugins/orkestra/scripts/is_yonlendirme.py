"""Orkestra iş yönlendirme: yeni görev satırı, kapanış/bayat tespiti.

Sınıflandırmayı (görev hangi işe ait, yoksa yeni iş) ana ajan yapar; modül ona yalnız açık işleri
ve karar kuralını tek satırda gösterir. Saf Python, yalnız standart kütüphane; dosya, ağ ve alt süreç
kullanmaz; yan etkisi yoktur.
"""
import re
from datetime import datetime, timedelta

BAYAT_GUN = 14
SATIR_SINIR = 700
MAX_IS = 6
BASLIK_SINIR = 28


VARSAYILAN_AYAR = {
    "yuksek": 0.6,
    "dusuk": 0.2,
    "durak_sozcukler": ["ile", "için", "icin", "ama", "fakat", "gibi", "daha", "çok", "cok",
                        "bir", "bu", "şu", "su", "ve", "veya", "yeni", "olan", "olarak"],
    "soru_etiketi": "soru",
    "baslik_kapsama_min_sozcuk": 5,
}
MIN_SOZCUK = 3
ONEK_MIN = 5
_TR_KATLA = str.maketrans("çğıöşü", "cgiosu")


def _kucult(metin):
    return str(metin).replace("İ", "i").replace("I", "ı").lower()


def _katla(sozcuk):
    return sozcuk.translate(_TR_KATLA)


def _ayar(ayar):
    """Ayarı doğrular; bozuk/eksik alan gömülü varsayılana düşer."""
    a = dict(VARSAYILAN_AYAR)
    if not isinstance(ayar, dict):
        return a
    yuksek, dusuk = ayar.get("yuksek"), ayar.get("dusuk")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if num(yuksek) and num(dusuk) and 0 < dusuk <= yuksek <= 1:
        a["yuksek"], a["dusuk"] = float(yuksek), float(dusuk)
    if isinstance(ayar.get("durak_sozcukler"), list):
        a["durak_sozcukler"] = [str(x) for x in ayar["durak_sozcukler"]]
    if isinstance(ayar.get("soru_etiketi"), str) and ayar["soru_etiketi"].strip():
        a["soru_etiketi"] = ayar["soru_etiketi"].strip()
    m = ayar.get("baslik_kapsama_min_sozcuk")
    if isinstance(m, int) and not isinstance(m, bool) and m >= 1:
        a["baslik_kapsama_min_sozcuk"] = m
    return a


def _sozcukler(metin, durak):
    """Küçük harf (Türkçe İ/ı), noktalama atılır; durak ve ≤2 karakterli sözcükler elenir; ASCII'ye katlanır."""
    if not isinstance(metin, str):
        return []
    out = []
    for s in re.findall(r"[^\W_]+", _kucult(metin)):
        if len(s) < MIN_SOZCUK or s.isdigit() or s in durak:
            continue
        out.append(_katla(s))
    return out


def _eslesir(a, b):
    if a == b:
        return True
    kisa, uzun = (a, b) if len(a) <= len(b) else (b, a)
    return len(kisa) >= ONEK_MIN and uzun.startswith(kisa)


_YAN_OTURUM_ON = re.compile(r"^\s*(?:Background|Task) \(from the session[^)]*\):\s*", re.I)


def devir_onu_at(metin):
    """Yan oturum devir öneklerini ('Background|Task (from the session…):', art arda) atar; başlık üretimi ve eşleştirme ortak kullanır."""
    metin = str(metin or "")
    while True:
        yeni = _YAN_OTURUM_ON.sub("", metin)
        if yeni == metin:
            return metin
        metin = yeni


def eslestir(istek, isler, ayar=None):
    """İstek sözcüklerinin iş metniyle örtüşme oranı (0-1); puana göre azalan [{'id','puan'}].
    Devir önekleri ('Task (from the session…):') istekten ve iş başlığından atılır: ortak sözcükler (session, task, from) başka işe bağlamasın."""
    if not isinstance(istek, str) or not isinstance(isler, (list, tuple)):
        return []
    a = _ayar(ayar)
    durak_ham = {_kucult(x) for x in a["durak_sozcukler"]}
    istek_s = set(_sozcukler(devir_onu_at(istek), durak_ham))
    if not istek_s:
        return []
    sonuc = []
    for is_ in isler:
        if not isinstance(is_, dict) or is_.get("id") is None:
            continue
        metin = " ".join(devir_onu_at(is_.get(k)) for k in ("baslik", "klasor", "metin"))
        is_s = set(_sozcukler(metin, durak_ham))
        say = sum(1 for s in istek_s if any(_eslesir(s, t) for t in is_s))
        puan = say / len(istek_s)
        # I-138 P3: yeterince uzun başlıkta başlık kapsaması da sayılır (başlığı üreten mesaj o işe bağlanır)
        baslik_s = set(_sozcukler(devir_onu_at(is_.get("baslik")), durak_ham))
        if len(baslik_s) >= a["baslik_kapsama_min_sozcuk"]:
            bsay = sum(1 for t in baslik_s if any(_eslesir(s, t) for s in istek_s))
            puan = max(puan, bsay / len(baslik_s))
        sonuc.append({"id": is_["id"], "puan": min(1.0, puan)})
    sonuc.sort(key=lambda x: -x["puan"])
    return sonuc


def karar(puanlar, ayar=None):
    """('bagla', id) | ('ac', None) | ('sec', [id, ...]) (en çok iki)."""
    a = _ayar(ayar)
    liste = [p for p in puanlar if isinstance(p, dict) and isinstance(p.get("puan"), (int, float))] \
        if isinstance(puanlar, (list, tuple)) else []
    if not liste:
        return ("ac", None)
    liste.sort(key=lambda x: -x["puan"])
    ilk = liste[0]
    if ilk["puan"] >= a["yuksek"]:
        return ("bagla", ilk["id"])
    if ilk["puan"] < a["dusuk"]:
        return ("ac", None)
    return ("sec", [p["id"] for p in liste[:2] if p["puan"] >= a["dusuk"]])


def isle_ilgili_mi(mesaj, is_, ayar=None):
    """Mesaj bağlı işe açıkça gönderme yapıyor mu (iş kimliği, klasör numarası/adı) ya da iş metniyle
    yeterince örtüşüyor mu (eslestir puanı >= yuksek). 'plan'/'todo' sözcüğü tek başına sayılmaz."""
    if not isinstance(mesaj, str) or not isinstance(is_, dict):
        return False
    m = _kucult(mesaj)
    iid = _kucult(str(is_.get("id") or ""))
    klasor = _kucult(str(is_.get("klasor") or ""))
    if iid and re.search(r"(?<![\w-])" + re.escape(iid) + r"(?![\w-])", m):
        return True
    num = re.match(r"(\d{3})-", klasor)
    if (num and (num.group(1) + "-") in m) or (len(klasor) >= 8 and klasor in m):
        return True
    p = eslestir(mesaj, [is_], ayar)
    return bool(p) and p[0]["puan"] >= _ayar(ayar)["yuksek"]


def _tek_satir(metin, sinir):
    s = " ".join(str(metin).split())
    return s if len(s) <= sinir else s[: sinir - 1].rstrip() + "…"


def yonlendir(isler, bagli_id, zorunlu=False, guncel_konu=""):
    """Yeni görev için tek satır: bağlı iş, açık işler ve karar kuralı. `zorunlu` (I-061): hook mesajı bağlı işle
    ilgili bulmadı; satır hatırlatma değil, ilk mesajda uygulanacak yönergedir. `guncel_konu`: kayıtlı güncel niyet."""
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
    if bagli_id is not None and zorunlu:
        konu = (' Güncel konu: "%s".' % _tek_satir(guncel_konu, 80)) if guncel_konu else ""
        kural = ("Yeni görev (%s): ZORUNLU (K-004): mesaj bağlı işe açıkça bağlı değil.%s Cevabından ÖNCE, ilk araçtan önce karar ver: "
                 "farklı konuysa bu sohbette yapma, `start_session` (initiation offer, başlık) ile yeni oturum öner; "
                 "kullanıcı 'burada yap' derse `orkestra is devam <id>` ya da `orkestra is ac \"<başlık>\" --klasor <klasör>` "
                 "ve `orkestra niyet --ne ...` ile güncel konuyu yaz. Aynı işin devamıysa devam et." % (bagli, konu))
    elif bagli_id is not None:
        # K-004: bağlı işten farklı konu bu sohbette yapılmaz; ilk mesajda yeni oturum önerilir.
        kural = ("Yeni görev (%s): bağlı işin parçasıysa devam. Bağlı işten FARKLI konuysa bu sohbette yapma: "
                 "ilk mesajda `start_session` (initiation offer, başlık) ile yeni oturum öner. Kullanıcı 'burada yap' "
                 "derse: başka açık işe aitse `orkestra is devam <id>`, değilse `orkestra is ac \"<başlık>\" --klasor <klasör>`."
                 % bagli)
    else:
        kural = ("Yeni görev (%s): başka açık işe aitse `orkestra is devam <id>`; "
                 "hiçbirine uymuyorsa `orkestra is ac \"<başlık>\" --klasor <klasör>`." % bagli)
    kural += " Yeni iş sıralıdır: mevcut durum, plan, todo (P-005)."
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
