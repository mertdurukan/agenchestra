"""Orkestra hook dağıtıcısı: `python hook.py <OlayAdı>` — girdi stdin'de JSON.

İlke: yalnız `.claude/orkestra/` açık projelerde iş yapar; başka her yerde sessizce geçer.
Kapılar (PreToolUse, Stop) iç hatada güvenli tarafa düşer: korunan dosyaya dokunuşu reddeder, gerisini geçirir.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

KORUNAN_ADLAR = {"ortak_defter.md", "ortak_defter.jsonl", "maliyet.jsonl", "gunluk.jsonl"}
YAZAN_ARACLAR = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
KABUK_ARACLARI = {"Bash", "PowerShell"}
# Yalnız KOMUT KONUMUNDAKİ orkestra çağrısı: satır/segment başı (^ ; & | ( sonrası), isteğe bağlı
# `python … <yol>/orkestra.py`. `grep x orkestra.py` gibi argüman olarak geçen adlar eşleşmez.
ORK_KOMUT = re.compile(
    r"""(?:^|[;&|(\n])\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"""
    r"""(?:(?:python[0-9.]*|py)(?:\.exe)?\s+(?:-\S+\s+)*["']?(?:[^\s"';&|]*[\\/])?)?"""
    r"""(?:[^\s"';&|]*[\\/])?orkestra(?:\.py|\.cmd)?["']?(?=\s|$)""", re.M)
COKLU_KOMUT = re.compile(r"(;|&&|\|\||\||`|\$\(|\n|>)")
YAZAN_ALT_KOMUT = re.compile(r"\b(kart\s+(yeni|toplu|durum|denetim|yukselt|teslim)|defter\s+ekle|baslat|ruya\s+(basla|bitti))\b")
KORUNAN_IZ = re.compile(r"(ortak_defter|maliyet\.jsonl|gunluk\.jsonl|\.denetim\.json|orkestra[\\/]+gorevler)", re.I)
_KORUNAN = r"(?:ortak_defter|maliyet\.jsonl|gunluk\.jsonl|\.denetim\.json|orkestra[\\/]+gorevler)"
# Yalnız yazma işlecinin HEDEFİ korunan dosyaysa: aynı komut parçasında (satır/;/&/| ile bölünmeden) işleç → korunan yol,
# ya da open(<korunan>, 'w'/'a'). Komut gövdesinde (heredoc, kod) korunan adın geçmesi tek başına yetmez.
KABUK_YAZMA_HEDEF = re.compile(
    r"(?:>>?|\btee\b|Set-Content|Add-Content|Out-File|\bsed\s+-i\S*|\brm\b|\bmv\b|\bcp\b|\bdel\b|Remove-Item|Move-Item|Copy-Item)"
    r"[^|;&\n]*?" + _KORUNAN
    + r"|open\([^)\n]*" + _KORUNAN + r"[^)\n]*,\s*['\"][wa]", re.I)


def izin_ver(guncel_girdi: dict | None = None, neden: str = ""):
    o = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                "permissionDecisionReason": neden or "orkestra"}}
    if guncel_girdi is not None:
        o["hookSpecificOutput"]["updatedInput"] = guncel_girdi
    L.hook_cikti(o)


def reddet(neden: str):
    L.hook_cikti({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                         "permissionDecisionReason": f"orkestra: {neden}"}})


def gec():
    L.hook_cikti(None)


# ---------------------------------------------------------------- ajan → görev eşlemesi

def ajan_gorevi(sd: str, inp: dict) -> tuple[str, str]:
    """Alt ajanın #GOREV/#SUREC etiketleri (önbellekli)."""
    aid = inp.get("agent_id")
    if not aid:
        return "-", "orkestrasyon"
    onbellek = os.path.join(sd, "oturumlar", f"ajan_{aid}.json")
    try:
        with open(onbellek, encoding="utf-8") as f:
            d = json.load(f)
            return d["gorev"], d["surec"]
    except Exception:
        pass
    tp = inp.get("agent_transcript_path") or L.alt_ajan_transkripti(inp.get("transcript_path", ""), inp.get("session_id", ""), aid)
    ilk = None
    try:
        with open(tp, encoding="utf-8", errors="replace") as f:
            for satir in f:
                o = json.loads(satir)
                if o.get("type") == "user":
                    ilk = L._metin((o.get("message") or {}).get("content"))
                    if ilk and ilk.strip():
                        break
    except Exception:
        pass
    gorev, surec = L.etiketler(ilk)
    if ilk:
        os.makedirs(os.path.dirname(onbellek), exist_ok=True)
        L.atomik_yaz(onbellek, json.dumps({"gorev": gorev, "surec": surec, "ajan": inp.get("agent_type") or "?"}))
    return gorev, surec


