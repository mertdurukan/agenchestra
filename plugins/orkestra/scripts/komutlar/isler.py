"""orkestra komutları: isler (orkestra.py bölünmesinden)."""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import hashlib
import os
import re
import subprocess
import sys
import time

import ork_lib as L  # noqa: E402
import ret_nedeni as RN  # noqa: E402
from komutlar._ortak import hata, oturum_id, sd_gerekli  # noqa: E402


def _ik():
    import is_kaydi
    return is_kaydi


def _oturum_dosyasi(sd, kenar=False):
    ad = ("is_" if kenar else "") + oturum_id() + ".json"
    return os.path.join(sd, "oturumlar", ad)


def _json_oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _oturum_isi(sd):
    """Bu oturumun bağlı işi: önce oturum dosyası, yoksa Stop hook'unun ezmediği yan dosya."""
    return _json_oku(_oturum_dosyasi(sd)).get("is") or _json_oku(_oturum_dosyasi(sd, True)).get("is")


def _oturumu_bagla(sd, is_id):
    """Oturum dosyasındaki mevcut anahtarlar korunur (oku-birleştir-yaz, kilitli); is.json oturumlar[]'a eklenir."""
    an = L.simdi()
    yol = _oturum_dosyasi(sd)  # eski is_<oturum>.json yan dosyası yalnız okunur, yeniden yazılmaz
    with L.kilit(yol):
        v = _json_oku(yol)
        v["is"] = is_id
        v["is_baglanma"] = an
        v.setdefault("is_gecmis", []).append({"is": is_id, "zaman": an})
        L.atomik_yaz(yol, json.dumps(v, ensure_ascii=False, indent=2) + "\n")
    _ik().is_oturum_bagla(sd, is_id, oturum_id())


def _is_gerekli(sd, is_id):
    try:
        kayit = _ik().is_al(sd, is_id)
    except ValueError as e:
        hata(str(e))
    if not kayit:
        hata(f"iş yok: {is_id}")
    return kayit


def _todo_satiri(klasor):
    t = _ik().todo_ozet(klasor)
    return t, f"todo {t['biten']}/{t['toplam']}"


def cmd_is_ac(a):
    sd = sd_gerekli()
    kayit = _ik().is_ac(sd, a.baslik, a.klasor, a.etiket)
    _oturumu_bagla(sd, kayit["id"])
    print(kayit["id"])


def cmd_is_devam(a):
    sd = sd_gerekli()
    kayit = _is_gerekli(sd, a.is_id)
    _oturumu_bagla(sd, a.is_id)
    klasor = kayit["klasor"]
    t, satir = _todo_satiri(klasor)
    print(f"{a.is_id} — {kayit['baslik']} [{kayit['durum']}]")
    print(f"plan: {os.path.join(klasor, 'plan.md')}")
    print(satir)
    for m in t["acik_maddeler"]:
        print(f"  [ ] {m}")
    son = ""
    yol = os.path.join(klasor, "oturumlar.md")
    if os.path.exists(yol):
        with open(yol, encoding="utf-8", errors="replace") as f:
            dolu = [s.rstrip() for s in f if s.strip()]
        son = dolu[-1] if len(dolu) > 1 else ""  # ilk satır başlık
    print(f"oturumlar.md son satır: {son or '(henüz yok)'}")


def cmd_is_liste(a):
    sd = sd_gerekli()
    ik = _ik()
    satirlar = []
    for g in ik.is_liste(sd, None if a.durum == "hepsi" else a.durum):
        kayit = ik.is_al(sd, g["id"]) or {}
        _, todo = _todo_satiri(g["klasor"])
        satirlar.append([g["id"], g.get("durum", "-"), g.get("baslik", ""), todo.replace("todo ", ""),
                         str(len(kayit.get("kartlar", []))), str(len(kayit.get("oturumlar", []))), g["klasor"]])
    if not satirlar:
        print("iş yok")
        return
    print("\t".join(["id", "durum", "baslik", "todo", "kart", "oturum", "klasor"]))
    for s in satirlar:
        print("\t".join(s))


