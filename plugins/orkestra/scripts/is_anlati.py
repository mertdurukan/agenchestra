"""İş anlatısı kanıt paketi (salt okuma). `orkestra is anlati` ve is-anlati skill'i bunu kullanır.

Bir işin kaydından (is.json, mevcut durum, plan, todo, çalışma özeti, ADR) madde başına durum, kanıt düzeyi ve
izinli fiil türetir. Kurallar deterministiktir; model karar vermez. Hiçbir dosya yazılmaz.
Belirtim: Claude_Orkestrasyon/105-.../tasarim.md, Modül 1.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ork_lib as L  # noqa: E402
import is_kaydi as IK  # noqa: E402

# Todo kanıt notunda doğrulama sinyali sayılan ifadeler (küçük harf, alt dize eşleşmesi).
SINYALLER = ("=>", "test", "pytest", "komut", "çıktı", "ölçüm", "canlı", "exit", "çıkış kodu", "ara ", "0 failed",
             "failed", "passed", "grep", "git diff", "sayısı")

FIILLER = {
    "Doğrulandı": ["doğruladım", "ölçtüm", "kontrol ettim"],
    "Tamamlandı": ["tamamladım", "hazırladım", "uyguladım"],
    "Başlandı": ["başladım", "üzerinde çalışıyorum"],
    "Planlandı": ["planladım", "kapsamını belirledim", "sıraya aldım"],
    "Engelli": ["ilerleyemedim", "engel nedeniyle durdurdum"],
}

_MAX = 300
_TODO_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(P\d+)\s*:\s*(.*)$")
_ETIKET_RE = re.compile(r"^\*\*[^*\n]+:\*\*")


def _kes(s: str, n: int = _MAX) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _oku(yol: str) -> str:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _en_yeni(klasor: str, desen: str) -> str:
    adaylar = sorted(glob.glob(os.path.join(klasor, desen))) if klasor else []
    return adaylar[-1] if adaylar else ""


def _bolum(metin: str, baslik_re: str) -> str:
    """`## <baslik_re>` başlığından sonraki `## ` başlığına kadar olan metin ('' = yok)."""
    m = re.search(r"^##\s+(?:%s)[^\n]*\n" % baslik_re, metin, re.M)
    if not m:
        return ""
    son = re.search(r"^##\s", metin[m.end():], re.M)
    return metin[m.end(): m.end() + son.start()] if son else metin[m.end():]


def _etiket(metin: str, ad: str) -> list[str]:
    """`**<ad>:**` etiketinin altındaki (ya da aynı satırdaki) dolu satırlar; madde işareti atılır."""
    satirlar = metin.splitlines()
    out: list[str] = []
    for i, s in enumerate(satirlar):
        m = re.match(r"^\*\*%s:\*\*\s*(.*)$" % re.escape(ad), s)
        if not m:
            continue
        if m.group(1).strip():
            out.append(m.group(1).strip())
        for t in satirlar[i + 1:]:
            if _ETIKET_RE.match(t) or t.startswith("#"):
                break
            t = re.sub(r"^\s*[-*]\s+", "", t).strip()
            if t:
                out.append(t)
        break
    return [_kes(x) for x in out]


def _paragraflar(metin: str) -> list[str]:
    return [_kes(" ".join(p.split())) for p in re.split(r"\n\s*\n", metin.strip()) if p.strip()
            and not p.strip().startswith("#")]


# ---------------------------------------------------------------- iş çözümü

def _isler(sd: str) -> list[dict]:
    out = []
    for g in IK.is_liste(sd):
        k = None
        try:
            k = IK.is_al(sd, g["id"])
        except Exception:
            k = None
        kayit = dict(k) if isinstance(k, dict) else {}
        for a, v in g.items():
            kayit.setdefault(a, v)
        out.append(kayit)
    return out


def coz(sd: str, kimlik: str) -> list[dict]:
    """I-nnn tam kimlik; yalnız rakam klasör numarası; Jira anahtarı başlık/klasör adında. Bulunmazsa []."""
    kimlik = (kimlik or "").strip()
    if not kimlik:
        return []
    isler = _isler(sd)
    if re.fullmatch(r"[Ii]-\d+", kimlik):
        return [i for i in isler if str(i.get("id", "")).upper() == kimlik.upper()]
    if re.fullmatch(r"\d+", kimlik):
        n = int(kimlik)
        out = []
        for i in isler:
            ad = os.path.basename(str(i.get("klasor") or "").rstrip("\\/"))
            m = re.match(r"(\d+)-", ad)
            if m and int(m.group(1)) == n:
                out.append(i)
        return out
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]+-\d+", kimlik):
        kal = re.compile(r"(?<![A-Za-z0-9])%s(?![0-9])" % re.escape(kimlik), re.I)
        return [i for i in isler
                if kal.search(str(i.get("baslik") or ""))
                or kal.search(os.path.basename(str(i.get("klasor") or "").rstrip("\\/")))]
    return []


# ---------------------------------------------------------------- ayrıştırma

def _todo(metin: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for s in metin.splitlines():
        m = _TODO_RE.match(s)
        if not m:
            continue
        govde = m.group(3)
        k = re.search(r"kanıt\s*:\s*(.*)$", govde, re.I)
        if k:
            not_ = k.group(1)
        else:
            t = re.search(r"\s[—-]\s*\d{4}-\d\d-\d\d\s*:\s*(.*)$", govde)
            not_ = t.group(1) if t else ""
        baslik = re.split(r"\s[—-]\s*\d{4}-\d\d-\d\d", govde)[0]
        out.setdefault(m.group(2), []).append(
            {"x": m.group(1).lower() == "x", "baslik": _kes(baslik, 120), "not": _kes(not_), "ham": govde})
    return out


def _plan(metin: str) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """-> ({P: {baslik, gap:[G..]}}, {G: [P..]} gap kapsama)."""
    maddeler: dict[str, dict] = {}
    parcalar = re.split(r"^(?=###\s+P\d+\b)", metin, flags=re.M)
    for p in parcalar:
        m = re.match(r"###\s+(P\d+)\s*(.*)", p)
        if not m:
            continue
        g = re.search(r"^\*\*Gap:\*\*\s*(.*)$", p, re.M)
        maddeler[m.group(1)] = {"baslik": _kes(m.group(2), 120),
                                "gap": re.findall(r"G\d+", g.group(1)) if g else []}
    kapsama: dict[str, list[str]] = {}
    for s in _bolum(metin, r"Gap kapsama").splitlines():
        m = re.match(r"^\s*[-*]\s*\*\*(G\d+)\*\*\s*(?:→|->)\s*(.*)$", s)
        if m:
            kapsama[m.group(1)] = re.findall(r"P\d+", m.group(2))
    return maddeler, kapsama


def _ozet_durum(metin: str) -> tuple[dict[str, str], dict[str, str]]:
    """Çalışma özeti 'Plana göre gerçekleşen': ({P: yapıldı|kısmen|yapılmadı}, {G: kapandı|açık})."""
    p: dict[str, str] = {}
    g: dict[str, str] = {}
    for s in _bolum(metin, r"Plana göre gerçekleşen").splitlines():
        m = re.match(r"^\s*[-*]\s*([PG]\d+)\s*:\s*([^\s.,;]+)", s)
        if not m:
            continue
        v = m.group(2).lower()
        (p if m.group(1)[0] == "P" else g)[m.group(1)] = v
    return p, g


def _gaplar(metin: str) -> list[tuple[str, str]]:
    out = []
    for s in _bolum(metin, r"6\. Gap analizi").splitlines():
        m = re.match(r"^\s*[-*]\s*\*\*(G\d+):\*\*\s*(.*)$", s)
        if m:
            out.append((m.group(1), _kes(m.group(2))))
    return out


def _adr_secenekler(plan: str, kok: str) -> list[str]:
    m = re.search(r"^\*\*ADR:\*\*\s*(ADR-\d+)", plan, re.M)
    if not m:
        return []
    dosyalar = sorted(glob.glob(os.path.join(kok, "adr", m.group(1) + "*.md")))
    if not dosyalar:
        return ["__yok__:" + m.group(1)]
    return _etiket_blok(_oku(dosyalar[0]), "Seçenekler")


def _etiket_blok(metin: str, ad: str) -> list[str]:
    """ADR alanı: `**Seçenekler**` ya da `**Seçenekler:**` altındaki satırlar."""
    satirlar = metin.splitlines()
    out: list[str] = []
    for i, s in enumerate(satirlar):
        if re.match(r"^\*\*%s:?\*\*" % re.escape(ad), s):
            ilk = re.sub(r"^\*\*%s:?\*\*\s*" % re.escape(ad), "", s).strip()
            if ilk:
                out.append(ilk)
            for t in satirlar[i + 1:]:
                if re.match(r"^\*\*[^*]+\*\*", t) or t.startswith("#"):
                    break
                t = re.sub(r"^\s*[-*]\s+", "", t).strip()
                if t:
                    out.append(t)
            break
    return [_kes(x) for x in out]


# ---------------------------------------------------------------- durum kuralları

def _sinyal(not_: str) -> bool:
    n = not_.lower()
    return any(s in n for s in SINYALLER)


def _madde_durumu(satirlar: list[dict], ozet: str | None, engelli: bool) -> tuple[str, str, str | None]:
    """-> (durum, kanıt düzeyi, çelişki). Todo esas alınır."""
    celiski = None
    if satirlar:
        xs = [s for s in satirlar if s["x"]]
        if len(xs) == len(satirlar):
            durum = "Doğrulandı" if any(_sinyal(s["not"]) for s in satirlar) else "Tamamlandı"
        elif xs:
            durum = "Başlandı"
        else:
            durum = "Planlandı"
        if engelli and len(xs) != len(satirlar):
            durum = "Engelli"
        if ozet == "kısmen" and durum in ("Doğrulandı", "Tamamlandı"):
            durum = "Başlandı"
        if ozet == "yapıldı" and len(xs) != len(satirlar):
            celiski = "özet 'yapıldı' ama todo [ ] açık"
        elif ozet == "yapılmadı" and xs:
            celiski = "özet 'yapılmadı' ama todo [x]"
    else:
        durum = "Engelli" if engelli else ("Başlandı" if ozet == "kısmen" else "Planlandı")
        if ozet == "yapıldı":
            celiski = "özet 'yapıldı' ama todo kaydı yok"
    if celiski:
        duzey = "Çıkarım"
    elif durum == "Doğrulandı":
        duzey = "Doğrulandı"
    else:
        duzey = "Beyan/kayıt"
    return durum, duzey, celiski


def guclu_fiil_izni(paket: dict) -> bool:
    """Kapanmış + tüm madde Doğrulandı + 'Doğrulanmayanlar' öğesi yok + çalışma özeti var."""
    if paket["is"].get("durum") != "kapandi":
        return False
    if not paket["belgeler"].get("calisma_ozeti"):
        return False
    m = paket["maddeler"]
    if not m or any(x["durum"] != "Doğrulandı" for x in m):
        return False
    return not any(s.startswith("Doğrulanmayanlar:") for s in paket["sinirlar"])


# ---------------------------------------------------------------- paket

def _sira(i: str) -> tuple:
    m = re.fullmatch(r"([A-Z])(\d+)", i)
    return (m.group(1), int(m.group(2))) if m else (i, 0)


def paket(is_kaydi: dict, sd: str | None = None) -> dict:
    kayit = is_kaydi or {}
    klasor = str(kayit.get("klasor") or "")
    uyarilar: list[str] = []
    dosya = {
        "mevcut_durum": _en_yeni(klasor, "mevcut_durum_*.md"),
        "plan": os.path.join(klasor, "plan.md") if klasor else "",
        "todo": os.path.join(klasor, "todo.md") if klasor else "",
        "calisma_ozeti": _en_yeni(klasor, "calisma_ozeti_*.md"),
    }
    metin = {a: (_oku(y) if y else "") for a, y in dosya.items()}
    belgeler = {a: bool(metin[a].strip()) for a in dosya}
    for a, ad in (("mevcut_durum", "mevcut durum"), ("plan", "plan"), ("todo", "todo"),
                  ("calisma_ozeti", "çalışma özeti")):
        if not belgeler[a]:
            uyarilar.append(f"{ad} yok" if a != "todo" or not os.path.exists(dosya[a] or "-") else "todo boş")
    todo = _todo(metin["todo"])
    if belgeler["todo"] and not todo:
        uyarilar.append("todo'da P maddesi yok")
    pm, kapsama = _plan(metin["plan"])
    ozet_p, ozet_g = _ozet_durum(metin["calisma_ozeti"])

    # kartlar: engel tespiti
    engel_kartlari: set[str] = set()
    kart_say = len(kayit.get("kartlar") or [])
    if sd:
        try:
            kl = [k for k in L.kartlar(sd, derin=False) if k.get("is") == kayit.get("id")]
            kart_say = max(kart_say, len(kl))
            engel_kartlari = {str(k.get("madde")) for k in kl if k.get("durum") in ("beklemede", "reddedildi")}
        except Exception:
            pass

    kimlikler = sorted(set(pm) | set(todo) | set(ozet_p), key=_sira)
    maddeler = []
    for k in kimlikler:
        satirlar = todo.get(k, [])
        engelli = k in engel_kartlari or any(re.search(r"\bengel", s["not"], re.I) for s in satirlar)
        durum, duzey, celiski = _madde_durumu(satirlar, ozet_p.get(k), engelli)
        notlar = [s["not"] for s in satirlar if s["not"]]
        sinyalli = [n for n in notlar if _sinyal(n)]
        baslik = (pm.get(k) or {}).get("baslik") or (satirlar[0]["baslik"] if satirlar else "")
        maddeler.append({"kimlik": k, "baslik": baslik, "durum": durum, "kanit": duzey,
                         "kanit_notu": _kes((sinyalli or notlar or [""])[0]),
                         "fiiller": list(FIILLER[durum]), "celiski": celiski})
        if celiski:
            uyarilar.append(f"{k}: {celiski} (çelişki)")
    mdurum = {m["kimlik"]: m["durum"] for m in maddeler}

    # gap'ler
    bagli: dict[str, list[str]] = {}
    for k, v in pm.items():
        for g in v["gap"]:
            bagli.setdefault(g, [])
            if k not in bagli[g]:
                bagli[g].append(k)
    for g, ps in kapsama.items():
        for k in ps:
            bagli.setdefault(g, [])
            if k not in bagli[g]:
                bagli[g].append(k)
    gapler = []
    for g, g_metin in _gaplar(metin["mevcut_durum"]):
        ps = sorted(bagli.get(g, []), key=_sira)
        v = ozet_g.get(g)
        if v is None:
            d = "Bilinmiyor"
        else:
            d = "kapandı" if v.startswith("kapan") else "açık"
        if d == "kapandı" and ps and any(mdurum.get(p) != "Doğrulandı" for p in ps):
            d = "açık"
            uyarilar.append(f"{g}: özet 'kapandı' ama bağlı madde Doğrulandı değil (açığa çekildi)")
        gapler.append({"kimlik": g, "metin": g_metin, "durum": d, "maddeler": ps})

    # anlatı alanları
    ne_icin = _paragraflar(_bolum(metin["plan"], r"1\. Hedef"))
    ne_icin += _etiket(metin["calisma_ozeti"], "Amaç")
    if not ne_icin:
        ne_icin = _paragraflar(_bolum(metin["plan"], r"Özet"))
    sonuc = _paragraflar(_bolum(metin["calisma_ozeti"], r"Özet")) + _etiket(metin["calisma_ozeti"], "Ana bulgu")
    yontem = _etiket(metin["mevcut_durum"], "Yöntem")
    kararlar = [_kes(re.sub(r"^\s*[-*]\s*", "", s)) for s in _bolum(metin["plan"], r"3\. Kararlar").splitlines()
                if re.match(r"^\s*[-*]\s*\*\*K\d+:\*\*", s)]
    yontem += kararlar[:4]
    kok = os.path.dirname(os.path.dirname(sd)) if sd else ""
    if metin["plan"]:
        adr = _adr_secenekler(metin["plan"], kok) if kok else []
        if adr and adr[0].startswith("__yok__:"):
            uyarilar.append(f"{adr[0][8:]} dosyası adr/ altında bulunamadı")
        else:
            yontem += adr
    sinirlar = ["Doğrulanmayanlar: " + x for x in _etiket(metin["calisma_ozeti"], "Doğrulanmayanlar")
                if x.strip(" .").lower() not in ("yok", "-")]
    sinirlar += ["Açık iş: " + x for x in _etiket(metin["calisma_ozeti"], "Açık işler")
                 if x.strip(" .").lower() not in ("yok", "-")]

    p = {
        "is": {"id": kayit.get("id"), "baslik": kayit.get("baslik"), "durum": kayit.get("durum"),
               "onay": kayit.get("onay"), "mod": kayit.get("mod"), "olusturma": kayit.get("olusturma"),
               "guncelleme": kayit.get("guncelleme"), "oturum_say": len(kayit.get("oturumlar") or []),
               "kart_say": kart_say},
        "belgeler": belgeler,
        "ne_icin": ne_icin[:3],
        "sonuc": sonuc,
        "yontem": yontem,
        "maddeler": maddeler,
        "gapler": gapler,
        "sinirlar": sinirlar,
        "guclu_fiil_izni": False,
        "uyarilar": uyarilar,
    }
    p["guclu_fiil_izni"] = guclu_fiil_izni(p)
    return p


# ---------------------------------------------------------------- çıktılar

def metin(p: dict) -> str:
    i = p["is"]
    s = [f"# {i['id']} — {_kes(i['baslik'] or '', 100)} [{i['durum']}]"]
    for u in p["uyarilar"][:5]:
        s.append(f"UYARI: {_kes(u, 150)}")
    if len(p["uyarilar"]) > 5:
        s.append(f"UYARI: +{len(p['uyarilar']) - 5} uyarı daha")

    def blok(ad, liste, en_cok):
        if not liste:
            return
        s.append(ad)
        s.extend("- " + _kes(x, 250) for x in liste[:en_cok])

    blok("NE İÇİN", p["ne_icin"], 3)
    blok("SONUÇ", p["sonuc"], 4)
    blok("YÖNTEM", p["yontem"], 5)
    if p["maddeler"]:
        s.append("MADDELER")
        for m in p["maddeler"][:12]:
            c = f" | ÇELİŞKİ: {_kes(m['celiski'], 60)}" if m["celiski"] else ""
            s.append(f"- {m['kimlik']} {_kes(m['baslik'], 60)}: {m['durum']} / {m['kanit']}; "
                     f"fiiller: {', '.join(m['fiiller'])}{c}")
        if len(p["maddeler"]) > 12:
            s.append(f"- +{len(p['maddeler']) - 12} madde")
    if p["gapler"]:
        s.append("GAP'LER")
        s.append("- " + "; ".join(f"{g['kimlik']} {g['durum']}" for g in p["gapler"]))
    blok("SINIRLAR", p["sinirlar"], 4)
    s.append("GÜÇLÜ FİİL İZNİ: " + ("evet" if p["guclu_fiil_izni"] else "hayır"))
    return "\n".join(s[:70])


def audit_metin(p: dict) -> str:
    i = p["is"]
    s = [f"# {i['id']} — {i['baslik']} [{i['durum']}]", "",
         "| madde | başlık | durum | kanıt | not | çelişki |", "|---|---|---|---|---|---|"]
    for m in p["maddeler"]:
        s.append("| " + " | ".join([m["kimlik"], m["baslik"], m["durum"], m["kanit"],
                                    m["kanit_notu"].replace("|", "/"), m["celiski"] or "-"]) + " |")
    s += ["", "| gap | durum | maddeler | metin |", "|---|---|---|---|"]
    for g in p["gapler"]:
        s.append(f"| {g['kimlik']} | {g['durum']} | {', '.join(g['maddeler']) or '-'} | {g['metin'].replace('|', '/')} |")
    for u in p["uyarilar"]:
        s.append(f"UYARI: {u}")
    s.append("GÜÇLÜ FİİL İZNİ: " + ("evet" if p["guclu_fiil_izni"] else "hayır"))
    return "\n".join(s)


def _zaman(v):
    try:
        t = datetime.datetime.fromisoformat(str(v))
        return t if t.tzinfo else t.astimezone()
    except (TypeError, ValueError):
        return None


def toplu(sd: str, gun: int = 7, en_cok: int = 8) -> list[dict]:
    esik = datetime.datetime.now().astimezone() - datetime.timedelta(days=gun)
    adaylar = []
    for k in _isler(sd):
        t = _zaman(k.get("guncelleme") or k.get("olusturma"))
        if t and t >= esik:
            adaylar.append((t, k))
    adaylar.sort(key=lambda x: x[0], reverse=True)
    out = []
    for _, k in adaylar[:en_cok]:
        p = paket(k, sd)
        out.append({"id": k.get("id"), "baslik": k.get("baslik"), "durum": k.get("durum"),
                    "madde_say": len(p["maddeler"]),
                    "dogrulandi_say": sum(1 for m in p["maddeler"] if m["durum"] == "Doğrulandı")})
    return out


def main(argv: list[str]) -> int:
    for ak in (sys.stdout, sys.stderr):
        try:
            ak.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if not argv or argv[0] not in ("paket", "toplu"):
        print("kullanım: is_anlati.py paket <kimlik> [--json|--audit] | toplu [--gun N]", file=sys.stderr)
        return 2
    sd = L.durum_dizini()
    if not sd:
        print("bu projede orkestra açık değil", file=sys.stderr)
        return 1
    if argv[0] == "toplu":
        gun = int(argv[argv.index("--gun") + 1]) if "--gun" in argv else 7
        for r in toplu(sd, gun):
            print(f"{r['id']}\t{r['durum']}\t{r['dogrulandi_say']}/{r['madde_say']}\t{r['baslik']}")
        return 0
    if len(argv) < 2:
        print("kimlik gerekli", file=sys.stderr)
        return 2
    bulunan = coz(sd, argv[1])
    if not bulunan:
        print(f"iş yok: {argv[1]}", file=sys.stderr)
        return 1
    if len(bulunan) > 1:
        for b in bulunan:
            print(f"{b.get('id')}\t{b.get('baslik')}")
        return 2
    p = paket(bulunan[0], sd)
    if "--json" in argv:
        print(json.dumps(p, ensure_ascii=False, indent=2))
    elif "--audit" in argv:
        print(audit_metin(p))
    else:
        print(metin(p))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
