"""postgres-mcp sarmalayıcısı: kapı, kimlik ve salt okunur oturum.

Sırayla: (1) ayarda `kapi: true` ise db-olcum kapısını (VPN, saat penceresi) çağırır, KALDI ise çıkar; (2) ortamda
DATABASE_URI yoksa parolayı kimlik klasöründen okuyup bağlantı adresini yalnız bu süreçte kurar (dosyaya, komut satırına, çıktıya yazılmaz); (3) oturumu
default_transaction_read_only=on ile açtırır; (4) postgres-mcp'yi --access-mode=restricted ile (`--yazma` argümanıyla: `yazma_izni: true` ve ortam prod değilken
unrestricted, salt okunur oturum ayarı olmadan; ADR-0093) alt süreç olarak
başlatır; (5) sunucu çalışırken kapıyı izleme_sn aralıkla yeniden çağırır, KALDI olursa alt süreci sonlandırır.

Ayar: eklenti ayarlar/postgres_mcp.json + proje .claude/orkestra/postgres_mcp.json (üst düzey anahtarlar yerine konur).
MCP stdio taşıdığı için stdout'a hiçbir şey yazılmaz; tanı iletileri stderr'e gider.
"""
import cfg
import json
import os
import shutil
import subprocess
import sys
import threading
from urllib.parse import quote

EKLENTI = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
KAPI = os.path.join(EKLENTI, "skills", "db-olcum", "scripts", "kapi.py")
AYAR_AD = "postgres_mcp"
ZAMAN_ASIMI = "-c statement_timeout=60000"
SALT_OKUNUR = "-c default_transaction_read_only=on " + ZAMAN_ASIMI


def hata(mesaj: str, kod: int = 2):
    print(f"postgres_mcp: {mesaj}", file=sys.stderr)
    sys.exit(kod)


def proje_koku() -> str:
    return os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def ayar_oku(proje: str | None = None) -> dict:
    """Eklenti varsayılanı + proje ezmesi; üst düzey anahtarlar yerine konur, `anahtarlar` anahtar anahtar birleşir."""
    proje = proje or proje_koku()
    sonuc: dict = {}
    for yol in (os.path.join(EKLENTI, "ayarlar", AYAR_AD + ".json"),
                os.path.join(proje, ".claude", "orkestra", AYAR_AD + ".json")):
        try:
            with open(yol, encoding="utf-8-sig") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            if k == "anahtarlar" and isinstance(v, dict):
                sonuc["anahtarlar"] = {**sonuc.get("anahtarlar", {}), **v}
            else:
                sonuc[k] = v
    return sonuc


def dogrudan_uri() -> str:
    """Ortamda DATABASE_URI varsa kimlik klasörü yerine o kullanılır."""
    return os.environ.get("DATABASE_URI", "").strip()


def ayar_denetle(ayar: dict, yazma: bool = False):
    if not dogrudan_uri():
        eksik = [a for a in ("kimlik_servisi", "veritabani") if not ayar.get(a)]
        eksik += [f"anahtarlar.{a}" for a in ("host", "kullanici", "parola") if not (ayar.get("anahtarlar") or {}).get(a)]
        if eksik:
            hata(f"ayar eksik: {', '.join(eksik)} ya da ortamda DATABASE_URI (.claude/orkestra/{AYAR_AD}.json)")
    komut = ayar.get("sunucu_komutu")
    if not (isinstance(komut, list) and komut and "--access-mode=restricted" in komut):
        hata("sunucu_komutu --access-mode=restricted içermeli")
    if yazma:
        if not ayar.get("yazma_izni"):
            hata(f"yazma kapalı: .claude/orkestra/{AYAR_AD}.json içinde yazma_izni: true gerekir (ADR-0093)", 4)
        if ayar.get("ortam", "kopya") == "prod":
            hata("prod ortamında yazma sunucusu başlatılmaz (ADR-0093)", 4)


def sunucu_komutu(ayar: dict, yazma: bool) -> list:
    komut = list(ayar["sunucu_komutu"])
    if yazma:
        komut = ["--access-mode=unrestricted" if a == "--access-mode=restricted" else a for a in komut]
    return komut


