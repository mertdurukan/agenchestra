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
import subprocess
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


def _beklemede_konumu(kart: dict):
    """Kartın beklemede olayının konumu: (sira, zaman). Yeni kartlarda `beklemede_sira`, eskilerde gecmis'teki son
    beklemede olayının zaman damgası."""
    sira = kart.get("beklemede_sira")
    zaman = ""
    for g in reversed(kart.get("gecmis", [])):
        if g.get("olay") == "beklemede":
            zaman = g.get("zaman", "")
            break
    return sira, zaman


def kart_durumu_hesapla(kart: dict) -> str:
    """Durum: teslim/iptal yapışkan. Son işçi çıktısından sonraki denetimlerden EN SON olanın (en büyük sira, yoksa
    zaman) kararı geçerlidir (ret → reddedildi, onay → onaylandi). beklemede yalnız kendisinden sonra denetim yoksa
    yapışkandır."""
    durum = kart.get("durum")
    if durum in ("teslim", "iptal"):
        return durum
    # Sıra numarası (aynı saniyedeki olayları da doğru sıralar); eski kartlarda zaman damgasına düşer.
    son_is_sira = kart.get("son_is_sira")
    son_is = kart.get("son_is_zamani")
    denetimler = [d for d in kart.get("denetimler", []) if d.get("karar") in ("ret", "onay")]
    if son_is_sira is not None:
        sonraki = [d for d in denetimler if d.get("sira", -1) > son_is_sira]
    else:
        sonraki = [d for d in denetimler if not son_is or d.get("zaman", "") >= son_is]
    if durum == "beklemede":
        b_sira, b_zaman = _beklemede_konumu(kart)
        if b_sira is not None:
            sonraki = [d for d in sonraki if d.get("sira", -1) > b_sira]
        else:
            sonraki = [d for d in sonraki if d.get("zaman", "") > b_zaman]
        if not sonraki:
            return "beklemede"
    if sonraki:
        if all("sira" in d for d in sonraki):
            son = max(sonraki, key=lambda d: d["sira"])
        else:
            son = max(sonraki, key=lambda d: d.get("zaman", ""))
        return "reddedildi" if son.get("karar") == "ret" else "onaylandi"
    if son_is:
        return "denetimde"
    return durum or "planlandi"


def sonraki_sira(kart: dict) -> int:
    kart["olay_sira"] = kart.get("olay_sira", 0) + 1
    return kart["olay_sira"]


def yazma_alaninda_mi(proje: str, yol: str, desenler: list[str]) -> bool:
    """Yol kartın yazma alanında mı. Göreli desen projeye göredir, mutlak desen olduğu gibi; ikisi de normalize edilmiş
    mutlak yola çevrilip karşılaştırılır (Windows'ta büyük/küçük harf ve / \\ farkı yok sayılır).

    Proje dışı yol serbest DEĞİLDİR, desene göre karar verilir. Tek istisna: geçici klasördeki git dışı yollar
    (scratchpad, ara çıktı) serbesttir."""
    if not desenler:
        return True
    tam = os.path.abspath(yol)
    if desen_eslesir(proje, tam, desenler):
        return True
    if yol_altinda(tam, proje):
        return False
    return yol_altinda(tam, tempfile.gettempdir()) and not git_koku(tam)


# ---------------------------------------------------------------- kart izolasyonu
# Paralel kartlar aynı fiziksel çalışma ağacında aynı dosyalara yazmasın: yazma alanı çakışma kapısı (muhafazakâr glob
# kesişimi) ve kart başına git çalışma ağacı (`kart/<id>` dalı) + teslimde `--no-ff` birleştirme. Çatışma asla otomatik
# çözülmez.

_GLOB_KARAKTER = re.compile(r"[*?\[]")


def _kiyas(yol: str) -> str:
    y = yol.replace("\\", "/").rstrip("/") or "/"
    return y.lower() if os.name == "nt" else y


def yol_altinda(yol: str, kok: str) -> bool:
    """`yol`, `kok` ile aynı ya da onun altında mı (bileşen bazında; Windows'ta büyük/küçük harf duyarsız)."""
    y, k = _kiyas(os.path.abspath(yol)), _kiyas(os.path.abspath(kok))
    return y == k or y.startswith(k.rstrip("/") + "/")


def desen_parcala(proje: str, desen: str) -> tuple[str, str]:
    """Deseni (mutlak literal önek, glob kalanı) olarak böler; göreli desen projeye göredir. Ayraç '/'."""
    d = (desen or "").replace("\\", "/").strip()
    while len(d) > 1 and d.endswith("/"):
        d = d[:-1]
    if not (os.path.isabs(d) or re.match(r"^[A-Za-z]:", d)):
        d = proje.replace("\\", "/").rstrip("/") + "/" + d
    parcalar = d.split("/")
    i = next((n for n, p in enumerate(parcalar) if _GLOB_KARAKTER.search(p)), len(parcalar))
    onek = "/".join(parcalar[:i]) or "/"
    if re.fullmatch(r"[A-Za-z]:", onek):
        onek += "/"
    onek = os.path.abspath(onek).replace("\\", "/")
    return onek, "/".join(parcalar[i:])


