"""İş başına maliyet/süre/kalite raporu (salt okuma). `orkestra is rapor` bunu kullanır.

Kaynaklar (sd = .claude/orkestra): maliyet.jsonl (yalnız ork_lib.maliyet_kayitlari), zaman.jsonl, isler.json,
iş klasörlerindeki todo.md, gorevler/G-*.json. 'is' değeri '-', boş ya da yoksa satır I-000 kovasına girer
(yalnız raporda; dosyalar değişmez).
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re

import ork_lib as L
import iz

KOVA = "I-000"
KOVA_BASLIK = "İşe bağlanmamış"
CSV_BASLIK = ["is", "baslik", "usd", "token", "claude_sn", "alt_sn", "oturum", "kart", "todo_biten", "todo_toplam",
              "ilk", "son"]


def _is_id(v) -> str:
    v = (v or "").strip() if isinstance(v, str) else ""
    return KOVA if v in ("", "-") else v


def _sayi(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _token(r: dict) -> int:
    return int(sum(_sayi(r.get(a)) for a in ("giris", "cikis", "onbellek_okuma", "onbellek_yazma")))


def _gun(r: dict):
    z = r.get("zaman")
    return z[:10] if isinstance(z, str) and len(z) >= 10 else None


def _json(yol: str) -> dict:
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _sirala(ids) -> list[str]:
    def anahtar(i):
        m = re.fullmatch(r"I-(\d+)", i)
        return (0, int(m.group(1)), i) if m else (1, 0, i)
    return sorted((i for i in ids if i != KOVA), key=anahtar)


def _todo(klasor) -> tuple[int, int]:
    if not isinstance(klasor, str) or not klasor:
        return 0, 0
    try:
        with open(os.path.join(klasor, "todo.md"), encoding="utf-8", errors="replace") as f:
            metin = f.read()
    except OSError:
        return 0, 0
    biten = len(re.findall(r"^\s*[-*]\s*\[[xX]\]", metin, re.M))
    acik = len(re.findall(r"^\s*[-*]\s*\[ \]", metin, re.M))
    return biten, biten + acik


def _veri(sd: str) -> dict:
    kartlar = L.kartlar(sd)
    kart_is = {k["id"]: k.get("is") for k in kartlar if k.get("id") and k.get("is")}
    mal = [dict(r, _is=_is_id(L.satir_isi(r, kart_is))) for r in L.maliyet_kayitlari(sd)]
    zam = [dict(r, _is=_is_id(L.satir_isi(r, kart_is))) for r in L.zaman_kayitlari(sd)]
    import is_kaydi as IK  # noqa: PLC0415
    try:
        isler = IK.merkez_isler(sd)   # klasor alanı çözülmüş (I-223: silinmiş worktree yolu ana ağaca bağlanır)
    except Exception:  # noqa: BLE001 - eski _json davranışı: bozuk/eksik merkez kayıt rapor üretimini durdurmaz
        isler = {}
    return {"mal": mal, "zam": zam, "isler": isler, "kartlar": kartlar}


def _kapi_golge(sd: str) -> dict:
    """gunluk.jsonl'daki `kapi_golge` olayları kapı adına göre sayılır (ADR-0035: gölge modunun ölçümü)."""
    sayi: dict = {}
    for o in L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")):
        if isinstance(o, dict) and o.get("tur") == "kapi_golge" and o.get("kapi"):
            sayi[o["kapi"]] = sayi.get(o["kapi"], 0) + 1
    return dict(sorted(sayi.items()))


CIKTI_ORNEK = 200  # ihlal geçişi kararı için en az tur (ADR-0075, plan K6)
CIKTI_HEDEF = {"ortanca": 400, "p90": 800}