def cmd_is_rapor(a):
    import is_rapor as IR
    sd = sd_gerekli()
    if a.is_id:
        d = IR.detay(sd, a.is_id)
        if d is None:
            hata(f"iş yok: {a.is_id}")
        print(IR.metin_detay(d))
        return
    r = IR.rapor(sd)
    if a.csv:
        t = IR.csv_metni(r)
        if a.cikti:
            with open(a.cikti, "w", encoding="utf-8", newline="") as f:
                f.write(t)
            print(f"yazıldı: {a.cikti}")
        else:
            sys.stdout.write(t)
        return
    print(IR.metin(r))


def cmd_is_kapat(a):
    sd = sd_gerekli()
    _is_gerekli(sd, a.is_id)
    _ik().is_durum(sd, a.is_id, "kapandi")
    print(f"{a.is_id} → kapandi")


TODO_KISA = 100  # --ekle/--bitti sonrası açık madde satırı en çok bu kadar karakter (numaralı; --bitti <n> ile aynı sıra)


def cmd_is_todo(a):
    sd = sd_gerekli()
    kayit = _is_gerekli(sd, a.is_id)
    ekle, bitti, not_ = getattr(a, "ekle", None), getattr(a, "bitti", None), getattr(a, "not_", None)
    if ekle is not None and bitti is not None:
        hata("--ekle ve --bitti birlikte verilemez.")
    if not_ is not None and bitti is None:
        hata("--not yalnız --bitti ile kullanılır.")
    if ekle is not None or bitti is not None:
        if ekle is not None and kayit.get("durum") == "kapandi":
            hata(f"{a.is_id} kapalı; --ekle yapılamaz.")
        try:
            if ekle is not None:
                _ik().todo_ekle(kayit["klasor"], ekle)
            else:
                _ik().todo_bitir(kayit["klasor"], bitti, not_)
        except (ValueError, OSError, TimeoutError) as e:
            hata(str(e))
    t, satir = _todo_satiri(kayit["klasor"])
    print(f"{a.is_id} {satir}")
    yazildi = ekle is not None or bitti is not None
    for n, m in enumerate(t["acik_maddeler"], 1):
        if yazildi and len(m) > TODO_KISA:  # yazma sonrası kısa liste: ana ajan bağlamına her seferinde tüm todo girmesin
            m = m[:TODO_KISA - 1] + "…"
        print(f"  {n}. [ ] {m}" if yazildi else f"  [ ] {m}")


def cmd_is_todo_denetle(a):
    sd = sd_gerekli()
    r = _ik().todo_denetle(sd, getattr(a, "kok", None))
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return None
    if not r:
        print("todo denetimi: işe bağlı olmayan todo dosyası yok")
        return None
    print(f"todo denetimi: {len(r)} dosya işe bağlı değil")
    for x in r:
        print(f"  [{x['tur']}] {_goreli(x['yol'])}")
    return None


def cmd_is_serit(a):
    sd = sd_gerekli()
    _is_gerekli(sd, a.is_id)
    s = _ik().is_serit(sd, a.is_id)
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return
    i, p = s["is"], s["ilerleme"]
    print(f"{i['id']} — {i['baslik']}  [{p['biten']}/{p['toplam']}]")
    for kova, baslik in (("yapildi", "✔ Yapıldı"), ("simdi", "◐ Şimdi"),
                         ("sirada", "○ Sırada"), ("planda_kart_yok", "◌ Planda, kart yok")):
        if not s[kova]:
            continue
        print(baslik)
        for o in s[kova]:
            if o["tur"] == "kart":
                adim, son = o["adim"], f"  ({o['kart']})"
                if o["bekledigi"]:
                    son += " ← " + ", ".join(o["bekledigi"])
            else:
                adim, son = (o["adimlar"][0] if o["adimlar"] else None), ""
            metin = o["metin"]
            if kova != "yapildi" and adim and metin.startswith(adim) and (len(metin) == len(adim) or metin[len(adim)] in " :"):
                metin = metin[len(adim):].lstrip(" :")
            print("  " + (f"{adim}  " if adim else "") + metin + son)
    if s["iptal"]:
        print(f"⊘ İptal ({len(s['iptal'])})")


