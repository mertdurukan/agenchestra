"""Orkestra çekirdek kütüphanesi.

Durum klasörü: <proje>/.claude/orkestra/  (yalnız `orkestra baslat` ile açılan projelerde)
  gorevler/<id>.json        görev kartları (yalnız CLI yazar)
  ortak_defter.md / .jsonl  herkesin ne yaptığı (yalnız sona ekleme)
  maliyet.jsonl             ajan x süreç x model token ve maliyet kaydı
  gunluk.jsonl              olay günlüğü (istekler, skill/ajan kullanımı) — skill avcısı okur
  oturumlar/<id>.json       oturum başına transkript okuma ofseti
  perspektif/                     perspektif (hafıza bakımı) raporları ve zaman damgası
  onerilen_skill/           skill avcısının taslakları
Bağımlılık yok: yalnız Python standart kütüphanesi.
"""
from __future__ import annotations

import copy
import datetime
import fnmatch
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SURECLER = (
    "triyaj", "plan", "is", "denetim", "duzeltme", "yukseltme", "sentez",
    "arsiv", "perspektif", "skill-avi", "arastirma", "orkestrasyon", "test-yaz", "on-kontrol", "test-kapisi", "bilinmiyor",
)
ACIK_DURUMLAR = ("isleniyor", "denetimde", "reddedildi", "onaylandi")
KAPALI_DURUMLAR = ("teslim", "iptal", "beklemede", "planlandi")
ETIKET_GOREV = re.compile(r"#GOREV:([A-Za-z0-9_.\-]+)")
ETIKET_SUREC = re.compile(r"#SUREC:([a-z\-]+)")
DEFTER_MAX_BAYT = 4 * 1024 * 1024
# Konsolsuz (panel gibi ayrık) süreçten çağrılan konsol programı Windows'ta yeni pencere açar; bu bayrak açtırmaz.
PENCERESIZ = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


# ---------------------------------------------------------------- zaman, yol

def simdi() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def gun_baslangici(gun, simdi: datetime.datetime | None = None) -> datetime.datetime:
    """'Son N gün' penceresinin başı, bilgisayarın yerel saatine göre TAKVİM günü: gun=1 -> bugün 00:00,
    gun=2 -> dün 00:00 ... Gün gece yarısında (yerel) döner; kayan 24 saat değildir. Tam sayı olmayan gün
    (ör. 0,5) kayan pencere olarak kalır: simdi - gun."""
    simdi = simdi or datetime.datetime.now().astimezone()
    if float(gun) != int(gun):
        return simdi - datetime.timedelta(days=gun)
    ilk = simdi.date() - datetime.timedelta(days=max(int(gun), 1) - 1)
    return datetime.datetime.combine(ilk, datetime.time.min, tzinfo=simdi.tzinfo)


DURUM_YEREL_ORTAM = "ORKESTRA_DURUM_YEREL"  # "1": worktree kendi durum kopyasını kullanır (test ve izolasyon)


def ana_agac_koku(d: str) -> str | None:
    """`d` bağlı (ek) bir git worktree'sinin kökü ise ana ağacın kökü, değilse None. Süreç başlatmaz: `d/.git` dosyasındaki
    `gitdir: <ortak>/worktrees/<ad>` satırından ortak `.git` dizinini, onun üst klasöründen ana ağacı bulur."""
    try:
        with open(os.path.join(d, ".git"), encoding="utf-8") as f:
            ilk = f.readline().strip()
    except OSError:
        return None  # .git yok ya da klasör: ana ağaç (ya da git dışı)
    if not ilk.startswith("gitdir:"):
        return None
    gitdir = os.path.normpath(os.path.join(d, ilk[len("gitdir:"):].strip()))
    ortak = os.path.dirname(os.path.dirname(gitdir))  # <ortak .git>/worktrees/<ad> -> <ortak .git>
    if os.path.basename(os.path.dirname(gitdir)) != "worktrees" or os.path.basename(ortak) != ".git":
        return None  # alt modül ya da çıplak depo: ana ağaç belirsiz
    return os.path.dirname(ortak)


def proje_dizini(cwd: str | None = None) -> str:
    """CLAUDE_PROJECT_DIR > cwd'den yukarı .claude/orkestra arayışı > cwd. Bulunan klasör bağlı bir git worktree'siyse
    (oturum worktree'si: durum kopyası git dışı olduğundan ayrışır) ve ana ağaçta durum klasörü varsa ana ağaç döner;
    hook, komut ve panel böylece tek durum kaynağını görür. `ORKESTRA_DURUM_YEREL=1` yerel kopyayı seçer (ADR-0032)."""
    baslangic = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()
    d = os.path.abspath(baslangic)
    while True:
        if os.path.isdir(os.path.join(d, ".claude", "orkestra")):
            if os.environ.get(DURUM_YEREL_ORTAM) != "1":
                ana = ana_agac_koku(d)
                if ana and os.path.isdir(os.path.join(ana, ".claude", "orkestra")):
                    return os.path.abspath(ana)
            return d
        ust = os.path.dirname(d)
        if ust == d:
            return os.path.abspath(baslangic)
        d = ust


ESKI_AD = "ruya"  # geriye uyum: perspektifin eski adı (durum klasörü, rapor öneki, süreç etiketi, ajan adı)


def perspektif_goc(p: str) -> None:
    """Eski <durum>/ruya klasörünü <durum>/perspektif'e taşır (yoksa). Taşıyamazsa kopyalar; eskiyi silmez.
    Eski ruya_*.md raporları adlarıyla kalır ve perspektif.py tarafından bulunur."""
    eski, yeni = os.path.join(p, ESKI_AD), os.path.join(p, "perspektif")
    if os.path.isdir(yeni) or not os.path.isdir(eski):
        return
    try:
        os.replace(eski, yeni)
    except OSError:
        try:
            shutil.copytree(eski, yeni)
        except Exception:
            return
    dj = os.path.join(yeni, "durum.json")
    try:
        with open(dj, encoding="utf-8") as f:
            d = json.load(f)
        if "son_ruya" in d:
            d["son_perspektif"] = d.pop("son_ruya")
        sr = d.get("son_rapor")
        if sr and not os.path.exists(sr):
            aday = os.path.join(yeni, os.path.basename(sr))
            if os.path.exists(aday):
                d["son_rapor"] = aday
        atomik_yaz(dj, json.dumps(d, ensure_ascii=False, indent=2))
    except Exception:
        pass


def durum_dizini(cwd: str | None = None, olustur: bool = False) -> str | None:
    p = os.path.join(proje_dizini(cwd), ".claude", "orkestra")
    if os.path.isdir(p):
        perspektif_goc(p)
        return p
    if olustur:
        for alt in ("gorevler", "oturumlar", "perspektif", "onerilen_skill", "raporlar"):
            os.makedirs(os.path.join(p, alt), exist_ok=True)
        return p
    return None


# ---------------------------------------------------------------- kilit ve yazım

@contextmanager
def kilit(yol: str, bekleme_s: float = 3.0):
    """Süreçler arası basit dosya kilidi (Windows msvcrt / POSIX fcntl). Beklemesi 3 sn: hook'u en çok bu kadar
    bloklar (önce 8 sn); süre dolarsa TimeoutError; kilit dosyasının yanındaki '.zaman_asimi.log'a bir satır yazılır."""
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
                        try:
                            with open(yol + ".zaman_asimi.log", "a", encoding="utf-8") as g:
                                g.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} kilit_zaman_asimi pid={os.getpid()}\n")
                        except OSError:
                            pass
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


# Kalıcı kayıtların (jsonl satırı, kart dosyası) biçim sürümü. Yeni kayıt "v" alanıyla yazılır; "v"si olmayan kayıt
# sürüm 0 (eski biçim) sayılır ve olduğu gibi okunur. Biçim değişirse bu sayı artar, eski kayıtlar dönüştürülmez.
KAYIT_SURUMU = 1


def kayit_surumu(kayit) -> int:
    """Kaydın biçim sürümü; alan yoksa ya da bozuksa 0 (eski biçim)."""
    try:
        return int(kayit.get("v", 0))
    except (AttributeError, TypeError, ValueError):
        return 0


def jsonl_ekle(yol: str, kayit: dict) -> None:
    sona_ekle(yol, json.dumps({"v": KAYIT_SURUMU, **kayit}, ensure_ascii=False) + "\n")


def jsonl_toplu_ekle(yol: str, kayitlar: list[dict]) -> None:
    """Çok satırı tek sona_ekle çağrısıyla ekler (tek kilit, tek açma); boş listede dosyaya dokunmaz."""
    if kayitlar:
        sona_ekle(yol, "".join(json.dumps({"v": KAYIT_SURUMU, **k}, ensure_ascii=False) + "\n" for k in kayitlar))


# ---------------------------------------------------------------- istek kimliği (I-030 P1)

def _oturum_json_yol(sd, oturum):
    return os.path.join(sd, "oturumlar", f"{oturum}.json")


def _oturum_json_oku(yol):
    """(durum, sözlük): 'yok' (dosya yok), 'ok', 'bozuk' (okunamaz ya da sözlük değil)."""
    if not os.path.exists(yol):
        return "yok", {}
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return "bozuk", {}
    return ("ok", d) if isinstance(d, dict) else ("bozuk", {})


