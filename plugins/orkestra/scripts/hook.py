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
YAZAN_ALT_KOMUT = re.compile(r"\b(kart\s+(yeni|toplu|durum|denetim|yukselt|teslim|agac|birlestir|test-kos|test-kilit-ac|test-ayar|butce)|defter\s+ekle|baslat|(?:perspektif|ruya)\s+(basla|basladi|bitti|kaydet|girdi))\b")
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
        if (k.get("test_kilidi") or {}).get("yesilde"):
            continue  # TDD'siz kart: testler işçinin, kilit yalnız onay kanıtı
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
    kilit = {_anahtar(y): (y, gid) for y, gid in kilitli_testler(sd, [k for k in ks if not k.get("test_koku")]).items()}
    if kilit:
        for a in sorted(paylasilan_goreli(proje, tam, ks)):
            if a in kilit:
                return kilit[a]
    # test_koku'lu kartların kilitleri kendi test köklerine göredir (proje dışı olabilir): kök başına aynı sorgu.
    gruplar: dict[str, list[dict]] = {}
    for k in ks:
        if k.get("test_koku"):
            gruplar.setdefault(L.kart_test_koku(proje, k), []).append(k)
    for taban in sorted(gruplar):
        kilit = {_anahtar(y): (taban.replace("\\", "/").rstrip("/") + "/" + y, gid)
                 for y, gid in kilitli_testler(sd, gruplar[taban]).items()}
        if not kilit:
            continue
        for a in sorted(paylasilan_goreli(taban, tam, ks)):
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


_KABUK_YAZMA_ON = re.compile(_KABUK_YAZMA_ISLEC + r"|open\(", re.I)


def kabuk_kilitli_yazma(komut: str, kilitli: dict[str, str]) -> str | None:
    """Kabuk komutu kilitli bir test dosyasını yazma işlecinin HEDEFİ yapıyorsa kart kimliğini döndürür (en iyi çaba).
    Yakalanamayanlar (değişken/dolaylı yol, betik içi yazma) `kart test-kos yesil` hash denetimine kalır."""
    dusuk = komut.lower()
    for rel, gid in kilitli.items():
        # Ön süzme: ne yol ne dosya adı komutta geçiyorsa regex derlemeye gerek yok (her Bash çağrısında yüzlerce derleme).
        if rel.lower() not in dusuk and os.path.basename(rel).lower() not in dusuk:
            continue
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
                # test_alani test köküne (test_koku, yoksa proje) göredir; kart ağacındaki yazım paylaşılan depodaki
                # karşılığı üzerinden okunur.
                tkok = L.kart_test_koku(proje, k) if k and k.get("test_koku") else proje
                ttrel = trel if tkok == proje else _rel(tkok, tam)
                if agacta:
                    es = L.agac_esdegeri(k, tam)
                    ttrel = _rel(tkok, es) if es is not None else None
                if k and k.get("sinif") == "kod" and k.get("test_alani") and ttrel is not None:
                    icinde = test_alaninda_mi(ttrel, k["test_alani"])
                    if surec == "test-yaz":
                        if not icinde:
                            reddet(f"{gorev}: #SUREC:test-yaz yalnız test_alani içine yazar ({', '.join(k['test_alani'])}).")
                        gec()
                    elif icinde and k.get("tdd") is not False:  # TDD'siz kartta testleri işçi yazar
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
        # Kilitli test denetimi yalnız yazma işleci içeren komutta anlamlı; yalnız-okuma komutunda kartları (125 JSON) okuma.
        kgid = kabuk_kilitli_yazma(komut, kilitli_testler(sd)) if _KABUK_YAZMA_ON.search(komut) else None
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


def _oturum_isi(sd: str, oid: str | None):
    try:
        with open(os.path.join(sd, "oturumlar", f"{oid}.json"), encoding="utf-8") as f:
            d = json.load(f)
        v = d.get("is") if isinstance(d, dict) else None
        return str(v) if v else None
    except Exception:
        return None


def _kart_isi(sd: str, gorev: str):
    try:
        if gorev and gorev != "-":
            k = L.kart_oku(sd, gorev)
            v = k.get("is") if isinstance(k, dict) else None
            return str(v) if v else None
    except Exception:
        pass
    return None


def _zaman_ekle(sd: str, kayit: dict) -> None:
    """zaman.jsonl'e tek satır (T-06); hata kancayı düşürmez."""
    try:
        L.jsonl_ekle(os.path.join(sd, "zaman.jsonl"), kayit)
    except Exception:
        pass


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
             "arac_cagrisi": ozet["arac_cagrisi"], "perspektif": bool(os.environ.get("ORKESTRA_PERSPEKTIF")), "kaynak": "hook",
             "araclar": dict(ozet["araclar"]), "arac_hata": ozet["arac_sayilari"]["arac_hata"],
             "tekrar_okuma": ozet["arac_sayilari"]["tekrar_okuma"],
             "is": _kart_isi(sd, gorev) or _oturum_isi(sd, inp.get("session_id"))}
    _maliyet_satirlari(sd, ozet, taban)
    _zaman_ekle(sd, {"zaman": L.simdi(), "oturum": inp.get("session_id"), "is": taban["is"], "tur": "alt", "agent_id": aid,
                     "ajan": atip, "gorev": gorev, "sure_ms": taban["sure_ms"]})
    ana_model = max(ozet["modeller"].items(), key=lambda x: x[1]["maliyet_usd"])[0] if ozet["modeller"] else "-"
    ilk = re.sub(r"#(GOREV|SUREC):\S+", "", ozet["ilk_kullanici"] or "").strip().replace("\n", " ")
    L.defter_ekle(sd, {"oturum": inp.get("session_id"), "gorev": gorev, "surec": surec, "baglam": baglam, "ajan": atip, "agent_id": aid, "model": ana_model,
                       "yaptim": meta.get("description") or ilk[:200], "sonuc": (inp.get("last_assistant_message") or "")[:600],
                       "dokunulan": ozet["dokunulan"], "token": ozet["toplam"], "kaynak": "hook"})
    try:
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
    except Exception:  # bozuk kart dosyası kancayı düşürmesin
        pass
    gec()


