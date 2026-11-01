#!/usr/bin/env python3
"""Makine genelinde kaynak kirası (lease) ve ortak işçi bütçesi (I-309 P4, sözleşme S4).

Sorun: aynı makinede eşzamanlı iki tam test koşusu (`test_paralel.py`) her biri `paralel_kos.cekirdek_sayisi()` kadar
işçi açıyor; toplam işçi çekirdek ve belleği aşıyor, koşular birbirini görmüyor.

Yer kararı: durum `cfg.ev_dizini()/kaynak_kira/<kaynak>.json` (varsayılan ~/.claude/orkestra-makine; ORKESTRA_HOME ezer).
Neden proje durum klasörü (sd) değil: çakışan koşular farklı projelerden ve çalışma ağaçlarından gelir, bütçe makinenindir.
Testler ORKESTRA_KAYNAK_KIRA_DIZINI ile ayrı dizin seçer.

Sözleşme:
- Kayıt (`<kaynak>.json`) `ork_lib.kilit` (FIFO bilet) altında okunur ve yazılır; yeni kilit sistemi yoktur.
- Sahip kaydı: kimlik, pid, başlangıç, işçi sayısı, komut özeti, `son` (heartbeat). Sahip süreç arka plan iş parçacığıyla
  `sona_erme_s / 3` aralıkla `son`u yeniler.
- Ölü sahip: heartbeat `sona_erme_s`'yi aştı VE pid yaşamıyor; ya da heartbeat `3 x sona_erme_s`'yi aştı (pid yeniden
  kullanılmış ya da süreç askıda). Ölü kayıt silinir, sıradaki bekleyen devralır ve "devralındı" satırı yazar.
- Bütçe: `butce` (null ise `paralel_kos.cekirdek_sayisi()`); eşzamanlı sahiplerin işçi toplamı bütçeyi aşmaz.
  Bekleyenler FIFO'dur; yalnız kuyruğun başı, kalan bütçe istenene yetince (ya da hiç sahip yokken) girer.
- Kuyruğa giren koşu "kaynak kirası: sıra: N, sahip: <pid>/<komut özeti>" satırını yazar (N = sahip sayısı + kuyruk yeri).
- İç içe koşu (kira sahibinin alt süreci) ORKESTRA_KAYNAK_KIRA_SAHIP ortam değişkenini görür ve kira almaz (kilitlenme olmaz).
- Modlar (`ayarlar/kaynak_kira.json`; proje ezmesi `.claude/orkestra/kaynak_kira.json`; testte ORKESTRA_KAYNAK_KIRA_AYAR):
  * kapali: hiçbir şey yapılmaz, davranış eskisi gibi (ORKESTRA_KAYNAK_KIRA=0 da kapatır).
  * golge: kira ALINIR (sahip kaydı yazılır, başkaları görür) ama beklenmez ve işçi kısılmaz; bekleme gerekseydi
    sıra satırı ve gölge uyarısı yazılır, gunluk.jsonl'a `kapi_golge` düşer (`kapi_mod.kaydet`, P-028).
  * ihlal: kuyrukta beklenir; işçi sayısı bütçeyle kısılır; `bekleme_ust_s` aşılırsa KiraZamanAsimi.
`kapi_mod.mod` yalnız golge|ihlal tanır; `kapali` bu yüzden burada okunur, gölge kaydı yine `kapi_mod.kaydet` ile yazılır.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402
import ork_lib as L  # noqa: E402

KAPI = "kaynak_kira"
SAHIP_ENV = "ORKESTRA_KAYNAK_KIRA_SAHIP"
MODLAR = ("golge", "ihlal", "kapali")
VARSAYILAN = {"mod": "golge", "sona_erme_s": 30.0, "bekleme_ust_s": 1800.0, "yoklama_s": 0.25, "butce": None,
              "onbellek": False}
_KILIT_BEKLEME_S = 10.0


class KiraZamanAsimi(TimeoutError):
    """ihlal modunda bekleme üst sınırı aşıldı."""


@dataclass
class Kira:
    isci: int                 # koşucunun kullanacağı işçi sayısı
    mod: str                  # golge | ihlal | kapali | ic_ice
    sira: int = 0             # 0: beklemeden alındı; N: kuyruğa N. sırada girdi
    kimlik: str = ""
    devralinan: list = field(default_factory=list)  # devralınan ölü sahiplerin pid'leri


# ---------------------------------------------------------------- ayar ve yer

def _json(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def ayarlar(proje: str | None = None) -> dict:
    """Eklenti ayarı < proje ezmesi < ORKESTRA_KAYNAK_KIRA_AYAR dosyası; ORKESTRA_KAYNAK_KIRA=0 modu kapali yapar."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yollar = [os.path.join(kok, "ayarlar", KAPI + ".json")]
    sd = L.durum_dizini(proje or os.getcwd())
    if sd:
        yollar.append(os.path.join(sd, KAPI + ".json"))
    if os.environ.get("ORKESTRA_KAYNAK_KIRA_AYAR"):
        yollar.append(os.environ["ORKESTRA_KAYNAK_KIRA_AYAR"])
    d = dict(VARSAYILAN)
    for y in yollar:
        d.update({k: v for k, v in _json(y).items() if k in VARSAYILAN})
    if d.get("mod") not in MODLAR:
        d["mod"] = VARSAYILAN["mod"]
    if os.environ.get("ORKESTRA_KAYNAK_KIRA", "").strip() == "0":
        d["mod"] = "kapali"
    return d