def _cikti(sd: str):
    """gunluk.jsonl'daki `cikti_olcum` turlarından kullanıcı çıktısı ölçümü (ADR-0075): ortanca, p90, aşım oranı.
    Karar: ≥200 turda ortanca ≤400 ve p90 ≤800 ise hedef tutuyor; değilse ihlal geçişi önerilir. Veri yoksa None."""
    toplam, kapanis = [], []
    for o in L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")):
        if isinstance(o, dict) and o.get("tur") == "cikti_olcum" and isinstance(o.get("toplam"), int):
            toplam.append(o["toplam"])
            if isinstance(o.get("kapanis"), int):
                kapanis.append(o["kapanis"])
    if not toplam:
        return None

    def q(v, p):
        v = sorted(v)
        return v[min(len(v) - 1, int(len(v) * p))]

    try:
        import cikti_butce
        sinir = cikti_butce.ayar_oku(sd).get("tur_siniri") or CIKTI_HEDEF["p90"]
    except Exception:
        sinir = CIKTI_HEDEF["p90"]
    n = len(toplam)
    ortanca, p90 = q(toplam, 0.5), q(toplam, 0.9)
    if n < CIKTI_ORNEK:
        karar = f"yetersiz örnek ({n}/{CIKTI_ORNEK}); karar verilmez"
    elif ortanca <= CIKTI_HEDEF["ortanca"] and p90 <= CIKTI_HEDEF["p90"]:
        karar = "hedef tutuyor; gölgede kalır"
    else:
        karar = "hedef tutmuyor; ihlal geçişi önerilir"
    return {"tur": n, "ortanca": ortanca, "p90": p90, "asim_orani": sum(1 for t in toplam if t > sinir) / n,
            "kapanis_tur": len(kapanis), "kapanis_ortanca": q(kapanis, 0.5) if kapanis else None, "karar": karar}


YONTEM_ESIK = 30  # kol başına denetimli bağımsız plan sayısı (ADR-0068, plan §7)


def fisher_tek_yonlu(a: int, b: int, c: int, d: int) -> float:
    """Tek yönlü Fisher kesin sınama: [[a, b], [c, d]] (satır 1 = yöntem kolu: başarılı, başarısız; satır 2 = kontrol).
    P(yöntem kolunda başarılı sayısı >= a), hipergeometrik."""
    n1, k, n = a + b, a + c, a + b + c + d
    if n == 0:
        return 1.0
    pay = sum(math.comb(k, i) * math.comb(n - k, n1 - i) for i in range(a, min(n1, k) + 1))
    return pay / math.comb(n, n1)


def _yontem(sd: str) -> dict:
    """ADR-0068 etki ölçümü (gunluk.jsonl): enjeksiyon sayıları ve oturum başına ilk planın kolu. Birim: oturum başına ilk
    `bic_ilk`; başarı: o işin ilk `bic_denetim_ilk` kaydında dört sorunun hepsi ✔."""
    enj = {"yontem": 0, "kontrol": 0}
    ilk: dict = {}
    denetim: dict = {}
    for o in L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")):
        if not isinstance(o, dict):
            continue
        t = o.get("tur")
        if t == "yontem_enjekte" and o.get("kol") in enj:
            enj[o["kol"]] += 1
        elif t == "bic_ilk" and o.get("kol") in enj:
            ilk.setdefault(o.get("oturum") or o.get("is"), o)
        elif t == "bic_denetim_ilk":
            denetim.setdefault(o.get("is"), o)
    kol = {k: {"plan": 0, "denetimli": 0, "ok": 0} for k in enj}
    for o in ilk.values():
        s = kol[o["kol"]]
        s["plan"] += 1
        d = denetim.get(o.get("is"))
        if d:
            s["denetimli"] += 1
            s["ok"] += 1 if d.get("hepsi_ok") else 0
    y, c = kol["yontem"], kol["kontrol"]
    p = fisher_tek_yonlu(y["ok"], y["denetimli"] - y["ok"], c["ok"], c["denetimli"] - c["ok"]) if y["denetimli"] and c["denetimli"] else None
    return {"enjeksiyon": enj, "kol": kol, "p": p, "esik": YONTEM_ESIK,
            "karar_zamani": y["denetimli"] >= YONTEM_ESIK and c["denetimli"] >= YONTEM_ESIK}


def _yontem_satirlari(y: dict) -> list:
    if not y or (not any(y["enjeksiyon"].values()) and not any(v["plan"] for v in y["kol"].values())):
        return []
    yk, ck = y["kol"]["yontem"], y["kol"]["kontrol"]
    oran = lambda s: "-" if not s["denetimli"] else f"{s['ok']}/{s['denetimli']} (%{100 * s['ok'] / s['denetimli']:.0f})"  # noqa: E731
    satirlar = [
        f"yöntem enjeksiyonu (ADR-0068): günlük satırı yöntem {y['enjeksiyon']['yontem']}, kontrol {y['enjeksiyon']['kontrol']}",
        f"  bağımsız plan (oturum başına ilk): yöntem {yk['plan']}, kontrol {ck['plan']}; denetimli: yöntem {yk['denetimli']}, kontrol {ck['denetimli']}",
        f"  dört soru ilk denetimde ✔: yöntem {oran(yk)}, kontrol {oran(ck)}"
        + ("" if y["p"] is None else f"; Fisher tek yönlü p={y['p']:.4f}"),
    ]
    if y["karar_zamani"]:
        satirlar.append(f"  karar zamanı: her kolda {y['esik']} denetimli plana ulaşıldı; p<0,05 ise etkili, değilse kanıtlanamadı; "
                        "kontrol payını 0'a çek (`ayarlar/yontem_enjeksiyonu.json` kontrol_payi)")
    else:
        satirlar.append(f"  karar için her kolda {y['esik']} denetimli plan gerekir (şimdi yöntem {yk['denetimli']}, kontrol {ck['denetimli']})")
    return satirlar


