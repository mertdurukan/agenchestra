"""Oturum worktree'lerindeki ayrışmış orkestra durum kopyalarını ana durum klasörüne devralır (ADR-0032, I-156 P3).

Neden: Claude her oturum için git dışı `.claude/orkestra` klasörünü worktree'ye kopyalar; `ork_lib.proje_dizini` artık
worktree'den ana ağaca çözüldüğü için YENİ kayıtlar ana klasöre gider, ama çözüm gelmeden önce kopyaya yazılanlar
(günlük, defter, maliyet, atıf, iş kaydı, onay) ağaç silinince kaybolurdu.

Kurallar (yalnız ekler; hedefte var olanı değiştirmez, kopyayı silmez):
- jsonl dosyaları: hedefte olmayan satırlar (tam satır eşliği) sona eklenir.
- isler.json: hedefte kimliği olmayan iş eklenir; aynı klasörü gösteren iş aynı iştir (atlanır); kimlik aynı ama klasör
  farklıysa ÇAKIŞMA sayılır, yazılmaz, raporlanır. Sayaç en büyük kimliğin altına düşmez.
- onaylar/, oturumlar/, gorevler/ altında hedefte olmayan dosya kopyalanır; aynı ad farklı içerik ÇAKIŞMA sayılır.
Uygulamadan önce `yedek/devral_<zaman>/` altına isler.json ve jsonl boyutları yazılır; kaynakta `.devralindi` damgası kalır.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

JSONL = ("gunluk.jsonl", "ortak_defter.jsonl", "maliyet.jsonl", "maliyet_duzeltme.jsonl", "atif.jsonl", "zaman.jsonl")
DOSYA_KLASORLERI = ("onaylar", "oturumlar", "gorevler")
DAMGA = ".devralindi"
GORULEN = "gorulen.json"  # onaylar/ altında {kimlik: zaman} haritası
_KILIT_DOSYASI = re.compile(r"\.lock$|^\.tmp_|\.zaman_asimi\.log$|^\.islem\.")


def _oku_json(yol: str, varsayilan):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return varsayilan


def _satirlar(yol: str) -> list[str]:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return [s.rstrip("\r\n") for s in f if s.strip()]
    except OSError:
        return []


def _is_no(kimlik: str) -> int:
    m = re.search(r"(\d+)$", str(kimlik))
    return int(m.group(1)) if m else 0


def _ayni_yol(a: str, b: str) -> bool:
    n = lambda x: os.path.normcase(os.path.realpath(str(x))).replace("\\", "/").rstrip("/")  # noqa: E731
    return n(a) == n(b)


def kaynaklar(hedef: str, cwd: str | None = None, tum: bool = False, kaynak: str | None = None) -> list[str]:
    """Devralınacak durum klasörleri: `kaynak` verilmişse o; `tum` ise deponun öteki tüm ağaçları; yoksa cwd'nin ağacı."""
    if kaynak:
        return [os.path.abspath(kaynak)]
    cwd = cwd or os.getcwd()
    ust = L.git_koku(cwd)
    if not ust:
        return []
    adaylar = []
    if tum:
        r = L.git(["worktree", "list", "--porcelain"], ust)
        for s in (r.stdout.splitlines() if r.returncode == 0 else []):
            if s.startswith("worktree "):
                adaylar.append(s[len("worktree "):].strip())
    else:
        adaylar.append(ust)
    out = []
    for w in adaylar:
        sd = os.path.join(w, ".claude", "orkestra")
        if os.path.isdir(sd) and not _ayni_yol(sd, hedef):
            out.append(sd)
    return out


