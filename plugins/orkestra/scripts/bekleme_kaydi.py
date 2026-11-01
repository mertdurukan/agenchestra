"""Bekleme kaydı (ADR-0146): ajan bir şeyi beklerken (kaynak kirası kuyruğu, arka plan görevi, CI koşusu, denetçi) boşa durmaz.

Bekleme noktası tek bir kayıt yazar: ne bekleniyor, hangi olayla biter, tahmini süre. Kayıt açıkken hook, işin todo'sundaki
BEKLEYENDEN BAĞIMSIZ açık maddeleri (plandaki `Önce:` ve `Yazma alanı:` alanlarından, `paralellik.maddeler`) ajanın önüne koyar
ve araç çağrılarını "bekleme sırasında yapılan iş" diye sayar. Kapanışta `gunluk.jsonl`'a `bekleme_kapat` düşer
(`bekleme_s`, `bos_s`, `yapilan`). Kayıtsız `sleep` / `Start-Sleep` / `gh run watch` komutu `bekleme_kaydi` kapısına takılır
(P-028: önce gölge; ihlal geçişi ≥14 gün ve ≥30 olay ölçümünden sonra ayrı ADR ile).

Model çağrılmaz. Ayar `ayarlar/bekleme_kaydi.json` (eklenti varsayılanı) ve durum klasöründeki `bekleme_kaydi.json` (anahtar
bazında ezer). Kapatma: ORKESTRA_BEKLEME_KAYDI=0. Kayıt dosyası durum klasöründe `bekleme.json`; sır değeri taşımaz.
"""
from __future__ import annotations

import json
import os
import re
import time

import ork_lib as L

KAPI = "bekleme_kaydi"
_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", KAPI + ".json")
_DOSYA = "bekleme.json"
_ADIM_UST = 500  # kayıt başına saklanan araç çağrısı zamanı sayısı


def _json_oku(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def ayar_oku(cwd: str | None = None) -> dict:
    ayar = _json_oku(VARSAYILAN_YOL) or {}
    sd = None
    if cwd:
        try:
            sd = L.durum_dizini(cwd)
        except Exception:
            sd = None
    if sd:
        proje = _json_oku(os.path.join(sd, KAPI + ".json"))
        if proje:
            ayar.update(proje)
    return ayar


def acik_mi() -> bool:
    return os.environ.get("ORKESTRA_BEKLEME_KAYDI") != "0"


# --- kayıt dosyası -------------------------------------------------------------------------------------------------

def _yol(sd: str) -> str:
    return os.path.join(sd, _DOSYA)


def _oku(sd: str) -> list[dict]:
    try:
        with open(_yol(sd), encoding="utf-8") as f:
            d = json.load(f)
        return [x for x in d.get("kayitlar", []) if isinstance(x, dict)] if isinstance(d, dict) else []
    except Exception:
        return []


def _yaz(sd: str, kayitlar: list[dict]) -> None:
    tmp = _yol(sd) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"kayitlar": kayitlar}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _yol(sd))


def _olu_mu(k: dict, simdi: float, ust_s: float) -> bool:
    """Tahmini süre bilinse bile kapanmamış kayıt `ust_s` sonra ölü sayılır (oturum çökmüş olabilir)."""
    tahmin = float(k.get("tahmin_s") or 0)
    return simdi - float(k.get("acilis") or 0) > max(ust_s, tahmin * 3)


def _gunluk(sd: str, kayit: dict) -> None:
    try:
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), kayit)
    except Exception:
        pass


def liste(sd: str, ayar: dict | None = None) -> list[dict]:
    """Açık (ölü olmayan) kayıtlar."""
    ust = float((ayar or ayar_oku()).get("sona_erme_s") or 7200)
    simdi = time.time()
    return [k for k in _oku(sd) if not _olu_mu(k, simdi, ust)]


def ac(sd: str, ne: str, olay: str, tahmin_s: float | None = None, kaynak: str = "elle", is_id: str = "",
       p: int | None = None, oturum: str = "") -> dict:
    """Bekleme kaydı açar; aynı (kaynak, ne) zaten açıksa onu döndürür (tekrar çağrılan köprüler kayıt çoğaltmasın)."""
    ayar = ayar_oku()
    ust = float(ayar.get("sona_erme_s") or 7200)
    simdi = time.time()
    with L.kilit(_yol(sd)):
        kayitlar = [k for k in _oku(sd) if not _olu_mu(k, simdi, ust)]
        for k in kayitlar:
            if k.get("kaynak") == kaynak and k.get("ne") == ne[:160]:
                return k
        k = {"id": "B" + format(int(simdi * 1000) % 10**9, "09d"), "ne": ne[:160], "olay": olay[:160], "tahmin_s": tahmin_s,
             "kaynak": kaynak, "is": is_id, "p": p, "oturum": oturum, "acilis": simdi, "adimlar": [], "bildirildi": False}
        kayitlar.append(k)
        _yaz(sd, kayitlar)
    _gunluk(sd, {"zaman": L.simdi(), "oturum": oturum, "tur": "bekleme_ac", "bekleme": k["id"], "kaynak": kaynak,
                 "ne": k["ne"], "olay": k["olay"], "tahmin_s": tahmin_s, "is": is_id})
    return k


