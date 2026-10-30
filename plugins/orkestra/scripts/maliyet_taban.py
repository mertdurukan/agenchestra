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
import random
import statistics
import time

import ork_lib as L

ESIKLER = (100_000, 150_000, 200_000)
DEVIR_BELGESI = (10_000, 5_000, 2_000)  # ADR-0034 / I-159 P4 varsayımı (ölçülmedi): devir belgesinin çıkış tokeni
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
    """Ana zincir çağrıları (mesaj kimliği bir kez): (bağlam, tam kullanım usd, okuma fiyatı $/M, çıkış fiyatı $/M, 1 saatlik yazma fiyatı $/M)."""
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
        out.append((baglam(u), usd, f["onbellek_okuma"], f["cikis"], f["onbellek_yazma_1sa"]))
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


def devir_net(oturumlar: list[list[tuple]], esik: int, yeni_taban: int, belge: int) -> tuple[int, float]:
    """ADR-0034 net devir kazancı: (devir olan oturum, net $). Devir noktası = bağlamın eşiği ilk aştığı çağrı; sonraki her çağrının bağlamı
    en çok (bağlam - yeni oturum tabanı) küçülür (brüt = küçülen bağlam x okuma fiyatı). Devir maliyeti = belge tokeni x çıkış fiyatı +
    yeni oturum tabanının (taban + belge) 1 saatlik yazımı. Oturum başına tek devir; belge boyutu varsayımdır."""
    devir, net = 0, 0.0
    for c in oturumlar:
        i = next((k for k, x in enumerate(c) if x[0] > esik), None)
        if i is None:
            continue
        devir += 1
        brut = sum(max(0, x[0] - yeni_taban) * x[2] for x in c[i + 1:]) / 1e6
        net += brut - (belge * c[i][3] + (yeni_taban + belge) * c[i][4]) / 1e6
    return devir, net


def esik_bolumu(dizin: str, gun: float, esikler=ESIKLER, sonra=None, yeni_taban: int | None = None) -> dict:
    tablo = L.fiyat_tablosu()
    cag, oturum_max, oturumlar = [], [], []
    for f in dosyalar(dizin, gun, sonra):
        c = cagrilar(f, tablo)
        cag += c
        if c:
            oturum_max.append(max(x[0] for x in c))
            oturumlar.append(c)
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
        if yeni_taban:
            satirlar[-1]["devir_net"] = {b: devir_net(oturumlar, e, yeni_taban, b) for b in DEVIR_BELGESI}
    return {"cagri": n, "oturum": len(oturum_max), "toplam_usd": top, "baglam_medyan": int(statistics.median(ctx)),
            "baglam_p90": ctx[int(n * .9)], "esikler": satirlar, "okuma_fiyat_toplam": sum(c[2] for c in cag)}


# Kullanıcının yazmadığı, çalışan işin devamı olan sistem mesajları yeni istek sayılmaz (arka plan görevi bildirimi, yerleşik komut çıktısı, kesinti notu).
_ISTEK_DISI = ("<task-notification", "<local-command", "<command-name>/", "[Request interrupted", "Task (from the session", "Caveat:")


def gunluk_asim(dizin: str, gun: float, esik: int = 200_000) -> dict:
    """Yerel gün -> {"n": ana zincir çağrısı, "asan": bağlamı eşiği aşan çağrı, "oturum_asan": {oturum dosyası: aşan çağrı}}. Kaynak: transkript zaman damgası."""
    out: dict = {}
    for f in dosyalar(dizin, gun):
        gorulen = set()
        for o in _satirlar(f):
            m = o.get("message") or {}
            u = m.get("usage")
            if o.get("type") != "assistant" or not u or o.get("isSidechain") or not o.get("timestamp"):
                continue
            mid = m.get("id") or o.get("uuid")
            if mid in gorulen:
                continue
            gorulen.add(mid)
            try:
                g = datetime.datetime.fromisoformat(str(o["timestamp"]).replace("Z", "+00:00")).astimezone().date()
            except ValueError:
                continue
            d = out.setdefault(g, {"n": 0, "asan": 0, "oturum_asan": {}})
            d["n"] += 1
            if baglam(u) > esik:
                d["asan"] += 1
                d["oturum_asan"][f] = d["oturum_asan"].get(f, 0) + 1
    return out


