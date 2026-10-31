#!/usr/bin/env python3
"""Orkestra T0 ön kontrol kapısı: LLM denetçisinden önce, model/ağ çağırmadan.

  on_kontrol.py taban <kart_id> [--proje DIZIN]
  on_kontrol.py kontrol <kart_id> [--ciktilar yol1,yol2] [--kaynak yol] [--proje DIZIN]

taban   : yazma_alani dosyalarının özetini (var, sha256, BOM, baskın satır sonu) ve kartta
          test_komutu varsa başarısız test kimliklerini <durum>/gorevler/<id>.onkontrol.json'a yazar.
kontrol : BOM/satır sonu değişimi, kapsam dışı çıktı, tabanda olmayan yeni başarısız test ve
          (kaynak verilmişse) çıktılarda eksik kalan sayı/kimlik/§ tokenları.
Çıktı: stdout'a tek JSON {gecti, ihlaller:[{tur,ayrinti}], onceden_dusen, sure_sn, uyarilar}.
Çıkış kodu: 0 geçti, 4 ihlal, 2 kullanım hatası.
"""
from __future__ import annotations

import argparse
import fnmatch
import glob
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import kapi_mod as KM  # noqa: E402

TEST_ZAMAN_ASIMI = 900.0
FAILED_RE = L.PYTEST_DUSEN_RE  # ortak ayrıştırıcı (ork_lib); geriye uyum için ad korunur

TUR_SATIR_SONU, TUR_BOM, TUR_KAPSAM, TUR_TEST, TUR_TOKEN = "satir-sonu", "bom", "kapsam", "yeni-test-hatasi", "eksik-token"


def _norm(p: str) -> str:
    return os.path.abspath(p).replace("\\", "/")


def _kok(proje: str, desen: str) -> str:
    d = desen.replace("\\", "/")
    return d if os.path.isabs(d) or re.match(r"^[A-Za-z]:/", d) else _norm(os.path.join(proje, d))


def dosya_ozeti(yol: str) -> dict:
    try:
        with open(yol, "rb") as f:
            veri = f.read()
    except OSError:
        return {"var": False}
    crlf = veri.count(b"\r\n")
    lf = veri.count(b"\n") - crlf
    satir = "yok" if crlf + lf == 0 else ("crlf" if crlf > lf else "lf")
    return {"var": True, "sha256": hashlib.sha256(veri).hexdigest(),
            "bom": veri.startswith(b"\xef\xbb\xbf"), "satir_sonu": satir}


def alan_dosyalari(proje: str, desenler: list[str]) -> list[str]:
    out = []
    for d in desenler or []:
        tam = _kok(proje, d)
        bulunan = glob.glob(tam, recursive=True) or [tam]
        for b in bulunan:
            if os.path.isfile(b) or not glob.has_magic(tam):
                n = _norm(b)
                if not os.path.isdir(b) and n not in out and "__pycache__" not in n:
                    out.append(n)
    return out


def yol_alanda_mi(proje: str, yol: str, desenler: list[str]) -> bool:
    y = _norm(yol if os.path.isabs(yol) else os.path.join(proje, yol))
    for d in desenler or []:
        t = _kok(proje, d).rstrip("/")
        if fnmatch.fnmatch(y, t) or y == t or y.startswith(t + "/") or fnmatch.fnmatch(y, t + "/**"):
            return True
    return False


def test_kos(komut: str, cwd: str, kart: dict | None = None) -> dict:
    """Kart verilirse geniş komut test_alani'ndaki test dosyalarına daralır (test_koku'lu kartta daralmaz: cwd farklı)."""
    if kart and not kart.get("test_koku"):
        komut, _ = L.test_komutu_daralt(komut, cwd, kart.get("test_alani") or [])
        if komut is None:
            return {"cikis": 0, "basarisiz": []}
    kod, cikti, _ = L.paralel_kos(komut, cwd, TEST_ZAMAN_ASIMI)
    return {"cikis": kod, "basarisiz": L.pytest_dusenler(cikti)}


# ---------------------------------------------------------------- token karşılaştırması

