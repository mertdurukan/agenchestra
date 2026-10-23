"""Onay merkezi: kuyruk, kaynak eşitleme ve kurallar (panel, CLI ve hook ortak kütüphanesi).

Depolama (sd = <proje>/.claude/orkestra):
  sd/onaylar/O-001.json ...      kayıt başına dosya
  sd/onaylar/gorulen.json        {oturum: son görülen karar zamanı}
  sd/kurallar/kurallar.json      {kurallar: [...], devre_disi: {...}}   proje katmanı
  <eklenti>/kurallar/eklenti_kurallari.json   {kurallar: [...]}          plugin katmanı (her projede geçerli)
  <proje>/.claude/rules/orkestra_kurallari.md   iki katmanın etkin kurallarından üretilir (her değişimde atomik yazılır)

Eşzamanlılık: tüm değişiklikler tek kilit altında (sd/onaylar/.islem). Kilit yeniden girişli değildir;
bu yüzden herkese açık işlevler kilidi alıp `_` önekli iç işlevleri çağırır.
"""
from __future__ import annotations

import datetime
import copy
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
KATMANLAR = ("proje", "plugin")
KATMAN_TAKMA = {"eklenti": "plugin"}
EKLENTI_DOSYASI = "eklenti_kurallari.json"
ESKI_BASLA = "<!-- eklenti-kurallari:basla -->"
ESKI_BITIS = "<!-- eklenti-kurallari:bitis -->"
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


def _yeni_kayit(sd: str, tur: str, baslik: str, metin: str, kaynak, anahtar, secenekler, oturum, ek: dict | None = None) -> dict:
    if tur not in TURLER:
        raise ValueError(f"geçersiz tür: {tur!r} ({', '.join(TURLER)})")
    simdi = L.simdi()
    k = {"id": _sonraki_id(sd), "tur": tur, "baslik": baslik, "metin": metin, "kaynak": kaynak or "",
         "anahtar": anahtar or "", "secenekler": list(secenekler or []), "oturum": oturum,
         "durum": "bekliyor", "karar": None, "uygulama": None,
         "olusturma": simdi, "guncelleme": simdi, "gecmis": [{"zaman": simdi, "olay": "olusturuldu"}]}
    if ek:
        k.update(ek)
    _kayit_yaz(sd, k)
    return k


def _etki_kancasi(k: dict, islem) -> None:
    """Etki ölçümü kancası (G-069): başarısızsa kayıt olduğu gibi kalır, onay akışı bozulmaz."""
    yedek = copy.deepcopy(k)
    try:
        islem()
    except Exception:
        k.clear()
        k.update(yedek)


def _anahtarli(sd: str, anahtar: str) -> dict | None:
    for k in _hepsi(sd):
        if k.get("anahtar") == anahtar:
            return k
    return None


# ---------------------------------------------------------------- kurallar (iç)
#
# İki katman: "proje" (sd/kurallar/kurallar.json; yalnız bu projeye özgü) ve "plugin" (eklenti deposunda
# kurallar/eklenti_kurallari.json; her projede geçerli). Kayıt biçimi aynıdır, `katman` alanı katmanı söyler.
# Kimlikler: proje K-nnn, eklentide yeni kurallar P-nnn; eklentiye taşınmış eski K-nnn kimlikleri korunur
# (belgeler ve kod o kimliğe atıf yapıyor). Proje için sonraki K numarası iki katmandaki en büyük K'dan türer,
# böylece korunan kimlik yeniden kullanılmaz. Çakışmada proje kuralı eklenti kuralından önce gelir.

def eklenti_kural_yolu() -> str:
    """Eklenti katmanının kural deposu. Önbellekten (plugins/cache) çalışırken yazım önbelleğe değil kaynak depoya gider
    (önbellek güncellemede silinir); kaynak yoksa ya da kaynak klasörden çalışılıyorsa PLUGIN_ROOT. Test ve özel kurulum:
    ORKESTRA_EKLENTI_KURALLARI tam dosya yolu."""
    env = os.environ.get("ORKESTRA_EKLENTI_KURALLARI")
    if env:
        return env
    kok = L.PLUGIN_ROOT
    if "/plugins/cache/" in os.path.normcase(kok).replace("\\", "/"):
        kaynak = L.pazar_kaynagi()
        aday = os.path.join(kaynak, "plugins", "orkestra") if kaynak else ""
        if aday and os.path.isdir(aday):
            kok = aday
    return L.kaynaga_cevir(os.path.join(kok, "kurallar", EKLENTI_DOSYASI))  # klondaysa kaynak depodaki dosya


def _katman_adi(katman: str | None) -> str:
    k = KATMAN_TAKMA.get((katman or "proje").strip().lower(), (katman or "proje").strip().lower())
    if k not in KATMANLAR:
        raise ValueError(f"geçersiz katman: {katman!r} ({', '.join(KATMANLAR)})")
    return k


def _depo_oku(sd: str) -> dict:
    v = _oku_json(_kurallar_yolu(sd), {"kurallar": []})
    if isinstance(v, list):
        v = {"kurallar": v}
    if not isinstance(v, dict):
        v = {"kurallar": []}
    if not isinstance(v.get("kurallar"), list):
        v["kurallar"] = []
    return v


def _kurallar_oku(sd: str) -> list[dict]:
    """Proje katmanı (geriye uyumlu ad). Eski kayıtlarda katman yoksa 'proje' sayılır."""
    liste_ = _depo_oku(sd)["kurallar"]
    for r in liste_:
        if isinstance(r, dict):
            r.setdefault("katman", "proje")
    return liste_