# ---------------------------------------------------------------- Stop (ana ajan)

_BILDIRIM_ID = re.compile(r"<tool-use-id>\s*([^<\s]+)\s*</tool-use-id>")
_BILDIRIM_BITTI = re.compile(r"<status>\s*(?:completed|failed|killed|stopped)\s*</status>")
ACIK_GOREV_AZAMI = 50


def _acik_arka_plan(yol, ofset, bitis, onceki) -> list:
    """Transkriptin [ofset, bitis) aralığındaki arka plan görevlerini önceki açık listeye işler; bildirimi gelmemiş araç kimlikleri döner."""
    acik = [str(x) for x in onceki] if isinstance(onceki, list) else []
    try:
        if not yol or not os.path.exists(yol) or bitis <= ofset:
            return acik
        with open(yol, "rb") as f:
            f.seek(ofset)
            veri = f.read(bitis - ofset)
        for ham in veri.splitlines():
            try:
                o = json.loads(ham.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if not isinstance(o, dict) or o.get("isSidechain"):
                continue
            icerik = (o.get("message") or {}).get("content")
            if o.get("type") == "assistant" and isinstance(icerik, list):
                for b in icerik:
                    if (isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in ("Agent", "Bash")
                            and isinstance(b.get("input"), dict) and b["input"].get("run_in_background") is True
                            and b.get("id") and b["id"] not in acik):
                        acik.append(b["id"])
            elif o.get("type") == "user":
                metin = icerik if isinstance(icerik, str) else json.dumps(icerik, ensure_ascii=False)
                if "<task-notification>" in metin and _BILDIRIM_BITTI.search(metin):
                    for kimlik in _BILDIRIM_ID.findall(metin):
                        if kimlik in acik:
                            acik.remove(kimlik)
    except Exception:
        pass
    return acik[-ACIK_GOREV_AZAMI:]


def _is_surekliligi(sd: str, oid: str, ofset_yolu: str, ozet: dict, kayda_deger: bool, inp: dict) -> str:
    """(D1) bağlı işin oturumlar.md'sine tur satırı; (D2) oturum başına en çok bir bloklamayan hatırlatma.

    Dönüş: hatırlatma metni ya da boş. Bu fonksiyon istisna fırlatabilir; çağıran yakalar."""
    import datetime
    import is_kaydi
    if not kayda_deger:
        return ""
    try:
        with open(ofset_yolu, encoding="utf-8") as f:
            o = json.load(f)
        if not isinstance(o, dict):
            o = {}
    except Exception:
        o = {}
    is_id = o.get("is")
    if not is_id:  # eski yan dosya yalnız okunur
        try:
            with open(os.path.join(sd, "oturumlar", f"is_{oid}.json"), encoding="utf-8") as f:
                y = json.load(f)
            is_id = y.get("is") if isinstance(y, dict) else None
        except Exception:
            is_id = None
    klasor = None
    if is_id:
        try:
            klasor = next((g.get("klasor") for g in is_kaydi.is_liste(sd) if g.get("id") == is_id), None)
        except Exception:
            klasor = None
    # (D1) oturum satırı
    if klasor and ozet["modeller"] and os.path.isdir(klasor):
        try:
            yol = os.path.join(klasor, "oturumlar.md")
            nerede = " ".join(str(inp.get("last_assistant_message") or "").split())[:150]
            satir = (f"- {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} · {oid[:8]} · {ozet['arac_cagrisi']} araç · "
                     f"${ozet['toplam']['maliyet_usd']:.2f} · nerede kalındı: {nerede}\n")
            with L.kilit(yol):
                bas = ""
                if os.path.exists(yol) and os.path.getsize(yol) > 0:
                    with open(yol, "rb") as f:
                        f.seek(-1, 2)
                        if f.read(1) != b"\n":
                            bas = "\n"
                with open(yol, "a", encoding="utf-8", newline="\n") as f:
                    f.write(bas + satir)
        except Exception:
            pass
    # (D2) hatırlatma: oturum başına en çok bir kez
    if o.get("is_hatirlatma"):
        return ""
    msg = ""
    if not is_id:
        msg = ("Orkestra: bu sohbet bir işe bağlı değil; sıradaki işler kaybolmasın diye `orkestra is devam <id>` ya da "
               "`orkestra is ac` ile bağla ve adımları `orkestra is todo <id> --ekle` ile yaz.")
    elif klasor:
        try:
            baglanma = datetime.datetime.fromisoformat(str(o.get("is_baglanma"))).timestamp()
        except Exception:
            baglanma = None
        if baglanma is not None:
            try:
                mt = os.path.getmtime(os.path.join(klasor, "todo.md"))
            except OSError:
                mt = 0.0
            if mt < baglanma:
                msg = (f"Orkestra: {is_id} todo.md bu oturumda güncellenmedi; sıradaki adımları "
                       "`orkestra is todo <id> --ekle` ile yaz, bitenleri `--bitti` ile kapat.")
    if inp.get("background_tasks"):
        return ""  # kapı geçilecek; hak harcanmasın
    with L.kilit(ofset_yolu):
        try:
            with open(ofset_yolu, encoding="utf-8") as f:
                yeni = json.load(f)
            if not isinstance(yeni, dict):
                yeni = {}
        except Exception:
            yeni = {}
        yeni["is_hatirlatma"] = True
        L.atomik_yaz(ofset_yolu, json.dumps(yeni))
    return msg


def _bayat_todo_uyarisi(sd: str, is_id) -> str:
    """Bağlı işin açık todo maddesinde anılan G-NNN kartı teslim/iptal ise TEK satırlık uyarı, yoksa boş metin."""
    if not is_id:
        return ""
    import is_kaydi
    b = is_kaydi.todo_bitmis_kartli(sd, is_id)
    if not b:
        return ""
    liste = ", ".join(f"{n}. madde {g} ({d})" for n, g, d in b[:4])
    return (f"Orkestra: {is_id} todo'sunda açık ama kartı bitmiş: {liste} — "
            f"`orkestra is todo {is_id} --bitti <n>`.")


def stop(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    oid = inp.get("session_id") or "-"
    ofset_yolu = os.path.join(sd, "oturumlar", f"{oid}.json")
    try:
        with open(ofset_yolu, encoding="utf-8") as f:
            onceki = json.load(f)
        if not isinstance(onceki, dict):
            onceki = {}
    except Exception:
        onceki = {}
    ofset = onceki.get("ofset", 0) if isinstance(onceki.get("ofset"), int) else 0
    onceki_baglam = str(onceki.get("baglam") or "")
    try:
        ozet = L.transkript_oku(inp.get("transcript_path"), ofset, yan_zincir=False)
    except Exception:  # okunamayan transkript kancayı düşürmesin; ofset ilerlemez
        ozet = {"modeller": {}, "toplam": {"giris": 0, "cikis": 0, "onbellek_okuma": 0, "onbellek_yazma": 0, "maliyet_usd": 0.0},
                "ilk_kullanici": None, "tur": 0, "arac_cagrisi": 0, "araclar": {}, "dokunulan": [], "okunan": [],
                "ilk_zaman": None, "son_zaman": None, "ofset": ofset}
    acik_gorevler = _acik_arka_plan(inp.get("transcript_path"), ofset, ozet["ofset"], onceki.get("acik_gorevler"))
    if not os.environ.get("ORKESTRA_PERSPEKTIF"):
        import niyet
        # Claude turu bitirdi → kullanıcıyı bekliyor (arka plan görevi açıksa bunu da işaretle)
        try:  # kullanıcıdan ne beklendiği (panelde "Seni bekliyor" kartında gösterilir)
            bekleme = niyet.bekleme_nedeni(inp.get("transcript_path"), ofset, inp.get("last_assistant_message"))
        except Exception:
            bekleme = None
        # neden çıkarılamadıysa (soru/karar yok) panel 'Seni bekliyor' yerine nötr durum gösterir (G-095)
        niyet.olay(oid, L.proje_dizini(inp.get("cwd")), "tur", arka_plan=True if acik_gorevler else None, bekleme=bekleme,
                   bekleme_yok=True if bekleme == "" else None)
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
    with L.kilit(ofset_yolu):  # oku-birleştir-yaz kilitli (iş bağıyla kayıp güncelleme yarışı olmasın)
        try:
            with open(ofset_yolu, encoding="utf-8") as f:
                yeni = json.load(f)
            if not isinstance(yeni, dict):
                yeni = {}
        except Exception:
            yeni = {}
        yeni.update({"ofset": ozet["ofset"], "baglam": baglam, "guncelleme": L.simdi()})
        if acik_gorevler:
            yeni["acik_gorevler"] = acik_gorevler
        else:
            yeni.pop("acik_gorevler", None)
        L.atomik_yaz(ofset_yolu, json.dumps(yeni))
    perspektif = bool(os.environ.get("ORKESTRA_PERSPEKTIF"))
    if not perspektif and ozet.get("ilk_zaman"):
        _zaman_ekle(sd, {"zaman": L.simdi(), "oturum": oid, "is": _oturum_isi(sd, oid), "tur": "ana",
                         "sure_ms": L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"]), "istek_zamani": ozet["ilk_zaman"]})
    ajan = "perspektif-bakimcisi" if perspektif else "ana-ajan"
    surec = "perspektif" if perspektif else "orkestrasyon"
    if ozet["modeller"]:
        taban = {"zaman": L.simdi(), "oturum": oid, "gorev": "-", "surec": surec, "baglam": baglam, "ajan": ajan, "agent_id": None,
                 "sure_ms": L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"]), "tur": ozet["tur"],
                 "arac_cagrisi": ozet["arac_cagrisi"], "perspektif": perspektif, "kaynak": "hook",
                 "is": _oturum_isi(sd, oid)}
        _maliyet_satirlari(sd, ozet, taban)
    kayda_deger = any(a in ozet["araclar"] for a in ("Agent", "Task", "Workflow")) or ozet["dokunulan"]
    if kayda_deger and ozet["modeller"]:
        araclar = ", ".join(f"{k}×{v}" for k, v in sorted(ozet["araclar"].items(), key=lambda x: -x[1])[:6])
        L.defter_ekle(sd, {"oturum": inp.get("session_id"), "gorev": "-", "surec": surec, "baglam": baglam, "ajan": ajan, "model": max(ozet["modeller"].items(), key=lambda x: x[1]["maliyet_usd"])[0],
                           "yaptim": f"Tur: {ozet['arac_cagrisi']} araç çağrısı ({araclar})",
                           "sonuc": (inp.get("last_assistant_message") or "")[:400], "dokunulan": ozet["dokunulan"],
                           "token": ozet["toplam"], "kaynak": "hook"})
    hatirlatma = ""
    if not perspektif:
        try:
            hatirlatma = _is_surekliligi(sd, oid, ofset_yolu, ozet, bool(kayda_deger), inp)
        except Exception:
            hatirlatma = ""
    if not perspektif:
        try:  # bayat todo: açık maddede anılan kart bitmiş (tek satır)
            u = _bayat_todo_uyarisi(sd, _oturum_isi(sd, oid))
            if u:
                hatirlatma = (hatirlatma + " " + u).strip()
        except Exception:
            pass
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
        try:  # insan aksiyonu: tur bitti → toast (sessiz hata)
            import bildirim
            bildirim.tur_bitti(sd, oid, L.sure_ms(ozet.get("ilk_zaman"), ozet.get("son_zaman")), inp.get("last_assistant_message") or "")
        except Exception:
            pass
        if hatirlatma:
            L.hook_cikti({"systemMessage": hatirlatma})
        gec()
    liste = "; ".join(f"{g} [{d}] {b[:50]}" for g, d, b in acik)
    ek = f" {hatirlatma}" if hatirlatma else ""
    if inp.get("stop_hook_active"):
        L.hook_cikti({"systemMessage": f"Orkestra: açık kartlar kaldı → {liste}{ek}"})
    L.hook_cikti({"decision": "block", "reason":
                  f"Orkestra bitiş kapısı: bu oturumun açık kartları var → {liste}. "
                  "onaylandi → sonucu topla ve `orkestra kart teslim <id>`; denetimde → ayrı denetçiyi çalıştır; "
                  "reddedildi → düzeltme/yükseltme yap; bilerek bırakıyorsan `orkestra kart durum <id> beklemede --not \"neden\"`." + ek})


# ---------------------------------------------------------------- diğer olaylar

def asili_uyari(sd: str, oturum: str | None = None) -> str:
    """Bitmeyen alt ajan varsa tek satırlık uyarı, yoksa boş metin (hatada sessiz).
    `oturum` verilirse yalnız o oturumun kayıtları sayılır."""
    try:
        import ozet
        a = ozet.asili_ajanlar(sd, oturum=oturum)
    except Exception:
        return ""
    if not a:
        return ""
    liste = "; ".join(f"{x['ajan']} {x['gorev']} ({x['dakika']} dk"
                      + (f", {x['sessiz_dk']} dk sessiz" if x.get("sessiz_dk") is not None else "") + ")" for x in a[:5])
    return (f"Orkestra: {ozet.ASILI_AJAN_DK} dk'dır bitmeyen ajan(lar): {liste}; "
            "takıldıysa TaskStop ya da kartı beklemede yap.")


def _son_dokunus(g: dict) -> str | None:
    """is.json/oturumlar.md son değişim ile kayıttaki güncelleme alanından en yenisi (ISO)."""
    import datetime as _dt
    adaylar = []
    klasor = g.get("klasor") or ""
    for ad in ("is.json", "oturumlar.md"):
        try:
            adaylar.append(_dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(klasor, ad))).astimezone())
        except Exception:
            pass
    try:
        gu = _dt.datetime.fromisoformat(str(g.get("guncelleme")).replace("Z", "+00:00"))
        adaylar.append(gu if gu.tzinfo else gu.astimezone())
    except Exception:
        pass
    return max(adaylar).isoformat() if adaylar else None


def _kapanis_notlari(sd: str, liste: list) -> dict:
    """{is_id: ' · kapatılabilir: ...' | ' · bayat'}; hatada boş (satırlar değişmez)."""
    try:
        import datetime as _dt
        import is_kaydi
        import is_yonlendirme
        acik_kart = {}
        for k in L.kartlar(sd):
            try:
                if L.kart_durumu_hesapla(k) in L.ACIK_DURUMLAR + ("beklemede",) and k.get("is"):
                    acik_kart[str(k["is"])] = acik_kart.get(str(k["is"]), 0) + 1
            except Exception:
                continue
        ozetler = []
        for g in liste:
            try:
                t = is_kaydi.todo_ozet(g.get("klasor") or "")
                ozetler.append({"id": g["id"], "toplam": t["toplam"], "biten": t["biten"],
                                "acik_kart": acik_kart.get(str(g["id"]), 0), "son_dokunus": _son_dokunus(g)})
            except Exception:
                continue
        a = is_yonlendirme.kapanis_adaylari(ozetler, _dt.datetime.now().astimezone())
        notlar = {}
        for i in a.get("kapat", []):
            try:
                is_kaydi.is_durum(sd, i, "kapandi")
                notlar[i] = " · otomatik kapandı"
            except Exception:
                notlar[i] = f" · kapatılabilir: orkestra is kapat {i}"
        notlar.update({i: " · bayat" for i in a.get("bayat", [])})
        return notlar
    except Exception:
        return {}


def _yonlendirme_ipucu(sd: str, oid, istek: str) -> str:
    """Bağlı işi olmayan/konu dışı istekte tek satırlık yönlendirme; oturumda aynı (tur,iş) bir kez. Hatada boş."""
    try:
        import is_kaydi
        import is_yonlendirme
        isler = []
        for g in is_kaydi.is_liste(sd, "acik"):
            try:
                klasor = g.get("klasor") or ""
                try:
                    todolar = is_kaydi.todo_ozet(klasor)["acik_maddeler"]
                except Exception:
                    todolar = []
                isler.append({"id": g["id"], "baslik": g.get("baslik") or "",
                              "klasor_adi": os.path.basename(klasor.rstrip("/\\")), "acik_todolar": todolar})
            except Exception:
                continue
        k = is_yonlendirme.yonlendir(istek, isler, _oturum_isi(sd, oid))
        if not k:
            return ""
        anahtar = f"{k['tur']}:{k.get('is')}"
        yol = os.path.join(sd, "oturumlar", f"yonlendirme_{oid}.json")
        gorulen = []
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            gorulen = [str(x) for x in d.get("gorulen", [])] if isinstance(d, dict) else []
        except Exception:
            pass
        if anahtar in gorulen:
            return ""
        gorulen.append(anahtar)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"gorulen": gorulen[-20:]}, f)
        return k["satir"]
    except Exception:
        return ""


