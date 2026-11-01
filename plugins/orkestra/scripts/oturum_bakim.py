"""SessionStart bakım koşucusu (ADR-0092, I-255): ağır bakım işleri hook'un kritik yolundan çıkar.

Hook yalnız `baslat` çağırır (alt süreç başlatmaz sayılır: tek ayrık Popen, beklenmez); işler ayrık süreçte `calistir` ile
kilit altında ve en çok ARA sn'de bir koşar. Uyarı üreten sonuç (bayatlık) `onbellek`ten sonraki oturumda okunur.
ORKESTRA_OTURUM_BAKIM=0 eski eşzamanlı yolu geri açar (hook.py session_start).
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402
import ork_lib as L  # noqa: E402

ARA = 3600  # sn: bakım işleri en çok bu aralıkta bir koşar
ISARET = "oturum_bakim.json"  # son başlatma zamanı (dosya mtime'ı aralığı belirler)
ONBELLEK = "bakim_onbellek.json"
KILIT = "oturum_bakim_kos"


def etkin() -> bool:
    return (os.environ.get("ORKESTRA_OTURUM_BAKIM") or "").strip() != "0"


def baslat(sd: str, cwd: str) -> bool:
    """Aralık dolduysa bakım koşucusunu ayrık süreçte başlatır ve beklemez. Hatada sessiz False (hook'u düşürmez)."""
    if not etkin() or not sd:
        return False
    isaret = os.path.join(sd, ISARET)
    try:
        with L.kilit(isaret, bekleme_s=0.5):
            try:
                if time.time() - os.path.getmtime(isaret) < ARA:
                    return False
            except OSError:
                pass
            L.atomik_yaz(isaret, json.dumps({"zaman": L.simdi()}))
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--sd", sd, "--cwd", cwd or ""],
                         creationflags=cfg.ARKA_PLAN_BAYRAK, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
        return True
    except Exception:  # noqa: BLE001  (TimeoutError, OSError: bakım bir sonraki oturuma kalır)
        return False


def onbellek(sd: str) -> dict:
    """Son bakım koşusunun sonucu (örn. bayatlık); yoksa {}."""
    try:
        with open(os.path.join(sd, ONBELLEK), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _u_maliyet(sd: str, cwd: str):
    import maliyet_anomali as MA
    olay = [x for x in MA.calistir(sd, 1) if x["kural"] in ("K3", "K4", "K5")]
    if olay:
        return "MALİYET: " + ", ".join(f"{x['kural']} {x['kart']}" for x in olay[:3]) + " (`orkestra maliyet anomali --gun 1`)"


def _u_hata(sd: str, cwd: str):
    import hata_en_cok as HE
    return HE.esik_satiri(sd) or None


def _u_iz(sd: str, cwd: str):
    import iz as IZ
    if IZ.kapsama_satiri(sd):
        return "iz kapsama eşik aşımı (`orkestra iz kapsama`)"


def _u_todo(sd: str, cwd: str):
    import is_kaydi
    if is_kaydi.todo_denetle_satiri(sd, L.proje_dizini(cwd)):
        return "işe bağlı olmayan todo dosyası var (`orkestra is todo-denetle`)"


def _u_devral(sd: str, cwd: str):
    import is_kaydi
    if is_kaydi.devral_ipucu(sd, cwd):
        return "worktree durum kopyasında devralınmamış kayıt var (`orkestra durum devral`)"


# SessionStart uyarıları: her biri 0,3-0,7 sn tutan, günlük/saatlik değişen bilgilendirme kontrolleri (ADR-0145).
UYARI_ADIMLARI = (("uyari_maliyet", _u_maliyet), ("uyari_hata", _u_hata), ("uyari_iz", _u_iz),
                  ("uyari_todo", _u_todo), ("uyari_devral", _u_devral))


def yavas_uyarilar(sd: str, cwd: str | None) -> list[str]:
    """Bakım açıkken son koşunun önbelleğindeki uyarı satırları (hook'ta hesap yok); kapalıyken eşzamanlı hesap."""
    if etkin():
        c = onbellek(sd)
        return [c[ad] for ad, _ in UYARI_ADIMLARI if isinstance(c.get(ad), str) and c[ad]]
    cikti = []
    for _, f in UYARI_ADIMLARI:
        try:
            v = f(sd, cwd)
        except Exception:  # noqa: BLE001
            v = None
        if v:
            cikti.append(v)
    return cikti


def _adimlar(sd: str, cwd: str) -> list:
    """(ad, çağrılabilir) listesi; dönen değer varsa önbelleğe ad anahtarıyla yazılır."""
    import dal_temizle
    import etki
    import panel_servis

    return [
        ("panel_servis", panel_servis.otomatik_kur),
        ("tmp_temizle", lambda: L.tmp_temizle(sd)),
        ("dal_temizle", lambda: dal_temizle.calistir(cwd or os.getcwd(), kaynak="oturum_bakim") and None),
        ("etki_izle", lambda: etki.izle(sd) and None),
        ("bayatlik", L.bayatlik),
    ] + [(ad, (lambda f=f: f(sd, cwd))) for ad, f in UYARI_ADIMLARI]


def _kilit_al(sd: str):
    """Koşu kilidi; başka kopya koşuyorsa None. Dönen nesne `with`/close ile bırakılır."""
    yigin = contextlib.ExitStack()
    try:
        yigin.enter_context(L.kilit(os.path.join(sd, KILIT), bekleme_s=0.1))
        return yigin
    except Exception:  # noqa: BLE001
        yigin.close()
        return None


def _hata_yaz(sd: str, adim: str, e: BaseException) -> None:
    try:
        import hata_kayit
        hata_kayit.kaydet(sd, "oturum_bakim", "bakim-adimi", f"{adim}: {type(e).__name__}: {e}"[:300])
    except Exception:  # noqa: BLE001
        pass


def calistir(sd: str, cwd: str) -> bool:
    """Bakım adımlarını sırayla koşar; bir adımın hatası ötekileri durdurmaz. Kilit başkasındaysa False."""
    kilit = _kilit_al(sd)
    if kilit is None:
        return False
    with kilit:
        sonuc: dict = {}
        for ad, f in _adimlar(sd, cwd):
            try:
                v = f()
                if v is not None:
                    sonuc[ad] = v
            except BaseException as e:  # noqa: BLE001  (panel_servis.kur SystemExit ile hata bildirir)
                _hata_yaz(sd, ad, e)
        try:
            L.atomik_yaz(os.path.join(sd, ONBELLEK), json.dumps({"zaman": L.simdi(), **sonuc}, ensure_ascii=False))
        except OSError:
            pass
    return True


def main(argv: list[str]) -> int:
    sd = cwd = ""
    for i, a in enumerate(argv):
        if a == "--sd" and i + 1 < len(argv):
            sd = argv[i + 1]
        elif a == "--cwd" and i + 1 < len(argv):
            cwd = argv[i + 1]
    if sd:
        calistir(sd, cwd)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
