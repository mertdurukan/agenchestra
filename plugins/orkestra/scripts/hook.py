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
import baglam as B  # noqa: E402

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
YAZAN_ALT_KOMUT = re.compile(r"\b(kart\s+(yeni|toplu|durum|denetim|yukselt|teslim|agac|birlestir|test-kos|test-kilit-ac)|defter\s+ekle|baslat|(?:perspektif|ruya)\s+(basla|bitti))\b")
KORUNAN_IZ = re.compile(r"(ortak_defter|maliyet\.jsonl|gunluk\.jsonl|\.denetim\.json|orkestra[\\/]+gorevler)", re.I)
_KORUNAN = r"(?:ortak_defter|maliyet\.jsonl|gunluk\.jsonl|\.denetim\.json|orkestra[\\/]+gorevler)"
# Yalnız yazma işlecinin HEDEFİ korunan dosyaysa: aynı komut parçasında (satır/;/&/| ile bölünmeden) işleç → korunan yol,
# ya da open(<korunan>, 'w'/'a'). Komut gövdesinde (heredoc, kod) korunan adın geçmesi tek başına yetmez.
KABUK_YAZMA_HEDEF = re.compile(
    r"(?:>>?|\btee\b|Set-Content|Add-Content|Out-File|\bsed\s+-i\S*|\brm\b|\bmv\b|\bcp\b|\bdel\b|Remove-Item|Move-Item|Copy-Item)"
    r"[^|;&\n]*?" + _KORUNAN
    + r"|open\([^)\n]*" + _KORUNAN + r"[^)\n]*,\s*['\"][wa]", re.I)


# ---------------------------------------------------------------- test kilidi (kod kartları)

def _rel(proje: str, tam: str) -> str | None:
    """Proje içi göreli yol ('/' ayraçlı); proje dışıysa None."""
    try:
        r = os.path.relpath(tam, proje).replace("\\", "/")
    except ValueError:
        return None
    return None if r == ".." or r.startswith("../") else r


def kilitli_testler(sd: str, ks: list[dict] | None = None) -> dict[str, str]:
    """Teslim/iptal olmayan kartların kilitli test dosyaları → {göreli yol: kart kimliği}."""
    out = {}
    for k in L.kartlar(sd) if ks is None else ks:
        if k.get("durum") in ("teslim", "iptal"):
            continue
        d = (k.get("test_kilidi") or {}).get("dosyalar")
        if isinstance(d, dict):
            for y in d:
                out.setdefault(y.replace("\\", "/"), k.get("id", "?"))
    return out


def _anahtar(rel: str) -> str:
    """Paylaşılan proje-göreli yolun kıyas biçimi: '/' ayraçlı; Windows'ta büyük/küçük harf duyarsız."""
    return os.path.normcase(rel.replace("\\", "/")).replace("\\", "/")


def _bicimler(yol: str) -> set[str]:
    """Yolun mutlak ve gerçek (bağlantı/kısa ad çözülmüş) biçimleri."""
    a = os.path.abspath(yol)
    try:
        return {a, os.path.realpath(a)}
    except (OSError, ValueError):
        return {a}


def paylasilan_goreli(proje: str, tam: str, ks: list[dict]) -> set[str]:
    """Yazım hedefi → paylaşılan proje-göreli yol uzayındaki karşılıkları (kıyas biçiminde; proje dışıysa boş küme).

    Kilitler bu uzaydadır. Hedef HERHANGİ bir kartın çalışma ağacındaysa o ağaçtan paylaşılan depoya çevrilir
    (`L.agac_esdegeri`); proje içindeyse doğrudan göreli yolu da eklenir. Ağaç sahibi kartın kim olduğu ve durumu
    önemsizdir: kilit sahibi başka bir kart olabilir, iptal kartı da `kart durum … isleniyor` ile yeniden açılabilir.
    Teslim edilen kartın ağacı birleşmede kaldırılır (`calisma_agaci` düşer), eşlemeye girmez."""
    out = set()
    agacli = [k for k in ks if (k.get("calisma_agaci") or {}).get("yol")]
    for t in _bicimler(tam):
        for p in _bicimler(proje):
            r = _rel(p, t)
            if r is not None:
                out.add(_anahtar(r))
            for k in agacli:
                es = L.agac_esdegeri(k, t)
                r = _rel(p, es) if es is not None else None
                if r is not None:
                    out.add(_anahtar(r))
    return out