def _acik_isler_satirlari(sd: str, bagli: str | None = None) -> list[str]:
    """Açık iş satırları. Oturum bir işe bağlıysa (`bagli`) yalnız o işin satırı uzun (başlık 40, son satır 80);
    diğerleri kısa (kimlik + başlık 24 + todo + not), ayrıntı `orkestra is goster <id>`. Bağsız oturumda hepsi uzun."""
    import is_kaydi
    parcalar = []
    liste = is_kaydi.is_liste(sd, "acik")[:5]
    notlar = _kapanis_notlari(sd, liste)
    if bagli:  # bağlı iş öne
        liste = sorted(liste, key=lambda g: str(g.get("id")) != str(bagli))
    for g in liste:
        try:
            uzun = not bagli or str(g.get("id")) == str(bagli)
            p = f"{g['id']} {str(g.get('baslik') or '')[:40 if uzun else 24]}"
            klasor = g.get("klasor") or ""
            try:
                t = is_kaydi.todo_ozet(klasor)
                p += f" todo {t['biten']}/{t['toplam']}"
            except Exception:
                pass
            if not uzun:
                p += notlar.get(g["id"], "")
                parcalar.append(p)
                continue
            try:
                with open(os.path.join(klasor, "oturumlar.md"), encoding="utf-8", errors="replace") as f:
                    dolu = [x.rstrip() for x in f if x.strip() and not x.lstrip().startswith("#")]  # başlık satırı sayılmaz
                if dolu:
                    p += f" · son: {dolu[-1][:80]}"
            except Exception:
                pass
            p += notlar.get(g["id"], "")
            parcalar.append(p)
        except Exception:
            continue
    if not parcalar:
        return []
    return ["Açık işler: " + " ; ".join(parcalar),
            "Devam için `orkestra is devam <id>`; adımlar: `orkestra is todo <id> --ekle` (todo.md)."]