def desen_mutlak(proje: str, desen: str) -> str:
    onek, kalan = desen_parcala(proje, desen)
    return onek.rstrip("/") + "/" + kalan if kalan else onek


def desen_eslesir(proje: str, yol: str, desenler: list[str]) -> bool:
    """Mutlak yolun desenlerden birine GERÇEKTEN uyup uymadığı (proje dışı yollar serbest sayılmaz)."""
    y = _kiyas(os.path.abspath(yol))
    for d in desenler or []:
        onek, kalan = desen_parcala(proje, d)
        if not kalan:
            if yol_altinda(yol, onek):
                return True
            continue
        tam = _kiyas(onek.rstrip("/") + "/" + kalan)
        if fnmatch.fnmatchcase(y, tam) or fnmatch.fnmatchcase(y, tam + "/**"):
            return True
    return False


def desen_kesisir(proje: str, a: str, b: str) -> bool:
    """Muhafazakâr kesişim: literal öneklerden biri diğerinin altındaysa ya da desenler birbirine fnmatch ile uyuyorsa."""
    oa, ka = desen_parcala(proje, a)
    ob, kb = desen_parcala(proje, b)
    if yol_altinda(oa, ob) or yol_altinda(ob, oa):
        return True
    ta, tb = _kiyas(desen_mutlak(proje, a)), _kiyas(desen_mutlak(proje, b))
    return fnmatch.fnmatchcase(ta, tb) or fnmatch.fnmatchcase(tb, ta)


def git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def git_koku(yol: str, onbellek: dict | None = None) -> str | None:
    """Yolun (ya da var olan en yakın üst klasörünün) içinde bulunduğu git çalışma ağacının kökü; yoksa None."""
    d = os.path.abspath(yol)
    while not os.path.isdir(d):
        ust = os.path.dirname(d)
        if ust == d:
            return None
        d = ust
    if onbellek is not None and d in onbellek:
        return onbellek[d]
    try:
        r = git(["rev-parse", "--show-toplevel"], d)
        kok = os.path.abspath(r.stdout.strip()).replace("\\", "/") if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, ValueError):
        kok = None
    if onbellek is not None:
        onbellek[d] = kok
    return kok


def _gercek(yol: str) -> str:
    """Bağlantı/junction ve harf farkından bağımsız karşılaştırma biçimi (var olmayan kuyruk olduğu gibi kalır)."""
    try:
        return _kiyas(os.path.realpath(yol))
    except (OSError, ValueError):
        return _kiyas(os.path.abspath(yol))


def kok_kapsiyor_mu(proje: str, desen: str, onbellek: dict | None = None) -> str | None:
    """Desen paylaşılan ağaçta izinli değilse nedeni (dolu metin), izinliyse None. İZİN LİSTESİ: kabul edilen tek
    biçim, sabit öneki (ilk joker bileşenden önceki mutlak yol) bir git deposunun KESİN alt yolu olan desendir.

    - Önek hiçbir deponun içinde değilse joker taşıyan ya da var olan bir klasörü gösteren desen reddedilir: altında
      hangi depoların olduğu (bugün ya da sonra) bilinemez. Depo dışındaki tek dosya literal yolu kabul edilir.
      Proje git deposu değilse proje klasörü kök sayılır (git dışı projede 'docs/**' geçer, '**' geçmez).
    - Önek deponun kökünün kendisiyse (ya da depo içine çözülmüyorsa) desen reddedilir. Kalanın biçimine
      bakılmaz: fnmatch'te '*' '/' dahil her karaktere uyar; kökteki '*.md' bile bütün alt klasörlere uzanır.
    Göreli desen projeye göre mutlaklaştırılır ('*/**' → proje kökü → ret). Depo içindeki iç içe depolar (önekin
    altında) bu kuralın değil, `yazma_cakismalari`ndaki fiziksel kesişim denetiminin konusudur."""
    onek, kalan = desen_parcala(proje, desen)
    kok = git_koku(onek, onbellek)
    if kok is None and yol_altinda(onek, proje) and git_koku(proje, onbellek) is None:
        kok = os.path.abspath(proje).replace("\\", "/")  # git dışı proje ('.git/**' gibi depo içi yollar buraya düşmez)
    if kok is None:
        if kalan or os.path.isdir(onek):
            return "git deposunun içinde değil; depo dışında joker ya da klasör alanı bir deponun kökünü kapsayabilir"
        return None
    o, k = _gercek(onek), _gercek(kok)
    if not o.startswith(k.rstrip("/") + "/"):
        return f"{kok} deposunun kökünü kapsıyor; sabit önek deponun bir alt klasörü ya da dosyası olmalı"
    return None


