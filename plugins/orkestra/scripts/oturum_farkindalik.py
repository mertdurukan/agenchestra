"""Oturumlar arası çakışma farkındalığı (ADR-0122, I-308): oturum kaydına konum yazar, aynı depoda canlı komşuyu bulur.

Model çağırmaz, subprocess açmaz (git bilgisi `.git` dosyalarından okunur), hiçbir şeyi engellemez.
Kayıt: `oturumlar/<oturum>.json` içindeki `konum` alanı (depo, dal, worktree, son yazılan dosyalar, uyarılanlar).
Canlılık: dosya mtime'ı ve `konum.gorulme`; bakılacak dosya sayısı mtime süzgeciyle birkaça iner.
Kapatma: ORKESTRA_OTURUM_FARKINDALIK=0. Mod: `ayarlar/oturum_farkindalik.json` (golge, P-028).
"""
from __future__ import annotations

import json
import os
import re
import time

import ork_lib as L

KAPI = "oturum_farkindalik"
CANLI_S = 30 * 60
YAZILAN_EN_COK = 50
YENILE_S = 60
UYARILAN_EN_COK = 40
_GIT_YAZAN = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?(merge|rebase|reset|checkout|switch|cherry-pick|pull|push|stash|"
    r"branch\s+-[dDmM]|worktree\s+(?:remove|prune|move)|update-ref|commit\s+--amend)\b")


def etkin() -> bool:
    return os.environ.get("ORKESTRA_OTURUM_FARKINDALIK") != "0"


def _norm(yol: str) -> str:
    return os.path.normcase(os.path.abspath(yol)).replace("\\", "/")


def git_konumu(cwd: str | None) -> dict | None:
    """{depo, dal, worktree, ana}: `.git` dosyalarından (subprocess yok). Git deposu değilse None."""
    if not cwd:
        return None
    d = os.path.abspath(cwd)
    while True:
        g = os.path.join(d, ".git")
        if os.path.exists(g):
            break
        ust = os.path.dirname(d)
        if ust == d:
            return None
        d = ust
    try:
        if os.path.isdir(g):
            gitdir, ortak = g, g
        else:
            with open(g, encoding="utf-8", errors="replace") as f:
                ilk = f.readline().strip()
            if not ilk.startswith("gitdir:"):
                return None
            gitdir = ilk[7:].strip()
            if not os.path.isabs(gitdir):
                gitdir = os.path.join(d, gitdir)
            ortak = gitdir
            try:
                with open(os.path.join(gitdir, "commondir"), encoding="utf-8") as f:
                    ortak = os.path.join(gitdir, f.readline().strip())
            except OSError:
                pass
        with open(os.path.join(gitdir, "HEAD"), encoding="utf-8", errors="replace") as f:
            head = f.readline().strip()
    except OSError:
        return None
    dal = head[16:] if head.startswith("ref: refs/heads/") else "(ayrık " + head[:7] + ")"
    ortak = os.path.normpath(ortak)
    return {"depo": _norm(ortak), "dal": dal, "worktree": _norm(d), "ana": _norm(os.path.dirname(ortak)) == _norm(d)}


def kaydet(sd: str, oturum: str, cwd: str | None, dosya: str | None = None, is_id: str | None = None,
           simdi: float | None = None) -> bool:
    """Oturum kaydının `konum` alanını yeniler. Değişiklik yoksa ve son yazım 60 sn içindeyse dosyaya dokunmaz (ucuz yol).
    Hata durumunda False (istisna fırlatmaz)."""
    if not (etkin() and sd and oturum):
        return False
    try:
        t = time.time() if simdi is None else simdi
        yol = L._oturum_json_yol(sd, oturum)
        konum = git_konumu(cwd)
        if not konum:
            return False
        dosya_n = _norm(dosya) if dosya else None
        with L.kilit(yol):
            durum, kayit = L._oturum_json_oku(yol)
            if durum == "bozuk":
                return False
            eski = kayit.get("konum") if isinstance(kayit.get("konum"), dict) else {}
            yazilan = [x for x in (eski.get("yazilan") or []) if isinstance(x, str)]
            yeni_dosya = bool(dosya_n) and dosya_n not in yazilan
            if yeni_dosya:
                yazilan = (yazilan + [dosya_n])[-YAZILAN_EN_COK:]
            degisti = (yeni_dosya or eski.get("dal") != konum["dal"] or eski.get("depo") != konum["depo"]
                       or eski.get("worktree") != konum["worktree"] or (is_id and eski.get("is") != is_id))
            if not degisti and t - float(eski.get("gorulme") or 0) < YENILE_S:
                return True
            kayit["konum"] = {**eski, **konum, "yazilan": yazilan, "gorulme": t,
                              "is": is_id or eski.get("is") or kayit.get("is")}
            L.atomik_yaz(yol, json.dumps(kayit, ensure_ascii=False))
        return True
    except Exception:
        return False


