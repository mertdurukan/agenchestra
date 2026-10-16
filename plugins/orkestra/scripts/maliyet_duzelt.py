"""Maliyet defteri geriye dönük iş atfı düzeltmesi (I-030 P3).

Ham maliyet.jsonl'e dokunulmaz. İşsiz satırların işi, kart (gorev -> kartın is alanı) ya da TEK işe bağlı
oturum (oturum json'u) üzerinden bulunur ve <sd>/maliyet_duzeltme.jsonl'e yalnız-ekleme olarak yazılır.
Okuma katmanı (ork_lib.maliyet_kayitlari) bu dosyayı bindirir.
"""
from __future__ import annotations

import os

import ork_lib as L

DUZELTME_DOSYASI = "maliyet_duzeltme.jsonl"


def duzeltme_yolu(sd: str) -> str:
    return os.path.join(sd, DUZELTME_DOSYASI)


def satir_anahtari(r: dict) -> str:
    return "|".join(str(r.get(a)) for a in ("oturum", "zaman", "agent_id", "kaynak", "model"))


def isiz_mi(r: dict) -> bool:
    return not r.get("is") or r.get("is") == "-"


def duzeltme_haritasi(sd: str) -> dict:
    """anahtar -> is (ilk yazılan kazanır). Bozuk/eksik satırlar atlanır."""
    out: dict = {}
    for e in L.jsonl_oku(duzeltme_yolu(sd)):
        a, i = e.get("anahtar"), e.get("is")
        if a and i and a not in out:
            out[a] = i
    return out


def oturum_isleri(sd: str, oturum) -> set:
    """Oturum json'undaki farklı iş kimlikleri (is_gecmis + is). Dosya yok/bozuksa boş küme."""
    if not oturum or oturum == "-":
        return set()
    durum, d = L._oturum_json_oku(L._oturum_json_yol(sd, oturum))
    if durum != "ok":
        return set()
    kume = {str(g.get("is")) for g in (d.get("is_gecmis") or []) if isinstance(g, dict) and g.get("is")}
    if d.get("is"):
        kume.add(str(d["is"]))
    return kume


def coz(sd: str, r: dict, onbellek: dict):
    """(is, kaynak) ya da None. Kart oturumdan önce gelir; çoklu işli oturum çözülmez."""
    gorev = r.get("gorev")
    if gorev and gorev != "-":
        if gorev not in onbellek["kart"]:
            k = L.kart_oku(sd, gorev)
            onbellek["kart"][gorev] = str(k["is"]) if isinstance(k, dict) and k.get("is") else None
        if onbellek["kart"][gorev]:
            return onbellek["kart"][gorev], "kart"
    oturum = r.get("oturum")
    if oturum not in onbellek["oturum"]:
        onbellek["oturum"][oturum] = oturum_isleri(sd, oturum)
    kume = onbellek["oturum"][oturum]
    if len(kume) == 1:
        return next(iter(kume)), "oturum"
    return None


def planla(sd: str) -> dict:
    """Ham (düzeltmesiz, tekilleştirilmiş) satırlardan düzeltilebilir / doldurulamayan dökümü. Dosya yazmaz."""
    rows = L._maliyet_kayitlari_oku(os.path.join(sd, "maliyet.jsonl"), duzeltme=False)
    var = duzeltme_haritasi(sd)
    onb = {"kart": {}, "oturum": {}}
    duzelt, doldurulamayan, zaten = [], [], 0
    gorulen = set()
    for r in rows:
        if not isiz_mi(r):
            continue
        a = satir_anahtari(r)
        if a in gorulen:
            continue
        gorulen.add(a)
        if a in var:
            zaten += 1
            continue
        c = coz(sd, r, onb)
        if c:
            duzelt.append((r, c[0], c[1]))
        else:
            doldurulamayan.append(r)
    usd = lambda l: sum((x[0] if isinstance(x, tuple) else x).get("maliyet_usd") or 0 for x in l)  # noqa: E731
    return {"duzelt": duzelt, "doldurulamayan": doldurulamayan, "zaten": zaten,
            "duzelt_satir": len(duzelt), "duzelt_usd": usd(duzelt),
            "duzelt_oturum": len({r.get("oturum") for r, _, _ in duzelt}),
            "doldurulamayan_satir": len(doldurulamayan), "doldurulamayan_usd": usd(doldurulamayan),
            "doldurulamayan_oturum": len({r.get("oturum") for r in doldurulamayan})}


def uygula(sd: str, p: dict) -> int:
    """Planı düzeltme dosyasına yalnız ekler (kilitli; dosyada zaten olan anahtar tekrar yazılmaz). Eklenen adet."""
    if not p["duzelt"]:
        return 0
    yol = duzeltme_yolu(sd)
    an = L.simdi()
    with L.kilit(os.path.join(sd, "maliyet_duzeltme_kontrol")):
        var = duzeltme_haritasi(sd)
        satirlar = []
        for r, is_id, kaynak in p["duzelt"]:
            a = satir_anahtari(r)
            if a in var:
                continue
            var[a] = is_id
            satirlar.append(L.json.dumps({"v": L.KAYIT_SURUMU, "anahtar": a, "is": is_id, "kaynak": kaynak, "zaman": an},
                                         ensure_ascii=False) + "\n")
        if satirlar:
            L.sona_ekle(yol, "".join(satirlar))
    return len(satirlar)


def metin(p: dict, uygulandi: int | None) -> str:
    an = L.simdi()
    s = [f"maliyet duzelt — ölçüm {an}",
         f"düzeltilebilir: {p['duzelt_satir']} satır, {p['duzelt_usd']:.2f} USD, {p['duzelt_oturum']} oturum",
         f"doldurulamayan: {p['doldurulamayan_satir']} satır, {p['doldurulamayan_usd']:.2f} USD "
         f"({p['doldurulamayan_oturum']} oturum; atif_nedeni=oturum-isiz)",
         f"zaten düzeltilmiş: {p['zaten']} satır"]
    s.append("kuru koşu: dosyaya yazılmadı (--uygula ile maliyet_duzeltme.jsonl'e eklenir)" if uygulandi is None
             else f"uygulandı: {uygulandi} düzeltme maliyet_duzeltme.jsonl'e eklendi")
    return "\n".join(s)
