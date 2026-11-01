"""Panel ağır üretimlerinin işçi süreci (I-315, ADR-0133).

ozet, analitik ve isler üreticileri ~1-3 sn CPU yer ve Python GIL'i tutar; panel sunucusunun kendi süreci içinde koşunca
/saglik gibi hafif istekleri de bekletir. Bu modül üreticileri ayrı bir süreçte çalıştırır: panel yalnız sonucu alır.
Tek işçi süreç kullanılır (ağır işler sıraya girer, CPU fırtınası olmaz) ve defter önbelleği işçide sıcak kalır.
`ORKESTRA_PANEL_ISCI=0` eski davranışı (aynı süreçte hesap) verir."""
from __future__ import annotations

import concurrent.futures as cf
import multiprocessing as mp
import os
import threading

ZAMAN_ASIMI = 120.0  # sn: işçi bu sürede dönmezse havuz atılır ve üretim panel sürecinde yapılır
AGIR = ("ozet", "analitik", "isler", "analitik-tum")

_kilit = threading.Lock()
_havuz: cf.ProcessPoolExecutor | None = None


ETKIN = False  # yalnız gerçek panel sunucusu (calistir, durum_yaz=True) açar; testler ve içe aktarmalar aynı süreçte hesaplar


def aktif() -> bool:
    return ETKIN and os.environ.get("ORKESTRA_PANEL_ISCI") != "0"


def calistir(ad: str, alan: str | None):
    """İşçi süreçte koşar: üretici adı + alan kimliği -> sözlük."""
    import panel  # noqa: PLC0415  — işçi tarafında geç içe aktarım (modül yükleme döngüsü olmasın)
    if ad == "ozet":
        return panel._ozet_json(alan)
    if ad == "analitik":
        return panel._analitik_json(alan)
    if ad == "isler":
        return panel._isler_json(alan)
    if ad == "analitik-tum":
        return panel.analitik.tum_alanlar()
    raise ValueError(f"bilinmeyen ağır üretici: {ad}")


def _hazir() -> bool:
    import panel  # noqa: F401, PLC0415
    return True


def _havuz_al() -> cf.ProcessPoolExecutor:
    global _havuz
    with _kilit:
        if _havuz is None:
            _havuz = cf.ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"))
        return _havuz


def _havuzu_at() -> None:
    global _havuz
    with _kilit:
        h, _havuz = _havuz, None
    if h is not None:
        surecler = list((getattr(h, "_processes", None) or {}).values())  # shutdown sonrası sözlük boşalır: önce al
        h.shutdown(wait=False, cancel_futures=True)
        for p in surecler:  # takılı işçi arkada CPU yemesin
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass


def isitma() -> None:
    """Panel açılırken işçiyi önceden yükler (ilk ağır istek içe aktarma süresini beklemesin)."""
    if aktif():
        try:
            _havuz_al().submit(_hazir)
        except Exception:  # noqa: BLE001
            _havuzu_at()


def uret(ad: str, alan: str | None, yerel):
    """Ağır üreticiyi işçide koşturur; işçi yoksa/çökerse/süre aşılırsa `yerel()` ile panel sürecinde hesaplar."""
    if not aktif():
        return yerel()
    try:
        return _havuz_al().submit(calistir, ad, alan).result(timeout=ZAMAN_ASIMI)
    except Exception:  # noqa: BLE001 — BrokenProcessPool, zaman aşımı, ValueError: havuz yenilenir, istek düşmez
        _havuzu_at()
        return yerel()
