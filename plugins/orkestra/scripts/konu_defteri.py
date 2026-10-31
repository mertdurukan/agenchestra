"""Sohbet konu defteri (ADR-0115, I-298): her sohbette konuşulan konular saniyeli zamanla kalıcı kaydedilir.

Defter proje başına `.claude/orkestra/konular.jsonl`, ekleme-only ve kilitlidir (ork_lib.jsonl_ekle). Olaylar:
  ac     yeni konu (kaynak=hook: sohbetin ilk isteği; kaynak=ajan: `orkestra konu ac`)
  tur    kullanıcı isteği, açık konuya sayılır (ne = ≤80 karakterlik kural tabanlı özet)
  aday   hook konu değişimi sinyali gördü (tür=ortusme: jeton örtüşmesi düşük; tür=bosluk: uzun ara)
Sayım yalnız `ac` olaylarıyla yapılır. Süre = son tur zamanı − açılış zamanı. Kapatma: ORKESTRA_KONU_DEFTERI=0.
Ayar: ayarlar/konu_defteri.json (proje ezmesi: .claude/orkestra/konu_defteri.json).
"""
from __future__ import annotations

import datetime
import json
import os
import re

import ork_lib as L

DOSYA = "konular.jsonl"
KAPI = "konu_defteri"
BASLIK_AZAMI = 120
OZET_AZAMI = 80
VARSAYILAN = {"ortusme_esigi": 0.10, "bosluk_dk": 60, "kisa_jeton": 4, "son_istek": 3}
_DURAK = frozenset("ve ile bir bu şu o da de mi mı mu mü için ama ancak gibi çok daha en ne nasıl neden "
                   "var yok ben sen biz siz ki ya veya the a an of to is and in on for it".split())
_ONAY = re.compile(r"^\W*(evet|hayır|tamam|olur|yap|onay\w*|başla|devam|ok|okay|peki|tamamdır)\W*$", re.I)


def acik() -> bool:
    return os.environ.get("ORKESTRA_KONU_DEFTERI") != "0"


def yol(sd: str) -> str:
    return os.path.join(sd, DOSYA)


