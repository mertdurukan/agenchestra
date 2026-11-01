"""orkestra komutları: kart (orkestra.py bölünmesinden)."""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import hashlib
import os
import re
import subprocess
import cfg  # noqa: E402
import sys
import time

import ork_lib as L  # noqa: E402
import plan_modeli_doldur as PM  # noqa: E402
import duzeltme_kapisi as DK  # noqa: E402
import gorev_turleri as GT  # noqa: E402
import kapi_mod as KM  # noqa: E402
import ret_nedeni as RN  # noqa: E402
import soru_sinif as SS  # noqa: E402
from komutlar._ortak import BASAMAKLAR, BETIK_DIZINI, hata, oturum_id, sd_gerekli  # noqa: E402
from komutlar.isler import _acik_is_dogrula, _ik, _kart_is_bag_kur, _kart_is_bagla, _merkez_saglamla  # noqa: E402


def _kart_al(sd, gid):
    k = L.kart_oku(sd, gid)
    if not k:
        hata(f"kart yok: {gid}")
    return k


RISKLER = ("dusuk", "orta", "yuksek")
EFFORTLAR = ("low", "medium", "high", "xhigh")


def _effort_dogrula(d: dict):
    """I-058: verilmediyse None (alan yazılmaz); geçersizse hata."""
    e = d.get("effort")
    if e is None:
        return None
    if not isinstance(e, str) or e not in EFFORTLAR:
        hata(f"effort {'|'.join(EFFORTLAR)} olmalı: {e!r} ({d.get('baslik') or '(başlıksız)'})")
    return e


def _risk_dogrula(d: dict):
    """N3: verilmediyse None (alan yazılmaz); geçersizse hata."""
    r = d.get("risk")
    if r is None:
        return None
    if not isinstance(r, str) or r not in RISKLER:
        hata(f"risk dusuk|orta|yuksek olmalı: {r!r} ({d.get('baslik') or '(başlıksız)'})")
    return r


def _sayi_dogrula(ad: str, v, tam: bool):
    if v is None:
        return None
    try:
        if isinstance(v, bool):
            raise ValueError
        n = float(v)
        if tam:
            if n != int(n) or (isinstance(v, str) and not re.fullmatch(r"\s*\d+\s*", v)):
                raise ValueError
            n = int(n)
        elif n == int(n) and isinstance(v, int):
            n = int(v)
    except (TypeError, ValueError, OverflowError):
        hata(f"{ad} {'tam sayı' if tam else 'sayı'} olmalı: {v!r}")
    if n < 0:
        hata(f"{ad} negatif olamaz: {v!r}")
    return n


def _butce_dogrula(d: dict):
    """N4: yalnız kayıt. {usd, token} (ikisi de isteğe bağlı) -> {usd, token, kaynak:'elle', esik_surumu:None}."""
    b = d.get("butce")
    if b is None:
        return None
    if not isinstance(b, dict):
        hata(f"butce {{usd, token}} nesnesi olmalı: {b!r}")
    usd = _sayi_dogrula("butce.usd", b.get("usd"), False)
    token = _sayi_dogrula("butce.token", b.get("token"), True)
    if usd is None and token is None:
        return None
    return {"usd": usd, "token": token, "kaynak": "elle", "esik_surumu": None}


def _oto_teslim_dogrula(d: dict) -> bool:
    """G-124: oto_teslim (bool). Belirtilmezse varsayılan: sinif 'kod' ise true, değilse false."""
    v = d.get("oto_teslim")
    if v is None:
        return (d.get("sinif") or "").strip().lower() == "kod"
    if not isinstance(v, bool):
        hata(f"oto_teslim true/false olmalı: {v!r} ({d.get('baslik') or '(başlıksız)'})")
    return v


def _oto_teslim_gecerli(k: dict) -> bool:
    """I-145: kartın oto-teslim politikası karar anında okunur. Karttaki açık değer (true/false) geçerlidir; alan yoksa
    (G-124 öncesi kart) sınıftan türetilir. Yalnız sinif 'kod' kartı oto-teslim olur."""
    if (k.get("sinif") or "").strip().lower() != "kod":
        return False
    v = k.get("oto_teslim")
    return True if v is None else v is True


def _kart_kur(sd, d: dict, onbellek: dict | None = None) -> dict:
    _sinif_zorunlu(d)
    # ADR-0092: basamak verilmezse görev türü kataloğundan türer; katalogda yoksa eski varsayılan T2.
    basamak = (d.get("basamak") or GT.varsayilan_basamak(d.get("sinif")) or "T2").upper()
    if basamak not in BASAMAKLAR:
        hata(f"basamak T0..T4 olmalı: {basamak}")
    basamak_neden = (d.get("basamak_neden") or "").strip() or None
    tur_eksik = GT.kapi_eksikleri(d.get("sinif"), basamak, basamak_neden)
    _soru_zorunlu(d, sd)
    test_alanlari = _test_alanlari_dogrula(d)
    risk = _risk_dogrula(d)
    effort = _effort_dogrula(d)
    butce = _butce_dogrula(d)
    oto_teslim = _oto_teslim_dogrula(d)
    kriterler, iskelet = _kabul_kontrol_dogrula(d, sd)  # I-224: kart sayacından önce; ret yarım kart bırakmaz
    _merkez_saglamla(sd)  # K2: bozuk/eksik isler.json bağ çözümünü düşürmez
    _acik_is_dogrula(sd, d.get("is"))  # doğrulama kart sayacından önce: hata sayacı ilerletmez
    gid = d.get("id") or L.yeni_kart_id(sd)
    if L.kart_oku(sd, gid):
        hata(f"kart zaten var: {gid}")
    yazma = list(d.get("yazma_alani") or [])
    bag = _kart_is_bag_kur(sd, gid, d.get("baslik") or "", yazma, d.get("is"), onbellek)
    k = {
        "id": gid,
        "baslik": d.get("baslik") or "(başlıksız)",
        "sinif": (d.get("sinif") or "-").strip().lower() or "-",   # kapılar tam "kod" eşleşmesi arar
        "basamak": basamak,
        "baslangic_basamak": basamak,
        "soru": d["soru"].strip(),
        "girdi": d.get("girdi") or "",
        "kabul_kriterleri": kriterler,
        "yazma_alani": yazma,
        "bagimliliklar": list(d.get("bagimliliklar") or []),
        "oto_teslim": oto_teslim,
        "durum": "planlandi",
        "oturum": oturum_id(),
        "plan_modeli": PM.plan_modeli_bul(sd, oturum_id()),
        "olusturma": L.simdi(),
        "isciler": [],
        "denetciler": [],
        "denetimler": [],
        "ciktilar": [],
        "gecmis": [{"zaman": L.simdi(), "olay": "olusturuldu", "basamak": basamak}],
    }
    if iskelet:
        k["kanit_iskeleti"] = iskelet
    if basamak_neden:
        k["basamak_neden"] = basamak_neden
    if tur_eksik:
        GT.golge_yaz(sd, k.get("is") or d.get("is"), tur_eksik)
    if d.get("genislet_onay") is True:
        k["genislet_onay"] = True
    if risk is not None:
        k["risk"] = risk
    if effort is not None:
        k["effort"] = effort
    if butce is not None:
        k["butce"] = butce
    if test_alanlari:
        k.update(test_alanlari)
        if not test_alanlari["tdd"] and not test_alanlari.get("test_koku"):
            # TDD'siz kartta testleri işçi yazar: test alanı yazma alanına katılır.
            k["yazma_alani"] = list(dict.fromkeys(list(k.get("yazma_alani") or []) + test_alanlari["test_alani"]))
    k["is"] = bag
    madde = d.get("madde")
    if madde is not None:
        if not isinstance(madde, str) or not madde.strip():
            hata(f"madde boş olmayan metin olmalı (todo.md madde parçası): {k['baslik']}")
        k["madde"] = madde.strip()
    adim = _ik().adim_coz(k["baslik"])
    if adim:
        k["adim"] = adim
    return k


# Yaygın sınıf adları (yalnız hata mesajında yol gösterir; başka kısa ad da kabul edilir).
SINIFLAR = ("kod", "belge", "arastirma", "analitik", "test", "altyapi", "arayuz", "birlestirme", "kod-duzenleme")


def _sinif_zorunlu(d: dict) -> None:
    """Yeni kart açılışında sinif zorunlu (eski sınıfsız kartlar okunmaya devam eder: bu yalnız oluşturmada çalışır)."""
    sn = d.get("sinif")
    if not isinstance(sn, str) or not sn.strip() or sn.strip() == "-":
        hata(f"sinif zorunlu (--sinif); geçerli sınıflar: {', '.join(SINIFLAR)}. Kart: {d.get('baslik') or '(başlıksız)'}")


KART_SORU_DOSYA = "kart_soru.json"


KART_SORU_VARSAYILAN = os.path.join(os.path.dirname(BETIK_DIZINI), "ayarlar", KART_SORU_DOSYA)


def _kart_soru_ayar(sd) -> dict:
    """Eklenti varsayılanı + proje ezmesi (durum dizinindeki kart_soru.json); bozuk/eksik dosya varsayılana düşer."""
    ayar = {"soru_max_karakter": 200, "analiz_siniflari": ["analiz", "analitik", "arastirma"], "genis_tarama_kaliplari": []}
    ayar.update(SS._json_oku(KART_SORU_VARSAYILAN) or {})
    if sd:
        ayar.update(SS._json_oku(os.path.join(sd, KART_SORU_DOSYA)) or {})
    return ayar


def _soru_zorunlu(d: dict, sd) -> None:
    """Yeni kart açılışında soru zorunlu: boş olmayan tek cümle (satır sonu yok, soru_max_karakter'i aşmaz)."""
    ad = d.get("baslik") or "(başlıksız)"
    s = d.get("soru")
    if not isinstance(s, str) or not s.strip():
        hata(f"soru zorunlu (--soru): kartın cevaplayacağı tek soru (tek cümle). Kart: {ad}")
    s = s.strip()
    mx = _kart_soru_ayar(sd).get("soru_max_karakter", 200)
    if "\n" in s or "\r" in s or (isinstance(mx, int) and len(s) > mx):
        hata(f"soru tek cümle olmalı (satır sonu yok, en çok {mx} karakter): {ad}")


def _genis_tarama_uyarisi(sd, k: dict) -> None:
    """Analiz sınıfı kartta geniş kapsam kalıbı varsa yalnız uyarı (stderr); genislet_onay varsa susar."""
    if k.get("genislet_onay") is True:
        return
    ayar = _kart_soru_ayar(sd)
    if (k.get("sinif") or "").strip().lower() not in [str(x).lower() for x in ayar.get("analiz_siniflari") or []]:
        return
    metin = SS._normallestir(" ".join([k.get("soru") or "", k.get("girdi") or "", *map(str, k.get("kabul_kriterleri") or [])]))
    for kalip in ayar.get("genis_tarama_kaliplari") or []:
        try:
            m = re.search(kalip, metin)
        except re.error:
            continue
        if m:
            print(f"orkestra: uyarı {k['id']}: geniş tarama ({m.group(0)}) — önce en ucuz kanıt (ör. varlık kontrolü); "
                  "genişletme kullanıcı onayıyla --genislet-onay", file=sys.stderr)
            return


KART_KONTROL = "kart_kontrol"
KART_KONTROL_ORTAM = "ORKESTRA_KART_KONTROL"
KART_KONTROL_VARSAYILAN = os.path.join(os.path.dirname(BETIK_DIZINI), "ayarlar", KART_KONTROL + ".json")
_KONTROL_RE = re.compile(r"(?:^|[\s;|,—–-])kontrol\s*:\s*(.*)$", re.I | re.S)
_KRITER_NO_RE = re.compile(r"\s*K(\d+)\b")
KRITER_ORNEK = ('örnek: --kabul "Boş girdi reddedilir; kontrol: pytest tests/test_x.py::test_bos -> 1 passed" '
                '(kontrol: komut, dosya:satır ya da sayı); JSON\'da {"metin": "...", "kontrol": "..."}')


def _kart_kontrol_ayar(sd) -> dict:
    """Eklenti varsayılanı + proje ezmesi (durum dizinindeki kart_kontrol.json); bozuk dosya varsayılana düşer."""
    ayar = {"olculebilir_kaliplar": [r"\d"], "olcusuz_ifadeler": []}
    ayar.update(SS._json_oku(KART_KONTROL_VARSAYILAN) or {})
    if sd:
        ayar.update(SS._json_oku(os.path.join(sd, KART_KONTROL + ".json")) or {})
    return ayar


def _kriter_metni(x) -> str:
    """Kriteri saklanan metin biçimine çevirir: metin olduğu gibi kalır (eski kartlarla aynı biçim);
    {"metin"|"kriter", "kontrol"} nesnesi '<metin>; kontrol: <kontrol>' olur."""
    if isinstance(x, dict):
        metin = str(x.get("metin") or x.get("kriter") or "").strip()
        kontrol = str(x.get("kontrol") or "").strip()
        return f"{metin}; kontrol: {kontrol}" if kontrol else metin
    return str(x)


def _kriter_kontrolu(metin: str) -> str:
    m = _KONTROL_RE.search(metin)
    return m.group(1).strip() if m else ""