def _kapi_ret(sd: str) -> dict:
    """gunluk.jsonl'daki `kapi_ret` olayları (ihlal modundaki ret) kapı adına göre sayılır (ADR-0069: yanlış pozitif ölçümünün paydası)."""
    sayi: dict = {}
    for o in L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")):
        if isinstance(o, dict) and o.get("tur") == "kapi_ret" and o.get("kapi"):
            sayi[o["kapi"]] = sayi.get(o["kapi"], 0) + 1
    return dict(sorted(sayi.items()))


def rapor(sd: str) -> dict:
    v = _veri(sd)
    mal, zam, isler, kartlar = v["mal"], v["zam"], v["isler"], v["kartlar"]
    ids = set(isler) | {r["_is"] for r in mal} | {r["_is"] for r in zam}
    ids |= {_is_id(k.get("is")) for k in kartlar if k.get("is")}
    sirali = _sirala(ids) + ([KOVA] if KOVA in ids else [])
    satirlar = []
    for i in sirali:
        m = [r for r in mal if r["_is"] == i]
        z = [r for r in zam if r["_is"] == i]
        t = iz.toplam(m)
        gunler = sorted(g for g in (_gun(r) for r in m + z) if g)
        oturum = {r.get("oturum") for r in m + z if r.get("oturum")}
        kayit = isler.get(i) if isinstance(isler.get(i), dict) else {}
        biten, toplam = _todo(kayit.get("klasor"))
        satirlar.append({
            "is": i,
            "baslik": KOVA_BASLIK if i == KOVA else (kayit.get("baslik") or ""),
            "usd": round(t["usd"], 6),
            "token": t["token"],
            "claude_sn": sum(_sayi(r.get("sure_ms")) for r in z if r.get("tur") == "ana") / 1000,
            "alt_sn": sum(_sayi(r.get("sure_ms")) for r in z if r.get("tur") == "alt") / 1000,
            "oturum": len(oturum),
            "kart": sum(1 for k in kartlar if k.get("is") == i),
            "todo_biten": biten,
            "todo_toplam": toplam,
            "ilk": gunler[0] if gunler else None,
            "son": gunler[-1] if gunler else None,
        })
    toplam_usd = sum(s["usd"] for s in satirlar)
    kova_usd = sum(s["usd"] for s in satirlar if s["is"] == KOVA)
    biten_t = sum(s["todo_biten"] for s in satirlar)
    toplam_tok = sum(s["token"] for s in satirlar)
    kova_tok = sum(s["token"] for s in satirlar if s["is"] == KOVA)
    ret, karar = L.ret_onay_say(kartlar)  # iptal kartlar hariç: KPI ret_orani ile aynı tanım
    gir = sum(_sayi(r.get("giris")) for r in mal)
    oku = sum(_sayi(r.get("onbellek_okuma")) for r in mal)
    yaz = sum(_sayi(r.get("onbellek_yazma")) for r in mal)
    kalite = {
        "todo_basina_usd": (toplam_usd - kova_usd) / biten_t if biten_t else None,
        "todo_basina_token": (toplam_tok - kova_tok) / biten_t if biten_t else None,   # I-064: token eşi
        "ret_orani": ret / karar if karar else None,
        "onbellek_isabet": oku / (gir + oku + yaz) if (gir + oku + yaz) else None,
        "baglanmamis_emek_yuzde": 100 * kova_usd / toplam_usd if toplam_usd else 0,
    }
    return {"satirlar": satirlar, "kalite": kalite, "kapi_golge": _kapi_golge(sd), "kapi_ret": _kapi_ret(sd), "yontem": _yontem(sd),
            "cikti": _cikti(sd)}


