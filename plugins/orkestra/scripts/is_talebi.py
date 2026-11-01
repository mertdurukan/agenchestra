"""Todo işi talebi (kira) (I-324 P1, ADR-0138): aynı todo işi iki oturumda birden yapılmasın.

Bir oturum todo maddesine başlarken talep alır. Başka bir canlı oturumun talebi aynı işi gösteriyorsa sahip döner:
gölge modunda uyarı ve `kapi_golge` kaydı (talep yine alınır), ihlal modunda talep reddedilir (`kapi_ret`).
Aynı iş: yazma alanı kümeleri kesişir ya da normalize madde metinlerinin token Jaccard benzerliği eşiği geçer
(`ayarlar/is_talebi.json` `jaccard_esik`, varsayılan 0,6). Sahip oturum 30 dk (oturum_farkindalik.CANLI_S) canlı
görünmezse talebi düşer ve talep eden devralır. Kendi talebini yenilemek eşleşme sayılmaz.

Kayıt: `<sd>/oturumlar/talepler.json` (ork_lib.kilit altında). Model çağırmaz, subprocess açmaz; madde metni
maskelenerek saklanır. Mod: `ayarlar/is_talebi.json` (proje ezmesi `<sd>/is_talebi.json`), yoksa `golge`;
ORKESTRA_IS_TALEBI=0 kapatır.
"""
from __future__ import annotations

import json
import os
import re
import time

import ork_lib as L

KAPI = "is_talebi"
MODLAR = ("golge", "ihlal", "kapali")
VARSAYILAN_MOD = "golge"
VARSAYILAN_ESIK = 0.6
MADDE_EN_COK = 200
try:
    from oturum_farkindalik import CANLI_S
except Exception:  # pragma: no cover - modül her zaman var; yine de talep kaydı bozulmasın
    CANLI_S = 30 * 60

DURAK = frozenset("""
ve ile bir bu şu o için de da ki mi mı mu mü ya veya ama gibi olarak her en çok daha ne nasıl sonra önce
ise hem yani the a an and or of to in on for with by is are be at as
""".split())
_TEMIZLE = re.compile(r"[\W\d_]+", re.UNICODE)


# ---------------------------------------------------------------- ayar ve mod

def _ayar(sd: str | None) -> dict:
    """Eklenti `ayarlar/is_talebi.json` üstüne proje ezmesi `<sd>/is_talebi.json`; dosya yoksa boş sözlük."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yollar = [os.path.join(kok, "ayarlar", KAPI + ".json")]
    if sd:
        yollar.append(os.path.join(sd, KAPI + ".json"))
    sonuc: dict = {}
    for yol in yollar:
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                sonuc.update(d)
        except (OSError, ValueError):
            pass
    return sonuc


def mod(sd: str | None = None) -> str:
    """`golge` | `ihlal` | `kapali`. ORKESTRA_IS_TALEBI=0 kapatır; ayar yoksa ya da bilinmeyen değerde `golge`."""
    if os.environ.get("ORKESTRA_IS_TALEBI") == "0":
        return "kapali"
    m = _ayar(sd).get("mod")
    return m if m in MODLAR else VARSAYILAN_MOD


def esik(sd: str | None = None) -> float:
    try:
        e = float(_ayar(sd).get("jaccard_esik", VARSAYILAN_ESIK))
        return e if 0 < e <= 1 else VARSAYILAN_ESIK
    except (TypeError, ValueError):
        return VARSAYILAN_ESIK


# ---------------------------------------------------------------- eşleşme

def tokenlar(metin: str | None) -> frozenset:
    """Küçük harf, noktalama ve sayı atılır, durak sözcük ve tek harfli parça çıkarılır."""
    m = (metin or "").replace("İ", "i").lower()
    return frozenset(t for t in _TEMIZLE.sub(" ", m).split() if len(t) > 1 and t not in DURAK)


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    birlesim = a | b
    return len(a & b) / len(birlesim) if birlesim else 0.0


def _yol_norm(y: str) -> str:
    y = str(y).strip().replace("\\", "/")
    while y.startswith("./"):
        y = y[2:]
    return os.path.normcase(y).replace("\\", "/").rstrip("/")


def alan_kumesi(yazma_alani) -> frozenset:
    if isinstance(yazma_alani, str):
        yazma_alani = [x for x in re.split(r"[,;\n]", yazma_alani)]
    return frozenset(n for n in (_yol_norm(x) for x in (yazma_alani or []) if x) if n)


def alan_kesisir(a, b) -> bool:
    """Aynı yol ya da biri ötekinin klasörü (`scripts` ⊃ `scripts/x.py`)."""
    for x in a:
        for y in b:
            if x == y or x.startswith(y + "/") or y.startswith(x + "/"):
                return True
    return False


def eslesme(talep: dict, alan: frozenset, tok: frozenset, esik_: float) -> str | None:
    """Eşleşme nedeni: `yazma_alani`, `jaccard` ya da None."""
    if alan and alan_kesisir(alan, frozenset(talep.get("yazma_alani") or [])):
        return "yazma_alani"
    if tok and jaccard(tok, talep.get("tokenlar") or []) >= esik_ - 1e-9:
        return "jaccard"
    return None


# ---------------------------------------------------------------- kayıt

def kayit_yolu(sd: str) -> str:
    return os.path.join(sd, "oturumlar", "talepler.json")


def _oku(yol: str) -> list[dict]:
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        t = d.get("talepler") if isinstance(d, dict) else None
        return [x for x in t if isinstance(x, dict) and x.get("oturum")] if isinstance(t, list) else []
    except (OSError, ValueError):
        return []


def _yaz(yol: str, talepler: list[dict]) -> None:
    L.atomik_yaz(yol, json.dumps({"talepler": talepler}, ensure_ascii=False))


def _oturum_gorulme(sd: str, oturum: str) -> float:
    """Oturum kaydındaki `konum.gorulme` (oturum_farkindalik.kaydet yazar); yoksa 0."""
    durum, kayit = L._oturum_json_oku(L._oturum_json_yol(sd, oturum))
    k = kayit.get("konum") if durum == "ok" and isinstance(kayit.get("konum"), dict) else {}
    try:
        return float(k.get("gorulme") or 0)
    except (TypeError, ValueError):
        return 0.0


def sahip_canli(sd: str, talep: dict, t: float, esik_s: float = CANLI_S) -> bool:
    """Sahip son esik_s içinde görüldüyse canlı: talebin son yenilenmesi ya da oturum kaydının konum.gorulme'si."""
    son = max(float(talep.get("yenilendi") or 0), _oturum_gorulme(sd, str(talep["oturum"])))
    return t - son <= esik_s


