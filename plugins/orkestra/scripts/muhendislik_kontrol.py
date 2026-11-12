"""Mühendislik kontrolü (EDEL uyarlaması, ADR-0179): G→P→S→T→E izlenebilirlik zinciri, kanıt kaydı ve üç kapı kararı.

Kaynak kayıt değişmez: mevcut durum (G), plan (P, `## Doğrulama planı` altındaki T satırları), sözleşme (S) ve todo
olduğu gibi okunur. Yeni olan tek kayıt iş klasöründeki `kanit.jsonl`dır (E): T'nin komutu plandan alınıp koşulur;
komut, çıkış kodu, saat, maskeli çıktı kuyruğu, çıktı sha256'sı ve kapsam dosyalarının imzası yazılır. Kapsam dosyası
ya da T komutu sonradan değişirse E bayat sayılır.

T satırı biçimi (plan.md `## Doğrulama planı`):
    - **T1:** S1, S2 — açıklama — Komut: `python -m pytest tests/x.py -q`
İsteğe bağlı parçalar: `Eval:` (agentic kanıt: model, prompt sürümü, eval seti, koşu sayısı ister),
`Engel: <neden>` (T koşulamıyor; kapı BLOCKED olur), `Kapsam: `glob, glob`` (imzalanacak dosyalar; verilmezse
T'nin S'lerine bağlı P maddelerinin `**Yazma alanı:**` globları).

Kapı kararı: istenen kontrollerden biri kalırsa FAIL; kalan yoksa ama engelli T varsa BLOCKED; değilse PASS. Kademe başına
istenen kontroller `ayarlar/edel.json`dadır (proje ezmesi: durum klasöründeki `edel.json`).

Komutlar (doğrudan):  python muhendislik_kontrol.py kontrol <iş klasörü> [--json]
                      python muhendislik_kontrol.py kanit <iş klasörü> T<n> [--model ... --prompt-surum ... --eval-seti ... --kosu N]
                      python muhendislik_kontrol.py olc <durum klasörü> [--json]
"""
from __future__ import annotations

import argparse
import glob as _glob
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import is_sirasi as S  # noqa: E402
import ork_lib as L  # noqa: E402

KAPI = "edel"
KANIT_DOSYA = "kanit.jsonl"
SONUCLAR = ("PASS", "FAIL", "BLOCKED")
VARSAYILAN_ZAMAN_ASIMI = 900
CIKTI_KUYRUK = 1500
ORNEK_SAYI = 10
EVAL_ALANLARI = ("model", "prompt_surum", "eval_seti", "kosu_sayisi")
_EVAL_SATIRI = re.compile(r"^EDEL_EVAL\s+(\{.*\})\s*$", re.M)

_T_SATIRI = re.compile(r"^\s*[-*]\s+\*\*T(\d+):?\*\*:?[ \t]*(.*)$", re.M)
_KOMUT = re.compile(r"Komut:\s*`([^`]+)`")
_KAPSAM = re.compile(r"Kapsam:\s*`([^`]+)`")
_ENGEL = re.compile(r"\bEngel:\s*(.+?)(?:\s+—\s|$)")
_EVAL = re.compile(r"\bEval:")
_S_NO = re.compile(r"\bS(\d+)\b")
_G_NO = re.compile(r"\bG(\d+)\b")
_DENETCI = re.compile(r"^\*\*Denetçi:\*\*[ \t]*orkestra:denetci[ \t]+\S+", re.M)


# --- ayar -------------------------------------------------------------------------------------------------------------

def _eklenti_ayar_yolu() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", KAPI + ".json")


def ayar(klasor: str | None = None) -> dict:
    """`ayarlar/edel.json`; durum klasöründeki `edel.json` üst düzey anahtarları ezer."""
    yollar = [_eklenti_ayar_yolu()]
    sd = L.durum_dizini(klasor) if klasor else None
    if sd:
        yollar.append(os.path.join(sd, KAPI + ".json"))
    sonuc: dict = {"mod": "golge", "eval_min_kosu": {}, "kapilar": {}}
    for yol in yollar:
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                sonuc.update({k: v for k, v in d.items() if k in ("mod", "eval_min_kosu", "kapilar")})
        except (OSError, ValueError):
            pass
    return sonuc