def paralellik_olcumu(sd: str, is_id: str, klasor: str | None, kart_is: dict | None = None,
                      zaman_satirlari: list | None = None) -> dict:
    """Planlanan ve gerçekleşen paralellik, aynı birimde: ortalama eşzamanlı iş sayısı (ADR-0080, S6, K6).
    planlanan = paralellik.analiz(plan.md)['planlanan_agirlikli']; gerçekleşen = metrikler.isci_eszamanlilik;
    oran = gerçekleşen ÷ planlanan. Ölçülemeyen değer None ve `neden` alanında gerekçe. Kapanış kapısı da bunu kullanır."""
    import metrikler as MT
    import paralellik as PAR
    planlanan, neden = None, []
    plan = os.path.join(klasor, "plan.md") if isinstance(klasor, str) and klasor else None
    if plan and os.path.exists(plan):
        try:
            with open(plan, encoding="utf-8") as f:
                planlanan = PAR.analiz(f.read(), ileri_yasak=False)["planlanan_agirlikli"] or None
        except OSError:
            planlanan = None
        if planlanan is None:
            neden.append("planlanan ölçülemedi (plan.md'de P maddesi yok ya da bağımlılık döngüsü)")
    else:
        neden.append("planlanan ölçülemedi (plan.md yok)")
    if zaman_satirlari is None:
        zaman_satirlari = L.zaman_kayitlari(sd)
    g = MT.isci_eszamanlilik(is_id, zaman_satirlari, kart_is)
    if g["deger"] is None:
        neden.append("gerçekleşen ölçülemedi (işçi ajanı kaydı yok)")
    oran = round(g["deger"] / planlanan, 3) if planlanan and g["deger"] is not None else None
    return {"birim": "ortalama eşzamanlı iş sayısı", "planlanan": planlanan, "gerceklesen": g["deger"], "oran": oran,
            "isci": g, "neden": neden}


def paralellik_satiri(p: dict | None) -> str:
    """`orkestra is rapor <iş>` satırı: planlanan ve gerçekleşen aynı birimde, oran ve `ajan: ?` payı."""
    if not p:
        return "paralellik: ölçülemedi"
    f = lambda x: "ölçülemedi" if x is None else f"{x:.2f}"  # noqa: E731
    b = p["isci"]["bilinmeyen"]
    pay = "-" if b["pay"] is None else f"{b['kayit']}/{p['isci']['alt_kayit']} kayıt (%{100 * b['pay']:.0f})"
    s = (f"paralellik ({p['birim']}, yalnız işçi ajanları): planlanan {f(p['planlanan'])}, gerçekleşen {f(p['gerceklesen'])}, "
         f"oran (gerçekleşen ÷ planlanan) {f(p['oran'])}; işçi kaydı {p['isci']['isci_kayit']}; ajan:? payı {pay}")
    return s + ("" if not p["neden"] else " — " + "; ".join(p["neden"]))


def detay(sd: str, is_id: str):
    v = _veri(sd)
    i = _is_id(is_id)
    m = [r for r in v["mal"] if r["_is"] == i]
    z = [r for r in v["zam"] if r["_is"] == i]
    if not m and not z and i not in v["isler"] and not any(k.get("is") == i for k in v["kartlar"]):
        return None
    kayit = v["isler"].get(i) if isinstance(v["isler"].get(i), dict) else {}
    kart_is = {k["id"]: k.get("is") for k in v["kartlar"] if k.get("id") and k.get("is")}
    try:
        par = paralellik_olcumu(sd, i, kayit.get("klasor"), kart_is, v["zam"])
    except Exception:
        par = None
    og: dict = {}
    for r in m + z:
        a = og.setdefault((r.get("oturum") or "-", _gun(r) or "-"),
                          {"oturum": r.get("oturum") or "-", "gun": _gun(r) or "-", "usd": 0.0, "token": 0,
                           "claude_sn": 0.0, "alt_sn": 0.0})
        if "maliyet_usd" in r or "giris" in r:
            a["usd"] += _sayi(r.get("maliyet_usd"))
            a["token"] += _token(r)
        if r.get("tur") in ("ana", "alt") and "sure_ms" in r:
            a["claude_sn" if r["tur"] == "ana" else "alt_sn"] += _sayi(r.get("sure_ms")) / 1000
    kr: dict = {}
    for r in m:
        a = kr.setdefault((r.get("surec") or "-", r.get("ajan") or "-", r.get("model") or "-"),
                          {"surec": r.get("surec") or "-", "ajan": r.get("ajan") or "-",
                           "model": r.get("model") or "-", "usd": 0.0, "token": 0})
        a["usd"] += _sayi(r.get("maliyet_usd"))
        a["token"] += _token(r)
    return {"is": i, "oturum_gun": [og[k] for k in sorted(og)],
            "kirilim": sorted(kr.values(), key=lambda x: -x["usd"]), "paralellik": par}


