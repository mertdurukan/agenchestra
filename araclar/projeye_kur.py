"""Orkestrayı bir projeye kurar — çalışma alanına özgü, genel ayarlara dokunmadan.

Kullanım:
    python araclar/projeye_kur.py --kullanici [--ui-yok] [--kuru] [--kaldir]   (önerilen: bilgisayardaki TÜM projeler)
    python araclar/projeye_kur.py <proje klasörü> [--ui-yok] [--kuru] [--kaynak {yerel,github}] [--repo SAHIP/DEPO]
    python araclar/projeye_kur.py <proje klasörü> --kaldir

--kullanici: marketplace'i tanıtır, plugin'leri USER kapsamında kurar (~/.claude). Projeye hiçbir şey yazılmaz; orkestra her
projede SessionStart hook'u ile kendiliğinden açılır (hook.py _otomatik_ac; kapatma ORKESTRA_OTOMATIK_ACIL=0).

Ne yapar (proje klasörü verilirse, hepsi o projenin içinde):
  1. Marketplace'i yayın klonundan (--yayin > ORKESTRA_YAYIN > <depo>/../claude-orchestration-yayin)
     bu bilgisayarda tanıtır (--kaynak github ise GitHub deposundan) (claude plugin marketplace add; zaten varsa geçer). Klon yoksa önce araclar/yayin_kur.py.
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
import re
import shutil
import subprocess
import sys

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKET = "claude-orchestration"
# Marketplace kaynağı: geliştirme deposunun temiz git klonu (yalnız commitlenmiş kod). Kurulum: araclar/yayin_kur.py


def yayin_yolu(arguman=None):
    """Öncelik: argüman > ORKESTRA_YAYIN > depo konumundan türetilen varsayılan."""
    v = arguman or os.environ.get("ORKESTRA_YAYIN") or os.path.join(os.path.dirname(DEPO), "claude-orchestration-yayin")
    return os.path.abspath(v).replace("\\", "/") if not (arguman or os.environ.get("ORKESTRA_YAYIN")) else v.replace("\\", "/")


# Geriye uyumlu ad: depo konumundan türetilir, sabit kişisel yol içermez.
VARSAYILAN_YAYIN = os.path.join(os.path.dirname(DEPO), "Claude_Orkestrasyon", "plugin_yayin").replace("\\", "/")
YAYIN = yayin_yolu()
KAYNAK = None  # {"source": ...} marketplace kaynağı (main doldurur)
PLUGINLER = ["orkestra", "orkestra-ui"]
VARSAYILAN = {
    "model": "claude-opus-5-5",
    "effortLevel": "medium",
    "autoMemoryEnabled": True,
    "autoDreamEnabled": True,
    "workflowSizeGuideline": "large",
}
GITIGNORE = [".claude/orkestra/*", "!.claude/orkestra/README.md", ".claude/orkestra/yerel.json",
             "!.claude/orkestra/doktor.d/", ".claude/agent-memory-local/", ".claude/settings.local.json"]
CLAUDE_MD_BOLUMU = """
## Orkestra (Claude orkestrasyon sistemi)
- Ana ajan (Opus 5.5 medium) planlar, dağıtır, toplar; işçi işini kendisi yapmaz ve onay yazmaz. Çok adımlı iş: `/orkestra:is <istek>`.
- Basamaklar: T0 betik · T1 Haiku · T2 Sonnet · T3 Opus medium · T4 Opus xhigh. İzin veren en düşük basamakla başla.
- Her işçi çıktısını ayrı `orkestra:denetci` denetler; kimse kendi işini onaylamaz. Bağımsız işler paralel; yazma alanları kesişmez.
- Ortak defter `.claude/orkestra/ortak_defter.md` (otomatik; `orkestra defter baglam <id>` ile ihtiyacın olanı oku). Token defteri: `/orkestra:maliyet`. Panel: `/orkestra` (Claude içi), `/orkestra-web` (HTML canlı).
- Ayarlar `.claude/settings.json` dosyasındadır; user kapsamında kurulduysa eklentiler ve kota durum satırı kullanıcı ayarındadır (`~/.claude/settings.json`).
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


