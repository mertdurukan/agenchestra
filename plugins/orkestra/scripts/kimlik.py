"""Kimlik bilgisi (credentials) okuyucusu: kullanıcı-düzeyi klasör, proje bazlı .env dosyaları (ADR-0008).

Düzen: <kök>/<proje>/<servis>.env ve ortak servisler için <kök>/_ortak/<servis>.env.
Kök: ORKESTRA_KIMLIK_DIZINI ya da ~/.orkestra/credentials (eklenti ve depo dışında; güncellemeden etkilenmez).
Değer YALNIZ `al()` ile çağıran süreçte döner; CLI hiçbir komutta değer yazmaz, hata iletilerinde de değer yoktur.
Öncelik: aynı adlı ortam değişkeni dosyadan önce gelir (CI, DEMOAPP_PROD_PW uyumu).
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402

ORTAK = "_ortak"
_AD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_ANAHTAR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GEVSEK = ("everyone", "authenticated users", "builtin\\users", "\\users:", "herkes")


class KimlikHata(Exception):
    """Mesajı hiçbir zaman değer içermez."""


def kok() -> str:
    return os.path.abspath(os.environ.get("ORKESTRA_KIMLIK_DIZINI") or os.path.join(os.path.expanduser("~"), ".orkestra", "credentials"))


def proje_adi(cwd: str | None = None) -> str:
    ad = os.environ.get("ORKESTRA_KIMLIK_PROJE")
    if ad:
        return ad
    try:
        import ork_lib as L
        return os.path.basename(os.path.normpath(L.proje_dizini() or cwd or os.getcwd()))
    except Exception:
        return os.path.basename(os.path.normpath(cwd or os.getcwd()))


def _ad_denetle(deger: str, ne: str):
    if not _AD.match(deger or ""):
        raise KimlikHata(f"geçersiz {ne} adı")


def yol(servis: str, proje: str | None = None) -> str | None:
    """Servis dosyasının yolu: önce proje, sonra _ortak; yoksa None."""
    _ad_denetle(servis, "servis")
    p = proje or proje_adi()
    _ad_denetle(p, "proje")
    for ust in (p, ORTAK):
        y = os.path.join(kok(), ust, servis + ".env")
        if os.path.isfile(y):
            return y
    return None


def ayristir(metin: str) -> dict[str, str]:
    sonuc: dict[str, str] = {}
    for satir in metin.splitlines():
        s = satir.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        if s.startswith("export "):
            s = s[7:].lstrip()
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip()
        if not _ANAHTAR.match(k):
            continue
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        sonuc[k] = v
    return sonuc


def yukle(servis: str, proje: str | None = None) -> dict[str, str]:
    y = yol(servis, proje)
    if not y:
        raise KimlikHata(f"kimlik dosyası yok: servis '{servis}' (proje '{proje or proje_adi()}' ve {ORTAK})")
    with open(y, encoding="utf-8-sig") as f:
        return ayristir(f.read())


def al(servis: str, anahtar: str, proje: str | None = None) -> str:
    """Değeri döner (yalnız çağıran süreçte). Ortam değişkeni dosyadan önce gelir."""
    if not _ANAHTAR.match(anahtar or ""):
        raise KimlikHata("geçersiz anahtar adı")
    if os.environ.get(anahtar):
        return os.environ[anahtar]
    d = yukle(servis, proje)
    if anahtar not in d:
        raise KimlikHata(f"anahtar yok: {servis}.{anahtar}")
    return d[anahtar]


def liste(proje: str | None = None) -> list[tuple[str, str, list[str]]]:
    """(kapsam, servis, anahtar adları); değer yok."""
    p = proje or proje_adi()
    _ad_denetle(p, "proje")
    out = []
    for ust in (p, ORTAK):
        d = os.path.join(kok(), ust)
        if not os.path.isdir(d):
            continue
        for ad in sorted(os.listdir(d)):
            if ad.endswith(".env"):
                with open(os.path.join(d, ad), encoding="utf-8-sig") as f:
                    out.append((ust, ad[:-4], sorted(ayristir(f.read()))))
    return out


def _kullanici() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or ""


def izin_sikilastir(yolu: str) -> str:
    """Yalnız mevcut kullanıcıya erişim. Dönen metin kısa durum iletisidir."""
    if os.name == "nt":
        k = _kullanici()
        if not k:
            raise KimlikHata("kullanıcı adı bulunamadı; ACL ayarlanamadı")
        r = subprocess.run(["icacls", yolu, "/inheritance:r", "/grant:r", f"{k}:(OI)(CI)F"], capture_output=True, text=True, **cfg.PENCERESIZ)
        if r.returncode != 0:
            raise KimlikHata("icacls başarısız: " + (r.stderr or r.stdout).strip()[:200])
        return "ACL: yalnız mevcut kullanıcı"
    os.chmod(yolu, stat.S_IRWXU)
    return "izin: 0700"


def izin_gevsek_mi(yolu: str) -> list[str]:
    """Gevşek izin bulgularını döner (boşsa sıkı)."""
    if os.name == "nt":
        r = subprocess.run(["icacls", yolu], capture_output=True, text=True, **cfg.PENCERESIZ)
        if r.returncode != 0:
            return ["icacls okunamadı"]
        dusuk = r.stdout.lower()
        return [g.strip("\\:") for g in _GEVSEK if g in dusuk]
    m = os.stat(yolu).st_mode
    return ["grup/diğer erişimi var"] if m & (stat.S_IRWXG | stat.S_IRWXO) else []


def kur(proje: str | None = None) -> list[str]:
    p = proje or proje_adi()
    _ad_denetle(p, "proje")
    k = kok()
    os.makedirs(os.path.join(k, p), exist_ok=True)
    os.makedirs(os.path.join(k, ORTAK), exist_ok=True)
    return [f"klasör: {k}", izin_sikilastir(k)]


def ekle(servis: str, anahtar: str, deger: str, proje: str | None = None, ortak: bool = False) -> str:
    _ad_denetle(servis, "servis")
    if not _ANAHTAR.match(anahtar or ""):
        raise KimlikHata("geçersiz anahtar adı")
    if "\n" in deger or "\r" in deger:
        raise KimlikHata("değer tek satır olmalı")
    ust = ORTAK if ortak else (proje or proje_adi())
    _ad_denetle(ust, "proje")
    kur(None if ortak else ust)
    y = os.path.join(kok(), ust, servis + ".env")
    mevcut = {}
    if os.path.isfile(y):
        with open(y, encoding="utf-8-sig") as f:
            mevcut = ayristir(f.read())
    mevcut[anahtar] = deger
    with open(y, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"{k}={v}\n" for k, v in mevcut.items()))
    return y


def aktar(kaynak_dizin: str, proje: str | None = None, uygula: bool = False) -> list[tuple[str, str, list[str]]]:
    """Eski Keys\\*.env dosyalarını kök/<proje>/ altına KOPYALAR (kaynağı silmez, var olanı ezmez).
    Dönen liste: (servis, durum, anahtar adları); değer yok."""
    p = proje or proje_adi()
    _ad_denetle(p, "proje")
    hedef = os.path.join(kok(), p)
    sonuc = []
    for ad in sorted(os.listdir(kaynak_dizin)):
        if not ad.endswith(".env") or not _AD.match(ad[:-4]):
            continue
        with open(os.path.join(kaynak_dizin, ad), encoding="utf-8-sig") as f:
            metin = f.read()
        adlar = sorted(ayristir(metin))
        h = os.path.join(hedef, ad)
        if os.path.exists(h):
            sonuc.append((ad[:-4], "atlandı (hedefte var)", adlar))
            continue
        if uygula:
            kur(p)
            with open(h, "w", encoding="utf-8", newline="\n") as f:
                f.write(metin)
        sonuc.append((ad[:-4], "kopyalandı" if uygula else "kopyalanır", adlar))
    return sonuc


def calistir(servis: str, komut: list[str], proje: str | None = None, cwd: str | None = None, env_ek: dict[str, str] | None = None) -> int:
    """Komutu servisin değişkenleri ortamda olarak çalıştırır; çıktıdaki değerler *** ile maskelenir."""
    if not komut:
        raise KimlikHata("çalıştırılacak komut yok")
    d = yukle(servis, proje)
    env = dict(os.environ)
    env.update(env_ek or {})  # ortam yorumlayıcısı (orkestra ortam calistir): PATH vb.
    for k, v in d.items():
        env.setdefault(k, v)  # ortam değişkeni önceliklidir
    r = subprocess.run(komut, env=env, cwd=cwd, capture_output=True, **cfg.PENCERESIZ)
    gizli = sorted({v for v in d.values() if len(v) >= 4}, key=len, reverse=True)

    def maske(b: bytes) -> bytes:
        s = b.decode("utf-8", errors="replace")
        for v in gizli:
            s = s.replace(v, "***")
        return s.encode("utf-8")
    sys.stdout.buffer.write(maske(r.stdout))
    sys.stderr.buffer.write(maske(r.stderr))
    return r.returncode
