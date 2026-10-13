"""Orkestrayı bir projeye kurar — çalışma alanına özgü, genel ayarlara dokunmadan.

Kullanım:
    python C:\\Users\\PC\\Desktop\\Claude-Orchestration\\araclar\\projeye_kur.py <proje klasörü> [--ui-yok] [--kuru]
    python ...\\projeye_kur.py <proje klasörü> --kaldir

Ne yapar (hepsi o projenin içinde):
  1. Marketplace'i yayın klonundan (Claude_Orkestrasyon/plugin_yayin; --yayin ya da ORKESTRA_YAYIN ile değişir)
     bu bilgisayarda tanıtır (claude plugin marketplace add; zaten varsa geçer). Klon yoksa önce araclar/yayin_kur.py.
     Bu, ayar değil, makinenin plugin kaydıdır (~/.claude/plugins/known_marketplaces.json).
  2. orkestra ve orkestra-ui plugin'lerini PROJE kapsamında kurar → <proje>/.claude/settings.json.
  3. Proje ayarlarına orkestra varsayılanlarını EKLER (var olan değerin üstüne yazmaz):
     model, effortLevel, autoMemoryEnabled, autoDreamEnabled, workflowSizeGuideline, env.PYTHONUTF8,
     permissions.allow "Bash(orkestra *)", extraKnownMarketplaces (autoUpdate: true); statusLine yoksa kota kaydı (scripts/kota.py:
     5 saatlik ve haftalık kullanım sınırını analitik paneli için kaydeder).
  4. `orkestra baslat` ile <proje>/.claude/orkestra/ durum klasörünü açar.
  5. Proje git deposuysa .gitignore'a çalışma zamanı satırlarını ekler.
  6. CLAUDE.md'ye (yoksa oluşturur) kısa bir "Orkestra" bölümü ekler (zaten varsa dokunmaz).
~/.claude/settings.json'a HİÇBİR ŞEY yazmaz. Kurulumdan sonra o projede yeni bir Claude oturumu aç.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKET = "claude-orchestration"
# Marketplace kaynağı: geliştirme deposunun temiz git klonu (yalnız commitlenmiş kod). Kurulum: araclar/yayin_kur.py
VARSAYILAN_YAYIN = "C:/Mert/McD/Claude_Orkestrasyon/plugin_yayin"
YAYIN = (os.environ.get("ORKESTRA_YAYIN") or VARSAYILAN_YAYIN).replace("\\", "/")
PLUGINLER = ["orkestra", "orkestra-ui"]
VARSAYILAN = {
    "model": "claude-opus-5-5",
    "effortLevel": "medium",
    "autoMemoryEnabled": True,
    "autoDreamEnabled": True,
    "workflowSizeGuideline": "large",
}
GITIGNORE = [".claude/orkestra/*", "!.claude/orkestra/README.md", ".claude/agent-memory-local/", ".claude/settings.local.json"]
CLAUDE_MD_BOLUMU = """
## Orkestra (Claude orkestrasyon sistemi)
- Ana ajan (Opus 5.5 medium) planlar, dağıtır, toplar; işçi işini kendisi yapmaz ve onay yazmaz. Çok adımlı iş: `/orkestra:is <istek>`.
- Basamaklar: T0 betik · T1 Haiku · T2 Sonnet · T3 Opus medium · T4 Opus xhigh. İzin veren en düşük basamakla başla.
- Her işçi çıktısını ayrı `orkestra:denetci` denetler; kimse kendi işini onaylamaz. Bağımsız işler paralel; yazma alanları kesişmez.
- Ortak defter `.claude/orkestra/ortak_defter.md` (otomatik; `orkestra defter baglam <id>` ile ihtiyacın olanı oku). Token defteri: `/orkestra:maliyet`. Panel: `/orkestra` (Claude içi), `/orkestra-web` (HTML canlı).
- Ayarlar bu çalışma alanına özgüdür (`.claude/settings.json`); genel ayar kullanılmaz.
"""


KOTA_KOMUTU = 'python "' + os.path.join(DEPO, "plugins", "orkestra", "scripts", "kota.py").replace("\\", "/") + '"'


def claude_exe() -> str:
    e = os.environ.get("CLAUDE_CODE_EXECPATH")
    if e and os.path.exists(e):
        return e
    adaylar = []
    for kok in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
        adaylar += glob.glob(os.path.join(kok, "Claude", "claude-code", "*", "*", "claude.exe"))
        adaylar += glob.glob(os.path.join(kok, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude", "claude-code", "*", "*", "claude.exe"))
    adaylar = [a for a in adaylar if os.path.exists(a)]
    if adaylar:
        return max(adaylar, key=os.path.getmtime)
    yol = shutil.which("claude")
    if yol:
        return yol
    sys.exit("claude.exe bulunamadı (Claude masaüstü uygulaması kurulu mu?).")


def kos(argv, cwd, kuru):
    print("  $ " + " ".join(f'"{a}"' if " " in a else a for a in argv))
    if kuru:
        return 0, ""
    r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    cikti = (r.stdout + r.stderr).strip()
    if cikti:
        print("    " + cikti.splitlines()[-1])
    return r.returncode, cikti


def ayar_birlestir(proje, ui, kuru):
    yol = os.path.join(proje, ".claude", "settings.json")
    s = {}
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            s = json.load(f)
    for k, v in VARSAYILAN.items():
        s.setdefault(k, v)
    s.setdefault("env", {}).setdefault("PYTHONUTF8", "1")
    izin = s.setdefault("permissions", {}).setdefault("allow", [])
    if "Bash(orkestra *)" not in izin:
        izin.append("Bash(orkestra *)")
    if "statusLine" not in s:  # kullanıcının kendi durum satırı varsa dokunma
        s["statusLine"] = {"type": "command", "command": KOTA_KOMUTU}
    girdi = s.setdefault("extraKnownMarketplaces", {}).setdefault(MARKET, {})
    girdi.setdefault("source", {"source": "directory", "path": YAYIN})
    girdi["autoUpdate"] = True
    ep = s.setdefault("enabledPlugins", {})
    ep[f"orkestra@{MARKET}"] = True
    if ui:
        ep[f"orkestra-ui@{MARKET}"] = True
    print(f"  ayarlar → {yol}")
    if not kuru:
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
            f.write("\n")


def gitignore(proje, kuru):
    if not os.path.isdir(os.path.join(proje, ".git")):
        return
    yol = os.path.join(proje, ".gitignore")
    mevcut = open(yol, encoding="utf-8").read().splitlines() if os.path.exists(yol) else []
    eksik = [s for s in GITIGNORE if s not in mevcut]
    if eksik:
        print(f"  .gitignore ← {len(eksik)} satır")
        if not kuru:
            with open(yol, "a", encoding="utf-8", newline="\n") as f:
                f.write(("\n" if mevcut and mevcut[-1] else "") + "# orkestra çalışma zamanı\n" + "\n".join(eksik) + "\n")


def claude_md(proje, kuru):
    yol = os.path.join(proje, "CLAUDE.md")
    metin = open(yol, encoding="utf-8").read() if os.path.exists(yol) else ""
    if "## Orkestra" in metin:
        return
    print(f"  CLAUDE.md ← Orkestra bölümü")
    if not kuru:
        with open(yol, "a", encoding="utf-8", newline="\n") as f:
            f.write(("" if not metin else "\n") + CLAUDE_MD_BOLUMU.lstrip("\n"))


def kur(proje, ui, kuru):
    exe = claude_exe()
    print(f"Orkestra kuruluyor → {proje}")
    kod, cikti = kos([exe, "plugin", "marketplace", "list"], proje, False)
    if MARKET not in cikti:
        kos([exe, "plugin", "marketplace", "add", YAYIN], proje, kuru)
    for p in PLUGINLER if ui else PLUGINLER[:1]:
        kos([exe, "plugin", "install", f"{p}@{MARKET}", "--scope", "project", "-y"], proje, kuru)
    ayar_birlestir(proje, ui, kuru)
    kos([sys.executable, os.path.join(DEPO, "plugins", "orkestra", "scripts", "orkestra.py"), "baslat"], proje, kuru)
    gitignore(proje, kuru)
    claude_md(proje, kuru)
    print("Tamam. Bu projede YENİ bir Claude oturumu aç; /orkestra ile paneli, /orkestra:is ile ilk işi başlat.")


def kaldir(proje, kuru):
    exe = claude_exe()
    print(f"Orkestra kaldırılıyor → {proje} (durum klasörü .claude/orkestra/ silinmez)")
    for p in PLUGINLER:
        kos([exe, "plugin", "uninstall", f"{p}@{MARKET}", "--scope", "project", "-y"], proje, kuru)
    yol = os.path.join(proje, ".claude", "settings.json")
    if os.path.exists(yol) and not kuru:
        with open(yol, encoding="utf-8") as f:
            s = json.load(f)
        for p in PLUGINLER:
            s.get("enabledPlugins", {}).pop(f"{p}@{MARKET}", None)
        s.get("extraKnownMarketplaces", {}).pop(MARKET, None)
        if (s.get("statusLine") or {}).get("command") == KOTA_KOMUTU:
            s.pop("statusLine")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
            f.write("\n")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("proje", help="orkestranın kurulacağı proje klasörü")
    p.add_argument("--ui-yok", action="store_true", help="arayüz modunu kurma")
    p.add_argument("--kuru", action="store_true", help="yalnız ne yapılacağını göster")
    p.add_argument("--kaldir", action="store_true", help="bu projeden kaldır")
    p.add_argument("--yayin", help="marketplace kaynağı (yayın klonu); varsayılan ORKESTRA_YAYIN ya da " + VARSAYILAN_YAYIN)
    a = p.parse_args()
    if a.yayin:
        global YAYIN
        YAYIN = a.yayin.replace("\\", "/")
    proje = os.path.abspath(a.proje)
    if not os.path.isdir(proje):
        sys.exit(f"klasör yok: {proje}")
    if a.kaldir:
        kaldir(proje, a.kuru)
    else:
        kur(proje, not a.ui_yok, a.kuru)


if __name__ == "__main__":
    main()
