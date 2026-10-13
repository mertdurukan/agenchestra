"""Rüya: oturumlar arasında arka planda çalışan hafıza bakımı (+ skill avı).

Ne zaman: son rüyadan bu yana ≥7 gün ya da ≥10 oturum geçtiyse, oturum kapanırken (SessionEnd) arka planda.
Nasıl: başsız `claude -p` (Sonnet), YALNIZ OKUMA araçlarıyla; hafızayı değiştirmez, öneri raporu yazar.
Rapor: <durum>/ruya/ruya_<tarih>.md ; bir sonraki oturumda ana ajan özetler, kullanıcı onaylarsa `/orkestra:ruya` uygular.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

GUN_ESIGI = 7
OTURUM_ESIGI = 10
CALISMA_ZAMAN_ASIMI_SN = 2 * 3600


def _durum_yolu(sd):
    return os.path.join(sd, "ruya", "durum.json")


def _oku(sd) -> dict:
    try:
        with open(_durum_yolu(sd), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"son_ruya": None, "oturum_sayaci": 0, "son_rapor": None, "rapor_okundu": True, "calisiyor": None}


def _yaz(sd, d):
    L.atomik_yaz(_durum_yolu(sd), json.dumps(d, ensure_ascii=False, indent=2))


def oturum_say(sd, kaynak):
    if kaynak not in (None, "startup"):
        return
    with L.kilit(_durum_yolu(sd)):
        d = _oku(sd)
        d["oturum_sayaci"] = d.get("oturum_sayaci", 0) + 1
        _yaz(sd, d)


def durum(sd) -> dict:
    d = _oku(sd)
    simdi = datetime.datetime.now().astimezone()
    calisiyor = d.get("calisiyor")
    if calisiyor:
        try:
            if (simdi - datetime.datetime.fromisoformat(calisiyor)).total_seconds() > CALISMA_ZAMAN_ASIMI_SN:
                calisiyor = None
        except Exception:
            calisiyor = None
    gun = None
    if d.get("son_ruya"):
        try:
            gun = (simdi - datetime.datetime.fromisoformat(d["son_ruya"])).days
        except Exception:
            gun = None
    zamani = not calisiyor and (gun is None or gun >= GUN_ESIGI or d.get("oturum_sayaci", 0) >= OTURUM_ESIGI)
    return {"son_ruya": d.get("son_ruya"), "gun_once": gun, "oturum_sayaci": d.get("oturum_sayaci", 0),
            "zamani_geldi": bool(zamani), "calisiyor": calisiyor, "son_rapor": d.get("son_rapor"),
            "okunmamis_rapor": d.get("son_rapor") if d.get("son_rapor") and not d.get("rapor_okundu") else None}


def bitti_isaretle(sd):
    with L.kilit(_durum_yolu(sd)):
        d = _oku(sd)
        d["rapor_okundu"] = True
        _yaz(sd, d)


def hafiza_dizini(proje: str, transkript: str | None = None) -> str:
    if transkript:
        return os.path.join(os.path.dirname(transkript), "memory")
    ad = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(proje))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", ad, "memory")


def claude_exe() -> str | None:
    e = os.environ.get("CLAUDE_CODE_EXECPATH")
    if e and os.path.exists(e):
        return e
    adaylar = []
    for kok in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
        adaylar += glob.glob(os.path.join(kok, "Claude", "claude-code", "*", "*", "claude.exe"))
        adaylar += glob.glob(os.path.join(kok, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude", "claude-code", "*", "*", "claude.exe"))
    adaylar = [a for a in adaylar if os.path.exists(a)]
    return max(adaylar, key=os.path.getmtime) if adaylar else None


ISTEM = """#SUREC:ruya
Sen orkestra sisteminin RÜYA (hafıza bakımı) koşusunsun. Kullanıcı yok; YALNIZ OKU, hiçbir dosyayı değiştirme.
Görev: aşağıdaki kaynakları oku ve tek bir Markdown rapor üret (yanıtın yalnız rapor olsun).

Kaynaklar:
1. Otomatik hafıza: {hafiza}  (MEMORY.md dizini + konu dosyaları). Not: oturum başında MEMORY.md'nin yalnız ilk 200 satırı / 25 KB'ı okunur.
2. Proje kuralları: {proje}\\CLAUDE.md ve {proje}\\.claude\\rules\\ (varsa).
3. Ortak defter: {sd}\\ortak_defter.md — yalnız SON ~400 satırı oku (Read offset ile).
4. Olay günlüğü: {sd}\\gunluk.jsonl — son 7 günün istekleri ve skill/ajan kullanımı.
5. Mevcut skill'ler: {proje}\\.claude\\skills\\ ve orkestra plugin skill'leri.

Rapor bölümleri (Türkçe, kısa cümleler):
## 1. Özet — 3-5 madde.
## 2. Birleştirilecek kopyalar — aynı bilgiyi taşıyan hafıza kayıtları; hangi dosyada kalsın.
## 3. Çelişkiler — iki kaydın birbirini yalanladığı yerler; hangisi güncel (tarih/kanıt).
## 4. Eskimiş veya doğrulanamayan — adı geçen dosya/klasör yolları Glob ile var mı? Olmayanları listele. "devam ediyor" denip bitmiş işler.
## 5. Boyut — MEMORY.md satır/bayt; 200 satır sınırına yakınsa hangi kayıtlar konu dosyalarına bölünmeli.
## 6. Önerilen değişiklikler — her biri için dosya, ne değişecek, gerekçe; uygulanabilir kısa diff blokları.
## 7. Skill adayları — gunluk.jsonl'da skill'siz tekrarlanan (≥3) istek türleri; her aday için ad, tetik cümleleri, girdi→çıktı, başlangıç basamağı (T0-T4), mevcut betik.
## 8. Orkestra sağlığı — ortak defterde etiketsiz (#GOREV yok) ajan oranı, reddedilen/yükseltilen kartlar, dikkat çeken maliyet.