def _sahip(talep: dict) -> dict:
    return {"oturum": talep.get("oturum"), "is_id": talep.get("is_id"), "madde": talep.get("madde")}


def _gunluk(sd: str, tur: str, olay: str, oturum: str, is_id, sahip: dict, neden: str, j: float) -> None:
    try:
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"),
                     {"zaman": L.simdi(), "tur": tur, "kapi": KAPI, "olay": olay, "oturum": str(oturum)[:8],
                      "is": is_id, "sahip": str(sahip.get("oturum") or "")[:8], "sahip_is": sahip.get("is_id"),
                      "neden": neden, "jaccard": round(j, 3)})
    except Exception:
        pass


def _kendi_mi(talep: dict, oturum: str, is_id, tok: frozenset) -> bool:
    return talep.get("oturum") == oturum and talep.get("is_id") == is_id and frozenset(talep.get("tokenlar") or []) == tok


def _tara(sd: str, talepler: list[dict], oturum: str, alan, tok, esik_: float, t: float):
    """(canlı eşleşen [(talep, neden)], ölü eşleşen [talep], ölü diğer [talep]); kendi oturumunun talepleri atlanır."""
    canli, olu_es, olu = [], [], []
    for x in talepler:
        if x.get("oturum") == oturum:
            continue
        neden = eslesme(x, alan, tok, esik_)
        if sahip_canli(sd, x, t):
            if neden:
                canli.append((x, neden))
        elif neden:
            olu_es.append(x)
        else:
            olu.append(x)
    canli.sort(key=lambda p: float(p[0].get("zaman") or 0))
    return canli, olu_es, olu


# ---------------------------------------------------------------- API

def talep_al(sd: str, oturum: str, is_id, madde_metni: str, yazma_alani=None, simdi: float | None = None) -> dict:
    """Madde için talep alır. Dönüş: {durum, sahip, mod, ...}.
    durum: `alindi` (eşleşme yok ya da kendi talebi yenilendi), `sahip_var` (canlı başka sahip; gölgede talep yine
    alınır, ihlalde `reddedildi: True`), `devralindi` (eşleşen sahip canlı değildi, talebi düştü), `kapali`, `hata`."""
    m = mod(sd)
    if m == "kapali" or not (sd and oturum):
        return {"durum": "kapali", "sahip": None, "mod": m}
    t = time.time() if simdi is None else simdi
    alan, tok = alan_kumesi(yazma_alani), tokenlar(madde_metni)
    esik_ = esik(sd)
    yol = kayit_yolu(sd)
    try:
        with L.kilit(yol):
            talepler = _oku(yol)
            canli, olu_es, olu = _tara(sd, talepler, oturum, alan, tok, esik_, t)
            dusen = {id(x) for x in olu_es + olu}
            talepler = [x for x in talepler if id(x) not in dusen]
            kendi = next((x for x in talepler if _kendi_mi(x, oturum, is_id, tok)), None)
            sonuc: dict = {"mod": m}
            if canli:
                ilk, neden = canli[0]
                j = jaccard(tok, ilk.get("tokenlar") or [])
                sonuc.update(durum="sahip_var", sahip=_sahip(ilk), neden=neden, jaccard=round(j, 3))
                if m == "ihlal":
                    sonuc["reddedildi"] = True
                    _gunluk(sd, "kapi_ret", "talep_al", oturum, is_id, sonuc["sahip"], neden, j)
                else:
                    _gunluk(sd, "kapi_golge", "talep_al", oturum, is_id, sonuc["sahip"], neden, j)
            elif olu_es:
                sonuc.update(durum="devralindi", sahip=_sahip(olu_es[0]))
            else:
                sonuc.update(durum="alindi", sahip=None)
            if not sonuc.get("reddedildi"):
                if kendi:
                    kendi["yenilendi"] = t
                    sonuc["yenilendi"] = True
                else:
                    talepler.append({"oturum": oturum, "is_id": is_id,
                                     "madde": L.maskele(" ".join(str(madde_metni or "").split()))[:MADDE_EN_COK],
                                     "tokenlar": sorted(tok), "yazma_alani": sorted(alan), "zaman": t, "yenilendi": t})
            if dusen or not sonuc.get("reddedildi"):
                _yaz(yol, talepler)
            return sonuc
    except Exception as e:  # hook'u bozmaz
        return {"durum": "hata", "sahip": None, "mod": m, "hata": type(e).__name__}