def _araligi(oranlar: list, tohum: int, tekrar: int = 2000) -> tuple:
    """Gün oranlarının ortalaması ve günler üzerinden bootstrap %95 aralığı (sabit tohum; kümeleme birimi gün, çünkü bir günün çağrıları bağımlıdır)."""
    rng = random.Random(tohum)
    ort = sorted(statistics.fmean(rng.choices(oranlar, k=len(oranlar))) for _ in range(tekrar))
    return statistics.fmean(oranlar), ort[int(0.025 * tekrar)], ort[int(0.975 * tekrar) - 1]


def uyari_etkisi(dizin: str, kesim: datetime.datetime, gun: float = 30, esik: int = 200_000, min_gun: int = 7,
                 min_cagri: int = 1000, min_fark: float = 0.05, tohum: int = 1, bugun: datetime.date | None = None) -> dict:
    """Devir uyarısı (kesim anı) öncesi/sonrası günlük "bağlamı eşiği aşan çağrı payı" karşılaştırması (ADR-0034 etki ölçümü).
    Kural (ölçümden ÖNCE sabit): her iki yanda >= `min_gun` tam gün (kesim günü ve bugün kısmi gün: dışarıda; çağrısı < `min_cagri` olan gün dışarıda);
    fark >= `min_fark` (5 puan) ve gün-bootstrap %95 aralıkları örtüşmüyorsa "etki var"; örtüşüyorsa ya da fark küçükse "etki görülmedi"; günler yetmezse "yetersiz veri".
    Karıştırıcı: aşan çağrıların oturumlara dağılımı (az sayıda uzun oturum günlük payı tek başına oynatır) ayrıca gösterilir."""
    bugun = bugun or datetime.date.today()
    kd = kesim.astimezone().date()
    gunler = gunluk_asim(dizin, gun, esik)
    yan = {"once": {}, "sonra": {}}
    elenen = {"once": 0, "sonra": 0}
    for g, d in sorted(gunler.items()):
        if g == kd or g >= bugun:
            continue
        k = "once" if g < kd else "sonra"
        if d["n"] < min_cagri:
            elenen[k] += 1
            continue
        yan[k][g] = d
    r = {"kesim": kesim.isoformat(timespec="minutes"), "esik": esik, "min_gun": min_gun, "min_cagri": min_cagri, "min_fark": min_fark, "tohum": tohum, "yanlar": {}}
    for k, v in yan.items():
        oran = [d["asan"] / d["n"] for d in v.values()]
        oturum_asan = [c for d in v.values() for c in d["oturum_asan"].values()]
        y = {"gun": len(v), "elenen_gun": elenen[k], "cagri": sum(d["n"] for d in v.values()), "asan": sum(d["asan"] for d in v.values()),
             "asan_oturum": len(oturum_asan), "oturum_asan_medyan": statistics.median(oturum_asan) if oturum_asan else 0}
        if oran:
            y["ort"], y["alt"], y["ust"] = _araligi(oran, tohum)
        r["yanlar"][k] = y
    o, s_ = r["yanlar"]["once"], r["yanlar"]["sonra"]
    if o["gun"] < min_gun or s_["gun"] < min_gun:
        r["karar"] = "yetersiz veri"
        r["neden"] = f"günler yetmiyor: önce {o['gun']}, sonra {s_['gun']} (gerekli >= {min_gun} + >= {min_gun})"
    else:
        r["fark"] = o["ort"] - s_["ort"]
        ortusmuyor = s_["ust"] < o["alt"]
        r["karar"] = "etki var" if (r["fark"] >= min_fark and ortusmuyor) else "etki görülmedi"
        r["neden"] = f"düşüş {100 * r['fark']:.1f} puan; aralıklar " + ("örtüşmüyor" if ortusmuyor else "örtüşüyor")
    return r


def _kullanici_istegi(o: dict) -> bool:
    """Gerçek kullanıcı mesajı (araç sonucu, yan zincir, meta ve sıkıştırma özeti değil): yeni istek başlatır."""
    if o.get("type") != "user" or o.get("isSidechain") or o.get("isMeta") or o.get("isCompactSummary"):
        return False
    c = (o.get("message") or {}).get("content")
    if isinstance(c, str):
        ilk = c.strip()
    else:
        blok = [x for x in (c or []) if isinstance(x, dict)]
        if any(x.get("type") == "tool_result" for x in blok):
            return False
        ilk = " ".join(x.get("text") or "" for x in blok if x.get("type") == "text").strip()
    return bool(ilk) and not ilk.startswith(_ISTEK_DISI)


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
        import is_kaydi as IK  # noqa: PLC0415
        isler = IK.merkez_isler(sd)   # klasor alanı çözülmüş (I-223)
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