def cmd_is_aktif(a):
    sd = sd_gerekli()
    i = _oturum_isi(sd)
    if not i:
        print("bağlı iş yok")
        return
    kayit = _ik().is_al(sd, i)
    print(f"{i} — {kayit['baslik']} [{kayit['durum']}]" if kayit else i)


def _alan_listesi(v):
    if isinstance(v, str):
        return [v]
    return [x for x in (v or []) if isinstance(x, str)]


def _gorev_klasoru(sd, yazma, test):
    """Yazma + test alanı yollarından çözülen bağlam GÖREV düzeyindeyse görev klasörünün mutlak yolu; yoksa None."""
    import baglam as B
    esleme = B.esleme_oku(sd)
    if not esleme:
        return None
    proje = L.proje_dizini()
    b = B.coz(esleme, proje, _alan_listesi(yazma), _alan_listesi(test))
    parcalar = [p for p in b.split("/") if p]
    if len(parcalar) < 2 or not B._desen_uyar(esleme.get("gorev_deseni"), parcalar[-1]):
        return None
    return os.path.join(proje, *parcalar)


def _gorev_isi(sd, klasor, olustur):
    """Görev klasörünün açık işi; yoksa (olustur) yeni iş açar. Klasörde kapalı iş/yetim is.json varsa None (ezilmez)."""
    ik = _ik()
    i = ik.is_klasorle_bul(sd, klasor)
    if i:
        return i
    if not olustur or ik.is_klasorle_bul(sd, klasor, True) or os.path.exists(os.path.join(klasor, "is.json")):
        return None
    return ik.is_ac(sd, os.path.basename(klasor), klasor)["id"]


def _acik_is_dogrula(sd, acik_is):
    """--is / plan 'is' verilmişse iş var olmalı (yoksa hata). Kapalı olması hata değildir: kart açık bir işe bağlanır."""
    if acik_is:
        _is_gerekli(sd, acik_is)


def _goreli(yol):
    """Proje köküne göre göreli gösterim (dışarıdaysa mutlak); yalnız ileti için."""
    try:
        r = os.path.relpath(yol, L.proje_dizini())
    except ValueError:
        r = ".."
    return (yol if r.startswith("..") else r).replace("\\", "/")


def _is_kaydi_guvenli(sd, i):
    try:
        return _ik().is_al(sd, i) if i else None
    except Exception:
        return None


def _bilinen_is_klasorleri(sd, derinlik=3):
    """is.json bulunan klasörler: baglam.json projeleri (Proje/Süreç/Görev, en çok `derinlik` düzey; gizli ve haric
    dizinler atlanır) ve <durum dizini>/isler. Merkez yok/bozukken yeniden kurulum ve sayaç için kullanılır."""
    import baglam
    proje = L.proje_dizini()
    esleme = baglam.esleme_oku(sd) or {}
    haric = {str(h).casefold() for h in esleme.get("haric") or []}
    kokler = [os.path.join(sd, "isler")]
    if proje:
        kokler += [os.path.normpath(os.path.join(proje, str(p))) for p in esleme.get("projeler") or [] if str(p).strip()]
    bulunan, gorulen = [], set()
    for kok in kokler:
        if not os.path.isdir(kok):
            continue
        for yol, dizinler, dosyalar in os.walk(kok):
            goreli = os.path.relpath(yol, kok)
            if (0 if goreli == "." else goreli.count(os.sep) + 1) >= derinlik:
                dizinler[:] = []
            else:
                dizinler[:] = [d for d in dizinler if not d.startswith(".") and d.casefold() not in haric]
            anahtar = os.path.normcase(os.path.abspath(yol))
            if "is.json" in dosyalar and anahtar not in gorulen:
                gorulen.add(anahtar)
                bulunan.append(os.path.abspath(yol))
    return bulunan


