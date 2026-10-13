"""Orkestra çekirdek kütüphanesi.

Durum klasörü: <proje>/.claude/orkestra/  (yalnız `orkestra baslat` ile açılan projelerde)
  gorevler/<id>.json        görev kartları (yalnız CLI yazar)
  ortak_defter.md / .jsonl  herkesin ne yaptığı (yalnız sona ekleme)
  maliyet.jsonl             ajan x süreç x model token ve maliyet kaydı
  gunluk.jsonl              olay günlüğü (istekler, skill/ajan kullanımı) — skill avcısı okur
  oturumlar/<id>.json       oturum başına transkript okuma ofseti
  ruya/                     rüya (hafıza bakımı) raporları ve zaman damgası
  onerilen_skill/           skill avcısının taslakları
Bağımlılık yok: yalnız Python standart kütüphanesi.
"""
from __future__ import annotations

import datetime
import fnmatch
import glob
import json
import os
import re
import sys
import tempfile
import time
from contextlib import contextmanager

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SURECLER = (
    "triyaj", "plan", "is", "denetim", "duzeltme", "yukseltme", "sentez",
    "arsiv", "ruya", "skill-avi", "arastirma", "orkestrasyon", "bilinmiyor",
)
ACIK_DURUMLAR = ("isleniyor", "denetimde", "reddedildi", "onaylandi")
KAPALI_DURUMLAR = ("teslim", "iptal", "beklemede", "planlandi")
ETIKET_GOREV = re.compile(r"#GOREV:([A-Za-z0-9_.\-]+)")
ETIKET_SUREC = re.compile(r"#SUREC:([a-z\-]+)")
DEFTER_MAX_BAYT = 4 * 1024 * 1024


# ---------------------------------------------------------------- zaman, yol

def simdi() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def proje_dizini(cwd: str | None = None) -> str:
    """CLAUDE_PROJECT_DIR > cwd'den yukarı .claude/orkestra arayışı > cwd."""
    baslangic = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()
    d = os.path.abspath(baslangic)
    while True:
        if os.path.isdir(os.path.join(d, ".claude", "orkestra")):
            return d
        ust = os.path.dirname(d)
        if ust == d:
            return os.path.abspath(baslangic)
        d = ust


def durum_dizini(cwd: str | None = None, olustur: bool = False) -> str | None:
    p = os.path.join(proje_dizini(cwd), ".claude", "orkestra")
    if os.path.isdir(p):
        return p
    if olustur:
        for alt in ("gorevler", "oturumlar", "ruya", "onerilen_skill", "raporlar"):
            os.makedirs(os.path.join(p, alt), exist_ok=True)
        return p
    return None


# ---------------------------------------------------------------- kilit ve yazım

@contextmanager
def kilit(yol: str, bekleme_s: float = 8.0):
    """Süreçler arası basit dosya kilidi (Windows msvcrt / POSIX fcntl)."""
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    fd = os.open(yol + ".lock", os.O_RDWR | os.O_CREAT)
    try:
        bitis = time.time() + bekleme_s
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    os.lseek(fd, 0, 0)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.time() > bitis:
                        raise TimeoutError(f"kilit alınamadı: {yol}")
                    time.sleep(0.02)
            try:
                yield
            finally:
                os.lseek(fd, 0, 0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def sona_ekle(yol: str, metin: str) -> None:
    with kilit(yol):
        with open(yol, "a", encoding="utf-8", newline="\n") as f:
            f.write(metin)


def jsonl_ekle(yol: str, kayit: dict) -> None:
    sona_ekle(yol, json.dumps(kayit, ensure_ascii=False) + "\n")


def jsonl_oku(yol: str) -> list[dict]:
    if not os.path.exists(yol):
        return []
    out = []
    with open(yol, encoding="utf-8", errors="replace") as f:
        for satir in f:
            satir = satir.strip()
            if satir:
                try:
                    out.append(json.loads(satir))
                except json.JSONDecodeError:
                    pass
    return out


def atomik_yaz(yol: str, metin: str) -> None:
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=os.path.dirname(yol), prefix=".tmp_")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)
    os.replace(gecici, yol)


# ---------------------------------------------------------------- maskeleme

_SIR_KALIPLARI = [
    re.compile(r"(?i)((?:password|passwd|pwd|parola|şifre|sifre|secret|token|api[_-]?key|account[_-]?key)\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{12,})"),
    re.compile(r"(postgres(?:ql)?://[^:\s/]+:)([^@\s]+)(@)"),
]
_UZUN_ANAHTAR = re.compile(r"\b(?=[A-Za-z0-9+/=_\-]*\d)(?=[A-Za-z0-9+/=_\-]*[A-Za-z])[A-Za-z0-9+/=_\-]{32,}\b")
_EPOSTA = re.compile(r"\b[\w.+\-]+@[\w\-]+\.[\w.\-]+\b")