def _kalip_bul(kaliplar, metin: str):
    for kalip in kaliplar or []:
        try:
            m = re.search(kalip, metin, re.I)
        except re.error:
            continue
        if m:
            return m
    return None


def _kabul_kontrol_dogrula(d: dict, sd) -> tuple[list, list]:
    """I-224: her kabul kriteri ölçülebilir 'kontrol:' alanı (komut, dosya:satır ya da sayı) taşır ve ölçüsüz ifade
    içermez; kriter başına K-iskeleti üretir. Mod kapi_mod ile (ayarlar/kart_kontrol.json; ihlal reddeder, golge uyarır);
    ORKESTRA_KART_KONTROL=0 kapıyı ve iskeleti kapatır. Yalnız oluşturmada çalışır: eski kartlar okunur kalır."""
    kriterler = [_kriter_metni(x) for x in (d.get("kabul_kriterleri") or [])]
    if os.environ.get(KART_KONTROL_ORTAM) == "0" or not kriterler:
        return kriterler, []
    ayar = _kart_kontrol_ayar(sd)
    ad = d.get("baslik") or "(başlıksız)"
    eksik, iskelet = [], []
    for i, metin in enumerate(kriterler, 1):
        m = _KRITER_NO_RE.match(metin)
        no = int(m.group(1)) if m else i
        kisa = re.sub(r"\s+", " ", metin).strip()[:60]
        kontrol = _kriter_kontrolu(metin)
        bos = SS._normallestir(metin)
        olcusuz = _kalip_bul(ayar.get("olcusuz_ifadeler"), bos)
        if olcusuz:
            eksik.append(f"K{no} '{kisa}': ölçüsüz ifade '{olcusuz.group(0)}' — yerine ölçü (eşik, sayı, komut sonucu) yaz")
        if not kontrol:
            eksik.append(f"K{no} '{kisa}': 'kontrol:' alanı yok")
        elif not _kalip_bul(ayar.get("olculebilir_kaliplar"), kontrol):
            eksik.append(f"K{no} '{kisa}': 'kontrol: {kontrol[:40]}' ölçülebilir değil (komut, dosya:satır ya da sayı olmalı)")
        iskelet.append(f"K{no}: <dosya:satır | komut çıktısı | sayı>" + (f" — kontrol: {kontrol}" if kontrol else ""))
    proje = os.path.dirname(os.path.dirname(sd)) if sd else None
    if eksik:
        if proje:
            red = KM.ret_ver(proje, KART_KONTROL, eksik)
        else:
            red = eksik if KM.mod(KART_KONTROL) == "ihlal" else []
        if red:
            hata(f"kabul kriteri ölçülebilir değil ({ad}): " + "; ".join(red) + f". {KRITER_ORNEK}")
    return kriterler, iskelet


def _test_alanlari_dogrula(d: dict) -> dict | None:
    """sinif 'kod' ise test_komutu (boş olmayan metin) ve test_alani (boş olmayan glob listesi) zorunlu; değilse None.
    İsteğe bağlı test_koku (var olan mutlak dizin) yalnız kod kartında kabul edilir; test_alani ve test_komutu ona göredir."""
    ad = d.get("baslik") or "(başlıksız)"
    tk = d.get("test_koku")
    if (d.get("sinif") or "").strip().lower() != "kod":
        if tk:
            hata(f"test_koku yalnız kod kartında (sinif kod) anlamlı: {ad}")
        return None
    if tk is not None and tk != "":
        try:
            tk = L.test_koku_dogrula(tk)
        except ValueError as e:
            hata(f"{e}: {ad}")
    komut = d.get("test_komutu")
    if not isinstance(komut, str) or not komut.strip():
        hata(f"kod kartında test_komutu zorunlu (boş olmayan metin; --test-komutu): {ad}")
    alan = d.get("test_alani")
    if isinstance(alan, str):
        alan = [alan]
    if not isinstance(alan, list) or not [g for g in alan if isinstance(g, str) and g.strip()]:
        hata(f"kod kartında test_alani zorunlu (boş olmayan glob listesi; --test-alani): {ad}")
    sonuc = {"test_komutu": komut.strip(), "test_alani": [g.strip() for g in alan if isinstance(g, str) and g.strip()],
             "test_kilidi": None, "test_kosulari": [],
             # TDD yalnız riskli kod kartında (TOK-4): varsayılan kapalı; açıkken test yazarı + kırmızı kapı koşar.
             "tdd": d.get("tdd") is True or str(d.get("tdd")).lower() in ("1", "true", "evet")}
    if tk:
        sonuc["test_koku"] = tk
    return sonuc


def cmd_kart_yeni(a):
    sd = sd_gerekli()
    if not a.kabul:  # iş/klasör açılmadan önce
        hata("en az bir --kabul kriteri gerekli (denetçi buna göre karar verir).")
    k = _kart_kur(sd, {"baslik": a.baslik, "sinif": a.sinif, "basamak": a.basamak, "basamak_neden": a.basamak_neden, "girdi": a.girdi,
                       "soru": a.soru, "genislet_onay": a.genislet_onay or None,
                       "kabul_kriterleri": a.kabul, "yazma_alani": a.yazma, "bagimliliklar": a.bagimli,
                       "test_komutu": a.test_komutu, "test_alani": a.test_alani, "test_koku": a.test_koku,
                       "tdd": a.tdd, "is": a.is_id, "risk": a.risk, "effort": a.effort, "madde": a.madde, "oto_teslim": a.oto_teslim,
                       "butce": ({"usd": a.butce_usd, "token": a.butce_token}
                                 if a.butce_usd is not None or a.butce_token is not None else None)})
    if not k["kabul_kriterleri"]:
        hata("en az bir --kabul kriteri gerekli (denetçi buna göre karar verir).")
    L.kart_yaz(sd, k)
    _kart_is_bagla(sd, k)
    _cakisma_uyarisi(sd, [k])
    _genis_tarama_uyarisi(sd, k)
    print(k["id"])


def _cakisma_uyarisi(sd, ks):
    """Oluşturma sırasında yalnız uyarı: asıl kapı `kart durum … isleniyor` geçişindedir."""
    proje = L.proje_dizini()
    for k in ks:
        for m in L.yazma_cakismalari(sd, proje, k):
            print(f"orkestra: uyarı {k['id']}: {m}", file=sys.stderr)


def cmd_kart_toplu(a):
    sd = sd_gerekli()
    yol = a.json_dosya or a.json_yol
    if not yol:
        hata("plan dosyası gerekli: orkestra kart toplu plan.json (ya da --json-dosya plan.json)")
    with open(yol, encoding="utf-8") as f:
        liste = json.load(f)
    if isinstance(liste, dict):
        liste = liste.get("gorevler") or []
    yerel = {}
    olusan = []
    _merkez_saglamla(sd)
    for d in liste:  # hiçbir kart oluşmadan önce hepsini doğrula
        if not d.get("kabul_kriterleri"):
            hata(f"kabul kriteri eksik: {d.get('baslik')}")
        _kabul_kontrol_dogrula(d, sd)
        _sinif_zorunlu(d)
        _soru_zorunlu(d, sd)
        _test_alanlari_dogrula(d)
        _risk_dogrula(d)
        _effort_dogrula(d)
        _butce_dogrula(d)
        _oto_teslim_dogrula(d)
        if d.get("madde") is not None and (not isinstance(d["madde"], str) or not d["madde"].strip()):
            hata(f"madde boş olmayan metin olmalı: {d.get('baslik')}")
        _acik_is_dogrula(sd, d.get("is"))
    # Bağımlılıklar kart oluşmadan önce çözülür: bilinmeyen başvuru ve ref döngüsü yarım kart bırakmaz; listede sonra
    # gelen bir ref'e ileri başvuru, bağımlılığı önce kurulacak sırayla çözülür.
    refler = {d["ref"]: d for d in liste if d.get("ref")}
    for d in liste:
        for b in d.get("bagimliliklar") or []:
            if b not in refler and not L.kart_oku(sd, b):
                hata(f"bilinmeyen bağımlılık: {b} (kart: {d.get('baslik')})")
    sirali, kalan = [], list(liste)
    while kalan:
        hazir = next((d for d in kalan if all(b not in refler or any(refler[b] is s for s in sirali)
                                                for b in d.get("bagimliliklar") or [])), None)
        if hazir is None:
            hata("bağımlılık döngüsü (ref): " + ", ".join(str(d.get("ref") or d.get("baslik")) for d in kalan))
        sirali.append(hazir)
        kalan = [d for d in kalan if d is not hazir]
    liste = sirali
    onbellek = {}  # aynı klasöre çözülen kartlar tek işe bağlanır
    for d in liste:
        takma = d.pop("ref", None)
        d["bagimliliklar"] = [yerel.get(b, b) for b in d.get("bagimliliklar") or []]
        k = _kart_kur(sd, d, onbellek)
        L.kart_yaz(sd, k)
        _kart_is_bagla(sd, k)
        if takma:
            yerel[takma] = k["id"]
        olusan.append(k)
    # döngü kontrolü
    harita = {k["id"]: k["bagimliliklar"] for k in L.kartlar(sd)}

    def dongu(n, yol):
        if n in yol:
            return True
        return any(dongu(m, yol | {n}) for m in harita.get(n, []))
    for k in olusan:
        if dongu(k["id"], set()):
            hata(f"bağımlılık döngüsü: {k['id']}")
    _cakisma_uyarisi(sd, olusan)
    for k in olusan:
        _genis_tarama_uyarisi(sd, k)
    print(json.dumps([{"id": k["id"], "baslik": k["baslik"], "basamak": k["basamak"], "bagimliliklar": k["bagimliliklar"]}
                      for k in olusan], ensure_ascii=False))


def cmd_kart_goster(a):
    sd = sd_gerekli()
    k = _kart_al(sd, a.gid)
    k["durum"] = L.kart_durumu_hesapla(k)
    k.setdefault("oto_teslim", False)  # G-124: alansız eski kart elle teslimdir
    ca = k.get("calisma_agaci") or {}
    if ca.get("yol"):
        k["calisma_agaci_satiri"] = L.CALISMA_AGACI_ONEKI + ca["yol"]
    print(json.dumps(k, ensure_ascii=False, indent=2))


def cmd_kart_liste(a):
    sd = sd_gerekli()
    oid = oturum_id()
    tum = L.kartlar(sd)
    for k in tum:
        k["durum"] = L.kart_durumu_hesapla(k)
    sec = {x.strip() for x in (getattr(a, "durum", None) or "").split(",") if x.strip()}
    if sec:
        ks = [k for k in tum if k["durum"] in sec]
    else:  # varsayılan: açık kartlar + beklemede olanlar (bekleyen kart gözden kaçmasın)
        ks = [k for k in tum if a.hepsi or k.get("oturum") == oid
              or k["durum"] in L.ACIK_DURUMLAR or k["durum"] == "beklemede"]
    if a.json:
        print(json.dumps(ks, ensure_ascii=False))
        return
    for k in ks:
        print(f"{k['id']:7s} {k['durum']:11s} {k['basamak']} {k['baslik'][:70]}"
              + (f"  ← {','.join(k['bagimliliklar'])}" if k["bagimliliklar"] else ""))
    if not ks:
        print("(kart yok)")


def _kim(a):
    return (a.ajan_id or "bilinmiyor"), (a.ajan_tipi or "bilinmiyor")


def _sha_birlestir(parcalar) -> str:
    h = hashlib.sha256()
    for p in parcalar:
        b = p if isinstance(p, bytes) else str(p).encode("utf-8")
        h.update(str(len(b)).encode() + b":" + b)
    return h.hexdigest()


def _cikti_ozeti_sha(k: dict) -> str:
    """Kartın ciktilar dosyalarının birleşik sha256'sı (var olmayan atlanır; liste sırası sabit)."""
    parcalar = []
    for c in k.get("ciktilar") or []:
        yol = c if os.path.isabs(c) else os.path.join(L.proje_dizini(), c)
        if os.path.isfile(yol):
            with open(yol, "rb") as f:
                parcalar.append(f.read())
    return _sha_birlestir(parcalar)


def _girdi_sha(k: dict) -> str:
    return _sha_birlestir([_girdi_agacsiz(k.get("girdi")), json.dumps(k.get("kabul_kriterleri") or [], ensure_ascii=False),
                           k.get("test_komutu") or ""])


def _is_turu(k: dict, a, ajan_id: str, ajan_tipi: str, sira: int) -> dict:
    """N2: o an koşan işçinin gerçek basamağı yalnız ajan tipinden ('orkestra:isci-tN' -> 'TN'); kart alanından kopyalanmaz."""
    ad = ajan_tipi.split(":", 1)[-1].lower()
    m = re.fullmatch(r"isci-t([0-4])", ad)
    t = {"sira": sira, "basamak": ("T" + m.group(1)) if m else None, "agent_id": ajan_id}
    if not m:
        t["basamak_kaynak"] = "bilinmiyor"
    surec = getattr(a, "surec", None)
    if not surec and ad.startswith("isci"):
        surec = "is"
    t["surec"] = surec or None
    t["cikti_ozeti_sha"] = _cikti_ozeti_sha(k)
    t["cikti_dosya_sha"] = DK.dosya_shalari(L.proje_dizini(), k.get("ciktilar"))  # A9 tabanı (ADR-0083)
    t["girdi_sha"] = _girdi_sha(k)
    return t


