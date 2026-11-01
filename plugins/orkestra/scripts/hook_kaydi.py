"""Hook çalışma kaydı (I-309): hangi oturumda hangi hook çalıştı, bitti mi, ne kadar sürdü, zaman aşımına uğradı mı.

Sorun: Claude Code zaman aşımında hook sürecini öldürür; süreç kendini kaydedemez, iz kalmaz.
Çözüm: başlarken `hook_acik/<pid>-<ns>.json` işareti (kilitsiz, tek küçük dosya), biterken işaret silinir ve
`gunluk.jsonl`'a `tur=hook_calisma` yazılır. Silinmemiş eski işaret = öldürülmüş hook; sonraki hook ya da
`orkestra oturum hook` onu `tur=hook_zaman_asimi` olarak kaydeder (sürecin canlı olmadığı doğrulanır).
Sıcak yol: hızlı ve başarılı PreToolUse için günlük satırı yazılmaz (yalnız işaret yazılıp silinir).
Ölçüm dönemi için ORKESTRA_HOOK_ORNEK=N hızlı başarılı PreToolUse'un 1/N'ini `ornek: true` ile yazar (varsayılan kapalı; I-328 P5).
Hatada sessiz; hook çıktısı değişmez. ORKESTRA_HOOK_KAYDI=0 kapatır.
"""
from __future__ import annotations

import json
import os
import random
import time

import ork_lib as L

ACIK = "hook_acik"
VARSAYILAN_ZA_S = 10
ZA_S = {"SubagentStop": 30, "Stop": 30}  # hooks.json ile aynı tutulur (testle doğrulanır)
YAVAS_MS = 1000       # PreToolUse bunun üstündeyse satır yazılır
SAYAC_PAYI_S = 3      # işaret yaşı zaman aşımı + pay'ı aşarsa yetim sayılır


def etkin() -> bool:
    return os.environ.get("ORKESTRA_HOOK_KAYDI") != "0"


def basla(sd: str | None, olay: str, oturum, arac=None, agent=None) -> str | None:
    if not sd or not etkin():
        return None
    try:
        d = os.path.join(sd, ACIK)
        os.makedirs(d, exist_ok=True)
        yol = os.path.join(d, f"{os.getpid()}-{time.time_ns()}.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"zaman": L.simdi(), "t": time.time(), "pid": os.getpid(), "olay": olay, "oturum": oturum,
                       "arac": arac, "agent": agent}, f)
        return yol
    except Exception:
        return None


def _ornekle(rng=random.random) -> bool:
    """ORKESTRA_HOOK_ORNEK=N (N>1) ise çağrıların 1/N'i True; kapalı/hatalı değerde False."""
    try:
        n = int(os.environ.get("ORKESTRA_HOOK_ORNEK", "0"))
    except ValueError:
        return False
    return n > 1 and rng() < 1.0 / n


def bitir(sd: str | None, yol: str | None, olay: str, oturum, arac, sonuc: str, ms: float) -> None:
    """sonuc: ok | cikis_<kod> | hata. İşareti siler; günlük satırı yazar (hızlı başarılı PreToolUse hariç)."""
    if not yol:
        return
    try:
        os.remove(yol)
    except OSError:
        pass
    try:
        ornek = False
        if olay == "PreToolUse" and sonuc == "ok" and ms < YAVAS_MS:
            if not _ornekle():
                return
            ornek = True
        kayit = {"zaman": L.simdi(), "oturum": oturum, "tur": "hook_calisma", "olay": olay, "arac": arac,
                 "sonuc": sonuc, "sure_ms": round(ms)}
        if ornek:
            kayit["ornek"] = True
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), kayit)
    except Exception:
        pass


def _canli(pid) -> bool:
    try:
        pid = int(pid)
        if os.name == "nt":
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False


def yetim_tara(sd: str | None, simdi: float | None = None) -> int:
    """Öldürülmüş hook işaretlerini zaman aşımı olarak kaydeder ve siler; kaydedilen sayısını döner."""
    if not sd or not etkin():
        return 0
    d = os.path.join(sd, ACIK)
    n = 0
    try:
        adlar = os.listdir(d)
    except OSError:
        return 0
    simdi = simdi if simdi is not None else time.time()
    for ad in adlar:
        yol = os.path.join(d, ad)
        try:
            with open(yol, encoding="utf-8") as f:
                k = json.load(f)
        except (OSError, ValueError):
            try:  # yarım yazılmış işaret: yaşlıysa temizle
                if simdi - os.path.getmtime(yol) > 60:
                    os.remove(yol)
            except OSError:
                pass
            continue
        sinir = ZA_S.get(k.get("olay"), VARSAYILAN_ZA_S) + SAYAC_PAYI_S
        yas = simdi - float(k.get("t") or 0)
        if yas <= sinir or (_canli(k.get("pid")) and yas <= 600):
            continue
        try:
            os.remove(yol)  # silebilen sahiplenir (iki tarayıcı aynı işareti çift yazmasın)
        except OSError:
            continue
        try:
            L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"),
                         {"zaman": L.simdi(), "oturum": k.get("oturum"), "tur": "hook_zaman_asimi",
                          "olay": k.get("olay"), "arac": k.get("arac"), "basladi": k.get("zaman"),
                          "sinir_s": ZA_S.get(k.get("olay"), VARSAYILAN_ZA_S)})
            n += 1
        except Exception:
            pass
    return n


