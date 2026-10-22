"""Otomatik compact devri (ADR-0036): PreCompact'ta modelsiz devir özeti yazılır, SessionStart (compact/resume) onu bağlama ekler.

Özet deterministiktir: bağlı iş ve açık todo maddeleri, son kullanıcı mesajları, dal ve son commit. Sır değeri taşımaz
(ork_lib.maskele). Dosya: <sd>/oturumlar/devir_<oturum>.md; her iki adım <sd>/oturumlar/devir_<oturum>.log'a bir satır yazar.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import cfg  # noqa: E402

import ork_lib as L

AZAMI_KARAKTER = 3500  # SessionStart bağlamı 10.000 karakterle sınırlı; özet ondan çok küçük kalır
SON_MESAJ = 6
MESAJ_KESME = 400
_ATLA = re.compile(r"^\s*(?:<system-reminder>|<task-notification>|<command-|Caveat:|\[Request interrupted)", re.I)


def _yol(sd: str, oturum, uzanti: str) -> str:
    return os.path.join(sd, "oturumlar", f"devir_{oturum}.{uzanti}")


def log_yaz(sd: str, oturum, olay: str, ayrinti: str = "") -> None:
    try:
        os.makedirs(os.path.join(sd, "oturumlar"), exist_ok=True)
        with open(_yol(sd, oturum, "log"), "a", encoding="utf-8") as f:
            f.write(f"{L.simdi()}\t{olay}\t{ayrinti}\n")
    except Exception:
        pass


def _metin(icerik) -> str:
    if isinstance(icerik, str):
        return icerik
    if isinstance(icerik, list):
        return " ".join(str(b.get("text") or "") for b in icerik if isinstance(b, dict) and b.get("type") == "text")
    return ""


def son_kullanici_mesajlari(transkript: str, adet: int = SON_MESAJ) -> list[str]:
    """Transkriptteki en son `adet` gerçek kullanıcı mesajı (araç sonucu, hook bağlamı ve sistem metni atlanır)."""
    sonuc: list[str] = []
    if not transkript or not os.path.isfile(transkript):
        return sonuc
    try:
        with open(transkript, encoding="utf-8", errors="replace") as f:
            for satir in f:
                try:
                    k = json.loads(satir)
                except ValueError:
                    continue
                if k.get("type") != "user" or k.get("isSidechain") or k.get("isMeta"):
                    continue
                m = _metin((k.get("message") or {}).get("content")).strip()
                if m and not _ATLA.match(m):
                    sonuc.append(re.sub(r"\s+", " ", m)[:MESAJ_KESME])
    except OSError:
        return []
    return sonuc[-adet:]


def _git(cwd: str, *arg: str) -> str:
    try:
        r = subprocess.run(["git", "-c", "safe.directory=*", "-C", cwd, *arg], capture_output=True, text=True,
                           encoding="utf-8", timeout=5, **cfg.PENCERESIZ)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _acik_todo(klasor: str) -> list[str]:
    try:
        with open(os.path.join(klasor, "todo.md"), encoding="utf-8") as f:
            return [s.strip()[:160] for s in f if s.lstrip().startswith("- [ ]")][:8]
    except OSError:
        return []


def uret(inp: dict, is_kaydi: dict | None) -> str:
    cwd = inp.get("cwd") or os.getcwd()
    satirlar = ["Devir özeti (compact öncesi otomatik yazıldı; kaynak değil, hatırlatmadır — şüphede dosyaya bak):", ""]
    if is_kaydi:
        satirlar.append(f"- **Bağlı iş:** {is_kaydi.get('id')} — {is_kaydi.get('baslik')}")
        todo = _acik_todo(str(is_kaydi.get("klasor") or ""))
        satirlar.append(f"- **Açık todo ({len(todo)} gösterildi):**" if todo else "- **Açık todo:** yok")
        satirlar += [f"  - {t}" for t in todo]
    else:
        satirlar.append("- **Bağlı iş:** yok")
    dal, son = _git(cwd, "branch", "--show-current"), _git(cwd, "log", "-1", "--format=%h %s")
    if dal or son:
        satirlar.append(f"- **Git:** dal {dal or '-'}, son commit {son[:100] or '-'}")
    mesajlar = son_kullanici_mesajlari(inp.get("transcript_path") or "")
    if mesajlar:
        satirlar.append("- **Son kullanıcı mesajları (eskiden yeniye):**")
        satirlar += [f"  - {m}" for m in mesajlar]
    return L.maskele("\n".join(satirlar))[:AZAMI_KARAKTER]


def yaz(sd: str, inp: dict, is_kaydi: dict | None) -> str:
    """PreCompact: özeti yazar, dosya yolunu döner (hata durumunda boş)."""
    oturum = inp.get("session_id")
    if not oturum:
        return ""
    try:
        metin = uret(inp, is_kaydi)
        os.makedirs(os.path.join(sd, "oturumlar"), exist_ok=True)
        with open(_yol(sd, oturum, "md"), "w", encoding="utf-8") as f:
            f.write(metin)
        log_yaz(sd, oturum, "PreCompact", f"tetik={inp.get('trigger') or '-'} bayt={len(metin)}")
        return _yol(sd, oturum, "md")
    except Exception as e:
        log_yaz(sd, oturum, "PreCompact-hata", f"{type(e).__name__}: {e}"[:200])
        return ""


def baglam(sd: str, inp: dict) -> str:
    """SessionStart (kaynak compact | resume): varsa özet metni; yoksa boş. Yüklenince log satırı yazılır."""
    if inp.get("source") not in ("compact", "resume"):
        return ""
    oturum = inp.get("session_id")
    try:
        with open(_yol(sd, oturum, "md"), encoding="utf-8") as f:
            metin = f.read()
    except OSError:
        log_yaz(sd, oturum, "SessionStart-ozet-yok", f"kaynak={inp.get('source')}")
        return ""
    log_yaz(sd, oturum, "SessionStart", f"kaynak={inp.get('source')} bayt={len(metin)}")
    return metin