def kilitli_test_bul(sd: str, proje: str, tam: str) -> tuple[str, str] | None:
    """Yazım hedefi açık bir kartın kilitli test dosyasıysa (göreli yol, kilit sahibi kart), değilse None.

    Hedef önce paylaşılan proje-göreli uzaya normalize edilir, sonra TÜM açık kartların kilit kümesiyle tek sorguda
    karşılaştırılır; ağaç sayısından ve ağaç/kilit sahibi eşleşmesinden bağımsızdır. Örnek: G1 tests/test_x.py'yi
    kilitlediyse G2'nin ağacındaki tests/test_x.py de kapalıdır (G2 teslimde birleşince G1'in kilitli testi değişirdi)."""
    ks = L.kartlar(sd)
    kilit = {_anahtar(y): (y, gid) for y, gid in kilitli_testler(sd, ks).items()}
    if not kilit:
        return None
    for a in sorted(paylasilan_goreli(proje, tam, ks)):
        if a in kilit:
            return kilit[a]
    return None


def test_alaninda_mi(rel: str, desenler: list[str]) -> bool:
    """rel, test_alani glob'larından birine uyar mı (`**` özyinelemeli; `a/**/b` `a/b`yi de kapsar)."""
    import fnmatch
    for d in desenler or []:
        d = (d or "").replace("\\", "/").strip()
        for v in {d, d.replace("/**/", "/")}:
            if v and fnmatch.fnmatch(os.path.normcase(rel), os.path.normcase(v)):
                return True
    return False


_KABUK_YAZMA_ISLEC = (r"(?:>>?|\btee\b|Set-Content|Add-Content|Out-File|\bsed\s+-i\S*|\brm\b|\bmv\b|\bcp\b|\bdel\b|"
                      r"Remove-Item|Move-Item|Copy-Item|\btruncate\b)")


def kabuk_kilitli_yazma(komut: str, kilitli: dict[str, str]) -> str | None:
    """Kabuk komutu kilitli bir test dosyasını yazma işlecinin HEDEFİ yapıyorsa kart kimliğini döndürür (en iyi çaba).
    Yakalanamayanlar (değişken/dolaylı yol, betik içi yazma) `kart test-kos yesil` hash denetimine kalır."""
    for rel, gid in kilitli.items():
        ad = "(?:" + re.escape(rel) + "|" + re.escape(os.path.basename(rel)) + ")(?![\\w.])"
        r = re.compile(_KABUK_YAZMA_ISLEC + r"[^|;&\n]*?" + ad
                       + r"|open\([^)\n]*" + ad + r"[^)\n]*,\s*['\"][wax]", re.I)
        if r.search(komut):
            return gid
    return None


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

def transkript_bul(ana_transkript: str, session_id: str, agent_id: str) -> str:
    """Alt ajan transkripti: önce <oturum>/subagents/agent-<id>.jsonl, yoksa subagents/**/ altında (workflows/<run>/...)."""
    yol = L.alt_ajan_transkripti(ana_transkript or "", session_id or "", agent_id)
    if os.path.exists(yol):
        return yol
    import glob
    kok = os.path.join(os.path.dirname(ana_transkript or ""), session_id or "", "subagents")
    bulunan = sorted(glob.glob(os.path.join(glob.escape(kok), "**", f"agent-{glob.escape(agent_id)}.jsonl"), recursive=True))
    return bulunan[0] if bulunan else yol


def transkript_etiketleri(tp: str, en_cok: int = 5) -> tuple[str, str, bool]:
    """İlk `en_cok` kullanıcı mesajında #GOREV arar → (görev, süreç, ilk_mesaj_var_mı).

    Hiçbirinde #GOREV yoksa eski davranış: ilk dolu mesajdan etiketler."""
    ilk, n = None, 0
    try:
        with open(tp, encoding="utf-8", errors="replace") as f:
            for satir in f:
                try:
                    o = json.loads(satir)
                except json.JSONDecodeError:
                    continue
                if o.get("type") != "user":
                    continue
                m = L._metin((o.get("message") or {}).get("content"))
                if not (m and m.strip()):
                    continue
                n += 1
                if ilk is None:
                    ilk = m
                g, s = L.etiketler(m)
                if g != "-":
                    return g, s, True
                if n >= en_cok:
                    break
    except Exception:
        pass
    g, s = L.etiketler(ilk)
    return g, s, bool(ilk)