# Kart kilidi (TOK-1): kapalı kart yeniden işlenmez; başka ajanın yakın zamanda aldığı kart ikinci ajana verilmez.
# Çıkış 6 = kart kilitli: işçi işe başlamadan durur (workflow sonucu 'kilitli').
KAPALI_DURUMLAR = ("teslim", "onaylandi", "iptal")


SAHIPLIK_SURESI_S = 2 * 3600


def _kart_kilidi_engeli(k: dict, ajan_id: str) -> str | None:
    durum = L.kart_durumu_hesapla(k)
    if durum in KAPALI_DURUMLAR:
        return (f"kart {durum}: yeniden işlenmez (yeniden açmak için ana ajan `orkestra kart durum {k['id']} planlandi`). "
                "İşi BIRAK, kapı=kilitli bildir.")
    if k.get("durum") != "isleniyor":
        return None
    for o in reversed(k.get("gecmis") or []):
        if o.get("olay") == "kapi-gecmedi":
            return None  # son sahip kapıyı geçemeden bitti: düzeltme turu yeni ajanla açılabilir
        if o.get("olay") != "isleniyor":
            continue
        sahip = o.get("agent_id")
        if not sahip or sahip == ajan_id or sahip in ("bilinmiyor", "ana"):
            return None
        ts = _zaman_s(o.get("zaman"))
        if ts is not None and time.time() - ts > SAHIPLIK_SURESI_S:
            return None  # bayat sahiplik: ajan bitişi düşmemiş
        return f"kart başka bir ajanda işleniyor ({sahip}, {o.get('zaman')}); ikinci koşu açılmaz. İşi BIRAK, kapı=kilitli bildir."
    return None


def _zaman_s(z) -> float | None:
    import datetime
    try:
        t = datetime.datetime.fromisoformat(str(z))
        return t.timestamp() if t.tzinfo else t.astimezone().timestamp()
    except (ValueError, TypeError):
        return None


def tdd_karti(k: dict) -> bool:
    """Test-önce akışı: yalnız `tdd` açık kod kartında (alanı olmayan eski kod kartları TDD sayılır)."""
    return k.get("sinif") == "kod" and k.get("tdd", True) is not False


# Kapılar is-bitti'de (TOK-5): test ve ön kontrol model çağırmadan CLI'de koşar; geçmezse is-bitti kaydedilmez
# (çıkış 4), işçi aynı oturumda düzeltir. Bash aracının 600 sn sınırına sığsın diye test zaman aşımı en çok 540 sn.
KAPI_TEST_ZAMAN_ASIMI_S = 540


def _ic_komut(fn, ns) -> tuple[int, str]:
    """CLI alt komutunu süreç içinde koşar; (çıkış kodu, stdout+stderr)."""
    import contextlib
    import io
    tampon = io.StringIO()
    kod = 0
    with contextlib.redirect_stdout(tampon), contextlib.redirect_stderr(tampon):
        try:
            r = fn(ns)
            kod = r if isinstance(r, int) else 0
        except SystemExit as e:
            kod = e.code if isinstance(e.code, int) else (0 if e.code is None else 2)
    return kod, tampon.getvalue()


def _test_zaman_asimi(k: dict) -> int:
    z = k.get("test_zaman_asimi")
    z = z if isinstance(z, (int, float)) and z > 0 else KAPI_TEST_ZAMAN_ASIMI_S
    return int(min(z, KAPI_TEST_ZAMAN_ASIMI_S))


def _onkontrol_ns(gid: str, ajan_id: str | None, ciktilar: list[str] | None = None):
    return argparse.Namespace(id=gid, proje=None, ciktilar=",".join(ciktilar or []), kaynak=None, ajan_id=ajan_id)


def _taban_kapisi(sd: str, k: dict, ajan_id: str) -> None:
    """İlk isleniyor'da ön kontrol tabanı (dosya özetleri, gerekirse test tabanı). Hata işi durdurmaz."""
    if os.path.exists(os.path.join(sd, "gorevler", k["id"] + ".onkontrol.json")):
        return
    import on_kontrol
    _ic_komut(on_kontrol.taban, _onkontrol_ns(k["id"], ajan_id))


def _kanit_kapisi(sd: str, k: dict, ozet, kanitlar, ciktilar: list[str], kayit: dict) -> tuple[bool, str]:
    """K-001/K-002 kanıt kapısı (yalnız işçi, test+ön kontrol geçtikten sonra). Hiçbir hata is-bitti'yi engellemez.
    Dönüş: (ihlal, ihlal raporu). Gölge uyarıları kayit['_mesajlar']'a konur (çağıran yazdırır ve siler)."""
    try:
        import kanit_kapisi
        r = kanit_kapisi.kapi(sd, L.proje_dizini(), k, ozet, list(kanitlar or []), ciktilar)
        ek = dict(r.get("kayit") or {})
        if "hata" in ek:
            ek["kanit_hata"] = ek.pop("hata")
        kayit.update(ek)
        mesajlar = [str(m) for m in (r.get("mesajlar") or [])]
        if r.get("ihlal"):
            return True, "\n".join("orkestra: " + m for m in mesajlar)
        if mesajlar:
            kayit["_mesajlar"] = mesajlar
    except Exception as e:
        kayit["kanit_hata"] = type(e).__name__
    return False, ""


def _is_bitti_kapisi(sd: str, k: dict, ajan_id: str, ajan_tipi: str, ciktilar: list[str],
                     ozet=None, kanitlar=None) -> tuple[bool, str, dict]:
    """is-bitti kapısı. Dönüş: (geçti, rapor metni, kayıt). Kapı yalnız işçi ve test yazarı için koşar."""
    ad = ajan_tipi.split(":", 1)[-1].lower()
    kod_karti = k.get("sinif") == "kod" and k.get("test_komutu") and k.get("test_alani")
    kayit: dict = {}
    if ad == "test-yazari":
        if not (kod_karti and tdd_karti(k)):
            return True, "", kayit
        if k.get("test_kilidi"):
            son = [x for x in (k.get("test_kosulari") or []) if x.get("asama") == "kirmizi"]
            kayit["test"] = "kirmizi-kayitli"
            return bool(son and son[-1].get("gecti")), "", kayit
        kod, cikti = _ic_komut(cmd_kart_test_kos, argparse.Namespace(
            gid=k["id"], asama="kirmizi", zaman_asimi=_test_zaman_asimi(k), ajan_id=ajan_id, ajan_tipi=ajan_tipi))
        kayit["test"] = "kirmizi-gecti" if kod == 0 else f"kirmizi-gecmedi({kod})"
        return kod == 0, cikti, kayit
    if not ad.startswith("isci"):
        return True, "", kayit
    rapor = []
    if kod_karti:
        kod, cikti = _ic_komut(cmd_kart_test_kos, argparse.Namespace(
            gid=k["id"], asama="yesil", zaman_asimi=_test_zaman_asimi(k), ajan_id=ajan_id, ajan_tipi=ajan_tipi))
        kayit["test"] = "yesil-gecti" if kod == 0 else f"yesil-gecmedi({kod})"
        if kod != 0:
            return False, cikti, kayit
        yesiller = [x for x in (_kart_al(sd, k["id"]).get("test_kosulari") or []) if x.get("asama") == "yesil"]
        if yesiller and isinstance(yesiller[-1].get("sira"), int):
            kayit["yesil_sira"] = yesiller[-1]["sira"]
        rapor.append(cikti.strip())
    import on_kontrol
    kod, cikti = _ic_komut(on_kontrol.kontrol, _onkontrol_ns(k["id"], ajan_id, ciktilar))
    kayit["on_kontrol"] = "gecti" if kod == 0 else f"gecmedi({kod})"
    rapor.append(cikti.strip())
    if kod not in (0, 2):  # 2 = kullanım hatası: işi durdurmaz
        return False, "\n".join(r for r in rapor if r), kayit
    ihlal, ihlal_rapor = _kanit_kapisi(sd, k, ozet, kanitlar, ciktilar, kayit)
    if ihlal:
        rapor.append(ihlal_rapor)
        return False, "\n".join(r for r in rapor if r), kayit
    return True, "\n".join(r for r in rapor if r), kayit


def _kanit_kirp(sd: str, kanitlar) -> list:
    """--kanit satırlarını maskeler; satır başına ve toplam üst sınıra (ayarlar/on_kontrol.json) kırpar."""
    satir_az, toplam_az = 400, 6000
    try:
        import kanit_kapisi
        c = kanit_kapisi.ayar_yukle(sd)["kontroller"]["kanit-satiri"]
        satir_az, toplam_az = int(c.get("kanit_satir_azami", satir_az)), int(c.get("kanit_toplam_azami", toplam_az))
    except Exception:
        pass
    out, kalan = [], toplam_az
    for x in kanitlar:
        if kalan <= 0:
            break
        m = L.maskele(str(x))[:min(satir_az, kalan)]
        out.append(m)
        kalan -= len(m)
    return out


def _teknik_kapisi(a, ajan_tipi: str):
    """İşçi is-bitti teknik not kapısı. Geçerli notu döner; kapı kapalı/işçi değilse None; geçersizse çıkış 4."""
    if os.environ.get("ORKESTRA_TEKNIK_KAPISI") == "0":
        return None
    if not ajan_tipi.split(":", 1)[-1].lower().startswith("isci"):
        return None
    import json as _json
    import teknik_not
    yol = getattr(a, "teknik", None)
    on = f"{a.gid} is-bitti KAYDEDİLMEDİ: teknik not"
    if not yol:
        hata(f"{on} yok: --teknik <json_dosya> ver (yaklasim, neden_bu_yol, alternatifler, entegrasyon, riskler).", 4)
    try:
        with open(yol, encoding="utf-8") as f:
            nesne = _json.load(f)
    except OSError as e:
        hata(f"{on} dosyası okunamadı ({yol}): {e.__class__.__name__}.", 4)
    except ValueError as e:
        hata(f"{on} JSON bozuk: {e}", 4)
    tamam, hatalar = teknik_not.dogrula(nesne)
    if not tamam:
        hata(f"{on} geçersiz: " + "; ".join(hatalar), 4)
    return nesne


def mevcut_kapisi_acik(k: dict, ajan_tipi: str) -> bool:
    """Mevcut-durum kapısı yalnız kod kartında çalışan işçiye (test yazarı hariç) uygulanır; ORKESTRA_MEVCUT_KAPISI=0 kapatır."""
    if os.environ.get("ORKESTRA_MEVCUT_KAPISI") == "0":
        return False
    return k.get("sinif") == "kod" and ajan_tipi.split(":", 1)[-1].lower().startswith("isci")


def _mevcut_kapisi(k: dict, ajan_tipi: str) -> None:
    """İşçi is-bitti: kod kartında kayıtlı mevcut-durum notu yoksa çıkış 4 (not `orkestra kart mevcut` ile kaydedilir)."""
    if mevcut_kapisi_acik(k, ajan_tipi) and not isinstance(k.get("mevcut_durum"), dict):
        hata(f"{k['id']} is-bitti KAYDEDİLMEDİ: mevcut durum notu yok. Kod yazmadan önce ilgili mevcut kodu oku ve "
             f"`orkestra kart mevcut {k['id']} --dosya <json>` ile kaydet (okunan, yetenekler, karar, neden, etkilenenler).", 4)


def _maskele_nesne(v):
    if isinstance(v, str):
        return L.maskele(v)
    if isinstance(v, list):
        return [_maskele_nesne(x) for x in v]
    if isinstance(v, dict):
        return {k: _maskele_nesne(x) for k, x in v.items()}
    return v


def cmd_kart_mevcut(a):
    """Kod kartı mevcut-durum notunu doğrular ve karta yazar (işçi kod yazmadan önce çalıştırır)."""
    sd = sd_gerekli()
    k0 = _kart_al(sd, a.gid)
    if k0.get("sinif") != "kod":
        hata(f"{a.gid} kod kartı değil (sinif={k0.get('sinif')}): mevcut durum notu yalnız kod kartında.")
    try:
        with open(a.dosya, encoding="utf-8") as f:
            nesne = json.load(f)
    except OSError as e:
        hata(f"{a.gid} mevcut durum notu okunamadı ({a.dosya}): {e.__class__.__name__}.", 4)
    except ValueError as e:
        hata(f"{a.gid} mevcut durum notu JSON bozuk: {e}", 4)
    import mevcut_durum
    proje = L.proje_dizini()
    ca = k0.get("calisma_agaci") or {}
    kokler = ([ca["yol"]] if ca.get("yol") and os.path.isdir(ca["yol"]) else []) + [proje]
    alan = list(k0.get("yazma_alani") or [])

    def yazma_eslesir(y: str) -> bool:
        es = L.agac_esdegeri(k0, y)
        return L.desen_eslesir(proje, es if es is not None else y, alan)

    tamam, hatalar = mevcut_durum.dogrula(nesne, kokler, yazma_eslesir if alan else None)
    if not tamam:
        hata(f"{a.gid} mevcut durum notu KAYDEDİLMEDİ: " + "; ".join(hatalar), 4)
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        k["mevcut_durum"] = _maskele_nesne(nesne)
        k["mevcut_durum_zaman"] = L.simdi()
        ajan_id, ajan_tipi = _kim(a)
        k["gecmis"].append({"zaman": k["mevcut_durum_zaman"], "olay": "mevcut-durum", "ajan": ajan_tipi,
                            "agent_id": ajan_id, "not": f"karar={nesne['karar']}; okunan={len(nesne['okunan'])}"})
        L.kart_yaz(sd, k)
    print(f"{a.gid} mevcut durum notu kaydedildi (karar={nesne['karar']}, okunan={len(nesne['okunan'])})")