def hiz_bolumu(sd: str, basla: str) -> dict | None:
    """Tur süresi kırılımı (kaynak: zaman.jsonl). Tur = `ana` satırının sure_ms'i (kullanıcı isteğinden yanıtın bitişine). Araç süresi = aynı istek_id'li `arac` satırları toplamı
    (paralel araçlar toplamı turu aşabilir: tura kırpılır, `kirpilan` sayılır). Kalan = tur - araç: model üretimi, ağ ve izin onayı beklemesi; bunlar ayrılamaz.
    AskUserQuestion süresi kullanıcı bekleme olarak ayrı verilir. istek_id taşımayan ana satırlar (eski kayıtlar) kırılıma girmez, sayısı yazılır."""
    yol = os.path.join(sd, "zaman.jsonl")
    if not os.path.isfile(yol):
        return None
    turlar, araclar = {}, {}
    toplam_ana, alt_sn = 0, 0.0
    for o in _satirlar(yol):
        if str(o.get("zaman", ""))[:10] < basla:
            continue
        if o.get("tur") == "ana" and o.get("sure_ms"):
            toplam_ana += 1
            if o.get("istek_id"):
                turlar[o["istek_id"]] = o["sure_ms"] / 1000
        elif o.get("tur") == "alt" and o.get("sure_ms"):
            alt_sn += o["sure_ms"] / 1000
        elif o.get("tur") == "arac" and o.get("istek_id") and o.get("sure_ms") is not None:
            araclar.setdefault(o["istek_id"], []).append((o.get("arac") or "?", o["sure_ms"] / 1000))
    if not turlar:
        return None
    kirpilan, bekleme, arac_top, kalan = 0, 0.0, {}, 0.0
    for kid, t in turlar.items():
        satir = araclar.get(kid, [])
        top = sum(x[1] for x in satir)
        k = min(1.0, t / top) if top else 1.0
        kirpilan += top > t
        for ad, sn in satir:
            arac_top[ad] = arac_top.get(ad, 0.0) + sn * k
        bekleme += sum(sn for ad, sn in satir if ad == "AskUserQuestion") * k
        kalan += max(0.0, t - min(top, t))
    sureler = sorted(turlar.values())
    toplam = sum(sureler)
    ana_arac = sum(arac_top.values())
    return {"basla": basla, "tur": len(sureler), "ana_toplam": toplam_ana, "istek_id_yok": toplam_ana - len(sureler), "medyan_sn": statistics.median(sureler),
            "p90_sn": sureler[int(0.9 * (len(sureler) - 1))], "toplam_sn": toplam, "arac_sn": ana_arac, "kalan_sn": kalan, "bekleme_sn": bekleme, "kirpilan": kirpilan, "alt_sn": alt_sn,
            "araclar": sorted(arac_top.items(), key=lambda x: -x[1])[:8]}