def yazma_cakismalari(sd: str, proje: str, kart: dict) -> list[str]:
    """Kartın yazma alanını AYNI fiziksel ağaçta açık olan diğer kartlarla (hangi oturumdan olursa olsun) karşılaştırır.

    Dönen: hata/uyarı metinleri (boşsa çakışma yok). Kendi çalışma ağacı olan kart paylaşılan ağaçta sayılmaz."""
    desenler = [d for d in kart.get("yazma_alani") or [] if (d or "").strip()]
    if not desenler:
        return []
    onbellek: dict = {}
    hatalar = []
    if not (kart.get("calisma_agaci") or {}).get("yol"):
        for d in desenler:
            neden = kok_kapsiyor_mu(proje, d, onbellek)
            if neden:
                hatalar.append(f"'{d}' paylaşılan ağaçta izinli değil: {neden} — alanı daralt ya da ayrı çalışma "
                               f"ağacı aç (`orkestra kart agac {kart.get('id')}`)")
    for k in kartlar(sd):
        if k.get("id") == kart.get("id") or kart_durumu_hesapla(k) not in ACIK_DURUMLAR:
            continue
        bulundu = None
        for a in desenler:
            agac_a = git_koku(desen_parcala(proje, a)[0], onbellek)
            for b in k.get("yazma_alani") or []:
                if not (b or "").strip():
                    continue
                agac_b = git_koku(desen_parcala(proje, b)[0], onbellek)
                if agac_a and agac_b and not (yol_altinda(agac_a, agac_b) or yol_altinda(agac_b, agac_a)):
                    continue  # ayrık fiziksel çalışma ağaçları çakışmaz; iç içe depo (biri ötekinin altında) ayrık değil
                if desen_kesisir(proje, a, b):
                    bulundu = b
                    break
            if bulundu:
                break
        if bulundu:
            hatalar.append(f"çakışma: {k['id']} ({bulundu}) — bekle ya da ayrı çalışma ağacı aç "
                           f"(`orkestra kart agac {kart.get('id')}`)")
    return hatalar


CALISMA_AGACI_ONEKI = "Çalışma ağacı: "
AGAC_KOK_KAPSAMIYOR = "kart ağacı proje kökünü kapsamıyor; test-kos ağaçta koşamaz"


def kart_agaci_ac(proje: str, kart: dict, taban: str = "HEAD") -> tuple[dict, list[str]]:
    """Kartın yazma alanının bulunduğu git deposunda `<depo>-kart-<id>` klasörüne `kart/<id>` dalıyla worktree açar.

    Dönen: (calisma_agaci, yeni köke çevrilmiş yazma alanı). Hata durumunda ValueError."""
    gid = kart["id"]
    if (kart.get("calisma_agaci") or {}).get("yol"):
        raise ValueError(f"{gid} kartının zaten çalışma ağacı var: {kart['calisma_agaci']['yol']}")
    desenler = [d for d in kart.get("yazma_alani") or [] if (d or "").strip()]
    kokler = {git_koku(desen_parcala(proje, d)[0]) for d in desenler} if desenler else {git_koku(proje)}
    if None in kokler or len(kokler) != 1:
        raise ValueError("yazma alanı tek bir git deposunun içinde olmalı (bulunan: "
                         + ", ".join(sorted(str(k) for k in kokler)) + ")")
    depo = kokler.pop()
    if kart.get("sinif") == "kod" and kart.get("test_alani") and not yol_altinda(proje, depo):
        raise ValueError(f"{gid}: {AGAC_KOK_KAPSAMIYOR} (depo {depo}, proje {os.path.abspath(proje)}); kod kartının "
                         "test_komutu ve test_alani proje köküne göredir, ağaçtaki kodu sınayamaz. Kartı paylaşılan "
                         "ağaçta yürüt ya da depoyu kapsayan bir projeden çalış.")
    yol = f"{depo}-kart-{gid}"
    dal = f"kart/{gid}"
    if os.path.exists(yol):
        raise ValueError(f"çalışma ağacı klasörü zaten var: {yol}")
    r = git(["rev-parse", "--verify", taban + "^{commit}"], depo)
    if r.returncode != 0:
        raise ValueError(f"taban okunamadı ({taban}): {(r.stderr or r.stdout).strip()}")
    taban_sha = r.stdout.strip()
    r = git(["worktree", "add", "-b", dal, yol, taban_sha], depo)
    if r.returncode != 0:
        raise ValueError(f"git worktree add başarısız: {(r.stderr or r.stdout).strip()}")
    yeni = []
    for d in desenler:
        tam = desen_mutlak(proje, d)
        if _kiyas(tam) == _kiyas(depo) or _kiyas(tam).startswith(_kiyas(depo) + "/"):
            tam = yol + tam[len(depo.rstrip("/")):]
        yeni.append(tam)
    return {"depo": depo, "yol": yol, "dal": dal, "taban": taban_sha}, yeni


def agac_esdegeri(kart: dict, yol: str) -> str | None:
    """Kartın çalışma ağacı altındaki yolun paylaşılan depodaki karşılığı (mutlak, '/'); ağaç dışıysa ya da ağaç yoksa None.

    test_alani ve test kilidi proje köküne göre yazılır; ağaçtaki yazım bu karşılık üzerinden aynı kurallara bağlanır."""
    ca = (kart or {}).get("calisma_agaci") or {}
    if not (ca.get("yol") and ca.get("depo")) or not yol_altinda(yol, ca["yol"]):
        return None
    y = os.path.abspath(yol).replace("\\", "/")
    kok = os.path.abspath(ca["yol"]).replace("\\", "/").rstrip("/")
    return os.path.abspath(ca["depo"]).replace("\\", "/").rstrip("/") + y[len(kok):]


