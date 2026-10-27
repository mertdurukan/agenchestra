"""Bash araç çıktılarının ana ajan bağlamındaki payını ve tavan (BASH_MAX_OUTPUT_LENGTH) etkisini ölçer (ADR-0086).

Girdi: Claude Code oturum günlükleri (`<dizin>/*.jsonl`). Çıktı: ağırlıklı paylar, büyük çıktı aileleri, tavan
simülasyonu, tekrar (yeniden koşma) oranı ve oturum bazlı bootstrap güven aralığı.

Yöntem
- Ağırlık: bir öğe (araç sonucu, girdi, metin) kendinden sonraki API çağrısı sayısı kadar bağlamda yeniden okunur;
  `compact_boundary` ağırlığı sıfırlar (öğe özetlenir). Yan zincir (isSidechain) sayılmaz.
- Tavan simülasyonu: eşiği aşan her çıktı yerine `onizleme` karakter girer (P1 deneyi: 2.519).
- Tekrar: aynı komut, boru türevi (aynı baş komut), komutta adı geçen dosyanın Read'i ya da kaydedilen çıktı yolunun
  Read'i; sonraki 3 araç çağrısında aranır.
- Güven: tekrar için Jeffreys %95 üst sınır; azalma için oturum bazlı bootstrap (tohum sabit).
Kullanım: python bash_cikti_olc.py [--dizin D] [--kesit ISO] [--tavan 10000] [--onizleme 2519] [--json]
"""
import argparse
import collections
import datetime
import glob
import json
import math
import os
import random
import re
import sys

VARSAYILAN_TAVAN = 10000
VARSAYILAN_ONIZLEME = 2519
BASH_ADLARI = ("Bash", "PowerShell")
SONRAKI_CAGRI = 3
KAYIT_YOLU = re.compile(r"Full output saved to:\s*(\S+)")
OKU_AILELERI = ("cat/sed/head/tail tek", "grep/rg", "ls/find", "cat/sed/awk boru")


def _utc(s):
    """ISO metni UTC datetime'a çevirir; saat dilimi yoksa yerel saat sayılır."""
    d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.astimezone()
    return d.astimezone(datetime.timezone.utc)


def metin_uzunlugu(c):
    if isinstance(c, str):
        return len(c)
    if isinstance(c, list):
        n = 0
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text":
                n += len(b.get("text", "") or "")
        return n
    return 0