def maskele(metin: str) -> str:
    if not metin:
        return metin
    for k in _SIR_KALIPLARI:
        metin = k.sub(lambda m: m.group(1) + "<gizli>" + (m.group(3) if m.lastindex and m.lastindex >= 3 else ""), metin)
    metin = _UZUN_ANAHTAR.sub("<gizli-anahtar>", metin)
    metin = _EPOSTA.sub("<e-posta>", metin)
    return metin


# ---------------------------------------------------------------- fiyat ve transkript

def fiyat_tablosu() -> dict:
    with open(os.path.join(PLUGIN_ROOT, "bin", "fiyat.json"), encoding="utf-8") as f:
        return json.load(f)


def model_fiyati(model: str, tablo: dict | None = None) -> dict:
    tablo = tablo or fiyat_tablosu()
    m = (model or "").lower().split("[")[0]
    en_iyi = None
    for anahtar in tablo["modeller"]:
        if m.startswith(anahtar) and (en_iyi is None or len(anahtar) > len(en_iyi)):
            en_iyi = anahtar
    return tablo["modeller"].get(en_iyi) or tablo["modeller"][tablo["varsayilan"]]


def kullanim_maliyeti(model: str, u: dict, tablo: dict | None = None) -> float:
    f = model_fiyati(model, tablo)
    cc = u.get("cache_creation") or {}
    cw5 = cc.get("ephemeral_5m_input_tokens")
    cw1 = cc.get("ephemeral_1h_input_tokens")
    if cw5 is None and cw1 is None:
        cw5, cw1 = u.get("cache_creation_input_tokens", 0) or 0, 0
    usd = (
        (u.get("input_tokens", 0) or 0) * f["giris"]
        + (u.get("output_tokens", 0) or 0) * f["cikis"]
        + (u.get("cache_read_input_tokens", 0) or 0) * f["onbellek_okuma"]
        + (cw5 or 0) * f["onbellek_yazma_5dk"]
        + (cw1 or 0) * f["onbellek_yazma_1sa"]
    ) / 1_000_000
    return round(usd, 6)


def _metin(icerik) -> str:
    if isinstance(icerik, str):
        return icerik
    if isinstance(icerik, list):
        parcalar = []
        for b in icerik:
            if isinstance(b, dict) and b.get("type") == "text":
                parcalar.append(b.get("text", ""))
        return "\n".join(parcalar)
    return ""


