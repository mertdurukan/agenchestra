"""Hook çalışma kaydı (I-309): hangi oturumda hangi hook çalıştı, bitti mi, ne kadar sürdü, zaman aşımına uğradı mı.

Sorun: Claude Code zaman aşımında hook sürecini öldürür; süreç kendini kaydedemez, iz kalmaz.
Çözüm: başlarken `hook_acik/<pid>-<ns>.json` işareti (kilitsiz, tek küçük dosya), biterken işaret silinir ve
`gunluk.jsonl`'a `tur=hook_calisma` yazılır. Silinmemiş eski işaret = öldürülmüş hook; sonraki hook ya da
`orkestra oturum hook` onu `tur=hook_zaman_asimi` olarak kaydeder (sürecin canlı olmadığı doğrulanır).
Sıcak yol: hızlı ve başarılı PreToolUse için günlük satırı yazılmaz (yalnız işaret yazılıp silinir).
Hatada sessiz; hook çıktısı değişmez. ORKESTRA_HOOK_KAYDI=0 kapatır.
"""
from __future__ import annotations

import json
import os
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


def bitir(sd: str | None, yol: str | None, olay: str, oturum, arac, sonuc: str, ms: float) -> None:
    """sonuc: ok | cikis_<kod> | hata. İşareti siler; günlük satırı yazar (hızlı başarılı PreToolUse hariç)."""
    if not yol:
        return
    try:
        os.remove(yol)
    except OSError:
        pass
    try:
        if olay == "PreToolUse" and sonuc == "ok" and ms < YAVAS_MS:
            return
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"),
                     {"zaman": L.simdi(), "oturum": oturum, "tur": "hook_calisma", "olay": olay, "arac": arac,
                      "sonuc": sonuc, "sure_ms": round(ms)})
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
    yol = os.path.join(sd, "gunluk.jsonl")
    try:
        with open(yol, encoding="utf-8") as f:
            for s in f:
                if '"hook_' not in s:
                    continue
                try:
                    k = json.loads(s)
                except ValueError:
                    continue
                if k.get("tur") not in ("hook_calisma", "hook_zaman_asimi"):
                    continue
                if oturum and not str(k.get("oturum") or "").startswith(oturum):
                    continue
                if k.get("zaman") and _epoch(k["zaman"]) < esik:
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
    return ozet


def _epoch(z: str) -> float:
    try:
        import datetime
        return datetime.datetime.fromisoformat(z.replace("Z", "+00:00")).timestamp()
    except Exception:
        return float("inf")