def rapor(sd: str, gun: int = 7, oturum: str | None = None) -> dict:
    """Oturum x olay özeti: çalışma, yavaş, hata, zaman aşımı sayıları ve en uzun süre."""
    yetim_tara(sd)
    esik = time.time() - gun * 86400
    ozet: dict = {}
    skiller: dict = {}
    acilan: set = set()
    gorulen: set = set()
    yol = os.path.join(sd, "gunluk.jsonl")
    try:
        with open(yol, encoding="utf-8") as f:
            for s in f:
                if '"hook_' not in s and '"skill' not in s and '"oturum_yukleme"' not in s:
                    continue
                try:
                    k = json.loads(s)
                except ValueError:
                    continue
                if k.get("tur") not in ("hook_calisma", "hook_zaman_asimi", "skill", "skill_hata", "oturum_yukleme"):
                    continue
                if oturum and not str(k.get("oturum") or "").startswith(oturum):
                    continue
                if k.get("zaman") and _epoch(k["zaman"]) < esik:
                    continue
                ok = str(k.get("oturum") or "-")[:8]
                if k["tur"] == "oturum_yukleme":
                    acilan.add(ok)
                    continue
                gorulen.add(ok)
                if k["tur"] in ("skill", "skill_hata"):
                    d = skiller.setdefault(ok, {"yuklendi": [], "hata": []})
                    d["yuklendi" if k["tur"] == "skill" else "hata"].append(k.get("skill") or "?")
                    continue
                o = ozet.setdefault(str(k.get("oturum") or "-")[:8], {}).setdefault(
                    k.get("olay") or "?", {"calisma": 0, "hata": 0, "zaman_asimi": 0, "en_uzun_ms": 0})
                if k["tur"] == "hook_zaman_asimi":
                    o["zaman_asimi"] += 1
                else:
                    o["calisma"] += 1
                    o["hata"] += k.get("sonuc") not in ("ok", "cikis_0")
                    o["en_uzun_ms"] = max(o["en_uzun_ms"], int(k.get("sure_ms") or 0))
    except OSError:
        pass
    return {"hook": ozet, "skill": skiller, "acilis_eksik": sorted(gorulen - acilan)}


def yukleme_yaz(sd: str | None, oturum, eklenti_koku: str | None = None) -> None:
    """SessionStart sonunda `tur=oturum_yukleme`: bu oturumda yüklenmesi beklenen hook olayları ve skill sayısı.
    Satır yoksa SessionStart tamamlanmamıştır (zaman aşımı ya da hata); rapor bunu `acilis_eksik` diye işaretler."""
    if not sd or not etkin():
        return
    try:
        kok = eklenti_koku or os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.join(os.path.dirname(__file__), "..")
        with open(os.path.join(kok, "hooks", "hooks.json"), encoding="utf-8") as f:
            olaylar = sorted(json.load(f).get("hooks", {}))
        try:
            skiller = sum(1 for e in os.scandir(os.path.join(kok, "skills")) if os.path.isfile(os.path.join(e.path, "SKILL.md")))
        except OSError:
            skiller = None
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"),
                     {"zaman": L.simdi(), "oturum": oturum, "tur": "oturum_yukleme", "hook_olaylari": olaylar,
                      "skill_sayisi": skiller})
    except Exception:
        pass


def uyari(sd: str | None, simdi: float | None = None) -> str:
    """Son 24 saatte zaman aşımına uğrayan, daha önce bildirilmemiş hook'lar için tek kısa satır; yoksa boş (0 karakter).
    Her zaman aşımı bir kez bildirilir (`hook_uyari.json` son bildirilen zamanı tutar). Engellemez, veridir."""
    if not sd or not etkin():
        return ""
    try:
        yetim_tara(sd)
        simdi = simdi if simdi is not None else time.time()
        isaret = os.path.join(sd, "hook_uyari.json")
        try:
            with open(isaret, encoding="utf-8") as f:
                son = float(json.load(f).get("son") or 0)
        except (OSError, ValueError, AttributeError):
            son = 0.0
        yol = os.path.join(sd, "gunluk.jsonl")
        with open(yol, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400_000))
            satirlar = f.read().decode("utf-8", "replace").splitlines()
        yeni, en_son = {}, son
        for s in satirlar:
            if '"hook_zaman_asimi"' not in s:
                continue
            try:
                k = json.loads(s)
            except ValueError:
                continue
            t = _epoch(k.get("zaman") or "")
            if t <= son or simdi - t > 86400 or t == float("inf"):
                continue
            yeni[k.get("olay") or "?"] = yeni.get(k.get("olay") or "?", 0) + 1
            en_son = max(en_son, t)
        if not yeni:
            return ""
        L.atomik_yaz(isaret, json.dumps({"son": en_son}))
        ayrinti = ", ".join(f"{o} x{n}" for o, n in sorted(yeni.items()))
        return f"orkestra: önceki hook zaman aşımı ({ayrinti}); yüklenmemiş olabilir. Ayrıntı: orkestra oturum hook"
    except Exception:
        return ""


def _epoch(z: str) -> float:
    try:
        import datetime
        return datetime.datetime.fromisoformat(z.replace("Z", "+00:00")).timestamp()
    except Exception:
        return float("inf")