def komsular(sd: str, oturum: str, cwd: str | None, dosya: str | None = None, esik_s: float = CANLI_S,
             simdi: float | None = None, git_islemi: bool = False) -> list[dict]:
    """Aynı depoda canlı başka oturumlar. Neden: dosya (aynı yazılan dosya), dal (aynı dal), worktree (aynı çalışma ağacı),
    yuzey (iki taraftan biri ana ağaçta/`main`'de) ya da depo (yalnız `git_islemi` iken: dal/ağaç değiştiren git komutu).
    Dosya > dal > worktree > yuzey > depo sırasıyla en güçlü neden seçilir; güçlüler önce gelir."""
    if not (etkin() and sd and oturum):
        return []
    konum = git_konumu(cwd)
    if not konum:
        return []
    t = time.time() if simdi is None else simdi
    dosya_n = _norm(dosya) if dosya else None
    klasor = os.path.join(sd, "oturumlar")
    sonuc = []
    try:
        girdiler = list(os.scandir(klasor))
    except OSError:
        return []
    for e in girdiler:
        ad = e.name
        if not ad.endswith(".json") or ".baglanti" in ad or ad.startswith("acik_ajan_") or ad[:-5] == oturum:
            continue
        try:
            if t - e.stat().st_mtime > esik_s:
                continue
            with open(e.path, encoding="utf-8") as f:
                kayit = json.load(f)
        except (OSError, ValueError):
            continue
        k = kayit.get("konum") if isinstance(kayit, dict) else None
        if not isinstance(k, dict) or k.get("depo") != konum["depo"] or t - float(k.get("gorulme") or 0) > esik_s:
            continue
        if dosya_n and dosya_n in (k.get("yazilan") or []):
            neden = "dosya"
        elif k.get("dal") == konum["dal"]:
            neden = "dal"
        elif k.get("worktree") == konum["worktree"]:
            neden = "worktree"
        elif konum["ana"] or k.get("ana") or konum["dal"] == "main" or k.get("dal") == "main":
            neden = "yuzey"
        elif git_islemi:
            neden = "depo"
        else:
            continue
        sonuc.append({"oturum": ad[:-5], "neden": neden, "dal": k.get("dal"), "is": k.get("is"),
                      "dk": int((t - float(k.get("gorulme") or 0)) // 60)})
    sira = {"dosya": 0, "dal": 1, "worktree": 2, "yuzey": 3, "depo": 4}
    return sorted(sonuc, key=lambda x: (sira[x["neden"]], x["dk"]))


def git_yazan_komut(komut: str | None) -> bool:
    return bool(komut and _GIT_YAZAN.search(komut))


def satir(komsu_listesi: list[dict], ek: str = "") -> str:
    """Tek kısa bağlam satırı (≤250 karakter). Boş listede boş metin: çakışmasız durumda ek bağlam 0 karakter."""
    if not komsu_listesi:
        return ""
    k = komsu_listesi[0]
    etiket = {"dosya": "aynı dosyayı yazıyor", "dal": "aynı dalda", "worktree": "aynı çalışma ağacında",
              "yuzey": "ortak yüzeyde (ana ağaç/main)", "depo": "aynı depoda"}[k["neden"]]
    ek_say = f" (+{len(komsu_listesi) - 1} oturum)" if len(komsu_listesi) > 1 else ""
    is_ = f", iş {k['is']}" if k.get("is") else ""
    s = (f"Eş zamanlı oturum {k['oturum'][:8]} {etiket}{ek_say}: dal {k['dal']}{is_}, {k['dk']} dk önce. "
         f"{ek}Akışı bozma; gerekirse `orkestra oturum not {k['oturum'][:8]} \"...\"`.")
    return s[:250]


def uyar_bir_kez(sd: str, oturum: str, anahtar: str) -> bool:
    """Oturum başına aynı uyarı en çok bir kez: anahtar yeniyse kaydeder ve True döner."""
    try:
        yol = L._oturum_json_yol(sd, oturum)
        with L.kilit(yol):
            durum, kayit = L._oturum_json_oku(yol)
            if durum == "bozuk":
                return False
            k = kayit.get("konum") if isinstance(kayit.get("konum"), dict) else {}
            u = [x for x in (k.get("uyarilan") or []) if isinstance(x, str)]
            if anahtar in u:
                return False
            k["uyarilan"] = (u + [anahtar])[-UYARILAN_EN_COK:]
            kayit["konum"] = k
            L.atomik_yaz(yol, json.dumps(kayit, ensure_ascii=False))
        return True
    except Exception:
        return False


def golge_yaz(sd: str, oturum: str, komsu: dict, dosya: str | None, olay: str) -> None:
    """Tespiti gunluk.jsonl'a `kapi_golge` olarak yazar (ölçüm: orkestra is rapor)."""
    try:
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"),
                     {"zaman": L.simdi(), "tur": "kapi_golge", "kapi": KAPI, "olay": olay, "oturum": oturum[:8],
                      "komsu": komsu["oturum"][:8], "neden": komsu["neden"], "dosya": bool(dosya)})
    except Exception:
        pass
