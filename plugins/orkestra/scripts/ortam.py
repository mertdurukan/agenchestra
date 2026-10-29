"""Codebase ortamı kurucusu (I-249, ADR-0001): manifest + kilitten, proje ve git dışında; model çağırmaz.

Python: `uv sync --locked` (uv.lock + uv kuruluysa), aksi halde `python -m venv` + `pip install -r requirements.txt` (ya da pyproject).
Node: `npm ci` (package-lock.json şart). Başarısız kurulum yarım ortamı siler. Kurulum `orkestra_ortam.json` damgasını yazar
(kilit özeti, araç); `dogrula` damgayı güncel kilitle karşılaştırır. Dış komut `runner` ile enjekte edilir (testte sahte).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402

DAMGA = "orkestra_ortam.json"


class OrtamHata(Exception):
    pass


def varsayilan_runner(komut, cwd, env):
    r = subprocess.run(komut, cwd=cwd, env=env, capture_output=True, text=True, **cfg.PENCERESIZ)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def kayitlar(kok: str, sd: str) -> dict[str, dict]:
    import harita as H
    return {r["id"].split(":", 1)[1]: r for r in H.oku(kok, sd, "ortamlar")}


def bul(kok: str, sd: str, ad: str) -> dict:
    """Codebase adı ya da göreli yoluyla kayıt; yoksa OrtamHata (bilinen adlar mesajda)."""
    k = kayitlar(kok, sd)
    for yol, r in k.items():
        if ad in (r["ad"], yol):
            return r
    raise OrtamHata(f"bilinmeyen codebase '{ad}'; bilinenler: {', '.join(sorted(r['ad'] for r in k.values())) or 'yok'}")


def kilit_ozeti(cb_dizin: str, kayit: dict) -> str:
    h = hashlib.sha256()
    for ad in [kayit["kilit_dosyasi"]] + [m for m in kayit["manifestler"] if m != kayit["kilit_dosyasi"]]:
        try:
            with open(os.path.join(cb_dizin, ad), "rb") as f:
                h.update(ad.encode() + f.read())
        except OSError:
            h.update(ad.encode() + b"|yok")
    return h.hexdigest()[:16]


def python_yolu(ortam_yolu: str) -> str:
    return os.path.join(ortam_yolu, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")


def _damga_yolu(kayit: dict) -> str:
    return os.path.join(kayit["ortam_yolu"], DAMGA if kayit["tur"] == "python" else ".orkestra_ortam.json")


def kur(kayit: dict, kok: str, runner=varsayilan_runner, uv_var=None, taban_python=None) -> dict:
    """Tek codebase ortamını kurar. Dönüş: {codebase, durum, arac, ortam_yolu}. Hatada ortam silinir, OrtamHata atılır."""
    cb = os.path.join(os.path.abspath(kok), kayit["yer"])
    yol, tur, kilit = kayit["ortam_yolu"], kayit["tur"], kayit["kilit_turu"]
    env = dict(os.environ)
    if uv_var is None:
        uv_var = shutil.which("uv") is not None
    adimlar: list[tuple[list[str], dict]] = []
    if tur == "python":
        if kilit == "uv" and uv_var:
            arac = "uv"
            adimlar.append((["uv", "sync", "--locked"], dict(env, UV_PROJECT_ENVIRONMENT=yol)))
        else:
            arac = "pip"
            py = taban_python or sys.executable
            adimlar.append(([py, "-m", "venv", yol], env))
            hedef = ["-r", "requirements.txt"] if os.path.isfile(os.path.join(cb, "requirements.txt")) else ["."]
            adimlar.append(([python_yolu(yol), "-m", "pip", "install", *hedef], env))
        os.makedirs(os.path.dirname(yol), exist_ok=True)
    else:
        if kilit != "npm-ci":
            raise OrtamHata(f"{kayit['ad']}: package-lock.json yok; kilitsiz Node ortamı kurulmaz")
        arac = "npm"
        adimlar.append((["npm", "ci"], env))
    for komut, e in adimlar:
        kod, cikti = runner(komut, cb, e)
        if kod != 0:
            shutil.rmtree(yol, ignore_errors=True)
            son = " | ".join((cikti or "").strip().splitlines()[-3:])
            raise OrtamHata(f"{kayit['ad']}: '{' '.join(komut[:3])}' kod {kod}: {son}")
    damga = {"codebase": kayit["ad"], "arac": arac, "kilit_turu": kilit, "kilit_ozeti": kilit_ozeti(cb, kayit),
             "tarih": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    os.makedirs(os.path.dirname(_damga_yolu(kayit)), exist_ok=True)
    with open(_damga_yolu(kayit), "w", encoding="utf-8") as f:
        json.dump(damga, f, ensure_ascii=False, indent=1)
    return {"codebase": kayit["ad"], "durum": "kuruldu", "arac": arac, "ortam_yolu": yol}


def dogrula(kayit: dict, kok: str) -> dict:
    """durum: yok (ortam/damga yok) | eski (kilit damgadan farklı) | guncel."""
    cb = os.path.join(os.path.abspath(kok), kayit["yer"])
    try:
        with open(_damga_yolu(kayit), encoding="utf-8") as f:
            damga = json.load(f)
    except (OSError, ValueError):
        return {"codebase": kayit["ad"], "durum": "yok"}
    if kayit["tur"] == "python" and not os.path.isfile(python_yolu(kayit["ortam_yolu"])):
        return {"codebase": kayit["ad"], "durum": "yok"}
    durum = "guncel" if damga.get("kilit_ozeti") == kilit_ozeti(cb, kayit) else "eski"
    return {"codebase": kayit["ad"], "durum": durum, "arac": damga.get("arac")}
