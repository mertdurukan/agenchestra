"""Açılış bağlamı tabanı ölçümü (`orkestra maliyet taban`): salt okuma, model çağırmaz, içerik yazmaz (yalnız boyut ve sayı).

Üç bölüm:
1. Taban: oturumların ilk API çağrısı bağlamı ve kalem dökümü (transkriptteki 'attachment' kayıtlarının karakter boyu).
2. Eşik tablosu: çağrı başına bağlamın eşikleri aştığı çağrı/oturum oranı, ücret payı, devir kazancı ÜST SINIRI.
3. İş başına $: işe bağlı harcama / kapanan iş (A) ve teslim edilen kart başına harcama + ret payı (B).

Token oranları ayarlar/taban_oranlari.json'dadır (kalibrasyon: merkez ve %95 aralık); kalibre edilmemiş kalemler genel bantla gösterilir.
Fiyat: bin/fiyat.json liste fiyatı (abonelikte gerçek fatura değildir).
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import statistics
import time

import ork_lib as L

ESIKLER = (100_000, 150_000, 200_000)
KALEMLER = ["sistem istemi", "kural dosyaları", "skill listesi", "ertelenmiş araç adları", "ajan listesi",
            "MCP yönergeleri", "hook ek bağlamı", "oturum bağlamı", "ortam ve model", "ilk kullanıcı mesajı"]
_ORAN_YOLU = os.path.join(L.PLUGIN_ROOT, "ayarlar", "taban_oranlari.json")
_ORAN_VARSAYILAN = {"genel": [0.30, 0.545], "kalemler": {"kural dosyaları": [0.447, 0.385, 0.520]}}


def oranlar() -> dict:
    try:
        with open(_ORAN_YOLU, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return _ORAN_VARSAYILAN


def boy(v) -> int:
    """Değerin karakter boyu: iç içe metinlerin uzunlukları toplamı (JSON kaçışı sayılmaz)."""
    if isinstance(v, str):
        return len(v)
    if isinstance(v, list):
        return sum(boy(x) for x in v)
    if isinstance(v, dict):
        return sum(boy(x) for x in v.values())
    return 0


def baglam(u: dict) -> int:
    return (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + (u.get("input_tokens") or 0)


def _satirlar(yol: str):
    with open(yol, encoding="utf-8", errors="replace") as h:
        for s in h:
            try:
                yield json.loads(s)
            except ValueError:
                continue


def dosyalar(dizin: str, gun: float) -> list[str]:
    esik = time.time() - gun * 86400
    return sorted(f for f in glob.glob(os.path.join(dizin, "*.jsonl")) if os.path.getmtime(f) >= esik)


_SINIF = {"prompt_snapshot": ("sistem istemi", "systemPrompt"), "skill_listing": ("skill listesi", "content"),
          "deferred_tools_delta": ("ertelenmiş araç adları", "addedLines"), "agent_listing_delta": ("ajan listesi", "addedLines"),
          "mcp_instructions_delta": ("MCP yönergeleri", "addedBlocks"), "hook_additional_context": ("hook ek bağlamı", "content"),
          "session_context": ("oturum bağlamı", "context")}


def _kalem(a: dict):
    t = a.get("type")
    if t == "instructions":
        return "kural dosyaları", boy([f.get("content") for f in a.get("files", [])])
    if t in _SINIF:
        k, alan = _SINIF[t]
        return k, boy(a.get(alan))
    if t in ("environment", "model"):
        return "ortam ve model", boy({k: v for k, v in a.items() if k != "type"})
    return None, 0


def oturum_taban(yol: str):
    """(kalem karakterleri, ilk çağrı bağlamı); ilk assistant çağrısından önceki kayıtlar sayılır."""
    kalem = {k: 0 for k in KALEMLER}
    for o in _satirlar(yol):
        m = o.get("message") or {}
        if o.get("type") == "assistant" and m.get("usage") and not o.get("isSidechain"):
            return kalem, baglam(m["usage"])
        a = o.get("attachment")
        if isinstance(a, dict):
            k, n = _kalem(a)
            if k:
                kalem[k] += n
        elif o.get("type") == "user" and not o.get("isSidechain"):
            c = m.get("content")
            kalem["ilk kullanıcı mesajı"] += boy(c if isinstance(c, str) else [x for x in (c or []) if isinstance(x, dict) and x.get("type") == "text"])
    return kalem, None


def cagrilar(yol: str, tablo: dict) -> list[tuple]:
    """Ana zincir çağrıları (mesaj kimliği bir kez): (bağlam, tam kullanım usd, okuma fiyatı $/M)."""
    gorulen, out = set(), []
    for o in _satirlar(yol):
        m = o.get("message") or {}
        u = m.get("usage")
        if o.get("type") != "assistant" or not u or o.get("isSidechain"):
            continue
        mid = m.get("id") or o.get("uuid")
        if mid in gorulen:
            continue
        gorulen.add(mid)
        f = L.model_fiyati(m.get("model"), tablo)
        cc = u.get("cache_creation") or {}
        cw5, cw1 = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
        if cw5 is None and cw1 is None:
            cw5, cw1 = u.get("cache_creation_input_tokens", 0) or 0, 0
        usd = ((u.get("input_tokens", 0) or 0) * f["giris"] + (u.get("output_tokens", 0) or 0) * f["cikis"]
               + (u.get("cache_read_input_tokens", 0) or 0) * f["onbellek_okuma"]
               + (cw5 or 0) * f["onbellek_yazma_5dk"] + (cw1 or 0) * f["onbellek_yazma_1sa"]) / 1e6
        out.append((baglam(u), usd, f["onbellek_okuma"]))
    return out


def taban_bolumu(dizin: str, gun: float) -> dict:
    satir = []
    for f in dosyalar(dizin, gun):
        kalem, ilk = oturum_taban(f)
        if ilk:
            satir.append((kalem, ilk))
    if not satir:
        return {"oturum": 0}
    ilkler = sorted(i for _, i in satir)
    med = statistics.median(ilkler)
    ort = oranlar()
    genel = ort["genel"]
    kalemler, toplam_orta = [], 0.0
    for k in KALEMLER:
        mk = statistics.median([s[k] for s, _ in satir])
        r = ort["kalemler"].get(k)
        orta, alt, ust = (r[0], r[1], r[2]) if r else ((genel[0] + genel[1]) / 2, genel[0], genel[1])
        kalemler.append({"kalem": k, "karakter": int(mk), "token": int(mk * orta), "token_alt": int(mk * alt),
                         "token_ust": int(mk * ust), "kalibre": bool(r)})
    return {"oturum": len(satir), "ilk_medyan": int(med), "ilk_p90": ilkler[int(len(ilkler) * .9)], "kalemler": kalemler}


def esik_bolumu(dizin: str, gun: float, esikler=ESIKLER) -> dict:
    tablo = L.fiyat_tablosu()
    cag, oturum_max = [], []
    for f in dosyalar(dizin, gun):
        c = cagrilar(f, tablo)
        cag += c
        if c:
            oturum_max.append(max(x[0] for x in c))
    if not cag:
        return {"cagri": 0}
    top = sum(c[1] for c in cag)
    ctx = sorted(c[0] for c in cag)
    n = len(cag)
    satirlar = []
    for e in esikler:
        ust = [c for c in cag if c[0] > e]
        usd = sum(c[1] for c in ust)
        satirlar.append({"esik": e, "cagri": len(ust), "cagri_orani": len(ust) / n, "usd": usd, "usd_payi": usd / top if top else 0,
                         "oturum": sum(1 for m in oturum_max if m > e), "oturum_orani": sum(1 for m in oturum_max if m > e) / len(oturum_max),
                         "devir_kazanc_ust_sinir": sum((c[0] - e) * c[2] for c in ust) / 1e6})
    return {"cagri": n, "oturum": len(oturum_max), "toplam_usd": top, "baglam_medyan": int(statistics.median(ctx)),
            "baglam_p90": ctx[int(n * .9)], "esikler": satirlar}


def is_basina_bolumu(sd: str, basla: str) -> dict:
    """A: pencerede kapanan iş başına iş-bağlı harcama. B: pencerede teslim edilen kart sayısı ve ret payı."""
    rs = [r for r in L.maliyet_kayitlari(sd) if str(r.get("zaman"))[:10] >= basla]
    usd = lambda r: r.get("maliyet_usd") or 0.0  # noqa: E731
    isli = [r for r in rs if r.get("is")]
    pay = sum(usd(r) for r in isli)
    sonuc = {"basla": basla, "toplam_usd": sum(usd(r) for r in rs), "is_bagli_usd": pay}
    kapanan = set()
    try:
        with open(os.path.join(sd, "isler.json"), encoding="utf-8") as f:
            isler = json.load(f)["isler"]
    except (OSError, ValueError, KeyError):
        isler = {}
    for iid, v in isler.items():
        if v.get("durum") != "kapandi":
            continue
        try:
            with open(os.path.join(v["klasor"], "is.json"), encoding="utf-8") as f:
                j = json.load(f)
        except (OSError, ValueError, KeyError):
            continue
        z = [g["zaman"] for g in j.get("gecmis", []) if g.get("olay") == "durum:kapandi"]
        if z and z[-1][:10] >= basla:
            kapanan.add(j.get("id") or iid)
    sonuc["kapanan_is"] = len(kapanan)
    sonuc["a_usd"] = pay / len(kapanan) if kapanan else None
    kart_usd: dict = {}
    for r in rs:
        g = r.get("gorev")
        if g and g != "-":
            kart_usd[g] = kart_usd.get(g, 0.0) + usd(r)
    teslim, ret = [], 0
    gd = os.path.join(sd, "gorevler")
    for f in (os.listdir(gd) if os.path.isdir(gd) else []):
        if not (f.startswith("G-") and f.endswith(".json")) or ".denetim" in f:
            continue
        try:
            with open(os.path.join(gd, f), encoding="utf-8") as h:
                x = json.load(h)
        except (OSError, ValueError):
            continue
        if not isinstance(x, dict) or x.get("durum") != "teslim":
            continue
        z = [g["zaman"] for g in x.get("gecmis", []) if g.get("olay") == "teslim"]
        if z and z[-1][:10] >= basla:
            gid = x.get("id") or f[:-5]
            teslim.append(gid)
            ret += any(d.get("karar") == "ret" for d in x.get("denetimler", []))
    sonuc["teslim_kart"] = len(teslim)
    sonuc["b_usd"] = sum(kart_usd.get(g, 0.0) for g in teslim) / len(teslim) if teslim else None
    sonuc["ret_orani"] = ret / len(teslim) if teslim else None
    return sonuc


def hesapla(sd: str, dizin: str, gun: float, basla: str) -> dict:
    return {"olcum": datetime.datetime.now().isoformat(timespec="minutes"), "gun": gun,
            "taban": taban_bolumu(dizin, gun), "esik": esik_bolumu(dizin, gun), "is_basina": is_basina_bolumu(sd, basla)}


def metin(r: dict) -> str:
    s = [f"ölçüm {r['olcum']}; pencere son {r['gun']:g} gün (transkript), liste fiyatı", ""]
    t = r["taban"]
    if not t.get("oturum"):
        s.append("taban: oturum yok")
    else:
        s += [f"## Taban: {t['oturum']} oturum; ilk çağrı bağlamı medyan {t['ilk_medyan']}, p90 {t['ilk_p90']} token", "",
              "| kalem | medyan karakter | token (merkez) | aralık | kalibrasyon |", "|---|---|---|---|---|"]
        for k in t["kalemler"]:
            s.append(f"| {k['kalem']} | {k['karakter']} | {k['token']} | {k['token_alt']} – {k['token_ust']} | {'var' if k['kalibre'] else 'genel bant'} |")
    e = r["esik"]
    if e.get("cagri"):
        s += ["", f"## Eşikler: {e['cagri']} çağrı, {e['oturum']} oturum; liste maliyeti {e['toplam_usd']:.2f}$; bağlam medyan {e['baglam_medyan']}, p90 {e['baglam_p90']}", "",
              "| eşik | aşan çağrı | ücret payı | aşan oturum | devir kazancı üst sınırı $ |", "|---|---|---|---|---|"]
        for x in e["esikler"]:
            s.append(f"| {x['esik'] // 1000} bin | {x['cagri']} (%{100 * x['cagri_orani']:.1f}) | {x['usd']:.2f}$ (%{100 * x['usd_payi']:.1f}) | {x['oturum']} (%{100 * x['oturum_orani']:.1f}) | {x['devir_kazanc_ust_sinir']:.2f} |")
    i = r["is_basina"]
    s += ["", f"## İş başına $ ({i['basla']}..şimdi): defter {i['toplam_usd']:.2f}$, iş-bağlı {i['is_bagli_usd']:.2f}$"]
    s.append(f"- A (kapanan iş başına): {i['kapanan_is']} iş" + (f" -> {i['a_usd']:.2f}$/iş" if i["a_usd"] is not None else ""))
    s.append(f"- B (teslim kart başına, ret/israf göstergesi): {i['teslim_kart']} kart" + (f" -> {i['b_usd']:.2f}$/kart, ret yiyen %{100 * i['ret_orani']:.0f}" if i["b_usd"] is not None else ""))
    return "\n".join(s)
