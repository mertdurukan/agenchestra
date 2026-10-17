"""İş sırası (P-005): mevcut_durum_<gün>.md → plan.md → todo.md. Her adım bir öncekinden beslenir.

Saf Python, yalnız okur; model çağrılmaz. Bir iş `is ac` ile açılırken is.json'a `sira` bayrağı konur;
bayraksız (eski) işler ve `ORKESTRA_SIRA_KAPISI=0` kapıyı atlar.

Ön koşul, önceki adımın TAMAM olmasıdır; tamam tanımı deterministiktir:
- mevcut durum: dosya var, 5 bölümün her birinde yer tutucu dışında içerik var, `**Ölçüm saati:**` dolu,
  §3'te (etki haritası) en az bir madde.
- plan: dosya var, ilk satırlarda mevcut durum dosyasına bağlantı var, en az bir `P<n>` maddesi var,
  her maddede geçerli `MD §<k>` dayanağı var.
- todo satırı: `P<n>` ile başlar ve `P<n>` planda var.
"""
from __future__ import annotations

import json
import os
import re

SIRA_ADI = "mevcut-durum-plan-todo"
BOLUM_SAYISI = 5
ETKI_BOLUMU = 3
BAGLANTI_PENCERE = 20  # plan.md'nin bu kadar ilk satırında mevcut duruma bağlantı aranır

_MD_AD = re.compile(r"^mevcut_durum_\d{8}\.md$")
_YORUM = re.compile(r"<!--.*?-->", re.S)
_BOLUM_BASLIK = re.compile(r"^##\s+(\d+)\.\s.*$", re.M)
_MADDE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+\S", re.M)
_OLCUM = re.compile(r"\*\*Ölçüm saati:\*\*[ \t]*(.*)$", re.M)
_P_SATIRI = re.compile(r"^(?:#{2,4}\s+|[-*]\s+(?:\*\*)?)P(\d+)\b", re.M)
_DAYANAK = re.compile(r"MD\s*§\s*(\d+)")
_TODO_SATIR = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*(.*)$")
_TODO_P = re.compile(r"^P(\d+)\b")


def kapi_acik() -> bool:
    return os.environ.get("ORKESTRA_SIRA_KAPISI") != "0"


def sirali_mi(klasor: str) -> bool:
    """Klasördeki is.json `sira` bayrağı taşıyor ve kapı açık mı."""
    if not kapi_acik():
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            veri = json.load(f)
        return isinstance(veri, dict) and veri.get("sira") == SIRA_ADI
    except (OSError, ValueError):
        return False


def mevcut_durum_yolu(klasor: str) -> str | None:
    """En yeni `mevcut_durum_<YYYYMMDD>.md` (ad sıralaması = tarih sıralaması); yoksa None."""
    try:
        adlar = sorted(a for a in os.listdir(klasor) if _MD_AD.match(a))
    except OSError:
        return None
    return os.path.join(klasor, adlar[-1]) if adlar else None


def _oku(yol: str) -> str | None:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _bolumler(metin: str) -> dict[int, str]:
    parcalar = _BOLUM_BASLIK.split(metin)
    return {int(parcalar[i]): parcalar[i + 1] for i in range(1, len(parcalar) - 1, 2)}


def _icerik(govde: str) -> str:
    return _YORUM.sub("", govde).strip()


def mevcut_durum_eksikleri(klasor: str) -> list[str]:
    """Boş liste = mevcut durum tamam."""
    yol = mevcut_durum_yolu(klasor)
    if yol is None:
        return ["mevcut_durum_<YYYYMMDD>.md yok (`orkestra is belge <id> mevcut_durum`)"]
    metin = _oku(yol) or ""
    eksik = []
    sade = _YORUM.sub("", metin)
    m = _OLCUM.search(sade)
    if not m:
        eksik.append("mevcut durum: `**Ölçüm saati:**` alanı yok")
    else:
        sonra = sade[m.end():].lstrip("\n")
        dolu = m.group(1).strip() or (sonra.split("\n\n", 1)[0].strip() if not sonra.startswith("**") else "")
        if not dolu or dolu.startswith("#"):
            eksik.append("mevcut durum: `**Ölçüm saati:**` boş")
    bolumler = _bolumler(metin)
    for n in range(1, BOLUM_SAYISI + 1):
        if n not in bolumler:
            eksik.append(f"mevcut durum: `## {n}.` bölümü yok")
        elif not _icerik(bolumler[n]):
            eksik.append(f"mevcut durum §{n} boş")
        elif n == ETKI_BOLUMU and not _MADDE.search(_icerik(bolumler[n])):
            eksik.append(f"mevcut durum §{n} (etki haritası) madde içermiyor")
    return eksik


