"""Orkestra niyet kaydı: hangi sohbette hangi projenin hangi parçası yapılıyor, neye yarayacak, kimi bekliyor.

Kayıt hesap genelidir (bütün projeler tek dosyada): ~/.claude/orkestra-panel/niyet.jsonl
Olay türleri:
  niyet   ana ajan yazar: `orkestra niyet --ne "…" --neden "…"`  (iş değişince; aynı işin devamında yazılmaz)
  sonuc   ana ajan yazar: `orkestra niyet --sonuc "…"`            (iş bitince ne çıktı)
  istek   UserPromptSubmit hook'u (kullanıcı yazdı → Claude çalışıyor)
  tur     Stop hook'u (Claude turu bitirdi → seni bekliyor)
  kapandi SessionEnd hook'u
`gorunum()` bunları oturum başına tek satıra indirger; panel /simdi.json ile okur.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

GENEL_DIZIN = os.path.join(os.path.expanduser("~"), ".claude", "orkestra-panel")
NIYET_YOLU = os.path.join(GENEL_DIZIN, "niyet.jsonl")
AZAMI_BAYT = 3 * 1024 * 1024
ARKA_PLAN_ZAMAN_ASIMI_DK = 60  # arka plan turundan sonra bu kadar dk etkinlik yoksa "beklemede"
ESKI_GUN = 3         # bu kadar gün dokunulmayan sohbet "beklemede" sayılır
GORUNUM_GUN = 7       # şeritte gösterilen en eski etkinlik


def _kisalt(metin: str | None, n: int) -> str:
    m = " ".join(re.sub(r"</?[A-Za-z_\-]+[^>]*>", " ", metin or "").split())  # <pasted_content …> gibi etiketler
    return m if len(m) <= n else m[: n - 1].rstrip() + "…"


def _gecici(yol: str | None) -> bool:
    """Testlerin ve geçici çalışma alanlarının projesi (Temp altında): şeride girmez."""
    return bool(re.search(r"[\\/]appdata[\\/]local[\\/]temp[\\/]|^[\\/]tmp[\\/]", yol or "", re.I))


def masaustu_oturumlari() -> dict:
    """Claude masaüstü uygulamasının sohbet kayıtlarından: CLI oturum kimliği → (uygulama kimliği, başlık, arşivli mi).

    Yalnız bu dört alan okunur. Bağlantı: claude://claude.ai/epitaxy/<uygulama kimliği> (uygulamanın kendi
    sohbet bağlantısı; belgelenmiş bir arayüz değildir, uygulama sürümüyle değişebilir).
    """
    kok = os.path.join(os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming"),
                       "Claude", "claude-code-sessions")
    onb_yolu = os.path.join(GENEL_DIZIN, "masaustu_onbellek.json")
    try:
        with open(onb_yolu, encoding="utf-8") as f:
            onb = json.load(f)
    except Exception:
        onb = {}
    out, yeni, degisti = {}, {}, False
    for p in glob.glob(os.path.join(kok, "*", "*", "local_*.json")):
        try:
            imza = f"{os.path.getsize(p)}:{int(os.path.getmtime(p))}"
        except OSError:
            continue
        k = onb.get(p)
        if not k or k.get("imza") != imza:
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                k = {"imza": imza, "id": d.get("sessionId"), "cli": d.get("cliSessionId"), "baslik": d.get("title"),
                     "arsiv": bool(d.get("isArchived"))}
            except Exception:
                continue
            degisti = True
        yeni[p] = k
        if k.get("cli") and k.get("id"):
            out[k["cli"]] = {"id": k["id"], "baslik": k.get("baslik"), "arsiv": k.get("arsiv"),
                             "link": "claude://claude.ai/epitaxy/" + k["id"]}
    if degisti or len(yeni) != len(onb):
        try:
            L.atomik_yaz(onb_yolu, json.dumps(yeni, ensure_ascii=False))
        except Exception:
            pass
    return out


def _transkript_basi(proje: str, oturum: str) -> dict | None:
    """Transkriptin ilk satırlarından: ilk istek metni, zamanı ve masaüstünde mi başladığı."""
    yol = os.path.join(L.proje_oturum_dizini(proje), oturum + ".jsonl")
    try:
        with open(yol, encoding="utf-8", errors="ignore") as f:
            satirlar = [f.readline() for _ in range(12)]
    except OSError:
        return None
    bas = {"metin": None, "zaman": None, "masaustu": False}
    for s in satirlar:
        try:
            d = json.loads(s)
        except Exception:
            continue
        if d.get("type") == "queue-operation" and d.get("operation") == "enqueue" and bas["metin"] is None:
            bas["metin"], bas["zaman"] = d.get("content"), _zaman(d.get("timestamp"))
        bas["masaustu"] = bas["masaustu"] or d.get("entrypoint") == "claude-desktop"
    return bas


def _yetimler(oturumlar: dict, masaustu: dict) -> dict:
    """Masaüstünde başlamış ama uygulamada kaydı kalmamış oturumlar → uygulamadaki asıl oturum (yoksa None).

    Uygulama bir sohbeti ilk saniyelerde yeniden başlatınca ilk CLI oturumu yetim kalır; asıl oturum aynı ilk
    istekle birkaç dakika içinde başlar. Yetim kart CLI yoluna düşüp sohbeti ana ekranda açamıyordu.
    """
    out = {}
    for oid, s in oturumlar.items():
        if not oid or oid in masaustu or not s.get("proje_yol"):
            continue
        bas = _transkript_basi(s["proje_yol"], oid)
        if not bas or not bas["masaustu"]:
            continue  # terminalde başlamış sohbet: CLI yolu doğru
        asil = None
        if bas["metin"] and bas["zaman"]:
            for cli in masaustu:
                b2 = _transkript_basi(s["proje_yol"], cli)
                if b2 and b2["metin"] and bas["metin"] in b2["metin"] and b2["zaman"] and \
                        0 <= (b2["zaman"] - bas["zaman"]).total_seconds() <= 600:
                    asil = cli
                    break
        out[oid] = asil
    return out


def ac(oturum: str) -> dict:
    """Sohbeti Claude masaüstü uygulamasında açar.

    Uygulamada kaydı varsa uygulamanın kendi bağlantısı (claude://…/epitaxy/<id>); yoksa (terminalde başlamış
    sohbet) belgelenmiş yol: `claude --desktop --resume <oturum>`.
    """
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", oturum or ""):
        return {"tamam": False, "hata": "geçersiz oturum kimliği"}
    masaustu = masaustu_oturumlari()
    m = masaustu.get(oturum)
    proje = None if m else _oturum_projesi(oturum)
    if proje:  # masaüstünde başlayıp yetim kalan oturum: asıl sohbete yönlen
        asil = _yetimler({oturum: {"proje_yol": proje}}, masaustu).get(oturum)
        m = masaustu.get(asil) if asil else None
    if m:
        if os.name == "nt":
            os.startfile(m["link"])  # noqa: S606 — yalnız sabit claude:// şeması, kimlik doğrulandı
        else:
            import subprocess
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", m["link"]])
        return {"tamam": True, "yol": "uygulama", "baslik": m.get("baslik")}
    import subprocess
    import perspektif
    exe = perspektif.claude_exe()
    if not exe:
        return {"tamam": False, "hata": f"claude bulunamadı; terminalde: claude --desktop --resume {oturum}"}
    bayrak = 0x08000000 if os.name == "nt" else 0  # pencere açma
    subprocess.Popen([exe, "--desktop", "--resume", oturum], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=bayrak, close_fds=True)
    return {"tamam": True, "yol": "cli"}


def olay(oturum: str | None, proje: str | None, tur: str, **alan) -> None:
    """Tek olay ekler. Hata asla çağırana taşmaz (hook'ları bozmamalı)."""
    if not oturum or oturum == "-" or _gecici(proje):
        return
    try:
        os.makedirs(GENEL_DIZIN, exist_ok=True)
        if os.path.exists(NIYET_YOLU) and os.path.getsize(NIYET_YOLU) > AZAMI_BAYT:
            with L.kilit(NIYET_YOLU):
                if os.path.getsize(NIYET_YOLU) > AZAMI_BAYT:
                    os.replace(NIYET_YOLU, NIYET_YOLU + ".1")
        kayit = {"zaman": L.simdi(), "oturum": oturum, "proje": os.path.abspath(proje) if proje else None, "tur": tur}
        kayit.update({k: (L.maskele(v) if isinstance(v, str) else v) for k, v in alan.items() if v not in (None, "")})
        L.jsonl_ekle(NIYET_YOLU, kayit)
    except Exception:
        pass


BEKLEME_UZUNLUK = 140


def _duz_metin(m: str) -> str:
    """Markdown'dan düz metin: kod blokları, satır içi kod işaretleri, bağlantılar, başlık/vurgu işaretleri."""
    m = re.sub(r"```.*?```", " ", m or "", flags=re.S)
    m = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", m)
    m = re.sub(r"[`*_#>|]+", "", m)
    return m


def _cumleler(m: str) -> list[str]:
    out = []
    for satir in _duz_metin(m).splitlines():
        satir = re.sub(r"^\s*(?:[-•]|\d+[.)])\s+", "", satir).strip()
        out += [c.strip() for c in re.split(r"(?<=[.!?])\s+", satir) if c.strip()]
    return out


def _transkript_sorulari(yol: str | None, ofset: int) -> dict:
    """Bu turda (ofsetten sonra) Claude'un kullanıcıya bıraktığı açık soru: AskUserQuestion ve wrap_up (ask/recap)."""
    bulunan: dict = {}
    if not yol:
        return bulunan
    try:
        with open(yol, "rb") as f:
            f.seek(max(0, int(ofset or 0)))
            veri = f.read()
    except Exception:
        return bulunan
    for ham in veri.splitlines():
        try:
            o = json.loads(ham)
        except Exception:
            continue
        if not isinstance(o, dict) or o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        icerik = (o.get("message") or {}).get("content")
        for b in icerik if isinstance(icerik, list) else []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            ad, gir = str(b.get("name") or ""), b.get("input") or {}
            if ad == "AskUserQuestion":
                sorular = gir.get("questions") or []
                if sorular and isinstance(sorular[0], dict) and sorular[0].get("question"):
                    bulunan["soru"] = str(sorular[0]["question"])
            elif ad.endswith("wrap_up"):
                bulunan["ask"] = str(gir.get("ask") or "") or None
                bulunan["recap"] = str(gir.get("recap") or "") or None
    return bulunan


def bekleme_nedeni(transkript: str | None, ofset: int, son_mesaj: str | None) -> str:
    """Claude turu bitirdiğinde kullanıcıdan ne beklendiği, tek kısa cümle (deterministik; LLM yok).

    Sıra: bu turdaki AskUserQuestion sorusu → wrap_up'ın `ask`'ı → son mesajdaki son soru cümlesi →
    wrap_up recap'inin ilk cümlesi → son mesajın son cümlesi. Hiçbiri yoksa ''.
    """
    t = _transkript_sorulari(transkript, ofset)
    cumleler = _cumleler(son_mesaj or "")
    soru = next((c for c in reversed(cumleler) if c.endswith("?")), None)
    recap = (_cumleler(t["recap"]) or [None])[0] if t.get("recap") else None
    secilen = t.get("soru") or t.get("ask") or soru or recap or (cumleler[-1] if cumleler else "")
    return _kisalt(secilen, BEKLEME_UZUNLUK)


def son_niyet(oturum: str) -> dict | None:
    """Bu oturumun en son niyet kaydı (hook bağlamına koymak için)."""
    son = None
    for k in L.jsonl_oku(NIYET_YOLU):
        if k.get("oturum") == oturum and k.get("tur") in ("niyet", "sonuc"):
            son = k
    return son


def son_baglam(oturum: str | None) -> str:
    """Bu oturumun son niyet kaydındaki `--baglam` değeri (yoksa '')."""
    k = son_niyet(oturum) if oturum else None
    return (k.get("baglam") or "") if k and k.get("tur") == "niyet" else ""


def baglam_metni(oturum: str | None) -> str:
    """UserPromptSubmit'te ana ajana verilen kısa hatırlatma."""
    k = son_niyet(oturum) if oturum else None
    kayitli = (f"Kayıtlı niyet: ne=\"{k.get('ne', '')}\" · neden=\"{k.get('neden', '')}\"" if k and k.get("tur") == "niyet"
               else "Bu sohbet için kayıtlı niyet yok.")
    return ("Orkestra niyet kaydı (kullanıcı birden çok sohbeti panelden izliyor). " + kayitli + " "
            "Bu istek YENİ bir iş başlatıyor ya da işi değiştiriyorsa, ilk araç çağrılarınla birlikte bir kez çalıştır: "
            "`orkestra niyet --ne \"<şu an ne yapılıyor, en çok 12 kelime>\" --neden \"<bu neye yarayacak, hangi hedefe hizmet ediyor; en çok 15 kelime>\"`. "
            "İstersen `--baglam \"<Proje/Süreç/Görev>\"` ekle (hangi proje/süreç/görev klasöründe çalışıldığı). "
            "Aynı işin devamıysa YAZMA. İş bitince: `orkestra niyet --sonuc \"<ne çıktı, en çok 15 kelime>\"`. "
            "Kullanıcıya bundan söz etme.")


# ---------------------------------------------------------------- görünüm

def _zaman(s):
    try:
        z = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return z if z.tzinfo else z.astimezone()
    except Exception:
        return None


def _basliklar(proje: str) -> dict:
    """Projenin sohbetleri: oturum → (kenar çubuğundaki ad, transkriptin son değişme zamanı); ork_lib önbelleğiyle."""
    try:
        sd = os.path.join(proje, ".claude", "orkestra")
        ls = L.sohbetler(sd if os.path.isdir(sd) else None, proje, limit=40, tahmin=False)
        return {s["oturum"]: (s["baslik"], s.get("son")) for s in ls}
    except Exception:
        return {}


def _gunluk_istekleri(proje: str, sinir: datetime.datetime) -> list[dict]:
    """Niyet kaydı başlamadan önceki sohbetler için orkestra günlüğündeki istekler (yedek)."""
    out = []
    for o in L.jsonl_oku(os.path.join(proje, ".claude", "orkestra", "gunluk.jsonl")):
        if o.get("tur") == "istek" and (_zaman(o.get("zaman")) or sinir) >= sinir and not str(o.get("metin", "")).startswith("<"):
            out.append({"zaman": o["zaman"], "oturum": o.get("oturum"), "proje": proje, "tur": "istek", "metin": o.get("metin")})
    return out


def _proje_adi(yol: str | None) -> str:
    return os.path.basename((yol or "").rstrip("\\/")) or (yol or "?")


def _kapanis(s: dict, bekleyen: str, n_acik: int, isler: list, simdi_z) -> dict:
    """Sohbet 'Kapatılabilir' mi: açık kart yok, alt ajan yok, niyet sonucu var, bağlı işin todo'su son turdan sonra güncel."""
    eksik = []
    if bekleyen == "claude":
        eksik.append("Claude çalışıyor")
    if n_acik:
        eksik.append(f"{n_acik} açık kart")
    proje = s.get("proje_yol")
    if proje:
        sd = os.path.join(proje, ".claude", "orkestra")
        var_denetci = var_diger = False
        for yol in glob.glob(os.path.join(sd, "oturumlar", "acik_ajan_*.json")):
            try:
                with open(yol, encoding="utf-8") as f:
                    k = json.load(f)
            except Exception:
                continue
            if k.get("oturum") != s.get("oturum"):
                continue
            if "denetci" in str(k.get("ajan") or "").lower():
                var_denetci = True
            else:
                var_diger = True
        if var_denetci:
            eksik.append("denetçi sürüyor")
        if var_diger:
            eksik.append("alt ajan sürüyor")
    if not (s.get("sonuc") or "").strip():
        eksik.append("niyet sonucu yok")
    z = _zaman(s.get("son_zaman"))
    if proje and z:
        sd = os.path.join(proje, ".claude", "orkestra")
        for i in isler:
            try:
                import is_kaydi as IK  # noqa: PLC0415
                kayit = IK.is_al(sd, i["id"])
                todo = IK._todo_dosyasi(kayit["klasor"]) if kayit else None
                if todo and os.path.getmtime(todo) < z.timestamp():
                    eksik.append(f"todo güncel değil ({i['id']})")
            except Exception:
                continue
    return {"kapatilabilir": not eksik, "eksik": eksik}


def gorunum(gun: int = GORUNUM_GUN) -> dict:
    simdi = datetime.datetime.now().astimezone()
    sinir = simdi - datetime.timedelta(days=gun)
    olaylar = [o for o in L.jsonl_oku(NIYET_YOLU) if (_zaman(o.get("zaman")) or sinir) >= sinir and not _gecici(o.get("proje"))]
    projeler = {o.get("proje") for o in olaylar if o.get("proje")}
    # orkestralı projelerin günlüğünden, niyet kaydı öncesi sohbetleri de getir
    if hasattr(L, "calisma_alanlari"):
        try:
            projeler |= {a["yol"] for a in L.calisma_alanlari() if a.get("orkestra")}
        except Exception:
            pass
    kayitli_oturum = {o.get("oturum") for o in olaylar}
    for p in list(projeler):
        olaylar += [o for o in _gunluk_istekleri(p, sinir) if o["oturum"] not in kayitli_oturum]
    olaylar.sort(key=lambda o: o.get("zaman") or "")

    oturumlar: dict = collections.OrderedDict()
    akis = []
    for o in olaylar:
        oid = o.get("oturum")
        s = oturumlar.setdefault(oid, {"oturum": oid, "proje_yol": o.get("proje"), "ne": None, "neden": None, "sonuc": None,
                                       "niyet_zamani": None, "son_istek": None, "son_olay": None, "son_zaman": None,
                                       "baslangic": o.get("zaman"), "istek_sayisi": 0, "kapandi": False, "hooklu": False,
                                       "arka_plan": False, "bekleme": None})
        s["proje_yol"] = s["proje_yol"] or o.get("proje")
        t = o.get("tur")
        s["hooklu"] = s["hooklu"] or t in ("tur", "kapandi", "niyet", "sonuc")
        if t == "niyet":
            if s["ne"] and (o.get("ne") != s["ne"]):
                akis.append({"zaman": s["niyet_zamani"], "oturum": oid, "proje_yol": s["proje_yol"], "tur": "onceki",
                             "ne": s["ne"], "neden": s["neden"], "sonuc": s["sonuc"]})
            s.update(ne=o.get("ne") or s["ne"], neden=o.get("neden") or s["neden"], niyet_zamani=o["zaman"], sonuc=None)
            akis.append({"zaman": o["zaman"], "oturum": oid, "proje_yol": s["proje_yol"], "tur": "niyet",
                         "ne": o.get("ne"), "neden": o.get("neden")})
        elif t == "sonuc":
            s["sonuc"] = o.get("sonuc")
            s["sonuc_zamani"] = o["zaman"]
            akis.append({"zaman": o["zaman"], "oturum": oid, "proje_yol": s["proje_yol"], "tur": "sonuc",
                         "ne": s["ne"], "sonuc": o.get("sonuc")})
        elif t == "istek":
            s["son_istek"] = o.get("metin") or s["son_istek"]
            s["istek_zamani"] = o["zaman"]
            s["istek_sayisi"] += 1
            s["kapandi"] = False
            s["arka_plan"] = False
            s["bekleme"] = None  # kullanıcı yanıtladı: eski bekleme nedeni geçersiz
        elif t == "tur":
            s["arka_plan"] = bool(o.get("arka_plan"))  # tur bitti ama arka planda iş sürüyor olabilir
            s["bekleme"] = o.get("bekleme") or None
        elif t == "kapandi":
            s["kapandi"] = True
        if t in ("istek", "tur", "kapandi", "niyet", "sonuc"):
            if t in ("istek", "tur", "kapandi"):
                s["son_olay"] = t
            s["son_zaman"] = o["zaman"]

    basliklar: dict = {}
    for p in {s["proje_yol"] for s in oturumlar.values() if s["proje_yol"]}:
        basliklar.update(_basliklar(p))
    kartlar: dict = collections.defaultdict(list)
    is_adlari: dict = {}  # (proje_yol, iş kimliği) → okunur iş adı; sohbet kartı bağlı işi bununla gösterir
    for p in {s["proje_yol"] for s in oturumlar.values() if s["proje_yol"]}:
        sd = os.path.join(p, ".claude", "orkestra")
        if os.path.isdir(sd):
            try:
                import is_kaydi as IK  # noqa: PLC0415
                for g in IK.is_liste(sd):
                    is_adlari[(p, g["id"])] = IK.is_adi(g.get("baslik", ""))
            except Exception:
                pass
            for k in L.kartlar(sd):
                d = L.kart_durumu_hesapla(k)
                if k.get("oturum") in oturumlar:
                    kartlar[k["oturum"]].append({"id": k["id"], "baslik": _kisalt(k.get("baslik"), 70), "durum": d, "is": k.get("is"),
                                                 "teslim_ozeti": _kisalt(k.get("teslim_ozeti"), 120)})

    try:
        masaustu = masaustu_oturumlari()
    except Exception:
        masaustu = {}
    try:
        yetim = _yetimler(oturumlar, masaustu)
    except Exception:
        yetim = {}
    satirlar = []
    for s in oturumlar.values():
        if s["oturum"] in yetim:
            asil = yetim[s["oturum"]]
            if not asil or asil in oturumlar:
                continue  # uygulamada karşılığı yok ya da asıl sohbet zaten listede: çift kart açma
            s["oturum"] = asil  # tıklama uygulamadaki asıl sohbete gitsin
        m = masaustu.get(s["oturum"]) or {}
        z = _zaman(s["son_zaman"])
        yas_gun = (simdi - z).total_seconds() / 86400 if z else 99
        acik_kart = [k for k in kartlar.get(s["oturum"], []) if k["durum"] in L.ACIK_DURUMLAR]
        baslik, transkript_son = basliklar.get(s["oturum"], (None, None))
        tz = _zaman(transkript_son)
        if tz and (not z or tz > z):
            z, s["son_zaman"] = tz, tz.isoformat(timespec="minutes")
            yas_gun = (simdi - z).total_seconds() / 86400
        bosta_dk = (simdi - z).total_seconds() / 60 if z else 9999
        if s["kapandi"]:
            bekleyen = "kapandi"
        elif (s["sonuc"] and (s.get("sonuc_zamani") or "") >= (s["niyet_zamani"] or "")
              and (s.get("sonuc_zamani") or "") >= (s.get("istek_zamani") or "")):  # sonuçtan sonra yeni istek geldiyse iş sürüyor
            bekleyen = "bitti"
        elif yas_gun >= ESKI_GUN:
            bekleyen = "beklemede"
        elif s["arka_plan"] and s["son_olay"] == "tur" and bosta_dk >= ARKA_PLAN_ZAMAN_ASIMI_DK:
            bekleyen = "beklemede"  # arka plan işi ölmüş olabilir: uzun süredir etkinlik yok
        elif s["arka_plan"] and s["son_olay"] == "tur":
            bekleyen = "claude"  # son turda arka plan işi var: Claude çalışmayı sürdürüyor
        elif (s["son_olay"] == "istek" or acik_kart) and (s["hooklu"] or bosta_dk < 10):
            bekleyen = "claude"  # hook'suz (eski) sohbette transkript 10 dk durgunsa Claude çalışmıyordur
        elif s["son_olay"] == "istek" and not s["hooklu"]:
            bekleyen = "beklemede"  # kancasız sohbet, istekten sonra 10 dk+ durgun: sıra kullanıcıda değil
        else:
            bekleyen = "sen"
        # niyet yazılmadıysa yedek: açık kart ya da son istek
        yedek = None
        if not s["ne"]:
            if acik_kart:
                yedek = acik_kart[0]["baslik"]
            elif kartlar.get(s["oturum"]):
                yedek = kartlar[s["oturum"]][-1]["baslik"]
            else:
                yedek = _kisalt(s["son_istek"], 110)
        satirlar.append({
            "oturum": s["oturum"], "kisa": (s["oturum"] or "")[:8], "proje": _proje_adi(s["proje_yol"]), "proje_yol": s["proje_yol"],
            "sohbet": m.get("baslik") or baslik or (s["oturum"] or "")[:8],
            "link": m.get("link"), "arsiv": bool(m.get("arsiv")),
            "devam": None if m.get("link") else f"claude --resume {s['oturum']}",
            "ne": s["ne"], "neden": s["neden"], "sonuc": s["sonuc"], "yedek": yedek, "niyet_var": bool(s["ne"]),
            "bekleyen": bekleyen, "bekleme": s["bekleme"] if bekleyen == "sen" else None, "son_zaman": s["son_zaman"], "baslangic": s["baslangic"], "istek_sayisi": s["istek_sayisi"],
            "son_istek": _kisalt(s["son_istek"], 160),
            "kartlar": {"acik": len(acik_kart), "toplam": len(kartlar.get(s["oturum"], [])),
                        "teslim": sum(1 for k in kartlar.get(s["oturum"], []) if k["durum"] == "teslim"),
                        "aktif": acik_kart[:3]},
            # sohbetin kartlarının bağlı olduğu işler (açık kartı olan iş önce); panel iş ↔ sohbet geçişinde kullanır
            "isler": [{"id": i, "ad": is_adlari.get((s["proje_yol"], i)) or i}
                      for i in dict.fromkeys([k["is"] for k in acik_kart if k.get("is")] +
                                             [k["is"] for k in kartlar.get(s["oturum"], []) if k.get("is")])],
        })
    satirlar = [r for r in satirlar if not r["arsiv"]]
    for r in satirlar:
        if r["bekleyen"] != "kapandi":
            r["kapanis"] = _kapanis(r, r["bekleyen"], r["kartlar"]["acik"], r["isler"], simdi)
    sira = {"sen": 0, "claude": 1, "bitti": 2, "beklemede": 3, "kapandi": 4}
    satirlar.sort(key=lambda r: (sira.get(r["bekleyen"], 9), -(_zaman(r["son_zaman"]) or sinir).timestamp()))
    for a in akis:
        a["proje"] = _proje_adi(a.get("proje_yol"))
        m = masaustu.get(a["oturum"]) or {}
        a["sohbet"] = m.get("baslik") or (basliklar.get(a["oturum"]) or (None,))[0] or (a["oturum"] or "")[:8]
        a["link"] = m.get("link")
    akis = sorted([a for a in akis if a["tur"] != "onceki"], key=lambda a: a["zaman"] or "", reverse=True)[:40]
    sayac = collections.Counter(r["bekleyen"] for r in satirlar)
    return {"uretim": L.simdi(), "oturumlar": satirlar, "akis": akis, "sayac": dict(sayac),
            "niyetsiz": sum(1 for r in satirlar if not r["niyet_var"] and r["bekleyen"] in ("sen", "claude"))}


# ---------------------------------------------------------------- komut satırı

def _oturum_projesi(oturum: str) -> str | None:
    """Oturumun projesi: hook'ların yazdığı kayıttan (Bash'in o anki klasörü proje olmayabilir), yoksa transkriptin yerinden."""
    for k in reversed(L.jsonl_oku(NIYET_YOLU)):
        if k.get("oturum") == oturum and k.get("tur") in ("istek", "tur") and k.get("proje"):
            return k["proje"]
    kok = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    for d in os.listdir(kok) if os.path.isdir(kok) else []:
        if os.path.exists(os.path.join(kok, d, oturum + ".jsonl")) and hasattr(L, "calisma_alanlari"):
            return next((a["yol"] for a in L.calisma_alanlari() if a["id"] == d), None)
    return None


def cmd(a) -> None:
    oturum = a.oturum or os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")
    if a.goster:
        g = gorunum()
        for r in g["oturumlar"]:
            print(f"[{r['bekleyen']}] {r['proje']} · {r['sohbet']}: {r['ne'] or r['yedek'] or '-'}"
                  + (f" → {r['neden']}" if r["neden"] else "") + (f" ✓ {r['sonuc']}" if r["sonuc"] else ""))
        return
    ana = getattr(a, "ajan_id", None) == "ana" or getattr(a, "ajan_tipi", None) == "ana"
    if getattr(a, "ajan_id", None) and not ana:
        sys.exit("niyet: yalnız ana ajan yazar (alt ajanlar kart özetini kullanır).")
    if not oturum:
        sys.exit("niyet: oturum kimliği bulunamadı (CLAUDE_CODE_SESSION_ID yok); --oturum ver.")
    proje = _oturum_projesi(oturum) or L.proje_dizini()
    if a.ne or a.neden:
        if not (a.ne and a.neden):
            sys.exit("niyet: --ne ile --neden birlikte verilir.")
        olay(oturum, proje, "niyet", ne=_kisalt(a.ne, 140), neden=_kisalt(a.neden, 160),
             baglam=_kisalt(getattr(a, "baglam", None), 200))
    if a.sonuc:
        olay(oturum, proje, "sonuc", sonuc=_kisalt(a.sonuc, 160))
    if not (a.ne or a.sonuc):
        sys.exit("niyet: --ne/--neden ya da --sonuc ver (göstermek için --goster).")
    print("niyet kaydedildi")


def ekle_ayristirici(alt) -> None:
    p = alt.add_parser("niyet", help="sohbetin şu an ne yaptığını ve neye yarayacağını kaydet (panel 'Şu an' şeridi)")
    p.add_argument("--ne", help="şu an ne yapılıyor (≤12 kelime)")
    p.add_argument("--neden", help="neye yarayacak, hangi hedefe hizmet ediyor (≤15 kelime)")
    p.add_argument("--baglam", help="isteğe bağlı: çalışılan klasör bağlamı 'Proje/Süreç/Görev' (maliyet/defter kayıtlarında yedek)")
    p.add_argument("--sonuc", help="iş bitince ne çıktı (≤15 kelime)")
    p.add_argument("--oturum", help="oturum kimliği (varsayılan: CLAUDE_CODE_SESSION_ID)")
    p.add_argument("--goster", action="store_true", help="bütün sohbetlerin şu anki durumunu yaz")
    p.set_defaults(f=cmd)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="niyet")
    alt = ap.add_subparsers()
    ekle_ayristirici(alt)
    a = ap.parse_args(["niyet"] + sys.argv[1:])
    a.f(a)
