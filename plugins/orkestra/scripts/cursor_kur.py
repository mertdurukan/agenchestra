"""Yerel Cursor kopyasını (~/.cursor/plugins/local/orkestra) eklenti kaynağıyla eşler (ADR-0172).

Neden: Cursor'un yerel eklenti kopyası elle kopyalanıyordu ve sessizce bayatlıyordu (08.11.2026: 13/42 skill, .mcp.json yok,
adaptörün eski sürümü). Kopya tek komutla, yedek alınarak ve geri alınabilir biçimde yenilenir; yalnız eksik ve farklı dosyalar
yazılır, hedefte fazladan duran dosyalara dokunulmaz. Bağlı (junction/symlink) hedefe dokunulmaz: zaten kaynağı gösterir."""
import datetime
import filecmp
import os
import shutil

HARIC_DIZIN = {"tests", "evals", "docs", "x", ".pytest_cache", "__pycache__", ".git", "node_modules"}
HARIC_DOSYA = {"readme-for-human.md"}
HARIC_UZANTI = (".pyc", ".pyo", ".lock")


def varsayilan_hedef():
    return os.path.join(os.path.expanduser("~"), ".cursor", "plugins", "local", "orkestra")


def baglanti_mi(yol):
    if os.path.islink(yol):
        return True
    junction = getattr(os.path, "isjunction", None)
    return bool(junction and junction(yol))


def kopyalanir(goreli):
    """Göreli yol (/ ya da \\ ile) kopya kümesinde mi? Kopya, bayatlık ve doktor aynı kümeyi bu yüklemle görür."""
    parcalar = goreli.replace("\\", "/").split("/")
    ad = parcalar[-1]
    if any(p in HARIC_DIZIN for p in parcalar[:-1]):
        return False
    return ad not in HARIC_DOSYA and not ad.endswith(HARIC_UZANTI)


def dosyalar(kok):
    """Kopyalanacak dosyalar: {göreli yol (/ ile): mutlak yol}."""
    sonuc = {}
    for dizin, altlar, adlar in os.walk(kok):
        altlar[:] = [a for a in altlar if a not in HARIC_DIZIN]
        for ad in adlar:
            yol = os.path.join(dizin, ad)
            goreli = os.path.relpath(yol, kok).replace(os.sep, "/")
            if kopyalanir(goreli):
                sonuc[goreli] = yol
    return sonuc


def fark(kaynak, hedef):
    """(eksik, degisen): kaynakta olup hedefte olmayan ve içeriği farklı olan göreli yollar. Hedefteki fazlalık sayılmaz."""
    eksik, degisen = [], []
    for goreli, yol in sorted(dosyalar(kaynak).items()):
        h = os.path.join(hedef, *goreli.split("/"))
        if not os.path.isfile(h):
            eksik.append(goreli)
        elif not filecmp.cmp(yol, h, shallow=False):
            degisen.append(goreli)
    return eksik, degisen


def guncelle(kaynak, hedef, yedek_kok):
    """Hedefi yedekleyip eksik ve farklı dosyaları yazar. Dönüş: (mesaj, yedek_yolu | None)."""
    if baglanti_mi(hedef):
        return f"hedef bağlantı, kaynağı gösterir; dokunulmadı: {hedef}", None
    eksik, degisen = fark(kaynak, hedef)
    if not eksik and not degisen:
        return "yerel Cursor kopyası zaten güncel", None
    yedek = None
    if os.path.isdir(hedef):
        yedek = os.path.join(yedek_kok, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), "orkestra")
        os.makedirs(os.path.dirname(yedek), exist_ok=True)
        shutil.copytree(hedef, yedek, ignore=shutil.ignore_patterns("__pycache__"))
        _eski_yedekleri_sil(yedek_kok)
    for goreli in eksik + degisen:
        k, h = os.path.join(kaynak, *goreli.split("/")), os.path.join(hedef, *goreli.split("/"))
        os.makedirs(os.path.dirname(h), exist_ok=True)
        shutil.copy2(k, h)
    return f"yerel Cursor kopyası güncellendi: {len(eksik)} yeni, {len(degisen)} değişen dosya (yedek: {yedek or 'yok, hedef yoktu'})", yedek


YEDEK_SAYISI = 5


def _eski_yedekleri_sil(yedek_kok):
    """Her güncelleme tam kopya bırakır; en yeni YEDEK_SAYISI yedek kalır."""
    try:
        yedekler = sorted(d for d in os.listdir(yedek_kok) if os.path.isdir(os.path.join(yedek_kok, d)))
    except OSError:
        return
    for d in yedekler[:-YEDEK_SAYISI]:
        shutil.rmtree(os.path.join(yedek_kok, d), ignore_errors=True)


def geri_yukle(hedef, yedek):
    """guncelle()'nin yedeğini hedefin yerine koyar; yedek yoksa (hedef yeni kurulmuştu) hedefi kaldırır."""
    if baglanti_mi(hedef):
        return f"hedef bağlantı; dokunulmadı: {hedef}"
    if os.path.isdir(hedef):
        shutil.rmtree(hedef)
    if not yedek:
        return f"kaldırıldı: {hedef}"
    shutil.copytree(yedek, hedef)
    return f"yedekten geri yüklendi: {hedef}"
