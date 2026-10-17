"""Teknik Detay: kartın ne/neden/nasıl/değişen/doğrulama/maliyet-süre/öğrenilen bloklarını betikle derler.

Kural tabanlı ve SALT OKUMA: LLM ya da ağ çağırmaz, kart/iş dosyasını değiştirmez (yalnız `md(..., yaz=True)`
işin klasörüne teknik_detay.md yazar). Kartın `token` alanı kullanılmaz (birikimli şişer); maliyet
ork_lib.maliyet_kayitlari'ndan (gorev=kart id) gelir. Çıktı metinleri ork_lib.maskele'den geçer.
"""
from __future__ import annotations

import ast
import datetime
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

BLOKLAR = ("ne", "neden", "nasil", "degisen", "dogrulama", "maliyet_sure", "ogrenilen")
_PY = (".py",)
_JS = (".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx")
_NODE_YERLESIK = frozenset("""assert async_hooks buffer child_process cluster console constants crypto dgram diagnostics_channel dns
domain events fs http http2 https inspector module net os path perf_hooks process punycode querystring readline repl stream
string_decoder sys timers tls trace_events tty url util v8 vm wasi worker_threads zlib""".split())
_JS_IMPORT = [
    re.compile(r"""\bimport\s+(?:[\w*${}\s,]+?\s+from\s+)?["']([^"']+)["']"""),
    re.compile(r"""\bexport\s+[\w*${}\s,]+?\s+from\s+["']([^"']+)["']"""),
    re.compile(r"""\brequire\s*\(\s*["']([^"']+)["']\s*\)"""),
    re.compile(r"""\bimport\s*\(\s*["']([^"']+)["']\s*\)"""),
]
_K_SATIRI = re.compile(r"^\s*[-*]?\s*(K\d+\s*[:.)\-].*)$", re.M)


def _mask(v):
    if isinstance(v, str):
        return L.maskele(v)
    if isinstance(v, list):
        return [_mask(x) for x in v]
    if isinstance(v, dict):  # commit özeti sır sanılmasın
        return {k: (x if k in ("son_commit", "temel") else _mask(x)) for k, x in v.items()}
    return v


# ---------------------------------------------------------------- import çıkarımı

def _proje(sd: str) -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(sd)))


def _cozumle(yol: str, proje: str) -> str:
    return yol if os.path.isabs(yol) else os.path.join(proje, yol)