# ---------------------------------------------------------------- PreToolUse

def pre_tool_use(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    arac = inp.get("tool_name", "")
    girdi = dict(inp.get("tool_input") or {})
    aid = inp.get("agent_id")
    atip = inp.get("agent_type") or ""

    if arac in YAZAN_ARACLAR:
        yol = girdi.get("file_path") or girdi.get("notebook_path") or ""
        if not yol:
            gec()
        tam = os.path.abspath(os.path.join(inp.get("cwd") or os.getcwd(), yol))
        try:
            rel = os.path.relpath(tam, sd).replace("\\", "/")
        except ValueError:
            rel = ".."
        if not rel.startswith(".."):
            ad = os.path.basename(tam)
            if ad in KORUNAN_ADLAR or rel.startswith("gorevler/") or ad.endswith(".denetim.json"):
                reddet("ortak defter, token defteri ve görev kartları elle düzenlenmez; `orkestra defter ekle` / `orkestra kart …` kullan.")
            gec()
        proje = L.proje_dizini(inp.get("cwd"))
        oid = inp.get("session_id")
        if aid:
            gorev, _ = ajan_gorevi(sd, inp)
            if gorev != "-":
                k = L.kart_oku(sd, gorev)
                if k and k.get("yazma_alani") and not L.yazma_alaninda_mi(proje, tam, k["yazma_alani"]):
                    reddet(f"{gorev} kartının yazma alanı dışında ({', '.join(k['yazma_alani'])}). Paralel işler çakışmasın diye "
                           "yalnız kendi alanına yaz; gerekiyorsa ana ajana bildir.")
            gec()
        # ana ajan: o anda işçide olan kartların alanına yazmaz (paralel güvenlik + rol ayrımı)
        for k in L.kartlar(sd):
            if k.get("oturum") == oid and k.get("durum") == "isleniyor" and k.get("yazma_alani") \
                    and L.yazma_alaninda_mi(proje, tam, k["yazma_alani"]):
                reddet(f"bu dosya şu an {k['id']} işçisinin yazma alanında. Ana ajan planlar, dağıtır, toplar; "
                       "işçi işini yapmaz. Değişiklik gerekiyorsa işi bir işçiye ver ya da kartı `beklemede`ye al.")
        gec()

    if arac in KABUK_ARACLARI:
        komut = girdi.get("command") or ""
        # Tırnak içi metin veridir (heredoc dışı argüman, python -c kodu): komut analizinden çıkarılır.
        # İstisna: tırnaklanmış program yolu "…/orkestra.py" korunur (tırnakları atılır).
        yol_acik = re.sub(r'["\']([^"\']*orkestra(?:\.py|\.cmd))["\']', lambda m: m.group(1).replace(" ", "_"), komut)
        tirnaksiz = re.sub(r'"(?:\\.|[^"\\])*"|\'[^\']*\'', '""', yol_acik)
        if ORK_KOMUT.search(tirnaksiz):
            yazan = bool(YAZAN_ALT_KOMUT.search(tirnaksiz))
            if COKLU_KOMUT.search(tirnaksiz):
                if yazan:
                    reddet("kart/defter yazan `orkestra` komutunu tek başına çalıştır (zincir, boru, yönlendirme olmadan).")
                gec()
            temiz = re.sub(r"\s--ajan-(id|tipi)(=|\s+)\S+", "", komut).rstrip()
            kimlik_id = aid or "ana"
            kimlik_tip = atip or ("ana" if not aid else "bilinmiyor")
            girdi["command"] = f"{temiz} --ajan-id {kimlik_id} --ajan-tipi {kimlik_tip}"
            izin_ver(girdi, "orkestra CLI (kimlik eklendi)")
        if KABUK_YAZMA_HEDEF.search(komut):
            reddet("orkestra durum dosyalarına kabukla yazılmaz; `orkestra` CLI'ını kullan.")
        gec()
    gec()


# ---------------------------------------------------------------- SubagentStart / Stop

def subagent_start(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    gorev, surec = ajan_gorevi(sd, inp)
    if gorev == "-" or not L.kart_oku(sd, gorev):
        gec()
    try:
        import subprocess
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "orkestra.py"), "defter", "baglam", gorev, "--max", "1800"],
                             capture_output=True, text=True, encoding="utf-8", timeout=8, cwd=L.proje_dizini(inp.get("cwd"))).stdout
    except Exception:
        out = ""
    if out.strip():
        L.hook_cikti({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                             "additionalContext": "Orkestra bağlamı (yalnız ihtiyacın olan kayıtlar):\n" + out[:1900]}})
    gec()