def _eklenti_oku() -> list[dict]:
    v = _oku_json(eklenti_kural_yolu(), {"kurallar": []})
    liste_ = v.get("kurallar", []) if isinstance(v, dict) else []
    liste_ = liste_ if isinstance(liste_, list) else []
    for r in liste_:
        if isinstance(r, dict):
            r["katman"] = "plugin"
    return liste_


def _katman_oku(sd: str, katman: str) -> list[dict]:
    return _eklenti_oku() if katman == "plugin" else _kurallar_oku(sd)


def _kurallar_yaz(sd: str, liste: list[dict]) -> None:
    """Proje deposunu yazar (devre_disi gibi başka anahtarlar korunur) ve kural dosyasını üretir."""
    depo = _depo_oku(sd)
    depo["kurallar"] = liste
    _yaz_json(_kurallar_yolu(sd), depo)
    _kural_dosyasini_yaz(sd)


def _eklenti_yaz(sd: str, liste: list[dict]) -> None:
    _yaz_json(eklenti_kural_yolu(), {"kurallar": liste})
    _kurallar_md_blogu_yaz(liste)
    _kural_dosyasini_yaz(sd)


def _katman_yaz(sd: str, katman: str, liste: list[dict]) -> None:
    (_eklenti_yaz if katman == "plugin" else _kurallar_yaz)(sd, liste)


def _devre_disi(sd: str) -> dict[str, dict]:
    """Bu projede kapatılmış eklenti kuralları: {kimlik: {not, zaman}}."""
    v = _depo_oku(sd).get("devre_disi")
    return {k: (x if isinstance(x, dict) else {}) for k, x in v.items()} if isinstance(v, dict) else {}


def etkin_kurallar(sd: str) -> list[dict]:
    """Bu projede geçerli etkin kurallar: eklenti (bu projede kapatılmamış) önce, proje sonra; her kayıtta `katman`."""
    kapali = _devre_disi(sd)
    out = [r for r in _eklenti_oku() if r.get("durum") == "etkin" and r.get("id") not in kapali]
    out += [r for r in _kurallar_oku(sd) if r.get("durum") == "etkin"]
    return out


def _kural_dosya_metni(sd: str) -> str:
    plug = [r for r in _eklenti_oku() if r.get("durum") == "etkin"]
    kapali = _devre_disi(sd)
    # yukle=hook: kuralı bir hook zorluyor ve gereken anda söylüyor; her oturumda yüklenen dosyaya girmez (panelde ve KURALLAR.md'de kalır)
    plug_acik = [r for r in plug if r.get("id") not in kapali and r.get("yukle") != "hook"]
    proje = [r for r in _kurallar_oku(sd) if r.get("durum") == "etkin"]
    if not plug_acik and not proje:
        return ""
    satirlar = ["# Orkestra kuralları (panelden yönetilir)", "",
                "Bu dosya Orkestra panelinden üretilir; elle düzenleme, panelde Kurallar sayfasını kullan.", ""]

    def kural_satirlari(liste_):
        for r in liste_:
            tarih = (r.get("etkinlesme") or r.get("olusturma") or "")[:10]
            satirlar.append(f"- {_tek_satir(r['metin'])} ({r['id']}, {tarih})")

    if plug_acik:  # tek katmanlıysa eski düzen (başlıksız) korunur
        satirlar += ["Çakışmada proje kuralı eklenti kuralından önce gelir.", "",
                     "## Eklenti kuralları (orkestra eklentisinden; her projede geçerli)", ""]
    kural_satirlari(plug_acik)
    if plug_acik and proje:
        satirlar += ["", "## Proje kuralları (yalnız bu projeye özgü)", ""]
    kural_satirlari(proje)
    kapali_etkin = [r for r in plug if r.get("id") in kapali]
    if kapali_etkin:
        satirlar += ["", "Bu projede kapatılmış eklenti kuralları (geçerli değil): "
                     + ", ".join(f"{r['id']}" + (f" ({_tek_satir(kapali[r['id']].get('not'))})" if kapali[r["id"]].get("not") else "")
                                 for r in kapali_etkin) + "."]
    return "\n".join(satirlar) + "\n"


def _kural_dosyasini_yaz(sd: str, liste: list[dict] | None = None) -> None:
    """<proje>/.claude/rules/orkestra_kurallari.md: iki katmanın etkin kuralları. Etkin kural yoksa dosya silinir.
    `liste` yalnız eski çağrılar için kabul edilir; içerik her zaman iki depodan okunur."""
    yol = _kural_dosya_yolu(sd)
    metin = _kural_dosya_metni(sd)
    if not metin:
        if os.path.exists(yol):
            os.remove(yol)
        return
    L.atomik_yaz(yol, metin)


def kural_dosyasi_esitle(sd: str) -> bool:
    """SessionStart: eklenti katmanı değişmişse (başka depodan güncelleme, başka projede eklenen kural) bu projenin kural
    dosyasını yeniler. İçerik aynıysa yazmaz. Yazdıysa True. Kural dosyası oturum açılışında yüklendiği için yeni içerik
    bir sonraki oturumda görünür."""
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        yol = _kural_dosya_yolu(sd)
        metin = _kural_dosya_metni(sd)
        try:
            with open(yol, encoding="utf-8", newline="") as f:
                var = f.read()
        except OSError:
            var = ""
        if var.replace("\r\n", "\n") == metin:
            return False
        _kural_dosyasini_yaz(sd)
        return True