# --- okuma ------------------------------------------------------------------------------------------------------------

def _alan(blok: str, ad: str) -> str:
    m = re.search(rf"^\*\*{re.escape(ad)}:\*\*[ \t]*(.*)$", blok or "", re.M)
    return m.group(1).strip() if m else ""


def dogrulama_plani(metin: str) -> dict[int, dict]:
    """plan.md `## Doğrulama planı` bölümündeki T satırları: {n: {s, komut, engel, eval, kapsam, satir}}."""
    bolum = S._baslik_bolumu(metin or "", "Doğrulama planı")
    tler: dict[int, dict] = {}
    for m in _T_SATIRI.finditer(bolum):
        govde = m.group(2)
        komut_m = _KOMUT.search(govde)
        kapsam_m = _KAPSAM.search(govde)
        komutsuz = _KAPSAM.sub(" ", _KOMUT.sub(" ", govde))
        bas = komutsuz.split(" — ", 1)[0]
        engel_m = _ENGEL.search(komutsuz)
        tler[int(m.group(1))] = {
            "s": sorted({int(x) for x in _S_NO.findall(bas)}),
            "komut": komut_m.group(1).strip() if komut_m else "",
            "engel": engel_m.group(1).strip() if engel_m else "",
            "eval": bool(_EVAL.search(komutsuz)),
            "kapsam": [p.strip() for p in re.split(r"[,;]", kapsam_m.group(1)) if p.strip()] if kapsam_m else None,
            "satir": govde.strip(),
        }
    return tler


def kanitlar(klasor: str) -> list[dict]:
    return [r for r in L.jsonl_oku(os.path.join(klasor, KANIT_DOSYA)) if isinstance(r, dict)]


def son_kanit(kayitlar: list[dict], t: int) -> dict | None:
    for r in reversed(kayitlar):
        if r.get("t") == f"T{t}":
            return r
    return None


def _proje(klasor: str) -> str:
    sd = L.durum_dizini(klasor)
    return os.path.dirname(os.path.dirname(sd)) if sd else klasor


def calisma_koku(metin: str, klasor: str) -> str:
    """T komutunun koştuğu ve kapsam globlarının çözüldüğü dizin: planın ilk `**Kök:**` satırı, yoksa proje kökü."""
    import plan_dogrulama as PD
    for m in PD._KOK.finditer(metin or ""):
        for parca in re.split(r"[;,]", m.group(1)):
            p = parca.strip().strip("`")
            if p:
                return p if os.path.isabs(p) else os.path.join(_proje(klasor), p)
    return _proje(klasor)


class Baglam:
    """Bir işin kaynak kayıtlarını bir kez okur; kontroller buradan beslenir."""

    def __init__(self, klasor: str):
        self.klasor = klasor
        self.kademe = S.is_kademesi(klasor)
        try:
            with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
                self.is_kaydi = json.load(f) or {}
        except (OSError, ValueError):
            self.is_kaydi = {}
        self.md_yolu = S.mevcut_durum_yolu(klasor)
        self.md = S._oku(self.md_yolu) if self.md_yolu else None
        self.gler = S.mevcut_durum_gapleri(klasor) if self.md else set()
        self.soz_yolu = S.sozlesme_yolu(klasor)
        self.soz = S._oku(self.soz_yolu) if self.soz_yolu else None
        self.sler = S.sozlesme_kriterleri(klasor) if self.soz else set()
        self.plan = S._oku(os.path.join(klasor, "plan.md"))
        self.pler = S._p_bloklari(self.plan) if self.plan else {}
        self.tler = dogrulama_plani(self.plan or "")
        self.todo = S._oku(os.path.join(klasor, "todo.md"))
        self.kanitlar = kanitlar(klasor)
        self.kok = calisma_koku(self.plan or "", klasor)
        self._imza: dict[int, tuple[str, list[str]]] = {}

    def p_s(self, p: int) -> set[int]:
        return {int(x) for x in _S_NO.findall(_alan(self.pler.get(p, ""), "Sözleşme"))}

    def p_g(self, p: int) -> set[int]:
        return {int(x) for x in _G_NO.findall(_alan(self.pler.get(p, ""), "Gap"))}

    def t_kapsam(self, t: int) -> list[str]:
        tt = self.tler.get(t) or {}
        if tt.get("kapsam") is not None:
            return tt["kapsam"]
        globlar: list[str] = []
        for p in sorted(self.pler):
            if self.p_s(p) & set(tt.get("s") or []):
                for g in re.split(r"[,;]", _alan(self.pler[p], "Yazma alanı")):
                    g = g.strip().strip("`")
                    if g and g not in globlar:
                        globlar.append(g)
        return globlar

    def imza(self, t: int) -> tuple[str, list[str]]:
        if t not in self._imza:
            self._imza[t] = kapsam_imzasi(self.kok, self.t_kapsam(t))
        return self._imza[t]

    def engelli(self) -> list[int]:
        return sorted(t for t, v in self.tler.items() if v["engel"])

    def kosulacak(self) -> list[int]:
        return sorted(t for t, v in self.tler.items() if not v["engel"])