def ajan_gorevi(sd: str, inp: dict) -> tuple[str, str]:
    """Alt ajanın #GOREV/#SUREC etiketleri (önbellekli; '-' sonucu önbelleğe yazılmaz)."""
    aid = inp.get("agent_id")
    if not aid:
        return "-", "orkestrasyon"
    onbellek = os.path.join(sd, "oturumlar", f"ajan_{aid}.json")
    try:
        with open(onbellek, encoding="utf-8") as f:
            d = json.load(f)
            if d["gorev"] != "-":
                return d["gorev"], d["surec"]
    except Exception:
        pass
    tp = inp.get("agent_transcript_path") or transkript_bul(inp.get("transcript_path", ""), inp.get("session_id", ""), aid)
    gorev, surec, var = transkript_etiketleri(tp)
    if var and gorev != "-":
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
        trel = _rel(proje, tam)
        kb = kilitli_test_bul(sd, proje, tam)  # kilitli test: ana ajan dahil herkese kapalı (kart ağaçları dahil)
        if kb:
            reddet(f"kilitli test: {kb[0]} ({kb[1]} kartının test kilidi). Kırmızı sonrası test dosyaları değişmez; "
                   "değişiklik gerekiyorsa ana ajan `orkestra kart test-kilit-ac` ile kilidi açar.")
        if aid:
            gorev, surec = ajan_gorevi(sd, inp)
            if gorev != "-":
                k = L.kart_oku(sd, gorev)
                ca = (k or {}).get("calisma_agaci") or {}
                agacta = bool(k and ca.get("yol") and L.yol_altinda(tam, ca["yol"]))
                if k and ca.get("yol") and not agacta and ca.get("depo") and L.yol_altinda(tam, ca["depo"]):
                    reddet(f"{gorev} kartının çalışma ağacı var; paylaşılan ağaca ({ca['depo']}) değil, "
                           f"{L.CALISMA_AGACI_ONEKI.lower()}{ca['yol']} altına yaz.")
                # test_alani proje köküne göredir; kart ağacındaki yazım paylaşılan depodaki karşılığı üzerinden okunur.
                ttrel = trel
                if agacta:
                    es = L.agac_esdegeri(k, tam)
                    ttrel = _rel(proje, es) if es is not None else None
                if k and k.get("sinif") == "kod" and k.get("test_alani") and ttrel is not None:
                    icinde = test_alaninda_mi(ttrel, k["test_alani"])
                    if surec == "test-yaz":
                        if not icinde:
                            reddet(f"{gorev}: #SUREC:test-yaz yalnız test_alani içine yazar ({', '.join(k['test_alani'])}).")
                        gec()
                    elif icinde:
                        reddet(f"{gorev}: test_alani ({', '.join(k['test_alani'])}) yalnız #SUREC:test-yaz ile yazılır; "
                               "testleri kod işçisi değiştiremez.")
                if agacta:
                    # Kartın kendi çalışma ağacı var: işçi orada, (köke çevrilmiş) yazma alanı içinde yazar.
                    if k.get("yazma_alani") and not L.desen_eslesir(proje, tam, k["yazma_alani"]):
                        reddet(f"{gorev} kartının yazma alanı dışında ({', '.join(k['yazma_alani'])}); çalışma ağacı: {ca['yol']}.")
                    gec()
                if k and k.get("yazma_alani") and not L.yazma_alaninda_mi(proje, tam, k["yazma_alani"]):
                    reddet(f"{gorev} kartının yazma alanı dışında ({', '.join(k['yazma_alani'])}). Paralel işler çakışmasın diye "
                           "yalnız kendi alanına yaz; gerekiyorsa ana ajana bildir.")
            gec()
        # ana ajan: o anda işçide olan kartların alanına yazmaz (paralel güvenlik + rol ayrımı)
        for k in L.kartlar(sd):
            if k.get("oturum") == oid and k.get("durum") == "isleniyor" and k.get("yazma_alani") \
                    and L.desen_eslesir(proje, tam, k["yazma_alani"]):  # mutlak/çalışma ağacı desenleri dahil
                reddet(f"bu dosya şu an {k['id']} işçisinin yazma alanında. Ana ajan planlar, dağıtır, toplar; "
                       "işçi işini yapmaz. Değişiklik gerekiyorsa işi bir işçiye ver ya da kartı `beklemede`ye al.")
        gec()

    if arac in KABUK_ARACLARI:
        komut = girdi.get("command") or ""
        kgid = kabuk_kilitli_yazma(komut, kilitli_testler(sd))
        if kgid:
            reddet(f"kilitli test: komut {kgid} kartının kilitli test dosyasına yazıyor/siliyor. Kilit yalnız ana ajanın "
                   "`orkestra kart test-kilit-ac` komutuyla açılır.")
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
    aid = inp.get("agent_id")
    if aid:  # açık ajan kaydı: bitişi hiç gelmeyen (asılı) ajanları görünür kılar; subagent_stop siler
        try:
            L.atomik_yaz(os.path.join(sd, "oturumlar", f"acik_ajan_{aid}.json"), json.dumps(
                {"zaman": L.simdi(), "oturum": inp.get("session_id"), "agent_id": aid, "ajan": inp.get("agent_type") or "?",
                 "gorev": gorev, "surec": surec}, ensure_ascii=False))
        except Exception:
            pass
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


