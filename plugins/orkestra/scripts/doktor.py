#!/usr/bin/env python3
"""orkestra doktor: ilk çalıştırma sağlık denetimi + güvenli onarım.

Yalnız standart kütüphane ve cfg.py kullanır (ork_lib'e bağımlı değil): hook_python Python bulamasa da
`python scripts/doktor.py` kendi başına çalışır.

Kontroller (kimlik, sınıf, işlev). Sınıf: zorunlu | onerilen | opsiyonel.
Durum: gecti | uyari | hata | onarildi | atlandi.
Onarım sınıfları (plan K3):
  A  orkestra'nın kendi dizinini etkiler; --duzelt ile otomatik uygulanır, geri alma kaydı yazılır.
  B  makineyi değiştirir (pip install, git config --global); yalnız --duzelt ile birlikte --evet verilirse (ya da etkileşimli onayla).
  C  yalnız rehber (VPN, anahtar, kurulum); doktor hiçbir şey değiştirmez.
`--kuru` hiçbir şey yazmaz. Çıkış kodu: 0 = zorunlu kontrollerde hata yok, 1 = zorunlu kontrol hatalı.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import glob
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Callable, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402

DURUMLAR = ("gecti", "uyari", "hata", "onarildi", "atlandi")
EN_AZ_PYTHON = (3, 9)


# ---------------------------------------------------------------- veri tipleri

@dataclasses.dataclass
class Baglam:
    proje: Optional[str] = None
    kuru: bool = False
    proje_kod: bool = True           # False: projedeki doktor.d/*.py yüklenmez (arka plan koşusu güvenilmeyen depo kodu çalıştırmasın)


@dataclasses.dataclass
class Sonuc:
    durum: str
    mesaj: str
    ayrinti: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Onarim:
    sinif: str                       # A | B | C
    aciklama: str                    # kullanıcıya gösterilen tek satır
    uygula: Optional[Callable[[], str]] = None
    geri_al: Optional[dict] = None   # serileştirilebilir: {"tur": "dosya", yol, onceki} | {"tur": "komut", argv}
    komut: Optional[str] = None      # B/C için elle çalıştırılacak komut ya da rehber


@dataclasses.dataclass
class Kontrol:
    id: str
    ad: str
    sinif: str
    kontrol: Callable[[Baglam], Sonuc]
    onar: Optional[Callable[[Baglam, Sonuc], Optional[Onarim]]] = None


def _ok(m, **a):
    return Sonuc("gecti", m, a)


def _uyari(m, **a):
    return Sonuc("uyari", m, a)


def _hata(m, **a):
    return Sonuc("hata", m, a)


def _calistir(argv, zaman=60):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=zaman, encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return -1, str(e)


def _yazilabilir(dizin: str, olustur: bool = True) -> bool:
    """Dizine yazılabilir mi. olustur=False (kuru koşu): hiçbir şey oluşturmaz; var olan en yakın üst dizinin yazma iznine bakar."""
    if not olustur:
        d = os.path.abspath(dizin)
        while not os.path.isdir(d) and os.path.dirname(d) != d:
            d = os.path.dirname(d)
        return os.access(d, os.W_OK)
    try:
        os.makedirs(dizin, exist_ok=True)
        fd, yol = tempfile.mkstemp(dir=dizin, prefix=".doktor_")
        os.close(fd)
        os.remove(yol)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- kontroller

def k_python(b: Baglam) -> Sonuc:
    py = cfg.al("python")
    if not py:
        return _hata("Python yorumlayıcı bulunamadı")
    kod, cikti = _calistir([py, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"], 30)
    if kod != 0:
        return _hata(f"Python çalışmıyor: {py}", yol=py)
    try:
        sur = tuple(int(x) for x in cikti.strip().split(".")[:2])
    except ValueError:
        return _hata(f"Python sürümü okunamadı: {py}", yol=py)
    if sur < EN_AZ_PYTHON:
        return _hata(f"Python {sur[0]}.{sur[1]} eski; en az {EN_AZ_PYTHON[0]}.{EN_AZ_PYTHON[1]} gerekir", yol=py)
    return _ok(f"Python {sur[0]}.{sur[1]}", yol=py)


def o_python(b, s):
    return Onarim("C", "Python 3.9+ kur (python.org ya da paket yöneticisi) ya da ORKESTRA_PYTHON ile yorumlayıcı göster",
                  komut="ORKESTRA_PYTHON=<python yolu>")


def k_pytest(b: Baglam) -> Sonuc:
    py = cfg.al("python")
    if not py:
        return Sonuc("atlandi", "Python yok")
    kod, _ = _calistir([py, "-c", "import pytest"], 60)
    return _ok("pytest var") if kod == 0 else _uyari("pytest yok (test kapısı pytest ister)", yol=py)


def o_pytest(b, s):
    py = s.ayrinti.get("yol") or cfg.al("python")
    argv = [py, "-m", "pip", "install", "pytest"]

    def uygula():
        kod, cikti = _calistir(argv, 600)
        if kod != 0:
            raise RuntimeError(cikti.strip().splitlines()[-1] if cikti.strip() else "pip hata verdi")
        return "pytest kuruldu"
    return Onarim("B", "pytest'i pip ile kur", uygula, {"tur": "komut", "argv": [py, "-m", "pip", "uninstall", "-y", "pytest"]},
                  komut=" ".join(f'"{a}"' if " " in a else a for a in argv))


def k_hook_yorumlayici(b: Baglam) -> Sonuc:
    """bin/hook_python sırası: python3 > python > py -3 (WindowsApps stub'ları atlanır)."""
    for ad in ("python3", "python"):
        yol = shutil.which(ad)
        if yol and "windowsapps" not in yol.lower():
            return _ok(f"hook yorumlayıcısı: {ad}", yol=yol)
    if shutil.which("py"):
        return _ok("hook yorumlayıcısı: py -3", yol=shutil.which("py"))
    return _hata("python3/python/py PATH'te yok: hook'lar çalışmaz")


def o_hook_yorumlayici(b, s):
    return Onarim("C", "Python'u PATH'e ekle (Windows'ta Store stub'ı değil gerçek kurulum); hook ve CLI aynı sırayı kullanır",
                  komut="python.org'dan kur ve 'Add to PATH' seç")


def k_eklenti_dosyalari(b: Baglam) -> Sonuc:
    kok = cfg.eklenti_koku()
    eksik = [g for g in ("bin/hook_python", "bin/orkestra", "scripts/hook.py", "scripts/orkestra.py", "hooks/hooks.json")
             if not os.path.isfile(os.path.join(kok, *g.split("/")))]
    if eksik:
        return _hata("eklenti dosyası eksik: " + ", ".join(eksik), kok=kok)
    try:
        with open(os.path.join(kok, "hooks", "hooks.json"), encoding="utf-8") as f:
            n = sum(len(m.get("hooks", [])) for olay in json.load(f).get("hooks", {}).values() for m in olay)
    except (OSError, ValueError) as e:
        return _hata(f"hooks.json okunamadı: {e}", kok=kok)
    return _ok(f"eklenti dosyaları tamam ({n} hook)", kok=kok, surum=cfg.eklenti_surumu())


def o_eklenti_dosyalari(b, s):
    return Onarim("C", "Eklentiyi yeniden kur: claude plugin install orkestra (ya da `orkestra guncelle`)", komut="orkestra guncelle")


def k_yazma(b: Baglam) -> Sonuc:
    ev = cfg.ev_dizini()
    if not _yazilabilir(ev, olustur=not b.kuru):
        return _hata(f"config dizini yazılamıyor: {ev}", ev=ev)
    if b.proje:
        sd = os.path.join(b.proje, ".claude", "orkestra")
        if os.path.isdir(sd) and not _yazilabilir(sd, olustur=not b.kuru):
            return _hata(f"durum klasörü yazılamıyor: {sd}", sd=sd)
    return _ok("config ve durum klasörleri yazılabilir", ev=ev)


def o_yazma(b, s):
    return Onarim("C", "Klasör izinlerini düzelt ya da ORKESTRA_HOME ile yazılabilir bir yer göster", komut="ORKESTRA_HOME=<klasör>")


def k_home_cakisma(b: Baglam) -> Sonuc:
    """~/.claude/orkestra proje durumu içeriyorsa, home altındaki her proje ork_lib.proje_dizini() yüzünden orkestrayı açık sayar."""
    d = os.path.join(os.path.expanduser("~"), ".claude", "orkestra")
    belirtec = [x for x in ("gorevler", "ortak_defter.md", "isler.json", "gunluk.jsonl") if os.path.exists(os.path.join(d, x))]
    if belirtec:
        return _uyari("home dizinindeki .claude/orkestra proje durumu içeriyor: home altındaki tüm projeler orkestrayı açık sayar",
                      yol=d, belirtec=belirtec)
    return _ok("home dizininde çakışan orkestra durum klasörü yok")


def o_home_cakisma(b, s):
    return Onarim("C", f"{s.ayrinti.get('yol', '~/.claude/orkestra')} klasörünü başka bir adla taşı (ör. orkestra-eski); "
                       "home gerçekten bir orkestra projesiyse bu uyarıyı yok say", komut="klasörü yeniden adlandır")


def k_makine_config(b: Baglam) -> Sonuc:
    if not os.path.isfile(cfg.makine_dosyasi()):
        return _uyari("makine config'i yok (ilk çalıştırma)")
    if not cfg.makine_taze_mi():
        return _uyari("makine config'i eski: farklı makine ya da şema sürümü")
    d = cfg.makine_oku().get("degerler") or {}
    bayat = [ad for ad in d if not cfg.DOGRULA.get(ad, lambda v: True)(cfg._katman_degeri({"degerler": d}, ad))]
    if bayat:
        return _uyari("makine config'inde geçersiz değer: " + ", ".join(sorted(bayat)), bayat=sorted(bayat))
    return _ok(f"makine config'i güncel ({len(d)} değer)")


def o_makine_config(b, s):
    yol = cfg.makine_dosyasi()
    try:
        with open(yol, encoding="utf-8") as f:
            onceki = f.read()
    except OSError:
        onceki = None

    def uygula():
        bulunan = {}
        for ad in ("python", "claude_exe", "bash"):
            d = cfg.KESIF.get(ad)
            v = d() if d else None
            if v and cfg.DOGRULA.get(ad, lambda x: True)(v):
                bulunan[ad] = v
        if not cfg.makine_taze_mi() and os.path.isfile(yol):
            os.remove(yol)  # eski makineden kalan değerler taşınmaz
        cfg.makine_yaz(bulunan, kaynak="doktor")
        return "makine config'i yazıldı: " + ", ".join(sorted(bulunan))
    return Onarim("A", "keşfedilen yolları makine config'ine yaz", uygula, {"tur": "dosya", "yol": yol, "onceki": onceki})


def k_claude_exe(b: Baglam) -> Sonuc:
    exe = cfg.al("claude_exe")
    return _ok("claude bulundu", yol=exe) if exe else _uyari("claude çalıştırılabilir dosyası bulunamadı (arka plan ajanları ve `orkestra guncelle` çalışmaz)")


def o_claude_exe(b, s):
    return Onarim("C", "Claude Code'u kur ya da CLAUDE_CODE_EXECPATH ile yolunu göster", komut="CLAUDE_CODE_EXECPATH=<claude yolu>")


def k_bash(b: Baglam) -> Sonuc:
    yol = cfg.al("bash")
    return _ok("bash bulundu", yol=yol) if yol else _uyari("bash bulunamadı (plan kanıtlarındaki `komut` satırları koşmaz)")


def o_bash(b, s):
    return Onarim("C", "Git for Windows kur (bash içerir) ya da ORKESTRA_BASH ile yolunu göster", komut="ORKESTRA_BASH=<bash yolu>")


def k_git(b: Baglam) -> Sonuc:
    g = shutil.which("git")
    if not g:
        return _uyari("git bulunamadı (otomatik commit, yayın klonu ve iş şeridi çalışmaz)")
    if b.proje and os.path.isdir(os.path.join(b.proje, ".git")):
        kod, cikti = _calistir(["git", "-C", b.proje, "rev-parse", "--is-inside-work-tree"], 30)
        if kod != 0 and "dubious ownership" in cikti:
            return _hata("git bu proje klasörünü güvenli saymıyor (safe.directory)", proje=b.proje)
    return _ok("git bulundu", yol=g)


def o_git(b, s):
    if s.ayrinti.get("proje"):
        p = s.ayrinti["proje"].replace("\\", "/")
        argv = ["git", "config", "--global", "--add", "safe.directory", p]

        def uygula():
            kod, cikti = _calistir(argv, 30)
            if kod != 0:
                raise RuntimeError(cikti.strip())
            return f"safe.directory eklendi: {p}"
        return Onarim("B", "projeyi git safe.directory listesine ekle (global git ayarı)", uygula,
                      {"tur": "komut", "argv": ["git", "config", "--global", "--fixed-value", "--unset", "safe.directory", p]},
                      komut=" ".join(argv))
    return Onarim("C", "git kur (git-scm.com)", komut="git --version")


def k_utf8(b: Baglam) -> Sonuc:
    if sys.flags.utf8_mode or os.environ.get("PYTHONUTF8") == "1":
        return _ok("UTF-8 modu açık")
    enc = (sys.stdout.encoding or "").lower().replace("-", "")
    if enc == "utf8":
        return _ok("konsol UTF-8")
    return _uyari(f"varsayılan kodlama {sys.stdout.encoding}; Türkçe çıktı bozulabilir")


def o_utf8(b, s):
    return Onarim("C", "PYTHONUTF8=1 ayarla (araclar/projeye_kur.py bunu proje settings.json env'ine ekler)", komut="PYTHONUTF8=1")


def k_panel_port(b: Baglam) -> Sonuc:
    port = cfg.panel_port(b.proje)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        dolu = s.connect_ex(("127.0.0.1", port)) == 0
    servis = _panel_servisi_kurulu()
    if dolu:
        if servis:
            return _ok(f"panel portu {port} dolu; Task Scheduler görevi 'Orkestra Panel' kurulu", port=port)
        return _uyari(f"panel portu {port} dolu (orkestra paneli çalışıyorsa normal)", port=port)
    if servis:
        return _uyari(f"Task Scheduler görevi 'Orkestra Panel' kurulu ama panel portu {port} boş: `orkestra panel` ya da `orkestra panel servis durum`", port=port)
    return _ok(f"panel portu {port} boş", port=port)


def _panel_servisi_kurulu() -> bool:
    """'Orkestra Panel' görevi kayıtlı mı (Windows dışında False; doktor ork_lib'e bağımlı olmadığı için schtasks doğrudan)."""
    if os.name != "nt":
        return False
    try:
        return subprocess.run(["schtasks", "/Query", "/TN", "Orkestra Panel"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def o_panel_port(b, s):
    return Onarim("C", "panel çalışmıyorsa portu boşalt ya da ORKESTRA_PANEL_PORT ile başka port ver", komut="ORKESTRA_PANEL_PORT=<port>")


def k_pazar_klonu(b: Baglam) -> Sonuc:
    kaynak = cfg.pazar_kaynagi()
    if not kaynak:
        return _ok("pazar klonu yok (--plugin-dir ya da başka kurulum)")
    if not os.path.isdir(os.path.join(kaynak, ".git")):
        return _ok("pazar kaynağı git klonu değil", kaynak=kaynak)
    kod, cikti = _calistir(["git", "-C", kaynak, "status", "--porcelain"], 30)
    if kod != 0:
        return _uyari("pazar klonu okunamadı", kaynak=kaynak)
    if cikti.strip():
        return _uyari("pazar klonunda commitlenmemiş değişiklik var (güncelleme reddedilir)", kaynak=kaynak)
    return _ok("pazar klonu temiz", kaynak=kaynak)


def o_pazar_klonu(b, s):
    k = s.ayrinti.get("kaynak", "<klon>")
    return Onarim("C", "pazar klonundaki değişiklikleri commitle ya da sakla (doktor silmez)", komut=f"git -C {k} status --short")


def k_izin_politikasi(b: Baglam) -> Sonuc:
    kok = cfg.eklenti_koku()
    try:
        sys.path.insert(0, os.path.join(kok, "scripts"))
        import izin_politikasi as IP
        c = IP.ayar_yukle(os.path.join(b.proje, ".claude", "orkestra") if b.proje else None)
        kotu = IP.gecersiz_desenler(c)
        mod = IP.mod_bul(c)
        with open(os.path.join(kok, "hooks", "hooks.json"), encoding="utf-8") as f:
            eslesme = json.load(f)["hooks"]["PreToolUse"][0]["matcher"]
    except Exception as e:
        return _hata(f"izin politikası okunamadı: {type(e).__name__}: {e}")
    if kotu:
        return _hata("izin politikasında geçersiz desen: " + ", ".join(kotu), desenler=kotu)
    if "mcp__" not in eslesme:
        return _uyari("hooks.json PreToolUse eşleşmesi MCP araçlarını kapsamıyor: GitHub/Jira kapısı çalışmaz", eslesme=eslesme)
    return _ok(f"izin politikası geçerli (mod: {mod})", mod=mod)


def o_izin_politikasi(b, s):
    return Onarim("C", "ayarlar/izin_politikasi.json desenlerini düzelt ve hooks.json PreToolUse eşleşmesine mcp__.* ekle (eklenti kaynağında)",
                  komut="orkestra izin goster")


_CURSOR_SINIRI = ("Cursor: hook'lar cursor_hook.py adaptörüyle çalışır; .cursor/hooks.json git kökünden okunur (iç klasördekiler yok sayılır), "
                  "IDE sürümü sınanmadı (yalnız CLI), taşınabilirlik yaklaşık %83")


def _cursor_izleri(b: Baglam) -> list[str]:
    """Cursor kullanıldığına işaret eden yollar: projede .cursor klasörü, kullanıcı dizininde .cursor."""
    adaylar = [os.path.join(b.proje, ".cursor")] if b.proje else []
    adaylar.append(os.path.join(os.path.expanduser("~"), ".cursor"))
    return [a for a in adaylar if os.path.isdir(a)]


def k_cursor_siniri(b: Baglam) -> Sonuc:
    """Cursor izi varsa kısıtı tek satırda söyler; hooks.json BOM'luysa hook'lar sessizce yüklenmez (uyarı)."""
    izler = _cursor_izleri(b)
    if not izler:
        return Sonuc("atlandi", "Cursor izi yok")
    for iz in izler:
        yol = os.path.join(iz, "hooks.json")
        try:
            with open(yol, "rb") as f:
                if f.read(3) == b"\xef\xbb\xbf":
                    return _uyari(f"{yol} BOM'lu: Cursor hook'ları sessizce yüklemez. " + _CURSOR_SINIRI, yol=yol)
        except OSError:
            pass
    return _ok(_CURSOR_SINIRI, izler=izler)


def o_cursor_siniri(b, s):
    return Onarim("C", ".cursor/hooks.json dosyasını BOM'suz UTF-8 olarak yeniden yaz", komut="orkestra doktor")


KONTROLLER: list[Kontrol] = [
    Kontrol("python", "Python yorumlayıcı", "zorunlu", k_python, o_python),
    Kontrol("hook_yorumlayici", "hook yorumlayıcısı (PATH)", "zorunlu", k_hook_yorumlayici, o_hook_yorumlayici),
    Kontrol("eklenti_dosyalari", "eklenti dosyaları ve hook tanımı", "zorunlu", k_eklenti_dosyalari, o_eklenti_dosyalari),
    Kontrol("yazma", "config ve durum klasörü yazma izni", "zorunlu", k_yazma, o_yazma),
    Kontrol("home_cakisma", "home dizininde durum klasörü çakışması", "onerilen", k_home_cakisma, o_home_cakisma),
    Kontrol("makine_config", "makine config'i", "onerilen", k_makine_config, o_makine_config),
    Kontrol("pytest", "pytest", "onerilen", k_pytest, o_pytest),
    Kontrol("izin_politikasi", "izin politikası (kapı desenleri ve MCP eşleşmesi)", "onerilen", k_izin_politikasi, o_izin_politikasi),
    Kontrol("git", "git ve safe.directory", "onerilen", k_git, o_git),
    Kontrol("utf8", "UTF-8 kodlama", "onerilen", k_utf8, o_utf8),
    Kontrol("claude_exe", "claude çalıştırılabilir dosyası", "opsiyonel", k_claude_exe, o_claude_exe),
    Kontrol("bash", "bash", "opsiyonel", k_bash, o_bash),
    Kontrol("panel_port", "panel portu", "opsiyonel", k_panel_port, o_panel_port),
    Kontrol("pazar_klonu", "pazar (yayın) klonu", "opsiyonel", k_pazar_klonu, o_pazar_klonu),
    Kontrol("cursor_siniri", "Cursor hook sınırları", "opsiyonel", k_cursor_siniri, o_cursor_siniri),
]


def proje_kontrolleri(proje: Optional[str]) -> list[Kontrol]:
    """Projeye özgü kontroller: <proje>/.claude/orkestra/doktor.d/*.py; her dosya `KONTROLLER = [Kontrol(...)]` tanımlar.
    Kimlikler `proje:` önekiyle verilir. Yüklenemeyen dosya doktoru düşürmez: kendi adıyla "hata" veren opsiyonel bir kontrol olur.
    Bu kod depodan gelir; yalnız kullanıcının başlattığı koşuda yüklenir (kos: Baglam.proje_kod)."""
    if not proje:
        return []
    dizin = os.path.join(proje, ".claude", "orkestra", "doktor.d")
    sonuc: list[Kontrol] = []
    for yol in sorted(glob.glob(os.path.join(glob.escape(dizin), "*.py"))):
        dosya = os.path.basename(yol)
        try:
            spec = importlib.util.spec_from_file_location("orkestra_doktor_d_" + os.path.splitext(dosya)[0], yol)
            modul = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modul)
            for k in list(modul.KONTROLLER):
                if not isinstance(k, Kontrol) or k.sinif not in ("zorunlu", "onerilen", "opsiyonel"):
                    raise TypeError(f"geçersiz kontrol: {k!r}")
                sonuc.append(k if k.id.startswith("proje:") else dataclasses.replace(k, id="proje:" + k.id))
        except (Exception, SystemExit) as e:
            sonuc.append(Kontrol(f"proje:{dosya}", dosya, "opsiyonel",
                                 lambda b, e=e: Sonuc("hata", f"proje kontrol dosyası yüklenemedi: {type(e).__name__}: {e}")))
    return sonuc


# ---------------------------------------------------------------- çalıştırıcı

def _geri_al_dizini() -> str:
    return os.path.join(cfg.ev_dizini(), "doktor", "geri_al")


def _geri_al_uygula(spec: dict) -> str:
    if spec.get("tur") == "dosya":
        yol, onceki = spec["yol"], spec.get("onceki")
        if onceki is None:
            if os.path.exists(yol):
                os.remove(yol)
            return f"silindi: {yol}"
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(onceki)
        return f"eski içerik yazıldı: {yol}"
    if spec.get("tur") == "komut":
        kod, cikti = _calistir(spec["argv"], 600)
        if kod != 0:
            raise RuntimeError(cikti.strip())
        return "geri alındı: " + " ".join(spec["argv"])
    raise ValueError(f"bilinmeyen geri alma türü: {spec!r}")


def kos(baglam: Baglam, duzelt: bool = False, evet_b: bool = False,
        onay: Optional[Callable[[str], bool]] = None, kontroller: Optional[list[Kontrol]] = None) -> dict:
    """Kontrolleri çalıştırır; duzelt ise onarımları sınıf kurallarına göre uygular. Sonuç sözlüğü JSON'a uygundur."""
    kosu_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    satirlar, geri = [], []
    for k in (kontroller if kontroller is not None else KONTROLLER + (proje_kontrolleri(baglam.proje) if baglam.proje_kod else [])):
        try:
            s = k.kontrol(baglam)
        except Exception as e:  # bir kontrolün çökmesi doktoru düşürmesin
            s = Sonuc("hata", f"kontrol çöktü: {type(e).__name__}: {e}")
        satir = {"id": k.id, "ad": k.ad, "sinif": k.sinif, "durum": s.durum, "mesaj": s.mesaj}
        if s.durum in ("uyari", "hata") and k.onar:
            try:
                o = k.onar(baglam, s)
            except Exception as e:
                o = None
                satir["onarim_hata"] = f"{type(e).__name__}: {e}"
            if o:
                satir["onarim"] = {"sinif": o.sinif, "aciklama": o.aciklama, "komut": o.komut, "uygulandi": False}
                izin = (o.sinif == "A" and duzelt) or (o.sinif == "B" and duzelt and (evet_b or (onay is not None and onay(o.aciklama))))
                if izin and o.uygula and not baglam.kuru:
                    try:
                        if o.geri_al:
                            geri.append({"id": k.id, "aciklama": o.aciklama, "geri_al": o.geri_al})
                        satir["onarim"]["sonuc"] = o.uygula()
                        satir["onarim"]["uygulandi"] = True
                        s2 = k.kontrol(baglam)
                        satir["durum"] = "onarildi" if s2.durum == "gecti" else s2.durum
                        satir["mesaj"] = s2.mesaj if s2.durum != "gecti" else s.mesaj + " -> onarıldı"
                    except Exception as e:
                        satir["onarim"]["hata"] = f"{type(e).__name__}: {e}"
                        if o.geri_al and geri and geri[-1]["id"] == k.id:
                            geri.pop()
        satirlar.append(satir)
    if geri and not baglam.kuru:
        d = _geri_al_dizini()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, kosu_id + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(geri, f, ensure_ascii=False, indent=2)
    sonuc = {"kosu": kosu_id, "surum": cfg.eklenti_surumu(), "parmak": cfg.parmak_izi(), "kuru": baglam.kuru,
             "kontroller": satirlar,
             "ozet": {d: sum(1 for x in satirlar if x["durum"] == d) for d in DURUMLAR},
             "zorunlu_hata": [x["id"] for x in satirlar if x["sinif"] == "zorunlu" and x["durum"] == "hata"]}
    if not baglam.kuru:
        _kaydet(sonuc)
    return sonuc


def _kaydet(sonuc: dict) -> None:
    """Çalışma kaydı (<ev>/doktor/<kosu>.json) ve makine config'ine `son_doktor` işareti (hızlı yol buna bakar)."""
    try:
        d = os.path.join(cfg.ev_dizini(), "doktor")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, sonuc["kosu"] + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(sonuc, f, ensure_ascii=False, indent=2)
        cfg.makine_isaretle({"zaman": sonuc["kosu"], "surum": sonuc["surum"], "ozet": sonuc["ozet"],
                             "zorunlu_hata": sonuc["zorunlu_hata"]})
    except OSError:
        pass


def geri_al_son() -> list[str]:
    """En yeni geri alma kaydını ters sırayla uygular; dosya `.geri_alindi` son ekiyle işaretlenir."""
    d = _geri_al_dizini()
    if not os.path.isdir(d):
        return []
    dosyalar = sorted(f for f in os.listdir(d) if f.endswith(".json") and not f.endswith(".geri_alindi.json"))
    if not dosyalar:
        return []
    yol = os.path.join(d, dosyalar[-1])
    with open(yol, encoding="utf-8") as f:
        kayit = json.load(f)
    cikti = []
    for e in reversed(kayit):
        try:
            cikti.append(f"{e['id']}: {_geri_al_uygula(e['geri_al'])}")
        except Exception as ex:
            cikti.append(f"{e['id']}: GERİ ALINAMADI ({type(ex).__name__}: {ex})")
    os.replace(yol, yol[:-5] + ".geri_alindi.json")
    return cikti


# ---------------------------------------------------------------- çıktı

ETIKET = {"gecti": "OK     ", "uyari": "UYARI  ", "hata": "HATA   ", "onarildi": "ONARILDI", "atlandi": "ATLANDI"}


def metin(sonuc: dict) -> str:
    sat = [f"orkestra doktor {sonuc['kosu']}  (eklenti {sonuc['surum']}, parmak izi {sonuc['parmak']}{', KURU' if sonuc['kuru'] else ''})", ""]
    for x in sonuc["kontroller"]:
        sat.append(f"{ETIKET.get(x['durum'], x['durum'])} [{x['sinif']}] {x['ad']}: {x['mesaj']}")
        o = x.get("onarim")
        if o and x["durum"] in ("uyari", "hata"):
            sat.append(f"           -> {o['sinif']}: {o['aciklama']}" + (f"  ({o['komut']})" if o.get("komut") else ""))
        elif o and o.get("uygulandi"):
            sat.append(f"           -> {o['sinif']}: {o.get('sonuc', 'uygulandı')}")
        if o and o.get("hata"):
            sat.append(f"           !! onarım başarısız: {o['hata']}")
    ozet = sonuc["ozet"]
    sat += ["", "özet: " + ", ".join(f"{d} {n}" for d, n in ozet.items() if n)]
    if sonuc["zorunlu_hata"]:
        sat.append("ZORUNLU HATA: " + ", ".join(sonuc["zorunlu_hata"]))
    elif any(x["durum"] in ("uyari", "hata") and x.get("onarim") for x in sonuc["kontroller"]) and not sonuc["kuru"]:
        sat.append("onarım için: orkestra doktor --duzelt  (B sınıfı için ayrıca --evet)")
    return "\n".join(sat)


def argumanlar(ap) -> None:
    ap.add_argument("--proje", help="proje klasörü (varsayılan: CLAUDE_PROJECT_DIR ya da geçerli klasör)")
    ap.add_argument("--json", action="store_true", help="sonucu JSON yaz")
    ap.add_argument("--duzelt", action="store_true", help="A sınıfı onarımları uygula (B için --evet de ver)")
    ap.add_argument("--evet", action="store_true", help="B sınıfı (makineyi değiştiren) onarımlara onay ver")
    ap.add_argument("--kuru", action="store_true", help="hiçbir şey yazma ya da değiştirme")
    ap.add_argument("--geri-al", action="store_true", help="son doktor onarımlarını geri al")
    ap.add_argument("--arka-plan", action="store_true", help="otomatik koşu: projedeki doktor.d kontrolleri yüklenmez")


def calistir(a) -> int:
    if a.geri_al:
        for s in geri_al_son() or ["geri alınacak kayıt yok"]:
            print(s)
        return 0
    proje = a.proje or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    onay = None
    if a.duzelt and not a.evet and not a.json and sys.stdin.isatty():
        onay = lambda ac: input(f"B sınıfı onarım (makineyi değiştirir): {ac}. Uygulansın mı? [e/H] ").strip().lower() in ("e", "evet", "y", "yes")
    sonuc = kos(Baglam(proje=proje, kuru=a.kuru, proje_kod=not a.arka_plan), duzelt=a.duzelt, evet_b=a.evet, onay=onay)
    print(json.dumps(sonuc, ensure_ascii=False, indent=2) if a.json else metin(sonuc))
    return 1 if sonuc["zorunlu_hata"] else 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="orkestra doktor", description="ilk çalıştırma sağlık denetimi ve güvenli onarım")
    argumanlar(ap)
    return calistir(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