def kart_proje_koku(proje: str, kart: dict) -> str:
    """Kartın testlerinin koşacağı ve test özetlerinin alınacağı kök: kart ağacı varsa projenin ağaçtaki karşılığı
    (ağaç yolu + relpath(proje, depo)), ağaç yoksa proje.

    Ağaç proje kökünü kapsamıyorsa (depo projenin alt klasörü ya da projeden ayrık) ValueError: test_komutu ve
    test_alani proje köküne göredir, ağaçta karşılıkları yoktur. Paylaşılan köke düşmek ağaçtaki kodu sınamaz ve
    yeşil kapıyı yanıltır; çağıran (test-kos, onay kapısı) açık hata verir. `kart_agaci_ac` bu düzende kod kartına
    ağaç açmaz; bu dal o denetimden önce açılmış ağaçlar içindir."""
    ca = (kart or {}).get("calisma_agaci") or {}
    if not ca.get("yol"):
        return proje
    if not (ca.get("depo") and yol_altinda(proje, ca["depo"])):
        raise ValueError(f"{AGAC_KOK_KAPSAMIYOR} (depo {ca.get('depo') or '-'}, ağaç {ca['yol']}, proje "
                         f"{os.path.abspath(proje)}). Paylaşılan ağaçta koşmak ağaçtaki kodu sınamaz; ağacı "
                         f"`orkestra kart birlestir {(kart or {}).get('id', '<id>')}` ile paylaşılan ağaca al, "
                         "sonra test-kos koş.")
    r = os.path.relpath(os.path.abspath(proje), os.path.abspath(ca["depo"]))
    return os.path.abspath(ca["yol"] if r == "." else os.path.join(ca["yol"], r))


def _git_bayt(args: list[str], cwd: str) -> bytes | None:
    """git çıktısı ham bayt olarak (dosya içeriği, -z listeleri); hata ya da sıfırdan farklı çıkışta None."""
    try:
        r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True)
    except (OSError, ValueError):
        return None
    return r.stdout if r.returncode == 0 else None


def _goreli_anahtar(rel: str) -> str:
    r = rel.replace("\\", "/")
    return r.lower() if os.name == "nt" else r


def birlestirme_kilit_ihlalleri(proje: str, kart: dict, ks: list[dict]) -> tuple[list[tuple[str, str, str]], str | None]:
    """Birleştirme öncesi deterministik kilit kapısı: hook'u atlatan dolaylı yazımların (ağaçta git checkout, betik,
    doğrudan dosya sistemi + commit) son savunması.

    Kart dalında değişen dosyalar (`git diff --name-only --no-renames -z` ile `<taban>...<dal>` ve `HEAD...<dal>`
    birleşimi) paylaşılan proje-göreli yola çevrilir. Teslim/iptal dışındaki herhangi bir kartın (kartın kendisi dahil)
    kilitli test dosyasıyla kesişen her dosyanın DAL UCUNDAKİ içeriği kilitteki özetle karşılaştırılır; değişmiş ya da
    silinmişse ihlaldir (birleşme kilitli testi paylaşılan ağaçta değiştirirdi; kartın kendi kilidiyse kilit bozulmuş
    demektir). Dalda yeni yazılıp kilitlenmiş testin kilitteki hâliyle gelmesi ihlal değildir (olağan akış). Satır sonu
    dönüşümü (core.autocrlf) yanlış ret üretmesin diye ham blob ve çıkış filtresinden geçmiş içerik birlikte denenir.

    Dönen: ([(proje-göreli yol, kilit sahibi kart, 'değişmiş'|'silinmiş')], okuma hatası ya da None)."""
    import hashlib
    ca = kart.get("calisma_agaci") or {}
    depo, dal, taban = ca.get("depo"), ca.get("dal"), ca.get("taban")
    kilitler: dict[str, list[tuple[str, str, str]]] = {}
    for k in [kart] + [x for x in ks if x.get("id") != kart.get("id")]:
        if k.get("durum") in ("teslim", "iptal"):
            continue
        d = (k.get("test_kilidi") or {}).get("dosyalar")
        if isinstance(d, dict):
            for y, h in d.items():
                kilitler.setdefault(_goreli_anahtar(y), []).append((y.replace("\\", "/"), k.get("id", "?"), h))
    if not kilitler:
        return [], None
    adlar = set()
    for aralik in ([f"{taban}...{dal}"] if taban else []) + [f"HEAD...{dal}"]:
        b = _git_bayt(["diff", "--name-only", "--no-renames", "-z", aralik], depo)
        if b is None:
            return [], f"kart dalının farkı okunamadı ({aralik})"
        adlar.update(x for x in b.decode("utf-8", "surrogateescape").split("\0") if x)
    filtre_cwd = ca["yol"] if ca.get("yol") and os.path.isdir(ca["yol"]) else depo
    ihlaller = []
    for p in sorted(adlar):
        tam = depo.rstrip("/\\") + "/" + p
        if not yol_altinda(tam, proje):
            continue
        sahipler = kilitler.get(_goreli_anahtar(os.path.relpath(os.path.abspath(tam), os.path.abspath(proje))))
        if not sahipler:
            continue
        ozet = set()
        for args in (["cat-file", "blob", f"{dal}:{p}"], ["cat-file", "--filters", f"{dal}:{p}"]):
            icerik = _git_bayt(args, filtre_cwd)
            if icerik is not None:
                ozet.add(hashlib.sha256(icerik).hexdigest())
        for rel, gid, h in sahipler:
            if h not in ozet:
                ihlaller.append((rel, gid, "değişmiş" if ozet else "silinmiş"))
    return ihlaller, None