def _kurallar_md_blogu_yaz(liste: list[dict]) -> None:
    """Eklenti KURALLAR.md'sindeki kayıtlı-kural bloğunu (işaretçiler arası) eklenti deposundan yeniden üretir.
    KURALLAR.md yoksa dokunmaz (test ve özel kurulum)."""
    yol = os.path.join(os.path.dirname(os.path.dirname(eklenti_kural_yolu())), "KURALLAR.md")
    if not os.path.isfile(yol):
        return
    with open(yol, encoding="utf-8", newline="") as f:
        ham = f.read()
    crlf = "\r\n" in ham
    t = ham.replace("\r\n", "\n")
    etkin = [r for r in liste if r.get("durum") == "etkin"]
    blok = ""
    if etkin:
        blok = [ESKI_BASLA, "## Kayıtlı eklenti kuralları", "",
                "Bu bölüm `orkestra kural` komutuyla yönetilir (`kurallar/eklenti_kurallari.json`); elle düzenleme.", ""]
        for r in etkin:
            tarih = (r.get("etkinlesme") or r.get("olusturma") or "")[:10]
            blok.append(f"- {_tek_satir(r['metin'])} ({r['id']}, {tarih})")
            if r.get("neden"):
                blok.append(f"  - Neden: {_tek_satir(r['neden'])}")
        blok.append(ESKI_BITIS)
        blok = "\n".join(blok)
    desen = re.compile(re.escape(ESKI_BASLA) + r".*?" + re.escape(ESKI_BITIS), re.S)
    if desen.search(t):
        t = desen.sub(lambda _: blok, t, count=1)
        if not blok:
            t = re.sub(r"\n{3,}", "\n\n", t)
    elif blok:
        t = t.rstrip("\n") + "\n\n" + blok + "\n"
    t = t.rstrip("\n") + "\n"
    if t == ham.replace("\r\n", "\n").rstrip("\n") + "\n":
        return
    L.atomik_yaz(yol, t.replace("\n", "\r\n") if crlf else t)


