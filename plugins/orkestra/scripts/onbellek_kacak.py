"""Önbellek kaçakları: ana ajan çağrılarında önceki bağlamın okunmayıp yeniden yazıldığı olayları sınıflar (model çağırmaz).

Kaçak: önceki çağrının bağlamının yarısından azı okunup 40 bin tokenden fazlası yazılan çağrı.
Sınıflar: katman_5dk (yazma 5 dakikalık katmanda), model (model değişti), bosluk (önceki çağrıdan 60 dakika ve üstü),
sikistirma (bağlam küçüldü), diger.

Kaynak: ~/.claude/projects/<proje>/*.jsonl ana zincir çağrıları. Dosya başına sıkıştırılmış çağrı listesi
`<sd>/onbellek_kacak.json` içinde önbelleklenir (boyut + değişme anı değişmediyse dosya yeniden okunmaz).
"""
from __future__ import annotations

import datetime
import glob
import json
import os

import ork_lib as L

ESIK_YAZMA = 40_000
ESIK_OKUMA_ORANI = 0.5
BOSLUK_DK = 60
SINIFLAR = ("katman_5dk", "model", "bosluk", "sikistirma", "diger")
_ONBELLEK_ADI = "onbellek_kacak.json"
_SURUM = 1


def _damga(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def _dosya_cagrilari(yol: str) -> list[list]:
    """Ana zincir (isSidechain değil) çağrıları: [zaman, model, girdi, okuma, yazma, yazma_5dk]; mesaj kimliğiyle tekilleştirilir."""
    sirali: dict[str, list] = {}
    with open(yol, "rb") as f:
        for ham in f:
            if b'"usage"' not in ham or b'"assistant"' not in ham:
                continue
            try:
                o = json.loads(ham)
            except ValueError:
                continue
            if o.get("type") != "assistant" or o.get("isSidechain"):
                continue
            m = o.get("message") or {}
            u = m.get("usage")
            model = m.get("model") or ""
            if not u or model == "<synthetic>" or not o.get("timestamp"):
                continue
            cc = u.get("cache_creation") or {}
            yazma = u.get("cache_creation_input_tokens", 0) or 0
            kayit = [o["timestamp"], model, u.get("input_tokens", 0) or 0, u.get("cache_read_input_tokens", 0) or 0,
                     yazma, cc.get("ephemeral_5m_input_tokens") or 0]
            kimlik = m.get("id") or o.get("uuid") or str(len(sirali))
            if kimlik in sirali:   # akış satırları: istek anı ilk satırın zamanı, kullanım son satırın değeri
                kayit[0] = sirali[kimlik][0]
            sirali[kimlik] = kayit
    return list(sirali.values())


def _yukle(sd: str) -> dict:
    try:
        with open(os.path.join(sd, _ONBELLEK_ADI), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("surum") == _SURUM:
            return d
    except (OSError, ValueError):
        pass
    return {"surum": _SURUM, "dosyalar": {}}


def _kaydet(sd: str, d: dict) -> None:
    yol = os.path.join(sd, _ONBELLEK_ADI)
    gecici = yol + f".{os.getpid()}.tmp"
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(gecici, yol)
    except OSError:
        try:
            os.remove(gecici)
        except OSError:
            pass


def oturumlar(sd: str, proje: str | None = None) -> dict[str, list[list]]:
    """{oturum_kimligi: çağrılar}; değişmeyen dosyalar önbellekten gelir."""
    import belge_ara as BA
    proje = proje or BA.proje_kok(sd)
    d = _yukle(sd)
    eski, yeni, degisti = d["dosyalar"], {}, False
    for yol in glob.glob(os.path.join(L.proje_oturum_dizini(proje), "*.jsonl")):
        try:
            st = os.stat(yol)
        except OSError:
            continue
        ad = os.path.basename(yol)[:-6]
        imza = [st.st_size, int(st.st_mtime)]
        e = eski.get(ad)
        if e and e["imza"] == imza:
            yeni[ad] = e
            continue
        try:
            yeni[ad] = {"imza": imza, "cagrilar": _dosya_cagrilari(yol)}
        except OSError:
            continue
        degisti = True
    if degisti or set(yeni) != set(eski):
        _kaydet(sd, {"surum": _SURUM, "dosyalar": yeni})
    return {ad: v["cagrilar"] for ad, v in yeni.items()}


def sinifla(ts_oturumlar: dict[str, list[list]], tablo: dict | None = None) -> list[dict]:
    """Kaçak olayları. USD: yazılan tokenlar katman fiyatıyla (5 dk ve 1 saat ayrı)."""
    tablo = tablo or L.fiyat_tablosu()
    olaylar = []
    for oturum, cagrilar in ts_oturumlar.items():
        sirali = sorted(cagrilar, key=lambda c: c[0])
        for a, b in zip(sirali, sirali[1:]):
            onceki = a[2] + a[3] + a[4]
            yazma, okuma = b[4], b[3]
            if not (yazma > ESIK_YAZMA and okuma < ESIK_OKUMA_ORANI * onceki):
                continue
            gap = (_damga(b[0]) - _damga(a[0])).total_seconds() / 60
            if b[5] > 0:
                sinif = "katman_5dk"
            elif a[1] != b[1]:
                sinif = "model"
            elif gap >= BOSLUK_DK:
                sinif = "bosluk"
            elif okuma + yazma < 0.6 * onceki:
                sinif = "sikistirma"
            else:
                sinif = "diger"
            f = L.model_fiyati(b[1], tablo)
            usd = (b[5] * f["onbellek_yazma_5dk"] + (yazma - b[5]) * f["onbellek_yazma_1sa"]) / 1e6
            olaylar.append({"oturum": oturum, "zaman": b[0], "sinif": sinif, "bosluk_dk": round(gap, 1),
                            "onceki_baglam": onceki, "yazma": yazma, "okuma": okuma, "usd": round(usd, 4),
                            "model_once": a[1], "model": b[1]})
    return sorted(olaylar, key=lambda o: o["zaman"])


def ozet(sd: str, gun: float | None = None, simdi: datetime.datetime | None = None, proje: str | None = None,
         yalniz_defter: bool = False) -> dict:
    """{olay_sayisi, usd, siniflar:{sinif:{olay,usd}}, olaylar:[...], katman_5dk_son_24s}; gun verilirse takvim penceresi.

    yalniz_defter: yalnız maliyet defterinde kaydı olan oturumlar (ana ajan payı havuzuyla karşılaştırma için)."""
    simdi = simdi or datetime.datetime.now().astimezone()
    oturum = oturumlar(sd, proje)
    if yalniz_defter:
        kayitli = {r.get("oturum") for r in L.maliyet_kayitlari(sd)}
        oturum = {ad: v for ad, v in oturum.items() if ad in kayitli}
    olaylar = sinifla(oturum)
    if gun:
        esik = L.gun_baslangici(gun, simdi)
        olaylar = [o for o in olaylar if _damga(o["zaman"]) >= esik]
    siniflar = {s: {"olay": 0, "usd": 0.0} for s in SINIFLAR}
    for o in olaylar:
        siniflar[o["sinif"]]["olay"] += 1
        siniflar[o["sinif"]]["usd"] += o["usd"]
    for v in siniflar.values():
        v["usd"] = round(v["usd"], 2)
    return {"olay_sayisi": len(olaylar), "usd": round(sum(o["usd"] for o in olaylar), 2), "siniflar": siniflar,
            "olaylar": olaylar, "katman_5dk_son_24s": katman_5dk_sayisi(oturum, simdi)}


def katman_5dk_sayisi(ts_oturumlar: dict[str, list[list]], simdi: datetime.datetime, saat: float = 24) -> int:
    """Son `saat` saatte 5 dakikalık önbellek katmanına yazan ana ajan çağrısı sayısı."""
    esik = simdi - datetime.timedelta(hours=saat)
    return sum(1 for cagrilar in ts_oturumlar.values() for c in cagrilar if c[5] > 0 and esik <= _damga(c[0]) <= simdi)