def cmd_kart_durum(a):
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    path = L.kart_yolu(sd, a.gid)
    kapi_kaydi = None
    teknik_nesne = None
    if a.durum in ("isleniyor", "is-bitti") and ajan_tipi not in ("ana", "bilinmiyor"):
        k0 = _kart_al(sd, a.gid)
        if a.durum == "isleniyor":
            engel = _kart_kilidi_engeli(k0, ajan_id)
            if engel:
                hata(f"{a.gid} kilitli — {engel}", 6)
            import butce
            engel = butce.engel(sd, k0, ajan_tipi)
            if engel:
                hata(f"{a.gid} bütçe — {engel} İşi BIRAK, kapi=butce bildir.", 7)
            _taban_kapisi(sd, k0, ajan_id)
        else:
            _mevcut_kapisi(k0, ajan_tipi)  # en ucuz kanıt: mevcut kod okunmadan teknik not/test koşusu başlamaz
            teknik_nesne = _teknik_kapisi(a, ajan_tipi)  # ucuz kanıt önce: not eksikken test koşusu başlamaz
            ciktilar = list(dict.fromkeys(list(k0.get("ciktilar") or []) + list(a.cikti or [])))
            kanitlar = [L.maskele(x) for x in (getattr(a, "kanit", None) or [])]
            gecti, rapor, kapi_kaydi = _is_bitti_kapisi(sd, k0, ajan_id, ajan_tipi, ciktilar, a.ozet, kanitlar)
            if gecti:
                for m in kapi_kaydi.pop("_mesajlar", []):
                    print("orkestra: " + m)
            if not gecti:
                with L.kilit(path):  # sahipliği bırak: aynı ajan yeniden dener ya da workflow düzeltme ajanı açar
                    kk = _kart_al(sd, a.gid)
                    kk["gecmis"].append({"zaman": L.simdi(), "olay": "kapi-gecmedi", "ajan": ajan_tipi,
                                         "agent_id": ajan_id, "not": str(kapi_kaydi)[:300]})
                    L.kart_yaz(sd, kk)
                print(rapor[-6000:])
                if "(çıkış -1," in rapor:
                    hata(f"{a.gid} is-bitti KAYDEDİLMEDİ: test komutu zaman aşımı ({_test_zaman_asimi(k0)} sn). "
                         "Kod düzeltmesiyle çözülmez; kapi=gecmedi bildir.", 4)
                for kalip in ("hiçbir proje dosyasına uymuyor", "kilit yok", "test_komutu/test_alani yok", "kapsamıyor"):
                    if any(l.startswith("orkestra:") and kalip in l for l in rapor.splitlines()):
                        hata(f"{a.gid} is-bitti KAYDEDİLMEDİ: kart/test ayarı hatası ({kalip}); kapi=gecmedi bildir.", 2)
                hata(f"{a.gid} is-bitti KAYDEDİLMEDİ: kapı geçmedi ({kapi_kaydi}). Yukarıdaki çıktıya göre düzelt ve "
                     "is-bitti'yi yeniden çalıştır.", 4)
    with L.kilit(path):
        k = _kart_al(sd, a.gid)
        mevcut = L.kart_durumu_hesapla(k)
        if mevcut in ("iptal", "teslim") and (a.durum == "is-bitti" or (a.durum == "isleniyor" and ajan_tipi not in ("ana", "bilinmiyor"))):
            hata(f"{a.gid} {mevcut} kartta '{a.durum}' kaydedilmez (kapanmış kart canlandırılmaz); yeni kart aç.")
        if a.durum == "is-bitti":
            if ajan_tipi == "ana":
                hata("ana ajan işçi işi bitiremez: işi bir işçi ajana ver.")
            k["son_is_zamani"] = L.simdi()
            k["son_is_sira"] = L.sonraki_sira(k)
            if ajan_id not in k["isciler"]:
                k["isciler"].append(ajan_id)
            for c in a.cikti or []:
                if c not in k["ciktilar"]:
                    k["ciktilar"].append(c)
            tur = _is_turu(k, a, ajan_id, ajan_tipi, k["son_is_sira"])
            if kapi_kaydi:
                tur["kapi"] = kapi_kaydi
            k.setdefault("is_turlari", []).append(tur)
            if a.ozet:
                k["son_ozet"] = L.maskele(a.ozet)[:2000]
            if getattr(a, "kanit", None):
                k["son_kanit"] = _kanit_kirp(sd, a.kanit)
            if teknik_nesne is not None:
                k["teknik"] = teknik_nesne
                k["teknik_zaman"] = L.simdi()
            k["durum"] = "denetimde"
        else:
            if a.durum in ("iptal", "beklemede", "planlandi") and ajan_tipi not in ("ana", "bilinmiyor"):
                hata("kartı iptal/beklemeye yalnız ana ajan alır.")
            if a.durum == "isleniyor" and ajan_tipi not in ("ana", "bilinmiyor"):
                engel = _kart_kilidi_engeli(k, ajan_id)  # yarış: kilit dışındaki denetimden sonra başka koşu girmiş olabilir
                if engel:
                    hata(f"{a.gid} kilitli — {engel}", 6)
            if a.durum == "isleniyor":
                # Çakışma kapısı: aynı fiziksel ağaçta açık kartlarla yazma alanı kesişmesi ya da depo kökü/'**' reddedilir.
                cakismalar = L.yazma_cakismalari(sd, L.proje_dizini(), k)
                if cakismalar:
                    hata(f"{a.gid} isleniyor'a geçemez — " + " | ".join(cakismalar), 5)
            k["durum"] = a.durum
            if a.durum == "beklemede":
                k["beklemede_sira"] = L.sonraki_sira(k)  # sonraki denetimlerle sıralanabilsin
        if a.durum in ("isleniyor", "is-bitti", "planlandi") and oturum_id():
            k["son_oturum"] = oturum_id()  # I-145: güncel sahip; `oturum` oluşturan olarak kalır
        k["gecmis"].append({"zaman": L.simdi(), "olay": a.durum, "ajan": ajan_tipi, "agent_id": ajan_id,
                            "not": L.maskele(a.not_ or "")[:500]})
        uyarilar = _iptal_agac_temizle(k) if a.durum == "iptal" else []
        L.kart_yaz(sd, k)
    print(f"{a.gid} → {k['durum']}")
    for u in uyarilar:
        print(f"uyarı: {u}", file=sys.stderr)
    if a.durum == "is-bitti" and ajan_tipi.split(":", 1)[-1].lower().startswith("isci"):
        _politika_uygula(sd, a.gid)


def _politika_hesapla(sd, gid) -> dict | None:
    """Denetim politikası kararı (L5). mod 'tam' ise None (kayıt yok, çıktı yok); 'golge'/'etkin' ise karar kartın
    politika_kararlari alanına yazılır ve döner. Hata çağırana sızmaz (None)."""
    try:
        import denetim_politika as DP
    except ImportError:  # modülü olmayan kurulum: politika yok = mod 'tam' (sessiz)
        return None
    try:
        cfg = DP.ayar_yukle(sd)
        mod = cfg.get("mod", "tam")
        if mod not in ("golge", "etkin"):
            return None
        kartlar = L.kartlar(sd)
        kart = next((c for c in kartlar if c.get("id") == gid), None)
        if not kart:
            return None
        gecit = DP.gecit_kontrol(kartlar, cfg)
        s = DP.karar(kart, DP.grup_tablosu(kartlar, cfg), cfg, bool(gecit.get("acik")))
        s["mod"] = mod
        DP.kaydet(sd, gid, s, mod)
        return s
    except Exception as e:  # politika is-bitti'yi asla engellemez
        print(f"orkestra: uyarı {gid}: denetim politikası hesaplanamadı ({type(e).__name__}); kart denetimde kaldı",
              file=sys.stderr)
        return None


def _politika_uygula(sd, gid) -> None:
    """is-bitti sonrası: politika 'uygulanir' derse (mod etkin + geçit açık + atla) CLI otomatik onay yazar.
    Kod kartında denetçi onayıyla aynı taze yeşil kuralı geçerlidir; engel varsa onay yazılmaz."""
    s = _politika_hesapla(sd, gid)
    if not s or not s.get("uygulanir"):
        return
    neden = str(s.get("neden") or "-")
    try:
        with L.kilit(L.kart_yolu(sd, gid)):
            k = _kart_al(sd, gid)
            if L.kart_durumu_hesapla(k) != "denetimde":
                return
            if k.get("sinif") == "kod":
                engel = _yesil_kapi_engeli(k)
                if engel:
                    k["gecmis"].append({"zaman": L.simdi(), "olay": "politika-onay-engeli", "ajan": "politika",
                                        "not": L.maskele(engel)[:300]})
                    L.kart_yaz(sd, k)
                    print(f"orkestra: politika otomatik onayı verilmedi: {engel}", file=sys.stderr)
                    return
            kayit = {"zaman": L.simdi(), "sira": L.sonraki_sira(k), "karar": "onay", "denetim_turu": "otomatik",
                     "gerekce": f"politika: {neden}", "talimat": "", "agent_id": None, "ajan": "politika",
                     "basamak": k.get("basamak"),
                     "politika": {x: s.get(x) for x in ("karar", "neden", "grup", "mod", "orneklenmis", "uygulanir")}}
            k.setdefault("denetimler", []).append(kayit)
            k["durum"] = L.kart_durumu_hesapla(k)
            k["gecmis"].append({"zaman": kayit["zaman"], "olay": "denetim:onay", "ajan": "politika", "agent_id": None,
                                "otomatik": True})
            L.kart_yaz(sd, k)
            L.atomik_yaz(os.path.join(sd, "gorevler", f"{gid}.denetim.json"),
                         json.dumps(k["denetimler"], ensure_ascii=False, indent=2) + "\n")
    except Exception as e:
        print(f"orkestra: uyarı {gid}: politika otomatik onayı yazılamadı ({type(e).__name__}); kart denetimde kaldı",
              file=sys.stderr)
        return
    print(f"OTOMATIK-ONAY: politika {neden}")
    if k["durum"] == "onaylandi" and _oto_teslim_gecerli(k):
        _oto_teslim_dene(sd, gid, f"politika: {neden}")


def _neden_kodlari() -> str:
    return ", ".join(RN.NEDENLER)


def _neden_yardim() -> str:
    satirlar = [f"  {k}: {v}" for k, v in RN.NEDENLER.items()]
    return "\n".join(["ret için ZORUNLU ret nedeni kodu (onayda yok sayılır). Geçerli kodlar:"] + satirlar)


