"""Orkestra makine/proje config katmanı: makineye özgü değerler (yol, ad, port) için tek erişim noktası.

Yalnız standart kütüphane (doktor hook'tan bağımsız çalışabilsin diye); ork_lib'e bağımlı değildir.

Çözüm önceliği (yüksekten düşüğe): ortam değişkeni > proje config'i > makine config'i > keşif > çağıranın varsayılanı.
  ortam:   ORTAM tablosundaki değişken (ör. python -> ORKESTRA_PYTHON)
  proje:   <proje>/.claude/orkestra/yerel.json
  makine:  <ev>/makine.json; ev = ORKESTRA_HOME ya da ~/.claude/orkestra-makine
  keşif:   KESIF tablosuna kayıtlı işlev (P4); sonuç makine config'ine yazılmaz, yalnız doktor yazar

Dosya biçimi: {"surum": 1, "parmak": "<makine parmak izi>", "olusturma": "<ISO>", "degerler": {ad: {"deger", "kaynak", "zaman"}}}.
Sır değeri yazılmaz (yalnız yol ve ad): sır benzeri anahtar adı ya da değer ValueError verir.
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable

SURUM = 1

# mantıksal ad -> ortam değişkeni (yüksek öncelik)
ORTAM = {
    "python": "ORKESTRA_PYTHON",
    "yayin": "ORKESTRA_YAYIN",
    "claude_exe": "CLAUDE_CODE_EXECPATH",
    "bash": "ORKESTRA_BASH",
    "panel_port": "ORKESTRA_PANEL_PORT",
    "bildirim": "ORKESTRA_BILDIRIM",
}

PANEL_PORT_VARSAYILAN = 8765

# mantıksal ad -> değer geçerli mi (bayat önbellek ya da yanlış ortam değeri bir sonraki katmana düşsün).
# python doğrulanmaz: ORKESTRA_PYTHON bilerek aynen kabul edilir.
DOGRULA: dict[str, Callable[[Any], bool]] = {
    "claude_exe": lambda v: os.path.exists(str(v)),
    "bash": lambda v: os.path.isfile(str(v)),
    "yayin": lambda v: os.path.isdir(str(v)),
}

# mantıksal ad -> keşif işlevi (aşağıda kayıtlı)
KESIF: dict[str, Callable[[], Any]] = {}

_SIR_ANAHTAR = re.compile(r"(key|token|secret|passw|parola|sifre|şifre|credential)", re.I)
_SIR_DEGER = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY)")


def ev_dizini() -> str:
    """Makine config'inin evi: ORKESTRA_HOME > ~/.claude/orkestra-makine.
    Ad bilerek `orkestra` değildir: ork_lib.proje_dizini() cwd'den yukarı `.claude/orkestra` arar; ev dizini bu ad olursa
    ev klasörünün üstündeki her proje (home altındakiler) o klasörü proje durumu sanıp orkestra'yı açık görür (I-026 P11 bulgusu)."""
    e = (os.environ.get("ORKESTRA_HOME") or "").strip()
    return os.path.abspath(e) if e else os.path.join(os.path.expanduser("~"), ".claude", "orkestra-makine")


def makine_dosyasi() -> str:
    return os.path.join(ev_dizini(), "makine.json")


def proje_dosyasi(proje: str) -> str:
    return os.path.join(proje, ".claude", "orkestra", "yerel.json")


def parmak_izi() -> str:
    """Bu makinenin kısa kimliği: bilgisayar adı, işletim sistemi, mimari, home dizini. Sır içermez (sha1 özeti)."""
    ham = "|".join((platform.node().lower(), sys.platform, platform.machine().lower(),
                    os.path.normcase(os.path.expanduser("~"))))
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


def _simdi() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def sir_mi(ad: str, deger: Any) -> bool:
    if _SIR_ANAHTAR.search(str(ad)):
        return True
    return isinstance(deger, str) and bool(_SIR_DEGER.search(deger))


def _oku(yol: str) -> dict:
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _atomik_yaz(yol: str, veri: dict) -> None:
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=os.path.dirname(yol), prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(gecici, yol)
    except BaseException:
        try:
            os.remove(gecici)
        except OSError:
            pass
        raise


def makine_oku() -> dict:
    return _oku(makine_dosyasi())


