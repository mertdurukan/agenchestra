"""Göreve özgü ön bağlam (I-139 P9, bce F04/F16/F19/F21/F27/F35; ADR-0024).

Kullanıcı isteğinden çıpa çıkarır ve ajana "buraya bak" satırları verir. Saf Python, model çağırmaz, deterministiktir
(aynı istek ve aynı depo durumu → aynı çıktı), hata hook'u düşürmez. VARSAYILAN KAPALIDIR: ADR-0024 gereği
`orkestra isabet --on-baglam` ölçümü kabul edilebilir çıkmadan açılmaz.

Açma: `ORKESTRA_ON_BAGLAM=1` ya da `ayarlar/on_baglam.json` içinde `"acik": true`; `ORKESTRA_ON_BAGLAM=0` her zaman kapatır.

Çıpalar (her satır kaynağını ve nedenini taşır):
- istekte anılan ve diskte var olan yol (F21)
- istekte adı geçen kimlik servisi: yalnız servis ve anahtar adları, değer asla (F04)
- sözcük benzerliğiyle bulunan geçmiş iş, ADR ya da kural belgesi (F16) ve geçmiş işin belgesinde anılan dosyalar
- her yol için son `gun` gündeki git değişim sayısı: sık değişen yer risk işaretidir (F35)
"""
from __future__ import annotations

import json
import os
import re
import subprocess

import yol_denetimi as YD

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AYAR_YOLU = os.path.join(_KOK, "ayarlar", "on_baglam.json")
VARSAYILAN = {"acik": False, "en_kisa_istek": 20, "azami_karakter": 1200, "gun": 90, "benzer_belge": 3,
              "benzer_esik": 0.15, "azami_yol": 6}
_ISTEKTE_YOL = re.compile(r"[\w.\-~:/\\]+")


def ayar(sd: str | None = None) -> dict:
    a = dict(VARSAYILAN)
    for yol in (AYAR_YOLU, os.path.join(sd, "on_baglam.json") if sd else None):
        if not yol:
            continue
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                a.update(d)
        except (OSError, ValueError):
            pass
    return a


def acik_mi(sd: str | None = None) -> bool:
    ortam = os.environ.get("ORKESTRA_ON_BAGLAM")
    if ortam == "0":
        return False
    if ortam == "1":
        return True
    return bool(ayar(sd).get("acik"))