def orkestra_ayarlari(s):
    """Orkestranın çalışması için gereken üç ayarı ekler (proje ve kullanıcı kurulumu ortak): PYTHONUTF8, `orkestra`
    komut izni, kota durum satırı. Var olan değere dokunmaz; kullanıcının kendi durum satırı korunur."""
    s.setdefault("env", {}).setdefault("PYTHONUTF8", "1")
    izin = s.setdefault("permissions", {}).setdefault("allow", [])
    if "Bash(orkestra *)" not in izin:
        izin.append("Bash(orkestra *)")
    if "statusLine" not in s:
        s["statusLine"] = {"type": "command", "command": KOTA_KOMUTU}


def kullanici_ayar_yolu():
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def _ayar_oku(yol):
    if not os.path.exists(yol):
        return {}
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def _ayar_yaz(yol, s):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
        f.write("\n")


def kullanici_ayar_yaz(kuru):
    yol = kullanici_ayar_yolu()
    s = _ayar_oku(yol)
    orkestra_ayarlari(s)
    print(f"  ayarlar → {yol} (PYTHONUTF8, Bash(orkestra *), kota durum satırı; var olan değerler korunur)")
    if not kuru:
        _ayar_yaz(yol, s)


def kullanici_ayar_geri(kuru):
    """Yalnız orkestranın yazdığı kota durum satırını ve komut iznini siler; PYTHONUTF8 ve öteki ayarlara dokunmaz."""
    yol = kullanici_ayar_yolu()
    s = _ayar_oku(yol)
    if (s.get("statusLine") or {}).get("command") == KOTA_KOMUTU:
        s.pop("statusLine")
    izin = (s.get("permissions") or {}).get("allow") or []
    if "Bash(orkestra *)" in izin:
        izin.remove("Bash(orkestra *)")
    print(f"  ayarlar → {yol} (kota durum satırı ve Bash(orkestra *) kaldırıldı)")
    if not kuru and os.path.exists(yol):
        _ayar_yaz(yol, s)


def ayar_birlestir(proje, ui, kuru):
    yol = os.path.join(proje, ".claude", "settings.json")
    s = {}
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            s = json.load(f)
    for k, v in VARSAYILAN.items():
        s.setdefault(k, v)
    orkestra_ayarlari(s)
    girdi = s.setdefault("extraKnownMarketplaces", {}).setdefault(MARKET, {})
    girdi.setdefault("source", KAYNAK or {"source": "directory", "path": YAYIN})
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
    """Eksik satırları ekler. Dosyanın satır sonu (CRLF/LF) ve son satırının durumu korunur; var olan satır tekrar eklenmez."""
    if not os.path.isdir(os.path.join(proje, ".git")):
        return
    yol = os.path.join(proje, ".gitignore")
    ham = ""
    if os.path.exists(yol):
        with open(yol, encoding="utf-8", newline="") as f:  # newline="": satır sonları olduğu gibi okunur
            ham = f.read()
    mevcut = [x.strip() for x in ham.splitlines()]
    eksik = [s for s in GITIGNORE if s not in mevcut]
    if not eksik:
        return
    print(f"  .gitignore ← {len(eksik)} satır")
    if kuru:
        return
    sonu = "\r\n" if "\r\n" in ham else "\n"
    onek = ("" if not ham or ham.endswith("\n") else sonu) + (sonu if ham.strip() and mevcut[-1] else "")
    govde = sonu.join(["# orkestra çalışma zamanı"] + eksik) + sonu
    with open(yol, "a", encoding="utf-8", newline="") as f:
        f.write(onek + govde)


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
        kos([exe, "plugin", "marketplace", "add", KAYNAK.get("repo") or KAYNAK["path"]], proje, kuru)
    for p in PLUGINLER if ui else PLUGINLER[:1]:
        kos([exe, "plugin", "install", f"{p}@{MARKET}", "--scope", "project", "-y"], proje, kuru)
    ayar_birlestir(proje, ui, kuru)
    kos([sys.executable, os.path.join(DEPO, "plugins", "orkestra", "scripts", "orkestra.py"), "baslat"], proje, kuru)
    gitignore(proje, kuru)
    claude_md(proje, kuru)
    print("Tamam. Bu projede YENİ bir Claude oturumu aç; /orkestra ile paneli, /orkestra:is ile ilk işi başlat.")


