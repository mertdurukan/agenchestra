"""Onay merkezi: kuyruk, kaynak eşitleme ve kurallar (panel, CLI ve hook ortak kütüphanesi).

Depolama (sd = <proje>/.claude/orkestra):
  sd/onaylar/O-001.json ...      kayıt başına dosya
  sd/onaylar/gorulen.json        {oturum: son görülen karar zamanı}
  sd/kurallar/kurallar.json      {kurallar: [...]}
  <proje>/.claude/rules/orkestra_kurallari.md   etkin kurallardan üretilir (her değişimde atomik yazılır)

Eşzamanlılık: tüm değişiklikler tek kilit altında (sd/onaylar/.islem). Kilit yeniden girişli değildir;
bu yüzden herkese açık işlevler kilidi alıp `_` önekli iç işlevleri çağırır.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

TURLER = ("perspektif", "skill", "kural", "karar")
DURUMLAR = ("bekliyor", "onaylandi", "reddedildi", "uygulaniyor", "uygulandi", "eskidi", "iptal")
KURAL_DURUMLARI = ("oneri", "etkin", "reddedildi", "kaldirildi")
KURAL_DOSYASI = "orkestra_kurallari.md"
SKILL_MAX = 6000
KAYNAK_MAX = 8000
BAGLAM_MAX = 900


# ---------------------------------------------------------------- yardımcılar

def _an() -> str:
    """Mikrosaniye çözünürlüklü zaman: aynı saniyedeki kararlar 'görüldü' karşılaştırmasında kaçmasın."""
    return datetime.datetime.now().astimezone().isoformat(timespec="microseconds")


def _proje(sd: str) -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(sd)))


def _onay_dizini(sd: str) -> str:
    return os.path.join(sd, "onaylar")


def _kilit_yolu(sd: str) -> str:
    return os.path.join(_onay_dizini(sd), ".islem")


def _kurallar_yolu(sd: str) -> str:
    return os.path.join(sd, "kurallar", "kurallar.json")


def _kural_dosya_yolu(sd: str) -> str:
    return os.path.join(_proje(sd), ".claude", "rules", KURAL_DOSYASI)


def _kayit_yolu(sd: str, oid: str) -> str:
    if not re.fullmatch(r"O-\d{3,}", oid or ""):
        raise ValueError(f"geçersiz onay kimliği: {oid!r}")
    return os.path.join(_onay_dizini(sd), oid + ".json")


def _oku_json(yol: str, varsayilan):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return varsayilan


def _yaz_json(yol: str, veri) -> None:
    L.atomik_yaz(yol, json.dumps(veri, ensure_ascii=False, indent=2) + "\n")


def _kayit_oku(sd: str, oid: str) -> dict | None:
    return _oku_json(_kayit_yolu(sd, oid), None)


def _kayit_yaz(sd: str, k: dict) -> None:
    k["guncelleme"] = L.simdi()
    _yaz_json(_kayit_yolu(sd, k["id"]), k)


def _hepsi(sd: str) -> list[dict]:
    out = []
    d = _onay_dizini(sd)
    if os.path.isdir(d):
        for ad in sorted(os.listdir(d)):
            if re.fullmatch(r"O-\d{3,}\.json", ad):
                k = _oku_json(os.path.join(d, ad), None)
                if isinstance(k, dict):
                    out.append(k)
    return out


def _sonraki_id(sd: str) -> str:
    en = 0
    for k in _hepsi(sd):
        m = re.fullmatch(r"O-(\d+)", k.get("id", ""))
        if m:
            en = max(en, int(m.group(1)))
    return f"O-{en + 1:03d}"


def _olay(k: dict, olay: str, not_: str | None = None) -> None:
    g = {"zaman": L.simdi(), "olay": olay}
    if not_:
        g["not"] = not_
    k.setdefault("gecmis", []).append(g)


def _yeni_kayit(sd: str, tur: str, baslik: str, metin: str, kaynak, anahtar, secenekler, oturum) -> dict:
    if tur not in TURLER:
        raise ValueError(f"geçersiz tür: {tur!r} ({', '.join(TURLER)})")
    simdi = L.simdi()
    k = {"id": _sonraki_id(sd), "tur": tur, "baslik": baslik, "metin": metin, "kaynak": kaynak or "",
         "anahtar": anahtar or "", "secenekler": list(secenekler or []), "oturum": oturum,
         "durum": "bekliyor", "karar": None, "uygulama": None,
         "olusturma": simdi, "guncelleme": simdi, "gecmis": [{"zaman": simdi, "olay": "olusturuldu"}]}
    _kayit_yaz(sd, k)
    return k


def _anahtarli(sd: str, anahtar: str) -> dict | None:
    for k in _hepsi(sd):
        if k.get("anahtar") == anahtar:
            return k
    return None


# ---------------------------------------------------------------- kurallar (iç)

def _kurallar_oku(sd: str) -> list[dict]:
    v = _oku_json(_kurallar_yolu(sd), {"kurallar": []})
    return v.get("kurallar", []) if isinstance(v, dict) else []


def _kurallar_yaz(sd: str, liste: list[dict]) -> None:
    _yaz_json(_kurallar_yolu(sd), {"kurallar": liste})
    _kural_dosyasini_yaz(sd, liste)


def _kural_dosyasini_yaz(sd: str, liste: list[dict]) -> None:
    yol = _kural_dosya_yolu(sd)
    etkin = [r for r in liste if r.get("durum") == "etkin"]
    if not etkin:
        if os.path.exists(yol):
            os.remove(yol)
        return
    satirlar = ["# Orkestra kuralları (panelden yönetilir)", "",
                "Bu dosya Orkestra panelinden üretilir; elle düzenleme, panelde Kurallar sayfasını kullan.", ""]
    for r in etkin:
        tarih = (r.get("etkinlesme") or r.get("olusturma") or "")[:10]
        satirlar.append(f"- {_tek_satir(r['metin'])} ({r['id']}, {tarih})")
        if r.get("neden"):
            satirlar.append(f"  - Neden: {_tek_satir(r['neden'])}")
    L.atomik_yaz(yol, "\n".join(satirlar) + "\n")


def _tek_satir(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _kural_bul(liste: list[dict], kid: str) -> dict:
    for r in liste:
        if r.get("id") == kid:
            return r
    raise ValueError(f"kural bulunamadı: {kid}")


def _kural_sonraki_id(liste: list[dict]) -> str:
    en = 0
    for r in liste:
        m = re.fullmatch(r"K-(\d+)", r.get("id", ""))
        if m:
            en = max(en, int(m.group(1)))
    return f"K-{en + 1:03d}"


def _kural_yeni(liste: list[dict], metin: str, neden: str | None, durum: str, kaynak: str) -> dict:
    metin = L.maskele(_tek_satir(metin))
    if not metin:
        raise ValueError("kural metni boş olamaz.")
    simdi = L.simdi()
    r = {"id": _kural_sonraki_id(liste), "metin": metin, "neden": L.maskele(_tek_satir(neden)) if neden else "",
         "durum": durum, "kaynak": kaynak, "olusturma": simdi, "guncelleme": simdi,
         "gecmis": [{"zaman": simdi, "olay": "olusturuldu" if durum == "oneri" else "eklendi", "metin": metin}]}
    if durum == "etkin":
        r["etkinlesme"] = simdi
    liste.append(r)
    return r


def _kural_durum(r: dict, durum: str, olay: str, not_: str | None = None) -> None:
    r["durum"] = durum
    r["guncelleme"] = L.simdi()
    if durum == "etkin":
        r["etkinlesme"] = r["guncelleme"]
    g = {"zaman": r["guncelleme"], "olay": olay}
    if not_:
        g["not"] = not_
    r.setdefault("gecmis", []).append(g)


# ---------------------------------------------------------------- eşitleme

_MADDE = re.compile(r"^(\d+)\.\s+\S")
_CIT = re.compile(r"^\s*(```|~~~)")


def _rapor_maddeleri(metin: str) -> list[tuple[str, int, str]]:
    """Rapordan (bölüm kısaltması, numara, madde metni) üçlüleri: 'oneri' ve 'skill' bölümleri."""
    out = []
    bolum = None
    cur = None
    cit = False

    def kapat():
        nonlocal cur
        if cur:
            out.append((cur[0], cur[1], "\n".join(cur[2]).rstrip()))
        cur = None

    for satir in metin.splitlines():
        if _CIT.match(satir):
            cit = not cit
        if not cit and satir.startswith("## "):
            kapat()
            b = satir.lower()
            if "önerilen" in b:
                bolum = "oneri"
            elif "skill" in b and "aday" in b:
                bolum = "skill"
            else:
                bolum = None
            continue
        if bolum is None:
            continue
        m = None if cit or _CIT.match(satir) else _MADDE.match(satir)
        if m:
            kapat()
            cur = (bolum, int(m.group(1)), [satir])
        elif cur:
            cur[2].append(satir)
    kapat()
    return out


def _skill_adi(ilk_satir: str) -> str:
    govde = re.sub(r"^\d+\.\s+", "", ilk_satir).strip()
    m = re.search(r"\*\*(.+?)\*\*", govde)
    return (m.group(1) if m else govde).strip()


def en_yeni_rapor(sd: str) -> str | None:
    """sd/perspektif/ ve sd/ruya/ altındaki raporlardan dosya adındaki tarih damgasına göre en yenisi (hata dosyaları hariç)."""
    adaylar = (glob.glob(os.path.join(sd, "perspektif", "perspektif_*.md"))
               + glob.glob(os.path.join(sd, "perspektif", "ruya_*.md"))
               + glob.glob(os.path.join(sd, "ruya", "ruya_*.md")))
    raporlar = [p for p in adaylar if not os.path.basename(p).startswith(("ruya_hata_", "perspektif_hata_"))]
    if not raporlar:
        return None

    def damga(p):
        ad = os.path.basename(p)
        return (re.sub(r"^(?:ruya|perspektif)_", "", ad), ad)

    return max(raporlar, key=damga)


def _esitle_perspektif(sd: str) -> None:
    yol = en_yeni_rapor(sd)
    if not yol:
        return
    ad = os.path.basename(yol)
    with open(yol, encoding="utf-8", errors="replace") as f:
        metin = f.read()
    for bolum, n, govde in _rapor_maddeleri(metin):
        anahtar = f"perspektif:{ad}#{bolum}-{n}"
        if _anahtarli(sd, anahtar):
            continue
        ilk = govde.splitlines()[0]
        if bolum == "skill":
            baslik = "Skill adayı: " + _skill_adi(ilk)
        else:
            baslik = re.sub(r"^\d+\.\s+", "", ilk).strip()[:100]
        _yeni_kayit(sd, "perspektif", baslik, govde, yol, anahtar, [], None)
    # Daha eski rapordan gelen, hâlâ bekleyen perspektif kayıtları eskir.
    for k in _hepsi(sd):
        a = k.get("anahtar", "")
        if k.get("tur") == "perspektif" and k.get("durum") == "bekliyor" and a.startswith("perspektif:"):
            if a[len("perspektif:"):].split("#")[0] != ad:
                k["durum"] = "eskidi"
                _olay(k, "eskidi", f"yeni rapor: {ad}")
                _kayit_yaz(sd, k)


def _kes(s: str, n: int) -> str:
    return s[:n]


def _esitle_skill(sd: str) -> None:
    kok = os.path.join(sd, "onerilen_skill")
    if not os.path.isdir(kok):
        return
    skills = os.path.join(_proje(sd), ".claude", "skills")
    for ad in sorted(os.listdir(kok)):
        klasor = os.path.join(kok, ad)
        skill_md = os.path.join(klasor, "SKILL.md")
        if not os.path.isfile(skill_md) or os.path.exists(os.path.join(skills, ad)):
            continue
        anahtar = f"skill:{ad}"
        if _anahtarli(sd, anahtar):
            continue
        parcalar = []
        for dosya in ("GEREKCE.md", "SKILL.md"):
            yol = os.path.join(klasor, dosya)
            if os.path.isfile(yol):
                with open(yol, encoding="utf-8", errors="replace") as f:
                    parcalar.append(_kes(f.read(), SKILL_MAX))
        _yeni_kayit(sd, "skill", f"Skill önerisi: {ad}", "\n\n---\n\n".join(parcalar), klasor, anahtar, [], None)


def _esitle_kural(sd: str) -> None:
    for r in _kurallar_oku(sd):
        if r.get("durum") != "oneri":
            continue
        anahtar = f"kural:{r['id']}"
        if _anahtarli(sd, anahtar):
            continue
        _kural_onayi_ac(sd, r)


def _kural_onayi_ac(sd: str, r: dict) -> dict:
    metin = r["metin"] + (f"\n\nNeden: {r['neden']}" if r.get("neden") else "")
    return _yeni_kayit(sd, "kural", "Kural önerisi: " + r["metin"][:80], metin, r.get("kaynak"),
                       f"kural:{r['id']}", [], None)


def esitle(sd: str) -> None:
    """Kaynaklardan bekleyen kayıt üretir; idempotent (anahtar varsa yeni kayıt açmaz)."""
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        _esitle_perspektif(sd)
        _esitle_skill(sd)
        _esitle_kural(sd)


# ---------------------------------------------------------------- sorgu

def liste(sd: str, durum: str | None = None, tur: str | None = None) -> list[dict]:
    kayitlar = [k for k in _hepsi(sd) if (not durum or k.get("durum") == durum) and (not tur or k.get("tur") == tur)]
    kayitlar.sort(key=lambda k: k.get("guncelleme", ""), reverse=True)
    kayitlar.sort(key=lambda k: k.get("durum") != "bekliyor")  # kararlı: bekleyenler önce
    return kayitlar


def goster(sd: str, id: str) -> dict | None:
    try:
        return _kayit_oku(sd, id)
    except ValueError:
        return None


def sayac(sd: str) -> dict:
    s = {"bekliyor": 0, "uygulanacak": 0, "tur": {t: 0 for t in TURLER}}
    for k in _hepsi(sd):
        if k.get("durum") == "bekliyor":
            s["bekliyor"] += 1
            s["tur"][k.get("tur", "karar")] = s["tur"].get(k.get("tur", "karar"), 0) + 1
        elif k.get("durum") in ("onaylandi", "uygulaniyor"):
            s["uygulanacak"] += 1
    return s


# ---------------------------------------------------------------- değişiklikler

def iste(sd: str, baslik: str, metin: str, secenekler=None, tur: str = "karar", oturum=None,
         kaynak=None, anahtar=None) -> dict:
    """Ajanın panelden karar istemesi. anahtar verilir ve varsa mevcut kayıt döner."""
    if not (baslik or "").strip():
        raise ValueError("başlık boş olamaz.")
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        if anahtar:
            var = _anahtarli(sd, anahtar)
            if var:
                return var
        return _yeni_kayit(sd, tur, baslik.strip(), metin or "", kaynak or oturum, anahtar, secenekler, oturum)


def _gerekli(sd: str, id: str) -> dict:
    k = _kayit_oku(sd, id)
    if not k:
        raise ValueError(f"onay kaydı bulunamadı: {id}")
    return k


def karar_ver(sd: str, id: str, sonuc: str, secim=None, not_=None, kim: str = "panel") -> dict:
    if sonuc not in ("onay", "ret"):
        raise ValueError("sonuç 'onay' ya da 'ret' olmalı.")
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        k = _gerekli(sd, id)
        if k["durum"] != "bekliyor":
            raise ValueError(f"{id} bekliyor durumunda değil (şu an: {k['durum']}); karar verilemez.")
        if sonuc == "onay" and k.get("secenekler"):
            if not secim:
                raise ValueError(f"{id} için seçim zorunlu: {', '.join(k['secenekler'])}")
            if secim not in k["secenekler"]:
                raise ValueError(f"geçersiz seçim {secim!r}; seçenekler: {', '.join(k['secenekler'])}")
        zaman = _an()
        k["karar"] = {"sonuc": sonuc, "secim": secim, "not": not_, "zaman": zaman, "kim": kim}
        k["durum"] = "onaylandi" if sonuc == "onay" else "reddedildi"
        _olay(k, "onaylandi" if sonuc == "onay" else "reddedildi", not_)
        if k["tur"] == "kural" and (k.get("anahtar") or "").startswith("kural:"):
            liste_ = _kurallar_oku(sd)
            try:
                r = _kural_bul(liste_, k["anahtar"].split(":", 1)[1])
            except ValueError:
                r = None
            if r and r.get("durum") == "oneri":
                if sonuc == "onay":
                    _kural_durum(r, "etkin", "etkinleştirildi", not_)
                    k["durum"] = "uygulandi"
                    k["uygulama"] = {"oturum": None, "alma_zamani": None, "zaman": L.simdi(),
                                     "ozet": "panelde etkinleştirildi"}
                    _olay(k, "uygulandi", "panelde etkinleştirildi")
                else:
                    _kural_durum(r, "reddedildi", "reddedildi", not_)
                _kurallar_yaz(sd, liste_)
        _kayit_yaz(sd, k)
        return k


def al(sd: str, id: str, oturum: str) -> dict:
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        k = _gerekli(sd, id)
        if k["durum"] == "uygulaniyor":
            if (k.get("uygulama") or {}).get("oturum") == oturum:
                return k
            raise ValueError(f"{id} zaten {(k.get('uygulama') or {}).get('oturum')} oturumu tarafından alındı.")
        if k["durum"] != "onaylandi":
            raise ValueError(f"{id} onaylandı durumunda değil (şu an: {k['durum']}); alınamaz.")
        k["durum"] = "uygulaniyor"
        k["uygulama"] = {"oturum": oturum, "alma_zamani": L.simdi(), "zaman": None, "ozet": None}
        _olay(k, "alindi", oturum)
        _kayit_yaz(sd, k)
        return k


def uygulandi(sd: str, id: str, ozet: str, oturum=None) -> dict:
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        k = _gerekli(sd, id)
        if k["durum"] not in ("onaylandi", "uygulaniyor"):
            raise ValueError(f"{id} uygulanabilir durumda değil (şu an: {k['durum']}).")
        u = k.get("uygulama") or {"oturum": oturum, "alma_zamani": None}
        if oturum and not u.get("oturum"):
            u["oturum"] = oturum
        u["zaman"] = L.simdi()
        u["ozet"] = ozet
        k["uygulama"] = u
        k["durum"] = "uygulandi"
        _olay(k, "uygulandi", ozet)
        _kayit_yaz(sd, k)
        return k


def iptal(sd: str, id: str, not_: str) -> dict:
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        k = _gerekli(sd, id)
        if k["durum"] not in ("bekliyor", "onaylandi", "uygulaniyor"):
            raise ValueError(f"{id} iptal edilemez (şu an: {k['durum']}).")
        k["durum"] = "iptal"
        _olay(k, "iptal", not_)
        if k["tur"] == "kural" and (k.get("anahtar") or "").startswith("kural:"):
            liste_ = _kurallar_oku(sd)
            try:
                r = _kural_bul(liste_, k["anahtar"].split(":", 1)[1])
            except ValueError:
                r = None
            if r and r.get("durum") == "oneri":
                _kural_durum(r, "reddedildi", "onay iptal edildi", not_)
                _kurallar_yaz(sd, liste_)
        _kayit_yaz(sd, k)
        return k


# ---------------------------------------------------------------- hook bağlamı

def _kisalt(s: str, n: int) -> str:
    s = _tek_satir(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def gorulen_isaretle(sd: str, oturum: str) -> None:
    """Oturumun taban zamanını şimdiki en son karar zamanına çeker: geçmiş kararlar UserPromptSubmit'te dökülmez."""
    if not oturum or not os.path.isdir(_onay_dizini(sd)):
        return
    with L.kilit(_kilit_yolu(sd)):
        en = max(((k.get("karar") or {}).get("zaman", "") for k in _hepsi(sd)), default="")
        if not en:
            return
        yol = os.path.join(_onay_dizini(sd), "gorulen.json")
        gorulen = _oku_json(yol, {})
        if gorulen.get(oturum, "") < en:
            gorulen[oturum] = en
            _yaz_json(yol, gorulen)


