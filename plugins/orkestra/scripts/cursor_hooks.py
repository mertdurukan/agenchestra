"""Kullanıcı düzeyi Cursor hooks.json'u (~/.cursor/hooks.json) kanonik hooks/cursor-hooks.json'dan üretir ve güvenle eşler.

Cursor yerel eklentisinin hooks/hooks.json'u yüklenmediği için Orkestra hook'ları kullanıcı dosyasından çalışır; bu dosya
elle yazılınca kanonik tanımdan (olaylar, timeout) sessizce sapıyordu (I-083). Kullanıcının kendi girdileri ve üst düzey
anahtarları korunur; yalnız Orkestra girdileri (yerel kopyadaki cursor_hook.py <olay>) yeniden üretilir.
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import re
import shutil
import tempfile

IZINLI_ALANLAR = ("timeout", "matcher", "failClosed")
YEDEK_SAYISI = 5
_BOM = b"\xef\xbb\xbf"
_HOOK_OLAYI = re.compile(r"""cursor_hook\.py["']?\s+(\S+)""")
_HOOK_YOLU = re.compile(r"""(?:"([^"]*cursor_hook\.py)"|'([^']*cursor_hook\.py)'|(\S*cursor_hook\.py))""")


class AyristirmaHatasi(ValueError):
    pass


def _ileri(yol: str) -> str:
    return yol.replace("\\", "/")


def _komut(kopya_koku: str, olay: str) -> str:
    return f'python "{_ileri(kopya_koku).rstrip("/")}/scripts/cursor_hook.py" {olay}'


def uret(kanonik_yol: str, kopya_koku: str) -> dict:
    """Kanonik tanımdaki her olay için tek girdi: yerel kopyadaki adaptörü çağıran komut + izinli alanlar."""
    with open(kanonik_yol, encoding="utf-8-sig") as f:
        kanonik = json.load(f)
    hooks = {}
    for olay, girdiler in (kanonik.get("hooks") or {}).items():
        ilk = next((g for g in girdiler or [] if isinstance(g, dict)), {})
        girdi = {"command": _komut(kopya_koku, olay)}
        girdi.update({a: ilk[a] for a in IZINLI_ALANLAR if a in ilk})
        hooks[olay] = [girdi]
    return {"version": 1, "hooks": hooks}


def orkestra_girdisi_mi(girdi, olay: str, kopya_koku: str) -> bool:
    """Komut cursor_hook.py <aynı olay> çalıştırıyor ve yolu yerel kopyayı (ya da bir orkestra klasörünü) gösteriyorsa."""
    if not isinstance(girdi, dict) or not isinstance(girdi.get("command"), str):
        return False
    komut = _ileri(girdi["command"])
    m = _HOOK_OLAYI.search(komut)
    if not m or m.group(1) != olay:
        return False
    if _ileri(kopya_koku).rstrip("/").lower() in komut.lower():
        return True
    y = _HOOK_YOLU.search(komut)
    return bool(y) and "orkestra" in next(g for g in y.groups() if g is not None).lower()


def birlestir(mevcut: dict, uretilen: dict, kopya_koku: str) -> dict:
    """Mevcut dosyaya üretilen Orkestra girdilerini yerleştirir; girdiyi değiştirmez, diğer her şeyi sırasıyla korur."""
    sonuc = copy.deepcopy(mevcut)
    if "version" not in sonuc:
        sonuc = {"version": uretilen.get("version", 1), **sonuc}
    eski = sonuc.get("hooks", {})
    if not isinstance(eski, dict):
        raise AyristirmaHatasi("'hooks' alanı sözlük değil")
    yeni_u = uretilen.get("hooks") or {}
    hooks = {}
    for olay, liste in eski.items():
        if olay not in yeni_u:
            hooks[olay] = liste
            continue
        if not isinstance(liste, list):
            raise AyristirmaHatasi(f"'hooks.{olay}' liste değil")
        yeni, eklendi = [], False
        for g in liste:
            if orkestra_girdisi_mi(g, olay, kopya_koku):
                if not eklendi:
                    yeni.extend(copy.deepcopy(yeni_u[olay]))
                    eklendi = True
            else:
                yeni.append(g)
        if not eklendi:
            yeni.extend(copy.deepcopy(yeni_u[olay]))
        hooks[olay] = yeni
    for olay, liste in yeni_u.items():
        if olay not in hooks:
            hooks[olay] = copy.deepcopy(liste)
    sonuc["hooks"] = hooks
    return sonuc