def _sayi(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


def istek_id_yeni(sd, oturum):
    """Yeni kullanıcı isteği için '<oturum ilk 8>-<sıra 4 hane>' üretir; sıra oturum json'unda kilitli artar
    (istek_sira, son_istek_id; istek_tur sıfırlanır). Hata durumunda None (istisna fırlatmaz, dosya bozulmaz)."""
    try:
        if not sd or not oturum:
            return None
        yol = _oturum_json_yol(sd, oturum)
        with kilit(yol):
            durum, d = _oturum_json_oku(yol)
            if durum == "bozuk":
                return None
            sira = _sayi(d.get("istek_sira")) + 1
            kimlik = f"{str(oturum)[:8]}-{sira:04d}"
            d.update({"istek_sira": sira, "son_istek_id": kimlik, "istek_tur": 0})
            atomik_yaz(yol, json.dumps(d))
            return kimlik
    except Exception:
        return None


def istek_id_oku(sd, oturum):
    """Oturumun son istek_id'si; yoksa ya da hata varsa None."""
    try:
        if not sd or not oturum:
            return None
        durum, d = _oturum_json_oku(_oturum_json_yol(sd, oturum))
        v = d.get("son_istek_id") if durum == "ok" else None
        return str(v) if v else None
    except Exception:
        return None


def istek_kimlik_alanlari(sd, oturum, agent_id=None, tur_arttir=False) -> dict:
    """Kayıt satırına eklenecek {istek_id, span_id, ust_span_id}; kimlik yoksa {} (alan yazılmaz).
    Ana tur span'ı '<istek_id>.t<n>' (tur_arttir=True n'yi kilitli artırır, değilse geçerli n, en az 1);
    alt ajan span'ı '<istek_id>.a-<agent_id>'. ust_span_id her ikisinde istek_id."""
    try:
        iid = istek_id_oku(sd, oturum)
        if not iid:
            return {}
        if agent_id:
            span = f"{iid}.a-{agent_id}"
        else:
            n = 1
            yol = _oturum_json_yol(sd, oturum)
            if tur_arttir:
                with kilit(yol):
                    durum, d = _oturum_json_oku(yol)
                    if durum == "ok" and d.get("son_istek_id") == iid:
                        n = _sayi(d.get("istek_tur")) + 1
                        d["istek_tur"] = n
                        atomik_yaz(yol, json.dumps(d))
            else:
                durum, d = _oturum_json_oku(yol)
                n = max(1, _sayi(d.get("istek_tur"))) if durum == "ok" else 1
            span = f"{iid}.t{n}"
        return {"istek_id": iid, "span_id": span, "ust_span_id": iid}
    except Exception:
        return {}


# ---------------------------------------------------------------- iş atfı (I-030 P2)

def is_coz(sd, oturum, gorev=None, niyet_dahil=True):
    """Tek iş çözümü: (is_id_ya_da_None, atif_nedeni). Sıra: görev kartının is alanı, oturum json'u, niyet bağlamı.
    Hiçbiri yoksa (None, 'kart-isiz') (gerçek bir görev var ama iş yok) ya da (None, 'oturum-isiz');
    hata durumunda ('-', 'hata'); istisna fırlatmaz."""
    try:
        gorevli = bool(gorev) and gorev != "-"
        if gorevli:
            try:  # bozuk/okunamayan kart oturumun işine düşer (çökme ya da 'hata' değil)
                k = kart_oku(sd, gorev)
            except Exception:
                k = None
            v = k.get("is") if isinstance(k, dict) else None
            if v:
                return str(v), None
        if sd and oturum:
            durum, d = _oturum_json_oku(_oturum_json_yol(sd, oturum))
            v = d.get("is") if durum == "ok" else None
            if v:
                return str(v), None
        if niyet_dahil and oturum:
            try:
                import niyet
                b = str(niyet.son_baglam(oturum) or "").strip()
            except Exception:
                b = ""
            if re.fullmatch(r"I-\d+", b):
                return b, None
        return None, ("kart-isiz" if gorevli else "oturum-isiz")
    except Exception:
        return "-", "hata"


def is_alanlari(sd, oturum, gorev=None) -> dict:
    """Maliyet/zaman satırına yazılacak {'is': ..., ['atif_nedeni': ...]}; is_coz üzerinden. Bağsızda is None."""
    is_id, neden = is_coz(sd, oturum, gorev)
    if is_id and is_id != "-":
        return {"is": is_id}
    return {"is": None, "atif_nedeni": neden or "oturum-isiz"}


def atif_yaz(sd, oturum, is_id, kaynak) -> bool:
    """Oturum bir işe bağlandığında, o oturumun bağsız maliyet satırları için <sd>/atif.jsonl'e TEK ek olay yazar.
    Ham defter değişmez; aynı oturum+iş için tekrar yazılmaz; bağsız satır yoksa yazılmaz. Hata yutulur (False)."""
    try:
        if not (sd and oturum and is_id):
            return False
        bagsiz = [r for r in jsonl_oku(os.path.join(sd, "maliyet.jsonl"))
                  if r.get("oturum") == oturum and (not r.get("is") or r.get("is") == "-")]
        if not bagsiz:
            return False
        yol = os.path.join(sd, "atif.jsonl")
        with kilit(os.path.join(sd, "atif_kontrol")):  # jsonl_ekle yol'un kendi kilidini alır: ayrı kilit
            if any(e.get("oturum") == oturum and e.get("is") == is_id for e in jsonl_oku(yol)):
                return False
            jsonl_ekle(yol, {"tur": "atif", "zaman": simdi(), "oturum": oturum, "is": is_id, "kaynak": kaynak,
                             "satir_adedi": len(bagsiz), "ilk_zaman": bagsiz[0].get("zaman"),
                             "son_zaman": bagsiz[-1].get("zaman")})
        return True
    except Exception:
        return False


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
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
        for deneme in range(12):  # toplam bekleme ~1,3 sn: yük altında (AV/okuyucu) 0,2 sn yetmiyordu
            try:
                os.replace(gecici, yol)
                return
            except PermissionError:
                # Windows: hedef başka bir okuyucuda açıkken kısa süre reddedilebilir.
                if deneme == 11:
                    raise
                time.sleep(0.02 * (deneme + 1))
    finally:
        # başarısız yazım (disk dolu, izin, başka OSError) .tmp_* dosyası bırakmasın; başarıda dosya zaten taşındı
        if os.path.exists(gecici):
            try:
                os.remove(gecici)
            except OSError:
                pass


def tmp_temizle(dizin: str, yas_s: float = 3600.0) -> int:
    """Çöken yazımlardan kalan '.tmp_*' dosyalarını (yas_s'den eski) siler; silinen sayısını döner."""
    silinen = 0
    esik = time.time() - yas_s
    try:
        for ad in os.listdir(dizin):
            if not ad.startswith(".tmp_"):
                continue
            yol = os.path.join(dizin, ad)
            try:
                if os.path.isfile(yol) and os.path.getmtime(yol) < esik:
                    os.remove(yol)
                    silinen += 1
            except OSError:
                pass
    except OSError:
        pass
    return silinen


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

_FIYAT_ONBELLEK: dict = {}


def fiyat_tablosu() -> dict:
    """bin/fiyat.json; aynı süreçte dosya (yol, mtime_ns, boyut) değişmedikçe yeniden okunmaz (satır başına çağrılıyordu)."""
    yol = os.path.join(PLUGIN_ROOT, "bin", "fiyat.json")
    try:
        st = os.stat(yol)
        imza = (yol, st.st_mtime_ns, st.st_size)
    except OSError:
        imza = None
    if imza and _FIYAT_ONBELLEK.get("imza") == imza:
        return _FIYAT_ONBELLEK["tablo"]
    with open(yol, encoding="utf-8") as f:
        tablo = json.load(f)
    if imza:
        _FIYAT_ONBELLEK.update({"imza": imza, "tablo": tablo})
    return tablo


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
            ilk_kullanici, tur, arac_cagrisi, araclar:Counter-dict, dokunulan:[...] (yazılanlar), okunan:[...] (Read), ilk_zaman, son_zaman, ofset}
    """
    sonuc = {
        "modeller": {}, "toplam": {"giris": 0, "cikis": 0, "onbellek_okuma": 0, "onbellek_yazma": 0, "maliyet_usd": 0.0},
        "ilk_kullanici": None, "tur": 0, "arac_cagrisi": 0, "araclar": {}, "dokunulan": [], "okunan": [],
        "ilk_zaman": None, "son_zaman": None, "ofset": ofset,
        "arac_sayilari": {"arac_hata": 0, "tekrar_okuma": 0},
    }
    if not yol or not os.path.exists(yol):
        return sonuc
    hata_idleri: set[str] = set()
    okuma_sayac: dict[str, int] = {}
    son_kullanim: dict[str, tuple[str, dict]] = {}
    arac_idleri: set[str] = set()
    arac_izi: list[tuple] = []  # (tool_use_id, ad, mesaj_id, tool_use zamanı)
    sonuc_zamani: dict[str, str] = {}  # tool_use_id -> ilk tool_result zamanı
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
        if tip == "user" and isinstance(mesaj, dict) and isinstance(mesaj.get("content"), list):
            for b in mesaj["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    if b.get("is_error") is True:
                        hata_idleri.add(str(b.get("tool_use_id") or id(b)))
                    if b.get("tool_use_id") and ts:
                        sonuc_zamani.setdefault(b["tool_use_id"], ts)
        if tip != "assistant":
            continue
        mid = mesaj.get("id") or o.get("uuid")
        if mesaj.get("usage"):
            son_kullanim[mid] = (mesaj.get("model") or "bilinmiyor", mesaj["usage"])
        for b in mesaj.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") not in arac_idleri:
                arac_idleri.add(b.get("id"))
                ad = b.get("name", "?")
                arac_izi.append((b.get("id"), ad, mid, ts))
                sonuc["araclar"][ad] = sonuc["araclar"].get(ad, 0) + 1
                giris = b.get("input") or {}
                fp = giris.get("file_path") or giris.get("notebook_path")
                if ad in ("Write", "Edit", "MultiEdit", "NotebookEdit") and fp and fp not in sonuc["dokunulan"]:
                    sonuc["dokunulan"].append(fp)
                rp = giris.get("file_path")
                if ad == "Read" and rp and rp not in sonuc["okunan"]:
                    sonuc["okunan"].append(rp)
                if ad == "Read" and rp:
                    okuma_sayac[rp] = okuma_sayac.get(rp, 0) + 1
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
    sonuc["arac_sayilari"] = {"arac_hata": len(hata_idleri), "tekrar_okuma": sum(n - 1 for n in okuma_sayac.values() if n > 1)}
    sonuc["arac_izleri"] = arac_izleri_hesapla(arac_izi, sonuc_zamani, son_kullanim)
    return sonuc


_USAGE_ALANLARI = (("giris", "input_tokens"), ("cikis", "output_tokens"),
                   ("onbellek_okuma", "cache_read_input_tokens"), ("onbellek_yazma", "cache_creation_input_tokens"))


def _paylastir(toplam: int, n: int) -> list[int]:
    """toplam'ı n parçaya tamsayı olarak böler; kalan ilk parçalara 1'er dağıtılır (toplam korunur)."""
    q, r = divmod(max(0, toplam), n)
    return [q + (1 if i < r else 0) for i in range(n)]


def arac_izleri_hesapla(arac_izi, sonuc_zamani, son_kullanim) -> list[dict]:
    """Araç başına {tool_use_id, arac, sure_ms, giris, cikis, onbellek_okuma, onbellek_yazma} (I-030 P4).

    sure_ms: tool_use satırı zamanından ilk tool_result zamanına (sonuç yoksa ya da negatifse None).
    Token: aynı asistan mesajının (mesaj kimliği tekil) usage'ı o mesajdaki araç sayısına bölünür;
    toplam usage'a eşittir, yaklaşıktır (tahmin)."""
    mesaj_araclari: dict = {}
    for i, (_tid, _ad, mid, _ts) in enumerate(arac_izi):
        mesaj_araclari.setdefault(mid, []).append(i)
    paylar: dict[int, dict] = {}
    for mid, sira in mesaj_araclari.items():
        u = (son_kullanim.get(mid) or (None, {}))[1] or {}
        for alan, anahtar in _USAGE_ALANLARI:
            v = u.get(anahtar, 0)
            for i, p in zip(sira, _paylastir(v if isinstance(v, int) and not isinstance(v, bool) else 0, len(sira))):
                paylar.setdefault(i, {})[alan] = p
    izler = []
    for i, (tid, ad, _mid, ts) in enumerate(arac_izi):
        sure = sure_ms(ts, sonuc_zamani.get(tid)) if ts and tid in sonuc_zamani else None
        izler.append({"tool_use_id": tid, "arac": ad, "sure_ms": sure if sure is None or sure >= 0 else None,
                      **{alan: paylar.get(i, {}).get(alan, 0) for alan, _ in _USAGE_ALANLARI}})
    return izler