def hesapla(sd: str, dizin: str, gun: float, basla: str, sonra=None, uyari_kesim=None) -> dict:
    taban = taban_bolumu(dizin, gun, sonra)
    esik, istek = esik_bolumu(dizin, gun, sonra=sonra, yeni_taban=taban.get("ilk_medyan")), istek_bolumu(dizin, gun, sonra)
    istek["sikistirma_gunluk"] = sikistirma_gunluk(sd, basla)
    return {"olcum": datetime.datetime.now().isoformat(timespec="minutes"), "gun": gun, "sonra": sonra.isoformat(timespec="minutes") if sonra else None,
            "taban": taban, "esik": esik, "istek": istek, "onek": onek_maliyeti(taban, esik, istek), "is_basina": is_basina_bolumu(sd, basla), "hiz": hiz_bolumu(sd, basla),
            "uyari": uyari_etkisi(dizin, uyari_kesim) if uyari_kesim else None}


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
              "| eşik | aşan çağrı | ücret payı | aşan oturum | eşik üstü okuma fazlası $ (brüt üst sınır; devir değil) | net devir kazancı $ (belge 10k–2k token; ADR-0034) |",
              "|---|---|---|---|---|---|"]
        for x in e["esikler"]:
            n = x.get("devir_net")
            net = f"{n[DEVIR_BELGESI[0]][1]:+.2f} … {n[DEVIR_BELGESI[-1]][1]:+.2f} ({n[DEVIR_BELGESI[0]][0]} oturum)" if n else "-"
            s.append(f"| {x['esik'] // 1000} bin | {x['cagri']} (%{100 * x['cagri_orani']:.1f}) | {x['usd']:.2f}$ (%{100 * x['usd_payi']:.1f}) | {x['oturum']} (%{100 * x['oturum_orani']:.1f}) | {x['devir_kazanc_ust_sinir']:.2f} | {net} |")
        s += ["", "Okuma: iki sütun aynı şeyi ölçmez. \"Okuma fazlası\" eşik üstündeki bağlamın tamamını sayar ve hiç devir maliyeti içermez; \"net devir\" "
                  "devirden sonra kalan çağrılardaki küçülmeyi sayar, devir belgesi ve yeni oturum tabanı maliyetini düşer. Belge boyutu varsayımdır (ölçülmedi); kalite etkisi ölçülmedi."]
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
    u = r.get("uyari")
    if u:
        s += ["", f"## Devir uyarısı etkisi (kesim {u['kesim']}; ölçüt: günlük >{u['esik'] // 1000} bin bağlamlı çağrı payı)",
              f"Karar: **{u['karar']}** ({u['neden']}). Kural ölçümden önce sabit: her yanda >= {u['min_gun']} tam gün, günde >= {u['min_cagri']} çağrı, fark >= {100 * u['min_fark']:.0f} puan ve gün-bootstrap %95 aralıkları örtüşmüyor (tohum {u['tohum']}).", "",
              "| yan | gün | elenen gün | çağrı | aşan | günlük pay ort. (%95 aralık) | aşan oturum | oturum başına aşan çağrı medyanı |", "|---|---|---|---|---|---|---|---|"]
        for k, ad in (("once", "uyarı öncesi"), ("sonra", "uyarı sonrası")):
            y = u["yanlar"][k]
            aralik = f"%{100 * y['ort']:.1f} (%{100 * y['alt']:.1f}..%{100 * y['ust']:.1f})" if "ort" in y else "-"
            s.append(f"| {ad} | {y['gun']} | {y['elenen_gun']} | {y['cagri']} | {y['asan']} | {aralik} | {y['asan_oturum']} | {y['oturum_asan_medyan']:g} |")
        s.append("Karıştırıcı: iş yükü ve uzun oturum sayısı iki yanda aynı değildir; aşan oturum sütunu payın birkaç oturumdan mı geldiğini gösterir. Nedensellik iddia edilmez.")
    h = r.get("hiz")
    if h:
        pay = lambda x: f"%{100 * x / h['toplam_sn']:.1f}"  # noqa: E731
        s += ["", f"## Hız: tur süresi kırılımı ({h['basla']}..şimdi, kaynak zaman.jsonl; {h['tur']} tur, istek_id'siz {h['istek_id_yok']} ana kayıt dışarıda)",
              f"- Tur süresi: medyan {h['medyan_sn']:.0f} sn, p90 {h['p90_sn']:.0f} sn, toplam {h['toplam_sn'] / 3600:.1f} saat",
              f"- Araç zamanı {pay(h['arac_sn'])} (Bash dahil aşağıda); kullanıcı bekleme (AskUserQuestion) {pay(h['bekleme_sn'])}; kalan {pay(h['kalan_sn'])} = model üretimi + ağ + izin onayı + alt ajan beklemesi (ayrılamadı)",
              f"- Alt ajan satırları (tur=alt) toplamı {h['alt_sn'] / 3600:.1f} saat: ana turla örtüşebilir (arka plan ajanlar dahil); toplama eklenmez",
              "- Araç dağılımı: " + "; ".join(f"{ad} {sn / 3600:.1f} sa ({pay(sn)})" for ad, sn in h["araclar"]),
              f"- Paralel araçlar tur süresini aşan tur: {h['kirpilan']} (araç süresi tura kırpıldı)"]
    i = r["is_basina"]
    s += ["", f"## İş başına $ ({i['basla']}..şimdi): defter {i['toplam_usd']:.2f}$, iş-bağlı {i['is_bagli_usd']:.2f}$"]
    s.append(f"- A (kapanan iş başına): {i['kapanan_is']} iş" + (f" -> {i['a_usd']:.2f}$/iş" if i["a_usd"] is not None else ""))
    s.append(f"- B (teslim kart başına, ret/israf göstergesi): {i['teslim_kart']} kart" + (f" -> {i['b_usd']:.2f}$/kart, ret yiyen %{100 * i['ret_orani']:.0f}" if i["b_usd"] is not None else ""))
    return "\n".join(s)
