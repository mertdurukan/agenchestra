"""Yol bazlı gönderim kapısı (ADR-0012): yasak yollara dokunan commit hiçbir uzak depoya gitmez.

Yasak yollar `<git kökü>/.claude/orkestra/push_kapisi.json` içinde {"yollar": ["RNV", ...]} (ya da
ORKESTRA_PUSH_YASAK ortam değişkeni, virgüllü). `kur` .git/hooks/pre-push dosyasını yazar; var olan bir
pre-push `pre-push.onceki` adıyla saklanır ve kapıdan sonra çalıştırılır (zincir). Hook atlama bayrağı kullanılmaz.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

IZ = "# orkestra push-kapisi (ADR-0012)"
SIFIR = "0" * 40


class KapiHata(Exception):
    pass


def _git(kok: str, *arg: str) -> str:
    r = subprocess.run(["git", "-c", "safe.directory=*", "-C", kok, *arg], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise KapiHata(r.stderr.strip() or f"git {' '.join(arg)} başarısız")
    return r.stdout.strip()


def git_koku(dizin: str | None = None) -> str:
    return _git(dizin or os.getcwd(), "rev-parse", "--show-toplevel")


def ayar_yolu(kok: str) -> str:
    return os.path.join(kok, ".claude", "orkestra", "push_kapisi.json")


def yollar(kok: str) -> list[str]:
    env = os.environ.get("ORKESTRA_PUSH_YASAK", "").strip()
    if env:
        return [x.strip() for x in env.split(",") if x.strip()]
    try:
        with open(ayar_yolu(kok), encoding="utf-8-sig") as f:
            ham = json.load(f).get("yollar", [])
    except (OSError, ValueError):
        return []
    return [str(x).strip("/\\ ") for x in ham if str(x).strip("/\\ ")]


def yol_ekle(kok: str, yol: str) -> list[str]:
    mevcut = yollar(kok)
    if yol not in mevcut:
        mevcut.append(yol)
    p = ayar_yolu(kok)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"yollar": mevcut}, f, ensure_ascii=False, indent=2)
    return mevcut


def ihlaller(kok: str, uzak: str, girdi: str, yasak: list[str]) -> list[str]:
    """pre-push stdin satırları: '<yerel ref> <yerel sha> <uzak ref> <uzak sha>'. Her ihlal: 'ref:sha,...'."""
    bad: list[str] = []
    if not yasak:
        return bad
    for satir in girdi.splitlines():
        p = satir.split()
        if len(p) < 4 or p[1] == SIFIR:
            continue
        lref, lsha, _rref, rsha = p[:4]
        aralik = [lsha, "--not", f"--remotes={uzak}"] if rsha == SIFIR else [f"{rsha}..{lsha}"]
        try:
            cikti = _git(kok, "log", "--format=%h", "--max-count=5", *aralik, "--", *yasak)
        except KapiHata:
            continue
        if cikti:
            bad.append(f"{lref}:{cikti.replace(chr(10), ',')}")
    return bad


def kontrol(uzak: str, girdi: str, kok: str | None = None) -> int:
    kok = kok or git_koku()
    yasak = yollar(kok)
    bad = ihlaller(kok, uzak, girdi, yasak)
    if bad:
        print(f"GONDERIM ENGELLENDI: yasak yola ({', '.join(yasak)}) dokunan commit var ({' '.join(bad)}).", file=sys.stderr)
        print("Kural: orkestra push-kapisi (ADR-0012); kapı atlanmaz.", file=sys.stderr)
        return 1
    return 0


def _kanca(kok: str) -> str:
    return os.path.join(kok, ".git", "hooks", "pre-push")


def _hook_metni(py: str, betik: str, onceki: bool) -> str:
    zincir = '\nprintf "%s\\n" "$girdi" | "$(dirname "$0")/pre-push.onceki" "$@" || exit $?' if onceki else ""
    return (f'#!/bin/sh\n{IZ}\n'
            f'girdi=$(cat)\n'
            f'[ -f "{betik}" ] || {{ echo "push-kapisi betigi yok: {betik} (orkestra push-kapisi kur)" >&2; exit 1; }}\n'
            f'printf "%s\\n" "$girdi" | "{py}" -X utf8 "{betik}" push-kapisi kontrol "$@" || exit 1'
            f'{zincir}\nexit 0\n')


def kur(kok: str | None = None) -> list[str]:
    kok = kok or git_koku()
    k = _kanca(kok)
    os.makedirs(os.path.dirname(k), exist_ok=True)
    cikti: list[str] = []
    onceki = False
    if os.path.exists(k):
        with open(k, encoding="utf-8", errors="replace") as f:
            ilk = f.read()
        if IZ in ilk:
            cikti.append("kapı zaten kurulu; yeniden yazılıyor")
            onceki = os.path.exists(k + ".onceki")
        else:
            os.replace(k, k + ".onceki")
            onceki = True
            cikti.append(f"var olan pre-push saklandı: {k}.onceki (kapıdan sonra çalışır)")
    betik = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orkestra.py").replace("\\", "/")
    with open(k, "w", encoding="utf-8", newline="\n") as f:
        f.write(_hook_metni(sys.executable.replace("\\", "/"), betik, onceki))
    try:
        os.chmod(k, 0o755)
    except OSError:
        pass
    cikti.append(f"kapı kuruldu: {k}")
    if not yollar(kok):
        cikti.append("uyarı: yasak yol tanımlı değil; `orkestra push-kapisi yol ekle <YOL>` ile ekle")
    return cikti


def kaldir(kok: str | None = None) -> list[str]:
    kok = kok or git_koku()
    k = _kanca(kok)
    if not os.path.exists(k):
        return ["kurulu kapı yok"]
    with open(k, encoding="utf-8", errors="replace") as f:
        if IZ not in f.read():
            return ["pre-push bu kapıya ait değil; dokunulmadı"]
    os.remove(k)
    if os.path.exists(k + ".onceki"):
        os.replace(k + ".onceki", k)
        return ["kapı kaldırıldı; önceki pre-push geri konuldu"]
    return ["kapı kaldırıldı"]


def durum(kok: str | None = None) -> list[str]:
    kok = kok or git_koku()
    k = _kanca(kok)
    kurulu = False
    if os.path.exists(k):
        with open(k, encoding="utf-8", errors="replace") as f:
            kurulu = IZ in f.read()
    return [f"kapı: {'kurulu' if kurulu else 'kurulu değil'}", f"yasak yollar: {', '.join(yollar(kok)) or '-'}",
            f"zincirlenen önceki pre-push: {'var' if os.path.exists(k + '.onceki') else 'yok'}"]