def ne_ozeti(metin: str | None, azami: int = 120) -> str:
    """İstek metninin kural tabanlı tek satırlık özeti (I-030 P5): satır sonları boşluğa çevrilir,
    ilk cümle (. ! ? ardından boşluk ya da son) alınır, en çok `azami` karakter. LLM çağrısı yok."""
    t = " ".join(str(metin or "").split())
    if not t:
        return ""
    m = re.match(r"(.+?[.!?…])(?=\s|$)", t)
    return (m.group(1) if m else t)[:azami].rstrip()


def etiketler(metin: str | None) -> tuple[str, str]:
    metin = metin or ""
    g = ETIKET_GOREV.search(metin)
    s = ETIKET_SUREC.search(metin)
    surec = s.group(1) if s and s.group(1) in SURECLER + (ESKI_AD,) else "bilinmiyor"
    if surec == ESKI_AD:  # eski #SUREC:ruya etiketi
        surec = "perspektif"
    return (g.group(1) if g else "-"), surec


# Ajan tipi → süreç: "bilinmiyor" yazılmasın diye tek kaynak (I-071; hook.py ve komutlar/maliyet.py bunu çağırır).
AJAN_SUREC = {
    "orkestra:triyaj": "triyaj", "orkestra:arsivci": "arsiv", "orkestra:skill-avcisi": "skill-avi",
    "orkestra:test-yazari": "test-yaz", "orkestra:hafiza-bakimcisi": "perspektif", "orkestra:perspektif-ajani": "perspektif",
    "orkestra:arastirmaci": "arastirma", "Explore": "arastirma", "Plan": "plan",
    "general-purpose": "genel-ajan", "claude": "genel-ajan", "claude-code-guide": "genel-ajan", "statusline-setup": "genel-ajan",
}


def surec_turet(ajan_tipi: str | None, surec: str = "bilinmiyor") -> str:
    """Etiketten gelen süreç varsa onu korur; yoksa ajan tipinden türetir. Eşlenmemiş tip `diger:<tip>`,
    tip hiç okunamadıysa `tip-okunamadi` yazar; "bilinmiyor" üretilmez."""
    if surec and surec != "bilinmiyor":
        return surec
    a = (ajan_tipi or "").strip()
    if not a or a == "?":
        return "tip-okunamadi"
    if a in AJAN_SUREC:
        return AJAN_SUREC[a]
    if "denetci" in a:
        return "denetim"
    if "isci" in a:
        return "is"
    if "perspektif" in a or "ruya" in a:
        return "perspektif"
    return "diger:" + re.sub(r"[^A-Za-z0-9:_.\-]", "", a)[:40]


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
    kart.setdefault("v", KAYIT_SURUMU)
    atomik_yaz(kart_yolu(sd, kart["id"]), json.dumps(kart, ensure_ascii=False, indent=2) + "\n")


_KART_ONBELLEK: dict = {}  # dosya yolu -> ((mtime_ns, boyut), ayrıştırılmış kart | None)


def kartlar(sd: str, derin: bool = True) -> list[dict]:
    """derin=False: yüzeysel kopya (hızlı); yalnız kartı DEĞİŞTİRMEYEN salt okur çağıranlar için."""
    d = os.path.join(sd, "gorevler")
    out = []
    if os.path.isdir(d):
        for ad in sorted(os.listdir(d)):
            if re.fullmatch(r"G-\d+\.json", ad):
                yol = os.path.join(d, ad)
                try:
                    st = os.stat(yol)
                    imza = (st.st_mtime_ns, st.st_size)
                except OSError:
                    continue
                kayit = _KART_ONBELLEK.get(yol)
                if kayit and kayit[0] == imza:
                    k = kayit[1]
                else:
                    try:
                        with open(yol, encoding="utf-8") as f:
                            k = json.load(f)
                    except Exception:
                        k = None
                    _KART_ONBELLEK[yol] = (imza, k)  # bozuk kart da imzayla önbelleğe girer (her çağrıda yeniden denenmez)
                if isinstance(k, dict) and k.get("id"):
                    k = copy.deepcopy(k) if derin else dict(k)  # tüketiciler kartı değiştirebilir; önbellek bozulmasın
                    # eksik alanlı kart özet/panel tüketicilerini çökertmesin
                    k.setdefault("baslik", "")
                    k.setdefault("basamak", "-")
                    out.append(k)
        takma = takma_haritasi(sd)
        if takma:
            for k in out:
                if k.get("is") in takma:
                    k["is"] = takma[k["is"]]
    return out


_TAKMA_ONBELLEK: dict = {}


def takma_imzasi(sd: str):
    """isler.json (mtime_ns, size); dosya yoksa None (takma ad haritası ve maliyet önbelleği imzası)."""
    try:
        st = os.stat(os.path.join(sd, "isler.json"))
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def takma_haritasi(sd: str) -> dict:
    """isler.json 'takma' alanı: {eski iş kimliği: yeni iş kimliği}. Kaybolan ya da birleştirilen işin kartları ve
    harcaması yeni kimlik altında görünür; ham kart ve defter dosyaları değişmez. Zincirler çözülür."""
    imza = takma_imzasi(sd)
    if imza is None:
        return {}
    onb = _TAKMA_ONBELLEK.get(sd)
    if onb and onb[0] == imza:
        return onb[1]
    try:
        with open(os.path.join(sd, "isler.json"), encoding="utf-8") as f:
            ham = (json.load(f) or {}).get("takma") or {}
    except Exception:
        ham = {}
    harita = {}
    for eski, yeni in ham.items():
        if not (isinstance(eski, str) and isinstance(yeni, str)):
            continue
        for _ in range(5):  # zincir (I-002 → I-021 → …); döngüye karşı sınırlı
            yeni = ham.get(yeni, yeni) if ham.get(yeni) != eski else yeni
        harita[eski] = yeni
    _TAKMA_ONBELLEK[sd] = (imza, harita)
    return harita


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