def baglam_metni(sd: str, oturum: str, olay: str) -> str:
    """Hook'un ajana eklediği kısa metin (en çok 900 karakter); söyleyecek şey yoksa ''."""
    if not os.path.isdir(_onay_dizini(sd)):
        return ""
    if olay == "SessionStart":
        kayitlar = _hepsi(sd)
        uygulanacak = [k for k in kayitlar if k.get("durum") == "onaylandi"
                       and (k.get("tur") != "karar" or not k.get("oturum") or k.get("oturum") == oturum)]
        bekleyen = sum(1 for k in kayitlar if k.get("durum") == "bekliyor")
        parcalar = []
        if uygulanacak:
            satirlar = "; ".join(f"{k['id']} [{k['tur']}] {_kisalt(k['baslik'], 60)}" for k in uygulanacak)
            parcalar.append(f"Panelde onaylanmış, uygulanmayı bekleyen {len(uygulanacak)} karar "
                            f"(→ /orkestra:onay ile uygula): {satirlar}.")
        if bekleyen:
            parcalar.append(f"Kullanıcının panelde vereceği {bekleyen} karar bekliyor (/onaylar).")
        gorulen_isaretle(sd, oturum)
        return _kisalt_metin(" ".join(parcalar))
    if olay == "UserPromptSubmit":
        with L.kilit(_kilit_yolu(sd)):
            yol = os.path.join(_onay_dizini(sd), "gorulen.json")
            gorulen = _oku_json(yol, {})
            son = gorulen.get(oturum, "")
            yeni = []
            for k in _hepsi(sd):
                kz = (k.get("karar") or {}).get("zaman", "")
                if not kz or kz <= son:
                    continue
                if k.get("tur") == "karar" and k.get("oturum") and k.get("oturum") != oturum:
                    continue
                yeni.append((kz, k))
            if not yeni:
                return ""
            yeni.sort(key=lambda x: x[0])
            satirlar = []
            for kz, k in yeni:
                kr = k["karar"]
                if k["tur"] == "karar":
                    cevap = kr.get("secim") or ("ret" if kr.get("sonuc") == "ret" else "onay")
                    s = f"{k['id']} kararın: {cevap}"
                    if kr.get("not"):
                        s += f" (not: {_kisalt(kr['not'], 120)})"
                else:
                    s = (f"{k['id']} [{k['tur']}] {'onaylandı' if kr.get('sonuc') == 'onay' else 'reddedildi'}: "
                         f"{_kisalt(k['baslik'], 60)}")
                satirlar.append(s)
            gorulen[oturum] = yeni[-1][0]
            _yaz_json(yol, gorulen)
            metin = "Panel kararları: " + "; ".join(satirlar)
            if any(k["durum"] == "onaylandi" and k["tur"] != "karar" for _, k in yeni):
                metin += " → /orkestra:onay ile uygula."
            return _kisalt_metin(metin)
    return ""