def bos_sure(acilis: float, adimlar: list[float], kapanis: float, esik_s: float) -> float:
    """Ajanın gerçekten durduğu süre: ardışık araç çağrıları arasındaki, `esik_s`'yi aşan aralıkların toplamı.
    Aralıklar açılıştan ilk çağrıya ve son çağrıdan kapanışa kadar da sayılır; kısa aralıklar çalışma sayılır."""
    noktalar = [acilis] + sorted(a for a in adimlar if acilis <= a <= kapanis) + [kapanis]
    return round(sum(b - a for a, b in zip(noktalar, noktalar[1:]) if b - a > esik_s), 1)


def kapat(sd: str, bid: str, yapilan: int | None = None, oturum: str = "", neden: str = "bitti") -> dict | None:
    """Kaydı kapatır ve `bekleme_kapat` olayını yazar; kayıt yoksa None. `yapilan` verilmezse kayıtlı araç çağrısı sayısı."""
    ayar = ayar_oku()
    simdi = time.time()
    with L.kilit(_yol(sd)):
        kayitlar = _oku(sd)
        k = next((x for x in kayitlar if x.get("id") == bid), None)
        if not k:
            return None
        _yaz(sd, [x for x in kayitlar if x.get("id") != bid])
    adimlar = [float(a) for a in k.get("adimlar") or []]
    esik = float(ayar.get("bosluk_esik_s") or 90)
    sonuc = {"zaman": L.simdi(), "oturum": oturum or k.get("oturum"), "tur": "bekleme_kapat", "bekleme": bid,
             "kaynak": k.get("kaynak"), "ne": k.get("ne"), "neden": neden, "is": k.get("is"),
             "bekleme_s": round(simdi - float(k.get("acilis") or simdi), 1),
             "bos_s": bos_sure(float(k.get("acilis") or simdi), adimlar, simdi, esik),
             "yapilan": len(adimlar) if yapilan is None else int(yapilan)}
    _gunluk(sd, sonuc)
    return sonuc


def adim(sd: str, oturum: str = "") -> None:
    """Açık kayıtlara bir araç çağrısı zamanı ekler (bekleme sırasında yapılan iş). Hata sessiz."""
    try:
        simdi = time.time()
        if not os.path.exists(_yol(sd)):
            return
        with L.kilit(_yol(sd)):
            kayitlar = _oku(sd)
            if not kayitlar:
                return
            for k in kayitlar:
                if not oturum or not k.get("oturum") or k.get("oturum") == oturum:
                    a = list(k.get("adimlar") or [])
                    a.append(simdi)
                    k["adimlar"] = a[-_ADIM_UST:]
            _yaz(sd, kayitlar)
    except Exception:
        pass


def bildirildi_isaretle(sd: str, bid: str) -> None:
    with L.kilit(_yol(sd)):
        kayitlar = _oku(sd)
        for k in kayitlar:
            if k.get("id") == bid:
                k["bildirildi"] = True
        _yaz(sd, kayitlar)


def rapor(sd: str) -> dict:
    """gunluk.jsonl'daki bekleme olaylarından ölçüm: olay sayısı, bağımsız iş yapılan bekleme oranı, toplam bekleme ve boş süre,
    kayıtsız uyarı sayısı (ihlal geçişi için ≥14 gün ve ≥30 olay; ADR-0146)."""
    kapat, golge = [], 0
    try:
        with open(os.path.join(sd, "gunluk.jsonl"), encoding="utf-8") as f:
            for s in f:
                if "bekleme_kapat" not in s and KAPI not in s:
                    continue
                try:
                    o = json.loads(s)
                except ValueError:
                    continue
                if o.get("tur") == "bekleme_kapat":
                    kapat.append(o)
                elif o.get("tur") == "kapi_golge" and o.get("kapi") == KAPI:
                    golge += 1
    except OSError:
        pass
    n = len(kapat)
    return {"bekleme_olay": n, "bagimsiz_is_yapilan": sum(1 for o in kapat if (o.get("yapilan") or 0) > 0),
            "oran": round(sum(1 for o in kapat if (o.get("yapilan") or 0) > 0) / n, 2) if n else None,
            "bekleme_s": round(sum(float(o.get("bekleme_s") or 0) for o in kapat), 1),
            "bos_s": round(sum(float(o.get("bos_s") or 0) for o in kapat), 1), "kayitsiz_uyari": golge}


# --- bağımsız iş ---------------------------------------------------------------------------------------------------

_TODO_ACIK = re.compile(r"^\s*[-*]\s*\[ \]\s*P(\d+)\b\s*(.*)$")


