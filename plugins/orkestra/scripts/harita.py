"""Sistem haritası: projenin mevcut durumunu betikle çıkaran kalıcı katman (ADR-0005; model çağırmaz).

Depo: `<durum dizini>/sistem_haritasi/` altında katman başına `<katman>.json` ve üretilen `INDEX.md`.
Katmanlar: sirlar, dis_baglantilar, surecler, moduller, altyapi, veri_modeli, bagimliliklar, isler_adr, teknolojiler
(teknolojiler: kategorili teknoloji envanteri ve `teknolojiler/` altında md; ADR-0019, harita_teknoloji.py).
Kayıt: {id, ad, yer[], rol, ortam, durum}. durum: `dogrulandi` (kaynakta görüldü) | `dogrulanamadi` (kodda atıf var, canlı kaynak taranmadı).
İmza: katmanın aday dosyalarının (yol, boyut, değişim zamanı) özeti. İmza değişmişse katman baştan taranır ve
dosya yeniden yazılır (elle birleştirme ve sürüm biriktirme yok; eskimiş ya da yanlış kayıt kendiliğinden düşer).
Sır değeri hiçbir kayda girmez: yalnız değişken adı ve dosya yolu okunur. `Keys/` içeriği hiç okunmaz.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re

SURUM = 1
KATMANLAR = ("sirlar", "dis_baglantilar", "surecler", "moduller", "altyapi", "veri_modeli", "bagimliliklar", "isler_adr",
            "teknolojiler", "ortamlar")
KLASOR_ADI = "sistem_haritasi"
HARIC_DIZIN = {".git", "node_modules", "__pycache__", ".venv", "venv", "_arsiv", ".mypy_cache", ".pytest_cache",
               "dist", "build", ".idea", ".vscode", "worktrees", "site-packages", KLASOR_ADI}
SIR_DIZINI = {"Keys"}  # içeriği okunmaz, yalnız dosya adları kayda girer
METIN_UZANTI = {".py", ".js", ".ts", ".tsx", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".txt", ".md", ".sql",
                ".sh", ".ps1", ".bicep", ".tf", ".env", ".service", ".conf", ".properties"}
MAKS_BOYUT = 512 * 1024
SIR_AD = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|PASSWD|PWD|CREDENTIAL|CONNECTION|VAULT|DSN", re.I)
ENV_OKU = re.compile(r"""(?:os\.environ(?:\.get)?\s*[\[(]\s*|os\.getenv\s*\(\s*|process\.env\.|getenv\s*\(\s*)["']?([A-Z][A-Z0-9_]{2,})""")
ENV_SATIR = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
KEYVAULT = re.compile(r"SecretClient|azure\.keyvault|vault\.azure\.net|DefaultAzureCredential|keyvault", re.I)
URL = re.compile(r"""https?://(?:[^/@\s"'<>]*@)?([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)""")
URL_HARIC = {"example.com", "www.w3.org", "json-schema.org", "schemas.microsoft.com", "localhost"}
TABLO = re.compile(r"""(?:CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_."]+)|__tablename__\s*=\s*["']([A-Za-z0-9_]+)["'])""", re.I)
GIRIS = re.compile(r"""^if\s+__name__\s*==\s*["']__main__["']""", re.M)
DOCSTR = re.compile(r'^\s*(?:[rRuUbB]{0,2})(?:"""|\'\'\')(.+?)(?:"""|\'\'\'|$)', re.S)


def klasor_yolu(sd: str) -> str:
    return os.path.join(sd, KLASOR_ADI)


def sd_bul(klasor: str) -> str | None:
    """Bir iş klasöründen yukarı çıkarak `.claude/orkestra` durum dizinini bulur."""
    yol = os.path.abspath(klasor)
    while True:
        aday = os.path.join(yol, ".claude", "orkestra")
        if os.path.isdir(aday):
            return aday
        ust = os.path.dirname(yol)
        if ust == yol:
            return None
        yol = ust


def _simdi() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _yol(rel: str) -> str:
    return rel.replace(os.sep, "/")


def yuru(kok: str) -> list[tuple[str, str, int, int]]:
    """Proje dosyaları: (göreli yol, mutlak yol, boyut, değişim zamanı ns). Haric dizinler atlanır."""
    cikti = []
    for dizin, altlar, dosyalar in os.walk(kok):
        altlar[:] = [a for a in altlar if a not in HARIC_DIZIN
                     and _yol(os.path.relpath(os.path.join(dizin, a), kok)) != ".claude/orkestra"]  # orkestra durum verisi proje değil
        for ad in dosyalar:
            yol = os.path.join(dizin, ad)
            try:
                st = os.stat(yol)
            except OSError:
                continue
            cikti.append((_yol(os.path.relpath(yol, kok)), yol, st.st_size, st.st_mtime_ns))
    return cikti


def _metin_mi(rel: str, boyut: int) -> bool:
    ad = os.path.basename(rel).lower()
    uz = os.path.splitext(ad)[1]
    return boyut <= MAKS_BOYUT and (uz in METIN_UZANTI or ad.startswith(".env") or ad in ("dockerfile", "procfile", "crontab"))


def _oku(yol: str) -> str:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _parcalar(rel: str) -> list[str]:
    return rel.split("/")


def _sir_dizininde(rel: str) -> bool:
    return any(p in SIR_DIZINI for p in _parcalar(rel)[:-1])


# --- Aday süzgeçleri: katmanın tarayacağı dosyalar (imza bunlar üzerinden hesaplanır) ---

def _env_dosyasi(rel: str) -> bool:
    ad = os.path.basename(rel).lower()
    return ad.startswith(".env") or ad.endswith(".env")


def _kod_dosyasi(rel: str) -> bool:
    return os.path.splitext(rel)[1].lower() in (".py", ".js", ".ts", ".tsx", ".ps1", ".sh")


def _aday_sirlar(rel):
    return _sir_dizininde(rel) or _env_dosyasi(rel) or _kod_dosyasi(rel)


def _aday_dis(rel):
    return _kod_dosyasi(rel) or os.path.splitext(rel)[1].lower() in (".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".env")


def _aday_surecler(rel):
    ad = os.path.basename(rel).lower()
    return (".github/workflows/" in rel and ad.endswith((".yml", ".yaml"))) or ad.startswith("docker-compose") \
        or ad in ("procfile", "crontab") or ad.endswith((".service", ".cron"))


def _aday_moduller(rel):
    return rel.endswith(".py") or os.path.basename(rel) == "package.json"


def _aday_altyapi(rel):
    ad = os.path.basename(rel).lower()
    return ad.startswith("dockerfile") or ad.endswith((".bicep", ".tf")) or ad.startswith(("azure-pipelines", "host.json", "function.json")) \
        or ".github/workflows/" in rel


def _aday_veri(rel):
    return rel.endswith((".sql", ".py"))


def _aday_bagimlilik(rel):
    ad = os.path.basename(rel).lower()
    return (ad.startswith("requirements") and ad.endswith(".txt")) or ad in ("pyproject.toml", "package.json")


def _aday_teknoloji(rel):
    """Manifestler, Dockerfile, Terraform, iş akışı ve çalışma ağacı işareti (`.git` dosyası; `.git` dizini yürünmez)."""
    return os.path.basename(rel) == ".git" or _aday_bagimlilik(rel) or _aday_altyapi(rel)


ADAY = {"sirlar": _aday_sirlar, "dis_baglantilar": _aday_dis, "surecler": _aday_surecler, "moduller": _aday_moduller,
        "altyapi": _aday_altyapi, "veri_modeli": _aday_veri, "bagimliliklar": _aday_bagimlilik, "teknolojiler": _aday_teknoloji,
        "ortamlar": lambda rel: __import__("harita_ortam").aday(rel)}


def _adaylar(katman, dosyalar, kok, sd):
    if katman == "isler_adr":
        return [d for d in dosyalar if re.search(r"(^|/)adr/ADR-[^/]+\.md$", d[0])]
    return [d for d in dosyalar if ADAY[katman](d[0])]


def _imza(katman, adaylar, sd):
    h = hashlib.sha1()
    for rel, _, boyut, zaman in sorted(adaylar):
        h.update(f"{rel}|{boyut}|{zaman}\n".encode())
    if katman == "isler_adr":
        try:
            st = os.stat(os.path.join(sd, "isler.json"))
            h.update(f"isler.json|{st.st_size}|{st.st_mtime_ns}".encode())
        except OSError:
            h.update(b"isler.json|yok")
    if katman == "teknolojiler":
        import harita_teknoloji as T
        h.update(T.ayar_imzasi().encode())
    if katman == "ortamlar":
        import harita_ortam as O
        h.update(O.ayar_imzasi(sd).encode())
    return h.hexdigest()


# --- Tarayıcılar: her biri kayıt listesi döner ---

class _Toplayici:
    """Aynı kimlikli kayıtları birleştirir (yer listesi birikir)."""

    def __init__(self):
        self.kayit: dict[str, dict] = {}

    def ekle(self, kid, ad, yer, rol, ortam="genel", durum="dogrulandi"):
        k = self.kayit.setdefault(kid, {"id": kid, "ad": ad, "yer": [], "rol": rol, "ortam": ortam, "durum": durum})
        if yer not in k["yer"]:
            k["yer"].append(yer)

    def liste(self):
        for k in self.kayit.values():
            k["yer"].sort()
        return sorted(self.kayit.values(), key=lambda k: k["id"])


def _tara_sirlar(adaylar, kok, sd):
    t = _Toplayici()
    for rel, yol, boyut, _ in adaylar:
        if _sir_dizininde(rel):
            t.ekle(f"sir:dosya:{os.path.basename(rel)}", os.path.basename(rel), rel, "Sır dosyası (içerik okunmadı)", durum="dogrulandi")
            continue
        if not _metin_mi(rel, boyut):
            continue
        metin = _oku(yol)
        if _env_dosyasi(rel):
            for satir in metin.splitlines():
                m = ENV_SATIR.match(satir)  # yalnız '=' öncesi ad alınır, değer okunmaz
                if m:
                    t.ekle(f"sir:env:{m.group(1)}", m.group(1), rel, f"Yapılandırma değişkeni tanımlı ({os.path.basename(rel)})")
            continue
        for ad in set(ENV_OKU.findall(metin)):
            if SIR_AD.search(ad):
                t.ekle(f"sir:env:{ad}", ad, rel, "Kod bu ortam değişkenini okuyor")
        if KEYVAULT.search(metin):
            t.ekle("sir:azure-key-vault", "Azure Key Vault", rel, "Kodda Azure Key Vault atfı var; canlı kasa taranmadı", durum="dogrulanamadi")
    return t.liste()


def _tara_dis(adaylar, kok, sd):
    t = _Toplayici()
    for rel, yol, boyut, _ in adaylar:
        if not _metin_mi(rel, boyut) or _sir_dizininde(rel):
            continue
        for host in set(URL.findall(_oku(yol))):
            host = host.lower().strip(".")
            if host in URL_HARIC or host.endswith(".example.com"):
                continue
            t.ekle(f"dis:{host}", host, rel, "Kodda ya da yapılandırmada adı geçen dış adres", durum="dogrulanamadi")
    return t.liste()


def _tara_surecler(adaylar, kok, sd):
    t = _Toplayici()
    for rel, yol, boyut, _ in adaylar:
        if not _metin_mi(rel, boyut):
            continue
        metin, ad = _oku(yol), os.path.basename(rel).lower()
        if ".github/workflows/" in rel:
            m = re.search(r"^name:\s*(.+)$", metin, re.M)
            cron = re.findall(r"cron:\s*['\"]([^'\"]+)['\"]", metin)
            rol = "GitHub Actions iş akışı" + (f", zamanlanmış: {', '.join(cron)}" if cron else "")
            t.ekle(f"surec:workflow:{os.path.basename(rel)}", (m.group(1).strip() if m else ad), rel, rol)
        elif ad.startswith("docker-compose"):
            for s in re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", metin, re.M):
                t.ekle(f"surec:servis:{s}", s, rel, "docker-compose servisi")
        else:
            t.ekle(f"surec:{ad}:{rel}", ad, rel, "Süreç tanımı")
    return t.liste()


def _tara_moduller(adaylar, kok, sd):
    t = _Toplayici()
    for rel, yol, boyut, _ in adaylar:
        if not _metin_mi(rel, boyut):
            continue
        metin = _oku(yol)
        if rel.endswith("package.json"):
            try:
                for ad, komut in (json.loads(metin).get("scripts") or {}).items():
                    t.ekle(f"modul:npm:{rel}:{ad}", f"npm {ad}", rel, f"package.json komutu: {str(komut)[:80]}")
            except ValueError:
                pass
            continue
        m = DOCSTR.match(metin)
        rol = " ".join(m.group(1).split())[:100] if m else "(açıklama yok)"
        giris = bool(GIRIS.search(metin))
        t.ekle(f"modul:{rel}", os.path.basename(rel), rel, rol + (" [giriş noktası]" if giris else ""))
    return t.liste()


def _tara_altyapi(adaylar, kok, sd):
    t = _Toplayici()
    for rel, _, _, _ in adaylar:
        ad = os.path.basename(rel).lower()
        if ad.startswith("dockerfile"):
            tur = "Docker imajı"
        elif ad.endswith(".bicep"):
            tur = "Azure Bicep şablonu"
        elif ad.endswith(".tf"):
            tur = "Terraform"
        elif ".github/workflows/" in rel:
            tur = "CI/CD iş akışı"
        else:
            tur = "Dağıtım yapılandırması"
        t.ekle(f"altyapi:{rel}", os.path.basename(rel), rel, tur)
    return t.liste()


def _tara_veri(adaylar, kok, sd):
    t = _Toplayici()
    for rel, yol, boyut, _ in adaylar:
        if not _metin_mi(rel, boyut):
            continue
        for a, b in TABLO.findall(_oku(yol)):
            tablo = (a or b).strip('"')
            t.ekle(f"veri:{tablo.lower()}", tablo, rel, "Tablo tanımı (CREATE TABLE / __tablename__)")
    return t.liste()


def _tara_bagimlilik(adaylar, kok, sd):
    t = _Toplayici()
    for rel, yol, boyut, _ in adaylar:
        if not _metin_mi(rel, boyut):
            continue
        metin, ad = _oku(yol), os.path.basename(rel).lower()
        if ad.startswith("requirements"):
            for s in metin.splitlines():
                m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*((?:[=<>!~]=?|@)\s*\S+)?", s)
                if m and not s.lstrip().startswith(("#", "-")):
                    t.ekle(f"bagimlilik:py:{m.group(1).lower()}", m.group(1), rel, f"Python paketi {m.group(2) or ''}".strip())
        elif ad == "package.json":
            try:
                veri = json.loads(metin)
            except ValueError:
                continue
            for bolum in ("dependencies", "devDependencies"):
                for paket, surum in (veri.get(bolum) or {}).items():
                    t.ekle(f"bagimlilik:npm:{paket}", paket, rel, f"npm paketi {surum}")
        else:
            m = re.search(r"dependencies\s*=\s*\[(.*?)\]", metin, re.S)
            for paket in re.findall(r"""["']([A-Za-z0-9_.\-]+)""", m.group(1) if m else ""):
                t.ekle(f"bagimlilik:py:{paket.lower()}", paket, rel, "Python paketi (pyproject)")
    return t.liste()


def _tara_isler_adr(adaylar, kok, sd):
    t = _Toplayici()
    for rel, yol, boyut, _ in adaylar:
        m = re.search(r"^#\s*(ADR-\d+[^\n]*)", _oku(yol), re.M)
        kid = re.search(r"(ADR-\d+)", os.path.basename(rel))
        if kid:
            t.ekle(f"adr:{rel}", m.group(1).strip() if m else kid.group(1), rel, "Mimari karar kaydı")
    try:
        with open(os.path.join(sd, "isler.json"), encoding="utf-8") as f:
            isler = json.load(f)
        liste = isler.get("isler", isler) if isinstance(isler, dict) else isler
        for i in liste if isinstance(liste, list) else []:
            if isinstance(i, dict) and i.get("durum") == "acik" and i.get("id"):
                t.ekle(f"is:{i['id']}", f"{i['id']} {i.get('baslik', '')}".strip()[:100], str(i.get("klasor", "")), "Açık iş")
    except (OSError, ValueError):
        pass
    return t.liste()


def _tara_teknoloji(adaylar, kok, sd):
    import harita_teknoloji as T
    return T.tara(adaylar, kok, sd)


def _tara_ortam(adaylar, kok, sd):
    import harita_ortam as O
    return O.tara(adaylar, kok, sd)


TARAYICI = {"sirlar": _tara_sirlar, "dis_baglantilar": _tara_dis, "surecler": _tara_surecler, "moduller": _tara_moduller,
            "altyapi": _tara_altyapi, "veri_modeli": _tara_veri, "bagimliliklar": _tara_bagimlilik, "isler_adr": _tara_isler_adr,
            "teknolojiler": _tara_teknoloji, "ortamlar": _tara_ortam}


# --- Depo ---

def _katman_yolu(sd, katman):
    return os.path.join(klasor_yolu(sd), f"{katman}.json")


def _katman_oku(sd, katman):
    try:
        with open(_katman_yolu(sd, katman), encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, dict) and veri.get("surum") == SURUM else None
    except (OSError, ValueError):
        return None


def _atomik_yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)
    os.replace(gecici, yol)


def denetle(kok: str, sd: str, dosyalar=None) -> dict:
    """{'guncel': [...], 'eskimis': [...]}; dosyası olmayan ya da imzası uyuşmayan katman eskimiştir."""
    dosyalar = dosyalar if dosyalar is not None else yuru(kok)
    guncel, eskimis = [], []
    for k in KATMANLAR:
        mevcut = _katman_oku(sd, k)
        imza = _imza(k, _adaylar(k, dosyalar, kok, sd), sd)
        (guncel if mevcut and mevcut.get("imza") == imza else eskimis).append(k)
    return {"guncel": guncel, "eskimis": eskimis}


def yenile(kok: str, sd: str, katmanlar=None, zorla: bool = False) -> dict:
    """Eskimiş (ya da zorla: tüm) katmanları baştan tarayıp yeniden yazar; INDEX.md'yi günceller."""
    dosyalar = yuru(kok)
    durum = denetle(kok, sd, dosyalar)
    hedef = [k for k in (katmanlar or KATMANLAR) if zorla or k in durum["eskimis"]]
    for k in hedef:
        adaylar = _adaylar(k, dosyalar, kok, sd)
        kayitlar = TARAYICI[k](adaylar, kok, sd)
        _atomik_yaz(_katman_yolu(sd, k), json.dumps(
            {"surum": SURUM, "katman": k, "uretim": _simdi(), "imza": _imza(k, adaylar, sd), "kayitlar": kayitlar},
            ensure_ascii=False, indent=1))
    if hedef or not os.path.exists(os.path.join(klasor_yolu(sd), "INDEX.md")):
        _indeks_yaz(sd)
    if "teknolojiler" in hedef or (_katman_oku(sd, "teknolojiler") and not os.path.exists(
            os.path.join(klasor_yolu(sd), "teknolojiler", "README.md"))):
        import harita_teknoloji as T
        T.md_yaz(sd, kok, _simdi())
    return {"yenilenen": hedef, "atlanan": [k for k in KATMANLAR if k not in hedef]}


def _indeks_yaz(sd):
    satir = ["# Sistem haritası", "", f"_Üretim: {_simdi()}. Betikle üretilir, elle düzenlenmez (`orkestra harita yenile`)._", ""]
    for k in KATMANLAR:
        v = _katman_oku(sd, k)
        if not v:
            continue
        kay = v["kayitlar"]
        satir += [f"## {k} ({len(kay)})", ""]
        for r in kay[:15]:
            isaret = "" if r["durum"] == "dogrulandi" else " (doğrulanamadı)"
            satir.append(f"- `{r['id']}`: {r['rol']}{isaret}")
        if len(kay) > 15:
            satir.append(f"- … {len(kay) - 15} kayıt daha: `{k}.json`")
        satir.append("")
    _atomik_yaz(os.path.join(klasor_yolu(sd), "INDEX.md"), "\n".join(satir))


def oku(kok: str, sd: str, katman: str | None = None) -> list[dict]:
    """Kayıtları döner; eskimiş katmanı önce kendisi yeniler."""
    yenile(kok, sd)
    katmanlar = (katman,) if katman else KATMANLAR
    sonuc = []
    for k in katmanlar:
        v = _katman_oku(sd, k)
        if v:
            sonuc += [dict(r, katman=k) for r in v["kayitlar"]]
    return sonuc


def kenar_denetle(kok: str, graf: str) -> dict:
    """ADR-0112 kenar düzeyinde eskime: kenarın kaynak dosyasının bugünkü hash'i kayıtlı hash'ten farklıysa kenar eskimiştir.
    {'guncel': [...], 'eskimis': [...]} (şemaya uyan kenarlar); kenar dosyası yoksa ikisi de boş."""
    import harita_kenar as K
    import harita_sema as S
    yol = os.path.join(graf, "kenarlar.jsonl")
    kenarlar = S.kenarlari_oku(yol)[0] if os.path.exists(yol) else []
    guncel, eskimis = [], []
    for k in kenarlar:
        (guncel if K._hash(kok, k["kaynak"]) == k["hash"] else eskimis).append(k)
    return {"guncel": guncel, "eskimis": eskimis}


def kenar_yenile(kok: str, graf: str) -> dict:
    """Eskiyen kenarları kaynak dosya başına yeniden hesaplar; değişmeyen kenara dokunmaz. Statik ve geçmiş kökenli eski kenar
    düşer, yerine yenisi yazılır. LLM ve bildirilen kökenli eski kenar koruma altındadır: yeniden doğrulanana kadar eski hash'iyle
    `guven: dusuk` kalır. Dönüş: {'yenilenen': n, 'dogrulanmayi_bekleyen': n}."""
    import harita_kenar as K
    d = kenar_denetle(kok, graf)
    kaynaklar = {k["kaynak"] for k in d["eskimis"]}
    if not kaynaklar:
        return {"yenilenen": 0, "dogrulanmayi_bekleyen": 0}
    otomatik = ("statik", "gecmis")
    bekleyen = [dict(k, guven="dusuk") for k in d["eskimis"] if k["koken"] not in otomatik]
    yeni = [k for k in K.statik_kenarlar(kok) + K.gecmis_kenarlar(kok) if k["kaynak"] in kaynaklar]
    K.yaz(d["guncel"] + bekleyen + yeni, os.path.join(graf, "kenarlar.jsonl"))
    return {"yenilenen": len(yeni), "dogrulanmayi_bekleyen": len(bekleyen)}


def kayit_kimlikleri(sd: str) -> set[str] | None:
    """Haritadaki tüm kayıt kimlikleri; harita hiç yoksa None (plan kapısı doğrulayamaz)."""
    kim, var = set(), False
    for k in KATMANLAR:
        v = _katman_oku(sd, k)
        if v:
            var = True
            kim |= {r["id"] for r in v["kayitlar"]}
    return kim if var else None