def _kisalt_metin(s: str) -> str:
    return s if len(s) <= BAGLAM_MAX else s[: BAGLAM_MAX - 1] + "…"


# ---------------------------------------------------------------- kurallar (genel)

def kurallar(sd: str) -> list:
    return _kurallar_oku(sd)


def _kural_islemi(sd: str, islem):
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        liste_ = _kurallar_oku(sd)
        sonuc = islem(liste_)
        _kurallar_yaz(sd, liste_)
        return sonuc


def kural_oner(sd: str, metin: str, neden: str, kaynak: str) -> dict:
    """Öneri kuralı açar ve panelde onaylanması için tur='kural' onay kaydı ekler."""
    def is_(liste_):
        r = _kural_yeni(liste_, metin, neden, "oneri", kaynak)
        _kural_onayi_ac(sd, r)
        return r
    return _kural_islemi(sd, is_)


def kural_ekle(sd: str, metin: str, neden: str, kaynak: str = "panel") -> dict:
    """Doğrudan etkin kural (kullanıcı yazar)."""
    return _kural_islemi(sd, lambda liste_: _kural_yeni(liste_, metin, neden, "etkin", kaynak))


def kural_duzenle(sd: str, id: str, metin: str, neden: str | None = None) -> dict:
    def is_(liste_):
        r = _kural_bul(liste_, id)
        if r["durum"] not in ("oneri", "etkin"):
            raise ValueError(f"{id} düzenlenemez (durum: {r['durum']}).")
        yeni = L.maskele(_tek_satir(metin))
        if not yeni:
            raise ValueError("kural metni boş olamaz.")
        r.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": "duzenlendi", "metin": r["metin"]})
        r["metin"] = yeni
        if neden is not None:
            r["neden"] = L.maskele(_tek_satir(neden))
        r["guncelleme"] = L.simdi()
        return r
    return _kural_islemi(sd, is_)