def cmd_kart_denetim(a):
    neden = getattr(a, "neden", None)
    if a.karar == "ret":
        if not neden:
            hata(f"ret kararında --neden <kod> zorunlu. Geçerli kodlar: {_neden_kodlari()}", 2)
        if neden not in RN.NEDENLER:
            hata(f"geçersiz ret nedeni kodu: {neden!r}. Geçerli kodlar: {_neden_kodlari()}", 2)
    else:
        neden = None  # onayda --neden yok sayılır
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    if not ajan_tipi.endswith("denetci"):
        hata(f"denetim kararını yalnız denetçi ajan yazar (sen: {ajan_tipi}).", 3)
    duz = []
    if getattr(a, "duzeltmeler_dosya", None):
        if a.karar != "onay":
            hata("--duzeltmeler-dosya yalnız onay kararında geçerli (içerik eksiği ret ile işçiye döner).", 2)
        try:
            with open(a.duzeltmeler_dosya, encoding="utf-8") as f:
                duz = json.load(f)
        except (OSError, ValueError) as e:
            hata(f"--duzeltmeler-dosya okunamadı: {e}", 2)
    path = L.kart_yolu(sd, a.gid)
    with L.kilit(path):
        k = _kart_al(sd, a.gid)
        if ajan_id in k["isciler"]:
            hata("bu kartta işçi olarak çalışan ajan kendi işini denetleyemez.", 3)
        if not k.get("son_is_zamani"):
            hata("denetlenecek işçi çıktısı yok (işçi `kart durum … is-bitti` demedi).", 3)
        if L.kart_durumu_hesapla(k) in ("iptal", "teslim"):
            hata(f"{a.gid} kapanmış kartta denetim kararı yazılmaz.", 3)
        son_den = max((d.get("sira", -1) for d in k["denetimler"] if isinstance(d.get("sira"), int)), default=-1)
        if isinstance(k.get("son_is_sira"), int) and k["son_is_sira"] < son_den:
            hata("son denetimden sonra yeni işçi çıktısı yok (işçi yeniden `is-bitti` demeden ikinci karar yazılmaz).", 3)
        if a.karar == "onay" and k.get("sinif") == "kod":
            engel = _yesil_kapi_engeli(k)
            if engel:
                hata(f"kod kartında onay için taze ve geçen bir yeşil test koşusu gerekli: {engel} "
                     f"(`orkestra kart test-kos {a.gid} --asama yesil`). Karar kaydedilmedi.", 3)
        kayit = {"zaman": L.simdi(), "sira": L.sonraki_sira(k), "karar": a.karar, "gerekce": L.maskele(a.gerekce)[:3000],
                 "talimat": L.maskele(a.talimat or "")[:3000], "agent_id": ajan_id, "ajan": ajan_tipi,
                 "basamak": k["basamak"]}
        if a.karar == "onay":
            son_is = (k.get("is_turlari") or [{}])[-1]
            hatalar = DK.kapi(L.proje_dizini(), k.get("ciktilar"), son_is.get("cikti_dosya_sha"), duz)
            if hatalar:
                hata("A9 düzeltme kapısı onayı reddetti (karar kaydedilmedi): " + "; ".join(hatalar[:5]), 3)
            if duz:
                kayit["duzeltmeler"] = [{x: (L.maskele(v)[:500] if isinstance(v, str) else v) for x, v in d.items()}
                                        for d in duz]
                kayit["duzeltildi"] = DK.neden_kodlari(duz)
        if neden:
            kayit["neden"] = neden
            kayit["kok"] = RN.kok(neden)
            ids = L.ret_kriterleri(a.gerekce)
            onceki: set = set()
            for d in reversed(k["denetimler"]):
                if d.get("karar") == "ret":
                    onceki = set(d.get("kriter_ids") or [])
                    break
            kayit["kriter_ids"] = ids
            kayit["tekrar_kriter"] = sorted((i for i in ids if i in onceki), key=lambda x: int(x[1:]))
        k["denetimler"].append(kayit)
        if ajan_id not in k["denetciler"]:
            k["denetciler"].append(ajan_id)
        k["durum"] = L.kart_durumu_hesapla(k)
        olay = {"zaman": kayit["zaman"], "olay": f"denetim:{a.karar}", "ajan": ajan_tipi, "agent_id": ajan_id}
        if neden:
            olay["neden"] = neden
        k["gecmis"].append(olay)
        L.kart_yaz(sd, k)
        L.atomik_yaz(os.path.join(sd, "gorevler", f"{a.gid}.denetim.json"),
                     json.dumps(k["denetimler"], ensure_ascii=False, indent=2) + "\n")
    print(f"{a.gid} denetim: {a.karar} → {k['durum']}")
    if a.karar == "onay" and k["durum"] == "onaylandi" and _oto_teslim_gecerli(k):
        _oto_teslim_dene(sd, a.gid, a.gerekce)


def _oto_teslim_dene(sd, gid, gerekce) -> None:
    """G-124: onaylı oto_teslim kod kartını teslim eder (kilit dışında çağrılır). Hata/birleşmeme kartı 'onaylandi'
    bırakır, stderr'e uyarı yazar; denetim komutunun çıkış kodunu değiştirmez."""
    ozet = "oto: " + (L.maskele(gerekce or "").strip()[:200])
    try:
        notlar = _teslim_et(sd, gid, ozet, oto=True)
    except Exception as e:  # birleşme/teslim hatası denetim kararını bozmaz
        mesaj = getattr(e, "mesaj", None) or f"{type(e).__name__}: {e}"
        try:
            with L.kilit(L.kart_yolu(sd, gid)):
                k = L.kart_oku(sd, gid)
                if k and k.get("durum") != "teslim":
                    if k.get("durum") == "beklemede" and L.kart_durumu_hesapla({**k, "durum": None}) == "onaylandi":
                        k["durum"] = "onaylandi"  # birleşme çatışması kartı beklemede bırakmış; onay korunur
                    k["gecmis"].append({"zaman": L.simdi(), "olay": "oto-teslim-hata", "not": str(mesaj)[:500]})
                    L.kart_yaz(sd, k)
        except Exception:
            pass
        print(f"orkestra: uyarı {gid}: oto-teslim yapılamadı, kart 'onaylandi' kaldı — {mesaj}", file=sys.stderr)
        return
    for m in notlar:
        print(m)
    print(f"{gid} → teslim (oto)")


def teslim_bekleyenleri_topla(sd) -> tuple[list, list]:
    """I-145: denetçi onaylı, oto-teslim politikasına uyan ama `teslim` olmamış kartları teslim etmeyi dener.
    Döner: (teslim edilenler, bekleyenler). Son olayı `oto-teslim-hata` olan kart yeniden denenmez (olay yinelenmez);
    bekleyen sayılır. Tekrar çalıştırılabilir: teslim olan kart ikinci taramada görünmez."""
    teslim, bekleyen = [], []
    for k in L.kartlar(sd, derin=False):
        gid = k.get("id")
        if L.kart_durumu_hesapla(k) != "onaylandi" or not _oto_teslim_gecerli(k):
            continue
        if ((k.get("gecmis") or [{}])[-1]).get("olay") == "oto-teslim-hata":
            bekleyen.append(gid)
            continue
        _oto_teslim_dene(sd, gid, "tarama: onaylı kart teslim edilmemişti")
        son = L.kart_oku(sd, gid)
        (teslim if son and son.get("durum") == "teslim" else bekleyen).append(gid)
    return teslim, bekleyen


def cmd_kart_teslim_bekleyen(a):
    sd = sd_gerekli()
    _, ajan_tipi = _kim(a)
    if ajan_tipi not in ("ana", "bilinmiyor"):
        hata("teslimi yalnız ana ajan yapar.", 3)
    teslim, bekleyen = teslim_bekleyenleri_topla(sd)
    print(f"{len(teslim)} teslim" + (f": {', '.join(teslim)}" if teslim else ""))
    if bekleyen:
        print(f"{len(bekleyen)} teslim bekliyor: {', '.join(bekleyen)}")


def _yesil_kapi_engeli(k: dict) -> str | None:
    """Kod kartı onayı için engel metni; engel yoksa None. Koşul: son is-bitti'den SONRAKİ en son test koşusu
    geçen bir yeşil VE şu an yeniden hesaplanan test dosyası özetleri kilitle birebir aynı."""
    try:  # ağaç proje kökünü kapsamıyorsa paylaşılan ağaca sessizce düşülmez (önceki yeşil de ağacı sınamadı)
        kok = L.kart_proje_koku(L.proje_dizini(), k)
    except ValueError as e:
        return str(e)
    kosular = k.get("test_kosulari") or []
    son_is_sira = k.get("son_is_sira")
    kapi_sira = ((k.get("is_turlari") or [{}])[-1].get("kapi") or {}).get("yesil_sira")
    if son_is_sira is not None:
        alt = kapi_sira if isinstance(kapi_sira, int) else son_is_sira + 1
        sonraki = [x for x in kosular if (x.get("sira") or 0) >= alt]
    else:
        sonraki = [x for x in kosular if x.get("zaman", "") >= (k.get("son_is_zamani") or "")]
    if not sonraki:
        return "son is-bitti'den sonra yeşil koşu yok (yoksa bayat)"
    son = sonraki[-1]
    if son.get("asama") != "yesil":
        return "en son test koşusu yeşil değil"
    if not son.get("gecti"):
        return "en son yeşil koşu geçmedi"
    # Koşunun kökü güncel test kökü olmalı (test-ayar ile kök değişince eski kökteki yeşil kanıt değildir).
    # Kök alanı olmayan eski kayıtlar yalnız test_koku'suz kartta geçerli kalır (geriye uyum).
    kosu_koku = son.get("kok")
    if kosu_koku is None:
        if k.get("test_koku"):
            return "en son yeşil koşunun test kökü kayıtlı değil; güncel test kökünde yeniden yeşil koşulmalı"
    elif L._kiyas(os.path.abspath(kosu_koku)) != L._kiyas(os.path.abspath(kok)):
        return (f"en son yeşil koşu başka bir test kökünde ({kosu_koku}); güncel test kökünde ({kok}) yeniden "
                "yeşil koşulmalı")
    if not k.get("test_kilidi"):
        return "test kilidi yok"
    mevcut = L.test_dosyasi_ozetleri(kok, k.get("test_alani") or [])
    if not L.kilitle_tutarli(k["test_kilidi"], mevcut):
        fark = L.kilit_farki(k["test_kilidi"].get("dosyalar"), mevcut)
        return "yeşilden sonra test dosyaları kilitten saptı (" + ", ".join(
            f"{ad}: {len(v)}" for ad, v in fark.items() if v) + ")"
    return None


def _eski_surumde_kos(proje: str, ref: str, komut: str, dosyalar, zaman_asimi: float) -> tuple[int, str, float, str]:
    """Kırmızı kapı (005): testler çalışma ağacındaki hâliyle, uygulama kodu `ref` sürümünde (HEAD varsayılan) koşar.

    Çalışma ağacına dokunulmaz: `ref` geçici bir `git worktree` olarak ayrı klasöre açılır, test dosyaları ('/'li göreli
    yollar) çalışma ağacından oraya kopyalanır, komut orada koşar; worktree her durumda silinir. → (kod, çıktı, süre, ref sha)."""
    import shutil
    import subprocess
    import tempfile

    def git(*args, cwd=proje):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", **cfg.PENCERESIZ)
    ust = git("rev-parse", "--show-toplevel")
    if ust.returncode != 0:
        hata("--eski-surumde için proje bir git deposunda olmalı.")
    ust = os.path.abspath(ust.stdout.strip())
    sha = git("rev-parse", "--verify", "--quiet", ref + "^{commit}")
    if sha.returncode != 0:
        hata(f"--surum-ref bulunamadı: {ref}")
    sha = sha.stdout.strip()
    gecici = tempfile.mkdtemp(prefix="ork_kirmizi_")
    wt = os.path.join(gecici, "wt")
    try:
        ekle = git("worktree", "add", "--detach", "--quiet", wt, sha, cwd=ust)
        if ekle.returncode != 0:
            hata("geçici sürüm klasörü açılamadı: " + (ekle.stderr or ekle.stdout).strip()[:300])
        rel = os.path.relpath(os.path.abspath(proje), ust)
        kok = os.path.normpath(os.path.join(wt, rel))
        for y in dosyalar:
            hedef = os.path.join(kok, *y.split("/"))
            os.makedirs(os.path.dirname(hedef), exist_ok=True)
            shutil.copy2(os.path.join(os.path.abspath(proje), *y.split("/")), hedef)
        kod, cikti, sure = L.paralel_kos(komut, kok, zaman_asimi)
        return kod, cikti, sure, sha
    finally:
        git("worktree", "remove", "--force", wt, cwd=ust)
        shutil.rmtree(gecici, ignore_errors=True)
        git("worktree", "prune", cwd=ust)