def kartsiz_satir_mi(satir: dict) -> bool:
    """Defter satırının görevi boş ya da '-' (karta bağlı olmayan harcama): ana ajan ve kartsız alt ajan ortak kümesi."""
    g = satir.get("gorev")
    return not g or g == "-"


def ana_ajan_satiri_mi(satir: dict) -> bool:
    """Ana ajan payının tek tanımı: kartsız satır VE ajan 'ana-ajan' (eski satırda ajan alanı yoksa da ana sayılır).
    Kartsız alt ajan (araştırmacı, general-purpose, perspektif, hafıza bakımcısı...) ana ajana yazılmaz;
    `kartsiz_alt_ajan_satiri_mi` ayrı kalemdir. KPI, hedef panosu, maliyet anomalisi (K6) ve etki ölçümü aynı tanımı kullanır."""
    return kartsiz_satir_mi(satir) and (satir.get("ajan") in (None, "", "ana-ajan"))


def kartsiz_alt_ajan_satiri_mi(satir: dict) -> bool:
    """Karta bağlı olmayan ama ana ajan olmayan (alt ajan) defter satırı."""
    return kartsiz_satir_mi(satir) and not ana_ajan_satiri_mi(satir)


def ana_ajan_dagilimi(satirlar: list[dict]) -> dict:
    """Kartsız harcamanın üç kalemi: ana ajan işe bağlı, ana ajan işsiz (sohbet), kartsız alt ajan.
    Her kalem {satir, usd}. Kart satırları (görevi dolu) dahil değildir."""
    d = {"ana_is_bagli": {"satir": 0, "usd": 0.0}, "ana_is_bagsiz": {"satir": 0, "usd": 0.0},
         "kartsiz_alt_ajan": {"satir": 0, "usd": 0.0}}
    for r in satirlar:
        if not kartsiz_satir_mi(r):
            continue
        if ana_ajan_satiri_mi(r):
            k = "ana_is_bagli" if (r.get("is") and r.get("is") != "-") else "ana_is_bagsiz"
        else:
            k = "kartsiz_alt_ajan"
        d[k]["satir"] += 1
        d[k]["usd"] += float(r.get("maliyet_usd") or 0)
    return d


def zaman_kayitlari(sd: str) -> list[dict]:
    """zaman.jsonl satırları. Alt ajan satırı her SubagentStop'ta yazılır ve süre transkriptin tamamını kapsar
    (devam ettirilen ajanda kümülatif); aynı (oturum, agent_id) için yalnız en büyük süreli satır kalır, yoksa
    süreler çifte toplanır. agent_id'siz ('?') satırlar olduğu gibi kalır."""
    out: list[dict] = []
    alt: dict = {}
    for r in jsonl_oku(os.path.join(sd, "zaman.jsonl")):
        if not isinstance(r, dict):
            continue
        aid = r.get("agent_id")
        if r.get("tur") != "alt" or not aid or aid == "?":
            out.append(r)
            continue
        anahtar = (r.get("oturum"), aid)
        if anahtar not in alt:
            alt[anahtar] = len(out)
            out.append(r)
        elif (r.get("sure_ms") or 0) > (out[alt[anahtar]].get("sure_ms") or 0):
            out[alt[anahtar]] = r
    return out


def satir_isi(satir: dict, kart_is: dict) -> str:
    """Defter satırının bağlı olduğu iş: satırın görevi bir karta bağlıysa kartın işi (kart hangi işteyse harcaması da
    oradadır); aksi halde satırın kendi `is` alanı; yoksa boş. is_rapor ve panel iş toplamları aynı kuralı kullanır."""
    g = satir.get("gorev")
    if g and kart_is.get(g):
        return kart_is[g]
    return satir.get("is") or ""


def ret_onay_say(kartlar: list[dict]) -> tuple[int, int]:
    """(ret, onay+ret) denetim karar sayısı; iptal kartlar sayılmaz. Ret oranının tek tanımı (KPI ile aynı)."""
    ret = karar = 0
    for k in kartlar:
        if k.get("durum") == "iptal":
            continue
        for d in k.get("denetimler") or []:
            kr = d.get("karar") if isinstance(d, dict) else None
            if kr in ("ret", "onay"):
                karar += 1
                ret += kr == "ret"
    return ret, karar


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
                          errors="replace", **PENCERESIZ)


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
    baglar = {str(b) for b in kart.get("bagimliliklar") or []}
    for k in kartlar(sd):
        durum = kart_durumu_hesapla(k)
        if k.get("id") == kart.get("id") or durum not in ACIK_DURUMLAR:
            continue
        if durum == "onaylandi" and k.get("id") in baglar:
            continue  # onaylı ama teslim edilmemiş BAĞIMLILIK: iş bitti, alanı engel değil (bağımlı olmayan onaylı kart engel kalır)
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


def test_koku_dogrula(yol) -> str:
    """Kartın isteğe bağlı test_koku alanı: var olan MUTLAK dizin → '/' ayraçlı mutlak yol. Aksi hâlde ValueError."""
    if not isinstance(yol, str) or not yol.strip():
        raise ValueError("test_koku boş olmayan bir mutlak dizin yolu olmalı")
    y = yol.strip()
    if not os.path.isabs(y):
        raise ValueError(f"test_koku mutlak yol olmalı (göreli verildi): {y}")
    if not os.path.isdir(y):
        raise ValueError(f"test_koku dizini yok: {y}")
    return os.path.abspath(y).replace("\\", "/")


def kart_test_koku(proje: str, kart: dict) -> str:
    """test_alani ve test kilidinin göreli olduğu PAYLAŞILAN kök: kartın test_koku'su, yoksa proje (ağaç karşılığı değil)."""
    return os.path.abspath((kart or {}).get("test_koku") or proje)


AGAC_KOKU_ORTAM = "ORKESTRA_AGAC_KOKU"
AGAC_GIZLI_KLASOR = ".claude/worktrees"
NL = chr(10)


def agac_yolu(depo: str, gid: str) -> tuple[str, bool]:
    """Kart çalışma ağacının yolu ve varsayılan (depo içi) düzende olup olmadığı.

    `ORKESTRA_AGAC_KOKU` doluysa `<kök>/<depo-adı>/kart-<id>`; değilse `<depo>/.claude/worktrees/kart-<id>`."""
    depo = os.path.abspath(depo).replace("\\", "/").rstrip("/")
    kok = (os.environ.get(AGAC_KOKU_ORTAM) or "").strip()
    if kok:
        return os.path.abspath(os.path.join(kok, os.path.basename(depo), f"kart-{gid}")).replace("\\", "/"), False
    return f"{depo}/{AGAC_GIZLI_KLASOR}/kart-{gid}", True


def _gizli_klasoru_dislat(depo: str) -> None:
    """`<depo>/.claude/worktrees` git'te zaten yok sayılmıyorsa `.git/info/exclude`a bir kez ekler (.gitignore'a dokunmaz)."""
    r = git(["check-ignore", "-q", "--no-index", AGAC_GIZLI_KLASOR + "/kart-x"], depo)
    if r.returncode == 0:
        return
    r = git(["rev-parse", "--git-common-dir"], depo)
    if r.returncode != 0 or not r.stdout.strip():
        return
    ortak = r.stdout.strip()
    if not os.path.isabs(ortak):
        ortak = os.path.join(depo, ortak)
    ex = os.path.join(ortak, "info", "exclude")
    mevcut = ""
    if os.path.exists(ex):
        with open(ex, encoding="utf-8", errors="replace") as f:
            mevcut = f.read()
    if any(s.strip().rstrip("/") == AGAC_GIZLI_KLASOR for s in mevcut.splitlines()):
        return
    os.makedirs(os.path.dirname(ex), exist_ok=True)
    with open(ex, "a", encoding="utf-8", newline=NL) as f:
        f.write(("" if not mevcut or mevcut.endswith(NL) else NL) + AGAC_GIZLI_KLASOR + "/" + NL)