def metin(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join((b.get("text", "") or "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def aile(cmd):
    """Komutu aileye ayırır; `orkestra` yalnız komut konumunda aranır (cd .../orkestra && sed ... yanlış sayılmasın)."""
    cli = r"(^|[;&|(]\s*)(python3?\s+\S*orkestra\.py|orkestra)\s+"
    if re.search(cli + r"is\s+(todo|devam)", cmd):
        return "orkestra is todo/devam"
    if re.search(cli, cmd):
        return "orkestra diğer"
    if re.search(r"pytest|unittest", cmd):
        return "test (pytest)"
    if re.search(r"\bgit\b\s+(-\S+\s+)*(log|diff|show|status|blame)", cmd):
        return "git okuma"
    if re.search(r"\bgit\b", cmd):
        return "git diğer"
    if re.search(r"^\s*(cd [^;&|]*(&&|;)\s*)?(cat|sed|head|tail)\b", cmd) and "|" not in cmd:
        return "cat/sed/head/tail tek"
    if re.search(r"\b(grep|rg|findstr|Select-String)\b", cmd):
        return "grep/rg"
    if re.search(r"\b(ls|find|dir|tree)\b", cmd):
        return "ls/find"
    if re.search(r"(^|[\s;&|(])(python3?|py)(\.exe)?\s", cmd):
        return "python betik"
    if re.search(r"curl|az |gh |wget|Invoke-", cmd):
        return "ağ/CLI (curl,az,gh)"
    if re.search(r"\b(cat|sed|head|tail|awk|wc|sort)\b", cmd):
        return "cat/sed/awk boru"
    return "diğer"


def _bas(cmd):
    return re.split(r"(?<!\|)\|(?!\|)", cmd.strip(), maxsplit=1)[0].strip()


def jeffreys_ust(k, n):
    """Jeffreys %95 tek yönlü üst sınır (scipy yoksa normal yaklaşım)."""
    if n <= 0:
        return 0.0
    try:
        from scipy.stats import beta
        return float(beta.ppf(0.95, k + 0.5, n - k + 0.5))
    except Exception:
        p = (k + 0.5) / (n + 1)
        return min(1.0, p + 1.645 * math.sqrt(p * (1 - p) / (n + 1)))


def oturum_tara(satirlar, kesit=None):
    """Tek oturumun günlük satırlarını tarar. Döner: {"cagri", "ogeler": [(kategori, kar, agirlik)], "bash": [...]}."""
    gorulen = set()
    ncall = 0
    bekleyen = []   # (kategori, kar, ncall_basi, bash_kaydi|None)
    araclar = {}    # id -> (ad, anahtar)
    sira = []       # [(ad, anahtar)] araç çağrıları sırasıyla
    ogeler = []
    bash = []

    def kapat(bitis, canli=False):
        for kat, kar, nc, kayit in bekleyen:
            w = max(bitis - nc, 0)
            ogeler.append((kat, kar, w))
            if kayit is not None:
                kayit["w"] = w
                kayit["canli"] = canli  # oturum sonunda hâlâ bağlamda duran (compact_boundary'den sonra gelen) sonuç
        bekleyen.clear()

    for l in satirlar:
        try:
            d = json.loads(l)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if kesit is not None and d.get("timestamp"):
            try:
                if _utc(d["timestamp"]) > kesit:
                    continue
            except ValueError:
                pass
        t = d.get("type")
        if t == "system" and d.get("subtype") == "compact_boundary":
            kapat(ncall)
            continue
        m = d.get("message") or {}
        if t == "assistant":
            mid = m.get("id")
            if mid and mid not in gorulen:
                gorulen.add(mid)
                ncall += 1
            icerik = m.get("content") if isinstance(m.get("content"), list) else []
            for b in icerik:
                if b.get("type") == "tool_use":
                    ad = b.get("name")
                    inp = b.get("input", {})
                    anahtar = inp.get("command") or inp.get("file_path") or ""
                    araclar[b["id"]] = (ad, anahtar)
                    sira.append((ad, anahtar))
                    kat = "in:Bash" if ad in BASH_ADLARI else ("in:" + ad if ad in ("Write", "Edit") else "in:other")
                    bekleyen.append((kat, len(json.dumps(inp, ensure_ascii=False)), ncall, None))
                elif b.get("type") in ("text", "thinking"):
                    bekleyen.append(("asst_text", len(b.get("text", "") or b.get("thinking", "") or ""), ncall, None))
        elif t == "user":
            c = m.get("content")
            if isinstance(c, str):
                bekleyen.append(("user_text", len(c), ncall, None))
            elif isinstance(c, list):
                for b in c:
                    if b.get("type") == "tool_result":
                        ad, anahtar = araclar.get(b.get("tool_use_id"), ("?", ""))
                        kar = metin_uzunlugu(b.get("content"))
                        kat = "res:" + ("Bash" if ad in BASH_ADLARI else "Read" if ad == "Read" else "other")
                        kayit = None
                        if ad in BASH_ADLARI:
                            kayit = {"cmd": anahtar, "ch": kar, "w": 0, "pos": None,
                                     "kayit_yolu": (KAYIT_YOLU.search(metin(b.get("content"))) or [None, None])[1]}
                            for i in range(len(sira) - 1, -1, -1):
                                if sira[i] == (ad, anahtar):
                                    kayit["pos"] = i
                                    break
                            bash.append(kayit)
                        bekleyen.append((kat, kar, ncall, kayit))
                    elif b.get("type") == "text":
                        bekleyen.append(("user_text", len(b.get("text", "")), ncall, None))
        elif t == "attachment":
            bekleyen.append(("user_text", len(json.dumps(d.get("attachment", ""), ensure_ascii=False)), ncall, None))
    kapat(ncall, canli=True)
    for r in bash:
        r["tekrar"] = _tekrar_mi(r, sira)
    return {"cagri": ncall, "ogeler": ogeler, "bash": bash}


def _tekrar_mi(r, sira):
    pos = r["pos"]
    if pos is None:
        return False
    cb = _bas(r["cmd"])
    for ad, anahtar in sira[pos + 1: pos + 1 + SONRAKI_CAGRI]:
        if ad in BASH_ADLARI:
            if anahtar.strip() == r["cmd"].strip() or (cb and _bas(anahtar) == cb):
                return True
        elif ad == "Read" and anahtar:
            bn = os.path.basename(anahtar)
            if (bn and bn in r["cmd"]) or (r["kayit_yolu"] and anahtar == r["kayit_yolu"]):
                return True
    return False


def ilk_zaman(satirlar):
    """Günlükteki ilk zaman damgası (UTC) ya da None."""
    for l in satirlar:
        try:
            ts = json.loads(l).get("timestamp")
        except Exception:
            continue
        if ts:
            try:
                return _utc(ts)
            except ValueError:
                continue
    return None


def dizin_tara(dizin, kesit=None, bas=None):
    """bas verilirse yalnız ilk zaman damgası bas'tan sonra olan oturumlar taranır (önce/sonra pencereleri karışmasın)."""
    sonuc = []
    for f in sorted(glob.glob(os.path.join(dizin, "*.jsonl"))):
        with open(f, encoding="utf-8", errors="replace") as fh:
            satirlar = fh.readlines()
        if bas is not None:
            z = ilk_zaman(satirlar)
            if z is None or z < bas:
                continue
        o = oturum_tara(satirlar, kesit)
        o["oturum"] = os.path.basename(f)
        sonuc.append(o)
    return sonuc


def hesapla(oturumlar, tavan=VARSAYILAN_TAVAN, onizleme=VARSAYILAN_ONIZLEME, bootstrap=1000, tohum=0):
    toplam = collections.Counter()
    for o in oturumlar:
        for kat, kar, w in o["ogeler"]:
            toplam[kat] += kar * w
    agirlik = sum(toplam.values()) or 1
    bash = [r for o in oturumlar for r in o["bash"]]
    buyuk = [r for r in bash if r["ch"] > tavan]
    cagri = sum(o["cagri"] for o in oturumlar)
    cikti = {
        "oturum": len(oturumlar), "api_cagri": cagri, "bash_sonuc": len(bash), "buyuk": len(buyuk), "tavan": tavan,
        "pay": {k: v / agirlik for k, v in toplam.items()},
        "bash_payi": toplam["res:Bash"] / agirlik,
    }
    bash_w = sum(r["ch"] * r["w"] for r in bash)
    cikti["buyuk_pay_bash_icinde"] = (sum(r["ch"] * r["w"] for r in buyuk) / bash_w) if bash_w else 0.0
    # aileler
    sayac, kar_ail = collections.Counter(), collections.defaultdict(int)
    for r in buyuk:
        a = aile(r["cmd"])
        sayac[a] += 1
        kar_ail[a] += r["ch"]
    kar_top = sum(kar_ail.values()) or 1
    cikti["aileler"] = {a: {"adet": n, "kar_payi": kar_ail[a] / kar_top, "ort": kar_ail[a] / n} for a, n in sayac.most_common()}
    cs = ("cat/sed/head/tail tek", "cat/sed/awk boru")
    cikti["cat_sed_birlesik"] = {"adet": sum(sayac[a] for a in cs), "kar_payi": sum(kar_ail[a] for a in cs) / kar_top}
    oku_n = sum(sayac[a] for a in OKU_AILELERI)
    cikti["okuma_grubu"] = {"adet": oku_n, "kar_payi": sum(kar_ail[a] for a in OKU_AILELERI) / kar_top}
    # simülasyon
    def azalma(bs):
        kazanc = sum((r["ch"] - onizleme) * r["w"] for r in bs if r["ch"] > tavan)
        return kazanc
    k = azalma(bash)
    cikti["simulasyon"] = {"toplam_baglam_azalma": k / agirlik, "bash_karakter_azalma": (k / bash_w) if bash_w else 0.0}
    # bootstrap (oturum bazlı): bash karakterindeki göreli azalma
    rng = random.Random(tohum)
    oranlar = []
    if oturumlar and bootstrap:
        for _ in range(bootstrap):
            ornek = [oturumlar[rng.randrange(len(oturumlar))] for _ in oturumlar]
            bs = [r for o in ornek for r in o["bash"]]
            pay = sum(r["ch"] * r["w"] for r in bs)
            if pay:
                oranlar.append(azalma(bs) / pay)
    oranlar.sort()
    if oranlar:
        cikti["simulasyon"]["bootstrap_bash_azalma_95"] = [oranlar[int(0.025 * len(oranlar))], oranlar[int(0.975 * len(oranlar)) - 1]]
    # tekrar
    def tekrar(rs):
        k_ = sum(1 for r in rs if r["tekrar"])
        return {"k": k_, "n": len(rs), "oran": k_ / len(rs) if rs else 0.0, "jeffreys_ust": jeffreys_ust(k_, len(rs))}
    cikti["tekrar_tum"] = tekrar(bash)
    cikti["tekrar_buyuk"] = tekrar(buyuk)
    canli = [r for r in bash if r["canli"]]
    cikti["canli"] = {"bash_sonuc": len(canli), ">5000": sum(1 for r in canli if r["ch"] > 5000),
                      ">10000": sum(1 for r in canli if r["ch"] > 10000),
                      ">20000": sum(1 for r in canli if r["ch"] > 20000),
                      ">30000": sum(1 for r in canli if r["ch"] > 30000)}
    en_buyuk = sorted((r["ch"] for r in bash), reverse=True)[:12]
    cikti["en_buyuk_12"] = en_buyuk
    return cikti


def cagri_basina(oturumlar):
    """Çağrı başına ağırlıklı Bash sonuç karakteri (S1 ölçüsü)."""
    c = sum(o["cagri"] for o in oturumlar)
    return sum(r["ch"] * r["w"] for o in oturumlar for r in o["bash"]) / c if c else 0.0


def karsilastir(once, sonra, bootstrap=1000, tohum=0):
    """S1: sonra penceresinin çağrı başına Bash karakteri öncekine göre göreli azalma; oturum bazlı bootstrap %95 aralığı."""
    a, b = cagri_basina(once), cagri_basina(sonra)
    sonuc = {"once": {"oturum": len(once), "api_cagri": sum(o["cagri"] for o in once), "cagri_basina": a},
             "sonra": {"oturum": len(sonra), "api_cagri": sum(o["cagri"] for o in sonra), "cagri_basina": b},
             "azalma": (1 - b / a) if a else 0.0}
    rng = random.Random(tohum)
    oranlar = []
    if once and sonra and bootstrap:
        for _ in range(bootstrap):
            ao = cagri_basina([once[rng.randrange(len(once))] for _ in once])
            bo = cagri_basina([sonra[rng.randrange(len(sonra))] for _ in sonra])
            if ao:
                oranlar.append(1 - bo / ao)
    oranlar.sort()
    if oranlar:
        sonuc["bootstrap_95"] = [oranlar[int(0.025 * len(oranlar))], oranlar[int(0.975 * len(oranlar)) - 1]]
    return sonuc


def yaz(c):
    p = lambda *a: print(*a)  # noqa: E731
    p(f"oturum {c['oturum']}  api_çağrı {c['api_cagri']}  bash_sonuç {c['bash_sonuc']}  >{c['tavan']}: {c['buyuk']}")
    p(f"bash payı (ağırlıklı): %{c['bash_payi'] * 100:.1f}; bash içinde >{c['tavan']} çıktıların payı: %{c['buyuk_pay_bash_icinde'] * 100:.1f}")
    for k, v in sorted(c["pay"].items(), key=lambda x: -x[1]):
        p(f"  {k}: %{v * 100:.1f}")
    p(f"aile dökümü (>{c['tavan']}):")
    for a, v in c["aileler"].items():
        p(f"  {a}: {v['adet']} adet, karakter payı %{v['kar_payi'] * 100:.1f}, ort {v['ort']:.0f}")
    og = c["okuma_grubu"]
    p(f"dosya/dizin okuma grubu: {og['adet']} adet, karakter payı %{og['kar_payi'] * 100:.1f}")
    cb = c["cat_sed_birlesik"]
    p(f"cat/sed birleşik (tek + boru): {cb['adet']} adet, karakter payı %{cb['kar_payi'] * 100:.1f}"
      + (" — %30 yeniden değerlendirme eşiğini aşıyor" if cb["kar_payi"] > 0.30 else ""))
    s = c["simulasyon"]
    p(f"simülasyon (tavan {c['tavan']}): toplam bağlam %{s['toplam_baglam_azalma'] * 100:.1f}, bash karakteri %{s['bash_karakter_azalma'] * 100:.1f}"
      + (f", bootstrap95 [{s['bootstrap_bash_azalma_95'][0] * 100:.1f}; {s['bootstrap_bash_azalma_95'][1] * 100:.1f}]" if "bootstrap_bash_azalma_95" in s else ""))
    for ad in ("tekrar_tum", "tekrar_buyuk"):
        t = c[ad]
        p(f"{ad}: {t['k']}/{t['n']} (%{t['oran'] * 100:.2f}), Jeffreys95 üst %{t['jeffreys_ust'] * 100:.2f}")
    cl = c["canli"]
    p(f"canlı küme (compaction sonrası bağlamda): {cl['bash_sonuc']} sonuç; >5K {cl['>5000']}, >10K {cl['>10000']}, >20K {cl['>20000']}, >30K {cl['>30000']}")
    p("en büyük 12 çıktı:", c["en_buyuk_12"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dizin", default=os.path.join(os.path.expanduser("~"), ".claude", "projects", "C--Mert-McD"))
    ap.add_argument("--kesit", help="bu zamandan (ISO; saat dilimi yoksa yerel) sonraki günlük satırları sayılmaz")
    ap.add_argument("--bas", help="yalnız ilk günlük satırı bu zamandan (ISO) sonra olan oturumlar taranır (uygulama sonrası pencere)")
    ap.add_argument("--tavan", type=int, default=VARSAYILAN_TAVAN)
    ap.add_argument("--onizleme", type=int, default=VARSAYILAN_ONIZLEME)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--json", action="store_true", help="sonucu JSON basar")
    a = ap.parse_args(argv)
    kesit = _utc(a.kesit) if a.kesit else None
    bas = _utc(a.bas) if a.bas else None
    c = hesapla(dizin_tara(a.dizin, kesit, bas), a.tavan, a.onizleme, a.bootstrap)
    if a.json:
        print(json.dumps(c, ensure_ascii=False, indent=2))
    else:
        yaz(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
