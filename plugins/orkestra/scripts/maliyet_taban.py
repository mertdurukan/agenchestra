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


def _ilk_zaman(yol: str):
    for o in _satirlar(yol):
        z = o.get("timestamp")
        if z:
            try:
                return datetime.datetime.fromisoformat(str(z).replace("Z", "+00:00")).astimezone()
            except ValueError:
                return None
    return None


def dosyalar(dizin: str, gun: float, sonra: datetime.datetime | None = None) -> list[str]:
    """Son `gun` günde değişen oturum dosyaları; `sonra` verilirse yalnız ilk kaydı o andan sonra olanlar (değişiklik sonrası oturumlar)."""
    esik = time.time() - gun * 86400
    d = sorted(f for f in glob.glob(os.path.join(dizin, "*.jsonl")) if os.path.getmtime(f) >= esik)
    if sonra is None:
        return d
    return [f for f in d if (z := _ilk_zaman(f)) and z >= sonra]


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


def taban_bolumu(dizin: str, gun: float, sonra=None) -> dict:
    satir = []
    for f in dosyalar(dizin, gun, sonra):
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


def esik_bolumu(dizin: str, gun: float, esikler=ESIKLER, sonra=None) -> dict:
    tablo = L.fiyat_tablosu()
    cag, oturum_max = [], []
    for f in dosyalar(dizin, gun, sonra):
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
            "baglam_p90": ctx[int(n * .9)], "esikler": satirlar, "okuma_fiyat_toplam": sum(c[2] for c in cag)}


def _kullanici_istegi(o: dict) -> bool:
    """Gerçek kullanıcı mesajı (araç sonucu, yan zincir, meta ve sıkıştırma özeti değil): yeni istek başlatır."""
    if o.get("type") != "user" or o.get("isSidechain") or o.get("isMeta") or o.get("isCompactSummary"):
        return False
    c = (o.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip())
    blok = [x for x in (c or []) if isinstance(x, dict)]
    return any(x.get("type") == "text" for x in blok) and not any(x.get("type") == "tool_result" for x in blok)


def istekler(yol: str, tablo: dict) -> dict:
    """Ana zincir istekleri (kullanıcı mesajından bir sonrakine): [usd, araç çağrısı, API çağrısı] listesi, sıkıştırma olayı sayısı
    ve model başına çağrı sayısı. Kullanım transkriptten (kesin); aynı mesajın sonraki blokları araçları toplar, çıkışın en büyüğü alınır."""
    ist, mesaj, sikis, modeller = [], {}, 0, {}
    for o in _satirlar(yol):
        if o.get("subtype") == "compact_boundary":
            sikis += 1
            continue
        if _kullanici_istegi(o):
            ist.append([0.0, 0, 0])
            continue
        m = o.get("message") or {}
        u = m.get("usage")
        if o.get("type") != "assistant" or not u or o.get("isSidechain"):
            continue
        if not ist:
            ist.append([0.0, 0, 0])
        araclar = sum(1 for c in (m.get("content") or []) if isinstance(c, dict) and c.get("type") == "tool_use")
        mid = m.get("id") or o.get("uuid")
        r = mesaj.get(mid)
        if r is None:
            usd = L.kullanim_maliyeti(m.get("model") or "", u, tablo)
            mesaj[mid] = r = {"i": ist[-1], "u": dict(u), "model": m.get("model") or "", "usd": usd}
            ist[-1][0] += usd
            ist[-1][2] += 1
            modeller[r["model"]] = modeller.get(r["model"], 0) + 1
        elif (u.get("output_tokens") or 0) > (r["u"].get("output_tokens") or 0):
            r["u"]["output_tokens"] = u["output_tokens"]
            yeni = L.kullanim_maliyeti(r["model"], r["u"], tablo)
            r["i"][0] += yeni - r["usd"]
            r["usd"] = yeni
        r["i"][1] += araclar
    return {"istekler": [i for i in ist if i[2]], "sikistirma": sikis, "modeller": modeller}


def _pay(grup: list, toplam: float) -> dict:
    usd = sum(i[0] for i in grup)
    return {"adet": len(grup), "usd": usd, "pay": usd / toplam if toplam else 0.0}