def kart_agaci_ac(proje: str, kart: dict, taban: str = "HEAD") -> tuple[dict, list[str]]:
    """Kartın yazma alanının bulunduğu git deposunda `kart/<id>` dalıyla worktree açar (yol: `agac_yolu`).

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
    if kart.get("sinif") == "kod" and kart.get("test_alani") and not yol_altinda(kart_test_koku(proje, kart), depo):
        raise ValueError(f"{gid}: {AGAC_KOK_KAPSAMIYOR} (depo {depo}, test kökü {kart_test_koku(proje, kart)}); kod "
                         "kartının test_komutu ve test_alani test köküne (test_koku, yoksa proje) göredir, ağaçtaki "
                         "kodu sınayamaz. Kartı paylaşılan ağaçta yürüt, test_koku'yu depo içine al ya da depoyu "
                         "kapsayan bir projeden çalış.")
    yol, varsayilan = agac_yolu(depo, gid)
    dal = f"kart/{gid}"
    if os.path.exists(yol):
        raise ValueError(f"çalışma ağacı klasörü zaten var: {yol}")
    r = git(["rev-parse", "--verify", taban + "^{commit}"], depo)
    if r.returncode != 0:
        raise ValueError(f"taban okunamadı ({taban}): {(r.stderr or r.stdout).strip()}")
    taban_sha = r.stdout.strip()
    if varsayilan:
        _gizli_klasoru_dislat(depo)
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
    ağaç açmaz; bu dal o denetimden önce açılmış ağaçlar içindir.

    Kartta test_koku (proje dışı olabilen mutlak dizin) varsa proje yerine o kullanılır: ağaç yoksa test_koku'nun
    kendisi, ağaç varsa test_koku'nun ağaçtaki karşılığı; test_koku ağaç deposunun içinde değilse ValueError."""
    ca = (kart or {}).get("calisma_agaci") or {}
    tk = (kart or {}).get("test_koku")
    if tk:
        if not ca.get("yol"):
            return os.path.abspath(tk)
        if not (ca.get("depo") and yol_altinda(tk, ca["depo"])):
            raise ValueError(f"test_koku kart ağacının deposunda değil (test_koku {tk}, depo {ca.get('depo') or '-'}, "
                             f"ağaç {ca['yol']}); ağaçta karşılığı yok, test-kos ağaçtaki kodu sınayamaz. Ağacı "
                             f"`orkestra kart birlestir {(kart or {}).get('id', '<id>')}` ile paylaşılan ağaca al ya da "
                             "test_koku'yu `orkestra kart test-ayar` ile düzelt.")
        r = os.path.relpath(os.path.abspath(tk), os.path.abspath(ca["depo"]))
        return os.path.abspath(ca["yol"] if r == "." else os.path.join(ca["yol"], r))
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
        r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, **PENCERESIZ)
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
    birleşimi) paylaşılan mutlak yola çevrilir (kilitler kendi kartlarının test köküne göredir). Teslim/iptal dışındaki herhangi bir kartın (kartın kendisi dahil)
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
            tkok = kart_test_koku(proje, k)  # kilit yolları kartın test köküne (test_koku, yoksa proje) göredir
            for y, h in d.items():
                kilitler.setdefault(_goreli_anahtar(os.path.abspath(os.path.join(tkok, y))), []).append(
                    (y.replace("\\", "/"), k.get("id", "?"), h))
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
        sahipler = kilitler.get(_goreli_anahtar(os.path.abspath(tam)))
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


def agac_kaldir(depo: str, yol: str, dal: str | None) -> list[str]:
    """Çalışma ağacını `--force` OLMADAN kaldırır, sonra (ağaç gittiyse) dalı `branch -d` ile siler.

    Dönen: uyarı metinleri. Boşsa ağaç kalktı (dal birleşmemişse korunur, bu da uyarıdır). Kirli ağaç kalır ve
    uyarı döner; ağaç kalktıysa `os.path.exists(yol)` yanlış olur."""
    uyari = []
    if yol and os.path.isdir(yol):
        r = git(["worktree", "remove", yol], depo)
        if r.returncode != 0:
            return [f"çalışma ağacı kaldırılamadı, kayıt korundu ({yol}): {(r.stderr or r.stdout).strip()}"]
    else:
        git(["worktree", "prune"], depo)
    if dal:
        r = git(["branch", "-d", dal], depo)
        if r.returncode != 0:
            uyari.append(f"{dal} dalı silinmedi (birleşmemiş iş olabilir): {(r.stderr or r.stdout).strip()}")
    return uyari


def _agac_kayitlari(depo: str) -> list[dict]:
    """`git worktree list --porcelain` → [{yol, dal, prunable}] (ana ağaç hariç)."""
    r = git(["worktree", "list", "--porcelain"], depo)
    if r.returncode != 0:
        return []
    out, cur = [], None
    for s in r.stdout.splitlines() + [""]:
        if s.startswith("worktree "):
            cur = {"yol": s[9:].strip().replace("\\", "/"), "dal": None, "prunable": False}
        elif s.startswith("branch ") and cur:
            cur["dal"] = s[7:].strip().replace("refs/heads/", "", 1)
        elif s.startswith("prunable") and cur:
            cur["prunable"] = True
        elif not s.strip() and cur:
            out.append(cur)
            cur = None
    return [x for x in out[1:]]


def agac_temizle_siniflandir(depo: str, ks: list[dict]) -> dict:
    """Deponun worktree'lerini sınıflar: aday (kartı teslim/iptal ya da kartsız kart ağacı), acik (kart açık),
    oturum (Claude'un oturum başına açtığı `claude/<ad>-<hex>` ağacı; orkestra kaldırmaz, devralınmamış kayıt sayısını
    `devralinmamis` ile bildirir), kalip_disi (kart düzenine uymayan). Her öğe {yol, dal, kart, neden}."""
    depo_n = os.path.abspath(depo).replace("\\", "/").rstrip("/")
    kartlar_ = {k.get("id"): k for k in ks}
    kok = (os.environ.get(AGAC_KOKU_ORTAM) or "").strip()
    ebeveynler = {_kiyas(f"{depo_n}/{AGAC_GIZLI_KLASOR}")}
    if kok:
        ebeveynler.add(_kiyas(os.path.abspath(os.path.join(kok, os.path.basename(depo_n)))))
    eski = re.compile(re.escape(_kiyas(depo_n)) + r"-kart-(.+)$")
    sonuc = {"aday": [], "acik": [], "kalip_disi": []}
    for w in _agac_kayitlari(depo):
        y = w["yol"]
        ad = y.rstrip("/").rsplit("/", 1)[-1]
        ust = _kiyas(os.path.dirname(y.rstrip("/")))
        gid = None
        if ust in ebeveynler and ad.startswith("kart-"):
            gid = ad[5:]
        else:
            m = eski.match(_kiyas(y))
            if m:
                gid = y[len(y) - len(m.group(1)):]
        if not gid:
            sonuc["kalip_disi"].append({**w, "kart": None, "neden": "kart düzenine uymuyor"})
            continue
        k = kartlar_.get(gid)
        if k is None:
            sonuc["aday"].append({**w, "kart": gid, "neden": "kartı yok"})
        elif kart_durumu_hesapla(k) in ("teslim", "iptal"):
            sonuc["aday"].append({**w, "kart": gid, "neden": f"kart {kart_durumu_hesapla(k)}"})
        else:
            sonuc["acik"].append({**w, "kart": gid, "neden": "kart açık"})
    return sonuc


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


def python_yorumlayici() -> str:
    """Kapının kendi Python çağrıları için yorumlayıcı yolu (tek seçim noktası; cfg: ORKESTRA_PYTHON > makine config'i > `py -3.13` > sys.executable)."""
    return cfg.al("python") or sys.executable


def kabuk_kos(komut: str, cwd: str, zaman_asimi: float) -> tuple[int, str, float]:
    """Komutu kabukla çalıştırır → (çıkış kodu, birleşik stdout+stderr, süre sn).

    Zaman aşımında süreç ağacı öldürülür ve çıkış kodu -1 döner."""
    import subprocess
    bas = time.monotonic()
    ek = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    env = dict(os.environ)
    env.setdefault("ORKESTRA_PYTHON", python_yorumlayici())  # test komutunun alt süreçleri aynı yorumlayıcıyı görsün
    p = subprocess.Popen(komut, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, env=env, **ek)
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


# ---------------------------------------------------------------- test komutu daraltma

_DEGER_ALAN_SECENEKLER = {"-p", "-k", "-m", "-n", "-c", "-o", "-W", "--maxfail", "--tb", "--rootdir", "--ignore", "--deselect",
                          "--durations", "--basetemp", "--junitxml", "--zaman-asimi", "--en-yavas", "--confcutdir"}
_TOKEN_RE = re.compile(r'"[^"]*"|\'[^\']*\'|\S+')


def test_komutu_daralt(komut: str, proje: str, desenler: list[str]) -> tuple[str | None, str | None]:
    """Geniş pytest / test_paralel.py komutunu kartın test_alani'ndaki mevcut test dosyalarına daraltır.

    → (komut, not). Geniş = konumsal yol yok (cwd'nin tamamı) ya da bir konumsal yol klasör. Zaten dosya/düğüm
    verilmişse, pytest/test_paralel dışı bir koşucuysa (ör. unittest discover) ya da ORKESTRA_TEST_DARALT=0 ise
    komut aynen döner (not None). test_alani'na uyan test dosyası (test_*.py / *_test.py) yoksa (None, not): koşulacak
    test yok, tam paket koşturulmaz. Tam paket iş sonunda bir kez ayrıca koşar."""
    if os.environ.get("ORKESTRA_TEST_DARALT", "").strip() == "0":
        return komut, None
    ham = _TOKEN_RE.findall(komut or "")
    jt = [t.strip("\"'") for t in ham]
    kos = next((i for i, t in enumerate(jt) if t == "pytest" or os.path.basename(t.replace("\\", "/")) in ("test_paralel.py", "pytest.exe")), None)
    if kos is None:
        return komut, None
    konumsal, atla = [], False
    for i in range(kos + 1, len(jt)):
        if atla:
            atla = False
        elif jt[i].startswith("-"):
            atla = jt[i] in _DEGER_ALAN_SECENEKLER
        else:
            konumsal.append(i)
    kok = os.path.abspath(proje)
    if konumsal and not any(os.path.isdir(os.path.join(kok, jt[i].split("::")[0])) for i in konumsal):
        return komut, None  # zaten dosya düzeyinde
    dosyalar = [y for y in sorted(test_dosyasi_ozetleri(proje, desenler))
                if re.search(r"(?:^|/)(?:test_[^/]*|[^/]*_test)\.py$", y)]
    if not dosyalar:
        return None, "test_alani'na uyan test dosyası yok; koşulacak test yok"
    cikar = set(konumsal)
    yeni = [t for i, t in enumerate(ham) if i not in cikar]
    ekle = [f'"{d}"' if " " in d else d for d in dosyalar]
    yer = konumsal[0] - sum(1 for c in cikar if c < konumsal[0]) if konumsal else len(yeni)
    yeni[yer:yer] = ekle
    return " ".join(yeni), f"geniş test komutu {len(dosyalar)} test dosyasına daraltıldı"