def _oku(kullanici_yolu: str) -> tuple[bytes | None, dict]:
    """(ham bayt ya da None, ayrıştırılmış sözlük). Yok/boş dosya boş sözlüktür; bozuksa AyristirmaHatasi."""
    try:
        with open(kullanici_yolu, "rb") as f:
            ham = f.read()
    except FileNotFoundError:
        return None, {}
    govde = ham[len(_BOM):] if ham.startswith(_BOM) else ham
    if not govde.strip():
        return ham, {}
    try:
        veri = json.loads(govde.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise AyristirmaHatasi(str(e)) from e
    if not isinstance(veri, dict):
        raise AyristirmaHatasi("üst düzey JSON nesnesi değil")
    return ham, veri


def _yedekle(kullanici_yolu: str, yedek_koku: str) -> str:
    zaman = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    os.makedirs(yedek_koku, exist_ok=True)
    dizin, n = os.path.join(yedek_koku, zaman), 0
    while True:
        try:
            os.makedirs(dizin)
            break
        except FileExistsError:
            n += 1
            dizin = os.path.join(yedek_koku, f"{zaman}-{n}")
    yedek = os.path.join(dizin, "hooks.json")
    shutil.copy2(kullanici_yolu, yedek)
    _eski_yedekleri_sil(yedek_koku)
    return yedek


def _eski_yedekleri_sil(yedek_koku: str) -> None:
    try:
        yedekler = sorted(d for d in os.listdir(yedek_koku) if os.path.isdir(os.path.join(yedek_koku, d)))
    except OSError:
        return
    for d in yedekler[:-YEDEK_SAYISI]:
        shutil.rmtree(os.path.join(yedek_koku, d), ignore_errors=True)


def _atomik_yaz(yol: str, veri: bytes) -> None:
    dizin = os.path.dirname(os.path.abspath(yol))
    os.makedirs(dizin, exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=dizin, prefix=".hooks.json.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(veri)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, yol)
    except BaseException:
        if os.path.exists(gecici):
            os.remove(gecici)
        raise


def esitle(kullanici_yolu: str, kanonik_yol: str, kopya_koku: str, yedek_koku: str) -> tuple[str, str | None]:
    """Kullanıcı hooks.json'unu kanonikle eşler: (mesaj, yedek yolu | None). Bozuk dosyaya dokunmaz, istisna atmaz."""
    try:
        ham, mevcut = _oku(kullanici_yolu)
        hedef = birlestir(mevcut, uret(kanonik_yol, kopya_koku), kopya_koku)
    except AyristirmaHatasi as e:
        return f"{kullanici_yolu} ayrıştırılamıyor ({e}); dokunulmadı", None
    except (OSError, ValueError) as e:
        return f"{kullanici_yolu} eşlenemedi ({type(e).__name__}: {e}); dokunulmadı", None
    if ham is not None and not ham.startswith(_BOM) and mevcut == hedef:
        return f"zaten güncel ({kullanici_yolu})", None
    veri = (json.dumps(hedef, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        yedek = _yedekle(kullanici_yolu, yedek_koku) if ham is not None else None
        _atomik_yaz(kullanici_yolu, veri)
        with open(kullanici_yolu, "rb") as f:
            geri = f.read()
        if json.loads(geri.decode("utf-8")) != hedef:
            raise ValueError("geri okunan içerik yazılanla aynı değil")
    except (OSError, ValueError) as e:
        return f"{kullanici_yolu} yazılamadı ({type(e).__name__}: {e})", None
    return (f"güncellendi: {len(uret(kanonik_yol, kopya_koku)['hooks'])} Orkestra olayı ({kullanici_yolu}; "
            f"yedek: {yedek or 'yok, dosya yoktu'})"), yedek


def sapma(kullanici_yolu: str, kanonik_yol: str, kopya_koku: str) -> list[str]:
    """Kullanıcı dosyasının kanonikten sapmaları; güncelse boş liste. Dosyaya yazmaz."""
    try:
        ham, mevcut = _oku(kullanici_yolu)
    except AyristirmaHatasi as e:
        return [f"{kullanici_yolu} ayrıştırılamıyor ({e})"]
    if ham is None:
        return [f"{kullanici_yolu} yok"]
    uretilen = uret(kanonik_yol, kopya_koku)
    try:
        hedef = birlestir(mevcut, uretilen, kopya_koku)
    except AyristirmaHatasi as e:
        return [f"{kullanici_yolu} ayrıştırılamıyor ({e})"]
    sonuc = []
    if ham.startswith(_BOM):
        sonuc.append("dosya BOM'lu (Cursor BOM'suz UTF-8 bekler)")
    mevcut_hooks = mevcut.get("hooks") or {}
    for olay in uretilen["hooks"]:
        if olay not in mevcut_hooks:
            sonuc.append(f"{olay}: Orkestra girdisi yok")
        elif mevcut_hooks[olay] != hedef["hooks"][olay]:
            sonuc.append(f"{olay}: Orkestra girdisi kanonikten farklı ya da tekrarlı")
    if not sonuc and mevcut != hedef:
        sonuc.append("üst düzey alanlar kanonikten farklı (version)")
    return sonuc
