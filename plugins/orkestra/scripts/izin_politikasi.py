#!/usr/bin/env python3
"""Orkestra izin politikası: halka açık ve geri alınamaz eylemler dışında onaysız çalışma.

  izin_politikasi.py goster [--sd DIR]
  izin_politikasi.py sina --arac ARAC [--komut KOMUT] [--sd DIR]

Karar (PreToolUse hook'u kullanır): deny | ask | allow | None.
  deny   force/silme/ayna push.
  ask    git push, gh ile yazma, GitHub/Jira REST'ine yazan curl, GitHub ve Jira MCP yazma araçları.
  allow  kapı dışındaki her araç (yalnız mod=genis). Kullanıcının settings deny/ask kuralları hook allow'una rağmen geçerlidir.
  None   karar yok (mod=kapi'de kapı dışı; mod=kapali).
Mod: ayarlar/izin_politikasi.json; proje ezmesi <sd>/izin_politikasi.json (üst düzey alanlar); ORKESTRA_IZIN=0|kapi|genis modu ezer.
Desenler en iyi çabadır: betik içinden API çağrısı yakalanmaz. MCP'de okuma deseni dışındaki her araç kapıya düşer (güvenli varsayılan).
"""
from __future__ import annotations

import argparse
import copy
import functools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

AYAR_DOSYASI = os.path.join(L.PLUGIN_ROOT, "ayarlar", "izin_politikasi.json")
EZME_AD = "izin_politikasi.json"
MODLAR = ("genis", "kapi", "kapali")
KABUK_ARACLARI = ("Bash", "PowerShell")
_TIRNAK = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')
# Ayar dosyası yok/bozuksa son çare: yalnız push kapısı, geniş yetki yok.
_YEDEK = {"surum": 1, "mod": "kapi", "kabuk_yasak": [], "rest_kapi": [], "mcp": [],
          "kabuk_kapi": [{"ad": "git push", "desen": r"\bgit\b(?:\s+(?:-[Cc]\s+\S+|--[\w-]+=\S+|-\S+))*\s+push\b"}]}