def kur_kullanici(ui, kuru):
    exe = claude_exe()
    print("Orkestra kuruluyor → kullanıcı kapsamı (tüm projeler)")
    kod, cikti = kos([exe, "plugin", "marketplace", "list"], os.path.expanduser("~"), False)
    if MARKET not in cikti:
        kos([exe, "plugin", "marketplace", "add", KAYNAK.get("repo") or KAYNAK["path"]], os.path.expanduser("~"), kuru)
    for p in PLUGINLER if ui else PLUGINLER[:1]:
        kos([exe, "plugin", "install", f"{p}@{MARKET}", "--scope", "user", "-y"], os.path.expanduser("~"), kuru)
    kullanici_ayar_yaz(kuru)
    print("Tamam. Herhangi bir projede YENİ bir Claude oturumu aç; orkestra o projede kendiliğinden açılır.")


def kaldir_kullanici(kuru):
    exe = claude_exe()
    print("Orkestra kaldırılıyor → kullanıcı kapsamı (tüm projeler; durum klasörleri silinmez)")
    for p in PLUGINLER:
        kos([exe, "plugin", "uninstall", f"{p}@{MARKET}", "--scope", "user", "-y"], os.path.expanduser("~"), kuru)
    kullanici_ayar_geri(kuru)


def kaldir(proje, kuru):
    """Proje kapsamındaki kurulumu kaldırır ve plugin'leri bu projede `false` yapar: user kapsamında kurulu olsalar da
    bu projede yüklenmezler, SessionStart otomatik açılışı (hook.py _otomatik_ac) da çalışmaz."""
    exe = claude_exe()
    print(f"Orkestra kaldırılıyor → {proje} (durum klasörü .claude/orkestra/ silinmez)")
    for p in PLUGINLER:
        kos([exe, "plugin", "uninstall", f"{p}@{MARKET}", "--scope", "project", "-y"], proje, kuru)
    yol = os.path.join(proje, ".claude", "settings.json")
    print(f"  ayarlar → {yol} (enabledPlugins: false)")
    if not kuru:
        s = {}
        if os.path.exists(yol):
            with open(yol, encoding="utf-8") as f:
                s = json.load(f)
        ep = s.setdefault("enabledPlugins", {})
        for p in PLUGINLER:
            ep[f"{p}@{MARKET}"] = False
        s.get("extraKnownMarketplaces", {}).pop(MARKET, None)
        if (s.get("statusLine") or {}).get("command") == KOTA_KOMUTU:
            s.pop("statusLine")
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
            f.write("\n")


def origin_repo():
    r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=DEPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        return None
    m = re.search(r"github\.com[:/]+([^/\s]+/[^/\s]+?)(?:\.git)?/?\s*$", r.stdout.strip())
    return m.group(1) if m else None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("proje", nargs="?", help="orkestranın kurulacağı proje klasörü (--kullanici ile verilmez)")
    p.add_argument("--kullanici", action="store_true", help="user kapsamında kur: bilgisayardaki tüm projeler")
    p.add_argument("--ui-yok", action="store_true", help="arayüz modunu kurma")
    p.add_argument("--kuru", action="store_true", help="yalnız ne yapılacağını göster")
    p.add_argument("--kaldir", action="store_true", help="bu projeden kaldır")
    p.add_argument("--yayin", help="yerel marketplace kaynağı (yayın klonu); varsayılan ORKESTRA_YAYIN ya da <depo>/../claude-orchestration-yayin")
    p.add_argument("--kaynak", choices=["yerel", "github"], default="yerel", help="marketplace kaynağı türü (varsayılan yerel)")
    p.add_argument("--repo", help="--kaynak github için SAHIP/DEPO (yoksa depo origin'inden türetilir)")
    a = p.parse_args()
    global YAYIN, KAYNAK
    YAYIN = yayin_yolu(a.yayin)
    if a.kaynak == "github":
        repo = a.repo or origin_repo()
        if not repo:
            sys.exit("--kaynak github için repo bulunamadı: --repo SAHIP/DEPO ver ya da depoya github origin ekle.")
        KAYNAK = {"source": "github", "repo": repo}
    else:
        KAYNAK = {"source": "directory", "path": YAYIN}
    if a.kullanici:
        if a.proje:
            sys.exit("--kullanici ile proje klasörü verilmez.")
        return kaldir_kullanici(a.kuru) if a.kaldir else kur_kullanici(not a.ui_yok, a.kuru)
    if not a.proje:
        sys.exit("proje klasörü ver ya da --kullanici kullan.")
    proje = os.path.abspath(a.proje)
    if not os.path.isdir(proje):
        sys.exit(f"klasör yok: {proje}")
    if a.kaldir:
        kaldir(proje, a.kuru)
    else:
        kur(proje, not a.ui_yok, a.kuru)


if __name__ == "__main__":
    main()