def istek_bolumu(dizin: str, gun: float, sonra=None) -> dict:
    """İstek dağılımı (kesin kullanım): sayı, medyan/p90, 50+ ve 100+ araç çağrılı isteklerin adedi ve ücret payı, en pahalı 10 istek,
    pencerede transkriptte görülen sıkıştırma olayı ve oturum sayısı."""
    tablo = L.fiyat_tablosu()
    hepsi, sikis, sikis_oturum, modeller = [], 0, 0, {}
    for f in dosyalar(dizin, gun, sonra):
        r = istekler(f, tablo)
        hepsi += r["istekler"]
        sikis += r["sikistirma"]
        sikis_oturum += 1 if r["sikistirma"] else 0
        for k, v in r["modeller"].items():
            modeller[k] = modeller.get(k, 0) + v
    if not hepsi:
        return {"istek": 0, "sikistirma": sikis, "sikistirma_oturum": sikis_oturum}
    usd = sorted(i[0] for i in hepsi)
    top = sum(usd)
    return {"istek": len(hepsi), "toplam_usd": top, "medyan_usd": statistics.median(usd), "p90_usd": usd[int(len(usd) * .9)],
            "kucuk": _pay([i for i in hepsi if i[1] <= 3], top), "agir50": _pay([i for i in hepsi if i[1] >= 50], top),
            "agir100": _pay([i for i in hepsi if i[1] >= 100], top),
            "en_pahali": [{"usd": i[0], "arac": i[1], "api": i[2]} for i in sorted(hepsi, key=lambda i: -i[0])[:10]],
            "sikistirma": sikis, "sikistirma_oturum": sikis_oturum,
            "baskin_model": max(modeller.items(), key=lambda kv: kv[1])[0] if modeller else ""}


def sikistirma_gunluk(sd: str, basla: str) -> int:
    """gunluk.jsonl'daki `sikistirma` olay satırları (pre_compact kancası yazar); `basla` (YYYY-MM-DD) ve sonrası."""
    n = 0
    try:
        with open(os.path.join(sd, "gunluk.jsonl"), encoding="utf-8", errors="replace") as h:
            for s in h:
                if '"sikistirma"' not in s:
                    continue
                try:
                    r = json.loads(s)
                except ValueError:
                    continue
                if r.get("tur") == "sikistirma" and str(r.get("zaman"))[:10] >= basla:
                    n += 1
    except OSError:
        pass
    return n


def onek_maliyeti(taban: dict, esik: dict, istek: dict) -> dict | None:
    """Önekte (sabit açılış bağlamı) her 1000 token'ın pencere maliyeti: her çağrıda okunur + oturum ve sıkıştırma başına bir kez yazılır
    (1 saatlik yazma tarifesi, baskın model). Veri yoksa None."""
    if not taban.get("oturum") or not esik.get("cagri"):
        return None
    f = L.model_fiyati(istek.get("baskin_model") or "")
    okuma = esik["okuma_fiyat_toplam"] / 1000
    yazma = (taban["oturum"] + istek.get("sikistirma", 0)) * f["onbellek_yazma_1sa"] / 1000
    return {"bin_token_usd": okuma + yazma, "okuma": okuma, "yazma": yazma, "yazma_adedi": taban["oturum"] + istek.get("sikistirma", 0)}


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


def hesapla(sd: str, dizin: str, gun: float, basla: str, sonra=None) -> dict:
    taban, esik, istek = taban_bolumu(dizin, gun, sonra), esik_bolumu(dizin, gun, sonra=sonra), istek_bolumu(dizin, gun, sonra)
    istek["sikistirma_gunluk"] = sikistirma_gunluk(sd, basla)
    return {"olcum": datetime.datetime.now().isoformat(timespec="minutes"), "gun": gun, "sonra": sonra.isoformat(timespec="minutes") if sonra else None,
            "taban": taban, "esik": esik, "istek": istek, "onek": onek_maliyeti(taban, esik, istek), "is_basina": is_basina_bolumu(sd, basla)}