PANEL_GIRDI = "orkestra-panel"   # çalışma alanının .claude/launch.json'ındaki girdi adı
PANEL_VARSAYILAN_PORT = 8765     # panel.py baslat() varsayılanı


def _panel_girdisi(sd: str) -> dict | None:
    """Çalışma alanının <proje>/.claude/launch.json'ında name='orkestra-panel' girdisi; yoksa/bozuksa None."""
    try:
        with open(os.path.join(os.path.dirname(sd), "launch.json"), encoding="utf-8-sig") as f:
            d = json.load(f)
    except Exception:
        return None
    girdiler = d.get("configurations") if isinstance(d, dict) else None
    for g in girdiler if isinstance(girdiler, list) else []:
        if isinstance(g, dict) and g.get("name") == PANEL_GIRDI:
            return g
    return None


def _panel_durumu() -> tuple[int | None, bool]:
    """(panel.json'daki port, sunucu dinliyor mu). panel.json yoksa/bozuksa (None, False): kapalı sayılır.
    Dinleme 127.0.0.1:port'a en çok 0.3 sn'lik TCP denemesiyle anlaşılır (HTTP isteği yapılmaz)."""
    try:
        with open(os.path.join(L.GENEL_DIZIN, "panel.json"), encoding="utf-8-sig") as f:
            port = int(json.load(f)["port"])
    except Exception:
        return None, False
    if not 0 < port < 65536:
        return None, False
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return port, s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return port, False