def _p_bloklari(metin: str) -> dict[int, str]:
    """{P numarası: blok metni}; blok bir sonraki P satırına ya da `## ` başlığına kadar sürer."""
    satirlar = _YORUM.sub("", metin).splitlines()  # şablonun yer tutucu yorumundaki örnek P satırı sayılmaz
    bloklar: dict[int, list[str]] = {}
    gecerli = None
    # Başlık biçimli (`### P1`) madde varsa yalnız başlıklar madde başlatır; gövdedeki "- P1 testleri…" gibi madde işaretli
    # satırlar bir önceki maddeyi bölmez (I-057). Başlık yoksa eski madde işaretli biçim geçerlidir.
    baslik_var = any(re.match(r"^#{2,4}\s+P\d+", s) for s in satirlar)
    for s in satirlar:
        m = _P_SATIRI.match(s)
        if m and baslik_var and not s.lstrip().startswith("#"):
            m = None
        if m:
            gecerli = int(m.group(1))
            bloklar.setdefault(gecerli, []).append(s)
        elif re.match(r"^##\s", s):
            gecerli = None
        elif gecerli is not None:
            bloklar[gecerli].append(s)
    return {n: "\n".join(b) for n, b in bloklar.items()}


def plan_maddeleri(klasor: str) -> set[int]:
    metin = _oku(os.path.join(klasor, "plan.md"))
    return set(_p_bloklari(metin)) if metin else set()


def plan_eksikleri(klasor: str) -> list[str]:
    """Boş liste = plan tamam (mevcut durum ayrıca denetlenir)."""
    metin = _oku(os.path.join(klasor, "plan.md"))
    if metin is None:
        return ["plan.md yok (`orkestra is belge <id> plan`)"]
    eksik = []
    md = mevcut_durum_yolu(klasor)
    if md is not None:
        bas = "\n".join(metin.splitlines()[:BAGLANTI_PENCERE])
        if f"]({os.path.basename(md)})" not in bas:
            eksik.append(f"plan.md ilk {BAGLANTI_PENCERE} satırında `[{os.path.basename(md)}]({os.path.basename(md)})` bağlantısı yok")
    bloklar = _p_bloklari(metin)
    if not bloklar:
        eksik.append("plan.md'de `P<n>` maddesi yok (örn. `### P1 Başlık`)")
    for n, blok in sorted(bloklar.items()):
        dayanaklar = [int(k) for k in _DAYANAK.findall(blok)]
        if not dayanaklar:
            eksik.append(f"P{n}: `MD §<k>` dayanağı yok (mevcut durum bölümü)")
        elif not any(1 <= k <= BOLUM_SAYISI for k in dayanaklar):
            eksik.append(f"P{n}: dayanak MD §{dayanaklar[0]} geçersiz (§1-§{BOLUM_SAYISI})")
    return eksik


def adim(klasor: str) -> tuple[str, list[str]]:
    """(şu anki adım, o adımın eksikleri): 'mevcut_durum' | 'plan' | 'todo' (todo = ön koşullar tamam)."""
    e = mevcut_durum_eksikleri(klasor)
    if e:
        return "mevcut_durum", e
    e = plan_eksikleri(klasor)
    if e:
        return "plan", e
    return "todo", []


def plan_onkosulu(klasor: str) -> list[str]:
    """plan.md yazımı için ön koşul: mevcut durum tamam."""
    return mevcut_durum_eksikleri(klasor)


def todo_onkosulu(klasor: str) -> list[str]:
    """todo.md yazımı için ön koşul: mevcut durum ve plan tamam."""
    return mevcut_durum_eksikleri(klasor) or plan_eksikleri(klasor)


def todo_satir_ihlalleri(metin: str, planli: set[int]) -> list[str]:
    """Metindeki her onay kutusu satırı `P<n>` ile başlamalı ve P<n> planda olmalı."""
    ihlal = []
    for s in str(metin).splitlines():
        m = _TODO_SATIR.match(s)
        if not m or not m.group(1).strip():
            continue
        p = _TODO_P.match(m.group(1).strip())
        kisa = m.group(1).strip()[:60]
        if not p:
            ihlal.append(f"`{kisa}`: satır `P<n>:` ile başlamalı (plan maddesi)")
        elif int(p.group(1)) not in planli:
            ihlal.append(f"`{kisa}`: P{p.group(1)} plan.md'de yok; önce planı güncelle")
    return ihlal


def mesaj(neden: list[str], hedef: str) -> str:
    """Kullanıcıya/ajana tek paragraf: hangi dosya, neden yazılamıyor, ne yapılacak."""
    return (f"{hedef} yazılamaz: sıra mevcut durum → plan → todo (P-005). Eksik: " + "; ".join(neden[:6])
            + (f" (+{len(neden) - 6} eksik daha)" if len(neden) > 6 else "")
            + ". Önceki adımı tamamla, sonra yaz (kapatma: ORKESTRA_SIRA_KAPISI=0).")
