"""Komutu codebase ortamından koşturur (I-249, ADR-0001): yorumlayıcıyı ortamdan çözer, çalışma dizini codebase'dir.

Python'da komutun ilk sözcüğü `python`/`python3` ise ortamın python'u + `-I -X utf8` ile değiştirilir; ortamın Scripts/bin klasörü PATH başına
eklenir (pytest vb.). Node'da `node_modules/.bin` PATH başına eklenir. `kimlik` verilirse koşu `orkestra kimlik` üzerinden gider
(değerler maskelenir). Ortam kurulu değilse (damga yok) koşu reddedilir; kurmak için `orkestra ortam kur`.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402
import ortam as O  # noqa: E402

PYTHON_ADLARI = ("python", "python3", "python.exe")


def hazirla(kayit: dict, kok: str, komut: list[str]) -> tuple[list[str], str, dict[str, str]]:
    """(komut, cwd, env_ek). Ortam kurulu değilse OrtamHata."""
    d = O.dogrula(kayit, kok)
    if d["durum"] == "yok":
        raise O.OrtamHata(f"{kayit['ad']}: ortam kurulu değil; önce `orkestra ortam kur {kayit['ad']}`")
    if not komut:
        raise O.OrtamHata("çalıştırılacak komut yok")
    cwd = os.path.join(os.path.abspath(kok), kayit["dizin"])
    yol = kayit["ortam_yolu"]
    bin_dizin = os.path.dirname(O.python_yolu(yol)) if kayit["tur"] == "python" else os.path.join(yol, ".bin")
    yeni = list(komut)
    if kayit["tur"] == "python" and os.path.basename(yeni[0]).lower() in PYTHON_ADLARI:
        yeni[0:1] = [O.python_yolu(yol)] + ([] if "-I" in yeni[1:2] else ["-I", "-X", "utf8"])  # -I, PYTHONUTF8 ortam değişkenini yok sayar
    path = bin_dizin + os.pathsep + os.environ.get("PATH", "")
    return yeni, cwd, {"PATH": path, "VIRTUAL_ENV": yol} if kayit["tur"] == "python" else {"PATH": path}


def calistir(kayit: dict, kok: str, komut: list[str], kimlik: str | None = None, proje: str | None = None) -> int:
    yeni, cwd, env_ek = hazirla(kayit, kok, komut)
    if kimlik:
        import kimlik as K
        return K.calistir(kimlik, yeni, proje, cwd=cwd, env_ek=env_ek)
    env = dict(os.environ)
    env.update(env_ek)
    # PENCERESIZ (CREATE_NO_WINDOW) çocuğa konsol vermez: çıktı yakalanıp bu sürecin akışlarına aktarılır.
    r = subprocess.run(yeni, cwd=cwd, env=env, capture_output=True, **cfg.PENCERESIZ)
    sys.stdout.buffer.write(r.stdout)
    sys.stderr.buffer.write(r.stderr)
    return r.returncode