def _panel_ac_satiri(sd: str, oid) -> str:
    """launch.json'da 'orkestra-panel' girdisi varsa oturumda BİR KEZ: ana ajana paneli Claude masaüstü uygulamasının
    tarayıcı panelinde açtıran satır. Bir kez durumu <sd>/oturumlar/panel_ac_<oid>.json. Hatada boş metin.
    preview_start localhost url'sinde yol kabul etmez: launch.json url'si yalnız origin, /isler'e navigate ile gidilir."""
    try:
        g = _panel_girdisi(sd)
        if not g:
            return ""
        yol = None
        if oid:
            guvenli = re.sub(r"[^A-Za-z0-9_.-]", "_", str(oid))[:120]
            yol = os.path.join(sd, "oturumlar", f"panel_ac_{guvenli}.json")
            if os.path.exists(yol):
                return ""
        port, acik = _panel_durumu()
        if not port:
            try:
                import urllib.parse
                port = urllib.parse.urlsplit(str(g.get("url") or "")).port
            except ValueError:
                port = None
        adres = f"http://127.0.0.1:{port or PANEL_VARSAYILAN_PORT}/isler"
        on = "" if acik else "sunucu kapalı, önce `orkestra panel` çalıştır (başka port verirse onu kullan); sonra "
        satir = (f"PANEL: ilk turda Claude masaüstü uygulamasının tarayıcı panelinde orkestra panelini aç: {on}"
                 f"preview_start (name: {PANEL_GIRDI}), ardından navigate ile {adres}. "
                 "Oturumda bir kez; araç yoksa atla, kullanıcıya en çok tek satırla bildir.")
        if yol:
            try:
                L.atomik_yaz(yol, json.dumps({"zaman": L.simdi(), "oturum": str(oid), "adres": adres, "sunucu_acik": acik}))
            except Exception:
                pass
        return satir
    except Exception:
        return ""


def _kurallar_satiri() -> str:
    """Genel orkestra kurallarının (KURALLAR.md) mutlak yolu; hook.py konumundan türetilir, dosya yoksa boş."""
    yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "KURALLAR.md")
    return f"Orkestra kuralları: {yol} (orkestra işinden önce oku)." if os.path.isfile(yol) else ""


