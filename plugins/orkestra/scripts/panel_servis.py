"""Orkestra panelini Windows Task Scheduler görevi olarak yönetir (ADR-0033).

`orkestra panel servis kur|kaldir|durum`: oturum açılışında paneli sabit portta başlatır, çökerse yeniden başlatır.
Yalnız Windows; ek yazılım ve yönetici hakkı gerekmez (kullanıcı düzeyi görev).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402
import ork_lib as L  # noqa: E402

GOREV = "Orkestra Panel"
PANEL_BETIGI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel.py")


def _nt_zorunlu() -> None:
    if os.name != "nt":
        raise SystemExit("panel servisi yalnız Windows'ta desteklenir (Task Scheduler)")


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, timeout=30, **cfg.PENCERESIZ)


def _pythonw() -> str:
    """Konsol penceresi açmaması için pythonw.exe (yoksa python.exe)."""
    yol = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return yol if os.path.isfile(yol) else sys.executable


def gorev_xml(port: int, python: str | None = None, betik: str | None = None, calisma_dizini: str | None = None) -> str:
    """Oturum açılışında başlayan görev tanımı. Süreç ölürse (kapatılma dahil) her dakika tekrarlayan zaman tetikleyicisi
    yeniden başlatır (oturum açılışı tetikleyicisinin tekrarı yalnız açılıştan sonra işler, ölçüldü); çalışırken IgnoreNew ikinci süreç açmaz. RestartOnFailure yalnız görev hatayla biterse işe yarar,
    sonlandırılan süreçte (ölçüldü, 22.10.2026) tek başına yeniden başlatmadı."""
    python = python or _pythonw()
    betik = betik or PANEL_BETIGI
    calisma_dizini = calisma_dizini or L.GENEL_DIZIN
    # Tetikleyici ve ana hesap açıkça bu kullanıcı: UserId olmadan oturum açılışı tetikleyicisi yönetici hakkı ister.
    kullanici = escape(f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\"))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Orkestra paneli (127.0.0.1:{port}); orkestra panel servis kaldir ile silinir.</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{kullanici}</UserId></LogonTrigger>
    <TimeTrigger><Repetition><Interval>PT1M</Interval></Repetition><StartBoundary>2026-01-01T00:00:00</StartBoundary><Enabled>true</Enabled></TimeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>{kullanici}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author"><Exec>
    <Command>{escape(python)}</Command>
    <Arguments>"{escape(betik)}" _kos {port}</Arguments>
    <WorkingDirectory>{escape(calisma_dizini)}</WorkingDirectory>
  </Exec></Actions>
</Task>
"""


def kurulu() -> bool:
    """Görev kayıtlı mı (Windows dışında ya da schtasks yoksa False)."""
    if os.name != "nt":
        return False
    try:
        return _schtasks("/Query", "/TN", GOREV).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _eski_paneli_durdur() -> None:
    """Servisten önce elle/hook ile başlatılmış paneli kapatır; yoksa görev portu bağlayamaz."""
    try:
        with open(os.path.join(L.GENEL_DIZIN, "panel.json"), encoding="utf-8") as f:
            eski = json.load(f)
        subprocess.run(["taskkill", "/PID", str(eski["pid"]), "/F"], capture_output=True, **cfg.PENCERESIZ)
    except Exception:  # noqa: BLE001
        pass


ISARET = os.path.join(L.GENEL_DIZIN, "panel_servis.json")


def _isaret_oku() -> dict:
    try:
        with open(ISARET, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _isaret_yaz(durum: str, **ek) -> None:
    """Otomatik kurulumun makine başına kaydı: kuruldu | kaldirildi (kullanıcı kaldırdı, yeniden kurulmaz) | hata."""
    try:
        L.atomik_yaz(ISARET, json.dumps({"durum": durum, "betik": PANEL_BETIGI, "zaman": L.simdi(), **ek}))
    except Exception:  # noqa: BLE001
        pass


def _gorev_betigi_guncel() -> bool:
    """Kayıtlı görev bu eklenti kopyasının panel.py'sini mi çalıştırıyor (eklenti güncellenince yol değişir)."""
    r = _schtasks("/Query", "/TN", GOREV, "/XML")
    return r.returncode == 0 and escape(PANEL_BETIGI) in (r.stdout or "")


def otomatik_kur() -> str | None:
    """SessionStart'ta çağrılır (ADR-0034): Windows'ta görev yoksa kurar, eklenti yolu değiştiyse yeniden kaydeder.
    Kullanıcı `servis kaldir` dediyse ya da ORKESTRA_PANEL_SERVIS=0 ise dokunmaz; hatada aynı yolla yeniden denemez."""
    if os.name != "nt" or os.environ.get("ORKESTRA_PANEL_SERVIS") == "0":
        return None
    m = _isaret_oku()
    if m.get("durum") == "kaldirildi":
        return None
    if m.get("durum") in ("kuruldu", "hata") and m.get("betik") == PANEL_BETIGI:
        return None
    try:
        if kurulu() and _gorev_betigi_guncel():
            _isaret_yaz("kuruldu")
            return None
        kur()
        return "kuruldu"
    except BaseException as e:  # noqa: BLE001  (kur() SystemExit ile hata bildirir)
        _isaret_yaz("hata", hata=str(e)[:200])
        return None


def kur(port: int | None = None) -> dict:
    _nt_zorunlu()
    port = port or cfg.panel_port()
    xml = gorev_xml(port)
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
        f.write(xml)
        yol = f.name
    try:
        r = _schtasks("/Create", "/TN", GOREV, "/XML", yol, "/F")
    finally:
        os.unlink(yol)
    if r.returncode != 0:
        raise SystemExit(f"görev kurulamadı: {(r.stderr or r.stdout).strip()}")
    _eski_paneli_durdur()
    _schtasks("/Run", "/TN", GOREV)
    _isaret_yaz("kuruldu", port=port)
    return {"kuruldu": True, "gorev": GOREV, "port": port}


def kaldir() -> dict:
    _nt_zorunlu()
    _schtasks("/End", "/TN", GOREV)
    r = _schtasks("/Delete", "/TN", GOREV, "/F")
    _isaret_yaz("kaldirildi")
    return {"kaldirildi": r.returncode == 0, "gorev": GOREV}


def yeniden_baslat() -> bool:
    """Çalışan görevi durdurup yeniden başlatır (sürüm güncellemesi için); kurulu değilse False."""
    if not kurulu():
        return False
    _schtasks("/End", "/TN", GOREV)
    return _schtasks("/Run", "/TN", GOREV).returncode == 0


def durum() -> dict:
    port = cfg.panel_port()
    ok = None
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/saglik", timeout=1.5) as r:
            ok = r.read().decode()
    except Exception:  # noqa: BLE001
        pass
    return {"kurulu": kurulu(), "gorev": GOREV, "port": port, "panel": ok}


def main(argv: list[str]) -> None:
    komut = argv[0] if argv else "durum"
    if komut == "kur":
        sonuc = kur(int(argv[1]) if len(argv) > 1 else None)
    elif komut == "kaldir":
        sonuc = kaldir()
    elif komut == "durum":
        sonuc = durum()
    else:
        raise SystemExit("kullanım: panel_servis.py kur [port] | kaldir | durum")
    print(json.dumps(sonuc, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