# ---------------------------------------------------------------- test çıktısı ayrıştırma (test kapısı + ön kontrol)

# `FAILED/ERROR <kimlik>` ve subTest düşüşü `SUBFAILED(i=1) <kimlik>` / `SUBFAIL <kimlik>` (parantezli parametre atlanır)
PYTEST_DUSEN_RE = re.compile(r"^(?:SUBFAILED|SUBFAIL|FAILED|ERROR)(?:\(.*?\)(?=\s))?[ \t]+(\S+)", re.M)
UNITTEST_DUSEN_RE = re.compile(r"^(?:FAIL|ERROR):\s+(\S+)\s+\(([\w.]+)\)", re.M)
_PYTEST_OZET_RE = re.compile(r"\b\d+ (?:passed|failed|errors?|skipped|deselected|xfailed|xpassed)\b|\bno tests ran\b")
_UNITTEST_OZET_RE = re.compile(r"^Ran \d+ tests? in ", re.M)
# Yalnız satır başına bağlı pytest toplama kalıpları (assert/traceback içindeki aynı metin sayılmaz):
# `!!! Interrupted: N error during collection !!!`, `___ ERROR collecting <yol> ___`, `ERROR <yol>[ - ...]` (:: yok).
_TOPLAMA_RE = re.compile(r"^!+ Interrupted: .*during collection|^_+ ERROR collecting |^ERROR (?![^\n]*::)\S+(?: - [^\n]*)?$",
                         re.M)
# Son pytest özet satırı (`=== 2 failed, 1 error, 10 passed in 0.20s ===` ya da -q ile çerçevesiz)
_PYTEST_SONUC_RE = re.compile(r"^=*\s*(\d+ [\w ]+?(?:, \d+ [\w ]+?)*) in [\d.]+s\b", re.M)


def pytest_dusenler(cikti: str) -> list[str]:
    """pytest kısa özetindeki `FAILED/ERROR <kimlik>` satırlarından kimlikler (sıralı, tekil)."""
    return sorted(set(PYTEST_DUSEN_RE.findall(cikti or "")))


def pytest_dusus_satirlari(cikti: str) -> list[str]:
    """pytest kısa özetindeki test düşüş satırlarının kimlikleri, satır sırasıyla ve TEKİLLEŞTİRİLMEDEN.

    Bir test birden çok satırla düşebilir (subTest döngüsü: aynı kimlikte N `SUBFAILED(...)`; `FAILED` + teardown
    `ERROR`); pytest özetindeki failed + error sayısı bu satırlarla birebir tutar. Sayılmaz: toplama hatası satırı
    (`ERROR <yol>`, kimlikte :: yok; toplama ayrıca reddedilir) ve unittest özeti `FAILED (failures=1)`."""
    out = []
    for m in PYTEST_DUSEN_RE.finditer(cikti or ""):
        kimlik = m.group(1)
        if kimlik.startswith("(") or (m.group(0).startswith("ERROR") and "::" not in kimlik):
            continue
        out.append(kimlik)
    return out


def _unittest_kimligi(ad: str, nokta: str) -> str:
    """unittest başlığı `test_x (mod.Sinif.test_x)` (3.11+) ya da `test_x (mod.Sinif)` → `mod.Sinif.test_x`."""
    return nokta if nokta.rsplit(".", 1)[-1] == ad else f"{nokta}.{ad}"


def test_ciktisi_ayristir(cikti: str, cikis: int) -> dict:
    """Test komutu çıktısı → {"ayristirildi", "bicim", "dusenler": [kimlik], "toplama_hatasi", "toplama_nedeni"}.

    pytest: `FAILED/ERROR <yol::...>`, subTest `SUBFAILED(...) <yol::...>`; unittest: `FAIL:/ERROR: test
    (mod.Sinif[.test])` → `mod.Sinif.test`. Toplama/kullanım hatası: satır başında `Interrupted: ... during
    collection`, `ERROR collecting`, `ERROR <yol>` (:: yok) ya da ayrıştırılan çıktıda çıkış kodu 0/1 dışı (pytest ≥2,
    unittest 5, zaman aşımı -1). `ozet_dusen`: son pytest özet satırındaki failed + error toplamı (yoksa None).
    `dusus_satiri`: ayrıştırılan düşüş SATIRI sayısı, tekilleştirilmemiş (pytest_dusus_satirlari + unittest
    `FAIL:/ERROR:` satırları); gizli düşüş kıyası `ozet_dusen` ile bununla yapılır, tekil kimlik sayısıyla değil.
    Çıktı pytest/unittest değilse ayristirildi False."""
    metin = cikti or ""
    pyt = [x for x in pytest_dusenler(metin) if not x.startswith("(")]  # unittest özeti `FAILED (failures=1)` kimlik değil
    ut_satir = [_unittest_kimligi(ad, nokta) for ad, nokta in UNITTEST_DUSEN_RE.findall(metin)]
    ut = set(ut_satir)
    toplama = bool(_TOPLAMA_RE.search(metin))
    pytest_mi = bool(pyt or toplama or _PYTEST_OZET_RE.search(metin))
    unittest_mi = bool(ut or _UNITTEST_OZET_RE.search(metin))
    ayristirildi = pytest_mi or unittest_mi
    neden = None
    if toplama:
        neden = "toplama hatası (testler toplanamadı)"
    elif ayristirildi and cikis not in (0, 1):
        neden = "zaman aşımı" if cikis == -1 else f"toplama/kullanım hatası (çıkış {cikis})"
    ozet_dusen = None
    sonuclar = _PYTEST_SONUC_RE.findall(metin)
    if sonuclar:
        sayilar = dict((ad.strip(), int(n)) for n, ad in re.findall(r"(\d+) ([\w ]+?)(?:,|$)", sonuclar[-1]))
        ozet_dusen = sayilar.get("failed", 0) + sayilar.get("error", 0) + sayilar.get("errors", 0)
    return {"ayristirildi": ayristirildi, "bicim": "pytest" if pytest_mi else ("unittest" if unittest_mi else None),
            "dusenler": sorted(set(pyt) | ut), "toplama_hatasi": neden is not None, "toplama_nedeni": neden,
            "ozet_dusen": ozet_dusen, "dusus_satiri": len(pytest_dusus_satirlari(metin)) + len(ut_satir)}


def test_kimligi_dosyalari(kimlik: str) -> list[str]:
    """Test kimliğinden olası dosya yolları ('/' ayraçlı), en olası önce.

    pytest `yol/test_a.py::Sinif::test` → [yol/test_a.py]; unittest `paket.test_a.Sinif.test` →
    [paket/test_a.py, paket/test_a/Sinif.py, paket.py] (sınıf+yöntem atılmış hâli önce)."""
    k = (kimlik or "").strip()
    if "::" in k or "/" in k or "\\" in k or k.endswith(".py"):
        yol = k.split("::", 1)[0].replace("\\", "/")
        while yol.startswith("./"):
            yol = yol[2:]
        return [yol] if yol else []
    parca = [p for p in k.split(".") if p]
    out = []
    for atilan in (2, 1, 3):
        if len(parca) > atilan:
            aday = "/".join(parca[:len(parca) - atilan]) + ".py"
            if aday not in out:
                out.append(aday)
    return out


def _alan_eslesir(rel: str, desenler: list[str]) -> bool:
    """Göreli yol ('/') test_alani desenlerinden birine uyuyor mu (glob; `**` ve klasör öneki dahil)."""
    r = _kiyas(rel)
    for d in desenler or []:
        t = (d or "").replace("\\", "/").strip()
        while t.startswith("./"):
            t = t[2:]
        t = _kiyas(t) if t else ""
        if t and (r == t or fnmatch.fnmatchcase(r, t) or r.startswith(t + "/") or fnmatch.fnmatchcase(r, t + "/**")):
            return True
    return False