def _merkez_saglamla(sd):
    """K2: isler.json bozuksa yedeğe alınır; yoksa/yedeklendiyse bilinen is.json'lardan yeniden kurulur. Hata vermez."""
    ik = _ik()
    try:
        if os.path.exists(os.path.join(sd, "isler.json")) and not ik.merkez_bozuk_mu(sd):
            return
        r = ik.merkez_kurtar(sd, _bilinen_is_klasorleri(sd))
    except Exception as e:  # kurtarma kart oluşturmayı asla durdurmaz
        print(f"orkestra: uyarı: isler.json kurtarılamadı ({e})", file=sys.stderr)
        return
    if r.get("yedek"):
        print(f"orkestra: uyarı: isler.json bozuktu; {_goreli(r['yedek'])} olarak yedeklendi, "
              f"{len(r.get('farklar') or [])} kayıtla yeniden kuruldu", file=sys.stderr)


def _yeni_is(sd, baslik, klasor, uygula):
    """Klasörde iş açar (uygula değilse yalnız planlar). Klasör açılamazsa <durum dizini>/isler altında sıradaki NNN denenir."""
    if not uygula:
        return {"is": None, "klasor": klasor, "yeni": True}
    ik = _ik()
    try:
        return {"is": ik.is_ac(sd, baslik, klasor)["id"], "klasor": klasor, "yeni": True}
    except OSError as e:
        kok = os.path.join(sd, "isler")
        yedek = os.path.join(kok, ik.sonraki_klasor_adi(kok, baslik))
        print(f"orkestra: uyarı: {_goreli(klasor)} açılamadı ({e}); {_goreli(yedek)} kullanılıyor", file=sys.stderr)
        return {"is": ik.is_ac(sd, baslik, yedek)["id"], "klasor": yedek, "yeni": True}


def _is_coz(sd, baslik, yazma, onbellek, uygula=True):
    """K1 (c)/(d): yazma alanının ilk girdisi baglam.json ile Proje[/Süreç]/Görev klasörüne çözülür.

    (c) görev klasöründe açık iş varsa o; is.json yoksa orada yeni iş.
    (d) görev klasörü yoksa (ya da işi kapalıysa) çözülen kökte — çözülmezse eşlemedeki ilk projede,
        eşleme de yoksa <durum dizini>/isler altında — sıradaki NNN-YYYYMMDD-<slug> klasöründe yeni iş.
    onbellek aynı komutta aynı klasöre çözülen kartları tek işe toplar. Hata vermez.
    Dönüş: {"is": id|None (kuru koşuda yeni iş), "klasor", "yeni", "kaynak", "notlar"}.
    """
    import baglam
    ik = _ik()
    proje = L.proje_dizini()
    esleme = baglam.esleme_oku(sd)
    notlar = []
    c = baglam.klasor_coz(esleme, proje, yazma[0]) if yazma else None
    if c:
        kok, gorev = c
        kaynak = "yazma_alani"
    else:
        projeler = [str(p) for p in ((esleme or {}).get("projeler") or []) if str(p).strip()]
        # eşleme yoksa iş klasörü proje ağacını kirletmesin: durum dizininde (çoğunlukla git dışı) tutulur
        kok = os.path.normpath(os.path.join(proje, projeler[0])) if projeler else os.path.join(sd, "isler")
        gorev = None
        kaynak = "ilk proje" if projeler else "eşleme yok"

    def onbellekten(anahtar):
        r = onbellek.get(anahtar)
        if r is None:
            return None
        r = dict(r, kaynak=kaynak, notlar=notlar)
        if uygula:
            r["yeni"] = False
        return r

    if gorev:
        anahtar = "g:" + os.path.normcase(os.path.abspath(gorev))
        r = onbellekten(anahtar)
        if r:
            return r
        kayit = ik.is_klasorden(sd, gorev)
        if kayit is None:  # is.json geçerli ama merkezde kayıtlı değilse merkeze kaydedilir (kimlik çakışmıyorsa)
            kayit = ik.yetim_kaydet(sd, gorev, uygula)
            if kayit:
                notlar.append(f"{_goreli(gorev)}/is.json merkeze " + ("kaydedildi" if uygula else "kaydedilecek"))
        if kayit and kayit.get("durum") != "kapandi":
            r = {"is": kayit["id"], "klasor": gorev, "yeni": False}
        elif not os.path.exists(os.path.join(gorev, "is.json")):
            r = _yeni_is(sd, os.path.basename(gorev), gorev, uygula)
        else:
            notlar.append(f"{_goreli(gorev)} işi kapalı" if kayit
                          else f"{_goreli(gorev)}/is.json geçersiz ya da kimliği merkezde başka klasöre ait")
        if r:
            onbellek[anahtar] = r
            return dict(r, kaynak=kaynak, notlar=notlar)
    anahtar = "k:" + os.path.normcase(os.path.abspath(kok))
    r = onbellekten(anahtar)
    if r:
        return r
    r = _yeni_is(sd, baslik or "is", os.path.join(kok, ik.sonraki_klasor_adi(kok, baslik)), uygula)
    onbellek[anahtar] = r
    return dict(r, kaynak=kaynak, notlar=notlar)