def kart_agaci_birlestir(kart: dict, mesaj: str | None = None, proje: str | None = None,
                         ks: list[dict] | None = None) -> dict:
    """Kart dalını deponun güncel dalına `--no-ff` ile birleştirir. Sessiz ezme ve otomatik çözüm yok.

    Merge'den önce kilit kapısı (`birlestirme_kilit_ihlalleri`; `ks` diğer kartlar, kartın kendi kilidi her zaman):
    ihlalde birleştirme yapılmaz, worktree ve dal korunur.
    Dönen: {"sonuc": "tamam"|"kirli-kart"|"kilit"|"kirli-ana"|"catisma"|"hata", "mesaj": str, "dosyalar": [..],
    "commit": sha}"""
    ca = kart.get("calisma_agaci") or {}
    depo, yol, dal = ca.get("depo"), ca.get("yol"), ca.get("dal")
    if not (depo and dal):
        return {"sonuc": "hata", "mesaj": "kartın çalışma ağacı yok", "dosyalar": []}
    if yol and os.path.isdir(yol):
        r = git(["status", "--porcelain", "--untracked-files=all"], yol)
        if r.returncode != 0:
            return {"sonuc": "hata", "mesaj": f"kart ağacı okunamadı: {(r.stderr or r.stdout).strip()}", "dosyalar": []}
        kirli = [s[3:] for s in r.stdout.splitlines() if s.strip()]
        if kirli:
            return {"sonuc": "kirli-kart", "dosyalar": kirli,
                    "mesaj": f"kart dalında commitlenmemiş değişiklik var ({yol}): {', '.join(kirli[:10])} — önce commit et"}
    ihlaller, okuma_hatasi = birlestirme_kilit_ihlalleri(proje or proje_dizini(), kart, ks or [])
    if okuma_hatasi:
        return {"sonuc": "hata", "dosyalar": [], "mesaj": f"kilit kapısı: {okuma_hatasi} — birleştirme yapılmadı"}
    if ihlaller:
        kendi = kart.get("id")
        liste = "; ".join(f"{rel} ({gid} kartının kilidi{' — kartın kendisi, kilit bozulmuş' if gid == kendi else ''}, "
                          f"dalda {neden})" for rel, gid, neden in ihlaller)
        sahipler = ", ".join(sorted({gid for _, gid, _ in ihlaller}))
        return {"sonuc": "kilit", "dosyalar": sorted({rel for rel, _, _ in ihlaller}),
                "mesaj": f"kilitli test birleştirmeyi engelliyor: {liste}. Birleştirme yapılmadı (paylaşılan ağaç "
                         f"değişmedi); worktree ve {dal} korunuyor. Dalda dosyayı kilitteki hâline döndürüp commitle; "
                         f"değişiklik gerçekten gerekiyorsa kilit sahibi ({sahipler}) bitene kadar bekle ya da ana ajan "
                         "`orkestra kart test-kilit-ac` ile kilidi açsın."}
    r = git(["diff", "--name-only", f"HEAD...{dal}"], depo)
    if r.returncode != 0:
        return {"sonuc": "hata", "mesaj": f"kart dalı okunamadı ({dal}): {(r.stderr or r.stdout).strip()}", "dosyalar": []}
    dosyalar = [s for s in r.stdout.splitlines() if s.strip()]
    if dosyalar:
        r = git(["status", "--porcelain", "--untracked-files=all", "--"] + dosyalar, depo)
        kirli = [s[3:] for s in r.stdout.splitlines() if s.strip()]
        if r.returncode != 0 or kirli:
            return {"sonuc": "kirli-ana", "dosyalar": kirli,
                    "mesaj": f"ana ağaçta kartın dosyalarında commitlenmemiş değişiklik var ({depo}): {', '.join(kirli[:10])} "
                             "— sessiz ezme yok; önce o değişiklikleri commitle ya da kaldır"}
    r = git(["merge", "--no-ff", "--no-edit", "-m", mesaj or f"Kart {kart.get('id')} birleştirme ({dal})", dal], depo)
    if r.returncode != 0:
        cat = git(["diff", "--name-only", "--diff-filter=U"], depo)
        catisan = [s for s in cat.stdout.splitlines() if s.strip()]
        ab = git(["merge", "--abort"], depo)
        if catisan or ab.returncode == 0:
            return {"sonuc": "catisma", "dosyalar": catisan,
                    "mesaj": f"birleştirme çatıştı, geri alındı (merge --abort): {', '.join(catisan) or '-'}"}
        return {"sonuc": "hata", "dosyalar": [], "mesaj": f"git merge başarısız: {(r.stderr or r.stdout).strip()}"}
    commit = git(["rev-parse", "HEAD"], depo).stdout.strip()
    uyari = []
    if yol and os.path.isdir(yol):
        rr = git(["worktree", "remove", yol], depo)
        if rr.returncode != 0:
            uyari.append(f"worktree kaldırılamadı: {(rr.stderr or rr.stdout).strip()}")
    rr = git(["branch", "-d", dal], depo)
    if rr.returncode != 0:
        uyari.append(f"dal silinemedi: {(rr.stderr or rr.stdout).strip()}")
    return {"sonuc": "tamam", "dosyalar": dosyalar, "commit": commit,
            "mesaj": f"{dal} → {depo} birleştirildi ({commit[:8]})" + ("; " + "; ".join(uyari) if uyari else "")}