def _kart_satiri(ks: list) -> str:
    """Açık kartlar kimlik+durum+kısa başlık (24); beklemedekiler yalnız kimlik. Ayrıntı: `orkestra kart liste`."""
    aktif = [k for k in ks if L.kart_durumu_hesapla(k) != "beklemede"]
    bekl = [k for k in ks if L.kart_durumu_hesapla(k) == "beklemede"]
    s = "Açık/bekleyen kartlar: " + "; ".join(f"{k['id']} [{L.kart_durumu_hesapla(k)}] {k['baslik'][:24]}" for k in aktif[:6])
    if bekl:
        s += (" · " if aktif else "") + f"beklemede {len(bekl)}: " + ",".join(str(k["id"]) for k in bekl[:8])
    if len(aktif) > 6:
        s += f" · +{len(aktif) - 6} kart daha"
    return s + " (`orkestra kart liste`)"


def _niyet_metni(oturum: str | None) -> str:
    """UserPromptSubmit niyet hatırlatması (niyet.baglam_metni'nin kısa eşi; aynı yönerge)."""
    import niyet
    k = niyet.son_niyet(oturum) if oturum else None
    kayitli = (f"Kayıtlı niyet: ne=\"{k.get('ne', '')}\" · neden=\"{k.get('neden', '')}\"" if k and k.get("tur") == "niyet"
               else "Bu sohbet için kayıtlı niyet yok.")
    return ("Orkestra niyet: " + kayitli + " Yeni iş/iş değişimiyse ilk araç çağrınla bir kez: "
            "`orkestra niyet --ne \"<≤12 kelime>\" --neden \"<hangi hedefe hizmet; ≤15 kelime>\" [--baglam \"<Proje/Süreç/Görev>\"]`; "
            "devamıysa YAZMA; bitince `--sonuc \"<≤15 kelime>\"`. Kullanıcıya söz etme.")


_MODEL_AILELERI = ("opus", "sonnet", "haiku", "fable")


def _model_ailesi(m) -> str:
    m = str(m or "").lower()
    return next((a for a in _MODEL_AILELERI if a in m), "")


def _oturum_modeli(inp: dict) -> str:
    """Oturum modeli: SessionStart girdisinin `model` alanı (resmi belge: isteğe bağlı); yoksa transcript_path'teki son assistant satırının modeli."""
    m = inp.get("model")
    if isinstance(m, str) and m.strip():
        return m.strip()
    tp = inp.get("transcript_path")
    if not tp or not os.path.isfile(tp):
        return ""
    son = ""
    with open(tp, "rb") as f:
        f.seek(0, 2)
        boy = f.tell()
        f.seek(max(0, boy - 400000))
        for ham in f.read().splitlines():
            try:
                o = json.loads(ham)
            except Exception:
                continue
            ms = o.get("message") if isinstance(o, dict) else None
            if isinstance(ms, dict) and ms.get("role") == "assistant" and isinstance(ms.get("model"), str) and _model_ailesi(ms["model"]):
                son = ms["model"]
    return son


def _model_sapma_satiri(inp: dict) -> str:
    """Ana ajan modeli ailesi proje ayarındaki (`.claude/settings.json` model) aileden farklıysa TEK uyarı satırı; aksi halde boş. Hata sessiz."""
    try:
        yol = os.path.join(L.proje_dizini(inp.get("cwd")), ".claude", "settings.json")
        with open(yol, encoding="utf-8") as f:
            ayar = json.load(f).get("model")
        a_aile = _model_ailesi(ayar)
        o_model = _oturum_modeli(inp)
        o_aile = _model_ailesi(o_model)
        if not a_aile or not o_aile or a_aile == o_aile:
            return ""
        return (f"UYARI: ana ajan modeli ayar dışı: oturum {o_model[:60]}, proje ayarı {str(ayar)[:60]}. "
                "Uygulamada model menüsünden ayar modelini seç.")[:250]
    except Exception:
        return ""