def planla(kaynak: str, hedef: str) -> dict:
    """Salt okuma: hedefte olmayan öğeleri sayar. {jsonl:{ad:[satır]}, isler:[(id,kayıt)], cakisma:[metin], dosyalar:[(klasör,ad)]}"""
    plan = {"jsonl": {}, "isler": [], "cakisma": [], "dosyalar": [], "takma": {}, "sayac": None, "gorulen": {}}
    for ad in JSONL:
        hedef_set = set(_satirlar(os.path.join(hedef, ad)))
        yeni = [s for s in _satirlar(os.path.join(kaynak, ad)) if s not in hedef_set]
        if yeni:
            plan["jsonl"][ad] = yeni
    k_is = _oku_json(os.path.join(kaynak, "isler.json"), {})
    h_is = _oku_json(os.path.join(hedef, "isler.json"), {})
    h_kayitlar = h_is.get("isler") or {}
    h_klasorler = {os.path.normcase(str(v.get("klasor") or "")) for v in h_kayitlar.values() if isinstance(v, dict)}
    for kimlik, kayit in sorted((k_is.get("isler") or {}).items(), key=lambda x: _is_no(x[0])):
        if not isinstance(kayit, dict):
            continue
        klasor = os.path.normcase(str(kayit.get("klasor") or ""))
        if kimlik in h_kayitlar:
            if os.path.normcase(str(h_kayitlar[kimlik].get("klasor") or "")) != klasor:
                plan["cakisma"].append(f"iş {kimlik}: hedefte başka klasör ({h_kayitlar[kimlik].get('klasor')}), kaynakta {kayit.get('klasor')}")
        elif klasor and klasor in h_klasorler:
            continue  # aynı iş başka kimlikle zaten var
        else:
            plan["isler"].append((kimlik, kayit))
    for k, v in (k_is.get("takma") or {}).items():
        if k not in (h_is.get("takma") or {}):
            plan["takma"][k] = v
    en_buyuk = max([_is_no(k) for k, _ in plan["isler"]] + [_is_no(k) for k in h_kayitlar] + [0])
    if en_buyuk > int(h_is.get("sayac", 0) or 0):
        plan["sayac"] = en_buyuk
    for klasor in DOSYA_KLASORLERI:
        kdir, hdir = os.path.join(kaynak, klasor), os.path.join(hedef, klasor)
        try:
            adlar = sorted(os.listdir(kdir))
        except OSError:
            continue
        for ad in adlar:
            yol = os.path.join(kdir, ad)
            if not os.path.isfile(yol) or _KILIT_DOSYASI.search(ad):
                continue
            h = os.path.join(hdir, ad)
            if ad == GORULEN and klasor == "onaylar":
                eksik = {k: v for k, v in _oku_json(yol, {}).items() if k not in _oku_json(h, {})}
                if eksik:
                    plan["gorulen"] = eksik  # "görüldü" işaretleri birleşir; çakışma sayılmaz
                continue
            if not os.path.exists(h):
                plan["dosyalar"].append((klasor, ad))
            else:
                with open(yol, "rb") as f1, open(h, "rb") as f2:
                    if f1.read() != f2.read():
                        # oturum ve onay kayıtları işlem boyunca güncellenir: yalnız onaylar/ ve gorevler/ çakışma sayılır
                        if klasor != "oturumlar":
                            plan["cakisma"].append(f"{klasor}/{ad}: iki tarafta farklı içerik")
    return plan


def say(plan: dict) -> int:
    return (sum(len(v) for v in plan["jsonl"].values()) + len(plan["isler"]) + len(plan["dosyalar"])
            + len(plan["takma"]))


def devralinmamis_sayisi(kaynak: str, hedef: str) -> int:
    """Kaynakta olup hedefte bulunmayan öğe sayısı (temizlik ve uyarı için); hatada 0."""
    try:
        return say(planla(kaynak, hedef))
    except Exception:
        return 0


def uygula(kaynak: str, hedef: str, plan: dict, simdi: str | None = None) -> dict:
    """Planı hedefe işler; yedek ve damga yazar. Dönen: {yedek, eklenen, cakisma}."""
    simdi = simdi or L.simdi()
    damga_adi = re.sub(r"[^0-9]", "", simdi)[:14]
    yedek = os.path.join(hedef, "yedek", f"devral_{damga_adi}")
    os.makedirs(yedek, exist_ok=True)
    boyutlar = {}
    for ad in JSONL:
        yol = os.path.join(hedef, ad)
        boyutlar[ad] = os.path.getsize(yol) if os.path.exists(yol) else 0
    with open(os.path.join(yedek, "boyutlar.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(boyutlar, f, ensure_ascii=False, indent=2)
    h_is_yol = os.path.join(hedef, "isler.json")
    if os.path.exists(h_is_yol):
        shutil.copy2(h_is_yol, os.path.join(yedek, "isler.json"))
    for ad, satirlar in plan["jsonl"].items():
        L.sona_ekle(os.path.join(hedef, ad), "".join(s + "\n" for s in satirlar))
    if plan["isler"] or plan["takma"] or plan["sayac"]:
        with L.kilit(h_is_yol):
            veri = _oku_json(h_is_yol, {"sayac": 0, "isler": {}})
            veri.setdefault("isler", {})
            for kimlik, kayit in plan["isler"]:
                veri["isler"].setdefault(kimlik, kayit)
            if plan["takma"]:
                veri.setdefault("takma", {}).update({k: v for k, v in plan["takma"].items() if k not in veri.get("takma", {})})
            if plan["sayac"]:
                veri["sayac"] = max(int(veri.get("sayac", 0) or 0), plan["sayac"])
            L.atomik_yaz(h_is_yol, json.dumps(veri, ensure_ascii=False, indent=2))
    for klasor, ad in plan["dosyalar"]:
        os.makedirs(os.path.join(hedef, klasor), exist_ok=True)
        shutil.copy2(os.path.join(kaynak, klasor, ad), os.path.join(hedef, klasor, ad))
    sonuc = {"yedek": yedek, "eklenen": say(plan), "cakisma": list(plan["cakisma"])}
    L.atomik_yaz(os.path.join(kaynak, DAMGA), json.dumps({"zaman": simdi, "hedef": hedef, **sonuc}, ensure_ascii=False, indent=2))
    return sonuc