# ---------------------------------------------------------------- test kapısı (kod kartları)

TEST_KUYRUK_MAX = 2000


def test_dosyasi_ozetleri(proje: str, desenler: list[str]) -> dict[str, str]:
    """test_alani desenlerine (proje köküne göre glob, `**` özyinelemeli) uyan proje içi dosyalar → {göreli yol ('/'): sha256}.

    Klasörler, __pycache__ ve .pyc hariç (test koşusunun kendi ürettiği dosyalar kilidi bozmasın)."""
    import hashlib
    kok = os.path.abspath(proje)
    out = {}
    for d in desenler or []:
        d = (d or "").replace("\\", "/").strip()
        if not d:
            continue
        for tam in glob.glob(os.path.join(kok, d), recursive=True):
            if not os.path.isfile(tam):
                continue
            try:
                rel = os.path.relpath(os.path.abspath(tam), kok).replace("\\", "/")
            except ValueError:
                continue  # farklı sürücü: proje dışı
            if rel == ".." or rel.startswith("../") or "__pycache__" in rel.split("/") or rel.endswith(".pyc") or rel in out:
                continue
            h = hashlib.sha256()
            try:
                with open(tam, "rb") as f:
                    for parca in iter(lambda: f.read(1 << 16), b""):
                        h.update(parca)
            except OSError:
                continue
            out[rel] = h.hexdigest()
    return out


def kilit_farki(kilit_dosyalar: dict | None, mevcut: dict) -> dict:
    """Kilitteki özetlerle mevcut özetlerin farkı → {"eklenen": [...], "silinen": [...], "degisen": [...]}."""
    kilit_dosyalar = kilit_dosyalar or {}
    return {"eklenen": sorted(set(mevcut) - set(kilit_dosyalar)),
            "silinen": sorted(set(kilit_dosyalar) - set(mevcut)),
            "degisen": sorted(y for y in set(kilit_dosyalar) & set(mevcut) if kilit_dosyalar[y] != mevcut[y])}


def kilitle_tutarli(test_kilidi: dict | None, mevcut: dict) -> bool:
    """Dosya kümesi ve özetleri kilittekiyle birebir aynı mı (ekleme, silme, değişiklik tutarsızlıktır). Kilit yoksa False."""
    if not test_kilidi or not isinstance(test_kilidi.get("dosyalar"), dict):
        return False
    return not any(kilit_farki(test_kilidi["dosyalar"], mevcut).values())