def uri_kur(ayar: dict, deger, yazma: bool = False) -> str:
    """Bağlantı adresi; `deger(anahtar_adi)` parolayı ve diğer değerleri verir. Yalnız bellekte tutulur."""
    a = ayar["anahtarlar"]
    port = deger(a["port"]) if a.get("port") else "5432"
    return (f"postgresql://{quote(deger(a['kullanici']), safe='')}:{quote(deger(a['parola']), safe='')}"
            f"@{deger(a['host'])}:{port}/{quote(ayar['veritabani'], safe='')}"
            f"?sslmode={ayar.get('sslmode', 'require')}&options={quote(ZAMAN_ASIMI if yazma else SALT_OKUNUR, safe='')}")


def kimlik_degeri(ayar: dict):
    sys.path.insert(0, os.path.join(EKLENTI, "scripts"))
    import kimlik

    def deger(anahtar: str) -> str:
        try:
            return kimlik.al(ayar["kimlik_servisi"], anahtar)
        except Exception as e:  # kimlik.KimlikHata: ad ve servis söylenir, değer asla
            hata(f"kimlik okunamadı ({ayar['kimlik_servisi']}.{anahtar}): {type(e).__name__}")
    return deger


def kapi_gecti(ortam: str, proje: str | None = None) -> tuple[bool, str]:
    """db-olcum kapısını çağırır; (geçti, özet). Kapının çıktısı stdout'a değil çağırana döner."""
    env = dict(os.environ)
    if proje:
        env["CLAUDE_PROJECT_DIR"] = proje
    try:
        p = subprocess.run([sys.executable, "-I", KAPI, "--ortam", ortam], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, timeout=60, **cfg.PENCERESIZ)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"kapı çalışmadı: {type(e).__name__}"
    kalanlar = [s for s in p.stdout.splitlines() if s.startswith("[KALDI]")]
    return p.returncode == 0, "; ".join(kalanlar) or ("geçti" if p.returncode == 0 else f"kapı çıkış kodu {p.returncode}")


def sonlandir(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, **cfg.PENCERESIZ)
    else:
        proc.terminate()


def izle(proc: subprocess.Popen, ortam: str, aralik: float, proje: str, durdur: threading.Event, kapi=kapi_gecti):
    """Kapıyı aralıkla yeniden denetler; KALDI olunca alt süreci sonlandırır. Sonlandırdıysa True döner."""
    while not durdur.wait(aralik):
        if proc.poll() is not None:
            return False
        gecti, ozet = kapi(ortam, proje)
        if not gecti:
            print(f"postgres_mcp: kapı KALDI, sunucu sonlandırılıyor: {ozet}", file=sys.stderr)
            sonlandir(proc)
            return True
    return False


def main(argv: list | None = None) -> int:
    yazma = "--yazma" in (sys.argv[1:] if argv is None else argv)
    proje = proje_koku()
    ayar = ayar_oku(proje)
    ayar_denetle(ayar, yazma)
    ortam = ayar.get("ortam", "kopya")
    kapi_var = bool(ayar.get("kapi"))
    if kapi_var:
        gecti, ozet = kapi_gecti(ortam, proje)
        if not gecti:
            hata(f"kapı KALDI, sunucu başlatılmadı: {ozet}", 3)
    komut = sunucu_komutu(ayar, yazma)
    yol = shutil.which(komut[0])
    if not yol:
        hata(f"{komut[0]} bulunamadı (pipx install postgres-mcp ya da sunucu_komutu'nu uvx ile değiştir)")
    env = dict(os.environ)
    if dogrudan_uri():
        env["PGOPTIONS"] = (env.get("PGOPTIONS", "") + " " + (ZAMAN_ASIMI if yazma else SALT_OKUNUR)).strip()
    else:
        env["DATABASE_URI"] = uri_kur(ayar, kimlik_degeri(ayar), yazma)
    # MCP stdio devri: creationflags verilirse çocuk boruları almaz ve istemci takılır (I-304 denemesi); bayrak konmaz
    proc = subprocess.Popen([yol] + komut[1:], env=env)
    durdur = threading.Event()
    if kapi_var:
        threading.Thread(target=izle, args=(proc, ortam, float(ayar.get("izleme_sn", 60)), proje, durdur),
                         daemon=True).start()
    try:
        kod = proc.wait()
    finally:
        durdur.set()
        sonlandir(proc)
    return kod


if __name__ == "__main__":
    sys.exit(main())
