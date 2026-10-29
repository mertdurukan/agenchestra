"""MCP kimlik sarmalayıcısı (ADR-0096): kimlik klasöründeki değerleri MCP sürecinin ortamına verir.

Kullanım: `python mcp_kimlik.py <mcp-adı>` (MCP config'inde komut olarak yazılır; `orkestra mcp config` üretir).
Sırayla: (1) ayarlar/mcp_kimlik.json + proje ezmesi (.claude/orkestra/mcp_kimlik.json) okunur ve şemadan geçirilir,
(2) kayıttaki `ortam` eşlemesine göre değerler kimlik klasöründen alınır, (3) MCP komutu alt süreç olarak başlatılır;
stdin/stdout/stderr alt sürece aktarılır.
Değer yalnız alt sürecin ortamına konur: bu sürecin argv'sine, stdout'una, stderr'ine ve diske yazılmaz.
MCP stdio taşıdığı için stdout'a hiçbir şey yazılmaz; tanı iletileri stderr'e gider ve değer içermez.
"""
import json
import os
import re
import shutil
import subprocess
import sys

EKLENTI = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
AYAR_AD = "mcp_kimlik"
IZINLI_ALAN = {"aciklama", "komut", "kimlik_servisi", "ortam", "gerek"}
PROJE_YER_TUTUCU = "${CLAUDE_PROJECT_DIR}"
_ORTAM_ADI = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GEREK_ADI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_SERVIS_ADI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class KayitHata(Exception):
    """Mesajı hiçbir zaman değer içermez."""


def proje_koku() -> str:
    return os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def kayit_oku(proje: str | None = None) -> dict:
    """Eklenti kaydı + proje ezmesi; aynı adlı MCP girdisi bütünüyle yerine konur. Şemadan geçirilmiş sözlük döner."""
    proje = proje or proje_koku()
    sonuc: dict = {}
    for yol in (os.path.join(EKLENTI, "ayarlar", AYAR_AD + ".json"),
                os.path.join(proje, ".claude", "orkestra", AYAR_AD + ".json")):
        try:
            with open(yol, encoding="utf-8-sig") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        mcp = d.get("mcp") if isinstance(d, dict) else None
        if isinstance(mcp, dict):
            sonuc.update(mcp)
    for ad, girdi in sonuc.items():
        dogrula(ad, girdi)
    return sonuc


def dogrula(ad: str, girdi) -> None:
    """Şema: değer alanı yok. Bilinmeyen alan, ad dışı ortam girdisi ve boş komut reddedilir (mesaj değer taşımaz)."""
    if not isinstance(girdi, dict):
        raise KayitHata(f"{ad}: girdi nesne olmalı")
    fazla = sorted(set(girdi) - IZINLI_ALAN)
    if fazla:
        raise KayitHata(f"{ad}: bilinmeyen alan(lar) {', '.join(fazla)} (kayıtta değer alanı olamaz)")
    komut = girdi.get("komut")
    if not (isinstance(komut, list) and komut and all(isinstance(x, str) and x for x in komut)):
        raise KayitHata(f"{ad}: komut boş olmayan metin listesi olmalı")
    ortam = girdi.get("ortam", {})
    if not isinstance(ortam, dict):
        raise KayitHata(f"{ad}: ortam nesne olmalı")
    servissiz = False
    for ortam_adi, anahtar in ortam.items():
        servis, nokta, ad_ = anahtar.partition(".") if isinstance(anahtar, str) else ("", "", "")
        anahtar_adi = ad_ if nokta else servis
        if not (_ORTAM_ADI.match(ortam_adi) and isinstance(anahtar, str) and _ORTAM_ADI.match(anahtar_adi)
                and (not nokta or _SERVIS_ADI.match(servis))):
            raise KayitHata(f"{ad}: ortam girdileri 'ORTAM_ADI: ANAHTAR' ya da 'ORTAM_ADI: servis.ANAHTAR' olmalı (değer yazılamaz)")
        servissiz = servissiz or not nokta
    if servissiz and not girdi.get("kimlik_servisi"):
        raise KayitHata(f"{ad}: servis öneksiz ortam girdisi için kimlik_servisi gerekir")
    gerek = girdi.get("gerek", [])
    if not (isinstance(gerek, list) and all(isinstance(x, str) and _GEREK_ADI.match(x) for x in gerek)):
        raise KayitHata(f"{ad}: gerek komut adları listesi olmalı (yol ayracı içeremez)")
    for parca in komut:
        artik = parca.replace(PROJE_YER_TUTUCU, "")
        if "${" in artik:
            raise KayitHata(f"{ad}: komutta yalnız {PROJE_YER_TUTUCU} yer tutucusu desteklenir")


def komut_ac(komut: list, ad: str = "") -> list:
    """Komut başındaki ~ kullanıcı klasörüne açılır; ${CLAUDE_PROJECT_DIR} ortam değişkeniyle değiştirilir (yoksa hata, cwd'ye düşülmez)."""
    if any(PROJE_YER_TUTUCU in x for x in komut):
        kok = os.environ.get("CLAUDE_PROJECT_DIR")
        if not kok:
            raise KayitHata(f"{ad}: {PROJE_YER_TUTUCU} için CLAUDE_PROJECT_DIR tanımlı değil")
        komut = [x.replace(PROJE_YER_TUTUCU, kok) for x in komut]
    return [os.path.expanduser(komut[0])] + list(komut[1:])


def anahtar_coz(girdi: dict, anahtar: str) -> tuple:
    """'servis.ANAHTAR' ya da 'ANAHTAR' (girdinin kimlik_servisi'yle) -> (servis, anahtar)."""
    servis, nokta, ad_ = anahtar.partition(".")
    return (servis, ad_) if nokta else (girdi["kimlik_servisi"], anahtar)


def ortam_kur(ad: str, girdi: dict, al, taban: dict | None = None) -> dict:
    """Alt sürecin ortamı: taban + kimlikten gelen değerler. `al(servis, anahtar)` değeri verir; yoksa KayitHata (adlı, değersiz)."""
    env = dict(os.environ if taban is None else taban)
    for ortam_adi, anahtar in (girdi.get("ortam") or {}).items():
        servis, ad_ = anahtar_coz(girdi, anahtar)
        try:
            env[ortam_adi] = al(servis, ad_)
        except Exception:
            raise KayitHata(f"{ad}: kimlik klasöründe karşılığı yok: {servis}.{ad_} "
                            f"(orkestra kimlik ekle {servis} {ad_})") from None
    return env


def hata(mesaj: str, kod: int = 2):
    print(f"mcp_kimlik: {mesaj}", file=sys.stderr)
    sys.exit(kod)


def _kimlik_al():
    sys.path.insert(0, os.path.join(EKLENTI, "scripts"))
    import kimlik
    return kimlik.al


def main(argv: list | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        hata("kullanım: mcp_kimlik.py <mcp-adı>")
    ad = args[0]
    try:
        kayit = kayit_oku()
        if ad not in kayit:
            raise KayitHata(f"{ad}: kayıtta yok (kayıtlı: {', '.join(sorted(kayit)) or '-'})")
        girdi = kayit[ad]
        env = ortam_kur(ad, girdi, _kimlik_al())
        komut = komut_ac(girdi["komut"], ad)
    except KayitHata as e:
        hata(str(e), 3)
    yol = shutil.which(komut[0])
    if not yol:
        hata(f"{ad}: {komut[0]} bulunamadı (kurulum için mevcut_durum ve ayarlar/{AYAR_AD}.json açıklamasına bak)", 4)
    try:
        return subprocess.run([yol] + komut[1:], env=env).returncode
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