def _maliyet_satirlari(sd, ozet, taban):
    for model, m in ozet["modeller"].items():
        L.jsonl_ekle(os.path.join(sd, "maliyet.jsonl"), dict(taban, model=model, **m))


def subagent_stop(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    aid = inp.get("agent_id") or "?"
    tp = inp.get("agent_transcript_path") or L.alt_ajan_transkripti(inp.get("transcript_path", ""), inp.get("session_id", ""), aid)
    ozet = L.transkript_oku(tp)
    meta = L.alt_ajan_meta(tp)
    atip = inp.get("agent_type") or meta.get("agentType") or "?"
    gorev, surec = L.etiketler(ozet["ilk_kullanici"])
    if surec == "bilinmiyor":
        surec = "denetim" if "denetci" in atip else ("arastirma" if atip in ("Explore", "orkestra:arastirmaci") else
                                                      "ruya" if "ruya" in atip else "is" if "isci" in atip else "bilinmiyor")
    # Sayaç modülünün (maliyet tur) aynı ajanı görev/süreç/tip ile eşleyebilmesi için önbellek.
    L.atomik_yaz(os.path.join(sd, "oturumlar", f"ajan_{aid}.json"), json.dumps({"gorev": gorev, "surec": surec, "ajan": atip}))
    taban = {"zaman": L.simdi(), "oturum": inp.get("session_id"), "gorev": gorev, "surec": surec, "ajan": atip,
             "agent_id": aid, "sure_ms": L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"]), "tur": ozet["tur"],
             "arac_cagrisi": ozet["arac_cagrisi"], "ruya": bool(os.environ.get("ORKESTRA_RUYA")), "kaynak": "hook"}
    _maliyet_satirlari(sd, ozet, taban)
    ana_model = max(ozet["modeller"].items(), key=lambda x: x[1]["maliyet_usd"])[0] if ozet["modeller"] else "-"
    ilk = re.sub(r"#(GOREV|SUREC):\S+", "", ozet["ilk_kullanici"] or "").strip().replace("\n", " ")
    L.defter_ekle(sd, {"gorev": gorev, "surec": surec, "ajan": atip, "agent_id": aid, "model": ana_model,
                       "yaptim": meta.get("description") or ilk[:200], "sonuc": (inp.get("last_assistant_message") or "")[:600],
                       "dokunulan": ozet["dokunulan"], "token": ozet["toplam"], "kaynak": "hook"})
    if gorev != "-":
        yol = L.kart_yolu(sd, gorev)
        if os.path.exists(yol):
            with L.kilit(yol):
                k = L.kart_oku(sd, gorev)
                rol = "isciler" if "isci" in atip else ("denetciler" if "denetci" in atip else None)
                if rol and aid not in k[rol]:
                    k[rol].append(aid)
                k.setdefault("token", {"giris": 0, "cikis": 0, "maliyet_usd": 0.0})
                k["token"]["giris"] += ozet["toplam"]["giris"] + ozet["toplam"]["onbellek_okuma"] + ozet["toplam"]["onbellek_yazma"]
                k["token"]["cikis"] += ozet["toplam"]["cikis"]
                k["token"]["maliyet_usd"] = round(k["token"]["maliyet_usd"] + ozet["toplam"]["maliyet_usd"], 6)
                k["gecmis"].append({"zaman": L.simdi(), "olay": "ajan-bitti", "ajan": atip, "agent_id": aid, "surec": surec})
                L.kart_yaz(sd, k)
    gec()


# ---------------------------------------------------------------- Stop (ana ajan)

def stop(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    oid = inp.get("session_id") or "-"
    if not os.environ.get("ORKESTRA_RUYA"):
        import niyet
        niyet.olay(oid, L.proje_dizini(inp.get("cwd")), "tur")  # Claude turu bitirdi → kullanıcıyı bekliyor
    ofset_yolu = os.path.join(sd, "oturumlar", f"{oid}.json")
    try:
        with open(ofset_yolu, encoding="utf-8") as f:
            ofset = json.load(f).get("ofset", 0)
    except Exception:
        ofset = 0
    ozet = L.transkript_oku(inp.get("transcript_path"), ofset, yan_zincir=False)
    L.atomik_yaz(ofset_yolu, json.dumps({"ofset": ozet["ofset"], "guncelleme": L.simdi()}))
    ruya = bool(os.environ.get("ORKESTRA_RUYA"))
    ajan = "ruya-bakimcisi" if ruya else "ana-ajan"
    surec = "ruya" if ruya else "orkestrasyon"
    if ozet["modeller"]:
        taban = {"zaman": L.simdi(), "oturum": oid, "gorev": "-", "surec": surec, "ajan": ajan, "agent_id": None,
                 "sure_ms": L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"]), "tur": ozet["tur"],
                 "arac_cagrisi": ozet["arac_cagrisi"], "ruya": ruya, "kaynak": "hook"}
        _maliyet_satirlari(sd, ozet, taban)
    kayda_deger = any(a in ozet["araclar"] for a in ("Agent", "Task", "Workflow")) or ozet["dokunulan"]
    if kayda_deger and ozet["modeller"]:
        araclar = ", ".join(f"{k}×{v}" for k, v in sorted(ozet["araclar"].items(), key=lambda x: -x[1])[:6])
        L.defter_ekle(sd, {"gorev": "-", "surec": surec, "ajan": ajan, "model": max(ozet["modeller"].items(), key=lambda x: x[1]["maliyet_usd"])[0],
                           "yaptim": f"Tur: {ozet['arac_cagrisi']} araç çağrısı ({araclar})",
                           "sonuc": (inp.get("last_assistant_message") or "")[:400], "dokunulan": ozet["dokunulan"],
                           "token": ozet["toplam"], "kaynak": "hook"})
    # Bitiş kapısı: bu oturumun açık kartları
    if ruya or inp.get("background_tasks"):
        gec()
    acik = []
    for k in L.kartlar(sd):
        if k.get("oturum") != oid:
            continue
        d = L.kart_durumu_hesapla(k)
        if d in ("isleniyor", "denetimde", "reddedildi", "onaylandi"):
            acik.append((k["id"], d, k["baslik"]))
    if not acik:
        gec()
    liste = "; ".join(f"{g} [{d}] {b[:50]}" for g, d, b in acik)
    if inp.get("stop_hook_active"):
        L.hook_cikti({"systemMessage": f"Orkestra: açık kartlar kaldı → {liste}"})
    L.hook_cikti({"decision": "block", "reason":
                  f"Orkestra bitiş kapısı: bu oturumun açık kartları var → {liste}. "
                  "onaylandi → sonucu topla ve `orkestra kart teslim <id>`; denetimde → ayrı denetçiyi çalıştır; "
                  "reddedildi → düzeltme/yükseltme yap; bilerek bırakıyorsan `orkestra kart durum <id> beklemede --not \"neden\"`."})


# ---------------------------------------------------------------- diğer olaylar

def session_start(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    import ruya
    ruya.oturum_say(sd, inp.get("source"))
    ks = [k for k in L.kartlar(sd) if L.kart_durumu_hesapla(k) in L.ACIK_DURUMLAR + ("beklemede",)]
    satirlar = ["Orkestra bu projede açık. Ana ajan: planla → `orkestra kart` ile kartla → işçi + AYRI denetçiyle dağıt "
                "(`/orkestra:is`) → onaylıyı `orkestra kart teslim` ile topla. Ortak defter: `orkestra defter baglam <id>`."]
    if ks:
        satirlar.append("Açık/bekleyen kartlar: " + "; ".join(f"{k['id']} [{L.kart_durumu_hesapla(k)}] {k['baslik'][:40]}" for k in ks[:8]))
    r = ruya.durum(sd)
    if r.get("okunmamis_rapor"):
        satirlar.append(f"Rüya raporu hazır: {r['okunmamis_rapor']} — kullanıcıya kısaca özetle ve `/orkestra:ruya` ile uygulamayı öner.")
    elif r.get("zamani_geldi") and not r.get("calisiyor"):
        hafiza = ruya.hafiza_dizini(L.proje_dizini(inp.get("cwd")), inp.get("transcript_path"))
        satirlar.append("RÜYA ZAMANI: kullanıcının ilk isteğini yanıtlarken AYNI mesajda, kullanıcıyı bölmeden, Agent aracıyla "
                        "`orkestra:ruya-ajani` ajanını run_in_background: true ile başlat; istem: "
                        f"`#SUREC:ruya hafıza klasörü: {hafiza}`. Kullanıcıya yalnız tek satırla bildir.")
    L.hook_cikti({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(satirlar)[:1800]}})


def user_prompt_submit(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if sd and not os.environ.get("ORKESTRA_RUYA"):
        metin = L.maskele(inp.get("prompt") or "")
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": inp.get("session_id"), "tur": "istek",
                                                         "metin": metin[:300], "uzunluk": len(metin)})
        # Niyet kaydı: kullanıcı yazdı → Claude çalışıyor. Sistem iletileri (<agent-message>, <task-notification>) istek metni sayılmaz.
        import niyet
        sistem = metin.lstrip().startswith("<")
        niyet.olay(inp.get("session_id"), L.proje_dizini(inp.get("cwd")), "istek", metin=None if sistem else metin[:200])
        if not sistem:
            L.hook_cikti({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": niyet.baglam_metni(inp.get("session_id"))}})
    gec()


def post_tool_use(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    arac = inp.get("tool_name")
    g = inp.get("tool_input") or {}
    kayit = {"zaman": L.simdi(), "oturum": inp.get("session_id"), "ajan_baglami": inp.get("agent_type") or "ana"}
    if arac == "Skill":
        kayit.update(tur="skill", skill=g.get("skill") or g.get("name"))
    elif arac in ("Agent", "Task"):
        kayit.update(tur="ajan", ajan=g.get("subagent_type") or "general-purpose", model=g.get("model"),
                     arka_plan=bool(g.get("run_in_background")), aciklama=L.maskele(g.get("description") or "")[:80])
    elif arac == "Workflow":
        kayit.update(tur="workflow", ad=g.get("name") or (g.get("scriptPath") and os.path.basename(g["scriptPath"])) or "satir-ici")
    else:
        gec()
    L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), kayit)
    gec()


def session_end(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd or os.environ.get("ORKESTRA_RUYA"):
        gec()
    import niyet
    niyet.olay(inp.get("session_id"), L.proje_dizini(inp.get("cwd")), "kapandi")
    import ruya
    if ruya.durum(sd).get("zamani_geldi"):
        ruya.baslat(sd, L.proje_dizini(inp.get("cwd")), transkript=inp.get("transcript_path"))
    gec()


def config_change(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if sd:
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": inp.get("session_id"), "tur": "ayar",
                                                         "kaynak": inp.get("source"), "dosya": inp.get("file_path")})
    gec()


OLAYLAR = {
    "PreToolUse": pre_tool_use, "SubagentStart": subagent_start, "SubagentStop": subagent_stop, "Stop": stop,
    "SessionStart": session_start, "UserPromptSubmit": user_prompt_submit, "PostToolUse": post_tool_use,
    "SessionEnd": session_end, "ConfigChange": config_change,
}


def main():
    olay = sys.argv[1] if len(sys.argv) > 1 else ""
    inp = L.stdin_json()
    try:
        OLAYLAR[olay](inp)
    except SystemExit:
        if olay in ("SessionStart", "SubagentStop", "Stop", "PostToolUse"):
            sd = L.durum_dizini(inp.get("cwd"))
            if sd:
                import ozet
                ozet.yaz(sd, L.proje_dizini(inp.get("cwd")))
        raise
    except Exception as e:  # güvenli taraf
        try:
            sd = L.durum_dizini(inp.get("cwd"))
            if sd:
                L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "tur": "hook-hatasi", "olay": olay,
                                                                 "hata": f"{type(e).__name__}: {e}"[:300],
                                                                 "iz": traceback.format_exc()[-800:]})
        except Exception:
            pass
        if olay == "PreToolUse":
            g = inp.get("tool_input") or {}
            hedef = (g.get("file_path") or "") + " " + (g.get("command") or "")
            if KORUNAN_IZ.search(hedef):
                reddet("kapı iç hata verdi; korunan dosyaya dokunuş güvenlik için reddedildi.")
        gec()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