def kabuk_kos(komut: str, cwd: str, zaman_asimi: float) -> tuple[int, str, float]:
    """Komutu kabukla çalıştırır → (çıkış kodu, birleşik stdout+stderr, süre sn).

    Zaman aşımında süreç ağacı öldürülür ve çıkış kodu -1 döner."""
    import subprocess
    bas = time.monotonic()
    ek = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    p = subprocess.Popen(komut, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, **ek)
    try:
        cikti, _ = p.communicate(timeout=zaman_asimi)
        kod = p.returncode
    except subprocess.TimeoutExpired:
        kod = -1
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=15)
            else:
                import signal
                os.killpg(p.pid, signal.SIGKILL)
        except Exception:
            pass
        try:
            p.kill()
        except Exception:
            pass
        try:
            cikti, _ = p.communicate(timeout=15)
        except Exception:
            cikti = b""
        cikti = (cikti or b"") + f"\n[orkestra: zaman aşımı ({zaman_asimi:g} sn)]".encode("utf-8")
    metin = (cikti or b"").decode("utf-8", errors="replace").replace("\r\n", "\n")
    return kod, metin, round(time.monotonic() - bas, 2)


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
    if not kayit.get("oturum"):  # CLI/ruya yolu: yazan oturumun kimliği ortamdan (alt ajanda üst oturum)
        kayit["oturum"] = os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID") or None
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
    Aynı (oturum, agent_id) için 'tur' satırı varsa o grubun diğer satırları atılır ('tur' satırları parçadır, hepsi
    kalır). 'tur' satırı olmayan ve agent_id dolu grupta hook/eski satırlar BİRİKİMLİDİR (ajan SendMessage ile
    sürdürülünce her SubagentStop tüm transkripti yeniden okur): yalnız en son satır (zaman, eşitse maliyet_usd en
    büyük) kalır. agent_id boş (ana ajan) satırlarına dokunulmaz.
    """
    rows = jsonl_oku(os.path.join(sd, "maliyet.jsonl"))
    tur_var = {(r.get("oturum"), r.get("agent_id")) for r in rows if r.get("kaynak") == "tur"}
    son: dict = {}
    for r in rows:
        k = (r.get("oturum"), r.get("agent_id"))
        if r.get("kaynak") == "tur" or k in tur_var or not r.get("agent_id"):
            continue
        anahtar = (r.get("zaman") or "", r.get("maliyet_usd") or 0)
        if k not in son or anahtar >= son[k][0]:
            son[k] = (anahtar, r)
    out = []
    for r in rows:
        k = (r.get("oturum"), r.get("agent_id"))
        if r.get("kaynak") == "tur":
            out.append(r)
        elif k in tur_var:
            continue
        elif not r.get("agent_id") or son[k][1] is r:
            out.append(r)
    return out


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


GENEL_DIZIN = os.path.join(os.path.expanduser("~"), ".claude", "orkestra-panel")


def _transkript_tahmini(ana: str) -> tuple[float, dict]:
    """cost-state yokken (açık sohbet) transkriptten maliyet tahmini: ana zincir + alt ajanlar."""
    toplam, modeller = 0.0, {}
    oid = os.path.basename(ana)[:-6]
    yollar = [(ana, False)] + [(a, None) for a in glob.glob(os.path.join(os.path.dirname(ana), oid, "subagents", "agent-*.jsonl"))]
    for yol, zincir in yollar:
        o = transkript_oku(yol, 0, yan_zincir=zincir)
        for m, d in o["modeller"].items():
            modeller[m] = round(modeller.get(m, 0.0) + d["maliyet_usd"], 4)
            toplam += d["maliyet_usd"]
    return round(toplam, 4), modeller


def sohbetler(sd: str | None, proje: str, limit: int = 12, tahmin: bool | None = None,
              oturum_dizini: str | None = None) -> list[dict]:
    """Çalışma alanının sohbetleri (kenar çubuğundaki adlarıyla) ve maliyetleri.

    Ad: transkriptteki son `custom-title`. Kesin maliyet: son `cost-state.totalCostUSD` (Claude'un kendi hesabı;
    sohbet kapanınca yazılır). Açık sohbette: orkestra defteri (`sd` varsa) ya da transkript tahmini.
    Büyük transkriptler yalnız boyut/zaman değişince yeniden okunur; önbellek orkestra varsa durum klasöründe,
    yoksa ~/.claude/orkestra-panel altında.
    """
    dizin = oturum_dizini or proje_oturum_dizini(proje)
    if tahmin is None:
        tahmin = sd is None
    onb_yolu = (os.path.join(sd, "oturumlar", "sohbet_onbellek.json") if sd
                else os.path.join(GENEL_DIZIN, "onbellek", os.path.basename(dizin) + ".json"))
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
        if not k or k.get("imza") != imza or (tahmin and "tahmin_usd" not in k and not k.get("motor_usd")):
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
            if tahmin and not k["motor_usd"]:
                k["tahmin_usd"], tm = _transkript_tahmini(p)
                k["modeller"] = tm
            onb[oid] = k
            degisti = True
        out.append({"oturum": oid, "baslik": k["baslik"], "motor_usd": k["motor_usd"], "modeller": k["modeller"],
                    "tahmin_usd": k.get("tahmin_usd"),
                    "son": datetime.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="minutes")})
    if degisti:
        atomik_yaz(onb_yolu, json.dumps(onb, ensure_ascii=False))
    defter: dict = {}
    if sd:
        for r in maliyet_kayitlari(sd):
            defter[r.get("oturum")] = defter.get(r.get("oturum"), 0.0) + (r.get("maliyet_usd") or 0.0)
    for s in out:
        s["defter_usd"] = round(defter.get(s["oturum"], 0.0), 4)
    return out


def calisma_alanlari() -> list[dict]:
    """Bu bilgisayardaki Claude çalışma alanları (~/.claude/projects): ad, gerçek yol, orkestra kurulu mu, son etkinlik.

    Gerçek yol transkriptteki `cwd`dan okunur (önbellekli). Geçici klasörler (Temp altındakiler) listelenmez.
    """
    kok = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    onb_yolu = os.path.join(GENEL_DIZIN, "alanlar.json")
    try:
        with open(onb_yolu, encoding="utf-8") as f:
            onb = json.load(f)
    except Exception:
        onb = {}
    out, degisti = [], False
    for d in sorted(glob.glob(os.path.join(kok, "*"))):
        if not os.path.isdir(d):
            continue
        dosyalar = glob.glob(os.path.join(d, "*.jsonl"))
        if not dosyalar:
            continue
        aid = os.path.basename(d)
        son = max(dosyalar, key=os.path.getmtime)
        yol = (onb.get(aid) or {}).get("yol")
        if not yol:
            with open(son, "rb") as f:
                bas = f.read(400_000)
            m = re.search(rb'"cwd":"((?:[^"\\]|\\.)*)"', bas)
            yol = json.loads(b'"' + m.group(1) + b'"') if m else None
            if yol:
                onb[aid] = {"yol": yol}
                degisti = True
        if not yol or re.search(r"[\\/]AppData[\\/]Local[\\/]Temp[\\/]", yol, re.I):
            continue
        out.append({"id": aid, "ad": os.path.basename(yol.rstrip("\\/")) or yol, "yol": yol,
                    "orkestra": os.path.isdir(os.path.join(yol, ".claude", "orkestra")),
                    "sohbet": len(dosyalar),
                    "son": datetime.datetime.fromtimestamp(os.path.getmtime(son)).astimezone().isoformat(timespec="minutes")})
    adlar = {}
    for a in out:
        adlar.setdefault(a["ad"], []).append(a)
    for ayni in adlar.values():
        if len(ayni) > 1:
            for a in ayni:
                ust = os.path.basename(os.path.dirname(a["yol"].rstrip("\\/")))
                a["ad"] = f"{a['ad']} ({ust[:30]})"
    if degisti:
        atomik_yaz(onb_yolu, json.dumps(onb, ensure_ascii=False))
    return sorted(out, key=lambda a: a["son"], reverse=True)


# ---------------------------------------------------------------- plugin önbellek bayatlığı

def claude_exe() -> str | None:
    """claude.exe: CLAUDE_CODE_EXECPATH > %APPDATA%/%LOCALAPPDATA% altındaki en yeni > PATH."""
    e = os.environ.get("CLAUDE_CODE_EXECPATH")
    if e and os.path.exists(e):
        return e
    adaylar = []
    for kok in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
        if not kok:
            continue
        adaylar += glob.glob(os.path.join(kok, "Claude", "claude-code", "*", "*", "claude.exe"))
        adaylar += glob.glob(os.path.join(kok, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude", "claude-code", "*", "*", "claude.exe"))
    adaylar = [a for a in adaylar if os.path.exists(a)]
    if adaylar:
        return max(adaylar, key=os.path.getmtime)
    import shutil
    return shutil.which("claude")


def pazar_kaynagi(pazar: str = "claude-orchestration") -> str | None:
    """known_marketplaces.json'daki installLocation (kaynak depo klasörü)."""
    try:
        with open(os.path.join(os.path.expanduser("~"), ".claude", "plugins", "known_marketplaces.json"), encoding="utf-8") as f:
            yol = (json.load(f).get(pazar) or {}).get("installLocation")
        return yol if yol and os.path.isdir(yol) else None
    except Exception:
        return None