def _bag_aciklamasi(r):
    m = f"{r['kaynak']}: {_goreli(r['klasor'])}" + (", yeni iş" if r.get("yeni") else "")
    return m + "".join(f"; {n}" for n in r.get("notlar") or [])


def _bag_satiri(gid, is_id, aciklama):
    """K5: bağın hangi yoldan kurulduğu — kart başına tek satır, stderr (stdout biçimi değişmez)."""
    print(f"orkestra: {gid} → {is_id} ({aciklama})", file=sys.stderr)


def _kart_is_bag_kur(sd, gid, baslik, yazma, acik_is=None, onbellek=None):
    """Kartın işi — asla boş dönmez, bağ yüzünden ret vermez (var olmayan açık kimlik dışında).

    (a) --is / plan 'is' açıksa o; (b) oturumun açık işi; (c)/(d) `_is_coz`. Otomatik bulunan ya da açılan iş
    oturuma bağlanır (bu noktada oturumun açık işi yoktur)."""
    onbellek = {} if onbellek is None else onbellek
    notlar = []
    if acik_is:
        if _is_gerekli(sd, acik_is).get("durum") != "kapandi":
            _bag_satiri(gid, acik_is, "--is")
            return acik_is
        notlar.append(f"{acik_is} kapalı")
    i = _oturum_isi(sd)
    kayit = _is_kaydi_guvenli(sd, i)
    if kayit and kayit.get("durum") != "kapandi":
        _bag_satiri(gid, i, "oturum işi" + "".join(f"; {n}" for n in notlar))
        return i
    if kayit:
        notlar.append(f"oturum işi {i} kapalı")
    r = _is_coz(sd, baslik, yazma, onbellek, True)
    r["notlar"] = notlar + r["notlar"]
    _oturumu_bagla(sd, r["is"])
    _bag_satiri(gid, r["is"], _bag_aciklamasi(r))
    return r["is"]


