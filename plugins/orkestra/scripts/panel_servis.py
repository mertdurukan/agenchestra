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
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, timeout=30)


def _pythonw() -> str:
    """Konsol penceresi açmaması için pythonw.exe (yoksa python.exe)."""
    yol = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return yol if os.path.isfile(yol) else sys.executable


def gorev_xml(port: int, python: str | None = None, betik: str | None = None, calisma_dizini: str | None = None) -> str:
    """Oturum açılışında başlayan, hata sonrası 1 dk aralıkla yeniden başlayan görev tanımı."""
    python = python or _pythonw()
    betik = betik or PANEL_BETIGI
    calisma_dizini = calisma_dizini or L.GENEL_DIZIN
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Orkestra paneli (127.0.0.1:{port}); orkestra panel servis kaldir ile silinir.</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
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
        subprocess.run(["taskkill", "/PID", str(eski["pid"]), "/F"], capture_output=True)
    except Exception:  # noqa: BLE001
        pass


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
    return {"kuruldu": True, "gorev": GOREV, "port": port}


def kaldir() -> dict:
    _nt_zorunlu()
    _schtasks("/End", "/TN", GOREV)
    r = _schtasks("/Delete", "/TN", GOREV, "/F")
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