def makine_taze_mi() -> bool:
    """Makine config'i var, şema sürümü bu kodunki ve parmak izi bu makineninki mi (hızlı yol: bir küçük dosya okuma)."""
    d = makine_oku()
    return bool(d) and d.get("surum") == SURUM and d.get("parmak") == parmak_izi()


def makine_yaz(degerler: dict[str, Any], kaynak: str = "kesif") -> str:
    """Değerleri makine config'ine birleştirir (var olanın üstüne yazar), parmak izini bu makineye çeker.
    Parmak izi değişmişse eski makineden kalan değerler atılır. Sır benzeri girdi ValueError verir. Dosya yolunu döner."""
    for ad, deger in degerler.items():
        if sir_mi(ad, deger):
            raise ValueError(f"config'e sır yazılmaz: {ad!r}")
    mevcut = makine_oku()
    ayni_makine = mevcut.get("surum") == SURUM and mevcut.get("parmak") == parmak_izi()
    eski = mevcut.get("degerler") if ayni_makine and isinstance(mevcut.get("degerler"), dict) else {}
    yeni = dict(eski)
    z = _simdi()
    for ad, deger in degerler.items():
        yeni[ad] = {"deger": deger, "kaynak": kaynak, "zaman": z}
    veri = {"surum": SURUM, "parmak": parmak_izi(),
            "olusturma": mevcut.get("olusturma") if ayni_makine and mevcut.get("olusturma") else z,
            "degerler": yeni}
    if ayni_makine and mevcut.get("son_doktor"):
        veri["son_doktor"] = mevcut["son_doktor"]
    yol = makine_dosyasi()
    _atomik_yaz(yol, veri)
    return yol


def _katman_degeri(d: dict, ad: str) -> Any:
    v = (d.get("degerler") or {}).get(ad)
    if isinstance(v, dict):
        return v.get("deger")
    return v


def kaynakli_al(ad: str, proje: str | None = None, varsayilan: Any = None) -> tuple[Any, str]:
    """(değer, kaynak): kaynak ortam | proje | makine | kesif | varsayilan | yok."""
    gecerli = DOGRULA.get(ad, lambda v: True)
    ev = ORTAM.get(ad)
    if ev:
        o = (os.environ.get(ev) or "").strip()
        if o and gecerli(o):
            return o, "ortam"
    if proje:
        v = _katman_degeri(_oku(proje_dosyasi(proje)), ad)
        if v not in (None, "") and gecerli(v):
            return v, "proje"
    if makine_taze_mi():
        v = _katman_degeri(makine_oku(), ad)
        if v not in (None, "") and gecerli(v):
            return v, "makine"
    kesif = KESIF.get(ad)
    if kesif:
        try:
            v = kesif()
        except Exception:
            v = None
        if v not in (None, "") and gecerli(v):
            return v, "kesif"
    if varsayilan is not None:
        return varsayilan, "varsayilan"
    return None, "yok"


def al(ad: str, proje: str | None = None, varsayilan: Any = None) -> Any:
    """Config değerinin tek erişim noktası; öncelik için modül başlığına bak."""
    return kaynakli_al(ad, proje, varsayilan)[0]


def panel_port(proje: str | None = None) -> int:
    """Panel portu: config > PANEL_PORT_VARSAYILAN (geçersiz değer varsayılana düşer)."""
    try:
        p = int(al("panel_port", proje, PANEL_PORT_VARSAYILAN))
        return p if 0 < p < 65536 else PANEL_PORT_VARSAYILAN
    except (TypeError, ValueError):
        return PANEL_PORT_VARSAYILAN


