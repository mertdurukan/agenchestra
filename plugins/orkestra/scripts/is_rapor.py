"""İş başına maliyet/süre/kalite raporu (salt okuma). `orkestra is rapor` bunu kullanır.

Kaynaklar (sd = .claude/orkestra): maliyet.jsonl (yalnız ork_lib.maliyet_kayitlari), zaman.jsonl, isler.json,
iş klasörlerindeki todo.md, gorevler/G-*.json. 'is' değeri '-', boş ya da yoksa satır I-000 kovasına girer
(yalnız raporda; dosyalar değişmez).
"""
from __future__ import annotations

import csv
import io
import json
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
    isler = _json(os.path.join(sd, "isler.json")).get("isler")
    isler = isler if isinstance(isler, dict) else {}
    return {"mal": mal, "zam": zam, "isler": isler, "kartlar": kartlar}


def _kapi_golge(sd: str) -> dict:
    """gunluk.jsonl'daki `kapi_golge` olayları kapı adına göre sayılır (ADR-0035: gölge modunun ölçümü)."""
    sayi: dict = {}
    for o in L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")):
        if isinstance(o, dict) and o.get("tur") == "kapi_golge" and o.get("kapi"):
            sayi[o["kapi"]] = sayi.get(o["kapi"], 0) + 1
    return dict(sorted(sayi.items()))


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
    return {"satirlar": satirlar, "kalite": kalite, "kapi_golge": _kapi_golge(sd), "kapi_ret": _kapi_ret(sd)}


def detay(sd: str, is_id: str):
    v = _veri(sd)
    i = _is_id(is_id)
    m = [r for r in v["mal"] if r["_is"] == i]
    z = [r for r in v["zam"] if r["_is"] == i]
    if not m and not z and i not in v["isler"] and not any(k.get("is") == i for k in v["kartlar"]):
        return None
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
            "kirilim": sorted(kr.values(), key=lambda x: -x["usd"])}


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
    return "\n".join([
        govde, "",
        *golge_satiri,
        *ret_satiri,
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
    return f"{d['is']}\n\noturum x gün\n{og}\n\nsüreç x ajan x model\n{kr}"