def cmd_kart_test_kos(a):
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    path = L.kart_yolu(sd, a.gid)
    k = _kart_al(sd, a.gid)
    if k.get("sinif") != "kod":
        hata(f"test-kos yalnız kod kartında çalışır (sinif: {k.get('sinif')}).")
    if not k.get("test_komutu") or not k.get("test_alani"):
        hata("kartta test_komutu/test_alani yok.")
    if a.asama == "kirmizi" and k.get("test_kilidi"):
        hata("test dosyaları zaten kilitli: kırmızı yeniden koşulamaz (kilidi yalnız ana ajan açar: `kart test-kilit-ac`).")
    eski = bool(getattr(a, "eski_surumde", False))
    if (eski or getattr(a, "surum_ref", None)) and a.asama != "kirmizi":
        hata("--eski-surumde/--surum-ref yalnız --asama kirmizi ile kullanılır.")
    if getattr(a, "surum_ref", None) and not eski:
        hata("--surum-ref yalnız --eski-surumde ile birlikte verilir.")
    tdd = tdd_karti(k)
    if a.asama == "kirmizi" and not tdd:
        hata("kart TDD değil (tdd=false): kırmızı aşama yok; testler işçiyle birlikte yazılır, yeşilde kilitlenir.")
    if a.asama == "yesil" and tdd and not k.get("test_kilidi"):
        hata("test dosyalarında kilit yok: önce kırmızı aşama koşulmalı (`kart test-kos … --asama kirmizi`).")
    if a.zaman_asimi <= 0:
        hata("--zaman-asimi pozitif olmalı.")
    try:  # kart ağacı varsa testler ve özetler ağaçtaki karşılıkta; ağaç proje kökünü kapsamıyorsa açık hata
        proje = L.kart_proje_koku(L.proje_dizini(), k)
    except ValueError as e:
        hata(str(e))
    once = L.test_dosyasi_ozetleri(proje, k["test_alani"])
    if not once:
        if k.get("test_koku"):
            hata(f"test dosyası yok: test_alani ({', '.join(k['test_alani'])}) test kökünde ({proje}) hiçbir dosyaya "
                 "uymuyor.")
        hata(f"test dosyası yok: test_alani ({', '.join(k['test_alani'])}) hiçbir proje dosyasına uymuyor.")
    zaman = L.simdi()
    komut, daralma = L.test_komutu_daralt(k["test_komutu"], proje, k["test_alani"])
    if komut is None:
        hata(f"{daralma}: test_alani ({', '.join(k['test_alani'])}) test_*.py dosyasına uymuyor.")
    if daralma:
        print(f"orkestra: {daralma}", file=sys.stderr)
    eski_sha = None
    if eski:
        kod, cikti, sure, eski_sha = _eski_surumde_kos(proje, getattr(a, "surum_ref", None) or "HEAD", komut, sorted(once), a.zaman_asimi)
        print(f"orkestra: kırmızı kapı {eski_sha[:10]} sürümünde koşuldu (çalışma ağacı değişmedi)", file=sys.stderr)
    else:
        kod, cikti, sure = L.paralel_kos(komut, proje, a.zaman_asimi)
    sonra = L.test_dosyasi_ozetleri(proje, k["test_alani"])
    karar = _test_karari(sd, a.gid, k, proje, kod, cikti, once)
    with L.kilit(path):
        k = _kart_al(sd, a.gid)  # koşu sürerken kart değişmiş olabilir
        k.setdefault("test_kosulari", [])
        if a.asama == "kirmizi":
            if k.get("test_kilidi"):
                hata("test dosyaları koşu sırasında kilitlendi; kırmızı kaydedilmedi.")
            gecti = karar["kirmizi"]
            hash_tutarli = None  # kırmızıda kıyas yok: kilidi bu koşu kurar
            if gecti:
                k["test_kilidi"] = {"zaman": L.simdi(), "dosyalar": once}
        elif not tdd:
            # TDD'siz kod kartı: testler işçinin; kilit her geçen yeşilde koşulan dosyalarla yeniden kurulur.
            hash_tutarli = once == sonra
            gecti = karar["yesil"] and hash_tutarli
            if gecti:
                k["test_kilidi"] = {"zaman": L.simdi(), "dosyalar": sonra, "yesilde": True}
        else:
            if not k.get("test_kilidi"):
                hata("test kilidi koşu sırasında açıldı; yeşil kaydedilmedi.")
            hash_tutarli = L.kilitle_tutarli(k["test_kilidi"], once) and L.kilitle_tutarli(k["test_kilidi"], sonra)
            gecti = karar["yesil"] and hash_tutarli
        kayit = {"zaman": zaman, "sira": L.sonraki_sira(k), "asama": a.asama, "cikis_kodu": kod,
                 "hash_tutarli": hash_tutarli, "gecti": gecti, "sure_s": sure,
                 "kok": os.path.abspath(proje).replace("\\", "/"),  # onay kapısı yalnız güncel kökteki koşuyu sayar
                 "dusenler": karar["dusenler"], "yabanci_dusenler": karar["yabanci_dusenler"]}
        if eski_sha:
            kayit["eski_surum"] = eski_sha
        if not karar["ayristirildi"]:
            kayit["ayristirilamadi"] = True
        if karar["toplama_nedeni"]:
            kayit["toplama_hatasi"] = karar["toplama_nedeni"]
        kayit.update({"cikti_kuyrugu": L.maskele(cikti)[-L.TEST_KUYRUK_MAX:], "ajan": ajan_tipi, "agent_id": ajan_id})
        k["test_kosulari"].append(kayit)
        L.kart_yaz(sd, k)
    durum = "GEÇTİ" if gecti else "GEÇMEDİ"
    ek = ""
    if a.asama == "kirmizi" and not gecti:
        if kod == -1:
            ek = " (zaman aşımı; kilit yazılmadı)"
        else:
            ek = f" ({karar['kirmizi_neden'] or 'kırmızı aşamada test BAŞARISIZ olmalıydı'}; kilit yazılmadı)"
    elif a.asama == "kirmizi":
        ek = f" — {len(once)} test dosyası kilitlendi"
    elif not hash_tutarli:
        fark = L.kilit_farki(k["test_kilidi"].get("dosyalar"), sonra)
        ek = " — test dosyaları kilitten saptı: " + ", ".join(f"{ad} {', '.join(v)}" for ad, v in fark.items() if v)
    elif not gecti and karar["yesil_neden"]:
        ek = f" — {karar['yesil_neden']}"
    print(f"{a.gid} test {a.asama}: {durum} (çıkış {kod}, {sure} sn){ek}")
    if karar["ozet"]:
        print(karar["ozet"])
    if not gecti:
        sys.exit(4)


def _test_sahibi(sd: str, gid: str, kimlik: str, kosu_koku: str) -> str | None:
    """Düşen test kimliği hangi AÇIK kod kartının (durumu teslim/iptal değil, kendisi hariç) test_alani'nda
    (o kartın kendi test köküne göre)? Sahip yoksa None."""
    proje = L.proje_dizini()
    for o in L.kartlar(sd):
        if o.get("id") == gid or o.get("sinif") != "kod" or o.get("durum") in ("teslim", "iptal"):
            continue
        if not o.get("test_alani"):
            continue
        if L.test_alaninda_mi(kimlik, L.kart_test_koku(proje, o), o["test_alani"], kosu_koku):
            return o["id"]
    return None


def _kisa(kimlikler: list[str], n: int = 3) -> str:
    return ", ".join(kimlikler[:n]) + (f" (+{len(kimlikler) - n})" if len(kimlikler) > n else "")


def _test_karari(sd: str, gid: str, k: dict, proje: str, kod: int, cikti: str, once: dict) -> dict:
    """Test kapısı kararı düşen test kimliklerinden (çıkış kodu tek başına değil).

    KIRMIZI geçer ⇔ çıkış 1, toplama/kullanım hatası yok VE kartın test_alani'ndan en az bir test düştü.
    YEŞİL geçer ⇔ toplama/kullanım hatası yok VE test_alani'ndan düşen yok VE sahipsiz dış düşen yok VE
    (çıkış 0 YA DA dışarıda düşen her test başka bir açık kod kartının test_alani'nda). Çıktı pytest/unittest
    olarak ayrıştırılamazsa eski kural: kırmızı çıkış ∉ {0, -1}, yeşil çıkış 0."""
    a = L.test_ciktisi_ayristir(cikti, kod)
    karar = {"ayristirildi": a["ayristirildi"], "toplama_nedeni": a["toplama_nedeni"], "dusenler": [],
             "yabanci_dusenler": [], "kirmizi_neden": None, "yesil_neden": None, "ozet": ""}
    if not a["ayristirildi"]:
        karar.update(kirmizi=kod not in (0, -1), yesil=kod == 0,
                     ozet="uyarı: test çıktısı pytest/unittest olarak ayrıştırılamadı; karar çıkış koduna göre")
        return karar
    kendi_dosyalar = {L._kiyas(y) for y in once}
    for kimlik in a["dusenler"]:
        dosyalar = L.test_kimligi_dosyalari(kimlik)
        if (any(L._kiyas(d) in kendi_dosyalar for d in dosyalar)
                or L.test_alaninda_mi(kimlik, proje, k.get("test_alani") or [])):
            karar["dusenler"].append(kimlik)
        else:
            karar["yabanci_dusenler"].append({"test": kimlik, "dosya": dosyalar[0] if dosyalar else None,
                                              "kart": _test_sahibi(sd, gid, kimlik, proje)})
    sahipsiz = [y["test"] for y in karar["yabanci_dusenler"] if not y["kart"]]
    toplama = a["toplama_hatasi"]
    karar["kirmizi"] = kod == 1 and not toplama and bool(karar["dusenler"])
    # Gizli düşüş: pytest özetindeki failed + error sayısı ayrıştırılan düşüş SATIRI sayısından fazlaysa (-rN,
    # kısaltılmış/eksik özet) düşenlerin hepsi görülmedi; yeşil buna güvenip geçmez. Kıyas tekil kimlik sayısıyla
    # değil: bir test birden çok satırla düşebilir (N SUBFAILED, FAILED + teardown ERROR) ve özet her satırı sayar.
    ozet = a.get("ozet_dusen")
    satir = a.get("dusus_satiri", 0)
    gizli = ozet is not None and ozet > satir
    karar["yesil"] = (not toplama and not gizli and not karar["dusenler"] and not sahipsiz
                      and (kod == 0 or (kod == 1 and bool(karar["yabanci_dusenler"]))))
    yabanci = len(karar["yabanci_dusenler"])
    if toplama:
        karar["kirmizi_neden"] = karar["yesil_neden"] = a["toplama_nedeni"] + "; testler güvenilir biçimde koşmadı"
    else:
        if kod == 0:
            karar["kirmizi_neden"] = "kırmızı aşamada test BAŞARISIZ olmalıydı"
        elif not karar["dusenler"]:
            karar["kirmizi_neden"] = f"test_alani'ndan düşen test yok (dış düşen: {yabanci})"
        if karar["dusenler"]:
            karar["yesil_neden"] = "test_alani'ndan düşen var: " + _kisa(karar["dusenler"])
        elif sahipsiz:
            karar["yesil_neden"] = "sahipsiz dış düşen (hiçbir açık kod kartının test_alani'nda değil): " + _kisa(sahipsiz)
        elif gizli:
            karar["yesil_neden"] = (f"gizli düşüş: pytest özeti {ozet} failed/error diyor, ayrıştırılan düşüş "
                                    f"satırı {satir}")
        elif kod != 0 and not yabanci:
            karar["yesil_neden"] = f"çıkış {kod} ama düşen test kimliği bulunamadı"
    parcalar = [f"düşen (test_alani): {len(karar['dusenler'])}"]
    if karar["yabanci_dusenler"]:
        sahipli = [f"{y['test']} → {y['kart']}" for y in karar["yabanci_dusenler"] if y["kart"]]
        parcalar.append(f"dış düşen: {len(karar['yabanci_dusenler'])} (sahipli {len(sahipli)}, sahipsiz {len(sahipsiz)})")
        if sahipli:
            parcalar.append("sahipli: " + _kisa(sahipli))
    karar["ozet"] = "; ".join(parcalar)
    return karar


def cmd_kart_test_kilit_ac(a):
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    if ajan_tipi != "ana":
        hata(f"test kilidini yalnız ana ajan açar (sen: {ajan_tipi}).", 3)
    if not (a.neden or "").strip():
        hata("--neden boş olamaz.")
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if not k.get("test_kilidi"):
            hata("kartta açılacak test kilidi yok.")
        k["test_kilidi"] = None
        k["gecmis"].append({"zaman": L.simdi(), "olay": "test-kilit-ac", "ajan": ajan_tipi, "agent_id": ajan_id,
                            "not": L.maskele(a.neden)[:500]})
        L.kart_yaz(sd, k)
    print(f"{a.gid} test kilidi açıldı")


def cmd_kart_test_ayar(a):
    """Kod kartının test ayarları (yalnız ana ajan). Kilit yokken test_koku/test_komutu/test_alani serbestçe değişir;
    kilit varken yalnız test_koku değişir ve yalnız yeni kökte hesaplanan test özetleri kilitle birebir aynıysa."""
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    if ajan_tipi != "ana":
        hata(f"test ayarlarını yalnız ana ajan değiştirir (sen: {ajan_tipi}).", 3)
    if a.test_koku is None and a.test_komutu is None and not a.test_alani:
        hata("değiştirilecek alan yok: --test-koku, --test-komutu ya da --test-alani verin.")
    yeni = {}
    if a.test_koku is not None:
        if a.test_koku.strip():
            try:
                yeni["test_koku"] = L.test_koku_dogrula(a.test_koku)
            except ValueError as e:
                hata(str(e))
        else:
            yeni["test_koku"] = None  # boş değer: test_koku kaldırılır, kök yeniden proje olur
    if a.test_komutu is not None:
        if not a.test_komutu.strip():
            hata("--test-komutu boş olamaz.")
        yeni["test_komutu"] = a.test_komutu.strip()
    if a.test_alani:
        alan = [g.strip() for g in a.test_alani if g and g.strip()]
        if not alan:
            hata("--test-alani boş olamaz.")
        yeni["test_alani"] = alan
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if k.get("sinif") != "kod":
            hata(f"test-ayar yalnız kod kartında çalışır (sinif: {k.get('sinif')}).")
        if L.kart_durumu_hesapla(k) in ("teslim", "iptal"):
            hata(f"kapalı kartın test ayarı değişmez ({k.get('durum')}).")
        degisen = {ad: {"eski": k.get(ad), "yeni": v} for ad, v in yeni.items() if k.get(ad) != v}
        eklenen = []
        if yeni.get("test_alani"):
            kok = yeni["test_koku"] if "test_koku" in yeni else k.get("test_koku")
            kok = str(kok).replace("\\", "/").rstrip("/") if kok else ""
            ya = list(k.get("yazma_alani") or [])
            var = {os.path.normcase(x).replace("\\", "/") for x in ya}
            for desen in yeni["test_alani"]:
                girdi = kok + "/" + desen if kok else desen
                n = os.path.normcase(girdi).replace("\\", "/")
                if n not in var:
                    var.add(n)
                    ya.append(girdi)
                    eklenen.append(girdi)
            if eklenen:
                k["yazma_alani"] = ya
        if not degisen and not eklenen:
            print(f"{a.gid} test ayarı: değişiklik yok")
            return
        if k.get("test_kilidi"):
            yasak = [ad for ad in degisen if ad != "test_koku"]
            if yasak:
                hata(f"test dosyaları kilitli: yalnız test_koku değişebilir ({', '.join(yasak)} değişmez; önce ana ajan "
                     f"`orkestra kart test-kilit-ac {a.gid}` ile kilidi açar).")
            if "test_koku" in degisen:  # yalnız yazma_alani genişlemesinde kök doğrulaması gerekmez
                aday = dict(k)
                aday["test_koku"] = yeni["test_koku"]
                try:
                    kok = L.kart_proje_koku(L.proje_dizini(), aday)
                except ValueError as e:
                    hata(str(e))
                mevcut = L.test_dosyasi_ozetleri(kok, k.get("test_alani") or [])
                if not L.kilitle_tutarli(k["test_kilidi"], mevcut):
                    fark = L.kilit_farki(k["test_kilidi"].get("dosyalar"), mevcut)
                    hata(f"yeni test kökünde ({kok}) test dosyaları kilitle aynı değil (" + "; ".join(
                        f"{ad}: {', '.join(v)}" for ad, v in fark.items() if v) + "); test_koku değişmedi.")
        for ad, d in degisen.items():
            if d["yeni"] is None:
                k.pop(ad, None)
            else:
                k[ad] = d["yeni"]
        k["gecmis"].append({"zaman": L.simdi(), "olay": "test-ayar", "ajan": ajan_tipi, "agent_id": ajan_id,
                            "degisen": degisen})
        L.kart_yaz(sd, k)
    print(f"{a.gid} test ayarı: " + ", ".join(f"{ad} → {d['yeni'] if d['yeni'] is not None else '(proje)'}"
                                              for ad, d in degisen.items()))