def eklenti_koku() -> str:
    """Eklentinin kök klasörü (bu dosya <kök>/scripts/ altındadır)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def eklenti_surumu() -> str:
    """plugin.json `version` > önbellek klasör adı (…/orkestra/<sürüm>) > git kısa özet > '?'. plugin.json'da sürüm alanı yoktur."""
    kok = eklenti_koku()
    try:
        with open(os.path.join(kok, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            v = json.load(f).get("version")
        if v:
            return str(v)
    except (OSError, ValueError):
        pass
    ust, ad = os.path.split(kok)
    if os.path.basename(ust) == "orkestra" and ad != "orkestra":
        return ad
    try:
        r = subprocess.run(["git", "-C", kok, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, **PENCERESIZ)
        if r.returncode == 0 and r.stdout.strip():
            return "git-" + r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "?"


def hizli_surum() -> str | None:
    """eklenti_surumu() ile aynı zincir, git çağrısı olmadan (SessionStart hızlı yolu için); bulunamazsa None."""
    kok = eklenti_koku()
    try:
        with open(os.path.join(kok, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            v = json.load(f).get("version")
        if v:
            return str(v)
    except (OSError, ValueError):
        pass
    ust, ad = os.path.split(kok)
    return ad if os.path.basename(ust) == "orkestra" and ad != "orkestra" else None


def doktor_gerekli() -> str | None:
    """SessionStart hızlı yolu: doktor koşmalı mı? Neden metnini ya da None döner. Tek küçük dosya okuma, alt süreç yok.
    Nedenler: config yok · parmak izi (makine değişti) · doktor yok (hiç koşmamış) · sürüm (eklenti güncellendi; sürüm bilinmiyorsa sayılmaz)."""
    d = makine_oku()
    if not d or d.get("surum") != SURUM:
        return "config yok"
    if d.get("parmak") != parmak_izi():
        return "parmak izi"
    son = d.get("son_doktor")
    if not isinstance(son, dict):
        return "doktor yok"
    v = hizli_surum()
    if v and son.get("surum") != v:
        return "sürüm"
    return None


# Arka plan süreçleri için Windows oluşturma bayrağı: CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW. DETACHED_PROCESS EKLENMEZ:
# DETACHED_PROCESS konsolsuz süreç doğurur ve CREATE_NO_WINDOW'u yok sayar; konsolsuz sürecin başlattığı her konsol programı
# (git, py, python) varsayılan terminal uygulamasında yeni bir Terminal penceresi açar. NO_WINDOW tek başına gizli konsol verir, alt süreçler onu devralır.
ARKA_PLAN_BAYRAK = 0x00000200 | 0x08000000 if os.name == "nt" else 0
# Eklentinin başlattığı her alt süreç (subprocess.run/Popen/check_*) `**cfg.PENCERESIZ` taşır: konsolsuz bir süreçten (hook, panel)
# çağrılan konsol programı Windows'ta yeni pencere açar. tests/test_pencerisiz_subprocess.py bayraksız çağrıyı reddeder.
PENCERESIZ = {"creationflags": 0x08000000} if os.name == "nt" else {}

DOKTOR_ARA = 3600  # sn: başarısız ya da yazamayan doktor her oturumda yeniden başlamasın


def doktor_baslat(proje: str | None = None) -> bool:
    """Doktoru (yalnız A sınıfı onarım: --duzelt, --evet yok) ayrı süreçte başlatır; son denemeden DOKTOR_ARA sn geçmediyse başlatmaz.
    ORKESTRA_DOKTOR_OTOMATIK=0 ise hiç başlatmaz (test takımı ve CI gerçek makine config'ine dokunmasın)."""
    if (os.environ.get("ORKESTRA_DOKTOR_OTOMATIK") or "").strip() == "0":
        return False
    isaret = os.path.join(ev_dizini(), "doktor", ".deneme")
    try:
        if time.time() - os.path.getmtime(isaret) < DOKTOR_ARA:
            return False
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(isaret), exist_ok=True)
        with open(isaret, "w", encoding="utf-8") as f:
            f.write(_simdi() + "\n")
    except OSError:
        return False  # ev yazılamıyor: doktor da yazamaz
    args = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "doktor.py"), "--duzelt", "--arka-plan"]
    if proje:
        args += ["--proje", proje]
    try:
        subprocess.Popen(args, creationflags=ARKA_PLAN_BAYRAK, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
    except OSError:
        return False
    return True


def pazar_kaynagi(pazar: str = "claude-orchestration") -> str | None:
    """known_marketplaces.json'daki installLocation (kaynak depo klasörü)."""
    try:
        with open(os.path.join(os.path.expanduser("~"), ".claude", "plugins", "known_marketplaces.json"), encoding="utf-8") as f:
            yol = (json.load(f).get(pazar) or {}).get("installLocation")
        return yol if yol and os.path.isdir(yol) else None
    except Exception:
        return None


def makine_isaretle(son_doktor: dict) -> str:
    """Doktor çalışma özetini makine config'ine `son_doktor` olarak yazar (hızlı yol buna bakar); değerlere dokunmaz."""
    mevcut = makine_oku()
    ayni = mevcut.get("surum") == SURUM and mevcut.get("parmak") == parmak_izi()
    veri = {"surum": SURUM, "parmak": parmak_izi(),
            "olusturma": mevcut.get("olusturma") if ayni and mevcut.get("olusturma") else _simdi(),
            "degerler": mevcut.get("degerler") if ayni and isinstance(mevcut.get("degerler"), dict) else {},
            "son_doktor": son_doktor}
    yol = makine_dosyasi()
    _atomik_yaz(yol, veri)
    return yol


# ---------------------------------------------------------------- keşif işlevleri

def kesif_python() -> str:
    """`py -3.13` bulunursa onun yolu, yoksa bu sürecin yorumlayıcısı."""
    if shutil.which("py"):
        try:
            r = subprocess.run(["py", "-3.13", "-c", "import sys;print(sys.executable)"], capture_output=True,
                               text=True, timeout=20, **PENCERESIZ)
            yol = (r.stdout or "").strip().splitlines()
            if r.returncode == 0 and yol and os.path.isfile(yol[-1]):
                return yol[-1]
        except (OSError, subprocess.SubprocessError):
            pass
    return sys.executable


def claude_veri_kokleri() -> list[str]:
    """Claude masaüstü uygulamasının veri klasörü adayları (var olanlar, kesin sıra).

    Uygulama verisini sürümle yer değiştirir: `%APPDATA%\\Claude`, `%LOCALAPPDATA%\\Claude`,
    `%LOCALAPPDATA%\\Claude-Data\\<kurulum>` (20.10.2026 sonrası bu makinede) ve MSIX
    `%LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\Claude`. Kayıt ya da exe arayan herkes bu listeyi kullanır."""
    adaylar: list[str] = []
    for ev in ("APPDATA", "LOCALAPPDATA"):
        kok = os.environ.get(ev, "")
        if not kok:
            continue
        adaylar.append(os.path.join(kok, "Claude"))
        adaylar += sorted(glob.glob(os.path.join(kok, "Claude-Data", "*")))
        adaylar += sorted(glob.glob(os.path.join(kok, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude")))
    gorulen: set[str] = set()
    return [a for a in adaylar if os.path.isdir(a) and not (a in gorulen or gorulen.add(a))]


def kesif_claude_exe() -> str | None:
    """%APPDATA%/%LOCALAPPDATA% altındaki en yeni claude.exe, sonra PATH'teki claude.
    Masaüstü uygulaması iki yerleşim kullanır: `Claude\\claude-code\\<sürüm>\\<özet>` ve
    `Claude-Data\\<kurulum>\\claude-code\\<sürüm>\\<özet>` (22.10.2026'da bu makinede). Paneli başlatan süreçte
    CLAUDE_CODE_EXECPATH olmadığından 'Şimdi uygula' yalnız keşfe güvenir; yeni yerleşim bilinmezse düğme
    'oturum açmamış' diye yanlış hata veriyordu."""
    adaylar: list[str] = []
    for kok in claude_veri_kokleri():
        adaylar += glob.glob(os.path.join(kok, "claude-code", "*", "*", "claude.exe"))
    adaylar = [a for a in adaylar if os.path.exists(a)]
    if adaylar:
        return max(adaylar, key=os.path.getmtime)
    return shutil.which("claude")


def kesif_bash() -> str | None:
    """PATH'teki bash (Windows system32 stub'ı hariç); yoksa git kurulumunun bash'i."""
    b = shutil.which("bash")
    if b and "system32" not in b.lower():
        return b
    adaylar: list[str] = []
    g = shutil.which("git")
    if g:  # <git>/cmd/git.exe ya da <git>/bin/git.exe -> <git>/bin/bash.exe
        kok = os.path.dirname(os.path.dirname(os.path.abspath(g)))
        adaylar += [os.path.join(kok, "bin", "bash.exe"), os.path.join(kok, "usr", "bin", "bash.exe")]
    for ev in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        kok = os.environ.get(ev)
        if kok:
            alt = os.path.join(kok, "Programs") if ev == "LOCALAPPDATA" else kok
            adaylar += [os.path.join(alt, "Git", "bin", "bash.exe"), os.path.join(alt, "Git", "usr", "bin", "bash.exe")]
    for a in adaylar:
        if os.path.isfile(a):
            return a
    return None


KESIF.update({"python": kesif_python, "claude_exe": kesif_claude_exe, "bash": kesif_bash})