def test_alaninda_mi(kimlik: str, kok: str, desenler: list[str], kosu_koku: str | None = None) -> bool:
    """Test kimliğinin dosyası, `kok`'e göreli test_alani desenlerinden birine uyuyor mu.

    Kimlikteki göreli yol koşunun çalıştığı köke (`kosu_koku`, verilmezse `kok`) göredir: o yol `kok` altındaysa
    `kok`'e göre göreliye çevrilip, değilse (ör. başka kartın ağacında koşu) göreli hâliyle denenir."""
    kosu = os.path.abspath(kosu_koku or kok)
    for aday in test_kimligi_dosyalari(kimlik):
        tam = aday if os.path.isabs(aday) else os.path.join(kosu, aday)
        rel = aday
        if yol_altinda(tam, kok):
            try:
                rel = os.path.relpath(os.path.abspath(tam), os.path.abspath(kok)).replace("\\", "/")
            except ValueError:
                pass
        if _alan_eslesir(rel, desenler):
            return True
    if _unittest_kimligi_mi(kimlik):
        # unittest modül adı test klasörüne göreli olabilir (`unittest discover -s tests` → `test_x.T.test`):
        # test_alani'ndaki gerçek dosyalardan biri adayla bitiyorsa o dosyadır.
        adaylar = ["/" + _kiyas(a) for a in test_kimligi_dosyalari(kimlik)]
        for d in test_alani_dosyalari(kok, desenler):
            dd = "/" + _kiyas(d)
            if any(dd.endswith(a) for a in adaylar):
                return True
    return False


def _unittest_kimligi_mi(kimlik: str) -> bool:
    k = (kimlik or "").strip()
    return bool(k) and not ("::" in k or "/" in k or "\\" in k or k.endswith(".py"))


def test_alani_dosyalari(kok: str, desenler: list[str]) -> list[str]:
    """test_alani desenlerine (köke göre glob, `**` özyinelemeli) uyan kök içi dosyalar → göreli yollar ('/').
    Özet hesaplamaz (test_dosyasi_ozetleri'nin hafif eşi); __pycache__ ve .pyc hariç."""
    kok = os.path.abspath(kok)
    out = []
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
                continue
            if rel == ".." or rel.startswith("../") or "__pycache__" in rel.split("/") or rel.endswith(".pyc"):
                continue
            if rel not in out:
                out.append(rel)
    return out


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
    if not kayit.get("oturum"):  # CLI/perspektif yolu: yazan oturumun kimliği ortamdan (alt ajanda üst oturum)
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
            f.write(json.dumps({"v": KAYIT_SURUMU, **kayit}, ensure_ascii=False) + "\n")


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
    yol = os.path.join(sd, "maliyet.jsonl")
    try:
        st = os.stat(yol)
        imza = (yol, st.st_mtime_ns, st.st_size, _duzeltme_imzasi(sd), takma_imzasi(sd))  # düzeltme ve takma ad dosyaları da imzada
    except OSError:
        imza = None
    if imza and _MALIYET_ONBELLEK.get("imza") == imza:
        return [dict(r) for r in _MALIYET_ONBELLEK["out"]]  # aynı süreçte dosya değişmediyse yeniden okuma (hook'ta 3-4 kez çağrılır)
    out = _maliyet_kayitlari_oku(yol)
    takma = takma_haritasi(sd)
    if takma:
        for r in out:
            if r.get("is") in takma:
                r["is"] = takma[r["is"]]
    if imza:
        _MALIYET_ONBELLEK.update({"imza": imza, "out": out})
    return [dict(r) for r in out]


_MALIYET_ONBELLEK: dict = {}


def _duzeltme_imzasi(sd: str):
    """maliyet_duzeltme.jsonl (mtime_ns, size); dosya yoksa None."""
    try:
        st = os.stat(os.path.join(sd, "maliyet_duzeltme.jsonl"))
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _duzeltme_uygula(yol: str, out: list[dict]) -> list[dict]:
    """Ham defter yanındaki maliyet_duzeltme.jsonl'i bindirir (yalnız bellekte): işsiz satırın işini anahtardan
    doldurur (dolu işe dokunmaz); doldurulamayan işsiz satıra atif_nedeni='oturum-isiz' ekler (yoksa)."""
    harita: dict = {}
    for e in jsonl_oku(os.path.join(os.path.dirname(yol), "maliyet_duzeltme.jsonl")):
        if e.get("anahtar") and e.get("is") and e["anahtar"] not in harita:
            harita[e["anahtar"]] = e
    for r in out:
        if r.get("is") and r.get("is") != "-":
            continue
        e = harita.get("|".join(str(r.get(a)) for a in ("oturum", "zaman", "agent_id", "kaynak", "model")))
        if e:
            r["is"] = e["is"]
            r["atif_kaynagi"] = e.get("kaynak")
            r.pop("atif_nedeni", None)
        else:
            r.setdefault("atif_nedeni", "oturum-isiz")
    return out


_TOKEN_ALANLARI = ("giris", "cikis", "onbellek_okuma", "onbellek_yazma")


def _satir_usd(r: dict) -> float:
    """Defter satırının token sayılarından maliyet; önbellek yazma 1 sa tarifesiyle (hook satırlarıyla aynı)."""
    return kullanim_maliyeti(r.get("model") or "", {
        "input_tokens": r.get("giris") or 0, "output_tokens": r.get("cikis") or 0,
        "cache_read_input_tokens": r.get("onbellek_okuma") or 0,
        "cache_creation": {"ephemeral_1h_input_tokens": r.get("onbellek_yazma") or 0}})


def kalem_usd(r: dict) -> dict:
    """Defter satırının dört kalemlik USD kırılımı (giris, cikis, onbellek_okuma, onbellek_yazma).

    İlk üç kalem token x liste fiyatı. Önbellek yazma 'kalan'dır: satırın maliyet_usd'si eksi ilk üç kalem; böylece
    hook satırlarındaki gerçek 5 dk/1 sa karışımı kaybolmaz ve kalem toplamı defter toplamına birebir eşit kalır
    (negatif olamaz). maliyet_usd yoksa yazma 1 sa tarifesiyle fiyatlanır."""
    f = model_fiyati(r.get("model") or "")
    usd = {a: (r.get(a) or 0) * f[fiyat] / 1_000_000
           for a, fiyat in (("giris", "giris"), ("cikis", "cikis"), ("onbellek_okuma", "onbellek_okuma"))}
    if r.get("maliyet_usd") is not None:
        usd["onbellek_yazma"] = max(0.0, float(r["maliyet_usd"]) - sum(usd.values()))
    else:
        usd["onbellek_yazma"] = (r.get("onbellek_yazma") or 0) * f["onbellek_yazma_1sa"] / 1_000_000
    return usd


def kalemler(satirlar: list[dict]) -> dict:
    """Satır listesinin token ve USD toplamı, dört kalemle ve 'toplam'la: {'token': {...}, 'usd': {...}}.
    Kıyas katmanları (analitik, kpi, rapor, panel) bu tek tanımı kullanır."""
    token = {a: 0 for a in _TOKEN_ALANLARI}
    usd = {a: 0.0 for a in _TOKEN_ALANLARI}
    for r in satirlar:
        k = kalem_usd(r)
        for a in _TOKEN_ALANLARI:
            token[a] += int(r.get(a) or 0)
            usd[a] += k[a]
    token["toplam"] = sum(token[a] for a in _TOKEN_ALANLARI)
    usd = {a: round(v, 6) for a, v in usd.items()}
    usd["toplam"] = round(sum(usd[a] for a in _TOKEN_ALANLARI), 6)
    return {"token": token, "usd": usd}


# ---------------------------------------------------------------- panel pencereleri (tek takvim günü tanımı, I-137)

PENCERELER = ("bugun", "son_3_gun", "son_7_gun", "bu_ay", "tum_zaman")


def yerel_zaman(s) -> "datetime.datetime | None":
    """ISO zaman damgasını yerel saat dilimine çevirir; çözülemezse None (damgasız değer yerel kabul edilir)."""
    if not s:
        return None
    try:
        z = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return (z if z.tzinfo else z.astimezone()).astimezone()
    except Exception:
        return None


def pencere_icinde(pencere: str, gun: "datetime.date", bugun: "datetime.date") -> bool:
    """Panelin tek pencere tanımı: bugün dahil takvim günü (son_3_gun = bugün ve önceki 2 gün). Bütün panel alanları bunu kullanır."""
    if pencere == "bugun":
        return gun == bugun
    if pencere == "son_3_gun":
        return bugun - datetime.timedelta(days=2) <= gun <= bugun
    if pencere == "son_7_gun":
        return bugun - datetime.timedelta(days=6) <= gun <= bugun
    if pencere == "bu_ay":
        return (gun.year, gun.month) == (bugun.year, bugun.month)
    return True


def pencere_gun_sayisi(pencere: str, bugun: "datetime.date") -> "int | None":
    """Pencerenin takvim günü sayısı (bugüne kadar); tum_zaman için None."""
    return {"bugun": 1, "son_3_gun": 3, "son_7_gun": 7, "bu_ay": bugun.day}.get(pencere)


def onceki_aralik(pencere: str, bugun: "datetime.date") -> "tuple | None":
    """Aynı uzunluktaki önceki dönemin (ilk gün, son gün) aralığı; bu_ay için önceki ayın aynı gün sayısı. tum_zaman için None."""
    n = pencere_gun_sayisi(pencere, bugun)
    if n is None:
        return None
    if pencere == "bu_ay":
        gecen_ay_sonu = bugun.replace(day=1) - datetime.timedelta(days=1)
        return gecen_ay_sonu.replace(day=1), gecen_ay_sonu.replace(day=min(n, gecen_ay_sonu.day))
    bit = bugun - datetime.timedelta(days=n)
    return bit - datetime.timedelta(days=n - 1), bit