def kural_kaldir(sd: str, id: str, not_: str) -> dict:
    def is_(liste_):
        r = _kural_bul(liste_, id)
        if r["durum"] not in ("oneri", "etkin"):
            raise ValueError(f"{id} kaldırılamaz (durum: {r['durum']}).")
        bekleyen_oneri = r["durum"] == "oneri"
        _kural_durum(r, "kaldirildi", "kaldirildi", not_)
        if bekleyen_oneri:
            k = _anahtarli(sd, f"kural:{id}")
            if k and k.get("durum") == "bekliyor":
                k["durum"] = "iptal"
                _olay(k, "iptal", "kural kaldırıldı")
                _kayit_yaz(sd, k)
        return r
    return _kural_islemi(sd, is_)


def kural_gorunum(sd: str, proje: str) -> dict:
    liste_ = _kurallar_oku(sd)
    oneriler = []
    for r in liste_:
        if r.get("durum") == "oneri":
            k = _anahtarli(sd, f"kural:{r['id']}")
            oneriler.append(dict(r, onay_id=k["id"] if k else None))
    return {"etkin": [r for r in liste_ if r.get("durum") == "etkin"],
            "oneriler": oneriler,
            "gecmis": [r for r in liste_ if r.get("durum") in ("reddedildi", "kaldirildi")],
            "kaynaklar": _kural_kaynaklari(proje)}


def _kural_kaynaklari(proje: str) -> list[dict]:
    out = []
    claude_md = os.path.join(proje, "CLAUDE.md")
    if os.path.isfile(claude_md):
        with open(claude_md, encoding="utf-8", errors="replace") as f:
            satirlar = f.read().splitlines()
        i = 0
        while i < len(satirlar):
            s = satirlar[i]
            if s.startswith("## ") and "orkestra" in s.lower():
                j = i + 1
                while j < len(satirlar) and not satirlar[j].startswith("## "):
                    j += 1
                out.append({"yol": claude_md, "baslik": s[3:].strip(),
                            "metin": "\n".join(satirlar[i + 1:j]).strip()[:KAYNAK_MAX]})
                i = j
            else:
                i += 1
    for yol in sorted(glob.glob(os.path.join(proje, ".claude", "rules", "*.md"))):
        ad = os.path.basename(yol)
        if ad == KURAL_DOSYASI:
            continue
        with open(yol, encoding="utf-8", errors="replace") as f:
            out.append({"yol": yol, "baslik": ad, "metin": f.read().strip()[:KAYNAK_MAX]})
    return out