def _py_importlari(kaynak: str) -> list[tuple[str, int]]:
    """[(modül, göreli_düzey)]; sözdizimi hatasında SyntaxError fırlar (çağıran yakalar)."""
    cikti = []
    for n in ast.walk(ast.parse(kaynak)):
        if isinstance(n, ast.Import):
            cikti += [(a.name, 0) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.module or not n.level:
                cikti.append((n.module or "", n.level or 0))
            else:  # `from . import x`: modül adı yok, adlar kardeş modüllerdir
                cikti += [(a.name, n.level) for a in n.names]
    return cikti


def _js_importlari(kaynak: str) -> list[str]:
    bulunan = []
    for r in _JS_IMPORT:
        bulunan += r.findall(kaynak)
    return list(dict.fromkeys(bulunan))


def _yerel_mi(ust: str, klasorler: list[str]) -> str | None:
    for k in klasorler:
        for aday in (os.path.join(k, ust + ".py"), os.path.join(k, ust, "__init__.py"), os.path.join(k, ust)):
            if os.path.exists(aday):
                return aday
    return None


def import_coz(yol: str, kaynak: str, proje: str) -> dict:
    """Bir dosyanın importları: {stdlib, ucuncu_taraf, yerel, kenarlar[(ad, hedef)], uyari}. Hata fırlatmaz."""
    sonuc = {"stdlib": [], "ucuncu_taraf": [], "yerel": [], "kenarlar": [], "uyari": None}
    uzanti = os.path.splitext(yol)[1].lower()
    dizin = os.path.dirname(os.path.abspath(yol))
    klasorler = [dizin, os.path.abspath(proje)]
    try:
        if uzanti in _PY:
            for ad, duzey in _py_importlari(kaynak):
                ust = ad.split(".")[0]
                if duzey:
                    taban = dizin
                    for _ in range(duzey - 1):
                        taban = os.path.dirname(taban)
                    hedef = os.path.join(taban, *ad.split(".")) if ad else taban
                    for aday in (hedef + ".py", os.path.join(hedef, "__init__.py")):
                        if os.path.exists(aday):
                            hedef = aday
                            break
                    ad_goster = "." * duzey + ad
                    sonuc["yerel"].append(ad_goster)
                    sonuc["kenarlar"].append((ad_goster, hedef))
                elif ust in sys.stdlib_module_names:
                    sonuc["stdlib"].append(ust)
                else:
                    h = _yerel_mi(ust, klasorler)
                    if h:
                        sonuc["yerel"].append(ust)
                        sonuc["kenarlar"].append((ust, h))
                    elif ust:
                        sonuc["ucuncu_taraf"].append(ust)
        elif uzanti in _JS:
            for ad in _js_importlari(kaynak):
                if ad.startswith((".", "/")):
                    sonuc["yerel"].append(ad)
                    sonuc["kenarlar"].append((ad, os.path.normpath(os.path.join(dizin, ad))))
                    continue
                govde = ad[5:] if ad.startswith("node:") else ad
                ust = "/".join(govde.split("/")[:2]) if govde.startswith("@") else govde.split("/")[0]
                if ad.startswith("node:") or ust in _NODE_YERLESIK:
                    sonuc["stdlib"].append(ust)
                else:
                    sonuc["ucuncu_taraf"].append(ust)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
        sonuc = {"stdlib": [], "ucuncu_taraf": [], "yerel": [], "kenarlar": [],
                 "uyari": f"{os.path.basename(yol)}: sözdizimi çözülemedi ({type(e).__name__})"}
    for k in ("stdlib", "ucuncu_taraf", "yerel"):
        sonuc[k] = list(dict.fromkeys(sonuc[k]))
    return sonuc


def _tum_importlar(r: dict) -> set:
    return set(r["stdlib"]) | set(r["ucuncu_taraf"]) | set(r["yerel"])


# ---------------------------------------------------------------- git

def _git(cwd: str, *args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30, stdin=subprocess.DEVNULL, **L.PENCERESIZ)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return 127, ""


# Depo kökü ve temel commit değişmez; her dosya için yeniden git başlatmak kart ayrıntısını onlarca sn'ye çıkarıyordu.
# Yalnız bulunan değerler saklanır (depo sonradan açılırsa ya da commit sonradan gelirse yanlış None kalmasın).
_KOK_ONBELLEK: dict = {}
_TEMEL_ONBELLEK: dict = {}


def _git_koku(dosya: str) -> str | None:
    d = os.path.dirname(os.path.abspath(dosya))
    while d and not os.path.isdir(d):
        ust = os.path.dirname(d)
        if ust == d:
            return None
        d = ust
    if d in _KOK_ONBELLEK:
        return _KOK_ONBELLEK[d]
    kod, cikti = _git(d, "rev-parse", "--show-toplevel")
    kok = cikti.strip() if kod == 0 and cikti.strip() else None
    if kok:
        _KOK_ONBELLEK[d] = kok
    return kok


def _temel_commit(kok: str, kart: dict) -> str | None:
    """İlk `isleniyor` olayından önceki son commit (git log --before); olay ya da commit yoksa None."""
    for o in kart.get("gecmis") or []:
        if isinstance(o, dict) and o.get("olay") == "isleniyor" and o.get("zaman"):
            anahtar = (kok, o["zaman"])
            if anahtar in _TEMEL_ONBELLEK:
                return _TEMEL_ONBELLEK[anahtar]
            kod, cikti = _git(kok, "log", "-1", "--format=%H", f"--before={o['zaman']}")
            temel = (cikti.strip() or None) if kod == 0 else None
            if temel:
                _TEMEL_ONBELLEK[anahtar] = temel
            return temel
    return None


def _satir_say(dosya: str) -> int:
    try:
        with open(dosya, "rb") as f:
            veri = f.read()
    except OSError:
        return 0
    return veri.count(b"\n") + (1 if veri and not veri.endswith(b"\n") else 0)


def _degisim(dosya: str, kart: dict) -> dict:
    """Dosya başına +/- satır, son commit ve temel sürüm; git yoksa / depoda değilse kaynak='git-yok'."""
    kayit = {"dosya": dosya, "kaynak": "git-yok", "ekle": None, "sil": None, "son_commit": None, "temel": None}
    kok = _git_koku(dosya)
    if not kok:
        return kayit
    rel = os.path.relpath(os.path.abspath(dosya), kok).replace("\\", "/")
    kod, cikti = _git(kok, "log", "-1", "--format=%H", "--", rel)
    kayit["son_commit"] = (cikti.strip() or None) if kod == 0 else None
    kayit["kaynak"] = "git"
    temel = _temel_commit(kok, kart)
    kayit["temel"] = temel
    ekle = sil = None
    if temel:
        kod, _ = _git(kok, "cat-file", "-e", f"{temel}:{rel}")
        if kod != 0:  # temelde yok: yeni dosya
            ekle, sil = _satir_say(dosya), 0
        else:
            kod, cikti = _git(kok, "diff", "--numstat", temel, "--", rel)
            if kod == 0:
                if cikti.strip():
                    a, s = cikti.split("\t")[:2]
                    if a.isdigit() and s.isdigit():
                        ekle, sil = int(a), int(s)
                else:
                    ekle, sil = 0, 0
    elif os.path.exists(dosya):
        ekle, sil = _satir_say(dosya), 0
    kayit["ekle"], kayit["sil"] = ekle, sil
    return kayit


def _temel_kaynak(dosya: str, kart: dict) -> str | None:
    """Temel sürümdeki dosya metni; yok / git yok ise None."""
    kok = _git_koku(dosya)
    if not kok:
        return None
    temel = _temel_commit(kok, kart)
    if not temel:
        return None
    rel = os.path.relpath(os.path.abspath(dosya), kok).replace("\\", "/")
    kod, cikti = _git(kok, "show", f"{temel}:{rel}")
    return cikti if kod == 0 else None


# ---------------------------------------------------------------- bloklar

def _dosyalar(kart: dict, proje: str) -> list[str]:
    return [_cozumle(c, proje) for c in kart.get("ciktilar") or [] if isinstance(c, str) and c.strip()]


def _oku(yol: str) -> str | None:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _otomatik(kart: dict, proje: str) -> dict:
    kut = {"stdlib": [], "ucuncu_taraf": [], "yerel": []}
    yeni, graf, uyarilar = [], [], []
    for yol in _dosyalar(kart, proje):
        if os.path.splitext(yol)[1].lower() not in _PY + _JS:
            continue
        kaynak = _oku(yol)
        if kaynak is None:
            continue
        r = import_coz(yol, kaynak, proje)
        if r["uyari"]:
            uyarilar.append(r["uyari"])
            continue
        for k in kut:
            kut[k] += r[k]
        ad = os.path.basename(yol)
        graf += [f"{ad} → {os.path.basename(h) if os.path.exists(h) else h}: {a}" for a, h in r["kenarlar"]]
        eski = _temel_kaynak(yol, kart)
        if eski is not None:
            onceki = _tum_importlar(import_coz(yol, eski, proje))
            yeni += [f"{ad}: {m}" for m in sorted(_tum_importlar(r) - onceki)]
        elif _git_koku(yol):  # temelde dosya yok: tüm importlar yeni
            yeni += [f"{ad}: {m}" for m in sorted(_tum_importlar(r))]
    return {"kutuphaneler": {k: list(dict.fromkeys(v)) for k, v in kut.items()},
            "yeni_bagimlilik": list(dict.fromkeys(yeni)), "entegrasyon_grafi": list(dict.fromkeys(graf)),
            "uyarilar": uyarilar}


def _k_satirlari(gerekce: str) -> list[str]:
    return [m.group(1).strip() for m in _K_SATIRI.finditer(gerekce or "")]


def _dogrulama(kart: dict) -> dict:
    den = []
    for d in kart.get("denetimler") or []:
        if not isinstance(d, dict):
            continue
        den.append({"sira": d.get("sira"), "karar": d.get("karar"), "neden": d.get("neden"),
                    "k_satirlari": _k_satirlari(d.get("gerekce") or "")})
    tk = [{"asama": x.get("asama"), "gecti": x.get("gecti"), "cikis_kodu": x.get("cikis_kodu"), "zaman": x.get("zaman")}
          for x in kart.get("test_kosulari") or [] if isinstance(x, dict)]
    ok = [{"gecti": x.get("gecti"), "ihlal_turleri": x.get("ihlal_turleri"), "zaman": x.get("zaman")}
          for x in kart.get("onkontrol_kosulari") or [] if isinstance(x, dict)]
    return {"test_kosulari": tk, "onkontrol_kosulari": ok, "denetimler": den}


def _sureler(kart: dict) -> dict:
    import akis
    if not isinstance(kart.get("gecmis"), list):
        return {}
    try:
        tamam, _acik, _ilk = akis.kart_analiz(kart, datetime.datetime.now().astimezone())
    except Exception:
        return {}

    def top(*adlar):
        v = [tamam[a] for a in adlar if a in tamam]
        return round(sum(v), 1) if v else None

    s = {"kuyruk_sn": top("alinma_bekleme"), "is_sn": top("iscide_ilk", "iscide_duzeltme"), "denetim_sn": top("denetimde")}
    return {k: v for k, v in s.items() if v is not None}


def _maliyet(sd: str, kart_id: str) -> dict:
    toplam: dict = {}
    tok: dict = {}
    satir: list = []
    for r in L.maliyet_kayitlari(sd):
        if r.get("gorev") != kart_id:
            continue
        anahtar = (r.get("ajan") or "?", r.get("model") or "?")
        toplam[anahtar] = toplam.get(anahtar, 0.0) + float(r.get("maliyet_usd") or 0)
        tok[anahtar] = tok.get(anahtar, 0) + sum(int(r.get(a) or 0) for a in L._TOKEN_ALANLARI)
        satir.append(r)
    satirlar = [{"ajan": a, "model": m, "usd": round(u, 6), "token": tok.get((a, m), 0)} for (a, m), u in sorted(toplam.items())]
    return {"satirlar": satirlar, "toplam_usd": round(sum(s["usd"] for s in satirlar), 6),
            "toplam_token": sum(s["token"] for s in satirlar), "kalem": L.kalemler(satir)}


def _ogrenilen(kart: dict) -> dict:
    retler = []
    for d in kart.get("denetimler") or []:
        if isinstance(d, dict) and d.get("karar") == "ret":
            retler.append({"sira": d.get("sira"), "neden": d.get("neden"), "kok": d.get("kok"),
                           "talimat": (d.get("talimat") or "")[:300]})
    t = kart.get("teknik")
    riskler = list(t.get("riskler") or []) if isinstance(t, dict) else []
    return {"ret_dersleri": retler, "riskler": riskler}


def derle(sd: str, kart_id: str) -> dict:
    """7 blok + eksik. Kart yoksa ya da okunamazsa {"hata": ...} döner (istisna fırlatmaz)."""
    try:
        kart = L.kart_oku(sd, kart_id)
    except (ValueError, OSError) as e:
        return {"hata": f"kart okunamadı: {e}"}
    if not isinstance(kart, dict):
        return {"hata": f"kart bulunamadı: {kart_id}"}
    proje = _proje(sd)
    dosyalar = _dosyalar(kart, proje)
    teknik = kart.get("teknik") if isinstance(kart.get("teknik"), dict) else None
    ne = {"id": kart.get("id"), "baslik": kart.get("baslik"), "sinif": kart.get("sinif"), "basamak": kart.get("basamak"),
          "kabul_kriterleri": kart.get("kabul_kriterleri") or [], "ciktilar": kart.get("ciktilar") or []}
    neden = {"soru": kart.get("soru"), "is": kart.get("is")}
    otomatik = _otomatik(kart, proje)
    nasil = {"teknik": teknik, "teknik_zaman": kart.get("teknik_zaman"), "otomatik": otomatik}
    dl = [_degisim(d, kart) for d in dosyalar]
    git_var = [x for x in dl if x["kaynak"] == "git"]
    degisen = {"kaynak": "git" if git_var else "git-yok", "dosyalar": dl,
               "son_commit": next((x["son_commit"] for x in git_var if x["son_commit"]), None)}
    dogr = _dogrulama(kart)
    mal = _maliyet(sd, kart_id)
    maliyet_sure = {"maliyet": mal["satirlar"], "toplam_usd": mal["toplam_usd"], "toplam_token": mal["toplam_token"],
                    "kalem": mal["kalem"], "sureler": _sureler(kart)}
    ogr = _ogrenilen(kart)
    kut = otomatik["kutuphaneler"]
    eksik = []
    if not ne["baslik"]:
        eksik.append("ne")
    if not neden["soru"]:
        eksik.append("neden")
    if not teknik and not (kut["stdlib"] or kut["ucuncu_taraf"] or kut["yerel"]):
        eksik.append("nasil")
    if not dl:
        eksik.append("degisen")
    if not (dogr["test_kosulari"] or dogr["onkontrol_kosulari"] or dogr["denetimler"]):
        eksik.append("dogrulama")
    if not mal["satirlar"]:  # süre her kartta türetilebilir; maliyet defterde kayıt yoksa eksik
        eksik.append("maliyet_sure")
    if not (ogr["ret_dersleri"] or ogr["riskler"]):
        eksik.append("ogrenilen")
    return _mask({"ne": ne, "neden": neden, "nasil": nasil, "degisen": degisen, "dogrulama": dogr,
                  "maliyet_sure": maliyet_sure, "ogrenilen": ogr, "eksik": eksik})


# ---------------------------------------------------------------- markdown

def kart_md(kart_id: str, baslik: str | None, d: dict) -> str:
    if "hata" in d:
        return f"## {kart_id}\n\nHata: {d['hata']}\n"
    s = [f"## {kart_id} — {baslik or d['ne'].get('baslik') or ''}", ""]
    s.append(f"**Ne:** {d['ne'].get('baslik')} ({d['ne'].get('sinif')}, {d['ne'].get('basamak')})")
    s.append(f"**Neden:** {d['neden'].get('soru')}")
    t = d["nasil"].get("teknik")
    s += ["", "### Nasıl"]
    if t:
        s += [f"- Yaklaşım: {t.get('yaklasim')}", f"- Neden bu yol: {t.get('neden_bu_yol')}"]
        s += [f"- Alternatif: {a.get('secenek')} — elendi: {a.get('neden_elendi')}" for a in t.get("alternatifler") or []
              if isinstance(a, dict)]
        s += [f"- Entegrasyon: {e}" for e in t.get("entegrasyon") or []]
        s += [f"- Risk: {r}" for r in t.get("riskler") or []]
    o = d["nasil"]["otomatik"]
    for k, v in o["kutuphaneler"].items():
        if v:
            s.append(f"- Kütüphane ({k}): {', '.join(v)}")
    s += [f"- Yeni bağımlılık: {x}" for x in o["yeni_bagimlilik"]]
    s += [f"- Graf: {x}" for x in o["entegrasyon_grafi"]]
    s += [f"- Uyarı: {x}" for x in o["uyarilar"]]
    s += ["", f"### Değişen (kaynak: {d['degisen']['kaynak']}, son commit: {d['degisen'].get('son_commit')})"]
    s += [f"- {x['dosya']}: +{x['ekle']} / -{x['sil']} [{x['kaynak']}]" for x in d["degisen"]["dosyalar"]]
    s += ["", "### Doğrulama"]
    for x in d["dogrulama"]["denetimler"]:
        s.append(f"- Denetim {x['sira']}: {x['karar']} {x.get('neden') or ''}")
        s += [f"  - {k}" for k in x["k_satirlari"]]
    s += [f"- Test koşusu: {x['asama']} gecti={x['gecti']}" for x in d["dogrulama"]["test_kosulari"]]
    s += [f"- Ön kontrol: gecti={x['gecti']}" for x in d["dogrulama"]["onkontrol_kosulari"]]
    m = d["maliyet_sure"]
    s += ["", f"### Maliyet ve süre (toplam {m['toplam_usd']} USD)"]
    s += [f"- {x['ajan']} × {x['model']}: {x['usd']} USD" for x in m["maliyet"]]
    s += [f"- {k}: {v}" for k, v in m["sureler"].items()]
    s += ["", "### Öğrenilen"]
    s += [f"- Ret {x['sira']}: {x.get('neden')} {x.get('talimat')}" for x in d["ogrenilen"]["ret_dersleri"]]
    s += [f"- Risk: {x}" for x in d["ogrenilen"]["riskler"]]
    if d["eksik"]:
        s += ["", f"_Eksik bloklar: {', '.join(d['eksik'])}_"]
    return L.maskele("\n".join(s)) + "\n"


def _sira_anahtari(k: dict):
    m = re.search(r"(\d+)$", str(k.get("id")))
    return (k.get("olusturma") or "", int(m.group(1)) if m else 0)


def md(sd: str, is_id: str, yaz: bool = False) -> tuple[str, str | None]:
    """İşin kartlarını oluşturma sırasıyla markdown yapar -> (metin, yazılan_yol | None). İş yoksa ValueError."""
    import is_kaydi
    kayit = is_kaydi.is_al(sd, is_id)
    if not kayit:
        raise ValueError(f"iş bulunamadı: {is_id}")
    kartlar = []
    for gid in kayit.get("kartlar") or []:
        k = L.kart_oku(sd, gid)
        kartlar.append(k if isinstance(k, dict) else {"id": gid})
    kartlar.sort(key=_sira_anahtari)
    parcalar = [f"# Teknik detay — {is_id}: {L.maskele(str(kayit.get('baslik') or ''))}", ""]
    for k in kartlar:
        parcalar.append(kart_md(k["id"], k.get("baslik"), derle(sd, k["id"])))
    metin = "\n".join(parcalar)
    yol = None
    if yaz:
        yol = os.path.join(kayit["klasor"], "teknik_detay.md")
        L.atomik_yaz(yol, metin)
    return metin, yol