TOKEN_RES = [
    re.compile(r"§\s?\d+(?:\.\d+)*"),
    re.compile(r"\b[A-Z]{2,}-\d+\b"),
    re.compile(r"\bG\d+[a-z]\b"),
    re.compile(r"%\s?\d+(?:[.,]\d+)*|\b\d+(?:[.,]\d+)*\s?%"),
    re.compile(r"\b\d+(?:[.,]\d+)*\b"),
]


def tokenlar(metin: str) -> list[str]:
    bulunan, sirali = set(), []
    kalan = metin
    for r in TOKEN_RES:
        for m in r.finditer(kalan):
            t = re.sub(r"\s+", "", m.group(0))
            if t not in bulunan:
                bulunan.add(t)
                sirali.append(t)
        kalan = r.sub(" ", kalan)  # genel desen üstteki özel desenin parçalarını tekrar yakalamasın
    return sirali


def _oku(yol: str) -> str:
    with open(yol, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def eksik_tokenlar(kaynak: str, ciktilar: list[str]) -> list[str]:
    hedef = re.sub(r"\s+", "", "\n".join(_oku(c) for c in ciktilar if os.path.isfile(c)))
    return [t for t in tokenlar(_oku(kaynak)) if t not in hedef]


# ---------------------------------------------------------------- alt komutlar

def _kart(a):
    proje = os.path.abspath(a.proje) if a.proje else L.proje_dizini()
    sd = L.durum_dizini(proje)
    if not sd:
        raise SystemExit(_kullanim("durum dizini bulunamadı"))
    try:
        kart = L.kart_oku(sd, a.id)
    except ValueError as e:
        raise SystemExit(_kullanim(str(e)))
    if not kart:
        raise SystemExit(_kullanim(f"kart yok: {a.id}"))
    return proje, sd, kart


def _kullanim(msg: str) -> int:
    print(json.dumps({"hata": msg}, ensure_ascii=False))
    return 2


def _kayit_yolu(sd: str, gid: str) -> str:
    return os.path.join(sd, "gorevler", gid + ".onkontrol.json")


def _zaman_ts(z):
    import datetime
    try:
        t = datetime.datetime.fromisoformat(str(z))
        return t.timestamp() if t.tzinfo else t.astimezone().timestamp()
    except (ValueError, TypeError):
        return None


def gecerli_yesil_kaydi(proje: str, kart: dict, ciktilar: list[str]) -> bool:
    """Kod kartında en son yeşil test-kos kaydı geçtiyse ve çıktılardan sonra alındıysa True (test yeniden koşulmaz)."""
    if kart.get("sinif") != "kod":
        return False
    yesiller = [k for k in (kart.get("test_kosulari") or []) if k.get("asama") == "yesil"]
    if not yesiller or not yesiller[-1].get("gecti"):
        return False
    son = yesiller[-1]
    kok = son.get("kok")
    if kok and _norm(kok) != _norm(proje):
        return False
    t = _zaman_ts(son.get("zaman"))
    yollar = ciktilar or list(kart.get("ciktilar") or [])
    if t is None or not yollar:
        return False
    var = 0
    for y in yollar:
        yol = y if os.path.isabs(y) else os.path.join(proje, y)
        try:
            if os.path.getmtime(yol) > t:
                return False
            var += 1
        except OSError:
            continue  # var olmayan çıktı bayatlık kanıtı değil (kapsam denetimi ayrı)
    return var > 0


def kirmizi_kaydi_testi(kart: dict):
    """Kod kartında son kırmızı kayıt geçtiyse ve düşen kimlikler duruyorsa tabanın test sonucu; yoksa None."""
    if kart.get("sinif") != "kod":
        return None
    kirmiziler = [k for k in (kart.get("test_kosulari") or []) if k.get("asama") == "kirmizi"]
    if not kirmiziler or not kirmiziler[-1].get("gecti") or not kirmiziler[-1].get("dusenler"):
        return None
    k = kirmiziler[-1]
    return {"cikis": k.get("cikis_kodu", 1), "basarisiz": list(k["dusenler"])}


def taban(a) -> int:
    proje, sd, kart = _kart(a)
    kayit = {"zaman": L.simdi(), "dosyalar": {y: dosya_ozeti(y) for y in alan_dosyalari(proje, kart.get("yazma_alani"))}}
    if kart.get("test_komutu"):
        kayit["test"] = kirmizi_kaydi_testi(kart) or test_kos(kart["test_komutu"], proje, kart)
    L.atomik_yaz(_kayit_yolu(sd, kart["id"]), json.dumps(kayit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"taban": "kaydedildi", "dosya_sayisi": len(kayit["dosyalar"]),
                      "basarisiz_test": len(kayit.get("test", {}).get("basarisiz", []))}, ensure_ascii=False))
    return 0