def session_start(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    import perspektif
    perspektif.oturum_say(sd, inp.get("source"))
    ks = [k for k in L.kartlar(sd) if L.kart_durumu_hesapla(k) in L.ACIK_DURUMLAR + ("beklemede",)]
    satirlar = ["Orkestra bu projede açık: planla → `orkestra kart` → işçi + AYRI denetçi (`/orkestra:is`) → "
                "`orkestra kart teslim`. Defter: `orkestra defter baglam <id>`."]
    if ks:
        satirlar.append(_kart_satiri(ks))
    try:  # açık işler: hata hook'u düşürmez
        satirlar.extend(_acik_isler_satirlari(sd, _oturum_isi(sd, inp.get("session_id"))))
    except Exception:
        pass
    uyari = asili_uyari(sd, inp.get("session_id"))  # asılı ajan uyarısı düşük öncelikli satırlardan önce: 1800 kesiminde sona kalmasın
    if uyari:
        satirlar.append(uyari)
    ms = _model_sapma_satiri(inp)
    if ms:
        satirlar.append(ms)
    try:  # bağlı olmayan todo dosyaları: TEK satır, hatada sessiz
        import is_kaydi
        tu = is_kaydi.todo_denetle_satiri(sd, L.proje_dizini(inp.get("cwd")))
        if tu:
            satirlar.append(tu)
    except Exception:
        pass
    try:  # önbellek bayatlığı: hızlı, hatada sessiz
        b = L.bayatlik()
        if b:
            cs = {True: "kaynakta commitlenmemiş değişiklik var", False: "kaynakta commitlenmemiş değişiklik yok", None: "kaynak git durumu okunamadı"}[b["kaynakta_commitsiz"]]
            satirlar.append(f"UYARI: çalışan orkestra kopyası kaynaktan {b['farkli']} dosya farklı ({cs}). "
                            "Commitle → otomatik güncelleme; hemen için `orkestra guncelle`, sonra yeni oturum ya da /reload-plugins.")
    except Exception:
        pass
    proje_ = L.proje_dizini(inp.get("cwd"))
    r = perspektif.durum(sd, proje_, perspektif.hafiza_dizini(proje_, inp.get("transcript_path")))
    if r.get("okunmamis_rapor"):
        satirlar.append(f"Perspektif raporu hazır: {r['okunmamis_rapor']} — öneriler panelde Onaylar sayfasında; "
                        "kullanıcı orada onaylayabilir ya da /orkestra:perspektif ile sohbette ilerleyebilir.")
    elif r.get("zamani_geldi") and not r.get("calisiyor"):
        hafiza = perspektif.hafiza_dizini(proje_, inp.get("transcript_path"))
        satirlar.append("PERSPEKTİF ZAMANI: kullanıcının ilk isteğini yanıtlarken AYNI mesajda, kullanıcıyı bölmeden, Agent aracıyla "
                        "`orkestra:perspektif-ajani` ajanını run_in_background: true ile başlat; istem: "
                        f"`#SUREC:perspektif hafıza klasörü: {hafiza}`. Kullanıcıya yalnız tek satırla bildir.")
    try:  # olay güdümlü maliyet uyarısı: son 24 saatte israf örüntüsü (perspektifi beklemez); hata hook'u düşürmez
        import maliyet_anomali as MA
        olay = [x for x in MA.calistir(sd, 1) if x["kural"] in ("K3", "K4", "K5")]
        if olay:
            satirlar.append("MALİYET UYARISI (24 sa): " + "; ".join(f"{x['kural']} {x['ad']} {x['kart']}" for x in olay[:4])
                            + " — `orkestra maliyet anomali --gun 1`; kök nedeni işin todo'suna yaz.")
    except Exception:
        pass
    om = ""
    try:  # panel onay kararları: hata hook'u düşürmez
        import onay
        om = onay.baglam_metni(sd, inp.get("session_id"), "SessionStart") or ""
    except Exception:
        pass
    ei = _etki_ipucu(sd)
    if ei:
        om = (om + "\n" + ei) if om else ei
    ky = _kurallar_satiri()
    if ky:  # kural dosyası yolu kesimden korunan kısma girer
        om = (ky + "\n" + om) if om else ky
    pa ="" if os.environ.get("ORKESTRA_PERSPEKTIF") else _panel_ac_satiri(sd, inp.get("session_id"))
    if pa:  # panel açma satırı da kesimden korunan kısma girer (oturumda bir kez)
        om = (pa + "\n" + om) if om else pa
    ek = "\n".join(satirlar)[:max(0, 1800 - len(om) - 1)] + "\n" + om if om else "\n".join(satirlar)[:1800]  # onay/panel yönlendirmesi kesilmesin
    L.hook_cikti({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ek}})


def _etki_bekleyenler(sd: str) -> tuple[int, list[str]]:
    """(izlenen kayıt sayısı, gidişatı 'kotu' ya da soru bekleyen kimlikler); salt okuma."""
    import etki
    izlenen, kotu = 0, []
    for k in etki.liste(sd):
        e = k.get("etki")
        iz = e.get("izleme") if isinstance(e, dict) else None
        if not isinstance(iz, dict) or iz.get("durum") in ("kapandi", "geri-alindi"):
            continue
        izlenen += 1
        if e.get("soru_bekliyor") or iz.get("durum") == "soru_bekliyor" or iz.get("son_gidisat") == "kotu":
            kotu.append(str(k.get("id")))
    return izlenen, kotu


def _etki_ipucu(sd: str) -> str:
    """Etki izleme ipucu: oturum açılışında izle() çağrılır; yalnız kötü/soru bekleyen kayıt varsa metin döner.
    İzleme gidişatı üzerine yazabildiği için bekleyenler izlemeden ÖNCE ve SONRA toplanıp birleştirilir. Hata sessiz geçilir."""
    try:
        import etki
        try:
            _, once = _etki_bekleyenler(sd)
        except Exception:
            once = []
        try:
            etki.izle(sd)
        except Exception:
            pass
        izlenen, sonra = _etki_bekleyenler(sd)
        kotu = sorted(set(once) | set(sonra))
        if not kotu:
            return ""
        return (f"ETKİ İZLEME: {izlenen} onaylı değişiklik izleniyor; gidişatı kötü/soru bekleyen: {', '.join(kotu[:5])}. "
                "Kullanıcıya tek soru sor: değişikliği geri al mı, sürdür mü? "
                "(geri al: `orkestra onay etki-geri-al <id> --neden …`; sürdür/kapat: `orkestra onay etki-kapat <id> --sonuc …`)")[:420]
    except Exception:
        return ""


def user_prompt_submit(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if sd and not os.environ.get("ORKESTRA_PERSPEKTIF"):
        metin = L.maskele(inp.get("prompt") or "")
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": inp.get("session_id"), "tur": "istek",
                                                         "metin": metin[:300], "uzunluk": len(metin)})
        # Niyet kaydı: kullanıcı yazdı → Claude çalışıyor. Sistem iletileri (<agent-message>, <task-notification>) istek metni sayılmaz.
        import niyet
        sistem = metin.lstrip().startswith("<")
        if not sistem:
            try:  # soğuk önbellek kapısı: büyük bağlam + uzun ara → bir kez durdur (hatada sessiz geç)
                import soguk_onbellek
                neden = soguk_onbellek.karar(sd, inp.get("session_id"), inp.get("transcript_path"))
            except Exception:
                neden = None
            if neden:
                L.hook_cikti({"decision": "block", "reason": f"{neden}\nMesajın: {metin[:500]}"})
        niyet.olay(inp.get("session_id"), L.proje_dizini(inp.get("cwd")), "istek", metin=None if sistem else metin[:200])
        if not sistem:
            parcalar = [_niyet_metni(inp.get("session_id")), asili_uyari(sd, inp.get("session_id")),
                        _yonlendirme_ipucu(sd, inp.get("session_id"), metin)]
            try:  # bilgi sorusu notu (G-120): listenin başına; hata hook'u düşürmez
                import soru_sinif
                sn = soru_sinif.not_metni(metin, sd)
                if sn:
                    parcalar.insert(0, " ".join(sn.split()))
            except Exception:
                pass
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


