"""Git denetimi: dal, stash ve gönderilmemiş iş görünürlüğü (I-325; ADR-0050 tek main).

Salt okunur: hiçbir dal, stash ya da uzak kayıt değiştirilmez, silinmez, gönderilmez.
`dal_temizle` yalnız yerel birleşmiş dalları siler; burası ona bakmayan yeri gösterir:
uzakta birleşmiş artık dallar, uzakta kopyası olmayan (tek kopya) commit'ler, stash ve commitsiz dosya sayısı.
Hiçbir çağrı istisna fırlatmaz.
"""
from __future__ import annotations

import subprocess

import cfg

ANA = "main"
UZAK = "origin"


def _git(depo: str, *a: str) -> str:
    r = subprocess.run(["git", "-C", depo, *a], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, **cfg.PENCERESIZ)
    return r.stdout if r.returncode == 0 else ""


def _sayi(depo: str, *a: str) -> int:
    try:
        return int(_git(depo, *a).strip() or 0)
    except ValueError:
        return 0


def tara(depo: str) -> dict:
    """{yerel: [{ad, durum, adet}], uzak: [{ad, durum, adet}], stash, commitsiz}.

    Yerel durum: `uzakta` (tüm commit'ler bir uzak dalda), `gonderilmemis` (aynı adlı uzak dal var, önde),
    `yedeksiz` (aynı adlı uzak dal yok; commit'ler tek kopya). Adet: hiçbir uzak dalda olmayan commit sayısı.
    Uzak durum: `birlesmis` (origin/main'de tamamen var, silinebilir) ya da `benzersiz` (main'de olmayan commit var; adet)."""
    sonuc = {"yerel": [], "uzak": [], "stash": 0, "commitsiz": 0}
    try:
        uzaklar = set(_git(depo, "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{UZAK}").split())
        for ad in _git(depo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split():
            adet = _sayi(depo, "rev-list", "--count", ad, "--not", "--remotes")
            durum = "uzakta" if adet == 0 else ("gonderilmemis" if f"{UZAK}/{ad}" in uzaklar else "yedeksiz")
            sonuc["yerel"].append({"ad": ad, "durum": durum, "adet": adet})
        ana = f"{UZAK}/{ANA}"
        for ad in sorted(uzaklar):
            if ad in (ana, UZAK, f"{UZAK}/HEAD"):
                continue
            adet = _sayi(depo, "rev-list", "--count", f"{ana}..{ad}")
            sonuc["uzak"].append({"ad": ad, "durum": "birlesmis" if adet == 0 else "benzersiz", "adet": adet})
        sonuc["stash"] = len(_git(depo, "stash", "list").splitlines())
        sonuc["commitsiz"] = len(_git(depo, "status", "--porcelain").splitlines())
    except Exception:
        pass
    return sonuc


def uyari(depo: str) -> str:
    """Uzakta tek kopyası olmayan ya da önde kalan yerel dallar için tek satır; yoksa ''."""
    try:
        riskli = [d for d in tara(depo)["yerel"] if d["durum"] != "uzakta"]
    except Exception:
        return ""
    if not riskli:
        return ""
    parca = ", ".join(f"{d['ad']} ({d['adet']} commit, {'uzakta kopyası yok' if d['durum'] == 'yedeksiz' else 'uzağın önünde'})" for d in riskli[:5])
    return f"gönderilmemiş commit'li dal: {parca}; kaybolmaması için origin'e gönderilmeli."


def rapor(depo: str) -> str:
    t = tara(depo)
    s = [f"yerel dal: {len(t['yerel'])} · uzak dal (main hariç): {len(t['uzak'])} · stash: {t['stash']} · commitsiz dosya: {t['commitsiz']}"]
    for d in t["yerel"]:
        if d["durum"] != "uzakta":
            s.append(f"- yerel {d['ad']}: {d['durum']} ({d['adet']} commit)")
    bir = [d["ad"] for d in t["uzak"] if d["durum"] == "birlesmis"]
    ben = [f"{d['ad']} ({d['adet']})" for d in t["uzak"] if d["durum"] == "benzersiz"]
    s.append(f"- uzakta birleşmiş (silinebilir): {len(bir)}" + (f" — {', '.join(bir)}" if bir else ""))
    s.append(f"- uzakta main'de olmayan commit'li: {len(ben)}" + (f" — {', '.join(ben)}" if ben else ""))
    return "\n".join(s)