def ayar(sd: str | None = None) -> dict:
    """Eklenti ayarı + proje ezmesi; bozuk ya da eksikse varsayılan."""
    sonuc = dict(VARSAYILAN)
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yollar = [os.path.join(kok, "ayarlar", KAPI + ".json")]
    if sd:
        yollar.append(os.path.join(sd, KAPI + ".json"))
    for y in yollar:
        try:
            with open(y, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            for k in VARSAYILAN:
                if isinstance(d.get(k), (int, float)):
                    sonuc[k] = d[k]
    return sonuc


def _kisalt(m: str | None, n: int) -> str:
    t = " ".join(re.sub(r"</?[A-Za-z_\-]+[^>]*>", " ", L.maskele(m or "")).split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _zaman(s):
    try:
        return datetime.datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- okuma

def oku(sd: str) -> list[dict]:
    return L.jsonl_oku(yol(sd))


def _oturum_olaylari(sd: str, oturum: str) -> list[dict]:
    """Oturumun olayları. Önce dosya sonundan okunur (aktif sohbet sonda); yoksa bir kez tamamı taranır."""
    y = yol(sd)
    if not os.path.exists(y):
        return []
    try:
        boyut = os.path.getsize(y)
        with open(y, "rb") as f:
            f.seek(max(0, boyut - 256 * 1024))
            parca = f.read().decode("utf-8", "replace")
        satirlar = parca.splitlines()[1:] if boyut > 256 * 1024 else parca.splitlines()
        olaylar = []
        for s in satirlar:
            try:
                k = json.loads(s)
            except ValueError:
                continue
            if isinstance(k, dict) and k.get("oturum") == oturum:
                olaylar.append(k)
        if olaylar or boyut <= 256 * 1024:
            return olaylar
    except OSError:
        return []
    return [k for k in oku(sd) if k.get("oturum") == oturum]


# ---------------------------------------------------------------- yazma

def _yaz(sd: str, oturum: str, tur: str, **alan) -> None:
    kayit = {"zaman": L.simdi(), "oturum": oturum, "tur": tur}
    kayit.update({k: v for k, v in alan.items() if v not in (None, "")})
    L.jsonl_ekle(yol(sd), kayit)


def _son_sira(olaylar: list[dict]) -> int:
    return max([k.get("sira", 0) for k in olaylar if k.get("tur") == "ac"] or [0])


def ac(sd: str, oturum: str, baslik: str, kaynak: str = "ajan", neden: str | None = None) -> int:
    """Yeni konu açar, sırasını döndürür. Son iki olay aday→tur ise `devral` yazılır: o tur yeni konuya sayılır."""
    olaylar = _oturum_olaylari(sd, oturum)
    sira = _son_sira(olaylar) + 1
    devral, aday_tip = None, None
    if len(olaylar) >= 2 and olaylar[-1].get("tur") == "tur" and olaylar[-2].get("tur") == "aday":
        devral, aday_tip = True, olaylar[-2].get("tip")
    _yaz(sd, oturum, "ac", sira=sira, baslik=_kisalt(baslik, BASLIK_AZAMI) or f"Konu {sira}", kaynak=kaynak,
         neden=_kisalt(neden, 160) if neden else None, devral=devral, aday_tip=aday_tip)
    return sira


def tur_say(sd: str, oturum: str, ozet: str | None = None) -> int | None:
    """Açık konuya bir tur ekler; açık konu yoksa None."""
    sira = _son_sira(_oturum_olaylari(sd, oturum))
    if not sira:
        return None
    _yaz(sd, oturum, "tur", sira=sira, ne=_kisalt(ozet, OZET_AZAMI) or None)
    return sira


def aday(sd: str, oturum: str, tip: str, skor: float | None = None) -> None:
    _yaz(sd, oturum, "aday", tip=tip, skor=None if skor is None else round(skor, 3))


# ---------------------------------------------------------------- örtüşme ve hook akışı

def _jetonlar(m: str) -> set[str]:
    return {j for j in re.findall(r"\w+", (m or "").lower()) if len(j) > 2 and j not in _DURAK}


def ortusme(istek: str, konu: str, kisa_jeton: int = 4) -> float | None:
    """İstek ile konu metni arasındaki jeton Jaccard'ı. Kısa mesaj (≤ kisa_jeton jeton) ve onay: None (muaf)."""
    if _ONAY.match(istek or ""):
        return None
    a = _jetonlar(istek)
    if len(a) <= kisa_jeton:
        return None
    b = _jetonlar(konu)
    if not b:
        return None
    return len(a & b) / len(a | b)


HATIRLATMA = ("Orkestra konu defteri: bu istek önceki konudan farklı görünüyor ({tip}). Gerçekten yeni konuysa bir kez "
              "`orkestra konu ac \"<konu başlığı, en çok 12 kelime>\"` çalıştır; aynı konunun devamıysa YAZMA. "
              "Kullanıcıya bundan söz etme.")


def hook_istek(sd: str, oturum: str, metin: str) -> str:
    """UserPromptSubmit'te çağrılır: ilk istekte konu açar, sonrasında tur sayar ve gerekirse `aday` yazar.
    Ajana verilecek hatırlatma metnini döndürür ('' = yok). Hata asla çağırana taşmaz."""
    try:
        if not acik() or not oturum or not sd or (metin or "").lstrip().startswith("<"):
            return ""
        cfg = ayar(sd)
        ozet = L.ne_ozeti(metin)
        olaylar = _oturum_olaylari(sd, oturum)
        if not _son_sira(olaylar):
            ac(sd, oturum, ozet, kaynak="hook")
            tur_say(sd, oturum, ozet)
            return ""
        tip, skor = None, None
        son = next((k for k in reversed(olaylar) if k.get("tur") in ("tur", "ac")), None)
        z_son, z_simdi = _zaman(son.get("zaman")) if son else None, _zaman(L.simdi())
        if z_son and z_simdi and (z_simdi - z_son).total_seconds() >= cfg["bosluk_dk"] * 60:
            tip = "bosluk"
        else:
            sira = _son_sira(olaylar)
            baslik = next((k.get("baslik", "") for k in reversed(olaylar) if k.get("tur") == "ac" and k.get("sira") == sira), "")
            son_istekler = [k.get("ne", "") for k in olaylar if k.get("tur") == "tur" and k.get("sira") == sira][-int(cfg["son_istek"]):]
            skor = ortusme(metin, " ".join([baslik] + son_istekler), int(cfg["kisa_jeton"]))
            if skor is not None and skor < cfg["ortusme_esigi"]:
                tip = "ortusme"
        if tip:
            aday(sd, oturum, tip, skor)
        tur_say(sd, oturum, ozet)
        return HATIRLATMA.format(tip=tip) if tip else ""
    except Exception:
        return ""


# ---------------------------------------------------------------- özet ve rapor

def oturum_ozeti(olaylar: list[dict]) -> list[dict]:
    """Tek oturumun olaylarından konu listesi: sira, baslik, kaynak, acilis, son_tur, tur, sure_sn, devral, aday_tip."""
    konular: dict[int, dict] = {}
    zamanlar: dict[int, list] = {}
    siralar: list[int] = []
    son_tur = None  # (sira, zaman) en son tur olayı
    for k in sorted(olaylar, key=lambda x: str(x.get("zaman"))):
        t = k.get("tur")
        if t == "ac":
            s = k.get("sira")
            konular[s] = {"sira": s, "baslik": k.get("baslik"), "kaynak": k.get("kaynak"), "acilis": k.get("zaman"),
                          "devral": bool(k.get("devral")), "aday_tip": k.get("aday_tip")}
            zamanlar[s] = []
            siralar.append(s)
            if k.get("devral") and son_tur and son_tur[0] in zamanlar and son_tur[0] != s and zamanlar[son_tur[0]]:
                zamanlar[son_tur[0]].pop()  # aday sonrası gelen tur yeni konuya aittir
                zamanlar[s].append(son_tur[1])
        elif t == "tur" and k.get("sira") in zamanlar:
            zamanlar[k["sira"]].append(k.get("zaman"))
            son_tur = (k["sira"], k.get("zaman"))
    for s in siralar:
        konular[s]["tur"] = len(zamanlar[s])
        konular[s]["son_tur"] = zamanlar[s][-1] if zamanlar[s] else konular[s]["acilis"]
    out = []
    for s in siralar:
        c = konular[s]
        a, b = _zaman(c["acilis"]), _zaman(c["son_tur"])
        c["sure_sn"] = int((b - a).total_seconds()) if a and b and b >= a else 0
        out.append(c)
    return out


def _gunden(olaylar: list[dict], gun: int | None) -> list[dict]:
    if not gun:
        return olaylar
    sinir = datetime.datetime.now().astimezone() - datetime.timedelta(days=gun)
    return [k for k in olaylar if (z := _zaman(k.get("zaman"))) and z >= sinir]


def rapor(sdler: list[str], gun: int | None = None) -> dict:
    """Sohbet başına konu sayısı, dağılım ve aday göstergeleri; sayılar yalnız defterden hesaplanır."""
    oturumlar: dict[tuple, list[dict]] = {}
    for sd in sdler:
        for k in _gunden(oku(sd), gun):
            if k.get("oturum"):
                oturumlar.setdefault((sd, k["oturum"]), []).append(k)
    sayilar, konu_listesi = [], []
    adaylar = {"ortusme": 0, "bosluk": 0}
    teyit = {"ortusme": 0, "bosluk": 0}
    adaysiz = 0
    for (sd, oturum), ol in oturumlar.items():
        konular = oturum_ozeti(ol)
        sayilar.append(len(konular))
        konu_listesi.extend([dict(c, oturum=oturum, sd=sd) for c in konular])
        for k in ol:
            if k.get("tur") == "aday" and k.get("tip") in adaylar:
                adaylar[k["tip"]] += 1
        for c in konular:
            if c["sira"] > 1:
                if c["devral"] and c["aday_tip"] in teyit:
                    teyit[c["aday_tip"]] += 1
                else:
                    adaysiz += 1
    toplam = sum(sayilar)
    dagilim = {"1": 0, "2": 0, "3": 0, "4+": 0}
    for n in sayilar:
        dagilim["4+" if n >= 4 else str(max(n, 1))] += 1
    gostergeler = {}
    for tip in adaylar:
        gostergeler[tip] = {"aday": adaylar[tip], "teyit": teyit[tip],
                            "teyit_orani": round(teyit[tip] / adaylar[tip], 3) if adaylar[tip] else None}
    kapsanan = sum(teyit.values()) + adaysiz
    return {"sohbet": len(sayilar), "konu": toplam, "ortalama": round(toplam / len(sayilar), 2) if sayilar else 0,
            "en_cok": max(sayilar or [0]), "dagilim": dagilim, "gostergeler": gostergeler,
            "adaysiz_acilis": adaysiz, "kacirma_proxy": round(adaysiz / kapsanan, 3) if kapsanan else None,
            "konular": konu_listesi}


def sure_metni(sn: int) -> str:
    return f"{sn // 3600}s {sn % 3600 // 60}dk {sn % 60}sn" if sn >= 3600 else f"{sn // 60}dk {sn % 60}sn"


def liste_md(konular: list[dict], baslik: str = "Konu listesi") -> str:
    satirlar = [f"# {baslik}", ""]
    for c in konular:
        satirlar.append(f"- **{c['acilis']}** · K{c['sira']} · {c['baslik']} "
                        f"({c['kaynak']}, {c['tur']} tur, {sure_metni(c['sure_sn'])})")
    return "\n".join(satirlar) + "\n"


def rapor_md(r: dict, gun: int | None = None) -> str:
    ust = f"son {gun} gün" if gun else "tüm zamanlar"
    s = ["# Sohbet konu raporu", "", f"**Kapsam:** {ust}. **Üretim:** {L.simdi()}.", "",
         "## Özet", "",
         f"- **Sohbet:** {r['sohbet']}",
         f"- **Konu:** {r['konu']} (sohbet başına ortalama {r['ortalama']}, en çok {r['en_cok']})",
         f"- **Dağılım (konu sayısına göre sohbet):** " + ", ".join(f"{k}: {v}" for k, v in r["dagilim"].items()), "",
         "## Konu sınırı göstergeleri", ""]
    for tip, g in r["gostergeler"].items():
        o = "-" if g["teyit_orani"] is None else f"%{g['teyit_orani'] * 100:.0f}"
        s.append(f"- **{tip}:** aday {g['aday']}, ajan teyidi {g['teyit']}, teyit oranı {o}")
    kp = "-" if r["kacirma_proxy"] is None else f"%{r['kacirma_proxy'] * 100:.0f}"
    s += [f"- **Adaysız ajan açılışı:** {r['adaysiz_acilis']} (kaçırma göstergesi {kp})", "", "## Konular", ""]
    for c in r["konular"]:
        s.append(f"- **{c['acilis']}** · K{c['sira']} · {c['baslik']} "
                 f"({c['kaynak']}, {c['tur']} tur, {sure_metni(c['sure_sn'])}) · sohbet `{c['oturum'][:8]}`")
    return "\n".join(s) + "\n"


def etiket_md(sdler: list[str], gun: int | None = None) -> str:
    """Elle etiketleme şablonu: her kullanıcı turu bir satır, etiket sütunu boş (yeni / devam)."""
    s = ["# Konu sınırı etiket şablonu", "",
         "Her satırın sonuna `yeni` ya da `devam` yaz. Hedef: en az 50 yeni, 150 devam, toplam 200 tur.", ""]
    for sd in sdler:
        olaylar = _gunden(oku(sd), gun)
        for k in olaylar:
            if k.get("tur") in ("tur", "aday"):
                if k["tur"] == "aday":
                    s.append(f"  - aday ({k.get('tip')}, skor {k.get('skor')})")
                else:
                    s.append(f"- {k['zaman']} · `{k['oturum'][:8]}` · K{k.get('sira')} · {k.get('ne') or '-'} · etiket: ")
    return "\n".join(s) + "\n"


# ---------------------------------------------------------------- Stop gölge uyarısı

def stop_kontrol(sd: str, oturum: str) -> bool:
    """Tur biterken: son `aday` olayından sonra ajan konu açmadan tur bittiyse gunluk.jsonl'a `kapi_golge` yazar
    (ajan açılış oranı ölçümü, P-028). Aynı aday için bir kez yazılır; hata çağırana taşmaz. Yazıldıysa True."""
    try:
        if not acik() or not oturum:
            return False
        olaylar = _oturum_olaylari(sd, oturum)
        if not olaylar or olaylar[-1].get("tur") not in ("tur", "aday"):
            return False
        i = max((n for n, k in enumerate(olaylar) if k.get("tur") == "aday"), default=None)
        if i is None or any(k.get("tur") == "ac" for k in olaylar[i:]):
            return False
        gl = os.path.join(sd, "gunluk.jsonl")
        neden = f"aday {olaylar[i].get('zaman')} ({olaylar[i].get('tip')}) için ajan konu açmadı"
        if any(k.get("tur") == "kapi_golge" and k.get("kapi") == KAPI and k.get("neden") == neden for k in L.jsonl_oku(gl)[-300:]):
            return False
        L.jsonl_ekle(gl, {"zaman": L.simdi(), "oturum": oturum, "tur": "kapi_golge", "kapi": KAPI, "is": "-", "neden": neden})
        return True
    except Exception:
        return False