def kapsam_imzasi(kok: str, globlar: list[str]) -> tuple[str, list[str]]:
    """Kapsam globlarına uyan dosyaların sha256 imzası; uymayan glob `YOK` olarak imzaya girer (dosya sonradan doğarsa bayat)."""
    satirlar: list[str] = []
    for g in globlar:
        yol = g if os.path.isabs(g) else os.path.join(kok, g)
        eslesen = sorted(p for p in _glob.glob(yol, recursive=True) if os.path.isfile(p))
        if not eslesen:
            satirlar.append(f"{g}:YOK")
        for p in eslesen:
            try:
                with open(p, "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                h = "OKUNAMADI"
            satirlar.append(f"{os.path.relpath(p, kok).replace(os.sep, '/')}:{h}")
    return hashlib.sha256("\n".join(satirlar).encode("utf-8")).hexdigest(), satirlar


# --- kontroller -------------------------------------------------------------------------------------------------------
# Her kontrol eksik mesajlarının listesini döner (boş = geçti). Engelli T'ler T'ye bağlı kontrollerde atlanır.

def _k_md_var(b: Baglam):
    return [] if b.md else ["mevcut_durum_<YYYYMMDD>.md yok"]


def _k_md_gap(b: Baglam):
    return [] if b.gler else ["mevcut durum gap bölümünde G maddesi yok"]


def _k_sozlesme_kriter(b: Baglam):
    if not b.soz:
        return ["sozlesme_<YYYYMMDD>.md yok"]
    return [] if b.sler else ["sözleşme `## Başarı kriterleri` altında S maddesi yok"]


def _k_dogrulama_plani(b: Baglam):
    if not b.tler:
        return ["plan.md `## Doğrulama planı` bölümünde T satırı yok"]
    return [f"T{t}: `Komut:` yok" for t, v in sorted(b.tler.items()) if not v["komut"] and not v["engel"]]


def _k_t_s_kapsama(b: Baglam):
    eksik = []
    anilan = set()
    for t, v in sorted(b.tler.items()):
        if not v["s"]:
            eksik.append(f"T{t}: S anmıyor")
        for s in v["s"]:
            anilan.add(s)
            if s not in b.sler:
                eksik.append(f"T{t}: S{s} sözleşmede yok")
    eksik += [f"S{s}: doğrulama planında T yok" for s in sorted(b.sler - anilan)]
    return eksik


def _k_yol_karari(b: Baglam):
    return [] if S._baslik_bolumu(b.md or "", "Yol kararı") else ["mevcut durum `## Yol kararı` bölümü yok ya da boş"]


def _k_plan_p(b: Baglam):
    if b.plan is None:
        return ["plan.md yok"]
    return [] if b.pler else ["plan.md'de P maddesi yok"]


def _k_gap_kapsama(b: Baglam):
    kapsanan = set()
    for p in b.pler:
        kapsanan |= b.p_g(p)
    for satir in (b.plan or "").splitlines():
        if "Kapsam dışı" in satir:
            kapsanan |= {int(x) for x in _G_NO.findall(satir)}
    return [f"G{g}: hiçbir P'nin `**Gap:**` alanında yok" for g in sorted(b.gler - kapsanan)]


def _k_s_p_bag(b: Baglam):
    eksik, anilan = [], set()
    for p in sorted(b.pler):
        ps = b.p_s(p)
        anilan |= ps
        eksik += [f"P{p}: S{s} sözleşmede yok" for s in sorted(ps - b.sler)]
    eksik += [f"S{s}: hiçbir P'nin `**Sözleşme:**` alanında yok" for s in sorted(b.sler - anilan)]
    return eksik


def _k_todo_kanit(b: Baglam):
    if b.todo is None:
        return ["todo.md yok"]
    return S.todo_satir_ihlalleri(b.todo, set(b.pler), kanit=True)


def _k_todo_tamam(b: Baglam):
    if b.todo is None:
        return ["todo.md yok"]
    acik = re.findall(r"^\s*[-*]\s*\[ \]", b.todo, re.M)
    if not re.search(r"^\s*[-*]\s*\[[ xX]\]", b.todo, re.M):
        return ["todo.md'de madde yok"]
    return [f"todo.md'de {len(acik)} açık madde"] if acik else []


def _k_t_kanit_var(b: Baglam):
    return [f"T{t}: kanıt (E) yok (`orkestra is kanit <iş> T{t}`)" for t in b.kosulacak() if not son_kanit(b.kanitlar, t)]


def _k_kanit_gecti(b: Baglam):
    eksik = []
    for t in b.kosulacak():
        e = son_kanit(b.kanitlar, t)
        if not e:
            eksik.append(f"T{t}: kanıt yok")
        elif e.get("komut") != b.tler[t]["komut"]:
            eksik.append(f"T{t}: {e.get('e')} plandaki komuttan farklı komutla koşulmuş (bayat)")
        elif e.get("cikis") != 0:
            eksik.append(f"T{t}: son kanıt {e.get('e')} çıkış {e.get('cikis')}")
    return eksik


def _k_kanit_taze(b: Baglam):
    eksik = []
    for t in b.kosulacak():
        e = son_kanit(b.kanitlar, t)
        if e and e.get("kapsam_imza") != b.imza(t)[0]:
            eksik.append(f"T{t}: {e.get('e')} sonrası kapsam dosyası değişti (bayat; yeniden koş)")
    return eksik


def _k_eval_alanlari(b: Baglam):
    eksik = []
    esik = int((ayar(b.klasor).get("eval_min_kosu") or {}).get(b.kademe, 1) or 1)
    for t in b.kosulacak():
        if not b.tler[t]["eval"]:
            continue
        e = son_kanit(b.kanitlar, t)
        ev = (e or {}).get("eval") or {}
        bos = [a for a in EVAL_ALANLARI if ev.get(a) in (None, "")]
        if not e:
            continue  # kanıtsızlık kanit_gecti'de sayılır
        if bos:
            eksik.append(f"T{t}: eval kanıtında eksik alan: {', '.join(bos)}")
        else:
            try:
                n = int(ev.get("kosu_sayisi"))
            except (TypeError, ValueError):
                n = 0
            if n < esik:
                eksik.append(f"T{t}: eval koşu sayısı {n} < {b.kademe} eşiği {esik}")
    return eksik


def _ozet_metinleri(b: Baglam) -> list[str]:
    return [re.sub(r"<!--.*?-->", "", S._oku(y) or "", flags=re.S)
            for y in sorted(_glob.glob(os.path.join(b.klasor, "calisma_ozeti_*.md")))]


def _k_sozlesme_sonuc(b: Baglam):
    """Her S'nin sonucu sözleşme `## Sonuç` bölümünde ya da çalışma özetinde S numarasıyla anılır."""
    if not b.soz:
        return []  # sözleşmenin yokluğu kapı 1'in (sozlesme_kriter) bulgusudur; burada yinelenmez
    anilan = {int(x) for x in _S_NO.findall(" ".join([S._baslik_bolumu(b.soz, "Sonuç")] + _ozet_metinleri(b)))}
    return [f"S{s}: sonucu ne sözleşme `## Sonuç` bölümünde ne çalışma özetinde anılıyor" for s in sorted(b.sler - anilan)]


def _k_ozet_var(b: Baglam):
    for metin in _ozet_metinleri(b):
        m = re.search(r"\*\*(?:Ne yapıldı\?|Ana bulgu:)\*\*[ \t]*\n(.*?)(?=^\*\*[^\n]+[:?]\*\*|^#|\Z)", metin, re.S | re.M)
        if m and re.sub(r"^\s*[-*]\s*$", "", m.group(1), flags=re.M).strip():
            return []
    return ["doldurulmuş calisma_ozeti_<YYYYMMDD>.md yok"]


def _k_denetci(b: Baglam):
    return [] if _DENETCI.search(b.plan or "") else ["plan best in class denetiminde `**Denetçi:** orkestra:denetci <kimlik>` yok"]


def _k_teslim(b: Baglam):
    t = b.is_kaydi.get("teslim") or {}
    return [] if isinstance(t, dict) and (t.get("pr") or t.get("yerel_birlesme")) else ["teslim kaydı (PR ya da yerel birleşme) yok"]


KONTROLLER = {
    "md_var": _k_md_var, "md_gap": _k_md_gap, "sozlesme_kriter": _k_sozlesme_kriter,
    "dogrulama_plani": _k_dogrulama_plani, "t_s_kapsama": _k_t_s_kapsama, "yol_karari": _k_yol_karari,
    "plan_p": _k_plan_p, "gap_kapsama": _k_gap_kapsama, "s_p_bag": _k_s_p_bag, "todo_kanit": _k_todo_kanit,
    "todo_tamam": _k_todo_tamam, "t_kanit_var": _k_t_kanit_var,
    "kanit_gecti": _k_kanit_gecti, "kanit_taze": _k_kanit_taze, "eval_alanlari": _k_eval_alanlari,
    "sozlesme_sonuc": _k_sozlesme_sonuc, "ozet_var": _k_ozet_var, "denetci": _k_denetci, "teslim": _k_teslim,
}
T_BAGLI = {"t_kanit_var", "kanit_gecti", "kanit_taze", "eval_alanlari"}


def kapi_karari(b: Baglam, no: str, ayar_: dict) -> dict:
    tanim = (ayar_.get("kapilar") or {}).get(no) or {}
    istenen = list(tanim.get(b.kademe) or [])
    eksikler = []
    for ad in istenen:
        f = KONTROLLER.get(ad)
        eksikler += [(ad, m) for m in (f(b) if f else [f"bilinmeyen kontrol: {ad}"])]
    engeller = [f"T{t}: {b.tler[t]['engel']}" for t in b.engelli()] if T_BAGLI & set(istenen) else []
    sonuc = "FAIL" if eksikler else ("BLOCKED" if engeller else "PASS")
    return {"kapi": no, "ad": tanim.get("ad", no), "sonuc": sonuc, "kontroller": istenen,
            "eksikler": [{"kontrol": a, "mesaj": m} for a, m in eksikler], "engeller": engeller}


def zincir(b: Baglam) -> list[dict]:
    """G→P→S→T→E satırları (görünüm ve rapor için). Bağı olmayan halka `—` olur."""
    satirlar = []
    for g in sorted(b.gler) or [None]:
        pler = [p for p in sorted(b.pler) if g is None or g in b.p_g(p)] or [None]
        for p in pler:
            sler = sorted(b.p_s(p)) if p is not None else []
            for s in sler or [None]:
                tler = [t for t in sorted(b.tler) if s is not None and s in b.tler[t]["s"]] or [None]
                for t in tler:
                    satirlar.append({"g": g, "p": p, "s": s, "t": t, "e": _e_ozeti(b, t)})
    return satirlar


def _e_ozeti(b: Baglam, t: int | None) -> dict:
    if t is None:
        return {"e": None, "durum": "—"}
    if b.tler[t]["engel"]:
        return {"e": None, "durum": "engel"}
    e = son_kanit(b.kanitlar, t)
    if not e:
        return {"e": None, "durum": "yok"}
    if e.get("cikis") != 0:
        durum = "kaldı"
    elif e.get("komut") != b.tler[t]["komut"] or e.get("kapsam_imza") != b.imza(t)[0]:
        durum = "bayat"
    else:
        durum = "geçti"
    return {"e": e.get("e"), "durum": durum, "zaman": e.get("zaman"), "commit": e.get("commit")}


def kontrol(klasor: str) -> dict:
    """Üç kapı kararı; yan etkisiz (yazma yok)."""
    b = Baglam(klasor)
    a = ayar(klasor)
    kapilar = [kapi_karari(b, no, a) for no in ("1", "2", "3")]
    asama = next((k for k in kapilar if k["sonuc"] != "PASS"), None)
    return {"klasor": klasor, "is": b.is_kaydi.get("id"), "kademe": b.kademe, "mod": a.get("mod", "golge"),
            "kapilar": kapilar, "genel": asama["sonuc"] if asama else "PASS",
            "asama": asama["kapi"] if asama else None, "zincir": zincir(b),
            "tler": {f"T{t}": v for t, v in sorted(b.tler.items())}}


def kapanis_golge(klasor: str) -> dict | None:
    """`is kapat` anında: kapı 3 PASS değilse `kapi_golge` (kapi: edel) yazar. Kapanışı hiçbir koşulda engellemez."""
    try:
        r = kontrol(klasor)
    except Exception:  # noqa: BLE001 - kapanış hiçbir koşulda engellenmez
        return None
    k3 = r["kapilar"][2]
    if k3["sonuc"] != "PASS":
        import kapi_mod as KM
        ayrinti = "; ".join(e["mesaj"] for e in k3["eksikler"]) or "; ".join(k3["engeller"])
        KM.kaydet(klasor, KAPI, f"kapı 3 {k3['sonuc']} ({r['kademe']}): {ayrinti}"[:300])
    return r


# --- kanıt ------------------------------------------------------------------------------------------------------------

def _git_commit(kok: str) -> str | None:
    import plan_dogrulama as PD
    try:
        r = subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "HEAD"], cwd=kok, capture_output=True,
                           timeout=20, **PD.cfg.PENCERESIZ)
        return r.stdout.decode().strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def kanit_al(klasor: str, t: int, eval_beyan: dict | None = None, zaman_asimi: int = VARSAYILAN_ZAMAN_ASIMI) -> dict:
    """T'nin komutunu plandan alıp koşar ve `kanit.jsonl`a E kaydı ekler. Komut elle verilemez."""
    import plan_dogrulama as PD
    b = Baglam(klasor)
    v = b.tler.get(t)
    if v is None:
        raise ValueError(f"T{t} plan.md `## Doğrulama planı` bölümünde yok")
    if v["engel"]:
        raise ValueError(f"T{t} engelli ({v['engel']}); önce engeli kaldır")
    if not v["komut"]:
        raise ValueError(f"T{t} satırında `Komut: `...`` yok")
    yasak = PD.komut_yasakli(v["komut"])
    if yasak:
        raise ValueError(f"T{t} komutu koşulmaz: {yasak}")
    bash = PD._bash()
    arg = [bash, "-c", v["komut"]] if bash else v["komut"]
    env = dict(os.environ, PYTHONUTF8="1", ORKESTRA_DOGRULAMA_KAPISI="0")
    bas = time.time()
    try:
        r = subprocess.run(arg, shell=not bash, cwd=b.kok, capture_output=True, timeout=zaman_asimi, env=env,
                           **PD.cfg.PENCERESIZ)
        cikis, ham = r.returncode, (r.stdout or b"") + (r.stderr or b"")
    except subprocess.TimeoutExpired:
        cikis, ham = 124, f"komut {zaman_asimi} sn içinde bitmedi".encode()
    except OSError as e:
        cikis, ham = 127, f"komut başlatılamadı: {e}".encode()
    metin = ham.decode("utf-8", "replace")
    imza, dosyalar = b.imza(t)
    kayit = {"e": f"E{len(b.kanitlar) + 1}", "t": f"T{t}", "zaman": L.simdi(), "komut": v["komut"], "cikis": cikis,
             "sure_sn": round(time.time() - bas, 1), "cikti_sha256": hashlib.sha256(ham).hexdigest(),
             "cikti_ozet": L.maskele(metin[-CIKTI_KUYRUK:]), "kok": b.kok, "commit": _git_commit(b.kok),
             "kapsam": b.t_kapsam(t), "kapsam_dosya": len([d for d in dosyalar if not d.endswith(":YOK")]),
             "kapsam_imza": imza}
    ev = _eval_coz(metin, eval_beyan)
    if ev:
        kayit["eval"] = ev
    L.jsonl_ekle(os.path.join(klasor, KANIT_DOSYA), kayit)
    return kayit


