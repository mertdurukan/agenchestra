"""Yasak içerik kapısı: depo dışı gitignore'lu `<git kökü>/.claude/orkestra/push_kapisi.json` içindeki
`icerik_desenleri` (büyük/küçük harf duyarsız Python regex listesi) yazım anında ve push öncesi denetlenir.

Desenler depoda tutulmaz (desen listesi adları geri sokardı); yapılandırma yoksa kapı sessiz kalır.
ORKESTRA_ICERIK_YASAK ortam değişkeni (satır sonu ayrılmış regex) yapılandırmayı ezer.
"""
from __future__ import annotations

import json
import os
import re

AYAR_ADI = os.path.join(".claude", "orkestra", "push_kapisi.json")


def git_koku(yol: str) -> str | None:
    d = os.path.abspath(yol if os.path.isdir(yol) else os.path.dirname(yol))
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        ust = os.path.dirname(d)
        if ust == d:
            return None
        d = ust


def desenler(kok: str | None) -> list[re.Pattern]:
    ham: list[str] = []
    env = os.environ.get("ORKESTRA_ICERIK_YASAK", "")
    if env.strip():
        ham = [x for x in env.splitlines() if x.strip()]
    elif kok:
        try:
            with open(os.path.join(kok, AYAR_ADI), encoding="utf-8-sig") as f:
                ham = [str(x) for x in (json.load(f).get("icerik_desenleri") or [])]
        except (OSError, ValueError):
            ham = []
    derli = []
    for d in ham:
        try:
            derli.append(re.compile(d, re.IGNORECASE))
        except re.error:
            continue
    return derli


def eslesme(metin: str, derli: list[re.Pattern]) -> str | None:
    """İlk eşleşen satırı (kısaltılmış) döndürür; sır sızmasın diye yalnız satır numarası ve desen sırası yazılır."""
    for no, satir in enumerate(metin.splitlines(), 1):
        for i, d in enumerate(derli, 1):
            if d.search(satir):
                return f"satır {no}, desen #{i}"
    return None


def yazim_metni(arac: str, girdi: dict) -> str:
    if arac == "Write":
        return str(girdi.get("content") or "")
    if arac == "Edit":
        return str(girdi.get("new_string") or "")
    if arac == "MultiEdit":
        return "\n".join(str(e.get("new_string") or "") for e in (girdi.get("edits") or []) if isinstance(e, dict))
    return ""


def yazim_ihlali(arac: str, girdi: dict, tam_yol: str) -> str:
    """Yazılacak yeni metinde yasak desen varsa neden metni, yoksa ''. Yapılandırma yoksa ''."""
    kok = git_koku(tam_yol)
    derli = desenler(kok)
    if not derli:
        return ""
    yer = eslesme(yazim_metni(arac, girdi), derli)
    return f"yasak içerik deseni yazılıyor ({yer}); örnek veri nötr adlarla yazılır (AcmeRetail, demo-db) — push_kapisi.json icerik_desenleri" if yer else ""


def push_ihlalleri(kok: str, git_calistir, aralik: list[str]) -> list[str]:
    """Aralıktaki commit'lerin EKLEDİĞİ satırlarda yasak desen: ['sha: satır N, desen #i']. git_calistir(kok, *arg) -> str."""
    derli = desenler(kok)
    if not derli:
        return []
    sonuc: list[str] = []
    for sha in git_calistir(kok, "rev-list", "--max-count=200", *aralik).split():
        fark = git_calistir(kok, "show", "--format=", "-U0", "--no-color", sha)
        eklenen = "\n".join(s[1:] for s in fark.splitlines() if s.startswith("+") and not s.startswith("+++"))
        yer = eslesme(eklenen, derli)
        if yer:
            sonuc.append(f"{sha[:7]}: {yer}")
            if len(sonuc) >= 5:
                break
    return sonuc