def csv_metni(r: dict) -> str:
    cikti = io.StringIO()
    w = csv.writer(cikti, lineterminator="\n")
    w.writerow(CSV_BASLIK)
    for s in r["satirlar"]:
        w.writerow([("" if s[a] is None else s[a]) for a in CSV_BASLIK])
    return cikti.getvalue()


def _tablo(basliklar, satirlar) -> str:
    sat = [[str(x) for x in s] for s in satirlar]
    gen = [max(len(b), *(len(s[i]) for s in sat)) if sat else len(b) for i, b in enumerate(basliklar)]
    cizgi = lambda s: "  ".join(x.ljust(gen[i]) for i, x in enumerate(s)).rstrip()  # noqa: E731
    return "\n".join([cizgi(basliklar)] + [cizgi(s) for s in sat])


def _sure(sn: float) -> str:
    sn = int(round(sn))
    return f"{sn // 3600}s{sn % 3600 // 60:02d}d" if sn >= 3600 else f"{sn // 60}d{sn % 60:02d}s"


def _oran(v, yuzde=False) -> str:
    if v is None:
        return "-"
    return f"{v * 100:.1f}%" if not yuzde else f"{v:.1f}%"


def metin(r: dict) -> str:
    if not r["satirlar"]:
        govde = "iş yok"
    else:
        govde = _tablo(
            ["iş", "başlık", "USD", "token", "claude", "alt ajan", "oturum", "kart", "todo", "ilk", "son"],
            [[s["is"], s["baslik"], f"{s['usd']:.2f}", s["token"], _sure(s["claude_sn"]), _sure(s["alt_sn"]),
              s["oturum"], s["kart"], f"{s['todo_biten']}/{s['todo_toplam']}", s["ilk"] or "-", s["son"] or "-"]
             for s in r["satirlar"]])
    k = r["kalite"]
    td = "-" if k["todo_basina_usd"] is None else f"{k['todo_basina_usd']:.2f}"
    tt = "-" if k["todo_basina_token"] is None else f"{k['todo_basina_token']:,.0f}"
    golge = r.get("kapi_golge") or {}
    golge_satiri = ["gölge kapı uyarıları: " + ", ".join(f"{k} {n}" for k, n in golge.items())] if golge else []
    ret = r.get("kapi_ret") or {}
    ret_satiri = ["kapı retleri (ihlal modu): " + ", ".join(f"{k} {n}" for k, n in ret.items())] if ret else []
    c = r.get("cikti")
    cikti_satiri = [] if not c else [
        f"kullanıcı çıktısı ({c['tur']} tur): ortanca {c['ortanca']}, p90 {c['p90']} karakter, aşım oranı {_oran(c['asim_orani'])}"
        + ("" if c["kapanis_ortanca"] is None else f", kutudan sonraki kapanış ortanca {c['kapanis_ortanca']} ({c['kapanis_tur']} tur)")
        + f" — {c['karar']}"]
    return "\n".join([
        govde, "",
        *golge_satiri,
        *ret_satiri,
        *cikti_satiri,
        *_yontem_satirlari(r.get("yontem")),
        f"kapanan todo başına USD: {td}",
        f"kapanan todo başına token: {tt}",
        f"ret oranı: {_oran(k['ret_orani'])}",
        f"önbellek isabeti: {_oran(k['onbellek_isabet'])}",
        f"işe bağlanmamış emek: {_oran(k['baglanmamis_emek_yuzde'], True)}",
    ])


def metin_detay(d) -> str:
    if not d:
        return "iş yok"
    og = _tablo(["oturum", "gün", "USD", "token", "claude", "alt ajan"],
                [[x["oturum"], x["gun"], f"{x['usd']:.2f}", x["token"], _sure(x["claude_sn"]), _sure(x["alt_sn"])]
                 for x in d["oturum_gun"]])
    kr = _tablo(["süreç", "ajan", "model", "USD", "token"],
                [[x["surec"], x["ajan"], x["model"], f"{x['usd']:.2f}", x["token"]] for x in d["kirilim"]])
    return (f"{d['is']}\n\noturum x gün\n{og}\n\nsüreç x ajan x model\n{kr}\n\n"
            + paralellik_satiri(d.get("paralellik")))
