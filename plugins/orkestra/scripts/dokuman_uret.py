"""Başvuru dokümanını kaynaktan üretir: plugins/orkestra/docs/basvuru/*.md.

Elle düzenlenmez; envanter dosya sistemiyle senkron kalsın diye betik yazar.
Kullanım: python scripts/dokuman_uret.py [--kontrol]
  --kontrol: dosyaları yazmaz; üretilen içerik diskteki ile farklıysa çıkış 1 (CI/test için).
Kapsam: skill, ajan, CLI, ayar, hook, kural, standart/şablon, ortam değişkeni, ADR.
"""
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK.parent.parent
CIKTI = KOK / "docs" / "basvuru"
BASLIK = "<!-- Bu dosya scripts/dokuman_uret.py ile üretilir; elle düzenleme. -->\n\n"
ACIKLAMA_YOK = "açıklama yok"


def _oku(p):
    return Path(p).read_text(encoding="utf-8")


def _on_madde(metin):
    """YAML ön madde (basit anahtar: değer) -> sözlük."""
    m = re.match(r"---\r?\n(.*?)\r?\n---", metin, re.S)
    d = {}
    if m:
        for s in m.group(1).splitlines():
            k, sep, v = s.partition(":")
            if sep and not s.startswith((" ", "\t")):
                d[k.strip()] = v.strip()
    return d


def _ilk_cumle(s, n=220):
    s = " ".join(str(s).split())
    k = re.search(r"(?<=[.!?])\s", s)
    s = s[: k.start()] if k else s
    return s if len(s) <= n else s[: n - 1] + "…"


