"""Tek main için kapanışta birleştirme ve artık dal/worktree temizliği (I-201 ADR-0050; I-225 ADR-0086).

Mod her zaman ayardadır; bu belgede yazılmaz (eskir): `ayarlar/dal_temizle.json` artık dal temizliğini,
`ayarlar/kapanis_birlestirme.json` oturum dalının kapanışta birleştirilmesini ve biten worktree'lerin kaldırılmasını yönetir.
Proje ezmesi: durum klasöründe aynı adlı dosya. Modlar için bkz. kapi_mod.py.

Artık dal: `main`'e tamamen birleşmiş, hiçbir worktree'de açık olmayan ve çağıran oturumun olmayan yerel dal.
Yedek: her silme ve kaldırma önce `git bundle create` + `bundle verify`; yedek başarısızsa hiçbir şey silinmez.
`main`'e birleşmemiş dala hiçbir modda dokunulmaz. Hiçbir çağrı istisna fırlatmaz.
Kapatma: ORKESTRA_DAL_TEMIZLE=0 (artık dal), ORKESTRA_KAPANIS_BIRLESTIRME=0 (birleştirme ve worktree kaldırma).
"""
from __future__ import annotations

import os
import subprocess
import time

import cfg
import kapi_mod
import ork_lib as L

ANA = "main"