def transkript_oku(yol: str, ofset: int = 0, yan_zincir: bool | None = None) -> dict:
    """Transkripti ofsetten itibaren okur; mesaj kimliğine göre tekilleştirilmiş kullanım toplar.

    yan_zincir=False: yalnız ana zincir (isSidechain false) satırları sayılır.
    Dönen: {modeller:{model:{giris,cikis,onbellek_okuma,onbellek_yazma,maliyet_usd}}, toplam:{...},
            ilk_kullanici, tur, arac_cagrisi, araclar:Counter-dict, dokunulan:[...], ilk_zaman, son_zaman, ofset}
    """
    sonuc = {
        "modeller": {}, "toplam": {"giris": 0, "cikis": 0, "onbellek_okuma": 0, "onbellek_yazma": 0, "maliyet_usd": 0.0},
        "ilk_kullanici": None, "tur": 0, "arac_cagrisi": 0, "araclar": {}, "dokunulan": [],
        "ilk_zaman": None, "son_zaman": None, "ofset": ofset,
    }
    if not yol or not os.path.exists(yol):
        return sonuc
    son_kullanim: dict[str, tuple[str, dict]] = {}
    arac_idleri: set[str] = set()
    with open(yol, "rb") as f:
        f.seek(ofset)
        veri = f.read()
    son_tam = veri.rfind(b"\n")
    if son_tam < 0:
        return sonuc
    sonuc["ofset"] = ofset + son_tam + 1
    for ham in veri[: son_tam + 1].splitlines():
        try:
            o = json.loads(ham.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        if yan_zincir is False and o.get("isSidechain"):
            continue
        ts = o.get("timestamp")
        if ts:
            sonuc["ilk_zaman"] = sonuc["ilk_zaman"] or ts
            sonuc["son_zaman"] = ts
        tip = o.get("type")
        mesaj = o.get("message") or {}
        if tip == "user" and sonuc["ilk_kullanici"] is None:
            t = _metin(mesaj.get("content"))
            if t.strip():
                sonuc["ilk_kullanici"] = t
        if tip != "assistant":
            continue
        mid = mesaj.get("id") or o.get("uuid")
        if mesaj.get("usage"):
            son_kullanim[mid] = (mesaj.get("model") or "bilinmiyor", mesaj["usage"])
        for b in mesaj.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") not in arac_idleri:
                arac_idleri.add(b.get("id"))
                ad = b.get("name", "?")
                sonuc["araclar"][ad] = sonuc["araclar"].get(ad, 0) + 1
                giris = b.get("input") or {}
                fp = giris.get("file_path") or giris.get("notebook_path")
                if ad in ("Write", "Edit", "MultiEdit", "NotebookEdit") and fp and fp not in sonuc["dokunulan"]:
                    sonuc["dokunulan"].append(fp)
    tablo = fiyat_tablosu()
    for model, u in son_kullanim.values():
        if model == "<synthetic>":
            continue
        m = sonuc["modeller"].setdefault(model, {"giris": 0, "cikis": 0, "onbellek_okuma": 0, "onbellek_yazma": 0, "maliyet_usd": 0.0})
        m["giris"] += u.get("input_tokens", 0) or 0
        m["cikis"] += u.get("output_tokens", 0) or 0
        m["onbellek_okuma"] += u.get("cache_read_input_tokens", 0) or 0
        m["onbellek_yazma"] += u.get("cache_creation_input_tokens", 0) or 0
        m["maliyet_usd"] = round(m["maliyet_usd"] + kullanim_maliyeti(model, u, tablo), 6)
    for m in sonuc["modeller"].values():
        for k in ("giris", "cikis", "onbellek_okuma", "onbellek_yazma"):
            sonuc["toplam"][k] += m[k]
        sonuc["toplam"]["maliyet_usd"] = round(sonuc["toplam"]["maliyet_usd"] + m["maliyet_usd"], 6)
    sonuc["tur"] = len(son_kullanim)
    sonuc["arac_cagrisi"] = len(arac_idleri)
    return sonuc


def etiketler(metin: str | None) -> tuple[str, str]:
    metin = metin or ""
    g = ETIKET_GOREV.search(metin)
    s = ETIKET_SUREC.search(metin)
    surec = s.group(1) if s and s.group(1) in SURECLER else "bilinmiyor"
    return (g.group(1) if g else "-"), surec


def sure_ms(ilk: str | None, son: str | None) -> int | None:
    try:
        a = datetime.datetime.fromisoformat(ilk.replace("Z", "+00:00"))
        b = datetime.datetime.fromisoformat(son.replace("Z", "+00:00"))
        return int((b - a).total_seconds() * 1000)
    except Exception:
        return None


def alt_ajan_transkripti(ana_transkript: str, session_id: str, agent_id: str) -> str:
    return os.path.join(os.path.dirname(ana_transkript), session_id, "subagents", f"agent-{agent_id}.jsonl")


def alt_ajan_meta(transkript: str) -> dict:
    meta = transkript[: -len(".jsonl")] + ".meta.json" if transkript.endswith(".jsonl") else ""
    try:
        with open(meta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------- görev kartları

def kart_yolu(sd: str, gid: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", gid or ""):
        raise ValueError(f"geçersiz görev kimliği: {gid!r}")
    return os.path.join(sd, "gorevler", gid + ".json")


def kart_oku(sd: str, gid: str) -> dict | None:
    try:
        with open(kart_yolu(sd, gid), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def kart_yaz(sd: str, kart: dict) -> None:
    kart["guncelleme"] = simdi()
    atomik_yaz(kart_yolu(sd, kart["id"]), json.dumps(kart, ensure_ascii=False, indent=2) + "\n")


def kartlar(sd: str) -> list[dict]:
    d = os.path.join(sd, "gorevler")
    out = []
    if os.path.isdir(d):
        for ad in sorted(os.listdir(d)):
            if ad.endswith(".json") and not ad.endswith(".denetim.json") and not ad.startswith(".tmp_"):
                try:
                    with open(os.path.join(d, ad), encoding="utf-8") as f:
                        out.append(json.load(f))
                except Exception:
                    pass
    return out


def yeni_kart_id(sd: str) -> str:
    sayac = os.path.join(sd, "gorevler", ".sayac")
    with kilit(sayac):
        n = 0
        if os.path.exists(sayac):
            with open(sayac, encoding="utf-8") as f:
                n = int((f.read() or "0").strip() or 0)
        n += 1
        with open(sayac, "w", encoding="utf-8") as f:
            f.write(str(n))
    return f"G-{n:03d}"


def kart_durumu_hesapla(kart: dict) -> str:
    """Son işçi çıktısından sonraki denetimlere göre durum: ret varsa reddedildi, onay varsa onaylandi."""
    if kart.get("durum") in ("teslim", "iptal", "beklemede"):
        return kart["durum"]
    # Sıra numarası (aynı saniyedeki olayları da doğru sıralar); eski kartlarda zaman damgasına düşer.
    son_is_sira = kart.get("son_is_sira")
    son_is = kart.get("son_is_zamani")
    if son_is_sira is not None:
        sonraki = [d for d in kart.get("denetimler", []) if d.get("sira", -1) > son_is_sira]
    else:
        sonraki = [d for d in kart.get("denetimler", []) if not son_is or d.get("zaman", "") >= son_is]
    if sonraki:
        if any(d.get("karar") == "ret" for d in sonraki):
            return "reddedildi"
        if any(d.get("karar") == "onay" for d in sonraki):
            return "onaylandi"
    if son_is:
        return "denetimde"
    return kart.get("durum", "planlandi")


def sonraki_sira(kart: dict) -> int:
    kart["olay_sira"] = kart.get("olay_sira", 0) + 1
    return kart["olay_sira"]


def yazma_alaninda_mi(proje: str, yol: str, desenler: list[str]) -> bool:
    if not desenler:
        return True
    try:
        rel = os.path.relpath(os.path.abspath(yol), proje).replace("\\", "/")
    except ValueError:
        return True  # farklı sürücü: proje dışı
    if rel.startswith(".."):
        return True  # proje dışı (scratchpad vb.) serbest
    for d in desenler:
        d = d.replace("\\", "/").rstrip("/")
        if fnmatch.fnmatch(rel, d) or rel == d or rel.startswith(d + "/") or fnmatch.fnmatch(rel, d + "/**"):
            return True
    return False


# ---------------------------------------------------------------- ortak defter

def defter_blogu(kayit: dict) -> str:
    t = kayit.get("token") or {}
    satirlar = [
        f"## [{kayit.get('zaman', simdi())[:16].replace('T', ' ')}] {kayit.get('gorev', '-')} · {kayit.get('surec', '-')} · "
        f"{kayit.get('ajan', '-')} ({kayit.get('model', '-')})" + (f" · {kayit['agent_id'][:8]}" if kayit.get("agent_id") else ""),
    ]
    if kayit.get("yaptim"):
        satirlar.append(f"- Yaptım: {kayit['yaptim']}")
    if kayit.get("sonuc"):
        satirlar.append(f"- Sonuç: {kayit['sonuc']}")
    if kayit.get("dokunulan"):
        satirlar.append("- Dokunduğum dosyalar: " + ", ".join(kayit["dokunulan"][:12]))
    if kayit.get("not"):
        satirlar.append(f"- Sonrakine not: {kayit['not']}")
    if t:
        satirlar.append(
            f"- Token: giriş {t.get('giris', 0):,} · çıkış {t.get('cikis', 0):,} · önbellek okuma {t.get('onbellek_okuma', 0):,}"
            f" · yazma {t.get('onbellek_yazma', 0):,} · ≈${t.get('maliyet_usd', 0):.3f}".replace(",", ".")
        )
    return "\n".join(satirlar) + "\n\n"


def _defter_dondur(sd: str) -> None:
    md = os.path.join(sd, "ortak_defter.md")
    if os.path.exists(md) and os.path.getsize(md) > DEFTER_MAX_BAYT:
        damga = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.replace(md, os.path.join(sd, f"ortak_defter_{damga}.md"))


def defter_ekle(sd: str, kayit: dict) -> None:
    kayit = dict(kayit)
    kayit.setdefault("zaman", simdi())
    for alan in ("yaptim", "sonuc", "not"):
        if kayit.get(alan):
            kayit[alan] = maskele(str(kayit[alan]))[:900]
    md = os.path.join(sd, "ortak_defter.md")
    with kilit(md):
        _defter_dondur(sd)
        yeni = not os.path.exists(md)
        with open(md, "a", encoding="utf-8", newline="\n") as f:
            if yeni:
                f.write("# Ortak defter\n\nHer ajan bitişinde ne yaptığını buraya yazar (yalnız sona ekleme). "
                        "İhtiyacın olanı `orkestra defter baglam <görev>` ile oku; tamamını okuma.\n\n")
            f.write(defter_blogu(kayit))
        with open(os.path.join(sd, "ortak_defter.jsonl"), "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")


def defter_kayitlari(sd: str) -> list[dict]:
    return jsonl_oku(os.path.join(sd, "ortak_defter.jsonl"))


# ---------------------------------------------------------------- hook çıktısı

def hook_cikti(obj: dict | None = None, kod: int = 0) -> None:
    if obj:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()
    sys.exit(kod)


def stdin_json() -> dict:
    ham = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        return json.loads(ham) if ham.strip() else {}
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- maliyet okuma (tekilleştirilmiş)

def maliyet_kayitlari(sd: str) -> list[dict]:
    """Token defteri satırları, tekilleştirilmiş.

    Kaynaklar: 'tur' = sayaç modülü, motorun turn.complete kullanımı (kesin); 'hook' = SubagentStop/Stop
    transkript okuması (alt ajan çıkış tokenı eksik sayılır); 'gecmis' = geçmiş aktarımı.
    Aynı (oturum, agent_id) için 'tur' satırı varsa o grubun diğer satırları atılır.
    """
    rows = jsonl_oku(os.path.join(sd, "maliyet.jsonl"))
    tur_var = {(r.get("oturum"), r.get("agent_id")) for r in rows if r.get("kaynak") == "tur"}
    return [r for r in rows if r.get("kaynak") == "tur" or (r.get("oturum"), r.get("agent_id")) not in tur_var]


# ---------------------------------------------------------------- sohbetler (çalışma alanındaki oturumlar)

def proje_oturum_dizini(proje: str) -> str:
    ad = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(proje))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", ad)


def _son_json_satiri(veri: bytes, isaret: bytes) -> dict | None:
    i = veri.rfind(isaret)
    if i < 0:
        return None
    bas = veri.rfind(b"\n", 0, i) + 1
    son = veri.find(b"\n", i)
    try:
        return json.loads(veri[bas: son if son >= 0 else len(veri)].decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def sohbetler(sd: str, proje: str, limit: int = 12) -> list[dict]:
    """Çalışma alanının sohbetleri (kenar çubuğundaki adlarıyla), motorun maliyeti ve defterdeki maliyet.

    Ad: transkriptteki son `custom-title`. Motor maliyeti: son `cost-state.totalCostUSD` (motorun kendi hesabı;
    alt ajanlar dahil). Büyük transkriptler yalnız boyut/zaman değişince yeniden okunur.
    """
    dizin = proje_oturum_dizini(proje)
    onb_yolu = os.path.join(sd, "oturumlar", "sohbet_onbellek.json")
    try:
        with open(onb_yolu, encoding="utf-8") as f:
            onb = json.load(f)
    except Exception:
        onb = {}
    dosyalar = sorted(glob.glob(os.path.join(dizin, "*.jsonl")), key=os.path.getmtime, reverse=True)[:limit]
    out, degisti = [], False
    for p in dosyalar:
        oid = os.path.basename(p)[:-6]
        st = os.stat(p)
        imza = f"{st.st_size}:{int(st.st_mtime)}"
        k = onb.get(oid)
        if not k or k.get("imza") != imza:
            with open(p, "rb") as f:
                veri = f.read()
            baslik = _son_json_satiri(veri, b'"type":"custom-title"') or {}
            maliyet = _son_json_satiri(veri, b'"type":"cost-state"') or {}
            ilk = None
            if not baslik:
                for satir in veri.splitlines()[:60]:
                    try:
                        o = json.loads(satir)
                    except Exception:
                        continue
                    if o.get("type") == "user":
                        ilk = _metin((o.get("message") or {}).get("content")).strip().replace("\n", " ")[:50]
                        if ilk:
                            break
            k = {"imza": imza, "baslik": baslik.get("customTitle") or ilk or oid[:8],
                 "motor_usd": maliyet.get("totalCostUSD"),
                 "modeller": {m: round(v.get("costUSD", 0) or 0, 4) for m, v in (maliyet.get("modelUsage") or {}).items()}}
            onb[oid] = k
            degisti = True
        out.append({"oturum": oid, "baslik": k["baslik"], "motor_usd": k["motor_usd"], "modeller": k["modeller"],
                    "son": datetime.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="minutes")})
    if degisti:
        atomik_yaz(onb_yolu, json.dumps(onb, ensure_ascii=False))
    defter: dict = {}
    for r in maliyet_kayitlari(sd):
        defter[r.get("oturum")] = defter.get(r.get("oturum"), 0.0) + (r.get("maliyet_usd") or 0.0)
    for s in out:
        s["defter_usd"] = round(defter.get(s["oturum"], 0.0), 4)
    return out