def _tek_satir(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _kural_bul(liste: list[dict], kid: str) -> dict:
    for r in liste:
        if r.get("id") == kid:
            return r
    raise ValueError(f"kural bulunamadı: {kid}")


def _kural_katmani(sd: str, kid: str) -> str:
    """Kimliğin bulunduğu katman; ikisinde de yoksa ValueError."""
    for katman in KATMANLAR:
        if any(r.get("id") == kid for r in _katman_oku(sd, katman)):
            return katman
    raise ValueError(f"kural bulunamadı: {kid}")


def _kural_sonraki_id(liste: list[dict], katman: str = "proje", diger: list[dict] | None = None) -> str:
    """Proje: K-(iki katmandaki en büyük K)+1. Eklenti: P-(eklentideki en büyük P)+1."""
    onek = "P" if katman == "plugin" else "K"
    en = 0
    for r in list(liste) + list(diger or []):
        m = re.fullmatch(onek + r"-(\d+)", r.get("id", ""))
        if m:
            en = max(en, int(m.group(1)))
    return f"{onek}-{en + 1:03d}"


def _kural_yeni(liste: list[dict], metin: str, neden: str | None, durum: str, kaynak: str,
                katman: str = "proje", diger: list[dict] | None = None) -> dict:
    metin = L.maskele(_tek_satir(metin))
    if not metin:
        raise ValueError("kural metni boş olamaz.")
    simdi = L.simdi()
    r = {"id": _kural_sonraki_id(liste, katman, diger), "katman": katman, "metin": metin,
         "neden": L.maskele(_tek_satir(neden)) if neden else "",
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


_YAYIN = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?Yay[ıi]n(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.*)$", re.IGNORECASE)
_YAYIN_ETIKET = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?(Eklenti metni|Neden)(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.*)$", re.IGNORECASE)
_KAPSAMLAR = ("proje", "evrensel")
_HEDEFLER = ("kural", "skill", "yok")


def yayin_ayristir(govde: str) -> tuple[dict, bool]:
    """Madde gövdesindeki `Yayın: kapsam=<proje|evrensel>; hedef=<kural|skill|yok>` satırını ve altındaki
    `Eklenti metni:` / `Neden:` satırlarını ayrıştırır. (yayin, bicimli) döner; satır yoksa ya da bozuksa
    kapsam=proje, hedef=yok, bicimli=False."""
    varsayilan = {"kapsam": "proje", "hedef": "yok", "metin": "", "neden": ""}
    satirlar = (govde or "").splitlines()
    for i, s in enumerate(satirlar):
        m = _YAYIN.match(s)
        if not m:
            continue
        alanlar = {}
        for parca in re.split(r"[;,]", m.group(1).replace("**", "")):
            if "=" in parca:
                a, _, d = parca.partition("=")
                alanlar[a.strip().lower()] = d.strip().strip("`").lower()
        if alanlar.get("kapsam") not in _KAPSAMLAR or alanlar.get("hedef") not in _HEDEFLER:
            return varsayilan, False
        yayin = {"kapsam": alanlar["kapsam"], "hedef": alanlar["hedef"], "metin": "", "neden": ""}
        cur = None
        for s2 in satirlar[i + 1:]:
            e = _YAYIN_ETIKET.match(s2)
            if e:
                cur = "metin" if e.group(1).lower().startswith("eklenti") else "neden"
                yayin[cur] = e.group(2).strip()
            elif cur and s2.strip():
                yayin[cur] = (yayin[cur] + " " + s2.strip()).strip()
            else:
                cur = None
        return yayin, True
    return varsayilan, False


# ---------------------------------------------------------------- terfi kapısı

_TERFI_JIRA_IZINLI = ("UTF", "SHA", "ISO", "RFC", "MD", "HTTP", "ADR")  # ADR-0033 gibi karar kayıtları Jira kodu değildir
_TERFI_KALIPLAR = [
    ("sır", re.compile(r"(?i)\b(?:api[_ -]?key|apikey|token|secret|password|passwd|şifre|sifre)\b\s*[:=]\s*\S+"), True),
    ("sır", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|pk-lf-[A-Za-z0-9-]{8,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
                       r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,})"), True),
    ("kart kimliği", re.compile(r"\bG-\d{2,}\b"), False),
    ("Windows yolu", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'`]*"), False),
    ("e-posta", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), False),
]
_TERFI_JIRA = re.compile(r"\b([A-Z][A-Z0-9]+)-(\d+)\b")


def _terfi_yasak_terimleri(sd: str) -> list[str]:
    yol = os.path.join(sd, "terfi_yasak.json")
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        return []
    if isinstance(v, dict):
        v = v.get("terimler", [])
    return [t.strip() for t in v if isinstance(t, str) and t.strip()] if isinstance(v, list) else []


def terfi_denetle(metin: str, neden: str, sd: str) -> list[str]:
    """Eklenti katmanına (her projede geçerli) gidecek kural metni ve nedenini denetler; isabet satırları döner
    (boş liste = temiz). Sır değeri isabet satırına yazılmaz."""
    isabet = []
    terimler = _terfi_yasak_terimleri(sd)
    for alan, s in (("metin", metin or ""), ("neden", neden or "")):
        for ad, kalip, gizli in _TERFI_KALIPLAR:
            for m in kalip.finditer(s):
                isabet.append(f"{alan}: {ad}: " + ("<gizli>" if gizli else m.group(0)[:60]))
        for m in _TERFI_JIRA.finditer(s):
            if m.group(1) not in _TERFI_JIRA_IZINLI:
                isabet.append(f"{alan}: Jira kodu: {m.group(0)}")
        alt = s.lower()
        for t in terimler:
            if t.lower() in alt:
                isabet.append(f"{alan}: yasak terim: {t}")
    return isabet


def _terfi_kapisi(sd: str, metin: str, neden: str) -> None:
    isabet = terfi_denetle(metin, neden, sd)
    if isabet:
        raise ValueError("eklenti katmanına terfi kapısı reddetti (kural yazılmadı): " + "; ".join(isabet))


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
        yayin, bicimli = yayin_ayristir(govde)
        _yeni_kayit(sd, "perspektif", baslik, govde, yol, anahtar, [], None, ek={"yayin": yayin})
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


_ESITLE_IZI: dict[str, tuple] = {}   # sd -> son tam geçişteki girdi parmak izi (süreç içi; panel her okumada çağırır)


def _esitle_izi(sd: str) -> tuple:
    """esitle girdilerinin mtime parmak izi: rapor dizinleri ve içindeki dosyalar, onerilen_skill altındaki her skill
    klasörü, projenin skills klasörü, kural dosyası ve onay kayıtları dizini. Aynıysa esitle'nin yapacağı yeni iş yoktur."""
    def mt(yol):
        try:
            return os.stat(yol).st_mtime_ns
        except OSError:
            return None

    izi = [mt(_onay_dizini(sd)), mt(_kurallar_yolu(sd)), mt(os.path.join(_proje(sd), ".claude", "skills"))]
    for alt in ("perspektif", "ruya", "onerilen_skill"):
        d = os.path.join(sd, alt)
        izi.append(mt(d))
        try:
            with os.scandir(d) as it:
                izi.extend(sorted((e.name, e.stat().st_mtime_ns) for e in it))
        except OSError:
            pass
    return tuple(izi)


def esitle(sd: str) -> None:
    """Kaynaklardan bekleyen kayıt üretir; idempotent (anahtar varsa yeni kayıt açmaz). Girdiler son geçişten beri
    değişmediyse kilit almadan döner (I-157: panel her okumada çağırır, onay kilidini gereksiz tutuyordu)."""
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    anahtar = os.path.abspath(sd)
    once = _esitle_izi(sd)
    if _ESITLE_IZI.get(anahtar) == once:
        return
    with L.kilit(_kilit_yolu(sd)):
        _esitle_perspektif(sd)
        _esitle_skill(sd)
        _esitle_kural(sd)
        # geçiş girdileri değiştirmediyse (kayıt yazmadı, başkası da dokunmadı) parmak izi saklanır; yazdıysa bir sonraki
        # çağrı bir kez daha geçer ve kararlı izi saklar
        sonra = _esitle_izi(sd)
        if sonra == once:
            _ESITLE_IZI[anahtar] = once


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
    """`uygulanacak`: onaylandi + uygulaniyor (Onaylar sekmesi). `panelden_uygulanabilir`: "Şimdi uygula" düğmesinin
    gerçekten başlatabileceği kayıtlar; panel kartı bunu sayar, böylece kart ve düğme aynı kümeyi kullanır."""
    try:
        eski_alimlari_birak(sd)
    except Exception:  # noqa: BLE001 - sayaç okuması hiçbir koşulda düşmez
        pass
    s = {"bekliyor": 0, "uygulanacak": 0, "panelden_uygulanabilir": len(_uygulanacaklar(sd, "perspektif")),
         "tur": {t: 0 for t in TURLER}}
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
                    import etki  # geç içe aktarım: etki.py onay.py'yi içe aktarır
                    _etki_kancasi(k, lambda: etki.kanca_al(sd, k))  # E1: panelden onaylanan kural da taban + uygulama tarihi alır
                    _etki_kancasi(k, lambda: etki.kanca_uygulandi(k))
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
        import etki  # geç içe aktarım: etki.py onay.py'yi içe aktarır
        _etki_kancasi(k, lambda: etki.kanca_al(sd, k))
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
        import etki  # geç içe aktarım: etki.py onay.py'yi içe aktarır
        _etki_kancasi(k, lambda: etki.kanca_uygulandi(k))
        _kayit_yaz(sd, k)
        return k


def birak(sd: str, id: str, neden: str) -> dict:
    """`uygulaniyor` kaydını `onaylandi`ya geri bırakır (uygulanamadı, oturum öldü). Etki tabanı donuk kalır (_taban_ic)."""
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        k = _gerekli(sd, id)
        if k["durum"] != "uygulaniyor":
            raise ValueError(f"{id} uygulaniyor durumunda değil (şu an: {k['durum']}); bırakılamaz.")
        k["durum"] = "onaylandi"
        k["uygulama"] = None
        _olay(k, "birakildi", neden)
        _kayit_yaz(sd, k)
        return k


def eski_alimlari_birak(sd: str) -> list[str]:
    """Etkin başsız koşu yokken KOSU_ZAMAN_ASIMI_SN'den eski `uygulaniyor` alımlarını bırakır; bırakılan kimlikler döner."""
    if uygulama_durumu(sd):
        return []
    simdi = datetime.datetime.now().astimezone()
    birakilan = []
    for k in _hepsi(sd):
        if k.get("durum") != "uygulaniyor":
            continue
        try:
            gecen = (simdi - datetime.datetime.fromisoformat((k.get("uygulama") or {})["alma_zamani"])).total_seconds()
        except Exception:  # noqa: BLE001 - alma zamanı okunamayan alım eski sayılmaz
            continue
        if gecen >= KOSU_ZAMAN_ASIMI_SN:
            try:
                birak(sd, k["id"], f"otomatik: {int(gecen // 60)} dk önce alındı, kapanmadı")
                birakilan.append(k["id"])
            except ValueError:
                pass
    return birakilan


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


def _bu_oturumun(k: dict, oturum: str) -> bool:
    return k.get("tur") != "karar" or not k.get("oturum") or k.get("oturum") == oturum


def _calistir_yonergesi(sd: str, oturum: str) -> str:
    """Bekleyen karar kalmadıysa ve onaylı kayıt varsa ajana /orkestra:onay'ı çalıştırma talimatı; yoksa ''."""
    kayitlar = [k for k in _hepsi(sd) if _bu_oturumun(k, oturum)]
    if any(k.get("durum") == "bekliyor" for k in kayitlar):
        return ""
    onayli = [k for k in kayitlar if k.get("durum") == "onaylandi"]
    if not onayli:
        return ""
    return (f"Panelde bekleyen karar kalmadı; onaylı {len(onayli)} karar uygulanmamış "
            f"({', '.join(k['id'] for k in onayli)}). Kullanıcıya sormadan Skill aracıyla "
            f"orkestra:onay'ı şimdi çalıştır.")


def baglam_metni(sd: str, oturum: str, olay: str) -> str:
    """Hook'un ajana eklediği kısa metin (en çok 900 karakter); söyleyecek şey yoksa ''."""
    if not os.path.isdir(_onay_dizini(sd)):
        return ""
    if olay == "SessionStart":
        kayitlar = _hepsi(sd)
        uygulanacak = [k for k in kayitlar if k.get("durum") == "onaylandi" and _bu_oturumun(k, oturum)]
        bekleyen = sum(1 for k in kayitlar if k.get("durum") == "bekliyor")
        parcalar = []
        yonerge = _calistir_yonergesi(sd, oturum)
        if yonerge:
            parcalar.append(yonerge)
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
            yonerge = _calistir_yonergesi(sd, oturum)
            if not yeni:
                return yonerge
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
            if yonerge:
                metin += " " + yonerge
            elif any(k["durum"] == "onaylandi" and k["tur"] != "karar" for _, k in yeni):
                metin += " → /orkestra:onay ile uygula."
            return _kisalt_metin(metin)
    return ""


def _kisalt_metin(s: str) -> str:
    return s if len(s) <= BAGLAM_MAX else s[: BAGLAM_MAX - 1] + "…"


# ---------------------------------------------------------------- kurallar (genel)

def kurallar(sd: str, katman: str | None = None) -> list:
    """İki katmanın tüm kayıtları (eklenti, proje sırasıyla); her kayıtta `katman`, eklenti kayıtlarında ayrıca `devre_disi`
    (bu projede kapatılmış mı). `katman` verilirse yalnız o katman."""
    k = _katman_adi(katman) if katman else None
    kapali = _devre_disi(sd)
    out = []
    if k in (None, "plugin"):
        out += [dict(r, devre_disi=r.get("id") in kapali) for r in _eklenti_oku()]
    if k in (None, "proje"):
        out += _kurallar_oku(sd)
    return out


def _kural_islemi(sd: str, islem, katman: str = "proje"):
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        liste_ = _katman_oku(sd, katman)
        sonuc = islem(liste_)
        _katman_yaz(sd, katman, liste_)
        return sonuc


def _kural_id_islemi(sd: str, id: str, islem):
    """Kimliğin katmanını bulur, işlemi o katmanda koşar (kilit altında)."""
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        katman = _kural_katmani(sd, id)
        liste_ = _katman_oku(sd, katman)
        sonuc = islem(liste_)
        _katman_yaz(sd, katman, liste_)
        return sonuc


def _kontrol_dogrula(kontrol) -> str:
    """Kontrol kimliği kayıtlı değilse ValueError (geçerli kimlikleri sayar)."""
    import kanit_kapisi
    gecerli = kanit_kapisi.kontrol_kimlikleri()
    if kontrol not in gecerli:
        raise ValueError(f"bilinmeyen kontrol kimliği: {kontrol}. Geçerli kimlikler: {', '.join(gecerli) or '(yok)'}")
    return kontrol


def kural_oner(sd: str, metin: str, neden: str, kaynak: str, kontrol: str | None = None) -> dict:
    """Öneri kuralı açar ve panelde onaylanması için tur='kural' onay kaydı ekler. Öneri hep proje katmanındadır
    (onay kaydı projede tutulur); eklentiye taşımak için onaylandıktan sonra `kural_tasi`."""
    if kontrol:
        _kontrol_dogrula(kontrol)

    def is_(liste_):
        r = _kural_yeni(liste_, metin, neden, "oneri", kaynak, "proje", _eklenti_oku())
        if kontrol:
            r["kontrol"] = kontrol
        _kural_onayi_ac(sd, r)
        return r
    return _kural_islemi(sd, is_)


def kural_ekle(sd: str, metin: str, neden: str, kaynak: str = "panel", kontrol: str | None = None,
               katman: str = "proje") -> dict:
    """Doğrudan etkin kural (kullanıcı yazar). `katman`: 'proje' (varsayılan) ya da 'plugin'."""
    katman = _katman_adi(katman)
    if kontrol:
        _kontrol_dogrula(kontrol)
    if katman == "plugin":
        _terfi_kapisi(sd, metin, neden)

    def is_(liste_):
        r = _kural_yeni(liste_, metin, neden, "etkin", kaynak, katman,
                        _kurallar_oku(sd) if katman == "plugin" else _eklenti_oku())
        if kontrol:
            r["kontrol"] = kontrol
        return r
    return _kural_islemi(sd, is_, katman)


def kural_bagla(sd: str, id: str, kontrol: str | None = None, kaldir: bool = False) -> dict:
    """Öneri ya da etkin kurala kayıtlı ön kontrol bağı yazar ya da kaldırır (etkinlik kurallardan türer)."""
    if not kaldir:
        if not kontrol:
            raise ValueError("kontrol kimliği ya da --kaldir gerekli.")
        _kontrol_dogrula(kontrol)

    def is_(liste_):
        r = _kural_bul(liste_, id)
        if r["durum"] not in ("oneri", "etkin"):
            raise ValueError(f"{id} için kontrol bağı değiştirilemez (durum: {r['durum']}).")
        simdi = L.simdi()
        if kaldir:
            r.pop("kontrol", None)
            r.setdefault("gecmis", []).append({"zaman": simdi, "olay": "kontrol-kaldirildi"})
        else:
            r["kontrol"] = kontrol
            r.setdefault("gecmis", []).append({"zaman": simdi, "olay": "kontrol-baglandi", "kontrol": kontrol})
        r["guncelleme"] = simdi
        return r
    return _kural_id_islemi(sd, id, is_)


def kural_duzenle(sd: str, id: str, metin: str, neden: str | None = None) -> dict:
    def is_(liste_):
        r = _kural_bul(liste_, id)
        if r["durum"] not in ("oneri", "etkin"):
            raise ValueError(f"{id} düzenlenemez (durum: {r['durum']}).")
        yeni = L.maskele(_tek_satir(metin))
        if not yeni:
            raise ValueError("kural metni boş olamaz.")
        yeni_neden = L.maskele(_tek_satir(neden)) if neden is not None else None
        # Eklenti katmanı her projede geçerlidir: metin ya da neden değişiyorsa terfi kapısından geçer (yazmadan önce).
        if (r.get("katman") == "plugin" or _kural_katmani(sd, id) == "plugin") and (
                yeni != r.get("metin") or (yeni_neden is not None and yeni_neden != r.get("neden"))):
            # ham metin denetlenir (maskeleme e-posta gibi kalıpları kapı görmeden siler; kural_ekle de ham metni denetler)
            _terfi_kapisi(sd, metin, neden if neden is not None else (r.get("neden") or ""))
        r.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": "duzenlendi", "metin": r["metin"]})
        r["metin"] = yeni
        if yeni_neden is not None:
            r["neden"] = yeni_neden
        r["guncelleme"] = L.simdi()
        return r
    return _kural_id_islemi(sd, id, is_)


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
    return _kural_id_islemi(sd, id, is_)


def kural_tasi(sd: str, id: str, katman: str, kimligi_koru: bool = False) -> dict:
    """Etkin bir kuralı öbür katmana taşır. Kimlik varsayılan olarak hedef katmanın sıradaki kimliği olur (eski kimlik
    `eski_id` alanında kalır); `kimligi_koru` mevcut kimliği korur (belge ve kodun atıf yaptığı kimlikler için) ve hedefte
    o kimlik varsa reddedilir."""
    hedef_k = _katman_adi(katman)
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        kaynak_k = _kural_katmani(sd, id)
        if kaynak_k == hedef_k:
            raise ValueError(f"{id} zaten {hedef_k} katmanında.")
        kaynak = _katman_oku(sd, kaynak_k)
        hedef = _katman_oku(sd, hedef_k)
        r = _kural_bul(kaynak, id)
        if r["durum"] != "etkin":
            raise ValueError(f"{id} taşınamaz (durum: {r['durum']}); yalnız etkin kural taşınır.")
        if hedef_k == "plugin":
            _terfi_kapisi(sd, r.get("metin", ""), r.get("neden", ""))
        yeni_id = id if kimligi_koru else _kural_sonraki_id(hedef, hedef_k, kaynak)
        if any(x.get("id") == yeni_id for x in hedef):
            raise ValueError(f"{yeni_id} hedef katmanda zaten var; kimlik korunamaz.")
        simdi = L.simdi()
        kaynak.remove(r)
        r["katman"] = hedef_k
        if yeni_id != id:
            r["eski_id"] = id
            r["id"] = yeni_id
        r["guncelleme"] = simdi
        r.setdefault("gecmis", []).append({"zaman": simdi, "olay": "tasindi", "not": f"{kaynak_k} → {hedef_k}"
                                           + (f" ({id} → {yeni_id})" if yeni_id != id else "")})
        hedef.append(r)
        _katman_yaz(sd, hedef_k, hedef)  # önce hedef: yarıda kalırsa kural kaybolmaz, çift kalır
        _katman_yaz(sd, kaynak_k, kaynak)
        return r


def kural_kapat(sd: str, id: str, not_: str = "") -> dict:
    """Eklenti kuralını yalnız BU projede kapatır (eklenti deposuna dokunmaz)."""
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        if _kural_katmani(sd, id) != "plugin":
            raise ValueError(f"{id} proje kuralı; kapatmak yerine `kural kaldir` kullan. Yalnız eklenti kuralları kapatılır.")
        r = _kural_bul(_eklenti_oku(), id)
        if r["durum"] != "etkin":
            raise ValueError(f"{id} etkin değil (durum: {r['durum']}).")
        depo = _depo_oku(sd)
        kapali = depo.get("devre_disi") if isinstance(depo.get("devre_disi"), dict) else {}
        kapali[id] = {"not": L.maskele(_tek_satir(not_)), "zaman": L.simdi()}
        depo["devre_disi"] = kapali
        _yaz_json(_kurallar_yolu(sd), depo)
        _kural_dosyasini_yaz(sd)
        return dict(r, devre_disi=True)


def kural_ac(sd: str, id: str) -> dict:
    """Bu projede kapatılmış eklenti kuralını yeniden açar."""
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    with L.kilit(_kilit_yolu(sd)):
        depo = _depo_oku(sd)
        kapali = depo.get("devre_disi") if isinstance(depo.get("devre_disi"), dict) else {}
        if id not in kapali:
            raise ValueError(f"{id} bu projede kapalı değil.")
        del kapali[id]
        if kapali:
            depo["devre_disi"] = kapali
        else:
            depo.pop("devre_disi", None)
        _yaz_json(_kurallar_yolu(sd), depo)
        _kural_dosyasini_yaz(sd)
        return dict(_kural_bul(_eklenti_oku(), id), devre_disi=False)


def kural_gorunum(sd: str, proje: str) -> dict:
    proje_liste = _kurallar_oku(sd)
    eklenti = [dict(r, devre_disi=r.get("id") in _devre_disi(sd)) for r in _eklenti_oku()]
    oneriler = []
    for r in proje_liste:
        if r.get("durum") == "oneri":
            k = _anahtarli(sd, f"kural:{r['id']}")
            oneriler.append(dict(r, onay_id=k["id"] if k else None))
    return {"etkin": [r for r in eklenti if r.get("durum") == "etkin"]
            + [r for r in proje_liste if r.get("durum") == "etkin"],
            "oneriler": oneriler,
            "gecmis": [r for r in eklenti + proje_liste if r.get("durum") in ("reddedildi", "kaldirildi")],
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


# ---------------------------------------------------------------- şimdi uygula (panel düğmesi)

KOSU_ZAMAN_ASIMI_SN = 3600

KOSU_ISTEMI = """#SUREC:perspektif-uygula
Kullanıcı panelde "Şimdi uygula"ya bastı; kullanıcı yok, soru sorma. {skill} dosyasındaki adımları YALNIZ
tür=perspektif, durum=onaylandi kayıtlar için, şu sırayla ve her seferinde tek kayıt olarak uygula: {idler}.
Başka türe (skill, karar, kural) dokunma; yalnız hafıza klasöründe dosya değiştir. Hafıza klasörü: {hafiza}
Bir kayıt hata verirse nedenini yaz, onu atla ve sıradakine geç.
Hepsi bitince perspektif kayıtları kapandıysa `orkestra perspektif bitti` çalıştır. Yanıtın en çok 5 satırlık özet olsun."""


def _kosu_yolu(sd: str) -> str:
    return os.path.join(_onay_dizini(sd), "uygulama_kosu.json")


def uygulama_durumu(sd: str) -> dict | None:
    """Sürmekte olan 'şimdi uygula' koşusu ({baslangic, idler, tur}); yoksa ya da zaman aşımına uğradıysa None."""
    d = _oku_json(_kosu_yolu(sd), None)
    if not isinstance(d, dict) or d.get("bitis"):
        return None
    try:
        gecen = (datetime.datetime.now().astimezone() - datetime.datetime.fromisoformat(d["baslangic"])).total_seconds()
    except Exception:
        return None
    return d if gecen < KOSU_ZAMAN_ASIMI_SN else None


def _uygulanacaklar(sd: str, tur: str) -> list[str]:
    return sorted(k["id"] for k in _hepsi(sd) if k.get("durum") == "onaylandi" and k.get("tur") == tur)


def simdi_uygula(sd: str, tur: str = "perspektif") -> dict:
    """Onaylı `tur` kayıtlarını başsız bir Claude koşusunda sırayla uygulatır (arka planda). Hata: ValueError(Türkçe)."""
    import subprocess
    import perspektif as P
    if tur != "perspektif":
        raise ValueError("şimdilik yalnız perspektif kararları uygulanır.")
    os.makedirs(_onay_dizini(sd), exist_ok=True)
    idler = _uygulanacaklar(sd, tur)
    if not idler:
        raise ValueError("Uygulanacak onaylı perspektif kararı yok.")
    if uygulama_durumu(sd):
        raise ValueError("Uygulama zaten sürüyor.")
    exe = P.claude_exe()
    if not exe:
        raise ValueError("claude.exe bulunamadı (CLAUDE_CODE_EXECPATH ya da keşif); arka planda uygulanamaz. "
                         "Sohbette /orkestra:onay ile uygula.")
    if not P.headless_mumkun(sd, exe):
        raise ValueError("Komut satırı Claude oturum açmamış; arka planda uygulanamaz. Bir kez `claude auth login` çalıştır "
                         "ya da sohbette /orkestra:onay ile uygula.")
    proje = _proje(sd)
    hafiza = P.hafiza_dizini(proje)
    if not (os.path.isdir(hafiza) and any(os.path.isfile(os.path.join(hafiza, ad)) for ad in os.listdir(hafiza))):
        # I-215: boş klasörde başsız oturum uygulayacak dosya bulamaz, kayıtları takılı bırakır; oturum açmadan reddet
        raise ValueError(f"Hedef hafıza klasörü yok ya da boş ({hafiza}); karar bu projenin hafızasına ait değil ya da "
                         "perspektif başka projede çalıştırılmış. Kayıtlar olduğu gibi duruyor.")
    with L.kilit(_kilit_yolu(sd)):
        if uygulama_durumu(sd):
            raise ValueError("Uygulama zaten sürüyor.")
        _yaz_json(_kosu_yolu(sd), {"baslangic": L.simdi(), "idler": idler, "tur": tur, "bitis": None, "sonuc": None})
    args = [sys.executable, os.path.abspath(__file__), "_kos", sd, proje, exe, hafiza]
    import cfg
    try:
        subprocess.Popen(args, cwd=proje, creationflags=cfg.ARKA_PLAN_BAYRAK, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
    except OSError as e:
        _kosu_bitir(sd, f"başlatılamadı: {type(e).__name__}")
        raise ValueError(f"Koşu başlatılamadı: {type(e).__name__}")
    return {"idler": idler}


def _kosu_bitir(sd: str, sonuc: str) -> None:
    with L.kilit(_kilit_yolu(sd)):
        d = _oku_json(_kosu_yolu(sd), None)
        if isinstance(d, dict):
            d.update(bitis=L.simdi(), sonuc=sonuc)
            _yaz_json(_kosu_yolu(sd), d)


def _kos(sd: str, proje: str, exe: str, hafiza: str) -> None:
    import subprocess
    import cfg
    d = _oku_json(_kosu_yolu(sd), None) or {}
    idler = d.get("idler") or _uygulanacaklar(sd, "perspektif")
    skill = os.path.join(L.PLUGIN_ROOT, "skills", "onay", "SKILL.md")
    istem = KOSU_ISTEMI.format(skill=skill, idler=", ".join(idler), hafiza=hafiza)
    ortam = dict(os.environ, ORKESTRA_PERSPEKTIF="1", PYTHONUTF8="1")
    komut = [exe, "-p", istem, "--model", "sonnet", "--effort", "medium", "--max-turns", "80",
             "--allowedTools", "Read", "Glob", "Grep", "Write", "Edit", "Agent", "Bash(orkestra *)",
             "--add-dir", hafiza, "--add-dir", sd, "--output-format", "text"]
    sonuc = "tamam"
    try:
        r = subprocess.run(komut, cwd=proje, env=ortam, capture_output=True, text=True, encoding="utf-8", timeout=KOSU_ZAMAN_ASIMI_SN, **cfg.PENCERESIZ)
        if r.returncode != 0 or "Not logged in" in (r.stdout or ""):
            sonuc = f"hata: çıkış kodu {r.returncode}"
    except Exception as e:  # noqa: BLE001
        sonuc = f"hata: {type(e).__name__}"
    sonuc = _kosu_sonucu_dogrula(sd, idler, sonuc)
    _kosu_bitir(sd, sonuc)


def _kosu_sonucu_dogrula(sd: str, idler: list[str], sonuc: str) -> str:
    """Başarı çıkış koduna değil kayıtların durumuna bağlıdır (I-215): koşunun kapatmadığı `uygulaniyor` kayıtlar
    `onaylandi`ya bırakılır ve sonuç 'kayıtlar kapanmadı: N' olur. `tamam` yalnız hepsi kapandıysa yazılır."""
    kapanmayan = 0
    for i in idler:
        k = goster(sd, i)
        if not k or k.get("durum") not in ("onaylandi", "uygulaniyor"):
            continue
        kapanmayan += 1
        if k["durum"] == "uygulaniyor":
            try:
                birak(sd, i, f"başsız koşu kapatmadan bitti ({sonuc})")
            except ValueError:
                pass
    if kapanmayan:
        return f"kayıtlar kapanmadı: {kapanmayan}" + ("" if sonuc == "tamam" else f" ({sonuc})")
    return sonuc


if __name__ == "__main__" and len(sys.argv) >= 6 and sys.argv[1] == "_kos":
    _kos(*sys.argv[2:6])