def cmd_kart_yukselt(a):
    sd = sd_gerekli()
    b = a.basamak.upper()
    if b not in BASAMAKLAR:
        hata("basamak T0..T4 olmalı")
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if BASAMAKLAR.index(b) <= BASAMAKLAR.index(k["basamak"]):
            hata("yükseltme yalnız yukarı yapılır.")
        durum = L.kart_durumu_hesapla(k)
        if durum in ("teslim", "iptal", "onaylandi"):   # biten/onaylı kart yeniden işlenmeye çevrilmez
            hata(f"yükseltme {durum} kartta yapılmaz; yeni kart aç.")
        k["gecmis"].append({"zaman": L.simdi(), "olay": "yukseltme", "eski": k["basamak"], "yeni": b, "not": a.neden})
        k["basamak"] = b
        k["durum"] = "isleniyor"
        k.pop("son_is_zamani", None)
        k.pop("son_is_sira", None)
        L.kart_yaz(sd, k)
    print(f"{a.gid} → {b}")


class _TeslimHatasi(Exception):
    def __init__(self, mesaj, kod=2):
        super().__init__(mesaj)
        self.mesaj, self.kod = mesaj, kod


def _teslim_et(sd, gid, ozet, oto=False) -> list:
    """Tek kartı teslim eder (`kart teslim` ve `kart teslim-toplu` ortak çekirdeği). Yazdırmaz; birleştirme
    mesajlarını döndürür. Reddedilirse _TeslimHatasi(mesaj, çıkış_kodu) atar."""
    notlar = []
    madde = is_id = None
    with L.kilit(L.kart_yolu(sd, gid)):
        k = L.kart_oku(sd, gid)
        if not k:
            raise _TeslimHatasi(f"kart yok: {gid}")
        madde, is_id = k.get("madde"), k.get("is")
        durum = L.kart_durumu_hesapla(k)
        if durum == "teslim" and not oto and any(x.get("olay") == "oto-teslim" for x in k.get("gecmis") or []):
            return [f"{gid} denetçi onayında kendiliğinden teslim olmuştu (oto-teslim); yeniden teslim gerekmez"]
        beklemeden = False
        if durum == "beklemede":
            # Beklemede'ye alınmadan önce onay almış kart teslim edilebilir (sığ kopyada durum çekilir).
            if L.kart_durumu_hesapla({**k, "durum": None}) == "onaylandi":
                beklemeden = True
                durum = "onaylandi"
        if durum != "onaylandi":
            raise _TeslimHatasi(f"teslim için denetçi onayı gerekli (durum: {durum}).", 3)
        if (k.get("calisma_agaci") or {}).get("yol"):
            ok, mesaj = _birlestir(sd, k)
            L.kart_yaz(sd, k)
            if not ok:
                raise _TeslimHatasi(f"teslim reddedildi: kart çalışma ağacı birleşmedi — {mesaj}", 4)
            notlar.append(mesaj)
        if beklemeden:
            # Olay yalnız teslim gerçekleşecekse yazılır (birleştirme başarısızsa yazılmaz; yeniden denemede yinelenmez).
            k["gecmis"].append({"zaman": L.simdi(), "olay": "beklemeden-teslim"})
        k["durum"] = "teslim"
        k["teslim_ozeti"] = L.maskele(ozet or "")[:2000]
        if oto:
            k["gecmis"].append({"zaman": L.simdi(), "olay": "oto-teslim"})
        k["gecmis"].append({"zaman": L.simdi(), "olay": "teslim"})
        L.kart_yaz(sd, k)
    L.defter_ekle(sd, {"gorev": gid, "surec": "sentez", "ajan": "ana-ajan", "model": "-",
                       "yaptim": "Onaylı çıktıyı topladım ve teslim ettim.", "sonuc": "TESLİM", "not": ozet or ""})
    if madde:  # todo bayatlamasını önler; eşleşme yok/çok ise teslim engellenmez, yalnız uyarı
        ok, iletisi = _ik().todo_madde_bitir(sd, is_id, madde, gid)
        if ok:
            notlar.append(iletisi)
        else:
            print(f"orkestra: uyarı {gid}: {iletisi}", file=sys.stderr)
    return notlar


def cmd_kart_teslim(a):
    sd = sd_gerekli()
    _, ajan_tipi = _kim(a)
    if ajan_tipi not in ("ana", "bilinmiyor"):
        hata("teslimi yalnız ana ajan yapar.", 3)
    try:
        notlar = _teslim_et(sd, a.gid, a.ozet)
    except _TeslimHatasi as e:
        hata(e.mesaj, e.kod)
    for m in notlar:
        print(m)
    print(f"{a.gid} → teslim")


def cmd_kart_butce(a):
    """Kart bütçesini göster; --usd ile tavanı ayarla (yalnız ana ajan)."""
    import butce
    sd = sd_gerekli()
    if a.usd is not None:
        _, ajan_tipi = _kim(a)
        if ajan_tipi not in ("ana", "bilinmiyor"):
            hata("bütçeyi yalnız ana ajan değiştirir.", 3)
        if a.usd <= 0:
            hata("--usd pozitif olmalı.")
        path = L.kart_yolu(sd, a.gid)
        with L.kilit(path):
            k = _kart_al(sd, a.gid)
            k["butce"] = {**(k.get("butce") or {}), "usd": float(a.usd)}
            k["gecmis"].append({"zaman": L.simdi(), "olay": "butce", "usd": float(a.usd)})
            L.kart_yaz(sd, k)
    print(json.dumps(butce.durum(sd, _kart_al(sd, a.gid)), ensure_ascii=False))


def cmd_kart_teslim_toplu(a):
    sd = sd_gerekli()
    _, ajan_tipi = _kim(a)
    if ajan_tipi not in ("ana", "bilinmiyor"):
        hata("teslimi yalnız ana ajan yapar.", 3)
    try:
        with open(a.json_dosya, encoding="utf-8") as f:
            girdiler = json.load(f)
    except (OSError, ValueError) as e:
        hata(f"json dosyası okunamadı: {e}")
    if not isinstance(girdiler, list):
        hata('json dosyası bir dizi olmalı: [{"id": ..., "ozet": ...}, ...]')
    sonuc, hatali = [], False
    for g in girdiler:
        gid = g.get("id") if isinstance(g, dict) else None
        if not isinstance(gid, str) or not gid:
            sonuc.append({"id": gid, "sonuc": "hata", "mesaj": "girdide `id` yok"})
            hatali = True
            continue
        ozet = g.get("ozet")
        try:
            notlar = _teslim_et(sd, gid, ozet if isinstance(ozet, str) else None)
            sonuc.append({"id": gid, "sonuc": "teslim", "mesaj": " ".join(notlar + [f"{gid} → teslim"])})
        except _TeslimHatasi as e:
            sonuc.append({"id": gid, "sonuc": "hata", "mesaj": e.mesaj})
            hatali = True
        except Exception as e:  # bir kartın beklenmeyen hatası diğerlerini durdurmaz
            sonuc.append({"id": gid, "sonuc": "hata", "mesaj": f"{type(e).__name__}: {e}"})
            hatali = True
    print(json.dumps(sonuc, ensure_ascii=False))
    sys.exit(4 if hatali else 0)


def _girdi_agacsiz(girdi: str) -> str:
    satirlar = (girdi or "").split("\n")
    if satirlar and satirlar[0].startswith(L.CALISMA_AGACI_ONEKI):
        satirlar = satirlar[1:]
    return "\n".join(satirlar)


def cmd_kart_agac(a):
    sd = sd_gerekli()
    _, ajan_tipi = _kim(a)
    if ajan_tipi not in ("ana", "bilinmiyor"):
        hata("kart çalışma ağacını yalnız ana ajan açar.", 3)
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if L.kart_durumu_hesapla(k) in ("teslim", "iptal"):
            hata(f"kapalı karta çalışma ağacı açılmaz ({k['durum']}).")
        try:
            ca, yeni = L.kart_agaci_ac(L.proje_dizini(), k, a.taban)
        except ValueError as e:
            hata(str(e))
        k["yazma_alani_ilk"] = list(k.get("yazma_alani") or [])
        k["yazma_alani"] = yeni
        k["calisma_agaci"] = ca
        k["girdi"] = L.CALISMA_AGACI_ONEKI + ca["yol"] + "\n" + _girdi_agacsiz(k.get("girdi"))
        k["gecmis"].append({"zaman": L.simdi(), "olay": "calisma-agaci", "yol": ca["yol"], "dal": ca["dal"], "taban": ca["taban"]})
        L.kart_yaz(sd, k)
    print(ca["yol"])


def _iptal_agac_temizle(k: dict) -> list[str]:
    """İptal edilen kartın çalışma ağacını kaldırır (force yok). Kirli ağaçta kayıt ve ağaç kalır; uyarı döner."""
    ca = k.get("calisma_agaci") or {}
    if not (ca.get("depo") and ca.get("yol")):
        return []
    yol = ca["yol"]
    if os.path.isdir(yol):
        r = L.git(["status", "--porcelain", "--untracked-files=all"], yol)
        if r.returncode == 0 and r.stdout.strip():
            return [f"{k['id']} iptal edildi ama çalışma ağacı kirli, kaldırılmadı ve kayıt korundu ({yol}); "
                    "commitle/temizle, sonra `orkestra kart agac-temizle --uygula`."]
    uyarilar = L.agac_kaldir(ca["depo"], yol, ca.get("dal"))
    if os.path.isdir(yol):  # kaldırılamadı: kayıt korunur
        return uyarilar
    k["calisma_agaci_kaldirildi"] = k.pop("calisma_agaci")
    if "yazma_alani_ilk" in k:
        k["yazma_alani"] = k.pop("yazma_alani_ilk")
    k["girdi"] = _girdi_agacsiz(k.get("girdi"))
    k["gecmis"].append({"zaman": L.simdi(), "olay": "calisma-agaci-kaldirildi", "yol": yol})
    return uyarilar


def cmd_kart_agac_temizle(a):
    sd = sd_gerekli()
    if a.uygula:
        _, ajan_tipi = _kim(a)
        if ajan_tipi not in ("ana", "bilinmiyor"):
            hata("çalışma ağaçlarını yalnız ana ajan temizler.", 3)
    ks = L.kartlar(sd)
    depolar = _agac_temizle_depolari(ks)
    if not depolar:
        print("taranacak git deposu yok (proje git deposu değil, kartlarda depo bilgisi de yok); temizlenecek çalışma ağacı yok.")
        return
    bulundu = False
    for depo in depolar:
        if a.uygula:
            L.git(["worktree", "prune"], depo)  # klasörü elle silinmiş kayıtlar
        s = L.agac_temizle_siniflandir(depo, ks)
        if not s["aday"] and not s["kalip_disi"] and not s["oturum"]:
            continue
        bulundu = True
        if len(depolar) > 1:
            print(f"Depo: {depo}")
        baslik = "kaldırılanlar" if a.uygula else "adaylar (kuru koşu; kaldırmak için --uygula)"
        print(f"Biten ya da kartsız ağaçlar — {baslik}:" if s["aday"] else "Biten ya da kartsız ağaç yok.")
        for w in s["aday"]:
            if not a.uygula:
                print(f"  {w['yol']}  [{w['neden']}]")
                continue
            r = L.git(["status", "--porcelain", "--untracked-files=all"], w["yol"]) if os.path.isdir(w["yol"]) else None
            if r is not None and (r.returncode != 0 or r.stdout.strip()):
                print(f"  atlandı (kirli): {w['yol']}  [{w['neden']}]")
                continue
            u = L.agac_kaldir(depo, w["yol"], w["dal"])
            if os.path.isdir(w["yol"]):
                print(f"  atlandı: {w['yol']} — {'; '.join(u)}")
                continue
            print(f"  kaldırıldı: {w['yol']}  [{w['neden']}]")
            for x in u:
                print(f"    uyarı: {x}")
        for w in s["oturum"]:
            n = w.get("devralinmamis") or 0
            ek = (f" — ana klasörde olmayan {n} kayıt var; silmeden önce `orkestra durum devral --kaynak "
                  f"{w['yol']}/.claude/orkestra --uygula`") if n else ""
            print(f"  oturum ağacı (Claude yönetir, dokunulmadı): {w['yol']}{ek}")
        for w in s["kalip_disi"]:
            print(f"  kalıp dışı (dokunulmadı): {w['yol']}")
    if not bulundu:
        print("temizlenecek kart çalışma ağacı yok.")