def _satir_tok(r: dict) -> int:
    return sum(int(r.get(a) or 0) for a in _TOKEN_ALANLARI)


def pencere_toplamlari(satirlar, bugun: "datetime.date", anahtar=None) -> dict:
    """Defter satırlarının pencere başına {usd, token} toplamı. anahtar verilirse {anahtar(satır): {pencere: {...}}}
    (anahtar None dönerse satır atlanır); verilmezse {pencere: {...}}. Tüm paneldeki pencereli maliyet bu işlevden gelir."""
    cikti: dict = {}
    for r in satirlar:
        k = anahtar(r) if anahtar else ""
        if k is None:
            continue
        z = yerel_zaman(r.get("zaman"))
        usd = r.get("maliyet_usd") or 0.0
        tok = _satir_tok(r)
        t = cikti.setdefault(k, {w: [0.0, 0] for w in PENCERELER})
        for w in PENCERELER:
            if w == "tum_zaman" or (z and pencere_icinde(w, z.date(), bugun)):
                t[w][0] += usd
                t[w][1] += tok
    son = {k: {w: {"usd": round(v[0], 4), "token": v[1]} for w, v in t.items()} for k, t in cikti.items()}
    return son if anahtar else son.get("", {w: {"usd": 0.0, "token": 0} for w in PENCERELER})


def _maliyet_kayitlari_oku(yol: str, duzeltme: bool = True) -> list[dict]:
    rows = jsonl_oku(yol)
    for r in rows:  # eski 'tur' satırları (tarife damgası yok) 5 dk tarifesiyle yazılmıştı: 1 sa tarifesiyle yeniden fiyatla
        if (r.get("kaynak") == "tur" and not r.get("tarife") and r.get("model")
                and any(r.get(a) for a in _TOKEN_ALANLARI)):
            r["maliyet_usd"] = _satir_usd(r)
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
    out.extend(_hook_artigi(rows, tur_var))
    return _duzeltme_uygula(yol, out) if duzeltme else out


def _hook_artigi(rows: list[dict], tur_var: set) -> list[dict]:
    """'tur' kaydı olan gruplarda hook'un gördüğü ama tur satırlarının kapsamadığı token (tur kaydı başlamadan önceki
    turlar). Ana ajan hook satırları artımlıdır (toplanır); alt ajanda birikimlidir (en son satır). Artık = hook - tur,
    bileşen başına en az 0; sıfırdan büyükse 'hook-artik' satırı olarak eklenir. Netleme MODEL başına yapılır: karışık
    modelli grupta bir modelin fazlası ötekinin eksiğini kapatıp fiyat farkını yutmasın."""
    sonuc = []
    hook_grup: dict = {}  # satırlar bir kez gruplanır; grup başına yeniden taramak satır sayısıyla ikinci derece yavaşlar
    tur_grup: dict = {}
    for r in rows:
        k = (r.get("oturum"), r.get("agent_id"))
        if k in tur_var:
            (tur_grup if r.get("kaynak") == "tur" else hook_grup).setdefault(k, []).append(r)
    for k in tur_var:
        hook = hook_grup.get(k)
        if not hook:
            continue
        tur = tur_grup.get(k, [])
        if k[1]:
            hook = [max(hook, key=lambda r: (r.get("zaman") or "", r.get("maliyet_usd") or 0))]
        for model in sorted({r.get("model") or "" for r in hook}):
            h = [r for r in hook if (r.get("model") or "") == model]
            t = [r for r in tur if (r.get("model") or "") == model]
            art = {a: max(0, sum(r.get(a) or 0 for r in h) - sum(r.get(a) or 0 for r in t)) for a in _TOKEN_ALANLARI}
            if not any(art.values()):
                continue
            son = max(h, key=lambda r: r.get("zaman") or "")
            satir = {a: son.get(a) for a in ("zaman", "oturum", "gorev", "surec", "ajan", "agent_id", "model")}
            satir.update(art)
            satir["kaynak"] = "hook-artik"
            satir["maliyet_usd"] = _satir_usd(satir)
            sonuc.append(satir)
    return sonuc


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
        if not yol or re.search(r"[\\/]AppData[\\/]Local[\\/]Temp[\\/]|[\\/]ork_(?:tmp|canli)|[\\/]\.claude[\\/]worktrees[\\/]", yol, re.I):
            continue  # geçici, test ve worktree kopyaları gerçek çalışma alanı değildir
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
    """claude.exe: cfg (CLAUDE_CODE_EXECPATH > makine config'i > %APPDATA%/%LOCALAPPDATA% altındaki en yeni > PATH)."""
    return cfg.al("claude_exe")


def pazar_kaynagi(pazar: str = "claude-orchestration") -> str | None:
    """known_marketplaces.json'daki installLocation (kaynak depo klasörü)."""
    return cfg.pazar_kaynagi(pazar)


def _klon_kaynagi(kok: str) -> str | None:
    """`kok` bir git klonuysa ve origin'i yerel bir klasörse o klasör (yayın klonu → geliştirme deposu); değilse None."""
    try:
        with open(os.path.join(kok, ".git", "config"), encoding="utf-8", errors="replace") as f:
            m = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', f.read())
    except OSError:
        return None
    url = m.group(1) if m else ""
    return url if url and os.path.isdir(url) else None


def kopyada_mi(yol: str) -> str | None:
    """`yol`, eklentinin kopyasında mı? Kopyaya yazılan değişiklik bir sonraki eşitleme/güncellemede silinir.
    Kopya: Claude Code'un yönettiği ~/.claude/plugins/marketplaces ve cache altı, ya da origin'i yerel bir klasör olan
    yayın klonu (known_marketplaces installLocation). Dönüş: değişikliğin yapılacağı yer (bilinmiyorsa "kaynak depo"); kopya değilse None.
    ORKESTRA_KOPYA_YAZMA=1 kapıyı kapatır."""
    if os.environ.get("ORKESTRA_KOPYA_YAZMA") == "1":
        return None
    yonetilen = os.path.join(os.path.expanduser("~"), ".claude", "plugins")
    for alt in ("marketplaces", "cache"):
        if yol_altinda(yol, os.path.join(yonetilen, alt)):
            return "kaynak depo"
    kok = pazar_kaynagi()
    if kok and yol_altinda(yol, kok):
        return _klon_kaynagi(kok)
    return None


def kaynaga_cevir(yol: str) -> str:
    """Eklenti kopyasındaki (yayın klonu) bir yolu kaynak depodaki karşılığına çevirir; kopya değilse aynen döner.
    Eklentiye yazılacak ya da oturuma gösterilecek yollar kaynağı göstersin diye (kopyaya yazılan iş eşitlemede silinirdi)."""
    if os.environ.get("ORKESTRA_KOPYA_YAZMA") == "1":
        return yol
    kok = pazar_kaynagi()
    if kok and yol_altinda(yol, kok):
        kaynak = _klon_kaynagi(kok)
        if kaynak:
            return os.path.normpath(os.path.join(kaynak, os.path.relpath(os.path.abspath(yol), os.path.abspath(kok))))
    return yol


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
                           capture_output=True, text=True, timeout=1.0, **PENCERESIZ)
        if r.returncode == 0:
            commitsiz = bool(r.stdout.strip())
    except Exception:
        pass
    return {"farkli": fark, "kaynakta_commitsiz": commitsiz, "kaynak": kaynak_depo}


_RET_TR = str.maketrans({"ı": "i", "İ": "i", "I": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
                         "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})
_RET_ONEK = r"(?:k|kriter\s*)"
_RET_GRUP = re.compile(
    rf"(?<![a-z0-9_]){_RET_ONEK}\s*\d+(?:\s*-\s*(?:k\s*)?\d+)?(?:\s*[,/]\s*(?:k\s*)?\d+(?:\s*-\s*(?:k\s*)?\d+)?)*"
    r"[\s:;\-—–]*\(?(karsilanmadi|karsilandi|kanitsiz|kismen)\b")
_RET_KIMLIK = re.compile(r"(\d+)(?:\s*-\s*(?:k\s*)?(\d+))?")


def ret_kriterleri(gerekce) -> list[str]:
    """Gerekçeden KARŞILANMADI/KANITSIZ/KISMEN işaretli kriter kimliklerini ('K2', ...) sıralı, tekil döndürür.
    KARŞILANDI olanlar girmez. Ayrıştırılamazsa [] (istisna fırlatmaz). Saf fonksiyon."""
    try:
        if not isinstance(gerekce, str) or not gerekce:
            return []
        metin = gerekce.translate(_RET_TR).lower()
        sayilar: set[int] = set()
        for m in _RET_GRUP.finditer(metin):
            if m.group(1) == "karsilandi":
                continue
            govde = m.group(0)[:m.start(1) - m.start(0)]
            govde = re.sub(r"^(?:kriter|k)\s*", "", govde)
            for e in _RET_KIMLIK.finditer(govde):
                bas = int(e.group(1))
                son = int(e.group(2)) if e.group(2) else bas
                if son < bas or son - bas > 50:
                    son = bas
                sayilar.update(range(bas, son + 1))
        return [f"K{n}" for n in sorted(sayilar)]
    except Exception:
        return []