def icerik_ozetleri(kok: str) -> dict[str, str]:
    """{göreli yol: sha1}; __pycache__ ve .in_use klasörleri, .in_use / .orphaned_at / .pyc dosyaları hariç; CRLF/LF farkı yok sayılır."""
    import hashlib
    out = {}
    for d, altlar, dosyalar in os.walk(kok):
        altlar[:] = [x for x in altlar if x not in ("__pycache__", ".in_use")]
        for ad in dosyalar:
            if ad in (".in_use", ".orphaned_at") or ad.endswith(".pyc"):
                continue
            tam = os.path.join(d, ad)
            try:
                with open(tam, "rb") as f:
                    b = f.read().replace(bytes([13, 10]), bytes([10]))
            except OSError:
                continue
            out[os.path.relpath(tam, kok).replace("\\", "/")] = hashlib.sha1(b).hexdigest()
    return out


def bayatlik(calisan: str | None = None, kaynak_depo: str | None = None) -> dict | None:
    """Çalışan kopya ile kaynak plugins/orkestra arasındaki fark. Aynıysa, kaynak klasörde çalışıyorsa ya da kaynak yoksa None.
    Dönüş: {"farkli": n, "kaynakta_commitsiz": bool|None, "kaynak": yol}."""
    calisan = calisan or os.environ.get("CLAUDE_PLUGIN_ROOT") or PLUGIN_ROOT
    kaynak_depo = kaynak_depo or pazar_kaynagi()
    if not kaynak_depo:
        return None
    kaynak = os.path.join(kaynak_depo, "plugins", "orkestra")
    if not os.path.isdir(kaynak):
        return None
    gercek = lambda p: os.path.normcase(os.path.realpath(p))
    if gercek(calisan) == gercek(kaynak) or gercek(calisan).startswith(gercek(kaynak_depo) + os.sep):
        return None
    a, b = icerik_ozetleri(calisan), icerik_ozetleri(kaynak)
    fark = sum(1 for k in set(a) | set(b) if a.get(k) != b.get(k))
    if not fark:
        return None
    commitsiz = None
    try:
        import subprocess
        r = subprocess.run(["git", "-C", kaynak_depo, "status", "--porcelain", "--", "plugins", ".claude-plugin"],
                           capture_output=True, text=True, timeout=1.0)
        if r.returncode == 0:
            commitsiz = bool(r.stdout.strip())
    except Exception:
        pass
    return {"farkli": fark, "kaynakta_commitsiz": commitsiz, "kaynak": kaynak_depo}