def _kart_no(gid):
    try:
        return int(str(gid).split("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def _sahipsiz_kartlar(sd, uygula):
    """K7: 'is' alanı boş kartlar; kuru koşu yalnız önerir (dosya yazmaz, oturum bağlamaz), --uygula bağlar."""
    sahipsiz = sorted((k for k in L.kartlar(sd) if not k.get("is")), key=lambda k: _kart_no(k["id"]))
    if not sahipsiz:
        print("sahipsiz kart yok")
        return
    if uygula:
        _merkez_saglamla(sd)
    onbellek = {}
    baglanan = 0
    for k in sahipsiz:
        r = _is_coz(sd, k.get("baslik") or "", list(k.get("yazma_alani") or []), onbellek, uygula)
        if uygula:
            with L.kilit(L.kart_yolu(sd, k["id"])):
                guncel = L.kart_oku(sd, k["id"])
                if guncel and not guncel.get("is"):
                    guncel["is"] = r["is"]
                    L.kart_yaz(sd, guncel)
                    _ik().is_kart_ekle(sd, r["is"], k["id"])
                    baglanan += 1
        print(f"{k['id']} → {r['is'] or 'yeni iş'} ({_bag_aciklamasi(r)})")
    if uygula:
        print(f"{baglanan} sahipsiz kart işe bağlandı")
    else:
        print(f"{len(sahipsiz)} sahipsiz kart; bağlamak için --uygula")


def cmd_is_bagla(a):
    sd = sd_gerekli()
    if not a.geriye:
        hata("şimdilik yalnız `orkestra is bagla --geriye [--uygula]` var.")
    ik = _ik()
    satirlar = []
    acik_isler = None
    for k in L.kartlar(sd):
        gid = k["id"]
        yeni_is, neden, yeni_klasor = None, None, None
        if not k.get("is"):
            klasor = _gorev_klasoru(sd, k.get("yazma_alani"), k.get("test_alani"))
            if klasor:
                i = ik.is_klasorle_bul(sd, klasor)
                if i:
                    yeni_is, neden = i, "baglam"
                elif not ik.is_klasorle_bul(sd, klasor, True) and not os.path.exists(os.path.join(klasor, "is.json")):
                    yeni_klasor = klasor
                    neden = "baglam"
            if not yeni_is and not yeni_klasor and k.get("oturum"):
                if acik_isler is None:
                    acik_isler = [(g["id"], ik.is_al(sd, g["id"]) or {}) for g in ik.is_liste(sd) if g.get("durum") != "kapandi"]
                for iid, kayit in acik_isler:
                    if any(o.get("oturum") == k["oturum"] for o in kayit.get("oturumlar", [])):
                        yeni_is, neden = iid, "oturum"
                        break
        adim = ik.adim_coz(k.get("baslik"))
        adim_eksik = bool(adim) and not k.get("adim")
        if not (yeni_is or yeni_klasor or adim_eksik):
            continue
        if a.uygula:
            if yeni_klasor:
                yeni_is = _gorev_isi(sd, yeni_klasor, True)
            with L.kilit(L.kart_yolu(sd, gid)):
                guncel = L.kart_oku(sd, gid) or k
                degisti = False
                if yeni_is and not guncel.get("is"):
                    guncel["is"] = yeni_is
                    degisti = True
                else:
                    yeni_is = None
                if adim_eksik and not guncel.get("adim"):
                    guncel["adim"] = adim
                    degisti = True
                if degisti:
                    L.kart_yaz(sd, guncel)
            if yeni_is:
                ik.is_kart_ekle(sd, yeni_is, gid)
        if yeni_is or yeni_klasor:
            hedef = yeni_is or f"(yeni iş: {os.path.basename(yeni_klasor)})"
            satirlar.append(f"{gid} → {hedef} ({neden})")
        if adim_eksik:
            satirlar.append(f"{gid} adim={adim}")
    if not satirlar:
        print("fark yok")
        return
    for m in satirlar:
        print(m)
    if not a.uygula:
        print(f"{len(satirlar)} fark; uygulamak için --uygula")


def cmd_is_onar(a):
    sd = sd_gerekli()
    if a.kartlar:
        _sahipsiz_kartlar(sd, a.uygula)
        return
    r = _ik().onar(sd, a.klasor, a.uygula)
    for m in r["farklar"]:
        print(m)
    for m in r["uyarilar"]:
        print(f"uyarı: {m}", file=sys.stderr)
    if not r["farklar"]:
        print("fark yok")
    elif a.uygula:
        print(f"isler.json onarıldı ({len(r['farklar'])} fark)")
    else:
        print(f"{len(r['farklar'])} fark; uygulamak için --uygula")


def _kart_is_bagla(sd, k):
    if k.get("is"):
        _ik().is_kart_ekle(sd, k["is"], k["id"])


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    is_ = alt.add_parser("is", help="kalıcı iş katmanı (bir iş birden çok sohbete/karta yayılır)").add_subparsers(dest="alt", required=True)
    ia = is_.add_parser("ac")
    ia.add_argument("baslik")
    ia.add_argument("--klasor", required=True)
    ia.add_argument("--etiket", action="append", default=[])
    ia.set_defaults(f=cmd_is_ac)
    idv = is_.add_parser("devam")
    idv.add_argument("is_id")
    idv.set_defaults(f=cmd_is_devam)
    il = is_.add_parser("liste")
    il.add_argument("--durum", choices=["acik", "beklemede", "kapandi", "hepsi"], default="acik")
    il.set_defaults(f=cmd_is_liste)
    irp = is_.add_parser("rapor", help="iş başına maliyet/süre/kalite raporu (salt okuma)")
    irp.add_argument("is_id", nargs="?")
    irp.add_argument("--csv", action="store_true")
    irp.add_argument("--cikti", metavar="DOSYA", help="--csv çıktısını dosyaya yaz")
    irp.set_defaults(f=cmd_is_rapor)
    ik_ = is_.add_parser("kapat")
    ik_.add_argument("is_id")
    ik_.set_defaults(f=cmd_is_kapat)
    it_ = is_.add_parser("todo")
    it_.add_argument("is_id")
    it_.add_argument("--ekle", metavar="METİN", help="todo.md sonuna açık madde ekler")
    it_.add_argument("--bitti", metavar="SEÇİCİ", help="açık maddeyi [x] yapar (sıra no ya da alt dize)")
    it_.add_argument("--not", dest="not_", metavar="METİN", help="--bitti ile satır sonuna tarihli not")
    it_.set_defaults(f=cmd_is_todo)
    itd = is_.add_parser("todo-denetle", help="isler.json'a bağlı olmayan todo.md kopyalarını ve worktree kopyalarını listeler (salt okuma)")
    itd.add_argument("--kok", help="taranacak dizin (varsayılan: proje)")
    itd.add_argument("--json", action="store_true")
    itd.set_defaults(f=cmd_is_todo_denetle)
    isr = is_.add_parser("serit", help="iş şeridi: yapıldı/şimdi/sırada/planda kart yok")
    isr.add_argument("is_id")
    isr.add_argument("--json", action="store_true")
    isr.set_defaults(f=cmd_is_serit)
    is_.add_parser("aktif").set_defaults(f=cmd_is_aktif)
    io_ = is_.add_parser("onar", help="isler.json'u iş klasörlerindeki is.json'lardan yeniden kur (varsayılan kuru koşu)")
    io_.add_argument("--uygula", action="store_true", help="farkları isler.json'a yaz")
    io_.add_argument("--klasor", action="append", default=[], help="ek iş klasörü (tekrarlanabilir)")
    io_.add_argument("--kartlar", action="store_true",
                     help="'is' alanı boş kartları listele ve önerilen işi yaz (--uygula ile bağla, gerekirse iş/klasör aç)")
    io_.set_defaults(f=cmd_is_onar)
    ib_ = is_.add_parser("bagla", help="iş alanı boş kartları görev klasörü/oturum işine bağla (varsayılan kuru koşu)")
    ib_.add_argument("--geriye", action="store_true", help="mevcut kartları geriye dönük bağla")
    ib_.add_argument("--uygula", action="store_true", help="değişiklikleri yaz")
    ib_.set_defaults(f=cmd_is_bagla)
