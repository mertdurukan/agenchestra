"""Sistem haritası `teknolojiler` katmanı (ADR-0017; model çağırmaz).

Projeleri manifest dosyalarından bulur (requirements*.txt, pyproject.toml, package.json, Dockerfile, Terraform, iş akışı),
her teknolojiyi `ayarlar/teknoloji_kategorileri.json` ile kategoriler ve `<durum>/sistem_haritasi/teknolojiler/` altına
kategorik README ile proje başına bir md yazar. Sır değeri okunmaz: yalnız paket adı ve sürüm yazımı alınır.
Çalışma ağaçları (`.git` dosyası olan dizin) ve manifestsiz klasörler proje sayılmaz.
"""
from __future__ import annotations

import json
import os
import re

KLASOR = "teknolojiler"
AYAR_YOLU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "teknoloji_kategorileri.json")
SURUM_KURALI = "Sürümler manifest dosyalarındaki yazımdır; kurulu ya da canlı sürüm doğrulanmadı."

REQ = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*((?:[=<>!~]=?|@)\s*[^\s;#]+)?")
PYPROJE_SATIR = re.compile(r"^([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*(.*)$")
FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.I)
KULLAN = re.compile(r"^\s*-?\s*uses:\s*([^\s@#]+)@([^\s#]+)")


def ayar_oku() -> dict:
    try:
        with open(AYAR_YOLU, encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, dict) else {}
    except (OSError, ValueError):
        return {}


def ayar_imzasi() -> str:
    """Eşleme dosyası değişince katman eskir (imzaya girer)."""
    try:
        st = os.stat(AYAR_YOLU)
        return f"teknoloji_kategorileri.json|{st.st_size}|{st.st_mtime_ns}"
    except OSError:
        return "teknoloji_kategorileri.json|yok"


def kategori(ad: str, varsayilan: str = "diger", ayar: dict | None = None) -> str:
    ayar = ayar if ayar is not None else ayar_oku()
    a = ad.lower().replace("_", "-")
    tam = (ayar.get("paketler") or {}).get(a)
    if tam:
        return tam
    onekler = [p for p in (ayar.get("onekler") or {}) if a.startswith(p)]
    if onekler:
        return ayar["onekler"][max(onekler, key=len)]
    return varsayilan


def _kategori_adlari(ayar):
    sira = [(k["kod"], k["ad"]) for k in ayar.get("kategoriler") or [] if isinstance(k, dict) and k.get("kod")]
    return sira or [("diger", "Diğer (eşlenmemiş)")]


def _ekle(t, ayar, proje, ad, surum, tur, yer, varsayilan="diger"):
    kat = kategori(ad, varsayilan, ayar)
    kid = f"teknoloji:{proje or '.'}:{ad.lower()}"
    adlar = dict(_kategori_adlari(ayar))
    t.ekle(kid, ad, yer, f"{adlar.get(kat, kat)}: {tur}" + (f" {surum}" if surum else ""))
    k = t.kayit[kid]
    if "kategori" not in k:
        k.update(proje=proje or ".", kategori=kat, surum=surum, tur=tur)
    elif surum and not k["surum"]:
        k["surum"] = surum


def _requirements(metin, rel, proje, t, ayar):
    for s in metin.splitlines():
        if s.lstrip().startswith(("#", "-", "git+", "http")):
            continue
        m = REQ.match(s)
        if m:
            _ekle(t, ayar, proje, m.group(1), (m.group(2) or "").replace(" ", ""), "Python paketi", rel)


def _pyproject(metin, rel, proje, t, ayar):
    m = re.search(r'requires-python\s*=\s*"([^"]+)"', metin)
    if m:
        _ekle(t, ayar, proje, "python", m.group(1).replace(" ", ""), "Çalışma zamanı", rel)
    listeler = []
    d = re.search(r"^dependencies\s*=\s*\[(.*?)\]\s*$", metin, re.S | re.M)
    if d:
        listeler.append((d.group(1), "Python paketi"))
    o = re.search(r"^\[project\.optional-dependencies\]\s*\n(.*?)(?=^\[|\Z)", metin, re.S | re.M)
    if o:
        for ad, govde in re.findall(r"^([A-Za-z0-9_\-]+)\s*=\s*\[(.*?)\]\s*$", o.group(1), re.S | re.M):
            listeler.append((govde, f"Python paketi ({ad})"))
    for govde, tur in listeler:
        for s in re.findall(r"""["']([^"']+)["']""", govde):
            m = PYPROJE_SATIR.match(s.split(";")[0].strip())
            if m:
                _ekle(t, ayar, proje, m.group(1), m.group(2).replace(" ", ""), tur, rel)


def _package_json(metin, rel, proje, t, ayar):
    try:
        veri = json.loads(metin)
    except ValueError:
        return
    if not isinstance(veri, dict):
        return
    node = (veri.get("engines") or {}).get("node")
    if node:
        _ekle(t, ayar, proje, "node", str(node).replace(" ", ""), "Çalışma zamanı", rel)
    for bolum, tur in (("dependencies", "npm paketi"), ("devDependencies", "npm paketi (dev)")):
        for paket, surum in (veri.get(bolum) or {}).items():
            _ekle(t, ayar, proje, paket, str(surum), tur, rel)


def _dockerfile(metin, rel, proje, t, ayar):
    asamalar = set()
    for satir in metin.splitlines():
        m = FROM.match(satir)
        if not m:
            continue
        imaj = m.group(1)
        if m.group(2):
            asamalar.add(m.group(2).lower())
        if imaj.lower() in asamalar or imaj.lower() == "scratch" or imaj.startswith("$"):
            continue
        ad, _, etiket = imaj.split("@")[0].split("/")[-1].partition(":")
        if ad and not ad.startswith("$"):
            _ekle(t, ayar, proje, ad, etiket if not etiket.startswith("$") else "", "Docker taban imajı", rel, "altyapi")


def _terraform(metin, rel, proje, t, ayar):
    m = re.search(r'required_version\s*=\s*"([^"]+)"', metin)
    if m:
        _ekle(t, ayar, proje, "terraform", m.group(1).replace(" ", ""), "Terraform", rel, "altyapi")
    for govde in re.findall(r"\w+\s*=\s*\{([^{}]*source\s*=[^{}]*)\}", metin):
        kaynak = re.search(r'source\s*=\s*"([^"]+)"', govde)
        surum = re.search(r'version\s*=\s*"([^"]+)"', govde)
        if kaynak:
            _ekle(t, ayar, proje, kaynak.group(1).split("/")[-1], (surum.group(1) if surum else "").replace(" ", ""),
                  "Terraform sağlayıcısı", rel, "altyapi")
    for ad in re.findall(r'^\s*provider\s+"([^"]+)"', metin, re.M):
        _ekle(t, ayar, proje, ad, "", "Terraform sağlayıcısı", rel, "altyapi")
    for govde in re.findall(r'resource\s+"helm_release"\s+"[^"]+"\s*\{(.*?)^\}', metin, re.S | re.M):
        chart = re.search(r'chart\s*=\s*"([^"]+)"', govde)
        surum = re.search(r'^\s*version\s*=\s*"([^"]+)"', govde, re.M)
        if chart:
            _ekle(t, ayar, proje, chart.group(1), surum.group(1) if surum else "", "Helm chart", rel, "altyapi")


def _is_akisi(metin, rel, proje, t, ayar):
    for satir in metin.splitlines():
        m = KULLAN.match(satir)
        if m and not m.group(1).startswith(("./", "docker://")):
            _ekle(t, ayar, proje, m.group(1), m.group(2), "GitHub Actions eylemi", rel, "altyapi")


def _okuyucu(rel):
    ad = os.path.basename(rel).lower()
    if ad.startswith("requirements") and ad.endswith(".txt"):
        return _requirements
    if ad == "pyproject.toml":
        return _pyproject
    if ad == "package.json":
        return _package_json
    if ad.startswith("dockerfile"):
        return _dockerfile
    if ad.endswith(".tf"):
        return _terraform
    if ".github/workflows/" in rel and ad.endswith((".yml", ".yaml")):
        return _is_akisi
    return None


def _manifest_mi(rel):
    ad = os.path.basename(rel).lower()
    return (ad.startswith("requirements") and ad.endswith(".txt")) or ad in ("pyproject.toml", "package.json")


def _altinda(rel, dizin):
    return rel == dizin or rel.startswith(dizin + "/")


def projeler(dosyalar):
    """(proje eşlemesi {rel: proje}, çalışma ağaçları [dizin]). Proje: en yakın manifest dizini; yoksa dosyanın dizini."""
    agaclar = sorted({os.path.dirname(r) for r in dosyalar if os.path.basename(r) == ".git" and os.path.dirname(r)})
    kullanilan = [r for r in dosyalar if os.path.basename(r) != ".git" and not any(_altinda(r, a) for a in agaclar)]
    manifest_dizin = {os.path.dirname(r) for r in kullanilan if _manifest_mi(r)}
    esleme = {}
    for rel in kullanilan:
        d, proje = os.path.dirname(rel), None
        while True:
            if d in manifest_dizin:
                proje = d
                break
            if not d:
                break
            d = os.path.dirname(d)
        if proje is None:
            proje = rel[:rel.index(".github/workflows/")].rstrip("/") if ".github/workflows/" in rel else os.path.dirname(rel)
        esleme[rel] = proje
    return esleme, agaclar


def tara(adaylar, kok, sd):
    import harita as H
    ayar = ayar_oku()
    boyutlar = {rel: (yol, boyut) for rel, yol, boyut, _ in adaylar}
    esleme, agaclar = projeler(list(boyutlar))
    t = H._Toplayici()
    for rel, proje in sorted(esleme.items()):
        oku = _okuyucu(rel)
        yol, boyut = boyutlar[rel]
        if oku is None or boyut > H.MAKS_BOYUT:
            continue
        oku(H._oku(yol), rel, proje, t, ayar)
    sayim = {}
    for k in t.kayit.values():
        sayim[k["proje"]] = sayim.get(k["proje"], 0) + 1
    for proje, n in sayim.items():
        t.ekle(f"teknoloji-proje:{proje}", proje, proje, f"Proje: {n} teknoloji", "genel")
        t.kayit[f"teknoloji-proje:{proje}"].update(proje=proje, kategori="proje", surum="", tur="Proje")
    for a in agaclar:
        t.ekle(f"teknoloji-haric:{a}", a, a, "Çalışma ağacı (proje sayılmadı)", "genel")
        t.kayit[f"teknoloji-haric:{a}"].update(proje=a, kategori="haric", surum="", tur="Çalışma ağacı")
    return t.liste()


# --- Markdown üretimi ---

def _proje_adi(proje, kok):
    return proje if proje != "." else os.path.basename(os.path.abspath(kok)) or "kok"


def _dosya_adlari(proje_listesi, kok):
    adlar, kullanilan = {}, {}
    for p in proje_listesi:
        kisa = _proje_adi(p, kok).split("/")[-1]
        kullanilan.setdefault(kisa, []).append(p)
    for kisa, ps in kullanilan.items():
        for p in ps:
            adlar[p] = (kisa if len(ps) == 1 else _proje_adi(p, kok).replace("/", "--")) + ".md"
    return adlar


def _hucre(s):
    return str(s).replace("|", "\\|")


def _tablo(satirlar, proje_sutunu):
    bas = "| Teknoloji | Sürüm | " + ("Projeler | " if proje_sutunu else "Tür | ") + "Kaynak |"
    cikti = [bas, "|---|---|---|---|"]
    cikti += satirlar
    return cikti


def md_yaz(sd: str, kok: str, uretim: str) -> list[str]:
    """Katman dosyasından README ve proje md'lerini yazar; önceki md'ler silinir (üretilen klasör). Yazılan dosya adlarını döner."""
    import harita as H
    v = H._katman_oku(sd, "teknolojiler")
    hedef = os.path.join(H.klasor_yolu(sd), KLASOR)
    if os.path.isdir(hedef):
        for ad in os.listdir(hedef):
            if ad.endswith(".md"):
                os.remove(os.path.join(hedef, ad))
    if not v:
        return []
    ayar = ayar_oku()
    kategoriler = _kategori_adlari(ayar)
    tek = [r for r in v["kayitlar"] if r.get("kategori") not in ("proje", "haric")]
    haric = [r["ad"] for r in v["kayitlar"] if r.get("kategori") == "haric"]
    proje_listesi = sorted({r["proje"] for r in tek})
    dosya = _dosya_adlari(proje_listesi, kok)
    ust = ["", f"_Üretim: {uretim}. Betikle üretilir, elle düzenlenmez (`orkestra harita yenile`). {SURUM_KURALI}_", ""]
    yazilan = []

    readme = ["# Teknoloji envanteri", *ust, "## Projeler", ""]
    for p in proje_listesi:
        n = sum(1 for r in tek if r["proje"] == p)
        readme.append(f"- [{_proje_adi(p, kok)}]({dosya[p]}): `{p}`, {n} teknoloji")
    if haric:
        readme.append(f"- Hariç: {len(haric)} çalışma ağacı proje sayılmadı ({', '.join(f'`{h}`' for h in haric)})")
    readme.append("")
    for no, (kod, ad) in enumerate(kategoriler, 1):
        grup = {}
        for r in tek:
            if r["kategori"] == kod:
                g = grup.setdefault(r["ad"].lower(), {"ad": r["ad"], "surum": set(), "proje": set(), "yer": set()})
                if r["surum"]:
                    g["surum"].add(r["surum"])
                g["proje"].add(_proje_adi(r["proje"], kok).split("/")[-1])
                g["yer"].update(r["yer"])
        if not grup:
            continue
        satir = [f"| `{g['ad']}` | {_hucre(', '.join(sorted(g['surum'])) or '-')} | {_hucre(', '.join(sorted(g['proje'])))} | "
                 f"{_hucre(', '.join(sorted(g['yer'])))} |" for _, g in sorted(grup.items())]
        readme += [f"## {no}. {ad} ({len(grup)})", "", *_tablo(satir, True), ""]
    _yaz(hedef, "README.md", readme, yazilan)

    for p in proje_listesi:
        md = [f"# {_proje_adi(p, kok)}: kullanılan teknolojiler", *ust, f"**Kapsam:** `{p}`", ""]
        for no, (kod, ad) in enumerate(kategoriler, 1):
            satir = [f"| `{r['ad']}` | {_hucre(r['surum'] or '-')} | {_hucre(r['tur'])} | {_hucre(', '.join(r['yer']))} |"
                     for r in sorted(tek, key=lambda r: r["ad"].lower()) if r["proje"] == p and r["kategori"] == kod]
            if satir:
                md += [f"## {no}. {ad} ({len(satir)})", "", *_tablo(satir, False), ""]
        _yaz(hedef, dosya[p], md, yazilan)
    return yazilan


def _yaz(hedef, ad, satirlar, yazilan):
    import harita as H
    H._atomik_yaz(os.path.join(hedef, ad), "\n".join(satirlar) + "\n")
    yazilan.append(ad)
