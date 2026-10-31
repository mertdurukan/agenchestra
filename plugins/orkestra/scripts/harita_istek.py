"""İstek eşleme sorgusu (ADR-0112, I-296; model çağırmaz, deterministiktir).

`orkestra harita istek "<metin>"`: isteği konu kartlarının adı ve eşanlamlılarıyla eşler, kartın yüzeylerinden
kenar listesi boyunca bir adım gezip etki kümesini ve belirsiz (düşük güvenli, llm kökenli) kenarları listeler.
Girdi: `<graf dizini>/kartlar/<konu>.md` (şema `harita_sema.py`) ve `<graf dizini>/kenarlar.jsonl`.
Kartta yüzey satırı: `- <ad> (<yol>)` ya da yalnız `- <ad>`; eşanlamlı satırı `- <ifade>` ya da virgüllü liste.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re

GRAF_DIZINI = "bilgi_grafigi"
_SATIR = re.compile(r"^\s*[-*]\s*(.+?)\s*$")
_YUZEY = re.compile(r"^(.*?)\s*\(([^)]+)\)\s*$")
_KELIME = re.compile(r"[a-zçğıöşüâîû0-9]+")


def _kucuk(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _bolumler(metin: str) -> dict[str, list[str]]:
    sonuc, ad = {}, None
    for s in metin.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", s)
        if m:
            ad = m.group(1)
            sonuc[ad] = []
        elif ad is not None and s.strip():
            sonuc[ad].append(s)
    return sonuc


def kartlari_oku(graf: str) -> list[dict]:
    kartlar = []
    klasor = os.path.join(graf, "kartlar")
    if not os.path.isdir(klasor):
        return kartlar
    for ad in sorted(os.listdir(klasor)):
        if not ad.endswith(".md"):
            continue
        with open(os.path.join(klasor, ad), encoding="utf-8") as f:
            b = _bolumler(f.read())
        esanlamli = [os.path.splitext(ad)[0].replace("_", " ").replace("-", " ")]
        for s in b.get("Eşanlamlılar", []):
            m = _SATIR.match(s)
            esanlamli += [x.strip() for x in (m.group(1) if m else s).split(",") if x.strip()]
        yuzeyler = []
        for s in b.get("Yüzeyler", []):
            m = _SATIR.match(s)
            metin = m.group(1) if m else s.strip()
            y = _YUZEY.match(metin)
            yuzeyler.append({"ad": (y.group(1) if y else metin).strip(), "yol": y.group(2).strip() if y else ""})
        kartlar.append({"konu": os.path.splitext(ad)[0], "esanlamlilar": esanlamli, "yuzeyler": yuzeyler})
    return kartlar


def _kelime_esler(w: str, t: str) -> bool:
    if t == w:
        return True
    kisa = min(len(w), len(t))
    # kısa kök uzun başka sözcüğe ek sayılmasın ("yap" ≠ "yapılacak"): ek uzunluğu kök boyuna bağlı sınırlı
    ek_sinir = 5 if kisa < 5 else 8
    return kisa >= 3 and abs(len(w) - len(t)) <= ek_sinir and (t.startswith(w) or w.startswith(t))


def esle(istek: str, kartlar: list[dict]) -> list[dict]:
    """İstekteki sözcükleri kart ifadeleriyle eşler; ifadenin her sözcüğü istekte (ek toleranslı) geçmelidir."""
    tokenler = _KELIME.findall(_kucuk(istek))
    sonuc = []
    for k in kartlar:
        for ifade in k["esanlamlilar"]:
            kel = _KELIME.findall(_kucuk(ifade))
            if kel and all(any(_kelime_esler(w, t) for t in tokenler) for w in kel):
                sonuc.append(dict(k, eslesen=ifade))
                break
    return sonuc


def kenarlari_oku(graf: str) -> list[dict]:
    yol = os.path.join(graf, "kenarlar.jsonl")
    if not os.path.exists(yol):
        return []
    kenarlar = []
    with open(yol, encoding="utf-8") as f:
        for s in f:
            try:
                kenarlar.append(json.loads(s))
            except ValueError:
                continue
    return kenarlar


def _uyar(desen: str, yol: str) -> bool:
    if desen == yol:
        return True
    return ("*" in desen) and (fnmatch.fnmatch(yol, desen) or (desen.startswith("**/") and yol.endswith(desen[2:])))


def komsular(yollar: set[str], kenarlar: list[dict]) -> list[dict]:
    """Yüzey yollarına bir adım bağlı kenarlar (iki yönde); hedef desen (`**/ad`) yola eşleşir."""
    sonuc, gorulen = [], set()
    for k in kenarlar:
        if any(_uyar(k.get("hedef", ""), y) or _uyar(k.get("kaynak", ""), y) for y in yollar):
            anahtar = (k.get("kaynak"), k.get("iliski"), k.get("hedef"))
            if anahtar not in gorulen:
                gorulen.add(anahtar)
                sonuc.append(k)
    return sonuc


def etki(istek: str, graf: str) -> dict:
    kartlar = esle(istek, kartlari_oku(graf))
    if not kartlar:
        return {"eslesti": False, "konular": [], "yuzeyler": [], "komsular": [], "belirsiz": []}
    yuzeyler = [dict(y, konu=k["konu"]) for k in kartlar for y in k["yuzeyler"]]
    yollar = {y["yol"] for y in yuzeyler if y["yol"]}
    kom = komsular(yollar, kenarlari_oku(graf)) if yollar else []
    belirsiz = [k for k in kom if k.get("guven") == "dusuk" or k.get("koken") == "llm"]
    return {"eslesti": True, "konular": [k["konu"] for k in kartlar], "yuzeyler": yuzeyler,
            "komsular": [k for k in kom if k not in belirsiz], "belirsiz": belirsiz}


def metin(sonuc: dict) -> str:
    if not sonuc["eslesti"]:
        return "eşleşmedi: istek hiçbir konu kartıyla eşleşmedi (etki kümesi boş)"
    s = [f"konular: {', '.join(sonuc['konular'])}", "yüzeyler:"]
    s += [f"- {y['ad']}" + (f" ({y['yol']})" if y["yol"] else "") + f" [{y['konu']}]" for y in sonuc["yuzeyler"]]
    if sonuc["komsular"]:
        s.append("bağlı kenarlar:")
        s += [f"- {k['kaynak']} {k['iliski']} {k['hedef']} [{k['koken']}/{k['guven']}] {k['kanit']}" for k in sonuc["komsular"]]
    if sonuc["belirsiz"]:
        s.append("belirsiz kenarlar (düşük güven, doğrula):")
        s += [f"- {k['kaynak']} {k['iliski']} {k['hedef']} [{k['koken']}/{k['guven']}]" for k in sonuc["belirsiz"]]
    return "\n".join(s)