def _git(depo: str, *a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", depo, *a], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, **cfg.PENCERESIZ)


def _worktree_dallari(depo: str) -> tuple[str, set[str]]:
    """(ana worktree yolu, worktree'lerde açık dal adları)."""
    r = _git(depo, "worktree", "list", "--porcelain")
    ana, dallar = "", set()
    for blok in r.stdout.split("\n\n"):
        yol = dal = ""
        for satir in blok.splitlines():
            if satir.startswith("worktree "):
                yol = satir[9:]
            elif satir.startswith("branch refs/heads/"):
                dal = satir[18:]
        if yol and not ana:
            ana = yol
        if dal:
            dallar.add(dal)
    return ana, dallar


def adaylar(depo: str, oturum_dali: str = "") -> dict:
    """{'aday': [...], 'birlesmemis': [...]}: worktree'de açık olmayan, oturum dalı ve main dışındaki yerel dallar."""
    _, acik = _worktree_dallari(depo)
    r = _git(depo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    aday, birlesmemis = [], []
    for dal in r.stdout.split():
        if dal in (ANA, oturum_dali) or dal in acik:
            continue
        ata = _git(depo, "merge-base", "--is-ancestor", dal, ANA).returncode == 0
        (aday if ata else birlesmemis).append(dal)
    return {"aday": aday, "birlesmemis": birlesmemis}


def _yedekle(depo: str, ana_yol: str, dallar: list[str]) -> str:
    """Dalları tek bundle'a alır ve doğrular; yol döner, başarısızsa ''."""
    klasor = os.path.join(ana_yol, "_arsiv", os.path.basename(os.path.normpath(ana_yol)))
    os.makedirs(klasor, exist_ok=True)
    yol = os.path.join(klasor, "dal_yedek_" + time.strftime("%Y%m%d_%H%M%S") + ".bundle")
    refs = ["refs/heads/" + d for d in dallar]
    if _git(depo, "bundle", "create", yol, *refs).returncode != 0:
        return ""
    return yol if _git(depo, "bundle", "verify", yol).returncode == 0 else ""


def temizle(depo: str, oturum_dali: str = "", kip: str = "golge") -> dict:
    """Adayları bulur; kip `ihlal` ise yedekleyip siler. {'kip','aday','silinen','birlesmemis','bundle','hata'}."""
    s = {"kip": kip, "aday": [], "silinen": [], "birlesmemis": [], "bundle": "", "hata": ""}
    try:
        a = adaylar(depo, oturum_dali)
        s["aday"], s["birlesmemis"] = a["aday"], a["birlesmemis"]
        if kip != "ihlal" or not s["aday"]:
            return s
        ana_yol, _ = _worktree_dallari(depo)
        s["bundle"] = _yedekle(depo, ana_yol or depo, s["aday"])
        if not s["bundle"]:
            s["hata"] = "bundle alınamadı; silinmedi"
            return s
        for dal in s["aday"]:
            if _git(depo, "branch", "-d", dal).returncode == 0:
                s["silinen"].append(dal)
    except Exception as e:  # hook'u ve kapanışı asla düşürme
        s["hata"] = str(e)[:200]
    return s


# ---------------------------------------------------------------- I-225: kapanışta birleştirme ve worktree kaldırma

KAPI = "kapanis_birlestirme"
ATIL_SAAT_VARSAYILAN = 24


def _ayar(cwd: str, anahtar: str, varsayilan):
    """`ayarlar/kapanis_birlestirme.json` değeri; proje ezmesi (durum klasörü) önceliklidir."""
    import json
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yollar = [os.path.join(kok, "ayarlar", KAPI + ".json")]
    sd = L.durum_dizini(cwd)
    if sd:
        yollar.append(os.path.join(sd, KAPI + ".json"))
    sonuc = varsayilan
    for yol in yollar:
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and anahtar in d:
                sonuc = d[anahtar]
        except (OSError, ValueError):
            pass
    return sonuc


def _yol(p: str) -> str:
    return os.path.normcase(os.path.normpath(p))


def _kirli(yol: str) -> list[str] | None:
    """Commit'siz (izlenen, izlenmeyen) dosya yolları; git hata verirse None (güvenli tarafta kal)."""
    r = _git(yol, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if r.returncode != 0:
        return None
    alanlar = r.stdout.split("\0")
    yollar, i = [], 0
    while i < len(alanlar):
        a = alanlar[i]
        i += 1
        if len(a) < 4:
            continue
        yollar.append(a[3:])
        if a[0] in "RC":  # yeniden adlandırma/kopya: sıradaki alan eski yoldur
            if i < len(alanlar) and alanlar[i]:
                yollar.append(alanlar[i])
            i += 1
    return yollar


def _dal_dosyalari(depo: str, dal: str) -> list[str]:
    """`main`'den ayrıldığı yerden beri dalın değiştirdiği dosyalar (yeniden adlandırmada eski ve yeni yol)."""
    r = _git(depo, "diff", "--name-status", "-z", "-M", f"{ANA}...{dal}")
    alanlar = [x for x in r.stdout.split("\0")]
    yollar, i = [], 0
    while i < len(alanlar):
        durum = alanlar[i]
        i += 1
        if not durum:
            continue
        n = 2 if durum[0] in "RC" else 1
        yollar.extend(x for x in alanlar[i:i + n] if x)
        i += n
    return yollar


def _ortusme(ana_kirli: list[str], dal_dosyalari: list[str]) -> list[str]:
    """Ana worktree'nin commit'siz yolları ile dalın yolları: büyük/küçük harf duyarsız, dosya-klasör çakışması dahil."""
    a = {_yol(x): x for x in ana_kirli}
    ortusen = set()
    for d in dal_dosyalari:
        dn = _yol(d)
        for an, ao in a.items():
            if an == dn or an.startswith(dn + os.sep) or dn.startswith(an + os.sep):
                ortusen.add(ao)
    return sorted(ortusen)


def _yarim_islem(ana_yol: str) -> str:
    """Ana worktree'de yarım kalmış birleştirme/cherry-pick/rebase/revert varsa adı, yoksa ''."""
    for ad in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD", "rebase-merge", "rebase-apply"):
        r = _git(ana_yol, "rev-parse", "--git-path", ad)
        yol = r.stdout.strip()
        if r.returncode == 0 and yol:
            if not os.path.isabs(yol):
                yol = os.path.join(ana_yol, yol)
            if os.path.exists(yol):
                return ad
    return ""


def _kuru_birlestirme(depo: str, dal: str) -> tuple[str, list[str], str]:
    """`git merge-tree --write-tree` (çalışma ağacına dokunmaz): ('temiz'|'catisma'|'hata', çakışan dosyalar, hata)."""
    r = _git(depo, "merge-tree", "--write-tree", "--name-only", ANA, dal)
    if r.returncode == 0:
        return "temiz", [], ""
    if r.returncode == 1:
        dosyalar = []
        for x in r.stdout.splitlines()[1:]:
            if not x.strip():
                break
            dosyalar.append(x.strip())
        return "catisma", dosyalar, ""
    return "hata", [], (r.stderr or r.stdout).strip()[:200]


def _onkosul(cwd: str, ana_yol: str, dal: str) -> tuple[str, list[str], str]:
    """Birleştirme önkoşulları. ('' = hepsi sağlandı, aksi halde sonuç adı, ilgili dosyalar, hata)."""
    kendi = _kirli(cwd)
    if kendi is None or kendi:
        return "dal-kirli", kendi or [], ""
    ana_dal = _git(ana_yol, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if ana_dal != ANA:
        return "ana-dal-degil", [], f"ana worktree '{ana_dal or 'detached'}' dalında"
    durum, dosyalar, hata = _kuru_birlestirme(ana_yol, dal)
    if durum == "catisma":
        return "catisma", dosyalar, ""
    if durum == "hata":
        return "merge-tree-hata", [], hata
    ana_kirli = _kirli(ana_yol)
    if ana_kirli is None:
        return "ana-durum-hata", [], "ana worktree durumu okunamadı"
    ortusen = sorted(set(ana_kirli) & set(_dal_dosyalari(ana_yol, dal)))
    if ortusen:
        return "ortusme", ortusen, ""
    return "", [], ""


def kapanis_birlestir(cwd: str, kip: str = "golge", is_id: str = "") -> dict | None:
    """Oturum dalını güvenli koşulda ana worktree'deki `main`'e `--no-ff` ile birleştirir (ADR-0086).

    Gölge kipte kuru koşu yapılır ve sonuç yazılır; çalışma ağacı değişmez. Önkoşul sağlanmazsa hiçbir şey birleştirilmez
    ve neden `sonuc` alanına yazılır. Dönen: {'kip','is','dal','uc','sonuc','dosyalar','hata'}; yapacak dal yoksa None."""
    if os.environ.get("ORKESTRA_KAPANIS_BIRLESTIRME") == "0":
        return None
    s = {"kip": kip, "is": is_id, "dal": "", "uc": "", "sonuc": "", "dosyalar": [], "hata": ""}
    try:
        dal = _git(cwd, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
        ana_yol, _ = _worktree_dallari(cwd)
        if not dal or dal == ANA or not ana_yol:
            return None
        s["dal"] = dal
        s["uc"] = _git(cwd, "rev-parse", dal).stdout.strip()
        if _git(cwd, "merge-base", "--is-ancestor", dal, ANA).returncode == 0:
            s["sonuc"] = "zaten-birlesmis"
            return s
        sonuc, dosyalar, hata = _onkosul(cwd, ana_yol, dal)
        s["dosyalar"], s["hata"] = dosyalar[:50], hata
        if sonuc:
            s["sonuc"] = sonuc
        elif kip != "ihlal":
            s["sonuc"] = "birlestirirdi"
        else:
            # önkoşul sınaması ile birleştirme arasında başka oturum yazmış olabilir: hemen öncesinde bir kez daha
            sonuc, dosyalar, hata = _onkosul(cwd, ana_yol, dal)
            if sonuc:
                s["sonuc"], s["dosyalar"], s["hata"] = sonuc, dosyalar[:50], hata
            else:
                mesaj = f"Birleştir: {dal}" + (f" ({is_id} kapanışı)" if is_id else "")
                r = _git(ana_yol, "merge", "--no-ff", "--no-edit", "-m", mesaj, dal)
                if r.returncode != 0:
                    _git(ana_yol, "merge", "--abort")
                    s["sonuc"], s["hata"] = "hata", (r.stderr or r.stdout).strip()[:200]
                elif _git(ana_yol, "merge-base", "--is-ancestor", dal, ANA).returncode == 0:
                    s["sonuc"] = "birlesti"
                else:
                    s["sonuc"], s["hata"] = "hata", "birleştirme sonrası dal main'in atası değil"
    except Exception as e:  # kapanışı asla düşürme
        s["sonuc"], s["hata"] = s["sonuc"] or "hata", str(e)[:200]
    try:
        ana_yol, _ = _worktree_dallari(cwd)
        sd = L.durum_dizini(cwd) or (L.durum_dizini(ana_yol) if ana_yol else None)
        if sd:
            L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "tur": "kapanis_birlestirme", **s})
    except Exception:
        pass
    return s


def _agaclar(depo: str) -> list[dict]:
    """Ana worktree dışındaki worktree'ler: [{'yol','dal','kilitli','prunable'}]."""
    r = _git(depo, "worktree", "list", "--porcelain")
    out = []
    for i, blok in enumerate(r.stdout.split("\n\n")):
        d = {"yol": "", "dal": "", "kilitli": False, "prunable": False}
        for satir in blok.splitlines():
            if satir.startswith("worktree "):
                d["yol"] = satir[9:]
            elif satir.startswith("branch refs/heads/"):
                d["dal"] = satir[18:]
            elif satir.startswith("locked"):
                d["kilitli"] = True
            elif satir.startswith("prunable"):
                d["prunable"] = True
        if d["yol"] and i > 0:
            out.append(d)
    return out


def _son_etkinlik(yol: str, dal_commit: float, sinir: int = 20000) -> float:
    """Worktree'deki en yeni dosya değişikliği ile dalın son commit zamanının büyüğü (epoch sn)."""
    en = dal_commit
    sayac = 0
    for kok, klasorler, dosyalar in os.walk(yol):
        klasorler[:] = [k for k in klasorler if k != ".git"]
        for ad in dosyalar:
            try:
                en = max(en, os.path.getmtime(os.path.join(kok, ad)))
            except OSError:
                pass
            sayac += 1
            if sayac >= sinir:
                return time.time()  # çok büyük ağaç: emin olamadık, kullanımda say
    return en


def _acik_is_klasorleri(durum_klasorleri: list[str]) -> list[str]:
    """Verilen durum klasörlerindeki isler.json'dan kapanmamış işlerin klasörleri."""
    import json
    out = []
    for sd in durum_klasorleri:
        try:
            with open(os.path.join(sd, "isler.json"), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        for it in (d.get("isler") or {}).values() if isinstance(d, dict) else []:
            if isinstance(it, dict) and it.get("durum") not in ("kapandi", "iptal") and it.get("klasor"):
                out.append(_yol(it["klasor"]))
    return out


def agaclar_temizle(cwd: str, oturum_dali: str = "", kip: str = "golge", simdi: float | None = None) -> dict:
    """`main`'e birleşmiş, temiz, kilitsiz, açık iş kaydı olmayan ve atıl (varsayılan 24 saat) worktree'leri kaldırır.

    Kullanımda olmama sinyalleri: kilit yok, worktree'de açık iş yok (kayıt), son etkinlik eşikten eski (ikincil emniyet).
    İhlal kipinde önce dallar `git bundle` ile yedeklenir; yedek yoksa hiçbir şey kaldırılmaz. Kirli worktree'ye dokunulmaz.
    Dönen: {'kip','aday','atlanan','kaldirilan','bundle','hata'}."""
    s = {"kip": kip, "aday": [], "atlanan": [], "kaldirilan": [], "bundle": "", "hata": ""}
    try:
        simdi = time.time() if simdi is None else simdi
        esik = float(_ayar(cwd, "atil_saat", ATIL_SAAT_VARSAYILAN)) * 3600
        ana_yol, _ = _worktree_dallari(cwd)
        kendi = _yol(_git(cwd, "rev-parse", "--show-toplevel").stdout.strip() or cwd)
        acik = _acik_is_klasorleri([d for d in (L.durum_dizini(ana_yol), L.durum_dizini(cwd)) if d])
        for ag in _agaclar(cwd):
            yol, dal = ag["yol"], ag["dal"]
            if _yol(yol) == kendi or (dal and dal == oturum_dali):
                continue
            neden = ""
            if not dal or dal == ANA:
                neden = "dal-yok-ya-da-main"
            elif ag["kilitli"]:
                neden = "kilitli"
            elif ag["prunable"] or not os.path.isdir(yol):
                neden = "klasor-yok"
            elif _git(cwd, "merge-base", "--is-ancestor", dal, ANA).returncode != 0:
                neden = "birlesmemis"
            elif _kirli(yol) is None or _kirli(yol):
                neden = "kirli"
            elif any(k == _yol(yol) or k.startswith(_yol(yol) + os.sep) for k in acik):
                neden = "acik-is"
            else:
                ct = _git(cwd, "log", "-1", "--format=%ct", dal).stdout.strip()
                if simdi - _son_etkinlik(yol, float(ct) if ct.isdigit() else 0.0) < esik:
                    neden = "guncel"
            if neden:
                s["atlanan"].append({"yol": yol, "neden": neden})
            else:
                s["aday"].append({"yol": yol, "dal": dal})
        if kip != "ihlal" or not s["aday"]:
            return s
        s["bundle"] = _yedekle(cwd, ana_yol or cwd, [a["dal"] for a in s["aday"]])
        if not s["bundle"]:
            s["hata"] = "bundle alınamadı; kaldırılmadı"
            return s
        for a in s["aday"]:
            uyari = L.agac_kaldir(cwd, a["yol"], a["dal"])
            if uyari:
                s["hata"] = (s["hata"] + "; " if s["hata"] else "") + uyari[0][:160]
            if not os.path.isdir(a["yol"]):
                s["kaldirilan"].append(a["yol"])
    except Exception as e:
        s["hata"] = str(e)[:200]
    return s


def _agaclari_calistir(cwd: str, oturum_dali: str, kaynak: str) -> None:
    """Biten worktree'leri kip ayardan okunarak kaldırır (ADR-0086); sonuç günlüğe `worktree_temizle` olarak yazılır."""
    if os.environ.get("ORKESTRA_KAPANIS_BIRLESTIRME") == "0":
        return
    try:
        s = agaclar_temizle(cwd, oturum_dali, kapi_mod.mod(KAPI, cwd))
        if s["aday"] or s["hata"]:
            sd = L.durum_dizini(cwd)
            if sd:
                L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "tur": "worktree_temizle", "kaynak": kaynak, **s})
    except Exception:
        pass


def calistir(cwd: str, oturum_dali: str = "", kaynak: str = "") -> dict | None:
    """Artık dalları (`dal_temizle` kipi) ve biten worktree'leri (`kapanis_birlestirme` kipi) temizler, sonuçları günlüğe yazar.
    Dönen artık dal sonucudur; kapalıysa ya da yapacak bir şey yoksa None."""
    sonuc = None
    try:
        if not oturum_dali:
            oturum_dali = _git(cwd, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
        if os.environ.get("ORKESTRA_DAL_TEMIZLE") != "0":
            sonuc = temizle(cwd, oturum_dali, kapi_mod.mod("dal_temizle", cwd))
            if sonuc["aday"] or sonuc["hata"]:
                sd = L.durum_dizini(cwd)
                if sd:
                    L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "tur": "dal_temizle", "kaynak": kaynak, **sonuc})
        _agaclari_calistir(cwd, oturum_dali, kaynak)
    except Exception:
        pass
    return sonuc


def kapanis(cwd: str, is_id: str = "") -> str:
    """`orkestra is kapat` sonrası: oturum dalını güvenli koşulda `main`'e birleştirir (kipe göre), artık dalları ve biten
    worktree'leri temizler; oturum dalı hâlâ `main`'e birleşmemişse uyarı metni döndürür.
    Oturum dalının kendisi çalışan worktree'de açık olduğundan burada silinemez; worktree atıl kalınca sonraki SessionStart kaldırır."""
    try:
        b = kapanis_birlestir(cwd, kapi_mod.mod(KAPI, cwd), is_id)
        calistir(cwd, kaynak="is_kapat")
        dal = _git(cwd, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
        if dal and dal != ANA and _git(cwd, "merge-base", "--is-ancestor", dal, ANA).returncode != 0:
            neden = ""
            if b and b["sonuc"] not in ("", "birlestirirdi"):
                neden = f" ({b['sonuc']}" + (f": {', '.join(b['dosyalar'][:5])}" if b["dosyalar"] else "") + ")"
            return f"oturum dalı '{dal}' main'e birleşmemiş{neden}; birleştirmeden dal temizlenmez (git merge --no-ff {dal} main'de)."
    except Exception:
        pass
    return ""