def metin(r: dict) -> str:
    s = [f"ölçüm {r['olcum']}; pencere son {r['gun']:g} gün (transkript)" + (f", yalnız {r['sonra']} sonrası başlayan oturumlar" if r.get("sonra") else "") + ", liste fiyatı", ""]
    t = r["taban"]
    if not t.get("oturum"):
        s.append("taban: oturum yok")
    else:
        o = r.get("onek")
        s += [f"## Taban: {t['oturum']} oturum; ilk çağrı bağlamı medyan {t['ilk_medyan']}, p90 {t['ilk_p90']} token", "",
              "| kalem | medyan karakter | token (merkez) | aralık | kalibrasyon |" + (" pencere $ (merkez) |" if o else ""),
              "|---|---|---|---|---|" + ("---|" if o else "")]
        for k in t["kalemler"]:
            s.append(f"| {k['kalem']} | {k['karakter']} | {k['token']} | {k['token_alt']} – {k['token_ust']} | {'var' if k['kalibre'] else 'genel bant'} |"
                     + (f" {k['token'] / 1000 * o['bin_token_usd']:.2f}$ |" if o else ""))
        if o:
            s += ["", f"Önekte her 1000 token pencerede {o['bin_token_usd']:.2f}$ (okuma {o['okuma']:.2f}$ + {o['yazma_adedi']} yazma {o['yazma']:.2f}$; "
                      "yazma = oturum + sıkıştırma, 1 saatlik tarife, baskın model; kalibrasyonsuz kalemlerin $ değeri bant ortasıdır, tahmindir)."]
    e = r["esik"]
    if e.get("cagri"):
        s += ["", f"## Eşikler: {e['cagri']} çağrı, {e['oturum']} oturum; liste maliyeti {e['toplam_usd']:.2f}$; bağlam medyan {e['baglam_medyan']}, p90 {e['baglam_p90']}", "",
              "| eşik | aşan çağrı | ücret payı | aşan oturum | devir kazancı üst sınırı $ |", "|---|---|---|---|---|"]
        for x in e["esikler"]:
            s.append(f"| {x['esik'] // 1000} bin | {x['cagri']} (%{100 * x['cagri_orani']:.1f}) | {x['usd']:.2f}$ (%{100 * x['usd_payi']:.1f}) | {x['oturum']} (%{100 * x['oturum_orani']:.1f}) | {x['devir_kazanc_ust_sinir']:.2f} |")
    q = r.get("istek")
    if q and q.get("istek"):
        s += ["", f"## İstek dağılımı (kaynak: transkript, kesin kullanım; zaman.jsonl token alanları tahmindir, burada kullanılmaz): {q['istek']} istek, "
                  f"toplam {q['toplam_usd']:.2f}$, medyan {q['medyan_usd']:.2f}$, p90 {q['p90_usd']:.2f}$", "",
              "| grup | istek | ücret | pay |", "|---|---|---|---|"]
        for ad, g in (("<=3 araç çağrılı istek", q["kucuk"]), ("50+ araç çağrılı istek", q["agir50"]), ("100+ araç çağrılı istek", q["agir100"])):
            s.append(f"| {ad} | {g['adet']} | {g['usd']:.2f}$ | %{100 * g['pay']:.1f} |")
        s += ["", "En pahalı 10 istek: " + "; ".join(f"{x['usd']:.2f}$ ({x['arac']} araç, {x['api']} API çağrısı)" for x in q["en_pahali"])]
    if q is not None:
        s += ["", f"Sıkıştırma (compact): transkriptte {q['sikistirma']} olay / {q['sikistirma_oturum']} oturum; gunluk.jsonl'da {q.get('sikistirma_gunluk', 0)} olay satırı "
                  "(kanca kurulumundan sonrası; fark = kancadan önceki olaylar)."]
    i = r["is_basina"]
    s += ["", f"## İş başına $ ({i['basla']}..şimdi): defter {i['toplam_usd']:.2f}$, iş-bağlı {i['is_bagli_usd']:.2f}$"]
    s.append(f"- A (kapanan iş başına): {i['kapanan_is']} iş" + (f" -> {i['a_usd']:.2f}$/iş" if i["a_usd"] is not None else ""))
    s.append(f"- B (teslim kart başına, ret/israf göstergesi): {i['teslim_kart']} kart" + (f" -> {i['b_usd']:.2f}$/kart, ret yiyen %{100 * i['ret_orani']:.0f}" if i["b_usd"] is not None else ""))
    return "\n".join(s)