def cikti_ozeti_sha(proje: str, yollar: list[str]) -> str:
    """Çıktı dosyalarının birleşik sha256'sı: sıralı (yol, dosya_ozeti.sha256) çiftleri."""
    h = hashlib.sha256()
    for y in sorted({_norm(y if os.path.isabs(y) else os.path.join(proje, y)) for y in yollar}):
        h.update((y + "\0" + (dosya_ozeti(y).get("sha256") or "yok") + "\n").encode("utf-8"))
    return h.hexdigest()


def _kosu_kaydet(proje, sd, gid, ajan_id, gecti, turler, ciktilar) -> None:
    """Koşuyu karta kalıcı yazar (kart kilidi altında oku-birleştir-yaz). Hata kontrolü etkilemez."""
    try:
        yol = L.kart_yolu(sd, gid)
        with L.kilit(yol):
            kart = L.kart_oku(sd, gid)
            if not kart:
                return
            sira = L.sonraki_sira(kart)
            kart.setdefault("onkontrol_kosulari", []).append({
                "zaman": L.simdi(), "sira": sira, "agent_id": ajan_id or None, "gecti": bool(gecti),
                "ihlal_turleri": list(dict.fromkeys(turler)),
                "cikti_ozeti_sha": cikti_ozeti_sha(proje, ciktilar)})
            L.atomik_yaz(yol, json.dumps(kart, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        pass


def izole_degil(proje: str, kart: dict) -> bool:
    """Kod kartı, git deposunun ana çalışma ağacında mı çalışıyor (worktree değil)? Yalnız uyarı içindir (ADR-0035)."""
    if (kart.get("sinif") or "").strip().lower() != "kod":
        return False
    kok = L.git_koku(proje)
    return bool(kok) and os.path.isdir(os.path.join(kok, ".git"))


def kontrol(a) -> int:
    bas = time.monotonic()
    proje, sd, kart = _kart(a)
    ihlaller, uyarilar, onceden = [], [], []
    taban_kaydi = None
    try:
        with open(_kayit_yolu(sd, kart["id"]), encoding="utf-8") as f:
            taban_kaydi = json.load(f)
    except (OSError, ValueError):
        pass
    alan = kart.get("yazma_alani") or []
    ciktilar = [c.strip() for c in (a.ciktilar or "").split(",") if c.strip()]

    # (a) BOM / satır sonu
    if taban_kaydi is None:
        uyarilar.append("taban-yok")
    else:
        for yol in alan_dosyalari(proje, alan):
            simdi = dosya_ozeti(yol)
            once = taban_kaydi.get("dosyalar", {}).get(yol, {"var": False})
            if not simdi["var"]:
                continue
            if simdi["bom"] != (once.get("bom", False) if once.get("var") else False):
                ihlaller.append({"tur": TUR_BOM, "ayrinti": f"{yol}: BOM {'eklendi' if simdi['bom'] else 'kaldırıldı'}"})
            if once.get("var") and "yok" not in (once["satir_sonu"], simdi["satir_sonu"]) and once["satir_sonu"] != simdi["satir_sonu"]:
                ihlaller.append({"tur": TUR_SATIR_SONU, "ayrinti": f"{yol}: {once['satir_sonu']} -> {simdi['satir_sonu']}"})

    # (b) kapsam
    test_kok = kart.get("test_koku") or proje
    test_alani = kart.get("test_alani") or []
    for c in ciktilar:
        if not (yol_alanda_mi(proje, c, alan) or yol_alanda_mi(test_kok, c, test_alani)):
            ihlaller.append({"tur": TUR_KAPSAM, "ayrinti": f"{c}: yazma_alani dışında"})

    # (c) test farkı
    test_kaynagi = None
    if kart.get("test_komutu") and gecerli_yesil_kaydi(proje, kart, ciktilar):
        test_kaynagi = "yesil-kaydi"
    elif kart.get("test_komutu"):
        test_kaynagi = "kosu"
        if taban_kaydi is None or "test" not in taban_kaydi:
            if "taban-yok" not in uyarilar:
                uyarilar.append("taban-yok")
        else:
            once, simdi = taban_kaydi["test"], test_kos(kart["test_komutu"], proje, kart)
            if once["basarisiz"] or simdi["basarisiz"]:
                yeni = sorted(set(simdi["basarisiz"]) - set(once["basarisiz"]))
                onceden = sorted(set(simdi["basarisiz"]) & set(once["basarisiz"]))
                if yeni:
                    ihlaller.append({"tur": TUR_TEST, "ayrinti": yeni})
            elif once["cikis"] == 0 and simdi["cikis"] != 0:
                ihlaller.append({"tur": TUR_TEST, "ayrinti": f"komut çıkış kodu 0 -> {simdi['cikis']}"})
            elif once["cikis"] != 0 and simdi["cikis"] != 0:
                onceden = [f"komut (çıkış {once['cikis']})"]

    # (d) token karşılaştırması
    kaynak = a.kaynak or kart.get("kaynak_dosya")
    if kaynak and ciktilar:
        kyol = kaynak if os.path.isabs(kaynak) else os.path.join(proje, kaynak)
        try:
            eksik = eksik_tokenlar(kyol, [c if os.path.isabs(c) else os.path.join(proje, c) for c in ciktilar])
        except OSError as e:
            return _kullanim(f"kaynak okunamadı: {e}")
        if eksik:
            ihlaller.append({"tur": TUR_TOKEN, "ayrinti": eksik})

    # (e) izole ortam: kod kartı ana çalışma ağacında (yalnız uyarı ve gölge kaydı; ADR-0035)
    if os.environ.get("ORKESTRA_IZOLE_UYARI") != "0" and izole_degil(proje, kart):
        uyarilar.append("izole-ortam")
        KM.kaydet(proje, "izole_ortam", f"{kart['id']}: kod kartı ana çalışma ağacında; worktree önerilir")

    ajan = getattr(a, "ajan_id", None)
    if not ajan:
        for o in reversed(kart.get("gecmis") or []):
            if o.get("olay") == "is-bitti":
                aid = o.get("agent_id")
                ajan = aid if aid and aid != "ana" else None
                break
    _kosu_kaydet(proje, sd, kart["id"], ajan, not ihlaller,
                 [i["tur"] for i in ihlaller], kart.get("ciktilar") or ciktilar)

    print(json.dumps({"gecti": not ihlaller, "ihlaller": ihlaller, "onceden_dusen": onceden,
                      "sure_sn": round(time.monotonic() - bas, 2), "uyarilar": uyarilar,
                      "test_kaynagi": test_kaynagi}, ensure_ascii=False))
    return 4 if ihlaller else 0


class _Ayr(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"hata": message}, ensure_ascii=False))
        raise SystemExit(2)


def main(argv=None) -> int:
    p = _Ayr(description=__doc__)
    s = p.add_subparsers(dest="komut", required=True, parser_class=_Ayr)
    t = s.add_parser("taban")
    t.add_argument("id")
    t.add_argument("--proje")
    t.set_defaults(f=taban)
    k = s.add_parser("kontrol")
    k.add_argument("id")
    k.add_argument("--ciktilar")
    k.add_argument("--kaynak")
    k.add_argument("--proje")
    k.add_argument("--ajan-id", dest="ajan_id")
    k.set_defaults(f=kontrol)
    a = p.parse_args(argv)
    try:
        return a.f(a)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2


if __name__ == "__main__":
    sys.exit(main())