def _filtre(x: dict, oturum: str, is_id, madde_metni) -> bool:
    if x.get("oturum") != oturum or (is_id is not None and x.get("is_id") != is_id):
        return False
    return madde_metni is None or frozenset(x.get("tokenlar") or []) == tokenlar(madde_metni)


def yenile(sd: str, oturum: str, is_id=None, madde_metni: str | None = None, simdi: float | None = None) -> int:
    """Oturumun (süzülmüş) taleplerinin süresini yeniler; yenilenen sayısı."""
    if mod(sd) == "kapali" or not (sd and oturum):
        return 0
    t = time.time() if simdi is None else simdi
    yol = kayit_yolu(sd)
    try:
        with L.kilit(yol):
            talepler = _oku(yol)
            n = 0
            for x in talepler:
                if _filtre(x, oturum, is_id, madde_metni):
                    x["yenilendi"] = t
                    n += 1
            if n:
                _yaz(yol, talepler)
            return n
    except Exception:
        return 0


def birak(sd: str, oturum: str, is_id=None, madde_metni: str | None = None) -> int:
    """Oturumun (süzülmüş) taleplerini siler; silinen sayısı. Kapalı modda da çalışır (kayıt temizliği)."""
    if not (sd and oturum):
        return 0
    yol = kayit_yolu(sd)
    try:
        with L.kilit(yol):
            talepler = _oku(yol)
            kalan = [x for x in talepler if not _filtre(x, oturum, is_id, madde_metni)]
            if len(kalan) != len(talepler):
                _yaz(yol, kalan)
            return len(talepler) - len(kalan)
    except Exception:
        return 0


def devral_gerekir_mi(sd: str, oturum: str, is_id, madde_metni: str, yazma_alani=None,
                      simdi: float | None = None) -> dict:
    """Yazmadan önizleme: {gerekir, sahip, canli}. `gerekir` True: eşleşen talebin sahibi canlı değil, talep alınırsa
    devralınır. `canli` True: eşleşen canlı sahip var (iş onda). Eşleşme yoksa sahip None."""
    if mod(sd) == "kapali" or not (sd and oturum):
        return {"gerekir": False, "sahip": None, "canli": False}
    t = time.time() if simdi is None else simdi
    canli, olu_es, _ = _tara(sd, _oku(kayit_yolu(sd)), oturum, alan_kumesi(yazma_alani), tokenlar(madde_metni),
                             esik(sd), t)
    if canli:
        return {"gerekir": False, "sahip": _sahip(canli[0][0]), "canli": True}
    if olu_es:
        return {"gerekir": True, "sahip": _sahip(olu_es[0]), "canli": False}
    return {"gerekir": False, "sahip": None, "canli": False}


def satir(sonuc: dict) -> str:
    """Tek kısa bağlam satırı (≤250 karakter); sahip yoksa boş metin."""
    s = sonuc.get("sahip") if isinstance(sonuc, dict) else None
    if not s:
        return ""
    is_ = f", iş {s.get('is_id')}" if s.get("is_id") else ""
    if sonuc.get("durum") == "devralindi":
        metin = f"İş talebi devralındı: önceki sahip {str(s.get('oturum'))[:8]}{is_} 30 dk'dır görünmüyor."
    elif sonuc.get("reddedildi"):
        metin = f"UYARI: bu iş {str(s.get('oturum'))[:8]} oturumunda{is_}: talep reddedildi; maddeyi sahibe devret."
    else:
        metin = f"Bu iş {str(s.get('oturum'))[:8]} oturumunda olabilir{is_}: \"{str(s.get('madde') or '')[:80]}\"."
    return metin[:250]
