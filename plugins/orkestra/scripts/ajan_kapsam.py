"""Ajan türüne göre araç kapsamı (I-292 P3, ADR-0110).

Plugin ajanlarında `hooks`/`permissionMode` yok sayıldığından kısıt PreToolUse hook'unda uygulanır (hook.py).
Saf işlev `karar(...)`: (ajan türü, araç, girdi) -> ret nedeni ya da None. Ayar: ayarlar/ajan_kapsam.json.
Kabuk kısıtı deny-list'tir: yazan komutları yakalar, script dosyasının içini denetlemez.
"""
from __future__ import annotations

import json
import os
import re

AYAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "ajan_kapsam.json")
KABUK = ("Bash", "PowerShell")
YAZMA_ARACLARI = ("Write", "Edit", "MultiEdit", "NotebookEdit")
BOS_HEDEF = {"&1", "&2", "/dev/null", "$null", "nul"}
YAZAN_KOMUT = {
    "tee", "rm", "rmdir", "mv", "cp", "mkdir", "touch", "chmod", "chown", "ln", "truncate", "dd", "install",
    "set-content", "add-content", "out-file", "new-item", "remove-item", "move-item", "copy-item", "rename-item",
    "clear-content", "set-itemproperty", "del", "erase", "ren", "move", "copy", "md", "ni", "sc", "ac",
}
GIT_YAZAN = {"add", "commit", "push", "checkout", "switch", "reset", "merge", "rebase", "stash", "apply", "am",
             "clean", "rm", "mv", "restore", "cherry-pick", "revert", "tag", "pull", "fetch", "init", "clone"}
SQL_YAZAN = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE\s+[\w\".]+\s+SET|DELETE\s+FROM|DROP\s+(?:TABLE|SCHEMA|INDEX|DATABASE|VIEW)|"
    r"ALTER\s+(?:TABLE|SCHEMA|INDEX|DATABASE)|TRUNCATE|CREATE\s+(?:TABLE|INDEX|SCHEMA|DATABASE|VIEW)|"
    r"GRANT\s|REVOKE\s|COPY\s+\S+\s+FROM)\b", re.I)
SQL_BAGLAM = re.compile(r"psql|execute|cursor|read_sql|db\.py|postgres|sqlalchemy|\.query\(|pg_dump", re.I)
YORUMLAYICI = {"python", "python3", "py", "node", "powershell", "pwsh", "bash", "sh", "perl", "ruby"}
KOD_YAZIMI = re.compile(
    r"open\([^)]*['\"][wax]\+?b?['\"]|\.write_text|\.write_bytes|\.write\(|os\.remove|os\.unlink|shutil\.|rmtree|"
    r"\.unlink\(|to_csv|to_excel|\.mkdir|os\.makedirs|Set-Content|Add-Content|Out-File|Remove-Item|New-Item|"
    r"fs\.write|fs\.unlink|writeFile", re.I)
_TIRNAK = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')
_AYIR = re.compile(r"&&|\|\||[;|\n]|(?<![>&\d])&(?!>)")
_YONLENDIR = re.compile(r"(\d*)(>>?|&>>?)\s*(\S*)")


def ayar_yukle() -> dict:
    try:
        with open(AYAR, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def tur_adi(agent_type) -> str:
    return str(agent_type or "").split(":")[-1]


def mod_bul(cfg: dict) -> str:
    if os.environ.get("ORKESTRA_AJAN_KAPSAM") == "0":
        return "kapali"
    m = str(cfg.get("mod") or "ihlal")
    return m if m in ("ihlal", "golge", "kapali") else "ihlal"


def _norm(yol: str, proje: str = ".") -> str:
    if not os.path.isabs(yol):
        yol = os.path.join(proje, yol)
    return os.path.normcase(os.path.abspath(yol)).replace("\\", "/")


def _git_alt_komut(s: list) -> str:
    """git'in alt komutu: seçenekler (-C yol, -c k=v, --git-dir=...) atlanarak ilk sözcük."""
    i = 0
    while i < len(s):
        if s[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
        elif s[i].startswith("-"):
            i += 1
        else:
            return s[i]
    return ""


def kabuk_yazimi(komut: str):
    """Komut dosya/depo/veritabanı yazıyorsa nedeni, yoksa None."""
    komut = komut or ""
    if SQL_BAGLAM.search(komut):
        m = SQL_YAZAN.search(komut)
        if m:
            return f"SQL yazma ({m.group(0).split()[0].upper()})"
    kuru = _TIRNAK.sub('""', komut)
    for h in _YONLENDIR.finditer(kuru):
        t = h.group(3).strip('"')
        if t and t not in BOS_HEDEF and not t.startswith(("=", "&")):
            return f"yönlendirme ({h.group(0).strip()})"
    for parca in _AYIR.split(kuru):
        sozcuk = parca.strip().replace("(", " ").split()
        while sozcuk and (re.fullmatch(r"\w+=\S*", sozcuk[0]) or sozcuk[0] in ("sudo", "env", "time")):
            sozcuk = sozcuk[1:]
        if not sozcuk:
            continue
        bas = re.sub(r"\.exe$", "", os.path.basename(sozcuk[0].strip('"')).lower())
        if bas in YAZAN_KOMUT:
            return f"yazan komut ({bas})"
        if bas == "git" and _git_alt_komut(sozcuk[1:]) in GIT_YAZAN:
            return "git yazma"
        if bas in ("sed", "perl") and any(re.fullmatch(r"-[a-zA-Z]*i\S*", s) for s in sozcuk[1:]):
            return f"{bas} -i (yerinde düzenleme)"
        if bas in ("pip", "pip3", "npm", "pnpm", "yarn") and any(s in ("install", "i", "add", "uninstall") for s in sozcuk[1:3]):
            return "paket kurulumu"
        if bas in YORUMLAYICI and KOD_YAZIMI.search(komut):
            return "satır içi kodla dosya yazımı"
    if re.search(r"(?:xargs|-exec)\s+(?:rm|mv|cp|tee|sed\s+-i)\b", kuru):
        return "xargs/-exec ile yazan komut"
    return None


def karar(agent_type, arac: str, girdi, cfg=None, proje: str = ".", kart_ciktilari=None):
    """Ret nedeni (str) ya da None. `kart_ciktilari`: denetçinin bağlı kartının ciktilar listesi."""
    cfg = cfg if cfg is not None else ayar_yukle()
    if mod_bul(cfg) == "kapali":
        return None
    tur = tur_adi(agent_type)
    girdi = girdi or {}
    if arac in KABUK and tur in (cfg.get("salt_okuma_ajanlari") or []):
        n = kabuk_yazimi(str(girdi.get("command") or ""))
        if n:
            return f"{tur} salt okuma ajanıdır: {n} yapılamaz (ayarlar/ajan_kapsam.json)."
    if arac in YAZMA_ARACLARI:
        yol = str(girdi.get("file_path") or girdi.get("notebook_path") or "")
        yollar = (cfg.get("yazma_yollari") or {}).get(tur)
        if yollar is not None and not any(re.search(d, _norm(yol, proje), re.I) for d in yollar):
            return f"{tur} yalnız kendi çıktı yoluna yazar; '{yol}' izinli değil (ayarlar/ajan_kapsam.json)."
        if tur in (cfg.get("kart_ciktisi_ajanlari") or []):
            izinli = {_norm(c, proje) for c in (kart_ciktilari or [])}
            if _norm(yol, proje) not in izinli:
                return f"{tur} yalnız bağlı kartın çıktı dosyalarını düzeltir; '{yol}' kart çıktısı değil."
    return None