def _oturum_baglami(sd: str, oid: str | None) -> str:
    try:
        with open(os.path.join(sd, "oturumlar", f"{oid}.json"), encoding="utf-8") as f:
            return str(json.load(f).get("baglam") or "")
    except Exception:
        return ""


def subagent_stop(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    aid = inp.get("agent_id") or "?"
    try:
        os.remove(os.path.join(sd, "oturumlar", f"acik_ajan_{aid}.json"))
    except OSError:
        pass
    tp = inp.get("agent_transcript_path") or transkript_bul(inp.get("transcript_path", ""), inp.get("session_id", ""), aid)
    ozet = L.transkript_oku(tp)
    meta = L.alt_ajan_meta(tp)
    atip = inp.get("agent_type") or meta.get("agentType") or "?"
    gorev, surec, _var = transkript_etiketleri(tp)
    try:
        esleme = B.esleme_oku(sd)
        baglam = B.coz(esleme, L.proje_dizini(inp.get("cwd")), ozet["dokunulan"], ozet["okunan"]) if esleme else ""
        if esleme and not baglam:
            baglam = _oturum_baglami(sd, inp.get("session_id"))
    except Exception:
        baglam = ""
    if surec == "bilinmiyor":
        surec = "denetim" if "denetci" in atip else ("arastirma" if atip in ("Explore", "orkestra:arastirmaci") else
                                                      "perspektif" if ("perspektif" in atip or "ruya" in atip) else "is" if "isci" in atip else "bilinmiyor")
    # Sayaç modülünün (maliyet tur) aynı ajanı görev/süreç/tip ile eşleyebilmesi için önbellek.
    if gorev != "-":
        L.atomik_yaz(os.path.join(sd, "oturumlar", f"ajan_{aid}.json"), json.dumps({"gorev": gorev, "surec": surec, "ajan": atip, "baglam": baglam}))
    taban = {"zaman": L.simdi(), "oturum": inp.get("session_id"), "gorev": gorev, "surec": surec, "baglam": baglam, "ajan": atip,
             "agent_id": aid, "sure_ms": L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"]), "tur": ozet["tur"],
             "arac_cagrisi": ozet["arac_cagrisi"], "perspektif": bool(os.environ.get("ORKESTRA_PERSPEKTIF")), "kaynak": "hook"}
    _maliyet_satirlari(sd, ozet, taban)
    ana_model = max(ozet["modeller"].items(), key=lambda x: x[1]["maliyet_usd"])[0] if ozet["modeller"] else "-"
    ilk = re.sub(r"#(GOREV|SUREC):\S+", "", ozet["ilk_kullanici"] or "").strip().replace("\n", " ")
    L.defter_ekle(sd, {"oturum": inp.get("session_id"), "gorev": gorev, "surec": surec, "baglam": baglam, "ajan": atip, "agent_id": aid, "model": ana_model,
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
    if not os.environ.get("ORKESTRA_PERSPEKTIF"):
        import niyet
        niyet.olay(oid, L.proje_dizini(inp.get("cwd")), "tur")  # Claude turu bitirdi → kullanıcıyı bekliyor
    ofset_yolu = os.path.join(sd, "oturumlar", f"{oid}.json")
    try:
        with open(ofset_yolu, encoding="utf-8") as f:
            onceki = json.load(f)
        ofset = onceki.get("ofset", 0)
        onceki_baglam = str(onceki.get("baglam") or "")
    except Exception:
        ofset, onceki_baglam = 0, ""
    ozet = L.transkript_oku(inp.get("transcript_path"), ofset, yan_zincir=False)
    baglam = ""
    try:
        esleme = B.esleme_oku(sd)
        if esleme:
            baglam = B.coz(esleme, L.proje_dizini(inp.get("cwd")), ozet["dokunulan"], ozet["okunan"]) or onceki_baglam
            if not baglam:
                import niyet
                baglam = niyet.son_baglam(oid)
    except Exception:
        baglam = ""
    L.atomik_yaz(ofset_yolu, json.dumps({"ofset": ozet["ofset"], "baglam": baglam, "guncelleme": L.simdi()}))
    perspektif = bool(os.environ.get("ORKESTRA_PERSPEKTIF"))
    ajan = "perspektif-bakimcisi" if perspektif else "ana-ajan"
    surec = "perspektif" if perspektif else "orkestrasyon"
    if ozet["modeller"]:
        taban = {"zaman": L.simdi(), "oturum": oid, "gorev": "-", "surec": surec, "baglam": baglam, "ajan": ajan, "agent_id": None,
                 "sure_ms": L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"]), "tur": ozet["tur"],
                 "arac_cagrisi": ozet["arac_cagrisi"], "perspektif": perspektif, "kaynak": "hook"}
        _maliyet_satirlari(sd, ozet, taban)
    kayda_deger = any(a in ozet["araclar"] for a in ("Agent", "Task", "Workflow")) or ozet["dokunulan"]
    if kayda_deger and ozet["modeller"]:
        araclar = ", ".join(f"{k}×{v}" for k, v in sorted(ozet["araclar"].items(), key=lambda x: -x[1])[:6])
        L.defter_ekle(sd, {"oturum": inp.get("session_id"), "gorev": "-", "surec": surec, "baglam": baglam, "ajan": ajan, "model": max(ozet["modeller"].items(), key=lambda x: x[1]["maliyet_usd"])[0],
                           "yaptim": f"Tur: {ozet['arac_cagrisi']} araç çağrısı ({araclar})",
                           "sonuc": (inp.get("last_assistant_message") or "")[:400], "dokunulan": ozet["dokunulan"],
                           "token": ozet["toplam"], "kaynak": "hook"})
    # Bitiş kapısı: bu oturumun açık kartları
    if perspektif or inp.get("background_tasks"):
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

def asili_uyari(sd: str) -> str:
    """Bitmeyen alt ajan varsa tek satırlık uyarı, yoksa boş metin (hatada sessiz)."""
    try:
        import ozet
        a = ozet.asili_ajanlar(sd)
    except Exception:
        return ""
    if not a:
        return ""
    liste = "; ".join(f"{x['ajan']} {x['gorev']} ({x['dakika']} dk)" for x in a[:5])
    return (f"Orkestra: {ozet.ASILI_AJAN_DK} dakikadır bitmeyen ajan(lar): {liste}; "
            "takıldıysa TaskStop ile durdur ya da kartı beklemede yap.")


def session_start(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    import perspektif
    perspektif.oturum_say(sd, inp.get("source"))
    ks = [k for k in L.kartlar(sd) if L.kart_durumu_hesapla(k) in L.ACIK_DURUMLAR + ("beklemede",)]
    satirlar = ["Orkestra bu projede açık. Ana ajan: planla → `orkestra kart` ile kartla → işçi + AYRI denetçiyle dağıt "
                "(`/orkestra:is`) → onaylıyı `orkestra kart teslim` ile topla. Ortak defter: `orkestra defter baglam <id>`."]
    if ks:
        satirlar.append("Açık/bekleyen kartlar: " + "; ".join(f"{k['id']} [{L.kart_durumu_hesapla(k)}] {k['baslik'][:40]}" for k in ks[:8]))
    try:  # önbellek bayatlığı: hızlı, hatada sessiz
        b = L.bayatlik()
        if b:
            cs = {True: "kaynakta commitlenmemiş değişiklik var", False: "kaynakta commitlenmemiş değişiklik yok", None: "kaynak git durumu okunamadı"}[b["kaynakta_commitsiz"]]
            satirlar.append(f"UYARI: çalışan orkestra kopyası kaynaktan {b['farkli']} dosya farklı ({cs}). "
                            "Commitle → otomatik güncelleme; hemen için `orkestra guncelle`, sonra yeni oturum ya da /reload-plugins.")
    except Exception:
        pass
    r = perspektif.durum(sd)
    if r.get("okunmamis_rapor"):
        satirlar.append(f"Perspektif raporu hazır: {r['okunmamis_rapor']} — öneriler panelde Onaylar sayfasında; "
                        "kullanıcı orada onaylayabilir ya da /orkestra:perspektif ile sohbette ilerleyebilir.")
    elif r.get("zamani_geldi") and not r.get("calisiyor"):
        hafiza = perspektif.hafiza_dizini(L.proje_dizini(inp.get("cwd")), inp.get("transcript_path"))
        satirlar.append("PERSPEKTİF ZAMANI: kullanıcının ilk isteğini yanıtlarken AYNI mesajda, kullanıcıyı bölmeden, Agent aracıyla "
                        "`orkestra:perspektif-ajani` ajanını run_in_background: true ile başlat; istem: "
                        f"`#SUREC:perspektif hafıza klasörü: {hafiza}`. Kullanıcıya yalnız tek satırla bildir.")
    uyari = asili_uyari(sd)
    if uyari:
        satirlar.append(uyari)
    om = ""
    try:  # panel onay kararları: hata hook'u düşürmez
        import onay
        om = onay.baglam_metni(sd, inp.get("session_id"), "SessionStart") or ""
    except Exception:
        pass
    ek = "\n".join(satirlar)[:1800 - len(om) - 1] + "\n" + om if om else "\n".join(satirlar)[:1800]  # onay yönlendirmesi kesilmesin
    L.hook_cikti({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ek}})


def user_prompt_submit(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if sd and not os.environ.get("ORKESTRA_PERSPEKTIF"):
        metin = L.maskele(inp.get("prompt") or "")
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": inp.get("session_id"), "tur": "istek",
                                                         "metin": metin[:300], "uzunluk": len(metin)})
        # Niyet kaydı: kullanıcı yazdı → Claude çalışıyor. Sistem iletileri (<agent-message>, <task-notification>) istek metni sayılmaz.
        import niyet
        sistem = metin.lstrip().startswith("<")
        niyet.olay(inp.get("session_id"), L.proje_dizini(inp.get("cwd")), "istek", metin=None if sistem else metin[:200])
        if not sistem:
            parcalar = [niyet.baglam_metni(inp.get("session_id")), asili_uyari(sd)]
            try:  # panel onay kararları: hata hook'u düşürmez
                import onay
                om = onay.baglam_metni(sd, inp.get("session_id"), "UserPromptSubmit")
                if om:
                    parcalar.append(om)
            except Exception:
                pass
            L.hook_cikti({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": "\n".join(p for p in parcalar if p)}})
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
    if not sd or os.environ.get("ORKESTRA_PERSPEKTIF"):
        gec()
    import niyet
    niyet.olay(inp.get("session_id"), L.proje_dizini(inp.get("cwd")), "kapandi")
    import perspektif
    if perspektif.durum(sd).get("zamani_geldi"):
        perspektif.baslat(sd, L.proje_dizini(inp.get("cwd")), transkript=inp.get("transcript_path"))
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