def _git(kok: str, *args: str) -> str | None:
    """git çıktısı; git yoksa ya da komut hata verirse (ör. depo değil) None."""
    try:
        r = subprocess.run(["git", "-c", "safe.directory=*", "-C", kok, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def degisim_sayisi(kok: str, yol: str, gun: int) -> int | None:
    """Son `gun` günde yolu değiştiren commit sayısı; git yoksa ya da yol depo dışındaysa None."""
    goreli = os.path.relpath(yol, kok).replace("\\", "/")
    if goreli.startswith(".."):
        return None
    cikti = _git(kok, "log", f"--since={gun}.days", "--pretty=format:%h", "--", goreli)
    if cikti is None:
        return None
    return len([s for s in cikti.splitlines() if s.strip()])


def _cozumle(aday: str, kokler: list[str]) -> str | None:
    """Mutlak ya da köklere göreli aday diskte dosyaysa mutlak yol."""
    adaylar = [aday] if os.path.isabs(aday) else [os.path.join(k, aday) for k in kokler]
    for a in adaylar:
        if os.path.isfile(a):
            return os.path.abspath(a)
    return None


def istekte_anilan_yollar(istek: str, kokler: list[str]) -> list[str]:
    """İstemde geçen, diskte var olan dosya yolları (sıra: ilk anılış; tekrarsız)."""
    sonuc: list[str] = []
    for parca in _ISTEKTE_YOL.findall(istek):
        yol = YD.yol_adayi(parca.strip(".,;:()"))
        if not yol:
            continue
        c = _cozumle(yol, kokler)
        if c and c not in sonuc:
            sonuc.append(c)
    return sonuc


def anilan_kimlikler(istek: str) -> list[tuple[str, list[str]]]:
    """İstekte adı geçen kimlik servisleri: [(servis, anahtar adları)]; değer okunmaz. Kimlik klasörü yoksa boş."""
    try:
        import kimlik
        kayitlar = kimlik.liste()
    except Exception:
        return []
    kucuk = istek.lower()
    sonuc = []
    for _kapsam, servis, anahtarlar in kayitlar:
        if re.search(r"(?<![\w])" + re.escape(servis.lower()) + r"(?![\w])", kucuk) and servis not in [s for s, _ in sonuc]:
            sonuc.append((servis, list(anahtarlar)))
    return sonuc


def _is_no_bul(is_id: str) -> int:
    try:
        import is_kaydi
        return is_kaydi.is_no(is_id)
    except Exception:
        return 10 ** 9


def benzer_belgeler(istek: str, kokler: list[str], sd: str | None, a: dict, haric_klasor: str | None = None,
                    once_id: str | None = None) -> tuple[list[dict], list[dict]]:
    """(eşik üstü sonuçlar, aranan belgeler). Sözcük benzerliğiyle en yakın geçmiş belgeler (eşik altı atılır). haric_klasor ve once_id ölçüm sızıntısını önler:
    ölçülen işin kendi klasörü ve ondan sonra açılan işler aranmaz."""
    import belge_ara as BA
    belgeler = BA.belgeler(kokler[0], sd)
    if haric_klasor:
        goreli = os.path.relpath(haric_klasor, kokler[0]).replace("\\", "/") + "/"
        belgeler = [b for b in belgeler if not b["yol"].startswith(goreli)]
    if once_id:
        sinir = _is_no_bul(once_id)
        belgeler = [b for b in belgeler if not (b["tur"] == "is" and _is_no_bul(b["is_id"]) >= sinir)]
    return [r for r in BA.ara(belgeler, istek, int(a["benzer_belge"])) if r["skor"] >= float(a["benzer_esik"])], belgeler


def _belge_dosyalari(belge: dict, kokler: list[str]) -> list[str]:
    """Belgede backtick içinde anılan, diskte var olan dosyalar (yer tutucu ve 'yeni' satırlar atlanır)."""
    sonuc = []
    for k in YD.denetle_metin(belge["metin"], kokler):
        if k["var"]:
            c = _cozumle(k["yol"], kokler)
            if c and c not in sonuc:
                sonuc.append(c)
    return sonuc


def cipalar(istek: str, kokler: list[str], sd: str | None = None, haric_klasor: str | None = None,
            once_id: str | None = None) -> list[dict]:
    """Sıralı çıpa listesi: [{tur: yol|kimlik|belge, yol|ad, kaynak, neden}]. Yol çıpaları tekrarsızdır (ilk neden korunur)."""
    a = ayar(sd)
    sonuc: list[dict] = []
    for y in istekte_anilan_yollar(istek, kokler):
        sonuc.append({"tur": "yol", "yol": y, "kaynak": "istek", "neden": "istekte adı geçiyor"})
    for servis, anahtarlar in anilan_kimlikler(istek):
        sonuc.append({"tur": "kimlik", "ad": servis, "anahtarlar": anahtarlar, "kaynak": "kimlik klasörü",
                      "neden": "istekte servis adı geçiyor; değeri okuma, `orkestra kimlik calistir` kullan"})
    try:
        benzerler, belgeler = benzer_belgeler(istek, kokler, sd, a, haric_klasor, once_id)
    except Exception:
        benzerler, belgeler = [], []
    metin_by_yol = {b["yol"]: b for b in belgeler}
    gorulen_yol = {c["yol"] for c in sonuc if c["tur"] == "yol"}
    for r in benzerler:
        etiket = {"is": f"geçmiş iş {r['is_id']}", "adr": "ADR", "kural": "kural"}.get(r["tur"], r["tur"])
        sonuc.append({"tur": "belge", "yol": r["yol"], "kaynak": etiket, "neden": f"sözcük benzerliği {r['skor']:.2f}"})
        if r["tur"] == "is" and r["yol"] in metin_by_yol:
            for y in _belge_dosyalari(metin_by_yol[r["yol"]], kokler):
                if y not in gorulen_yol:
                    gorulen_yol.add(y)
                    sonuc.append({"tur": "yol", "yol": y, "kaynak": f"geçmiş iş {r['is_id']}",
                                  "neden": f"{r['yol']} belgesinde anılıyor"})
    return sonuc


def yollar(istek: str, kokler: list[str], sd: str | None = None, haric_klasor: str | None = None,
           once_id: str | None = None) -> list[str]:
    """Çıpalardan çıkan dosya yolları (belge çıpaları hariç) - `orkestra isabet --on-baglam` tahmin kümesi."""
    try:
        return [c["yol"] for c in cipalar(istek, kokler, sd, haric_klasor, once_id) if c["tur"] == "yol"]
    except Exception:
        return []


def _goreli(yol: str, kokler: list[str]) -> str:
    for k in kokler:
        g = os.path.relpath(yol, k)
        if not g.startswith(".."):
            return g.replace("\\", "/")
    return yol.replace("\\", "/")


def uret(istek: str, kokler: list[str], sd: str | None = None) -> str | None:
    """Hook bağlam metni; kapalıysa, istek kısaysa, `/` komutuysa ya da çıpa yoksa None. Hata hook'u düşürmez."""
    try:
        if not acik_mi(sd):
            return None
        a = ayar(sd)
        istek = (istek or "").strip()
        if len(istek) < int(a["en_kisa_istek"]) or istek.startswith("/"):
            return None
        satirlar, yol_sayisi = [], 0
        for c in cipalar(istek, kokler, sd):
            if c["tur"] == "kimlik":
                ek = f" ({', '.join(c['anahtarlar'])})" if c["anahtarlar"] else ""
                satirlar.append(f"- kimlik: {c['ad']}{ek} · kaynak: {c['kaynak']} · {c['neden']}")
            elif c["tur"] == "belge":
                satirlar.append(f"- belge: {c['yol']} · kaynak: {c['kaynak']} · {c['neden']}")
            else:
                if yol_sayisi >= int(a["azami_yol"]):
                    continue
                yol_sayisi += 1
                n = degisim_sayisi(kokler[0], c["yol"], int(a["gun"]))
                risk = "" if n is None else f" · son {a['gun']} günde {n} değişiklik"
                satirlar.append(f"- dosya: {_goreli(c['yol'], kokler)} · kaynak: {c['kaynak']} · {c['neden']}{risk}")
        if not satirlar:
            return None
        baslik = "Orkestra ön bağlam (deneme; ADR-0024): isteğe göre bakılabilecek yerler."
        metin = baslik
        for s in satirlar:
            if len(metin) + 1 + len(s) > int(a["azami_karakter"]):
                break
            metin += "\n" + s
        return metin if metin != baslik else None
    except Exception:
        return None