def _agac_temizle_depolari(ks: list[dict]) -> list[str]:
    """Taranacak git kökleri: proje deposu (git ise) + kartlardaki calisma_agaci / _birlesik / _kaldirildi depo değerleri. Benzersiz."""
    adaylar = [L.proje_dizini()]
    for k in ks:
        for alan in ("calisma_agaci", "calisma_agaci_birlesik", "calisma_agaci_kaldirildi"):
            d = (k.get(alan) or {}).get("depo")
            if d and os.path.isdir(d):
                adaylar.append(d)
    out, gorulen = [], set()
    for d in adaylar:
        kok = L.git_koku(d)
        if not kok:
            continue
        anahtar = os.path.normcase(os.path.abspath(kok)).replace("\\", "/").rstrip("/")
        if anahtar not in gorulen:
            gorulen.add(anahtar)
            out.append(kok)
    return out


def _birlestir(sd, k) -> tuple[bool, str]:
    """Kartın çalışma ağacını birleştirir ve kartı günceller (yazmaz). Çatışmada ya da kilit kapısı ihlalinde kart
    beklemede, dosyalar not edilir; worktree korunur. Kilit kapısı bütün kartların test kilitlerine bakar."""
    s = L.kart_agaci_birlestir(k, proje=L.proje_dizini(), ks=L.kartlar(sd))
    if s["sonuc"] == "tamam":
        ca = k.pop("calisma_agaci")
        ca.update(birlesme=L.simdi(), commit=s.get("commit"))
        k["calisma_agaci_birlesik"] = ca
        if "yazma_alani_ilk" in k:
            k["yazma_alani"] = k.pop("yazma_alani_ilk")
        k["girdi"] = _girdi_agacsiz(k.get("girdi"))
        k.pop("birlestirme_catismasi", None)
        k.pop("birlestirme_kilidi", None)
        k["gecmis"].append({"zaman": L.simdi(), "olay": "birlestirildi", "commit": s.get("commit"), "not": s["mesaj"][:500]})
        return True, s["mesaj"]
    if s["sonuc"] in ("catisma", "kilit"):
        k["durum"] = "beklemede"
        k["beklemede_sira"] = L.sonraki_sira(k)
        if s["sonuc"] == "catisma":
            k["birlestirme_catismasi"] = s["dosyalar"]
            not_ = "birleştirme çatışması (otomatik çözülmedi): " + ", ".join(s["dosyalar"])
            ek = " — kart beklemede; çatışmayı elle çöz, sonra yeniden birleştir"
        else:
            k["birlestirme_kilidi"] = s["dosyalar"]
            not_ = "birleştirme kilit kapısı: " + s["mesaj"]
            ek = " — kart beklemede"
        k["gecmis"].append({"zaman": L.simdi(), "olay": "beklemede", "ajan": "orkestra", "not": not_[:500]})
        return False, s["mesaj"] + ek
    k["gecmis"].append({"zaman": L.simdi(), "olay": "birlestirme-ret", "not": s["mesaj"][:500]})
    return False, s["mesaj"]


def cmd_kart_birlestir(a):
    sd = sd_gerekli()
    _, ajan_tipi = _kim(a)
    if ajan_tipi not in ("ana", "bilinmiyor"):
        hata("kart dalını yalnız ana ajan birleştirir.", 3)
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if not (k.get("calisma_agaci") or {}).get("yol"):
            hata(f"{a.gid} kartının çalışma ağacı yok (`orkestra kart agac {a.gid}`).")
        ok, mesaj = _birlestir(sd, k)
        L.kart_yaz(sd, k)
    if not ok:
        hata(mesaj, 4)
    print(mesaj)


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    kart = alt.add_parser("kart").add_subparsers(dest="alt", required=True)
    y = kart.add_parser("yeni")
    y.add_argument("--baslik", required=True)
    y.add_argument("--basamak", default=None, help="verilmezse görev türü kataloğundan türer (yoksa T2)")
    y.add_argument("--basamak-neden", dest="basamak_neden", help="T3/T4 için gerekçe (golge kapı)")
    y.add_argument("--sinif")
    y.add_argument("--girdi")
    y.add_argument("--soru", help="zorunlu: kartın cevaplayacağı tek soru (tek cümle)")
    y.add_argument("--genislet-onay", dest="genislet_onay", action="store_true",
                   help="analiz kartında geniş tarama uyarısını kullanıcı onayıyla kaldırır")
    y.add_argument("--kabul", action="append", default=[],
                   help='tekrarlanır: "<ne doğrulanır>; kontrol: <komut | dosya:satır | sayı>" (ölçüsüz ifade reddedilir)')
    y.add_argument("--yazma", action="append", default=[])
    y.add_argument("--bagimli", action="append", default=[])
    y.add_argument("--test-komutu", dest="test_komutu", help="kod kartında zorunlu: proje kökünde kabukla koşulan test komutu")
    y.add_argument("--test-alani", dest="test_alani", action="append", default=[],
                   help="kod kartında zorunlu (tekrarlanabilir): test dosyası glob'u, test köküne göre")
    y.add_argument("--test-koku", dest="test_koku",
                   help="kod kartında isteğe bağlı: test kökü (var olan mutlak dizin; yoksa proje kökü)")
    y.add_argument("--tdd", action="store_true",
                   help="kod kartında test-önce akışı (test yazarı + kırmızı kapı); yalnız riskli kartta")
    ot = y.add_mutually_exclusive_group()
    ot.add_argument("--oto-teslim", dest="oto_teslim", action="store_const", const=True, default=None,
                    help="denetçi onayında kart kendiliğinden teslim olur (varsayılan: kod kartında açık)")
    ot.add_argument("--elle-teslim", dest="oto_teslim", action="store_const", const=False,
                    help="onaydan sonra teslimi ana ajan yapar (varsayılan: kod dışı kartta)")
    y.add_argument("--risk", help="dusuk|orta|yuksek (isteğe bağlı; ölçüm kaydı)")
    y.add_argument("--effort", help="low|medium|high|xhigh (isteğe bağlı; kartın çalışma eforu kaydı)")
    y.add_argument("--madde", help="işin todo.md'sinde bu kartın bitireceği açık maddenin metin parçası; teslimde otomatik [x]")
    y.add_argument("--butce-usd", dest="butce_usd", help="isteğe bağlı bütçe (USD); yalnız kayıt")
    y.add_argument("--butce-token", dest="butce_token", help="isteğe bağlı bütçe (token); yalnız kayıt")
    y.add_argument("--is", dest="is_id", help="kartı bu işe bağla (I-NNN); verilmezse oturumun bağlı işi")
    y.set_defaults(f=cmd_kart_yeni)
    ty = kart.add_parser("test-ayar", help="kod kartının test ayarları (yalnız ana ajan; kilitliyken yalnız test_koku)")
    ty.add_argument("gid")
    ty.add_argument("--test-koku", dest="test_koku", help="mutlak dizin; boş değer kaldırır (kök yeniden proje)")
    ty.add_argument("--test-komutu", dest="test_komutu")
    ty.add_argument("--test-alani", dest="test_alani", action="append", default=[])
    ty.set_defaults(f=cmd_kart_test_ayar)
    t = kart.add_parser("toplu")
    t.add_argument("json_yol", nargs="?")
    t.add_argument("--json-dosya")
    t.set_defaults(f=cmd_kart_toplu)
    tk = kart.add_parser("test-kos")
    tk.add_argument("gid")
    tk.add_argument("--asama", required=True, choices=["kirmizi", "yesil"])
    tk.add_argument("--zaman-asimi", dest="zaman_asimi", type=float, default=600)
    tk.add_argument("--eski-surumde", dest="eski_surumde", action="store_true",
                    help="yalnız kırmızı: kod önceden yazılmışsa testi eski sürümde (varsayılan HEAD) geçici worktree'de koştur; çalışma ağacı değişmez")
    tk.add_argument("--surum-ref", dest="surum_ref", help="--eski-surumde için git referansı (varsayılan HEAD)")
    tk.set_defaults(f=cmd_kart_test_kos)
    ka = kart.add_parser("test-kilit-ac")
    ka.add_argument("gid")
    ka.add_argument("--neden", required=True)
    ka.set_defaults(f=cmd_kart_test_kilit_ac)
    g = kart.add_parser("goster")
    g.add_argument("gid")
    g.add_argument("--json", action="store_true", help="JSON çıktı (varsayılan zaten JSON; plan_modeli ve effort dahil)")
    g.set_defaults(f=cmd_kart_goster)
    li = kart.add_parser("liste")
    li.add_argument("--hepsi", action="store_true")
    li.add_argument("--durum", help="virgülle ayrılmış durum süzgeci (ör. beklemede,reddedildi); hepsi bayrağını geçersiz kılar")
    li.add_argument("--json", action="store_true")
    li.set_defaults(f=cmd_kart_liste)
    du = kart.add_parser("durum")
    du.add_argument("gid")
    du.add_argument("durum", choices=["isleniyor", "is-bitti", "beklemede", "iptal", "planlandi"])
    du.add_argument("--ozet")
    du.add_argument("--surec", help="is-bitti: süreç adı (verilmezse ajan tipinden: isci -> is)")
    du.add_argument("--cikti", action="append", default=[])
    du.add_argument("--kanit", action="append", default=[],
                    help='is-bitti: kabul kriteri kanıtı, tekrarlanır: --kanit "K1: <dosya:satır | komut çıktısı | sayı>"')
    du.add_argument("--teknik", help="işçi is-bitti: teknik not JSON dosyası yolu "
                    "(yaklasim, neden_bu_yol, alternatifler, entegrasyon, riskler)")
    du.add_argument("--not", dest="not_")
    du.set_defaults(f=cmd_kart_durum)
    mv = kart.add_parser("mevcut", help="kod kartı: mevcut kodu anladığını kanıtlayan not (kod yazmadan önce)")
    mv.add_argument("gid")
    mv.add_argument("--dosya", required=True, help="not JSON dosyası (okunan, yetenekler, karar, neden, etkilenenler)")
    mv.set_defaults(f=cmd_kart_mevcut)
    de = kart.add_parser("denetim", formatter_class=argparse.RawTextHelpFormatter)
    de.add_argument("gid")
    de.add_argument("--karar", required=True, choices=["onay", "ret"])
    de.add_argument("--gerekce", required=True)
    de.add_argument("--talimat")
    de.add_argument("--duzeltmeler-dosya", dest="duzeltmeler_dosya",
                    help="yalnız onayda: denetçinin Edit ile yaptığı mekanik düzeltmeler (JSON liste: dosya, "
                         "tur bicim|sayi, once, sonra, kanit_komutu); A9 kapısı doğrular (ADR-0083)")
    de.add_argument("--neden", metavar="KOD",
                    help=_neden_yardim())
    de.set_defaults(f=cmd_kart_denetim)
    yu = kart.add_parser("yukselt")
    yu.add_argument("gid")
    yu.add_argument("--basamak", required=True)
    yu.add_argument("--neden", required=True)
    yu.set_defaults(f=cmd_kart_yukselt)
    bu = kart.add_parser("butce", help="kart bütçesi: göster; --usd ile tavanı ayarla (yalnız ana ajan)")
    bu.add_argument("gid")
    bu.add_argument("--usd", type=float)
    bu.set_defaults(f=cmd_kart_butce)
    te = kart.add_parser("teslim")
    te.add_argument("gid")
    te.add_argument("--ozet")
    te.set_defaults(f=cmd_kart_teslim)
    tt = kart.add_parser("teslim-toplu", help="onaylı kartları tek çağrıda teslim et")
    tt.add_argument("--json-dosya", required=True, help='[{"id":"G-1","ozet":"..."}, ...]')
    tt.set_defaults(f=cmd_kart_teslim_toplu)
    tb = kart.add_parser("teslim-bekleyen", help="onaylı ama teslim edilmemiş oto-teslim kartlarını topla")
    tb.set_defaults(f=cmd_kart_teslim_bekleyen)
    ag = kart.add_parser("agac", help="kart başına git çalışma ağacı aç")
    ag.add_argument("gid")
    ag.add_argument("--taban", default="HEAD", help="worktree'nin açılacağı commit (varsayılan: deponun HEAD'i)")
    ag.set_defaults(f=cmd_kart_agac)
    at = kart.add_parser("agac-temizle", help="biten/kartsız kart çalışma ağaçlarını listele ya da kaldır")
    at.add_argument("--uygula", action="store_true", help="kuru koşu yerine kaldır (kirli ağaç atlanır, force yok)")
    at.set_defaults(f=cmd_kart_agac_temizle)
    bi = kart.add_parser("birlestir", help="kart dalını --no-ff birleştir ve worktree'yi temizle")
    bi.add_argument("gid")
    bi.set_defaults(f=cmd_kart_birlestir)