def _bagimli_mi(md: dict, n: int, hedef: int, gorulen: set | None = None) -> bool:
    """n maddesi hedef maddeye (dolaylı dahil) `Önce:` ile bağlı mı."""
    gorulen = gorulen if gorulen is not None else set()
    if n in gorulen or n not in md:
        return False
    gorulen.add(n)
    for (b, _tur, _g) in md[n]["once"]:
        if b == hedef or _bagimli_mi(md, b, hedef, gorulen):
            return True
    return False


def bagimsiz_isler(is_klasoru: str, bekleyen_p: int | None = None) -> list[str]:
    """İşin todo.md'sindeki açık `P<n>` satırlarından, bekleyen maddeden bağımsız olanlar (`- [ ] P<n> başlık`).

    Bağımsız: kendisi bekleyen madde değil, bekleyen maddeye `Önce:` ile (dolaylı da) bağlı değil ve yazma alanı
    bekleyen maddenin yazma alanıyla kesişmiyor. `bekleyen_p` yoksa bağımlılık/kesişim sınanmaz (tüm açık P maddeleri).
    Bir maddenin kendi `Önce:` bağımlılığı henüz açıksa (önceki madde bitmemiş) o madde de elenir."""
    try:
        import paralellik
        with open(os.path.join(is_klasoru, "todo.md"), encoding="utf-8") as f:
            satirlar = f.read().splitlines()
        try:
            with open(os.path.join(is_klasoru, "plan.md"), encoding="utf-8") as f:
                md = paralellik.maddeler(f.read())
        except OSError:
            md = {}
    except Exception:
        return []
    acik = {}
    for s in satirlar:
        m = _TODO_ACIK.match(s)
        if m:
            acik[int(m.group(1))] = s.strip()
    sonuc = []
    for n, satir in sorted(acik.items()):
        if n == bekleyen_p:
            continue
        if n in md:
            if any(b in acik for (b, _t, _g) in md[n]["once"]):
                continue  # önceki madde açık: bu madde henüz başlayamaz
            if bekleyen_p is not None:
                if _bagimli_mi(md, n, bekleyen_p):
                    continue
                if bekleyen_p in md and paralellik.alan_kesisir(md[n]["yazma"], md[bekleyen_p]["yazma"]):
                    continue
        sonuc.append(satir)
    return sonuc


def baglam_satiri(kayit: dict, isler: list[str]) -> str:
    """Ajana giden tek bildirim: ne bekleniyor, bitince ne olur, bağımsız iş listesi."""
    tahmin = f", tahmini {int(kayit['tahmin_s'])} sn" if kayit.get("tahmin_s") else ""
    s = (f"orkestra (bekleme, {kayit['id']}): '{kayit['ne']}' bekleniyor (biter: {kayit['olay']}{tahmin}). "
         "Boşa durma: bağımsız işi şimdi yap, bitince beklenene dön.")
    if isler:
        s += " Bağımsız açık maddeler: " + " | ".join(i[:90] for i in isler[:5]) + "."
    else:
        s += " Todo'da bağımsız açık madde yok; bekleneni arka planda tut, bitince bildirim gelir."
    s += f" Kapat: orkestra bekleme kapat {kayit['id']}"
    return s


# --- kayıtsız bekleme kapısı ---------------------------------------------------------------------------------------

_TIRNAK = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2(?=\s|$)", re.S)


def _veri_disi(komut: str) -> str:
    return _TIRNAK.sub('""', _HEREDOC.sub(" ", komut))


def kayitsiz_parca(komut, ayar: dict) -> str | None:
    """Bekleme komutu içeriyorsa ilk eşleşen parça (ilk 80 karakter); yoksa None. Tırnak içi metin veridir."""
    if not isinstance(komut, str) or not komut.strip():
        return None
    temiz = _veri_disi(komut)
    for kalip in ayar.get("komut_kaliplari") or []:
        try:
            m = re.search(kalip, temiz)
        except re.error:
            continue
        if not m:
            continue
        sn = m.groupdict().get("sn")
        if sn is not None:
            try:
                if float(sn) < float(ayar.get("sleep_min_s") or 5):
                    continue
            except ValueError:
                pass
        return " ".join(temiz[m.start():m.start() + 80].split())
    return None


def karar(komut, cwd: str | None = None, sd: str | None = None) -> tuple[str, str, str] | None:
    """None (geç) ya da (mod, mesaj, parça). Açık bekleme kaydı varken geçer. Kayıt ve ret çağıranındır."""
    if not acik_mi():
        return None
    ayar = ayar_oku(cwd)
    parca = kayitsiz_parca(komut, ayar)
    if not parca:
        return None
    sd = sd or (L.durum_dizini(cwd) if cwd else None)
    if sd and liste(sd, ayar):
        return None
    import kapi_mod
    m = kapi_mod.mod(KAPI, cwd)
    return m, str(ayar.get("ret_metni" if m == "ihlal" else "uyari_metni", "")), parca