def _json_sozluk(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def ayar_yukle(sd: str | None = None) -> dict:
    cfg = _json_sozluk(AYAR_DOSYASI) or copy.deepcopy(_YEDEK)
    if sd:
        ezme = _json_sozluk(os.path.join(sd, EZME_AD))
        if ezme:
            cfg.update(ezme)
    return cfg


def mod_bul(cfg: dict) -> str:
    """Ortam değişkeni > ayar. Tanınmayan değer kapı moduna düşer (kapıyı kapatmaz, geniş yetki de vermez)."""
    ort = (os.environ.get("ORKESTRA_IZIN") or "").strip().lower()
    if ort in ("0", "kapali", "off"):
        return "kapali"
    ham = ort or str(cfg.get("mod") or "kapi").lower()
    return ham if ham in MODLAR else "kapi"


@functools.lru_cache(maxsize=256)
def _derle(desen: str):
    try:
        return re.compile(desen)
    except re.error:
        return None


def gecersiz_desenler(cfg: dict) -> list[str]:
    """Derlenemeyen desenlerin listesi (doktor için)."""
    kotu = []
    for bolum in ("kabuk_yasak", "kabuk_kapi", "rest_kapi", "mcp"):
        for m in cfg.get(bolum) or []:
            for ad, d in m.items():
                if ad in ("desen", "arac", "adres", "yazma", "okuma") and _derle(str(d)) is None:
                    kotu.append(f"{bolum}.{m.get('ad', '?')}.{ad}")
    return kotu


def _tirnaksiz(komut: str) -> str:
    """Tırnak içi metin veridir (commit mesajı, echo argümanı): kapı desenleri yalnız komutun kendisine bakar."""
    return _TIRNAK.sub('""', komut)


# İç içe çalıştırma: tırnak içi kod başka bir kabuğa/yorumlayıcıya veriliyorsa o kod gerçekten çalışır (veri değildir).
_IC_ICE = re.compile(
    r"\b(?:bash|sh|zsh|dash|ksh|pwsh|powershell|cmd|python[\d.]*|py|node|perl|ruby)(?:\.exe)?\b"
    r"[^\n]*?(?:\s-[A-Za-z]*c\b|\s/[cCkK]\b|\s-[Cc]ommand\b|\s-e\b|<<)"
    r"|\beval\b|\bInvoke-Expression\b|\biex\b|\bxargs\b")
_KODLANMIS = re.compile(r"\b(?:powershell|pwsh)(?:\.exe)?\b[^\n]*?\s-(?:EncodedCommand|enc|ec)\b", re.I)


def _ic_ice(komut: str) -> str | None:
    """İç içe kod görülürse tırnaksız, noktalaması sadeleşmiş metin (kapı desenleri iç kodu da görsün); yoksa None."""
    if not _IC_ICE.search(komut):
        return None
    return re.sub(r"[^\w\-./:+=@]+", " ", komut)


_DOSYA_ARACLARI = ("Read", "Edit", "Write", "NotebookEdit", "Grep", "Glob")
_KIMLIK_YOLU = re.compile(r"\.orkestra[\/]+credentials", re.I)


_OKUMA_ARACLARI = ("Read", "Grep", "Glob")


def _kimlik_okuma_acik(cfg: dict) -> bool:
    """ADR-0014: kimlik klasörünü okuma varsayılan açık; ORKESTRA_KIMLIK_OKUMA=0 ya da ayarda kimlik_okuma=false kapatır."""
    if (os.environ.get("ORKESTRA_KIMLIK_OKUMA") or "").strip().lower() in ("0", "kapali", "off", "false"):
        return False
    return cfg.get("kimlik_okuma", True) is not False


def _kimlik_kapisi(arac: str, girdi: dict, okuma_acik: bool = False) -> str | None:
    """Kimlik klasörüne ajan erişimi (ADR-0008, ADR-0014): okuma (Read/Grep/Glob) ayarla serbest; yazma ve kabuk her zaman yasak.
    Okunan değer yanıta, belgeye, hafızaya ya da komut satırına yazılmaz; betiğe `orkestra kimlik calistir` ile verilir."""
    try:
        import kimlik as K
        kok = os.path.normcase(K.kok())
    except Exception:
        kok = ""
    metin = ""
    if arac in _DOSYA_ARACLARI:
        metin = " ".join(str(girdi.get(k) or "") for k in ("file_path", "notebook_path", "path", "pattern"))
    elif arac in KABUK_ARACLARI:
        metin = str(girdi.get("command") or "")
    if not metin:
        return None
    if _KIMLIK_YOLU.search(metin) or (kok and kok in os.path.normcase(metin.replace("/", os.sep))):
        if okuma_acik and arac in _OKUMA_ARACLARI:
            return None
        return "kimlik klasörü (ADR-0014): ajan yalnız Read/Grep/Glob ile okuyabilir (ayar kimlik_okuma); yazma ve kabuk yasak; değeri kullanıcı `orkestra kimlik ekle` ile girer, betiğe `orkestra kimlik calistir` verir."
    return None


def karar(arac: str, girdi: dict | None, sd: str | None = None, cfg: dict | None = None) -> tuple[str | None, str]:
    cfg = cfg or ayar_yukle(sd)
    ned = _kimlik_kapisi(arac, girdi or {}, _kimlik_okuma_acik(cfg))
    if ned:
        return "deny", ned  # mod ne olursa olsun
    mod = mod_bul(cfg)
    if mod == "kapali":
        return None, ""
    girdi = girdi or {}
    if arac in KABUK_ARACLARI:
        komut = str(girdi.get("command") or "")
        kuru = _tirnaksiz(komut)
        ic = _ic_ice(komut)  # bash -c "git push", python -c "subprocess.run(['git','push'])" gibi iç içe kod
        for m in cfg.get("kabuk_yasak") or []:
            d = _derle(str(m.get("desen") or ""))
            if d and (d.search(kuru) or (ic and d.search(ic))):
                return "deny", f"{m.get('ad')}: halka açık ve geri alınamaz; zorla/silme/ayna push yapılmaz."
        for m in cfg.get("kabuk_kapi") or []:
            d = _derle(str(m.get("desen") or ""))
            if d and (d.search(kuru) or (ic and d.search(ic))):
                return "ask", f"{m.get('ad')}: halka açık eylem, onay gerekir."
        if _KODLANMIS.search(komut):
            return "ask", "kodlanmış PowerShell komutu: içeriği denetlenemez, onay gerekir."
        for m in cfg.get("rest_kapi") or []:
            a, h, y = (_derle(str(m.get(k) or "")) for k in ("arac", "adres", "yazma"))
            if a and h and y and a.search(komut) and h.search(komut) and y.search(komut):
                return "ask", f"{m.get('ad')}: halka açık eylem, onay gerekir."
    elif arac.startswith("mcp__"):
        for m in cfg.get("mcp") or []:
            d, o = _derle(str(m.get("arac") or "")), _derle(str(m.get("okuma") or ""))
            if d and d.search(arac):
                if o and o.search(arac):
                    break  # okuma aracı: kapı dışı
                return "ask", f"{m.get('ad')} yazma aracı ({arac}): halka açık eylem, onay gerekir."
    if mod == "genis":
        return "allow", "orkestra izin politikası (geniş yetki; kapı: push, GitHub/Jira yazma)"
    return None, ""


# ---------------------------------------------------------------- CLI

def cmd_goster(a):
    sd = a.sd or L.durum_dizini(os.getcwd())
    cfg = ayar_yukle(sd)
    kaynak = "eklenti" + (" + proje ezmesi" if sd and os.path.exists(os.path.join(sd, EZME_AD)) else "")
    print(f"mod: {mod_bul(cfg)} (ayar: {cfg.get('mod')}; ORKESTRA_IZIN={os.environ.get('ORKESTRA_IZIN') or '-'}) kaynak: {kaynak}")
    for bolum, baslik in (("kabuk_yasak", "yasak (deny)"), ("kabuk_kapi", "kapı (ask)"), ("rest_kapi", "kapı: REST (ask)")):
        for m in cfg.get(bolum) or []:
            print(f"{baslik}: {m.get('ad')}")
    for m in cfg.get("mcp") or []:
        print(f"kapı: MCP {m.get('ad')} (okuma dışı ask)")
    kotu = gecersiz_desenler(cfg)
    if kotu:
        print("GEÇERSİZ DESEN: " + ", ".join(kotu))
        return 1
    return 0


def cmd_sina(a):
    sd = a.sd or L.durum_dizini(os.getcwd())
    k, neden = karar(a.arac, {"command": a.komut or ""}, sd)
    print(f"{k or 'karar-yok'}\t{neden}")
    return 0


def kaydet(alt):
    p = alt.add_parser("izin", help="izin politikası: goster | sina (kapı kararı; ayarlar/izin_politikasi.json)")
    s = p.add_subparsers(dest="izin_komut", required=True)
    g = s.add_parser("goster", help="etkin mod ve kapı listesi")
    g.add_argument("--sd")
    g.set_defaults(f=lambda a: sys.exit(cmd_goster(a)))
    n = s.add_parser("sina", help="bir araç çağrısının kararını göster (çalıştırmaz)")
    n.add_argument("--arac", required=True)
    n.add_argument("--komut", default="")
    n.add_argument("--sd")
    n.set_defaults(f=lambda a: sys.exit(cmd_sina(a)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    alt = ap.add_subparsers(dest="komut", required=True)
    g = alt.add_parser("goster")
    g.add_argument("--sd")
    g.set_defaults(f=cmd_goster)
    n = alt.add_parser("sina")
    n.add_argument("--arac", required=True)
    n.add_argument("--komut", default="")
    n.add_argument("--sd")
    n.set_defaults(f=cmd_sina)
    a = ap.parse_args(argv)
    return a.f(a) or 0


if __name__ == "__main__":
    sys.exit(main())