def dizin() -> str:
    e = (os.environ.get("ORKESTRA_KAYNAK_KIRA_DIZINI") or "").strip()
    return os.path.abspath(e) if e else os.path.join(cfg.ev_dizini(), KAPI)


def _yol(kaynak: str) -> str:
    return os.path.join(dizin(), kaynak + ".json")


def butce(ayar: dict, proje: str | None = None) -> int:
    try:
        b = int(ayar.get("butce") or 0)
    except (TypeError, ValueError):
        b = 0
    if b >= 1:
        return b
    import paralel_kos
    return paralel_kos.cekirdek_sayisi(proje)


# ---------------------------------------------------------------- süreç canlılığı

def pid_canli(pid: int) -> bool:
    """Süreç yaşıyor mu. Windows'ta os.kill(pid, 0) süreci SONLANDIRIR; bu yüzden OpenProcess + GetExitCodeProcess."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.GetLastError() == 5  # erişim reddi: süreç var, başka kullanıcının
        try:
            kod = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(kod)):
                return True
            return kod.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _olu_mu(kayit: dict, simdi: float, sona_erme: float) -> bool:
    gecen = simdi - float(kayit.get("son") or 0)
    if gecen <= sona_erme:
        return False
    return gecen > 3 * sona_erme or not pid_canli(kayit.get("pid"))


# ---------------------------------------------------------------- kayıt

def _oku(yol: str) -> dict:
    d = _json(yol)
    return {"sahipler": [x for x in d.get("sahipler", []) if isinstance(x, dict)],
            "bekleyenler": [x for x in d.get("bekleyenler", []) if isinstance(x, dict)]}


def _yaz(yol: str, d: dict) -> None:
    L.atomik_yaz(yol, json.dumps(d, ensure_ascii=False, indent=1))


def _temizle(d: dict, simdi: float, sona_erme: float) -> list[dict]:
    """Ölü sahip ve bekleyenleri düşürür; düşen sahipleri döndürür (devralma bilgisi)."""
    olu = [s for s in d["sahipler"] if _olu_mu(s, simdi, sona_erme)]
    d["sahipler"] = [s for s in d["sahipler"] if s not in olu]
    d["bekleyenler"] = [b for b in d["bekleyenler"] if not _olu_mu(b, simdi, sona_erme)]
    return olu


def _komut_ozeti(komut: str | None) -> str:
    if not komut:
        komut = " ".join([os.path.basename(sys.argv[0] or "-")] + list(sys.argv[1:]))
    return L.maskele(" ".join(str(komut).split()))[:120]


def _ozet(s: dict) -> str:
    return f"{s.get('pid')}/{s.get('komut', '')}"


def durum(kaynak: str = "test_kosusu") -> dict:
    """Panel ve hook (P6) için anlık görüntü: sahipler, bekleyenler, bütçe kullanımı. Kilit almadan okur (salt okuma)."""
    d = _oku(_yol(kaynak))
    simdi = time.time()
    sona_erme = float(ayarlar().get("sona_erme_s") or VARSAYILAN["sona_erme_s"])
    for x in d["sahipler"] + d["bekleyenler"]:
        x["canli"] = not _olu_mu(x, simdi, sona_erme)
    d["kullanilan"] = sum(int(s.get("isci") or 0) for s in d["sahipler"] if s["canli"])
    return d


# ---------------------------------------------------------------- kira

def _golge_kaydet(proje: str | None, neden: str) -> None:
    try:
        import kapi_mod
        kapi_mod.kaydet(proje or os.getcwd(), KAPI, neden)
    except Exception:
        pass


@contextmanager
def kira(istenen: int, komut: str | None = None, kaynak: str = "test_kosusu", proje: str | None = None,
         cikti=None):
    """Kaynak kirası al; `with kira(n) as k:` içinde `k.isci` işçi kullan. Çıkışta kira bırakılır.
    `cikti`: sıra/devralma satırlarının yazıldığı akış (varsayılan sys.stdout)."""
    cikti = cikti or sys.stdout
    istenen = max(1, int(istenen))
    ayar = ayarlar(proje)
    mod = ayar["mod"]
    if mod == "kapali":
        yield Kira(isci=istenen, mod="kapali")
        return
    if os.environ.get(SAHIP_ENV):
        yield Kira(isci=istenen, mod="ic_ice", kimlik=os.environ[SAHIP_ENV])
        return

    sona_erme = max(0.5, float(ayar.get("sona_erme_s") or VARSAYILAN["sona_erme_s"]))
    bekleme_ust = float(ayar.get("bekleme_ust_s") or VARSAYILAN["bekleme_ust_s"])
    yoklama = max(0.02, float(ayar.get("yoklama_s") or VARSAYILAN["yoklama_s"]))
    b = butce(ayar, proje)
    isci = istenen if mod == "golge" else min(istenen, b)
    yol = _yol(kaynak)
    kimlik = f"{os.getpid()}-{time.time_ns()}"
    ben = {"kimlik": kimlik, "pid": os.getpid(), "baslangic": L.simdi(), "isci": isci, "istenen": istenen,
           "komut": _komut_ozeti(komut), "son": time.time()}
    k = Kira(isci=isci, mod=mod, kimlik=kimlik)

    def yaz(satir):
        try:
            print(satir, file=cikti, flush=True)
        except Exception:
            pass

    def girebilir(d):
        kullanilan = sum(int(s.get("isci") or 0) for s in d["sahipler"])
        bas = d["bekleyenler"][0]["kimlik"] if d["bekleyenler"] else kimlik
        return bas == kimlik and (not d["sahipler"] or kullanilan + isci <= b)

    def devral_yaz(olu):
        for s in olu:
            k.devralinan.append(s.get("pid"))
            yaz(f"kaynak kirası: ölü sahip düşürüldü, devralındı: {_ozet(s)}")

    # 1) ilk deneme: hemen gir ya da kuyruğa yazıl
    with L.kilit(yol, bekleme_s=_KILIT_BEKLEME_S):
        d = _oku(yol)
        devral_yaz(_temizle(d, time.time(), sona_erme))
        if girebilir(d) or mod == "golge":
            if not girebilir(d):  # golge: bekleme gerekirdi, beklenmez
                k.sira = len(d["sahipler"]) + len(d["bekleyenler"]) + 1
                sahip = _ozet(d["sahipler"][0]) if d["sahipler"] else _ozet(d["bekleyenler"][0])
                neden = f"sıra: {k.sira}, sahip: {sahip}"
                yaz(f"kaynak kirası: {neden}")
                yaz(f"orkestra (gölge, {KAPI}): ihlal modunda bu koşu kuyrukta beklerdi; beklenmeden sürüyor")
                _golge_kaydet(proje, neden)
            d["sahipler"].append(ben)
            alindi = True
        else:
            d["bekleyenler"].append(ben)
            k.sira = len(d["sahipler"]) + len(d["bekleyenler"])
            sahip = _ozet(d["sahipler"][0]) if d["sahipler"] else _ozet(d["bekleyenler"][0])
            yaz(f"kaynak kirası: sıra: {k.sira}, sahip: {sahip}")
            alindi = False
        _yaz(yol, d)

    # 2) ihlal: kuyrukta bekle (bekleyen de heartbeat yazar, yoksa ölü sayılır)
    basla = time.time()
    try:
        while not alindi:
            time.sleep(yoklama)
            try:
                with L.kilit(yol, bekleme_s=_KILIT_BEKLEME_S):
                    d = _oku(yol)
                    simdi = time.time()
                    devral_yaz(_temizle(d, simdi, sona_erme))
                    if not any(x["kimlik"] == kimlik for x in d["bekleyenler"]):
                        d["bekleyenler"].append(ben)  # başkası ölü sandıysa sona yeniden yazıl
                    for x in d["bekleyenler"]:
                        if x["kimlik"] == kimlik:
                            x["son"] = simdi
                    if girebilir(d):
                        d["bekleyenler"] = [x for x in d["bekleyenler"] if x["kimlik"] != kimlik]
                        ben["son"] = simdi
                        d["sahipler"].append(ben)
                        _yaz(yol, d)
                        alindi = True
                        break
                    if simdi - basla > bekleme_ust:
                        raise KiraZamanAsimi(f"kaynak kirası {bekleme_ust:g} sn içinde alınamadı; sahip: "
                                             + (_ozet(d["sahipler"][0]) if d["sahipler"] else "-"))
                    _yaz(yol, d)
            except TimeoutError as e:
                if isinstance(e, KiraZamanAsimi):
                    raise
                continue  # kayıt kilidi o an alınamadı; yeniden yokla
    finally:
        # Her çıkış yolunda (zaman aşımı, KeyboardInterrupt, SystemExit, beklenmeyen hata) bekleyen kaydı silinir;
        # silinmezse kuyruk başı sona_erme_s boyunca tıkanır.
        if not alindi:
            _bekleyen_sil(yol, kimlik)
    if k.sira:
        yaz(f"kaynak kirası: alındı ({time.time() - basla:.1f} sn beklendi, işçi: {isci})")

    # 3) sahiplik: heartbeat
    dur = threading.Event()

    def kalp():
        while not dur.wait(sona_erme / 3):
            try:
                with L.kilit(yol, bekleme_s=_KILIT_BEKLEME_S):
                    d = _oku(yol)
                    for s in d["sahipler"]:
                        if s["kimlik"] == kimlik:
                            s["son"] = time.time()
                            break
                    else:
                        ben["son"] = time.time()
                        d["sahipler"].append(ben)  # yanlışlıkla düşürüldüyse yeniden yazıl
                    _yaz(yol, d)
            except Exception:
                pass

    t = threading.Thread(target=kalp, name="kaynak_kira_kalp", daemon=True)
    t.start()
    onceki = os.environ.get(SAHIP_ENV)
    os.environ[SAHIP_ENV] = kimlik
    try:
        yield k
    finally:
        if onceki is None:
            os.environ.pop(SAHIP_ENV, None)
        else:
            os.environ[SAHIP_ENV] = onceki
        dur.set()
        t.join(timeout=2)
        try:
            with L.kilit(yol, bekleme_s=_KILIT_BEKLEME_S):
                d = _oku(yol)
                d["sahipler"] = [s for s in d["sahipler"] if s.get("kimlik") != kimlik]
                _yaz(yol, d)
        except Exception:
            pass  # bırakılamadıysa heartbeat durduğu için sona erme süresinde düşer


if __name__ == "__main__":
    print(json.dumps(durum(sys.argv[1] if len(sys.argv) > 1 else "test_kosusu"), ensure_ascii=False, indent=1))