def _hucre(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def skiller():
    s = ["# Skill'ler\n", "Komut: `/orkestra:<ad>`. Kaynak: `skills/<ad>/SKILL.md`.\n",
         "| Skill | Ne zaman | Argüman |", "|---|---|---|"]
    for d in sorted((KOK / "skills").iterdir()):
        f = d / "SKILL.md"
        if f.exists():
            o = _on_madde(_oku(f))
            ac = _ilk_cumle(o.get("description", "")) or ACIKLAMA_YOK
            s.append(f"| `{d.name}` | {_hucre(ac)} | {_hucre(o.get('argument-hint', ''))} |")
    return "\n".join(s) + "\n"


def ajanlar():
    s = ["# Ajanlar\n", "Kaynak: `agents/<ad>.md`. Çağrı: Agent aracı, `subagent_type: orkestra:<ad>`.\n",
         "| Ajan | Görev | Model | Araçlar |", "|---|---|---|---|"]
    for f in sorted((KOK / "agents").glob("*.md")):
        o = _on_madde(_oku(f))
        ac = _ilk_cumle(o.get("description", "")) or ACIKLAMA_YOK
        s.append(f"| `{f.stem}` | {_hucre(ac)} | {o.get('model', '—')} | {_hucre(o.get('tools', '—'))} |")
    return "\n".join(s) + "\n"


def cli():
    # COLUMNS sabit: argparse satır sarmasını terminal genişliğinden alır; üretim ortama göre değişmesin.
    env = {**os.environ, "PYTHONUTF8": "1", "COLUMNS": "80"}
    r = subprocess.run([sys.executable, str(KOK / "scripts" / "orkestra.py"), "--help"],
                       capture_output=True, text=True, encoding="utf-8", env=env, **cfg.PENCERESIZ)
    return ("# CLI: `orkestra`\n\nKaynak: `scripts/orkestra.py` ve komut modülleri. Aşağıdaki metin `orkestra --help` çıktısıdır; "
            "komut başına ayrıntı için `orkestra <komut> --help`.\n\n```text\n" + r.stdout.rstrip() + "\n```\n")


def ayarlar():
    satirlar, aciklamasiz = [], 0
    for f in sorted((KOK / "ayarlar").glob("*.json")):
        try:
            d = json.loads(_oku(f))
        except Exception:
            continue
        d = d if isinstance(d, dict) else {}
        ac = _ilk_cumle(d.get("aciklama", ""))
        if not ac:
            ac, aciklamasiz = ACIKLAMA_YOK, aciklamasiz + 1
        satirlar.append(f"| `{f.stem}` | {_hucre(d.get('mod', '—'))} | {_hucre(ac)} |")
    s = ["# Ayarlar ve kapılar\n",
         "Kaynak: `ayarlar/*.json`. Proje ezmesi: `.claude/orkestra/<ad>.json`. `mod`: `golge` (uyarır, engellemez), `ihlal` (reddeder), `kapali`.\n",
         f"Toplam {len(satirlar)} ayar; `{ACIKLAMA_YOK}` işaretli: {aciklamasiz}.\n",
         "| Ayar | Mod | Açıklama |", "|---|---|---|"]
    return "\n".join(s + satirlar) + "\n"


def hooklar():
    d = json.loads(_oku(KOK / "hooks" / "hooks.json"))
    d = d.get("hooks", d)
    s = ["# Hook'lar\n", "Kaynak: `hooks/hooks.json`; hepsi `scripts/hook_giris.py <Olay>` çağırır (bayt kodu önbelleğini açıp hook.py'yi modül olarak çalıştırır).\n",
         "| Olay | Eşleyici | Komut sayısı |", "|---|---|---|"]
    for olay, girdiler in d.items():
        for g in girdiler:
            s.append(f"| {olay} | `{g.get('matcher') or '—'}` | {len(g.get('hooks', []))} |")
    return "\n".join(s) + "\n"


def kurallar():
    d = json.loads(_oku(KOK / "kurallar" / "eklenti_kurallari.json"))["kurallar"]
    s = ["# Kurallar\n", "Kaynak: `kurallar/eklenti_kurallari.json` (her projeye yüklenir). Tam metin kaynakta; burada kimlik ve ilk cümle.\n",
         "| Kimlik | Kural (ilk cümle) |", "|---|---|"]
    for k in d:
        m = re.sub(r"^ZORUNLU, istisnasız: *", "", k.get("metin", ""))
        s.append(f"| {k.get('id')} | {_hucre(_ilk_cumle(m, 260))} |")
    return "\n".join(s) + "\n"


def standartlar():
    s = ["# Standartlar ve şablonlar\n", "`orkestra standart goster <ad>` standardı gösterir.\n", "## Standartlar\n"]
    for f in sorted((KOK / "standartlar").glob("*.md")):
        b = next((x[2:] for x in _oku(f).splitlines() if x.startswith("# ")), f.stem)
        s.append(f"- `{f.stem}`: {b}")
    s += ["\n## Belge şablonları\n"]
    for f in sorted((KOK / "sablonlar").glob("*.md")):
        b = next((x.lstrip("# ") for x in _oku(f).splitlines() if x.startswith("#")), f.stem)
        s.append(f"- `{f.stem}`: {b}")
    return "\n".join(s) + "\n"


def ortam():
    kul = defaultdict(set)
    for f in (KOK / "scripts").rglob("*.py"):
        for m in set(re.findall(r"\bORKESTRA_[A-Z0-9_]+\b", _oku(f))):
            kul[m].add(f.name)
    s = ["# Ortam değişkenleri\n", f"Kaynakta geçen {len(kul)} değişken. `…_KAPISI=0` ilgili kapıyı kapatır.\n",
         "| Değişken | Geçtiği betikler |", "|---|---|"]
    for k in sorted(kul):
        dos = sorted(kul[k])
        s.append(f"| `{k}` | {', '.join(dos[:4])}{' …' if len(dos) > 4 else ''} |")
    return "\n".join(s) + "\n"


def adr():
    s = ["# ADR dizini\n", "Kaynak: depo kökündeki `adr/`.\n", "| No | Başlık | Durum |", "|---|---|---|"]
    for f in sorted((DEPO / "adr").glob("ADR-*.md")):
        t = _oku(f)
        b = next((x[2:] for x in t.splitlines() if x.startswith("# ")), f.stem)
        m = re.search(r"\*\*Durum:\*\*\s*(.+)", t)
        s.append(f"| [{f.stem[:8]}](../../../../adr/{f.name}) | {_hucre(b.split(':', 1)[-1].strip())} | {_hucre(m.group(1).strip()) if m else '—'} |")
    return "\n".join(s) + "\n"


SAYFALAR = {"skiller": skiller, "ajanlar": ajanlar, "cli": cli, "ayarlar": ayarlar, "hooklar": hooklar,
            "kurallar": kurallar, "standartlar": standartlar, "ortam": ortam, "adr": adr}


def uret(cikti=None):
    """{sayfa adı: içerik} döner; dosya yazmaz."""
    return {ad: BASLIK + fn() for ad, fn in SAYFALAR.items()}


def eskimis(cikti=None):
    """Diskteki sayfalarla üretilen farklı olanların adları."""
    cikti = Path(cikti or CIKTI)
    return [ad for ad, ic in uret().items()
            if not (cikti / f"{ad}.md").exists() or _oku(cikti / f"{ad}.md") != ic]


def main():
    if "--kontrol" in sys.argv:
        fark = eskimis()
        if fark:
            print("eskimiş başvuru sayfaları:", ", ".join(fark))
            sys.exit(1)
        print("güncel")
        return
    CIKTI.mkdir(parents=True, exist_ok=True)
    for ad, ic in uret().items():
        (CIKTI / f"{ad}.md").write_text(ic, encoding="utf-8", newline="\n")
    print("tamam")


if __name__ == "__main__":
    main()