def _eval_coz(metin: str, beyan: dict | None) -> dict | None:
    """Eval alanları: komut çıktısındaki son `EDEL_EVAL {json}` satırı (kaynak: cikti), yoksa CLI beyanı (kaynak: beyan)."""
    bulunan = _EVAL_SATIRI.findall(metin or "")
    if bulunan:
        try:
            d = json.loads(bulunan[-1])
            if isinstance(d, dict):
                return {**{a: d.get(a) for a in EVAL_ALANLARI}, "kaynak": "cikti"}
        except ValueError:
            pass
    beyan = {a: x for a, x in (beyan or {}).items() if x not in (None, "")}
    return {**{a: beyan.get(a) for a in EVAL_ALANLARI}, "kaynak": "beyan"} if beyan else None


# --- ölçüm ------------------------------------------------------------------------------------------------------------

def _isler(sd: str) -> list[dict]:
    try:
        with open(os.path.join(sd, "isler.json"), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    isler = d.get("isler", d) if isinstance(d, dict) else d
    if isinstance(isler, dict):  # isler.json: {"isler": {"I-001": {...}}}; kimlik anahtardadır
        isler = [{"id": k, **v} for k, v in isler.items() if isinstance(v, dict)]
    return [x for x in isler or [] if isinstance(x, dict)]


def olc(sd: str, ornek: int = ORNEK_SAYI, tohum: int = 447) -> dict:
    """Durum klasöründeki bütün sıralı işlerde üç kapıyı koşar (yazma yok): sonuç dağılımı, en sık eksikler, örnekler."""
    from collections import Counter
    dagilim = {k: Counter() for k in ("1", "2", "3", "genel", "kapali_3")}
    eksik_say = {k: Counter() for k in ("1", "2", "3", "kapali_3")}
    satirlar, hatalar = [], []
    for x in _isler(sd):
        k = str(x.get("klasor") or "")
        try:
            with open(os.path.join(k, "is.json"), encoding="utf-8") as f:
                if not (json.load(f) or {}).get("sira"):
                    continue
        except (OSError, ValueError, AttributeError):
            continue
        try:
            r = kontrol(k)
        except Exception as e:  # noqa: BLE001 - ölçüm tek işte bozulmaz
            hatalar.append(f"{x.get('id')}: {type(e).__name__}: {L.maskele(str(e))[:120]}")
            continue
        kapali = x.get("durum") in ("kapandi", "kapali")
        for kp in r["kapilar"]:
            dagilim[kp["kapi"]][kp["sonuc"]] += 1
            for ad in sorted({e["kontrol"] for e in kp["eksikler"]}):
                eksik_say[kp["kapi"]][ad] += 1
                if kapali and kp["kapi"] == "3":
                    eksik_say["kapali_3"][ad] += 1
        if kapali:  # kapanmış işte kapı 3 kalması gerçek açık ya da yanlış pozitiftir; açık işte beklenir
            dagilim["kapali_3"][r["kapilar"][2]["sonuc"]] += 1
        dagilim["genel"][r["genel"]] += 1
        satirlar.append({"is": x.get("id"), "klasor": k, "durum": x.get("durum"), "kademe": r["kademe"],
                         "genel": r["genel"], "asama": r["asama"],
                         "eksik": [f"{kp['kapi']}/{e['kontrol']}: {e['mesaj']}" for kp in r["kapilar"]
                                   for e in kp["eksikler"]][:8],
                         "engel": [e for kp in r["kapilar"] for e in kp["engeller"]][:2]})
    rnd = random.Random(tohum)
    ornekler = {}
    for sonuc in ("FAIL", "BLOCKED"):
        grup = sorted((s for s in satirlar if s["genel"] == sonuc), key=lambda s: str(s["is"]))
        ornekler[sonuc] = rnd.sample(grup, min(ornek, len(grup)))
    return {"is_sayisi": len(satirlar), "dagilim": {k: dict(v) for k, v in dagilim.items()},
            "en_sik_eksik": {k: v.most_common(8) for k, v in eksik_say.items()}, "ornekler": ornekler, "hatalar": hatalar}


# --- yazdırma ---------------------------------------------------------------------------------------------------------

def rapor_metni(r: dict) -> str:
    sat = [f"{r.get('is') or os.path.basename(r['klasor'])} · kademe: {r['kademe']} · mod: {r['mod']} · genel: {r['genel']}"]
    for kp in r["kapilar"]:
        sat.append(f"Kapı {kp['kapi']} {kp['ad']}: {kp['sonuc']}")
        sat += [f"  - {e['kontrol']}: {e['mesaj']}" for e in kp["eksikler"][:12]]
        if len(kp["eksikler"]) > 12:
            sat.append(f"  - (+{len(kp['eksikler']) - 12} eksik daha)")
        sat += [f"  - engel {e}" for e in kp["engeller"]]
    return "\n".join(sat)


def olcum_metni(o: dict) -> str:
    sat = [f"sıralı iş: {o['is_sayisi']}"]
    for k in ("1", "2", "3", "genel", "kapali_3"):
        d = o["dagilim"].get(k, {})
        sat.append(f"kapı {k}: " + ", ".join(f"{s} {d.get(s, 0)}" for s in SONUCLAR))
    for k in ("1", "2", "3", "kapali_3"):
        sat.append(f"kapı {k} en sık eksik: " + (", ".join(f"{a} {n}" for a, n in o["en_sik_eksik"][k]) or "-"))
    for sonuc, grup in o["ornekler"].items():
        sat.append(f"{sonuc} örnekleri ({len(grup)}):")
        for g in grup:
            sat.append(f"  {g['is']} [{g['kademe']}, {g['durum']}] {g['klasor']}")
            sat += [f"    - {m[:200]}" for m in (g["eksik"] or g["engel"])]
    if o["hatalar"]:
        sat.append(f"hata ({len(o['hatalar'])}): " + "; ".join(o["hatalar"][:5]))
    return "\n".join(sat)


def cikis_kodu(genel: str) -> int:
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}.get(genel, 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    alt = ap.add_subparsers(dest="komut", required=True)
    k = alt.add_parser("kontrol")
    k.add_argument("klasor")
    k.add_argument("--json", action="store_true")
    kn = alt.add_parser("kanit")
    kn.add_argument("klasor")
    kn.add_argument("t")
    for ad in ("--model", "--prompt-surum", "--eval-seti"):
        kn.add_argument(ad)
    kn.add_argument("--kosu", type=int)
    kn.add_argument("--zaman-asimi", type=int, default=VARSAYILAN_ZAMAN_ASIMI)
    o = alt.add_parser("olc")
    o.add_argument("sd")
    o.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.komut == "kontrol":
        r = kontrol(a.klasor)
        print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else rapor_metni(r))
        return cikis_kodu(r["genel"])
    if a.komut == "kanit":
        try:
            e = kanit_al(a.klasor, int(a.t.lstrip("Tt")), {"model": a.model, "prompt_surum": a.prompt_surum,
                                                           "eval_seti": a.eval_seti, "kosu_sayisi": a.kosu},
                         a.zaman_asimi)
        except ValueError as ex:
            print(f"orkestra: {ex}", file=sys.stderr)
            return 2
        print(f"{e['e']} {e['t']}: çıkış {e['cikis']} · {e['sure_sn']} sn · kapsam {e['kapsam_dosya']} dosya · imza {e['kapsam_imza'][:12]}")
        return 0 if e["cikis"] == 0 else 1
    r = olc(a.sd)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str) if a.json else olcum_metni(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