Kurallar: sır değeri, şifre, çalışan adı yazma. Emin olmadığın şeyi "doğrulanamadı" diye işaretle. Değişiklik UYGULAMA.
"""


def headless_mumkun(sd: str, exe: str | None) -> bool:
    """Komut satırı oturum açmış mı? (masaüstü oturumunun kimliği başsız koşuya geçmez). Sonuç 12 saat önbellekte."""
    if not exe:
        return False
    d = _oku(sd)
    onb = d.get("headless") or {}
    try:
        if onb.get("zaman") and (datetime.datetime.now().astimezone() - datetime.datetime.fromisoformat(onb["zaman"])).total_seconds() < 12 * 3600:
            return bool(onb.get("mumkun"))
    except Exception:
        pass
    try:
        r = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, encoding="utf-8", timeout=20)
        mumkun = bool(json.loads(r.stdout or "{}").get("loggedIn"))
    except Exception:
        mumkun = False
    with L.kilit(_durum_yolu(sd)):
        st = _oku(sd)
        st["headless"] = {"zaman": L.simdi(), "mumkun": mumkun}
        _yaz(sd, st)
    return mumkun


def basladi_isaretle(sd: str) -> None:
    with L.kilit(_durum_yolu(sd)):
        st = _oku(sd)
        st["calisiyor"] = L.simdi()
        _yaz(sd, st)


def kaydet(sd: str, rapor: str) -> None:
    with L.kilit(_durum_yolu(sd)):
        st = _oku(sd)
        st.update(son_ruya=L.simdi(), oturum_sayaci=0, son_rapor=os.path.abspath(rapor), rapor_okundu=False, calisiyor=None)
        _yaz(sd, st)
    L.defter_ekle(sd, {"gorev": "-", "surec": "ruya", "ajan": "orkestra:ruya-ajani", "model": "sonnet",
                       "yaptim": "Hafıza bakımı ve skill avı (yalnız okuma).", "sonuc": f"Rapor: {rapor}", "kaynak": "ruya"})


def baslat(sd: str, proje: str, transkript: str | None = None, zorla: bool = False) -> str:
    d = durum(sd)
    if d["calisiyor"]:
        return f"zaten çalışıyor (başlangıç {d['calisiyor']})"
    if not zorla and not d["zamani_geldi"]:
        return "zamanı gelmedi"
    exe = claude_exe()
    if not headless_mumkun(sd, exe):
        return ("HEADLESS-YOK: komut satırı oturum açmamış. Rüyayı oturum içinde başlat: Agent aracı, "
                "subagent_type `orkestra:ruya-ajani`, run_in_background true, istem `#SUREC:ruya hafıza klasörü: "
                + hafiza_dizini(proje, transkript) + "`. (Kalıcı çözüm: bir kez `claude auth login`.)")
    with L.kilit(_durum_yolu(sd)):
        st = _oku(sd)
        st["calisiyor"] = L.simdi()
        _yaz(sd, st)
    hafiza = hafiza_dizini(proje, transkript)
    args = [sys.executable, os.path.abspath(__file__), "_kos", sd, proje, hafiza, exe]
    bayrak = 0
    if os.name == "nt":
        bayrak = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    subprocess.Popen(args, cwd=proje, creationflags=bayrak, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    return f"rüya arka planda başladı → {os.path.join(sd, 'ruya')}"


def _kos(sd: str, proje: str, hafiza: str, exe: str):
    ortam = dict(os.environ, ORKESTRA_RUYA="1", PYTHONUTF8="1")
    istem = ISTEM.format(hafiza=hafiza, proje=proje, sd=sd)
    damga = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    rapor = os.path.join(sd, "ruya", f"ruya_{damga}.md")
    komut = [exe, "-p", istem, "--model", "sonnet", "--effort", "medium", "--max-turns", "60",
             "--allowedTools", "Read", "Glob", "Grep", "--add-dir", hafiza, "--output-format", "text"]
    try:
        r = subprocess.run(komut, cwd=proje, env=ortam, capture_output=True, text=True, encoding="utf-8", timeout=3600)
        metin = r.stdout.strip() or f"(boş çıktı; çıkış kodu {r.returncode})\n\n```\n{r.stderr[-2000:]}\n```"
    except Exception as e:
        metin = f"(rüya koşusu başarısız: {type(e).__name__}: {e})"
    L.atomik_yaz(rapor, f"# Rüya raporu — {L.simdi()[:16]}\n\n" + L.maskele(metin) + "\n")
    with L.kilit(_durum_yolu(sd)):
        st = _oku(sd)
        st.update(son_ruya=L.simdi(), oturum_sayaci=0, son_rapor=rapor, rapor_okundu=False, calisiyor=None)
        _yaz(sd, st)
    L.defter_ekle(sd, {"gorev": "-", "surec": "ruya", "ajan": "ruya-bakimcisi", "model": "sonnet",
                       "yaptim": "Arka planda hafıza bakımı ve skill avı yaptım (yalnız okuma).", "sonuc": f"Rapor: {rapor}",
                       "kaynak": "ruya"})


if __name__ == "__main__":
    if len(sys.argv) >= 6 and sys.argv[1] == "_kos":
        _kos(*sys.argv[2:6])