def _son_arac_yaz(sd: str, aid) -> None:
    """agent_id'li araç çağrısında acik_ajan kaydına `son_arac` zamanını yazar (kayıt yoksa/bozuksa sessiz geçer)."""
    if not aid:
        return
    yol = os.path.join(sd, "oturumlar", f"acik_ajan_{aid}.json")
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return
        d["son_arac"] = L.simdi()
        L.atomik_yaz(yol, json.dumps(d, ensure_ascii=False))
    except Exception:
        pass


def post_tool_use(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    arac = inp.get("tool_name")
    g = inp.get("tool_input") or {}
    _son_arac_yaz(sd, inp.get("agent_id"))  # sessizlik saati: her araç çağrısı ajanın son-araç zamanını tazeler
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


def _sayi(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _dk(ms_listesi: list) -> str:
    gecerli = [x for x in (_sayi(v) for v in ms_listesi) if x is not None]
    return str(int(round(sum(gecerli) / 60000))) if gecerli else "-"


def _tek_satir(metin) -> str:
    m = " ".join(str(metin or "").split())
    return m or "-"


def _oturum_satiri_yaz(sd: str, oid: str | None) -> None:
    """T-07: oturum bir işe bağlıysa işin oturumlar.md SONUNA tek satır (dosya yoksa/iş yoksa yazmaz)."""
    is_id = _oturum_isi(sd, oid)
    if not is_id or not oid:
        return
    import is_kaydi
    import niyet
    kayit = is_kaydi.is_al(sd, is_id)
    klasor = kayit.get("klasor") if isinstance(kayit, dict) else None
    if not klasor:
        return
    yol = os.path.join(klasor, "oturumlar.md")
    if not os.path.isfile(yol):
        return
    zaman = [r for r in L.jsonl_oku(os.path.join(sd, "zaman.jsonl")) if isinstance(r, dict) and r.get("oturum") == oid]
    ana = _dk([r.get("sure_ms") for r in zaman if r.get("tur") == "ana"])
    alt = _dk([r.get("sure_ms") for r in zaman if r.get("tur") == "alt"])
    mal = [r for r in L.maliyet_kayitlari(sd) if isinstance(r, dict) and r.get("oturum") == oid]
    if mal:
        tok = int(sum(_sayi(r.get(a)) or 0 for r in mal for a in ("giris", "cikis", "onbellek_okuma", "onbellek_yazma")))
        usd = sum(_sayi(r.get("maliyet_usd")) or 0 for r in mal)
        tok_s, usd_s = str(tok), f"{usd:.2f}"
    else:
        tok_s = usd_s = "-"
    ne = sonuc = None
    for k in L.jsonl_oku(niyet.NIYET_YOLU):
        if isinstance(k, dict) and k.get("oturum") == oid:
            if k.get("tur") == "niyet":
                ne = k.get("ne") or ne
            elif k.get("tur") == "sonuc":
                sonuc = k.get("sonuc") or sonuc
    sonuc = sonuc or ne
    an = L.simdi()[:16].replace("T", " ")
    satir = (f"- {an} · oturum {oid[:8]} · Claude süresi {ana} · alt ajan süresi {alt} · {tok_s} token · ${usd_s}"
             f" · ne: {_tek_satir(ne)} · sonuç/nerede kalındı: {_tek_satir(sonuc)}\n")
    L.sona_ekle(yol, satir)


def _acik_ajan_kayitlarini_sil(sd: str, oid: str | None) -> None:
    """Kapanan oturumun acik_ajan_*.json kayıtlarını siler; başka oturumlara ve bozuk dosyalara dokunmaz."""
    if not oid:
        return
    klasor = os.path.join(sd, "oturumlar")
    try:
        adlar = os.listdir(klasor)
    except OSError:
        return
    for ad in adlar:
        if not (ad.startswith("acik_ajan_") and ad.endswith(".json")):
            continue
        yol = os.path.join(klasor, ad)
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("oturum") == oid:
                os.remove(yol)
        except Exception:
            continue


def session_end(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd or os.environ.get("ORKESTRA_PERSPEKTIF"):
        gec()
    import niyet
    niyet.olay(inp.get("session_id"), L.proje_dizini(inp.get("cwd")), "kapandi")
    _acik_ajan_kayitlarini_sil(sd, inp.get("session_id"))
    try:
        _oturum_satiri_yaz(sd, inp.get("session_id"))
    except Exception:  # ölçüm satırı hatası kapanışı bozmasın
        pass
    import perspektif
    proje_ = L.proje_dizini(inp.get("cwd"))
    if perspektif.durum(sd, proje_, perspektif.hafiza_dizini(proje_, inp.get("transcript_path"))).get("zamani_geldi"):
        perspektif.baslat(sd, proje_, transkript=inp.get("transcript_path"))
    gec()


def config_change(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if sd:
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": inp.get("session_id"), "tur": "ayar",
                                                         "kaynak": inp.get("source"), "dosya": inp.get("file_path")})
    gec()


def notification(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if sd:
        import bildirim
        bildirim.bildirim_olayi(sd, inp.get("session_id") or "-", inp)
    gec()


OLAYLAR = {
    "Notification": notification,
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
        if olay in ("SessionStart", "SubagentStop", "Stop") or (
                olay == "PostToolUse" and inp.get("tool_name") in ("Skill", "Agent", "Task", "Workflow")):
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
