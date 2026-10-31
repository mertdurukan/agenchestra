#!/usr/bin/env python3
"""Test sonucu önbelleği ve tek uçuş (single-flight) (I-309 P5, sözleşme S5).

Sorun: aynı makinede aynı kod için aynı test kümesi art arda ya da eşzamanlı istenince her istek yeni bir tam koşu
açıyor; P4 kirası (kaynak_kira.py) koşuları sıraya koyar ama aynı işi iki kez yaptırır.

Davranış (`test_paralel.py` koşucu havuzunu ve kirayı açmadan ÖNCE çağırır):
1) Aynı anahtarla GEÇEN bir sonuç varsa (GECERLILIK_S içinde) yeni test süreci açılmaz; kayıtlı çıktı ve
   "önbellekten" satırı döner.
2) Aynı anahtarla süren bir koşu varsa (sahip kaydı canlı) yeni süreç açılmaz; bitmesi beklenir ve onun sonucu döner
   (geçtiyse "önbellekten (tek uçuş)", düştüyse "tek uçuş" satırıyla, düşen sonuç saklanmaz).
3) Yalnız GEÇEN (çıkış 0) sonuç önbelleğe yazılır; düşen, zaman aşan ya da yarıda kalan koşu yazılmaz.

Anahtar nasıl türer ve neden (bayat "geçti" en büyük risktir; her belirsizlikte anahtar DEĞİŞMELİ, isabet kaçmalı):
- Test kümesi: koşulacak test dosyalarının mutlak yolları (sıralı). Farklı küme farklı sonuçtur.
- İçerik özeti: eklenti kökünün TAMAMI (scripts/, tests/, ayarlar/ yanında hooks/, kurallar/, sablonlar/... çünkü testler
  bunları da okur) özyinelemeli, her dosyanın göreli yolu + sha256 içeriği. mtime kullanılmaz: dokunma (touch) isabeti
  bozmaz, içerik değişikliği her zaman bozar. Eklenti kökü dışındaki test dosyalarının klasörü (özyinelemesiz, yardımcı
  modüller dahil) ve üst klasörlerdeki pytest yapılandırması (conftest.py, pytest.ini, pyproject.toml, setup.cfg,
  tox.ini) da girer. Dışlananlar yalnız çalışma artığıdır: __pycache__, .git, .pytest_cache, node_modules, sd/ (çalışma
  durumu), *.pyc/*.pyo/*.lock/*.log. Yeni ya da silinen dosya yol listesini değiştirdiği için anahtarı da değiştirir.
- Yorumlayıcı: sys.version, sys.executable ve pytest sürümü.
- Komut: test_paralel.py'nin ayrıştırılmış argümanları (-n, --zaman-asimi, --en-yavas; çıktı biçimini de etkiler).
- Ortam: ORKESTRA_*, PYTHON*, PYTEST_* değişkenleri (kapı bayrakları testleri değiştirir) ve çalışma dizini. Değerler
  yalnız özete girer, diske yazılmaz (sır sızmaz). Her koşuda değişen sahip kimlikleri (kira, tek uçuş) dışlanır.
Anahtarın göremediği girdiler (kurulu paketler, işletim sistemi durumu, saate bağlı testler) GECERLILIK_S ile sınırlanır.

Mod (`ayarlar/kaynak_kira.json` `onbellek` alanı; proje ezmesi ve ORKESTRA_KAYNAK_KIRA_AYAR kaynak_kira.ayarlar ile):
- false | "kapali": hiçbir şey yapılmaz. ORKESTRA_TEST_ONBELLEK=0 da kapatır.
- "golge" (varsayılan, P-028): anahtar hesaplanır, geçen sonuç yazılır; isabet ya da beklenecek koşu olsaydı satır
  yazılır ve gunluk.jsonl'a `kapi_golge` düşer, ama koşu YİNE yapılır. Gölge koşusu isabetin doğru olup olmadığını da
  ölçer: önbellek "geçti" derken koşu düşerse "BAYAT isabet" kaydı düşer. ihlal geçişi bu sayı 0 iken ayrı kararla.
- true | "ihlal": isabet ve tek uçuş gerçekten uygulanır.
Gerekçe: önbellek bir kapı gibi davranışı değiştirir (koşuyu atlar) ve en büyük riski (bayat geçti) ancak gerçek koşuyla
yan yana ölçülerek görülür; kapi_mod'un golge -> ihlal düzeni buna birebir uyar. `kapi_mod.mod` bool tanımadığı için mod
burada okunur, gölge kaydı yine `kapi_mod.kaydet` ile yazılır.

İç içe koşu: lider ORKESTRA_TEST_ONBELLEK_ATALAR'a kendi anahtarını ekler; aynı anahtarlı alt koşu kendini beklemez.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import kaynak_kira  # noqa: E402

KAPI = "test_onbellek"
KAPAT_ENV = "ORKESTRA_TEST_ONBELLEK"
KOKLER_ENV = "ORKESTRA_TEST_ONBELLEK_KOKLER"  # testler için: eklenti kökü yerine özetlenecek kökler (os.pathsep ile)
ATALAR_ENV = "ORKESTRA_TEST_ONBELLEK_ATALAR"
EKLENTI_KOKU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Gerekçe: anahtar kodu ve ayarı tam kapsar; 1 saat yalnız anahtarın göremediği girdileri (paket kurulumu, sistem, saat)
# sınırlar, bir çalışma oturumundaki tekrarları (aynı tur içinde denetçi + is-bitti) karşılayacak kadar uzundur.
GECERLILIK_S = 3600.0
# Gerekçe: kayıt başına çıktı tam takımda ~1 MB'a varabilir; 50 kayıt (~50 MB üst sınır) birkaç çalışma ağacını ve
# test içi geçici koşuları taşır, en eskiler düşer.
EN_COK_KAYIT = 50
DISLA_DIZIN = {"__pycache__", ".git", ".pytest_cache", "node_modules", ".mypy_cache", ".ruff_cache", "sd"}
DISLA_UZANTI = (".pyc", ".pyo", ".lock", ".log")
YAPILANDIRMA = ("conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")
ORTAM_ONEKLERI = ("ORKESTRA_", "PYTHON", "PYTEST_")
ORTAM_DISLA = {kaynak_kira.SAHIP_ENV, ATALAR_ENV}


# ---------------------------------------------------------------- mod

def mod(proje: str | None = None) -> str:
    """kapali | golge | ihlal (`onbellek` alanı: false/true da kabul edilir)."""
    if os.environ.get(KAPAT_ENV, "").strip() == "0":
        return "kapali"
    v = kaynak_kira.ayarlar(proje).get("onbellek")
    if v is True or v == "ihlal":
        return "ihlal"
    if v == "golge":
        return "golge"
    return "kapali"


# ---------------------------------------------------------------- anahtar

def _dosya_ozeti(yol: str) -> str:
    h = hashlib.sha256()
    try:
        with open(yol, "rb") as f:
            for parca in iter(lambda: f.read(1 << 20), b""):
                h.update(parca)
    except OSError:
        return "okunamadi"
    return h.hexdigest()


def _dislanir(ad: str) -> bool:
    return ad.endswith(DISLA_UZANTI) or ad.startswith(".tmp_")


def _agac(h, kok: str, ozyineli: bool = True) -> int:
    """Kökteki dosyaların göreli yolu + içerik özeti, sıralı; dosya sayısı döner."""
    kok = os.path.abspath(kok)
    if not os.path.isdir(kok):
        h.update(f"yok:{os.path.normcase(kok)}\0".encode())
        return 0
    satirlar = []
    for d, altlar, dosyalar in os.walk(kok):
        altlar[:] = sorted(x for x in altlar if x not in DISLA_DIZIN) if ozyineli else []
        for ad in dosyalar:
            if not _dislanir(ad):
                tam = os.path.join(d, ad)
                satirlar.append((os.path.relpath(tam, kok).replace("\\", "/"), _dosya_ozeti(tam)))
    h.update(f"kok:{os.path.normcase(kok)}\0".encode())
    for g, o in sorted(satirlar):
        h.update(f"{g}\0{o}\0".encode())
    return len(satirlar)


def _altinda(yol: str, kok: str) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(os.path.abspath(yol)), os.path.normcase(os.path.abspath(kok))]) \
            == os.path.normcase(os.path.abspath(kok))
    except ValueError:
        return False


def _pytest_surumu() -> str:
    try:
        from importlib import metadata
        return metadata.version("pytest")
    except Exception:
        return "-"


def kokler() -> list[str]:
    e = (os.environ.get(KOKLER_ENV) or "").strip()
    return [os.path.abspath(x) for x in e.split(os.pathsep) if x.strip()] if e else [EKLENTI_KOKU]


def anahtar(dosyalar: list[str], argumanlar: dict, kok_listesi: list[str] | None = None) -> tuple[str, dict]:
    """(sha256 anahtar, bilgi). Türeyiş ve gerekçe: dosya başı."""
    h = hashlib.sha256(b"test_onbellek/1\0")
    kok_listesi = kok_listesi if kok_listesi is not None else kokler()
    sayi = 0
    for k in sorted(set(os.path.abspath(x) for x in kok_listesi)):
        sayi += _agac(h, k)
    mutlak = sorted(set(os.path.abspath(f) for f in dosyalar))
    h.update(b"kume\0")
    for f in mutlak:
        h.update(f"{os.path.normcase(f)}\0{_dosya_ozeti(f)}\0".encode())
    disarida = sorted({os.path.dirname(f) for f in mutlak if not any(_altinda(f, k) for k in kok_listesi)})
    for d in disarida:
        sayi += _agac(h, d, ozyineli=False)
    yapilandirma = set()
    for d in {os.path.dirname(f) for f in mutlak}:
        while True:
            for ad in YAPILANDIRMA:
                y = os.path.join(d, ad)
                if os.path.isfile(y):
                    yapilandirma.add(y)
            ust = os.path.dirname(d)
            if ust == d:
                break
            d = ust
    for y in sorted(yapilandirma):
        h.update(f"yap:{os.path.normcase(y)}\0{_dosya_ozeti(y)}\0".encode())
    h.update(f"py:{sys.version}\0{os.path.normcase(sys.executable)}\0pytest:{_pytest_surumu()}\0".encode())
    h.update(("arg:" + json.dumps(argumanlar, sort_keys=True, default=str, ensure_ascii=False) + "\0").encode())
    h.update(f"cwd:{os.path.normcase(os.path.abspath(os.getcwd()))}\0".encode())
    for k in sorted(os.environ):
        if k.upper().startswith(ORTAM_ONEKLERI) and k not in ORTAM_DISLA:
            h.update(f"env:{k}={os.environ[k]}\0".encode())
    return h.hexdigest(), {"dosya": sayi + len(mutlak) + len(yapilandirma), "test_dosyasi": len(mutlak)}


# ---------------------------------------------------------------- kayıt

def dizin() -> str:
    return os.path.join(kaynak_kira.dizin(), "onbellek")


def _yol(anahtar_: str, tur: str = "") -> str:
    return os.path.join(dizin(), anahtar_ + (("." + tur) if tur else "") + ".json")


def _oku(yol: str) -> dict | None:
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def _sil(yol: str) -> None:
    try:
        os.remove(yol)
    except OSError:
        pass


def isabet(anahtar_: str) -> dict | None:
    """Geçerli ve GEÇEN kayıt; yoksa None."""
    v = _oku(_yol(anahtar_))
    if not v or v.get("kod") != 0 or v.get("anahtar") != anahtar_:
        return None
    if time.time() - float(v.get("bitis") or 0) > GECERLILIK_S:
        return None
    return v


def _buda() -> None:
    try:
        kayitlar = []
        for ad in os.listdir(dizin()):
            if not ad.endswith(".json") or ad.startswith(".tmp_"):
                continue
            tam = os.path.join(dizin(), ad)
            yas = time.time() - os.path.getmtime(tam)
            if ad.endswith(".suren.json"):
                continue
            if yas > GECERLILIK_S:
                _sil(tam)
            elif ad.count(".") == 1:
                kayitlar.append((yas, tam))
        for _, tam in sorted(kayitlar)[EN_COK_KAYIT:]:
            _sil(tam)
    except OSError:
        pass


def _canli_suren(v: dict | None, sona_erme: float) -> bool:
    return bool(v) and not kaynak_kira._olu_mu(v, time.time(), sona_erme)


# ---------------------------------------------------------------- tek uçuş

@dataclass
class Ucus:
    anahtar: str
    mod: str
    sonuc: dict | None = None          # doluysa koşma: {"kod", "cikti", "satir"}
    lider: bool = False
    golge_isabet: dict | None = None
    notlar: list = field(default_factory=list)
    _kaydedildi: bool = False

    def kaydet(self, kod: int, cikti: str, sure: float = 0.0) -> None:
        """Koşu sonucu: GEÇENse önbelleğe, her durumda bekleyenler için `.son` kaydına."""
        if self.mod == "kapali" or self._kaydedildi:
            return
        self._kaydedildi = True
        kayit = {"anahtar": self.anahtar, "kod": int(kod), "cikti": cikti, "bitis": time.time(), "sure": round(sure, 2),
                 "zaman": L.simdi(), "pid": os.getpid()}
        try:
            with L.kilit(_yol(self.anahtar), bekleme_s=10.0):
                if kod == 0:
                    L.atomik_yaz(_yol(self.anahtar), json.dumps(kayit, ensure_ascii=False))
                if self.lider:
                    L.atomik_yaz(_yol(self.anahtar, "son"), json.dumps(kayit, ensure_ascii=False))
            _buda()
        except (OSError, TimeoutError):
            pass


def _yas(v: dict) -> str:
    return f"{max(0.0, time.time() - float(v.get('bitis') or 0)):.0f} sn önce"


@contextmanager
def tek_ucus(anahtar_: str, proje: str | None = None, cikti=None):
    """`with tek_ucus(k) as u:` -> `u.sonuc` doluysa koşma, onu bas; değilse koş ve `u.kaydet(kod, cikti)`."""
    cikti = cikti or sys.stdout
    m = mod(proje)
    u = Ucus(anahtar=anahtar_, mod=m)
    if m == "kapali":
        yield u
        return

    def yaz(s):
        try:
            print(s, file=cikti, flush=True)
        except Exception:
            pass

    def golge(neden):
        u.notlar.append(neden)
        yaz(f"orkestra (gölge, {KAPI}): {neden}; yine koşuluyor")
        try:
            import kapi_mod
            kapi_mod.kaydet(proje or os.getcwd(), KAPI, f"{neden} [{anahtar_[:12]}]")
        except Exception:
            pass

    ayar = kaynak_kira.ayarlar(proje)
    sona_erme = max(0.5, float(ayar.get("sona_erme_s") or 30))
    bekleme_ust = float(ayar.get("bekleme_ust_s") or 1800)
    yoklama = max(0.02, float(ayar.get("yoklama_s") or 0.25))
    kimlik = f"{os.getpid()}-{time.time_ns()}"
    ben = {"kimlik": kimlik, "pid": os.getpid(), "son": time.time(), "baslangic": L.simdi()}
    ic_ice = anahtar_ in (os.environ.get(ATALAR_ENV) or "").split(",")
    yol, suren_yol, son_yol = _yol(anahtar_), _yol(anahtar_, "suren"), _yol(anahtar_, "son")
    basla = time.time()
    beklenen = None  # beklenen liderin kimliği
    try:
        while True:
            with L.kilit(yol, bekleme_s=10.0):
                v = isabet(anahtar_)
                if v and m == "ihlal":
                    satir = f"önbellekten: {anahtar_[:12]} ({_yas(v)} geçti, kaynak koşu {v.get('sure', 0):g} sn)"
                    if beklenen:
                        satir = f"önbellekten (tek uçuş): süren aynı koşu beklendi ({time.time() - basla:.1f} sn), " \
                                f"{anahtar_[:12]}"
                    u.sonuc = {"kod": 0, "cikti": v.get("cikti", ""), "satir": satir}
                    break
                son = _oku(son_yol) if beklenen else None
                if son and son.get("kimlik_lider") == beklenen:
                    u.sonuc = {"kod": int(son.get("kod", 1)), "cikti": son.get("cikti", ""),
                               "satir": f"tek uçuş: süren aynı koşunun sonucu döndü (çıkış {son.get('kod')}; düşen "
                                        f"sonuç önbelleğe alınmaz), {anahtar_[:12]}"}
                    break
                suren = _oku(suren_yol)
                baskasi = _canli_suren(suren, sona_erme) and suren.get("kimlik") != kimlik and not ic_ice
                if m == "golge":
                    if v:
                        u.golge_isabet = v
                        golge(f"isabet olurdu ({_yas(v)} geçti)")
                    if baskasi:
                        golge(f"tek uçuş: süren aynı koşu beklenirdi (pid {suren.get('pid')})")
                    else:
                        L.atomik_yaz(suren_yol, json.dumps(ben))
                        u.lider = True
                    break
                if not baskasi or time.time() - basla > bekleme_ust:
                    if baskasi:
                        yaz(f"tek uçuş: {bekleme_ust:g} sn beklendi, süren koşu bitmedi; ayrı koşuluyor")
                    else:
                        L.atomik_yaz(suren_yol, json.dumps(ben))
                        u.lider = True
                    break
                if beklenen != suren.get("kimlik"):
                    beklenen = suren.get("kimlik")
                    yaz(f"tek uçuş: aynı girdili koşu sürüyor (pid {suren.get('pid')}), bitmesi bekleniyor")
            time.sleep(yoklama)
    except TimeoutError:
        pass  # kayıt kilidi alınamadı: önbelleksiz koş (güvenli yön)

    if u.sonuc is not None:
        yaz_satir = u.sonuc["satir"]
        u.sonuc["satir"] = yaz_satir
        yield u
        return

    dur = threading.Event()
    t = None
    if u.lider:
        def kalp():
            while not dur.wait(sona_erme / 3):
                try:
                    ben["son"] = time.time()
                    L.atomik_yaz(suren_yol, json.dumps(ben))
                except OSError:
                    pass
        t = threading.Thread(target=kalp, name="test_onbellek_kalp", daemon=True)
        t.start()
    onceki = os.environ.get(ATALAR_ENV)
    os.environ[ATALAR_ENV] = ",".join(x for x in [onceki, anahtar_] if x)
    orijinal_kaydet = u.kaydet

    def kaydet(kod, cikti_metni, sure=0.0):
        if u.lider and not u._kaydedildi:
            # `.son` kaydı lider kimliğini taşır: bekleyen yalnız beklediği liderin sonucunu alır
            kayit_kimlik[0] = kimlik
        orijinal_kaydet(kod, cikti_metni, sure)
        if u.golge_isabet is not None and int(kod) != 0:
            golge(f"BAYAT isabet: önbellek geçti diyordu, koşu düştü (çıkış {kod})")

    kayit_kimlik = [None]
    u.kaydet = kaydet
    try:
        yield u
    finally:
        if onceki is None:
            os.environ.pop(ATALAR_ENV, None)
        else:
            os.environ[ATALAR_ENV] = onceki
        dur.set()
        if t:
            t.join(timeout=2)
        if u.lider:
            try:
                with L.kilit(yol, bekleme_s=10.0):
                    son = _oku(son_yol)
                    if son is not None and son.get("pid") == os.getpid() and "kimlik_lider" not in son:
                        son["kimlik_lider"] = kimlik
                        L.atomik_yaz(son_yol, json.dumps(son, ensure_ascii=False))
                    s = _oku(suren_yol)
                    if s and s.get("kimlik") == kimlik:
                        _sil(suren_yol)
            except (OSError, TimeoutError):
                pass  # sahip kaydı heartbeat durduğu için sona erme süresinde ölü sayılır
