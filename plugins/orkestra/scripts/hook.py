"""Orkestra hook dağıtıcısı: `python hook.py <OlayAdı>` — girdi stdin'de JSON.

İlke: yalnız `.claude/orkestra/` açık projelerde iş yapar; başka her yerde sessizce geçer.
Kapılar (PreToolUse, Stop) iç hatada güvenli tarafa düşer: korunan dosyaya dokunuşu reddeder, gerisini geçirir.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402
import ork_lib as L  # noqa: E402
import baglam as B  # noqa: E402
import etkin_sure as ES  # noqa: E402

KORUNAN_ADLAR = {"ortak_defter.md", "ortak_defter.jsonl", "maliyet.jsonl", "gunluk.jsonl", "atif.jsonl"}
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


_DURUM_DIZINI = ""  # PreToolUse'ta kurulur: reddet davranış hatasını bu dizindeki hata.jsonl'e yazar (ADR-0037)
_PS_CMDLET = re.compile(r"\b(?:Get|Set|New|Remove|Select|Where|Write|Test|Invoke|Out|Start|Stop|Add|Import|Export|Copy|Move"
                        r"|Join|Split|ForEach|Sort|Measure|Convert(?:To|From))-[A-Z][A-Za-z]+\b|\$env:\w+")


def _davranis_yaz(tur: str, ileti: str, baglam=None) -> None:
    """Ajan davranış hatasını hata defterine yazar (ADR-0037); durum dizini yoksa ya da yazılamazsa sessiz geçer."""
    if not _DURUM_DIZINI:
        return
    try:
        import hata_kayit as HK
        HK.davranis(_DURUM_DIZINI, tur, ileti, baglam)
    except Exception:
        pass


def reddet(neden: str):
    _davranis_yaz("hook-red", neden)
    L.hook_cikti({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                         "permissionDecisionReason": f"orkestra: {neden}"}})


def sor(neden: str):
    """Kullanıcıya onay sordurur (permissionDecision: ask). İzin politikası kapısı: halka açık eylemler."""
    L.hook_cikti({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                         "permissionDecisionReason": f"orkestra: {neden}"}})


_BEKLEYEN_UYARI = ""  # PreToolUse gölge uyarısı: yazma engellenmez, çıkışta tek satır bağlam olarak gider
_KULLANICI_MESAJI = ""  # K-003: bağlantı satırlarını hook kullanıcıya gösterir (ADR-0040); model yazmaz
_VARSAYILAN_IZIN = ""  # izin politikası (mod=genis): kapı dışı çağrıya hook allow verir; settings deny/ask yine geçerlidir


_GUNCEL_GIRDI = None  # I-224 P9: biçim düzeltmesiyle değişen araç girdisi; çıkışta updatedInput olarak gider
_IZIN_KIPI = ""  # PreToolUse girdisindeki permission_mode
_KENDILIGINDEN_YAZAN_KIPLER = ("acceptEdits", "bypassPermissions", "auto")


def _pre_cikti(ek: str = ""):
    """PreToolUse çıkışı: varsayılan izin (allow) ve/veya ek bağlam; ikisi de yoksa karar vermeden çıkar.
    Düzeltilmiş girdi varsa updatedInput eklenir; Claude Code updatedInput'u yalnız allow/ask ile belgeler: izin
    politikası allow vermediyse, düzenlemeyi zaten sormadan yapan kipte allow, diğer kiplerde ask (kullanıcı
    düzeltilmiş girdiyi görür; izin yükseltmesi olmaz). settings deny/ask kuralları her durumda geçerlidir."""
    ho = {"hookEventName": "PreToolUse"}
    if _VARSAYILAN_IZIN:
        ho["permissionDecision"] = "allow"
        ho["permissionDecisionReason"] = _VARSAYILAN_IZIN
    if _GUNCEL_GIRDI is not None:
        if "permissionDecision" not in ho:
            ho["permissionDecision"] = "allow" if _IZIN_KIPI in _KENDILIGINDEN_YAZAN_KIPLER else "ask"
            ho["permissionDecisionReason"] = "orkestra: biçim düzeltildi (K-005)"
        ho["updatedInput"] = _GUNCEL_GIRDI
    if ek:
        ho["additionalContext"] = ek
    cikti = {"hookSpecificOutput": ho} if len(ho) > 1 else {}
    if _KULLANICI_MESAJI:
        cikti["systemMessage"] = _KULLANICI_MESAJI
    L.hook_cikti(cikti or None)


def gec():
    _pre_cikti(_BEKLEYEN_UYARI)


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

def _alan_uyarisi(sd: str, oid, proje: str, tam: str) -> None:
    """Oturum bir işe bağlıyken iş klasörü (+ is.json `alan` listesi) dışına yazmada oturumda klasör başına BİR kez
    engellemeyen tek satırlık uyarı (yol karşılaştırması; model yok). Hatada sessiz geçer."""
    try:
        isid = _oturum_isi(sd, oid)
        if not isid:
            return
        import is_kaydi
        is_ = (is_kaydi.is_al(sd, isid) or {})
        izinli = [is_.get("klasor") or ""] + [os.path.join(proje, a) for a in (is_.get("alan") or [])]
        if any(i and L.yol_altinda(tam, i) for i in izinli):
            return
        rel = _rel(proje, tam)
        if rel.startswith("..") or rel.startswith(".claude/"):
            return
        parts = rel.split("/")
        klasor = "/".join(parts[:max(1, min(2, len(parts) - 1))])
        yol = os.path.join(sd, "oturumlar", f"alan_{oid}.json")
        try:
            with open(yol, encoding="utf-8") as f:
                gorulen = json.load(f).get("gorulen", [])
        except Exception:
            gorulen = []
        if klasor in gorulen:
            return
        L.atomik_yaz(yol, json.dumps({"gorulen": (gorulen + [klasor])[-30:]}))
        _pre_cikti(f"Alan dışı yazma: {isid} işinin klasörü dışına ({klasor}) yazılıyor; işin parçasıysa devam, değilse ayrı sohbet/iş.")
    except Exception:
        return



def _yazilacak_metin(arac: str, girdi: dict) -> str:
    if arac == "Write":
        return girdi.get("content") or ""
    if arac == "Edit":
        return girdi.get("new_string") or ""
    if arac == "MultiEdit":
        return "\n\n".join(str(e.get("new_string") or "") for e in (girdi.get("edits") or []) if isinstance(e, dict))
    return ""


def _genis_tarama_kapisi(sd: str, oid, komut: str) -> None:
    """P-012 madde 4 (golge): zaman sınırsız geniş `grep -r`/`find` için `kural_ihlal / genis_tarama` günlüğe yazılır ve tek satır
    uyarı bağlama gider; komut engellenmez. Kalıplar ayarda (`ayarlar/genis_tarama_hatirlatma.json`); hatada sessiz geçer."""
    global _BEKLEYEN_UYARI
    try:
        import genis_tarama_hatirlatma as GT
        if not GT.ihlal_mi(komut, sd):
            return
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oid, "tur": "kural_ihlal",
                                                         "kural": "genis_tarama", "mod": GT.mod(GT.ayar_oku(sd)),
                                                         "is": _oturum_isi(sd, oid)})
        _BEKLEYEN_UYARI = GT.hatirlatma_metni(sd)
    except SystemExit:
        raise
    except Exception:
        return


def _kanit(eslesen=None, cumle=None) -> dict:
    """I-271: `kural_ihlal` satırının `eslesen`/`cumle` alanları (ortak yardımcı `kapi_mod.kanit_alanlari`: maske + 200 sınırı).
    Bilinmeyen alan yazılmaz; hatada boş sözlük (kaydı hiçbir zaman bozmaz)."""
    try:
        import kapi_mod
        return kapi_mod.kanit_alanlari(eslesen, cumle)
    except Exception:
        return {}


def _kalip_kaniti(kaliplar, metin: str, normallestir) -> dict:
    """Kalıp listesinde `normallestir(metin)` üstünde eşleşen ilk regex ve onu içeren cümle (`_kanit` alanları). Normalleştirme
    uzunluğu korursa cümle özgün metinden kesilir, korumazsa normalleştirilmiş metinden. Eşleşme yoksa boş sözlük."""
    metin = metin or ""
    norm = normallestir(metin)
    for k in kaliplar or []:
        try:
            m = re.search(k, norm)
        except re.error:
            continue
        if not m:
            continue
        kaynak = metin if len(metin) == len(norm) else norm
        bas = max(kaynak.rfind(c, 0, m.start()) for c in ".!?\n") + 1
        sonlar = [i for i in (kaynak.find(c, m.end()) for c in ".!?\n") if i != -1]
        return _kanit(k, kaynak[bas:(min(sonlar) + 1 if sonlar else len(kaynak))])
    return {}


def _bicim_kapisi(sd: str, inp: dict, arac: str, girdi: dict, tam: str, oid) -> None:
    """Okunacak belgeye (plan/todo/özet/bulgu/jira_onerisi/rapor .md) yazılacak metnin K-005 biçimi (Ö4).
    golge: `gunluk.jsonl`'a kural_ihlal kaydı + tek satır uyarı (yazma engellenmez); ihlal: yazım reddedilir.
    Hatada sessiz geçer; yazımı hiçbir zaman bozmaz."""
    global _BEKLEYEN_UYARI, _GUNCEL_GIRDI
    try:
        import belge_bicim as BB
        ayar = BB.ayar_oku(sd)
        if not BB.belge_mi(tam, ayar.get("yazim_kapisi") or {}):
            return
        ihlaller = BB.yazim_ihlalleri(_yazilacak_metin(arac, girdi), os.path.basename(tam), ayar)
        if not ihlaller:
            return
        kip = BB.mod(ayar, "yazim_kapisi")
        proje = L.proje_dizini(inp.get("cwd"))
        kayit = {"zaman": L.simdi(), "oturum": oid, "kural": "belge_bicim", "dosya": _rel(proje, tam) or tam,
                 "arac": arac, "is": _oturum_isi(sd, oid)}
        if kip == "ihlal" and arac == "Write" and BB.duzelt_acik(sd):
            # I-224 P9: ihlallerin tümü güvenli dönüşümle gideriliyorsa ret yerine düzeltilmiş içerik (updatedInput).
            # Yalnız Write: Edit/MultiEdit parçası çevresiz olduğundan (boş satır, önceki satır bilinmez) ret kalır.
            yeni, uyg = BB.guvenli_duzelt(girdi.get("content") or "", os.path.basename(tam), ayar)
            if uyg:
                girdi["content"] = yeni  # aynı sözlük: sonraki kapılar (sıra, alan) düzeltilmiş metni görür
                _GUNCEL_GIRDI = girdi
                L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {**kayit, "tur": "belge_duzeltme",
                                                                "ihlal_adet": len(ihlaller), "donusum_adet": len(uyg)})
                _BEKLEYEN_UYARI = (_BEKLEYEN_UYARI + "\n" if _BEKLEYEN_UYARI else "") + \
                    f"orkestra: biçim düzeltildi (K-005): {len(uyg)} dönüşüm; {os.path.basename(tam)} düzeltilmiş içerikle yazılıyor."
                return
        satirlar_ = _yazilacak_metin(arac, girdi).split("\n")  # belge_bicim._bloklar ile aynı numaralama
        no = ihlaller[0].get("satir") or 0
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {
            **kayit, "tur": "kural_ihlal", "mod": kip,
            "ihlal": [{"satir": i["satir"], "kural": i["kural"]} for i in ihlaller[:8]], "adet": len(ihlaller),
            **_kanit(ihlaller[0].get("kural"), satirlar_[no - 1] if 0 < no <= len(satirlar_) else None)})
        satir = BB.ozet_satiri(os.path.basename(tam), ihlaller)
        if kip == "ihlal":
            reddet(satir.replace("(K-005, gölge)", "(K-005)") + " Düzelt, sonra yaz; bilerek ise satır sonuna `<!-- biçim-tamam -->` koy.")
        _BEKLEYEN_UYARI = satir
    except SystemExit:
        raise
    except Exception:
        return


def _uygulanmis_metin(arac: str, girdi: dict, tam: str) -> str | None:
    """Yazım sonrası dosyanın tamamı: Write için yazılan metin, Edit/MultiEdit için düzenlemesi uygulanmış mevcut dosya.
    Düzenleme uygulanamıyorsa (yazım zaten başarısız olur) ya da arac tanınmıyorsa None."""
    if arac == "Write":
        return _yazilacak_metin(arac, girdi)
    if arac not in ("Edit", "MultiEdit"):
        return None
    try:
        with open(tam, encoding="utf-8", errors="replace", newline="") as f:
            yeni = f.read()
    except OSError:
        return None
    for e in ([girdi] if arac == "Edit" else [e for e in (girdi.get("edits") or []) if isinstance(e, dict)]):
        o, n = str(e.get("old_string") or ""), str(e.get("new_string") or "")
        if not o or o not in yeni:
            return None
        yeni = yeni.replace(o, n) if e.get("replace_all") else yeni.replace(o, n, 1)
    return yeni


def _todo_yeni_metin(arac: str, girdi: dict, tam: str) -> str:
    """todo.md yazımında denetlenecek metin. Write: tamamı. Edit/MultiEdit: düzenleme uygulanmış dosyanın, mevcut dosyada
    olmayan satırları (parça içinde `P1:` gibi önek silinip satır bozulsa da `new_string` tek başına bunu göstermez)."""
    if arac not in ("Edit", "MultiEdit"):
        return _yazilacak_metin(arac, girdi)
    try:
        with open(tam, encoding="utf-8", errors="replace", newline="") as f:
            eski = f.read()
        duzenlemeler = [girdi] if arac == "Edit" else [e for e in (girdi.get("edits") or []) if isinstance(e, dict)]
        yeni = eski
        for e in duzenlemeler:
            o, n = str(e.get("old_string") or ""), str(e.get("new_string") or "")
            if not o or o not in yeni:
                return _yazilacak_metin(arac, girdi)  # uygulanamayan düzenleme: yazım zaten başarısız olur
            yeni = yeni.replace(o, n) if e.get("replace_all") else yeni.replace(o, n, 1)
        mevcut = set(eski.splitlines())
        return "\n".join(s for s in yeni.splitlines() if s not in mevcut)
    except OSError:
        return _yazilacak_metin(arac, girdi)


def _sira_kapisi(arac: str, girdi: dict, tam: str) -> None:
    """P-005 (yazım anı): sıralı işin klasöründe plan.md mevcut durum tamam olmadan, todo.md plan tamam olmadan
    yazılamaz; todo.md'ye yazılan her onay kutusu satırı `P<n>:` ile başlar ve P<n> planda olmalıdır.
    Kaynak çözümler (şablon, `is ac`, CLI) Write aracıyla yapılan doğrudan yazımı engellemez; bu kapı yalnız onun içindir.
    Sıralı olmayan iş ve ORKESTRA_SIRA_KAPISI=0 geçer; hatada sessiz geçer, yazımı hiçbir zaman bozmaz."""
    global _BEKLEYEN_UYARI
    neden = ""
    try:
        ad = os.path.basename(tam).lower()
        if ad not in ("plan.md", "todo.md"):
            return
        import is_sirasi as SR
        klasor = os.path.dirname(tam)
        if not SR.sirali_mi(klasor):
            return
        if ad == "plan.md":
            eksik = SR.plan_onkosulu(klasor)
            yeni = _uygulanmis_metin(arac, girdi, tam)
            if not eksik:  # ADR-0072: `Mevcut varlık` biçimi yazıldığı anda denetlenir; todo yazıldıysa boş alan da eksiktir
                if yeni is not None:  # yalnız bu yazımın getirdiği eksikler reddedilir: bozuk planı madde madde düzeltmek engellenmez
                    bos = os.path.exists(os.path.join(klasor, "todo.md"))
                    onceki = set(SR.mevcut_varlik_eksikleri(klasor, None, bos_say=bos))
                    eksik = [e for e in SR.mevcut_varlik_eksikleri(klasor, yeni, bos_say=bos) if e not in onceki]
            # I-224: ret koşulu aynı; ileti planın tüm alan eksiklerini düzeltme satırıyla tek seferde verir. Ret yoksa bilgi olur.
            rapor = SR.plan_yazim_mesaji(klasor, eksik, yeni)
            neden = rapor if eksik else ""
            if rapor and not eksik:
                _BEKLEYEN_UYARI = (_BEKLEYEN_UYARI + "\n" if _BEKLEYEN_UYARI else "") + "orkestra: " + rapor
        else:
            eksik = SR.todo_onkosulu(klasor)
            if eksik:
                neden = SR.mesaj(eksik, "todo.md")
            else:
                ihlal = SR.todo_satir_ihlalleri(_todo_yeni_metin(arac, girdi, tam), SR.plan_maddeleri(klasor), SR.kaliteli_mi(klasor))
                neden = "todo.md yazılamaz (P-005): " + "; ".join(ihlal[:3]) if ihlal else ""
            if not neden:  # plan doğrulama kapısı: plan ✅/❌ kapısı (CLI ile aynı işlevler; gölge modda boş döner)
                import plan_dogrulama as PD
                neden = PD.todo_onkosulu(klasor) or PD.todo_satir_engelleri(klasor, _todo_yeni_metin(arac, girdi, tam))
    except Exception:
        return
    if neden:
        reddet(neden)


def _bagli_is(sd: str, oid):
    """Oturumun bağlı işi (oturum json'u, yoksa CLI'ın okuduğu eski is_<oturum>.json yan dosyası).
    Oturum json'u var ama okunamıyorsa istisna fırlatır (kapı serbest bırakır)."""
    yol = os.path.join(sd, "oturumlar", f"{oid}.json")
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("is"):
            return str(d["is"])
    try:
        with open(os.path.join(sd, "oturumlar", f"is_{oid}.json"), encoding="utf-8") as f:
            y = json.load(f)
        return str(y["is"]) if isinstance(y, dict) and y.get("is") else None
    except OSError:
        return None


def _is_kapisi(sd: str, oid, proje: str, tam: str) -> None:
    """P4-P5: bağsız oturumda ana ajanın yazması (Write/Edit/MultiEdit/NotebookEdit; plan.md/todo.md dahil) reddedilir;
    red metni bağlanma komutlarını ve en yakın iki işi söyler. ORKESTRA_IS_KAPISI=0 kapatır. Fail-open: oturum
    kimliği yoksa, merkez kayıt bozuksa ya da kapı kodunda herhangi bir istisna olursa çağrı serbest kalır."""
    if os.environ.get("ORKESTRA_IS_KAPISI") == "0":
        return
    neden = ""
    try:
        if not oid or _bagli_is(sd, oid):
            return
        import is_kaydi
        # merkez kayıt yoksa projede iş sistemi hiç kullanılmamış (ilk gerçek mesaj işi otomatik açar); bozuksa bağ çözülemez
        if not os.path.exists(is_kaydi._merkez(sd)) or is_kaydi.merkez_bozuk_mu(sd):
            return
        acik = is_kaydi.is_liste(sd, "acik")
        puanlar = []
        try:
            import is_yonlendirme
            isler = [{"id": g["id"], "baslik": g.get("baslik") or "",
                      "klasor": os.path.basename(str(g.get("klasor") or ""))} for g in acik]
            puanlar = [p for p in is_yonlendirme.eslestir((_rel(proje, tam) or tam).replace("/", " "), isler,
                                                          _esleme_ayari(sd)) if p.get("puan", 0) > 0]
        except Exception:
            puanlar = []
        neden = _bagsiz_secim_satiri(acik, puanlar, bas=(
            "bu oturum bir işe bağlı değil; bağsız oturumda dosya yazılmaz (plan.md/todo.md dahil). Önce bağlan: "
            "`orkestra is devam <id>` ya da `orkestra is ac \"<başlık>\" --klasor <klasör>`, sonra yazımı tekrarla."))
    except Exception:
        return
    if neden:
        reddet(neden)


def _is_klasorunu_commitle(klasor, cwd):
    """Hook'un yazdığı iş kaydını (is.json) aynı turda commit eder; arşivde commit edilmemiş dosya kalmasın.
    ORKESTRA_OTO_COMMIT kapalıysa, klasör depo dışındaysa ya da hata olursa sessiz çıkar."""
    try:
        import oto_commit
        if not klasor or not oto_commit.acik():
            return
        repo = oto_commit.depo_koku(os.path.abspath(cwd or os.getcwd()))
        if not repo:
            return
        goreli = os.path.relpath(os.path.abspath(klasor), repo)
        if not goreli.startswith(".."):
            oto_commit.klasorleri_commit(repo, [goreli], None, etiket="orkestra")
    except Exception:
        pass


def _onay_kaydi(sd: str, oid):
    """Oturumun bağlı işi `onay: bekliyor` ise iş kaydı, değilse None. Hatada None (fail-open)."""
    try:
        import is_onay
        if not oid or not is_onay.kapi_acik():
            return None
        is_id = _bagli_is(sd, oid)
        if not is_id:
            return None
        import is_kaydi
        kayit = is_kaydi.is_al(sd, is_id)
        if is_onay.otomatik_onay(sd, kayit):  # ADR-0009: /auto işte belgeler tamamsa onay kendiliğinden verilir
            return None
        if is_onay.bekleyen_onay_ver(sd, kayit):  # ADR-0072: eksik yüzünden saklanan kullanıcı onayı, eksik giderilince verilir
            return None
        return kayit if is_onay.bekliyor_mu(kayit) else None
    except Exception:
        return None


DURUM_SATIRI_SINIR = 200  # I-224 P6: iş bağlıyken bağlama giren tek satırlık durum özetinin üst sınırı
_SIRA_ADIMI = {"sozlesme": "sözleşme", "mevcut_durum": "mevcut durum", "plan": "plan.md"}


def _durum_satiri_acik(sd: str | None) -> bool:
    """`ayarlar/durum_satiri.json` mod (`acik` | `kapali`; proje ezmesi `<durum>/durum_satiri.json`); ORKESTRA_DURUM_SATIRI=0 kapatır."""
    if os.environ.get("ORKESTRA_DURUM_SATIRI") == "0":
        return False
    mod = "acik"
    for yol in (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "durum_satiri.json"),
                os.path.join(sd, "durum_satiri.json") if sd else ""):
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("mod") in ("acik", "kapali"):
                mod = d["mod"]
        except (OSError, ValueError):
            pass
    return mod == "acik"


def _durum_satiri(sd: str, oid) -> str:
    """I-224 P6 (R6): bağlı işin tek satırlık durumu (iş kimliği, onay, sıradaki belge/adım), en çok 200 karakter.
    Başlık ve todo metni girmez (sır/ad taşımaz). Bağsız oturum, kapalı ayar ya da hata: ''."""
    try:
        if not oid or not _durum_satiri_acik(sd):
            return ""
        is_id = _bagli_is(sd, oid)
        if not is_id:
            return ""
        import is_kaydi
        import is_onay
        kayit = is_kaydi.is_al(sd, is_id) or {}
        klasor = str(kayit.get("klasor") or "")
        od = is_onay.durum(kayit) if is_onay.kapi_acik() else None
        onay_m = {is_onay.BEKLIYOR: "onay bekliyor", is_onay.VERILDI: "onay verildi"}.get(od, "onay kapısı yok")
        sira = ""
        if klasor:
            import is_sirasi as SR
            if SR.sirali_mi(klasor):
                a, _ = SR.adim(klasor)
                sira = _SIRA_ADIMI.get(a, "")
                if not sira and not os.path.exists(os.path.join(klasor, "todo.md")):
                    sira = "todo.md"
        if not sira and od == is_onay.BEKLIYOR:
            sira = "kullanıcı onayı"
        if not sira:
            t = is_kaydi.todo_ozet(klasor) if klasor else {}
            ilk = next((m.group(1) for m in (re.match(r"\W*(P\d+)\b", x) for x in t.get("acik_maddeler") or []) if m), "")
            sira = (f"uygulama {ilk}".strip() + f" (todo {t['biten']}/{t['toplam']})") if t.get("toplam") else "uygulama"
        mod = f", mod {kayit[is_onay.MOD_ALANI]}" if kayit.get(is_onay.MOD_ALANI) else ""
        return f"Durum: {is_id} · {onay_m}{mod} · sıradaki: {sira}"[:DURUM_SATIRI_SINIR]
    except Exception:
        return ""


def _onay_kapisi(sd: str, oid, proje: str, tam: str = "", tirnaksiz: str = "") -> None:
    """P-016: iş onay beklerken (ana ve alt ajan) işin belgeleri dışında dosya yazılmaz; kabukta commit, bağımlılık
    kurma ve onay komutu çalışmaz. Hatada serbest; ORKESTRA_ONAY_KAPISI=0 kapatır."""
    kayit = _onay_kaydi(sd, oid)
    if not kayit:
        return
    try:
        import is_onay
        neden = (is_onay.yazma_engeli(kayit, proje, tam) if tam
                 else is_onay.kabuk_engeli(tirnaksiz, is_onay.git_izni_var(sd, oid)))  # ADR-0031
    except Exception:
        return
    if neden:
        reddet(neden)


def _bitis_baglanti_kapisi(sd: str, oid, proje: str) -> None:
    """K-003 kaynakta (ADR-0040): turu bitiren araç (wrap_up, AskUserQuestion, ExitPlanMode) çağrılırken, işin belgeleri
    son teslimden beri değiştiyse hazır bağlantı satırlarını hook kullanıcıya `systemMessage` ile gösterir; tur
    reddedilmez, model satır yazmaz (aynı imza ikinci kez gösterilmez). Gösterilen satırlar Stop'ta tekrarlanmasın diye
    kaydedilir. Hatada serbest."""
    global _KULLANICI_MESAJI
    try:
        import is_onay
        if not oid or not is_onay.kapi_acik():
            return
        is_id = _bagli_is(sd, oid)
        if not is_id:
            return
        import is_kaydi
        kayit = is_kaydi.is_al(sd, is_id)
        klasor = str((kayit or {}).get("klasor") or "")
        imza, satirlar = is_onay.teslim_imzasi(klasor, L.baglanti_koku(proje))
        if not imza:
            return
        yol = os.path.join(sd, "oturumlar", f"{oid}.baglanti.json")
        try:
            with open(yol, encoding="utf-8") as f:
                onceki = json.load(f).get("imza")
        except (OSError, ValueError):
            onceki = None
        if onceki == imza:
            return
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"imza": imza, "gosterilen": list(satirlar)}, f)
        _KULLANICI_MESAJI = "Orkestra belgeleri:" + chr(10) + chr(10).join(satirlar)
    except Exception:
        return


def _izin_karari(arac: str, girdi: dict, sd: str, oturum=None):
    """İzin politikası kararı (deny|ask|allow|None, neden). Hatada karar yok: Claude Code varsayılan istemine döner;
    push komutunda hata `ask`'tir (ADR-0036: settings ask satırı kalktı, fail-open yok)."""
    try:
        import izin_politikasi
        kar, neden = izin_politikasi.karar(arac, girdi, sd, oturum=oturum)
    except Exception:
        if arac in KABUK_ARACLARI and re.search(r"\bpush\b", str((girdi or {}).get("command") or "")):
            return "ask", "git push: izin politikası okunamadı, onay gerekir."
        return None, ""
    _izin_karar_yaz(arac, kar, neden, sd, oturum)
    return kar, neden


def _izin_karar_yaz(arac: str, kar, neden: str, sd: str, oturum) -> None:
    """ADR-0095: deny, ask ve auto-allow kararlarını gunluk.jsonl'a `izin_karar` olarak yazar (olağan allow yazılmaz).
    Yazım başarısız olursa sessiz geçer; araç çağrısını engellemez."""
    try:
        auto = kar == "allow" and "auto modu" in (neden or "")
        if kar not in ("deny", "ask") and not auto:
            return
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oturum, "tur": "izin_karar",
                                                       "arac": arac, "karar": kar, "mod": "auto" if auto else "-"})
    except Exception:
        return


_AUTO_SOZLESME = (
    "Orkestra /auto sözleşmesi (ADR-0086): bu mesaj Jira ve GitHub dahil kapsamdaki her eylem için açık yetkidir. "
    "Kullanıcıya soru sorma (AskUserQuestion ve wrap_up 'ask' reddedilir); kararı en iyi uygulamayla kendin ver ve "
    "çalışma özetindeki '## Otomatik kararlar' bölümüne yaz. Zorla/silme/ayna push, kalıcı silme, sır okuma ve veritabanı "
    "yazma yasak kalır; değeri yalnız kullanıcıda olan işler 'Kullanıcıya kalanlar' altına yazılır, koşu durmaz."
)


def _auto_soru_kapisi(arac: str, girdi: dict, sd: str, oturum, aid) -> None:
    """ADR-0086: bağlı işin modu `auto` ise ana ajan kullanıcıya soru soramaz: AskUserQuestion ve dolu `ask` alanlı wrap_up
    reddedilir (kutu yalnız özetle açılabilir). Mod okunamıyorsa serbest (plan davranışı). ORKESTRA_AUTO_YETKI=0 kapatır."""
    if aid or not oturum:
        return
    if arac == "AskUserQuestion":
        pass
    elif arac == "wrap_up" or arac.endswith("__wrap_up"):
        if not str((girdi or {}).get("ask") or "").strip():
            return
    else:
        return
    try:
        import izin_politikasi
        auto = izin_politikasi._auto_modu(sd, oturum)
    except Exception:
        return
    if auto:
        reddet("auto modunda kullanıcıya soru sorulmaz (ADR-0086): kararı en iyi uygulamayla kendin ver ve plan.md'deki "
               "'Otomatik kararlar' bölümüne yaz. Kullanıcıya ait engel (parola, değeri yalnız onda olan sır) soru olmaz; "
               "çalışma özetinde 'Kullanıcıya kalanlar'a yaz. Onay bekleyen işte belgeleri tamamla, onay hook'tan gelir. "
               "wrap_up'ı ask alanı olmadan çağır.")


def _kapi_uygula(kar, neden: str):
    if kar == "deny":
        reddet(neden)
    elif kar == "ask":
        sor(neden)


def _hafiza_duzeltme_kapisi(arac: str, girdi: dict, tam: str) -> None:
    """ADR-0029: hafıza .md yazımı birebir aynı düzeltme notunu ikinci kez ekliyorsa reddedilir (mod=golge: yalnız uyarı).
    Ana ve alt ajan aynıdır. ORKESTRA_HAFIZA_DUZELTME=0 kapatır. Fail-open: kapı kodunda her istisna çağrıyı serbest bırakır."""
    global _BEKLEYEN_UYARI
    neden, mod = "", ""
    try:
        import hafiza_duzeltme as HD
        if arac not in ("Write", "Edit", "MultiEdit") or not HD.acik():
            return
        a = HD.ayar()
        mod = a["mod"]
        if mod == "kapali" or not HD.hafiza_yolu_mu(tam, a):
            return
        try:
            with open(tam, encoding="utf-8", errors="replace") as f:
                onceki = f.read()
        except OSError:
            onceki = ""
        sonraki = HD.yazim_sonrasi(arac, girdi, onceki)
        if sonraki is not None:
            neden = HD.yazim_ihlali(tam, onceki, sonraki, a=a) or ""
    except Exception:
        return
    if not neden:
        return
    if mod == "golge":
        _BEKLEYEN_UYARI = f"orkestra (gölge): {neden}"
        return
    reddet(neden)


def _ajan_kapsam_kapisi(inp: dict, arac: str, girdi: dict, sd: str, atip: str) -> None:
    """I-292 P3 (ADR-0114): alt ajanın türüne göre araç kapsamı; ana ajan etkilenmez. mod=golge: yalnız uyarı.
    Fail-open: kapı kodunda her istisna çağrıyı serbest bırakır. ORKESTRA_AJAN_KAPSAM=0 kapatır."""
    global _BEKLEYEN_UYARI
    if not inp.get("agent_id"):
        return
    try:
        import ajan_kapsam as AK
        cfg = AK.ayar_yukle()
        mod = AK.mod_bul(cfg)
        tur = AK.tur_adi(atip)
        if mod == "kapali" or tur not in (set(cfg.get("salt_okuma_ajanlari") or []) | set(cfg.get("yazma_yollari") or {})):
            return
        ciktilar = None
        if tur in (cfg.get("kart_ciktisi_ajanlari") or []) and arac in AK.YAZMA_ARACLARI:
            gid, _ = ajan_gorevi(sd, inp)
            kart = L.kart_oku(sd, gid) if gid and gid != "-" else None
            ciktilar = (kart or {}).get("ciktilar") or []
        neden = AK.karar(atip, arac, girdi, cfg, inp.get("cwd") or ".", ciktilar)
    except Exception:
        return
    if not neden:
        return
    if mod == "ihlal":
        reddet(neden)
    _BEKLEYEN_UYARI = f"orkestra (gölge): {neden}"


def pre_tool_use(inp: dict):
    global _BEKLEYEN_UYARI, _VARSAYILAN_IZIN, _DURUM_DIZINI, _KULLANICI_MESAJI, _GUNCEL_GIRDI, _IZIN_KIPI
    _KULLANICI_MESAJI = ""
    _GUNCEL_GIRDI = None
    _IZIN_KIPI = str(inp.get("permission_mode") or "")
    _BEKLEYEN_UYARI = ""  # ic_kos işlem içi koşar: önceki çağrının uyarısı sızmasın
    _VARSAYILAN_IZIN = ""
    _DURUM_DIZINI = ""
    arac = inp.get("tool_name", "")
    if arac in YAZAN_ARACLAR:  # eklentinin kopyasına yazılan değişiklik eşitlemede silinir (proje orkestralı olmasa da)
        g0 = inp.get("tool_input") or {}
        y0 = g0.get("file_path") or g0.get("notebook_path") or ""
        kaynak = L.kopyada_mi(os.path.abspath(os.path.join(inp.get("cwd") or os.getcwd(), y0))) if y0 else None
        if kaynak:  # engellemez: yazım sürer, kopya eşitlenirken iş koruma dalına alınır; ajan doğru yere yönlendirilir
            _BEKLEYEN_UYARI = (f"orkestra: yazdığın yol eklentinin kopyası; eklenti değişikliği kaynak depoda yapılır: {kaynak}. "
                               "Kopyadaki değişiklik eşitlemede koruma/klon-* dalına alınır, main'e girmez.")
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    _DURUM_DIZINI = sd
    girdi = dict(inp.get("tool_input") or {})
    aid = inp.get("agent_id")
    atip = inp.get("agent_type") or ""
    _ajan_kapsam_kapisi(inp, arac, girdi, sd, atip)
    kar, kneden = _izin_karari(arac, girdi, sd, inp.get("session_id"))  # kabukta kapı, kilitli test denetiminden SONRA uygulanır (kilidi onayla aşamasın)
    if kar == "allow":
        _VARSAYILAN_IZIN = kneden
    elif arac not in KABUK_ARACLARI:
        _kapi_uygula(kar, kneden)
    _auto_soru_kapisi(arac, girdi, sd, inp.get("session_id"), aid)

    try:
        import is_onay as _io
        if not aid and _io.tur_bitiren_mi(arac):
            _bitis_baglanti_kapisi(sd, inp.get("session_id"), L.proje_dizini(inp.get("cwd")))
    except SystemExit:
        raise
    except Exception:
        pass

    try:  # ADR-0099: engellemeyen devir hatırlatması; hata aracı bozmaz
        import devir_hatirlatma as _dh
        dh = _dh.izle(arac, girdi, sd, inp.get("session_id"), aid, inp.get("cwd"))
        if dh:
            _BEKLEYEN_UYARI = (_BEKLEYEN_UYARI + " " + dh).strip()
    except Exception:
        pass

    if arac in YAZAN_ARACLAR:  # ADR-0111: tabi olunan denetimin kuralı yazım anında (engellemez)
        try:
            import uretim_enjeksiyonu as _ue
            ue = _ue.metin(girdi.get("file_path") or girdi.get("notebook_path"), sd, inp.get("session_id"), atip or None)
            if ue:
                _BEKLEYEN_UYARI = (_BEKLEYEN_UYARI + "\n" + ue).strip()
        except Exception:
            pass

    if arac in YAZAN_ARACLAR:
        yol = girdi.get("file_path") or girdi.get("notebook_path") or ""
        if not yol:
            gec()
        tam = os.path.abspath(os.path.join(inp.get("cwd") or os.getcwd(), yol))
        _hafiza_duzeltme_kapisi(arac, girdi, tam)
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
        if not aid:  # alt ajan çağrıları muaf; ana ajan bağsız oturumda yazamaz (plan.md/todo.md dahil)
            _is_kapisi(sd, oid, proje, tam)
        _onay_kapisi(sd, oid, proje, tam=tam)
        trel = _rel(proje, tam)
        kb = kilitli_test_bul(sd, proje, tam)  # kilitli test: ana ajan dahil herkese kapalı (kart ağaçları dahil)
        if kb:
            reddet(f"kilitli test: {kb[0]} ({kb[1]} kartının test kilidi). Kırmızı sonrası test dosyaları değişmez; "
                   "değişiklik gerekiyorsa ana ajan `orkestra kart test-kilit-ac` ile kilidi açar.")
        _bicim_kapisi(sd, inp, arac, girdi, tam, oid)
        _sira_kapisi(arac, girdi, tam)
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
                if k and k.get("sinif") == "kod" and k.get("yazma_alani") and not isinstance(k.get("mevcut_durum"), dict) \
                        and os.environ.get("ORKESTRA_MEVCUT_KAPISI") != "0" \
                        and atip.split(":", 1)[-1].lower().startswith("isci") \
                        and (L.desen_eslesir(proje, tam, k["yazma_alani"]) if agacta
                             else L.yazma_alaninda_mi(proje, tam, k["yazma_alani"])):
                    reddet(f"{gorev}: kod yazmadan önce mevcut durumu anla. İlgili mevcut kodu oku (Read/Grep), sonra "
                           f"`orkestra kart mevcut {gorev} --dosya <json>` ile kaydet (okunan[dosya, satir, alinti, rol], "
                           "yetenekler, karar: degistir|ekle|yeni, neden, etkilenenler). Not kaydedilmeden yazma alanına yazılmaz.")
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
        _alan_uyarisi(sd, oid, proje, tam)
        gec()

    if arac in KABUK_ARACLARI:
        komut = girdi.get("command") or ""
        _genis_tarama_kapisi(sd, inp.get("session_id"), komut)
        # Kilitli test denetimi yalnız yazma işleci içeren komutta anlamlı; yalnız-okuma komutunda kartları (125 JSON) okuma.
        kgid = kabuk_kilitli_yazma(komut, kilitli_testler(sd)) if _KABUK_YAZMA_ON.search(komut) else None
        if kgid:
            reddet(f"kilitli test: komut {kgid} kartının kilitli test dosyasına yazıyor/siliyor. Kilit yalnız ana ajanın "
                   "`orkestra kart test-kilit-ac` komutuyla açılır.")
        _kapi_uygula(kar, kneden)
        # Tırnak içi metin veridir (heredoc dışı argüman, python -c kodu): komut analizinden çıkarılır.
        # İstisna: tırnaklanmış program yolu "…/orkestra.py" korunur (tırnakları atılır).
        yol_acik = re.sub(r'["\']([^"\']*orkestra(?:\.py|\.cmd))["\']', lambda m: m.group(1).replace(" ", "_"), komut)
        tirnaksiz = re.sub(r'"(?:\\.|[^"\\])*"|\'[^\']*\'', '""', yol_acik)
        if arac == "Bash" and _PS_CMDLET.search(tirnaksiz):  # Bash'e PowerShell sözdizimi: engellenmez, davranış hatası olarak kaydedilir
            _davranis_yaz("kabuk-sozdizimi", komut[:120])
        _onay_kapisi(sd, inp.get("session_id"), L.proje_dizini(inp.get("cwd")), tirnaksiz=tirnaksiz)
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

def _denetim_basladi(sd: str, gorev: str, aid, tip) -> None:
    """Denetçi başlayınca karta 'denetim-basladi' olayı: 'is-bitti → denetim kararı' süresi denetçi başlayana
    kadar bekleme, sonrası denetçi çalışması diye ayrılabilsin. Aynı is-bitti için ilk başlangıç sayılır."""
    try:
        with L.kilit(L.kart_yolu(sd, gorev)):
            k = L.kart_oku(sd, gorev)
            if not k or L.kart_durumu_hesapla(k) != "denetimde":
                return
            for g in reversed(k.get("gecmis") or []):
                if g.get("olay") == "denetim-basladi":
                    return
                if g.get("olay") == "is-bitti":
                    break
            k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": "denetim-basladi", "ajan": tip, "agent_id": aid})
            L.kart_yaz(sd, k)
    except Exception:
        pass


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
    if str(inp.get("agent_type") or "").endswith("denetci"):
        _denetim_basladi(sd, gorev, aid, inp.get("agent_type"))
    try:
        import subprocess
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "orkestra.py"), "defter", "baglam", gorev, "--max", "1800"],
                             capture_output=True, text=True, encoding="utf-8", timeout=8, cwd=L.proje_dizini(inp.get("cwd")), **cfg.PENCERESIZ).stdout
    except Exception:
        out = ""
    try:  # ADR-0068: best in class yöntemi işçi görevin başında bağlamda olur (denetçi hariç); hata hook'u düşürmez
        import yontem_enjeksiyonu
        yontem = yontem_enjeksiyonu.isci_metni(inp.get("agent_type"), sd, inp.get("session_id"))
    except Exception:
        yontem = ""
    try:  # ADR-0101: işçi görevde hata görürse kök neden önce yöntemi (denetçi hariç)
        import kok_neden_enjeksiyonu
        kok = kok_neden_enjeksiyonu.isci_metni(inp.get("agent_type"), sd, inp.get("session_id"))
        if kok:
            yontem = (yontem + "\n" if yontem else "") + kok
    except Exception:
        pass
    if out.strip() or yontem:
        ek = (yontem + "\n") if yontem else ""
        if out.strip():
            ek += "Orkestra bağlamı (yalnız ihtiyacın olan kayıtlar):\n" + out[:1900 - len(ek)]
        L.hook_cikti({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": ek}})
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
    """Oturumun bağlı işi; çözüm ork_lib.is_coz'dadır (niyet bağlamı dahil edilmez: bağlılık kontrolü)."""
    v, _n = L.is_coz(sd, oid, "-", niyet_dahil=False)
    return v if v and v != "-" else None


def _hata_yaz(sd: str, yer: str, e: Exception) -> None:
    """Kancayı düşürmeyen ama sessiz de kalmayan hata: gunluk.jsonl'e 'hook-hatasi' satırı."""
    try:
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "tur": "hook-hatasi", "olay": yer,
                                                         "hata": f"{type(e).__name__}: {e}"[:300]})
    except Exception:
        pass
    try:   # ADR-0035: imzalı hata defteri; kayıt hatası kancayı düşürmez
        import hata_kayit as HK
        HK.kaydet(sd, "hook", type(e).__name__, str(e), {"yer": yer})
    except Exception:
        pass


def _zaman_ekle(sd: str, kayit: dict) -> None:
    """zaman.jsonl'e tek satır (T-06); hata kancayı düşürmez, günlüğe yazılır."""
    try:
        L.jsonl_ekle(os.path.join(sd, "zaman.jsonl"), kayit)
    except Exception as e:
        _hata_yaz(sd, "zaman_ekle", e)


def _arac_satirlari_ekle(sd: str, oturum, ozet: dict, kimlik: dict, ek: dict) -> None:
    """I-030 P4: her araç çağrısı için zaman.jsonl'e tur='arac' satırı, tek toplu yazımla.
    ust_span_id turun (ana/alt) span_id'sidir; token alanları mesaj usage'ının paylaştırılmış tahminidir.
    Hata kancayı düşürmez, gunluk'e 'hook-hatasi' yazılır."""
    try:
        izler = ozet.get("arac_izleri") or []
        if not izler:
            return
        ust = kimlik.get("span_id")
        zaman = L.simdi()
        satirlar = []
        for n, iz in enumerate(izler, 1):
            satirlar.append({"zaman": zaman, "oturum": oturum, **ek, "tur": "arac", "arac": iz.get("arac"),
                             "span_id": f"{ust}.c{n}" if ust else None,  # istek yoksa kimlik alanları boş (P1)
                             "ust_span_id": ust, "istek_id": kimlik.get("istek_id"), "sure_ms": iz.get("sure_ms"),
                             "giris": iz.get("giris", 0), "cikis": iz.get("cikis", 0),
                             "onbellek_okuma": iz.get("onbellek_okuma", 0), "onbellek_yazma": iz.get("onbellek_yazma", 0),
                             "tahmin": True})
        L.jsonl_toplu_ekle(os.path.join(sd, "zaman.jsonl"), satirlar)
    except Exception as e:
        _hata_yaz(sd, "arac_satirlari", e)


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
    surec = L.surec_turet(atip, surec)
    # Sayaç modülünün (maliyet tur) aynı ajanı görev/süreç/tip ile eşleyebilmesi için önbellek.
    if gorev != "-":
        L.atomik_yaz(os.path.join(sd, "oturumlar", f"ajan_{aid}.json"), json.dumps({"gorev": gorev, "surec": surec, "ajan": atip, "baglam": baglam}))
    kimlik = L.istek_kimlik_alanlari(sd, inp.get("session_id"), agent_id=aid)
    taban = {"zaman": L.simdi(), "oturum": inp.get("session_id"), "gorev": gorev, "surec": surec, "baglam": baglam, "ajan": atip,
             "agent_id": aid, "sure_ms": L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"]), "tur": ozet["tur"],
             "arac_cagrisi": ozet["arac_cagrisi"], "perspektif": bool(os.environ.get("ORKESTRA_PERSPEKTIF")), "kaynak": "hook",
             "araclar": dict(ozet["araclar"]), "arac_hata": ozet["arac_sayilari"]["arac_hata"],
             "tekrar_okuma": ozet["arac_sayilari"]["tekrar_okuma"],
             **L.is_alanlari(sd, inp.get("session_id"), gorev),
             **kimlik}
    _maliyet_satirlari(sd, ozet, taban)
    _zaman_ekle(sd, {"zaman": L.simdi(), "oturum": inp.get("session_id"), "is": taban["is"], "tur": "alt", "agent_id": aid,
                     **({"atif_nedeni": taban["atif_nedeni"]} if taban.get("atif_nedeni") else {}),
                     "ajan": atip, "gorev": gorev, "sure_ms": taban["sure_ms"], **kimlik})
    _arac_satirlari_ekle(sd, inp.get("session_id"), ozet, kimlik, {"is": taban["is"], "agent_id": aid, "gorev": gorev})
    ana_model = max(ozet["modeller"].items(), key=lambda x: x[1]["maliyet_usd"])[0] if ozet["modeller"] else "-"
    ilk = re.sub(r"#(GOREV|SUREC):\S+", "", ozet["ilk_kullanici"] or "").strip().replace("\n", " ")
    L.defter_ekle(sd, {"oturum": inp.get("session_id"), "gorev": gorev, "surec": surec, "baglam": baglam, "ajan": atip, "agent_id": aid, "model": ana_model,
                       "yaptim": meta.get("description") or ilk[:200], "sonuc": (inp.get("last_assistant_message") or "")[:600],
                       "dokunulan": ozet["dokunulan"], "token": ozet["toplam"], "kaynak": "hook", **kimlik})
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
                    # Devam ettirilen (resume) ajanın transkripti kümülatiftir: aynı ajanın önceki durağında eklenen
                    # kısım düşülür, karta yalnız fark eklenir (token_ajan: ajan başına son kümülatif değer).
                    t = ozet["toplam"]
                    simdiki = {"giris": t["giris"] + t["onbellek_okuma"] + t["onbellek_yazma"], "cikis": t["cikis"],
                               "maliyet_usd": t["maliyet_usd"]}
                    onceki = k.setdefault("token_ajan", {}).get(aid) or {"giris": 0, "cikis": 0, "maliyet_usd": 0.0}
                    k["token"]["giris"] += max(0, simdiki["giris"] - onceki["giris"])
                    k["token"]["cikis"] += max(0, simdiki["cikis"] - onceki["cikis"])
                    k["token"]["maliyet_usd"] = round(k["token"]["maliyet_usd"] + max(0.0, simdiki["maliyet_usd"] - onceki["maliyet_usd"]), 6)
                    k["token_ajan"][aid] = simdiki
                    k["gecmis"].append({"zaman": L.simdi(), "olay": "ajan-bitti", "ajan": atip, "agent_id": aid, "surec": surec})
                    L.kart_yaz(sd, k)
    except Exception as e:  # bozuk kart dosyası kancayı düşürmesin; günlüğe yazılır
        _hata_yaz(sd, "subagent_kart", e)
    gec()


# ---------------------------------------------------------------- Stop (ana ajan)

_BILDIRIM_ID = re.compile(r"<tool-use-id>\s*([^<\s]+)\s*</tool-use-id>")
_BILDIRIM_BITTI = re.compile(r"<status>\s*(?:completed|failed|killed|stopped)\s*</status>")
ACIK_GOREV_AZAMI = 50


def _sonuc_metni(icerik) -> str:
    """tool_result içeriği (metin ya da blok listesi) düz metin."""
    if isinstance(icerik, str):
        return icerik
    if isinstance(icerik, list):
        return " ".join(str(x.get("text") or "") for x in icerik if isinstance(x, dict))
    return ""


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
                    if (isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in ("Agent", "Bash", "Workflow")
                            and isinstance(b.get("input"), dict) and b["input"].get("run_in_background") is True
                            and b.get("id") and b["id"] not in acik):
                        acik.append(b["id"])
            elif o.get("type") == "user":
                metin = icerik if isinstance(icerik, str) else json.dumps(icerik, ensure_ascii=False)
                if isinstance(icerik, list):  # zaman aşımıyla arka plana düşen komut: bildirimi gelene kadar açık görev
                    import genis_tarama_hatirlatma as _gt
                    for b in icerik:
                        kim = b.get("tool_use_id") if isinstance(b, dict) and b.get("type") == "tool_result" else None
                        if kim and kim not in acik and _gt.arka_plana_dustu_mu(_sonuc_metni(b.get("content"))):
                            acik.append(kim)
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
            _bagli_agacta_satirlari_kaydet(sd, oid, yol)  # ADR-0038: bağlı worktree'de özet satırı + commit
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
                try:  # sıralı işte todo yazımı plan tamamlanana kadar reddedilir (P-005): hatırlatma güncel adımı söylesin
                    import is_sirasi as SR
                    if SR.sirali_mi(klasor):
                        adim, _ = SR.adim(klasor)
                        if adim != "todo":
                            msg = (f"Orkestra: {is_id} sıralı iş (P-005); şu an adım: {adim}. "
                                   f"Durum ve eksikler: `orkestra is sira {is_id}`; todo.md plan tamamlanınca yazılır.")
                except Exception:
                    pass
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


def _sm(*parca: str) -> str:
    """Stop çıkışı: K-003 bağlantı satırları (ADR-0040) varsa diğer sistem mesajlarının önüne eklenir."""
    return chr(10).join(x for x in (_KULLANICI_MESAJI, *parca) if x)


def _pre_gosterilenler(sd: str, oid) -> str:
    """PreToolUse kapısının bu turda gösterdiği satırlar (bir kez okunur, silinir); Stop aynı belgeyi tekrarlamasın."""
    yol = os.path.join(sd, "oturumlar", f"{oid}.baglanti.json")
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        gosterilen = d.pop("gosterilen", None) or []
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(d, f)
        return chr(10).join(gosterilen)
    except (OSError, ValueError):
        return ""


def _baglanti_kapisi(sd: str, oid, inp: dict, ozet: dict) -> None:
    """K-003 (Ö3, ADR-0040): bu turda dokunulan okunacak belgenin yanıtta bağlantısı yoksa golge: `gunluk.jsonl`'a
    kural_ihlal / belge_baglantisi_yok; ihlal: satırları hook kullanıcıya `systemMessage` ile gösterir (tur bloklanmaz,
    model satır yazmaz; PreToolUse'ta gösterilen belge tekrarlanmaz). Bash ile yazılan belgeler `dokunulan`a girmez.
    Hatada sessiz geçer."""
    global _KULLANICI_MESAJI
    try:
        import belge_bicim as BB
        gosterilen = _pre_gosterilenler(sd, oid)
        ayar = BB.ayar_oku(sd)
        eksik = BB.baglantisiz_belgeler(ozet.get("dokunulan"), inp.get("last_assistant_message"), ayar)
        if not eksik:
            return
        kip = BB.mod(ayar, "baglanti_kapisi")
        proje = L.proje_dizini(inp.get("cwd"))
        goreli = [_rel(proje, os.path.abspath(os.path.join(inp.get("cwd") or os.getcwd(), y))) or y for y in eksik]
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {
            "zaman": L.simdi(), "oturum": oid, "tur": "kural_ihlal", "kural": "belge_baglantisi_yok", "mod": kip,
            "dosyalar": goreli[:8], "adet": len(goreli), "is": _oturum_isi(sd, oid)})
        if kip == "ihlal":
            import is_kaydi
            satirlar = [is_kaydi.baglanti_satiri(
                "belge", os.path.abspath(os.path.join(inp.get("cwd") or os.getcwd(), y)),
                L.baglanti_koku(proje, inp.get("cwd"))) for y in eksik[:6]]
            satirlar = [x for x, g in zip(satirlar, goreli) if g not in gosterilen]
            if satirlar:
                _KULLANICI_MESAJI = "Orkestra belgeleri:" + chr(10) + chr(10).join(satirlar)
    except SystemExit:
        raise
    except Exception:
        return


def _kimlik_kapisi_yanit(sd: str, oid, inp: dict) -> None:
    """P-023: yanıt 'kimlik/erişim yok, bekleniyor, kullanıcı eklemeli' diyorsa kimlik klasörüne bakılmadan tur bitmez.
    Her kipte günlüğe `kural_ihlal / kimlik_once_bak` yazılır; `block` kipinde tur başına bir kez block (`stop_hook_active`
    döngüyü keser). Kalıplar ayarda (`ayarlar/kimlik_hatirlatma.json`); hatada sessiz geçer."""
    try:
        import kimlik_hatirlatma as KH
        if not KH.yanit_ihlali(inp.get("last_assistant_message"), sd):
            return
        kayar = KH.ayar_oku(sd)
        kip = KH.mod(kayar)
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oid, "tur": "kural_ihlal",
                                                         "kural": "kimlik_once_bak", "mod": kip, "is": _oturum_isi(sd, oid),
                                                         **_kalip_kaniti(kayar.get("yanit_kaliplari"), inp.get("last_assistant_message"),
                                                                         KH._normallestir)})
        if kip == "block" and not inp.get("stop_hook_active"):
            L.hook_cikti({"decision": "block", "reason": KH.hatirlatma_metni(sd)})
    except SystemExit:
        raise
    except Exception:
        return


def _secim_kapisi_yanit(sd: str, oid, inp: dict) -> None:
    """P-029: yanıt kullanıcıya düz metinle seçim yaptırıyor ama turda seçim ekranı aracı çağrılmadıysa ihlaldir.
    Her kipte günlüğe `kural_ihlal / secim_ekrani` yazılır; varsayılan kip `golge` (engellemez), `block` kipinde tur başına
    bir kez block (`stop_hook_active` döngüyü keser). Kalıplar ayarda (`ayarlar/secim_ekrani_hatirlatma.json`); hatada sessiz geçer."""
    try:
        import secim_ekrani_hatirlatma as SH
        import izin_politikasi
        if izin_politikasi._auto_modu(sd, oid):  # ADR-0086: /auto kullanıcıya seçim yaptırmaz, ekran hatırlatması susar
            return
        tetik = SH.yapisal_tetik(inp.get("transcript_path"), inp.get("last_assistant_message"), sd)
        if tetik:
            ykip = SH.yapisal_mod(SH.ayar_oku(sd))
            L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oid, "tur": "kural_ihlal",
                                                             "kural": "secim_ekrani_yapisal", "mod": ykip, "tetik": tetik,
                                                             "is": _oturum_isi(sd, oid), **_kanit(tetik)})
            if ykip == "block" and not inp.get("stop_hook_active"):
                L.hook_cikti({"decision": "block", "reason": SH.hatirlatma_metni(sd)})
        if not SH.yanit_ihlali(inp.get("last_assistant_message"), sd) or SH.secim_ekrani_sunuldu(inp.get("transcript_path"), sd):
            return
        sayar = SH.ayar_oku(sd)
        kip = SH.mod(sayar)
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oid, "tur": "kural_ihlal",
                                                         "kural": "secim_ekrani", "mod": kip, "is": _oturum_isi(sd, oid),
                                                         **_kalip_kaniti(sayar.get("yanit_kaliplari"),
                                                                         SH._kodsuz(inp.get("last_assistant_message") or ""),
                                                                         SH._normallestir)})
        if kip == "block" and not inp.get("stop_hook_active"):
            L.hook_cikti({"decision": "block", "reason": SH.hatirlatma_metni(sd)})
    except SystemExit:
        raise
    except Exception:
        return


def _kabuk_sozdizimi_yanit(sd: str, oid, inp: dict) -> None:
    """ADR-0102, P-043: yanıttaki kabuk kod bloğunda kullanıcı profiline yasak kalıp varsa günlüğe
    `kural_ihlal / kabuk_sozdizimi` yazılır. Yalnız golge (engellemez); hatada sessiz geçer."""
    try:
        import kabuk_profili as KP
        bulunan = KP.yanit_ihlalleri(inp.get("last_assistant_message"), sd)
        if bulunan:
            ayar = KP.ayar_oku(sd)
            L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oid, "tur": "kural_ihlal",
                                                             "kural": KP.KURAL, "mod": KP.stop_kip(ayar),
                                                             "profil": KP.profil_sec(ayar), "kalip": bulunan,
                                                             "is": _oturum_isi(sd, oid)})
    except SystemExit:
        raise
    except Exception:
        return


def _kanitsiz_iddia_yanit(sd: str, oid, inp: dict) -> None:
    """P-021 / ADR-0085: bilgi sorusu turunda kanıt aracı çağrılmadan, kaynak türü anılmadan olgu iddiası yazıldıysa
    her kipte günlüğe `kural_ihlal / kanitsiz_iddia` yazılır. Kullanıcıya deterministik (model çağrısız) `systemMessage`
    uyarısı yalnız ayarda `uyari_acik` iken (holdout kesinliği eşiği geçince) ya da `block` kipinde gider; `block` kipinde
    tur başına bir kez block (`stop_hook_active` döngüyü keser). Ayar `ayarlar/kanitsiz_iddia.json`; hatada sessiz geçer."""
    global _KULLANICI_MESAJI
    try:
        import kanitsiz_iddia as KI
        ayar = KI.ayar_oku(sd)
        kip = KI.mod(ayar)
        if kip == "kapali":
            return
        bulgu = KI.degerlendir(inp.get("transcript_path"), inp.get("last_assistant_message"), sd)
        if not bulgu:
            return
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oid, "tur": "kural_ihlal",
                                                         "kural": KI.KURAL, "mod": kip, "is": _oturum_isi(sd, oid),
                                                         **(_kalip_kaniti(ayar.get("tetik_kaliplari"), bulgu.get("alinti"),
                                                                          KI._normallestir) or _kanit(None, bulgu.get("alinti")))})
        if KI.uyari_acik(ayar):
            uyari = KI.uyari_metni(bulgu["alinti"], ayar)
            _KULLANICI_MESAJI = chr(10).join(x for x in (_KULLANICI_MESAJI, uyari) if x)
        if kip == "block" and not inp.get("stop_hook_active"):
            blok = {"decision": "block", "reason": ayar.get("hatirlatma", "")}
            if _KULLANICI_MESAJI:
                blok["systemMessage"] = _KULLANICI_MESAJI
            L.hook_cikti(blok)
    except SystemExit:
        raise
    except Exception:
        return


def _cikti_butce_yanit(sd: str, oid, inp: dict) -> None:
    """P-001 / ADR-0075: turun sohbet metni ölçülür. Her turda günlüğe `cikti_olcum` (rapor ortanca ve p90'ı bundan hesaplar),
    sınır aşımında `kapi_golge / cikti_butce` düşer; gölge modda engellemez. Ayar `ayarlar/cikti_butce.json`; hatada sessiz geçer."""
    try:
        import cikti_butce as CB
        ayar = CB.ayar_oku(sd)
        if not CB.acik(ayar):
            return
        olcum = CB.tur_olc(inp.get("transcript_path"), tuple(ayar.get("kutu_araclari") or ("wrap_up",)),
                           inp.get("last_assistant_message"))
        if not olcum:
            return
        yol, is_id = os.path.join(sd, "gunluk.jsonl"), _oturum_isi(sd, oid)
        L.jsonl_ekle(yol, {"zaman": L.simdi(), "oturum": oid, "tur": "cikti_olcum", "toplam": olcum["toplam"],
                           "kapanis": olcum["kapanis"], "is": is_id})
        nedenler = CB.asimlar(olcum, ayar)
        if nedenler:
            L.jsonl_ekle(yol, {"zaman": L.simdi(), "oturum": oid, "tur": "kapi_golge", "kapi": CB.KAPI, "is": is_id,
                               "neden": "; ".join(nedenler)})
    except SystemExit:
        raise
    except Exception:
        return


def _kapanis_kapisi(sd: str, oid, inp: dict) -> None:
    """P-009 tetik anı: bağlı işin tüm todo maddeleri bitti ama iş hâlâ açıksa tur bitmeden özet ve kapatma istenir.
    Tur başına bir kez block (`stop_hook_active` döngüyü keser); ORKESTRA_KAPANIS_KAPISI=0 kapatır. Hatada sessiz geçer."""
    if os.environ.get("ORKESTRA_KAPANIS_KAPISI") == "0" or inp.get("stop_hook_active"):
        return
    try:
        import is_kaydi
        from komutlar import isler
        is_id = _oturum_isi(sd, oid)
        if not is_id:
            return
        g = next((x for x in is_kaydi.is_liste(sd) if x.get("id") == is_id), None)
        if not g or g.get("durum") != "acik" or not g.get("klasor"):
            return
        t = is_kaydi.todo_ozet(g["klasor"])
        if not t["toplam"] or t["acik_maddeler"]:
            return
        adim = (f"`orkestra is belge {is_id} ozet` ile çalışma özetini doldur, sonra " if isler._ozet_eksigi(g["klasor"]) else "")
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oid, "tur": "kural_ihlal",
                                                         "kural": "kapanis_atlandi", "is": is_id,
                                                         **_kanit("todo_tamam_is_acik", f"{is_id} todo {t['biten']}/{t['toplam']} bitti, iş açık")})
        L.hook_cikti({"decision": "block", "reason":
                      f"Orkestra (P-009): {is_id} todo {t['biten']}/{t['toplam']} bitti ama iş açık. Turu bitirmeden önce: "
                      f"{adim}`orkestra is kapat {is_id}`. İş sürecekse `orkestra is todo {is_id} --ekle \"madde\"` ile yeni madde yaz."})
    except SystemExit:
        raise
    except Exception:
        return


def arka_plan_satiri(sd: str, gorevler) -> str:
    """Tur bitince tek satır: arka planda süren görevler (Claude görevleri + perspektif koşusu + onay uygulaması).
    Deterministik, model çağrısı yok; süren yoksa boş metin, hatada sessiz."""
    adlar = []
    try:
        for g in gorevler if isinstance(gorevler, list) else []:
            ad = ""
            if isinstance(g, dict):
                for anahtar in ("description", "title", "name", "summary", "command"):
                    if isinstance(g.get(anahtar), str) and g[anahtar].strip():
                        ad = g[anahtar].strip()
                        break
            elif isinstance(g, str):
                ad = g.strip()
            adlar.append(" ".join(ad.split())[:40] or "görev")
    except Exception:
        pass
    try:
        import perspektif
        if perspektif.durum(sd).get("calisiyor"):
            adlar.append("Perspektif koşusu")
    except Exception:
        pass
    try:
        import onay
        if onay.uygulama_durumu(sd):
            adlar.append("Onaylı kararlar uygulanıyor")
    except Exception:
        pass
    if not adlar:
        return ""
    gosterilen = ", ".join(adlar[:3]) + (f" +{len(adlar) - 3}" if len(adlar) > 3 else "")
    return f"Arka planda sürüyor ({len(adlar)}): {gosterilen}"


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
    perspektif = bool(os.environ.get("ORKESTRA_PERSPEKTIF"))
    kimlik = {} if perspektif else L.istek_kimlik_alanlari(sd, oid, tur_arttir=True)
    if not perspektif and ozet.get("ilk_zaman"):
        _sure = L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"])
        _zaman_ekle(sd, {"zaman": L.simdi(), "oturum": oid, **L.is_alanlari(sd, oid, "-"), "tur": "ana",
                         "sure_ms": _sure, "etkin_ms": ES.etkin_ms(_sure, sd), "istek_zamani": ozet["ilk_zaman"], **kimlik})
        _arac_satirlari_ekle(sd, oid, ozet, kimlik, {"is": L.is_alanlari(sd, oid, "-").get("is")})
    ajan = "perspektif-bakimcisi" if perspektif else "ana-ajan"
    surec = "perspektif" if perspektif else "orkestrasyon"
    if ozet["modeller"]:
        taban = {"zaman": L.simdi(), "oturum": oid, "gorev": "-", "surec": surec, "baglam": baglam, "ajan": ajan, "agent_id": None,
                 "sure_ms": L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"]), "tur": ozet["tur"],
                 "arac_cagrisi": ozet["arac_cagrisi"], "perspektif": perspektif, "kaynak": "hook",
                 **L.is_alanlari(sd, oid, "-"), **kimlik}
        _maliyet_satirlari(sd, ozet, taban)
        if not perspektif:
            try:  # I-271: pahalı tur (önbellek okuması eşik üstü) → sonraki mesaja devir ipucu; hata kancayı düşürmez
                import devir_esigi
                devir_esigi.tur_kaydet(sd, oid, (ozet.get("toplam") or {}).get("onbellek_okuma", 0))
            except Exception:
                pass
    # Ofset en son ilerler: maliyet/zaman satırı yazılamazsa tur bir sonraki durakta yeniden okunur (satır kaybolmaz).
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
    kayda_deger = any(a in ozet["araclar"] for a in ("Agent", "Task", "Workflow")) or ozet["dokunulan"]
    if kayda_deger and ozet["modeller"]:
        araclar = ", ".join(f"{k}×{v}" for k, v in sorted(ozet["araclar"].items(), key=lambda x: -x[1])[:6])
        L.defter_ekle(sd, {"oturum": inp.get("session_id"), "gorev": "-", "surec": surec, "baglam": baglam, "ajan": ajan, "model": max(ozet["modeller"].items(), key=lambda x: x[1]["maliyet_usd"])[0],
                           "yaptim": f"Tur: {ozet['arac_cagrisi']} araç çağrısı ({araclar})",
                           "sonuc": (inp.get("last_assistant_message") or "")[:400], "dokunulan": ozet["dokunulan"],
                           "token": ozet["toplam"], "kaynak": "hook", **kimlik})
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
    if not perspektif:
        try:  # konu dışı öneri kalıbı: yalnız ölçüm kaydı (ek token yok, kullanıcıya gürültü yok)
            import soru_sinif
            if soru_sinif.yanit_ihlali(inp.get("last_assistant_message"), sd):
                L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oid, "tur": "kural_ihlal",
                                                                 "kural": "konu_disi_oneri", "is": _oturum_isi(sd, oid),
                                                                 **_kalip_kaniti(soru_sinif.ayar_oku(sd).get("yanit_yasak_kaliplari"),
                                                                                 inp.get("last_assistant_message"),
                                                                                 soru_sinif._normallestir)})
        except Exception:
            pass
    if not perspektif:
        _baglanti_kapisi(sd, oid, inp, ozet)
        _kimlik_kapisi_yanit(sd, oid, inp)
        _secim_kapisi_yanit(sd, oid, inp)
        _kabuk_sozdizimi_yanit(sd, oid, inp)
        _kanitsiz_iddia_yanit(sd, oid, inp)
        _cikti_butce_yanit(sd, oid, inp)
        _kapanis_kapisi(sd, oid, inp)
    # Bitiş kapısı: bu oturumun açık kartları
    if perspektif:
        gec()
    if inp.get("background_tasks"):
        satir = arka_plan_satiri(sd, inp.get("background_tasks"))
        if satir:
            L.hook_cikti({"systemMessage": _sm(satir)})
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
        satir = arka_plan_satiri(sd, None)  # görev listesi boş; yalnız perspektif/onay uygulaması sürüyorsa
        mesaj = _sm(" ".join(x for x in (satir, hatirlatma) if x))
        if mesaj:
            L.hook_cikti({"systemMessage": mesaj})
        gec()
    liste = "; ".join(f"{g} [{d}] {b[:50]}" for g, d, b in acik)
    ek = f" {hatirlatma}" if hatirlatma else ""
    if inp.get("stop_hook_active"):
        L.hook_cikti({"systemMessage": _sm(f"Orkestra: açık kartlar kaldı → {liste}{ek}")})
    blok = {"decision": "block", "reason":
                  f"Orkestra bitiş kapısı: bu oturumun açık kartları var → {liste}. "
                  "onaylandi → sonucu topla ve `orkestra kart teslim <id>`; denetimde → ayrı denetçiyi çalıştır; "
                  "reddedildi → düzeltme/yükseltme yap; bilerek bırakıyorsan `orkestra kart durum <id> beklemede --not \"neden\"`." + ek}
    if _KULLANICI_MESAJI:
        blok["systemMessage"] = _KULLANICI_MESAJI
    L.hook_cikti(blok)


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


ESLEME_AYAR_YOLU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "is_esleme.json")


def _esleme_ayari(sd: str) -> dict:
    """İstek-iş eşleme eşikleri: eklenti `ayarlar/is_esleme.json`, üstüne proje `<durum>/is_esleme.json` (anahtar bazında).
    Bozuk/eksik dosya atlanır; doğrulamayı is_yonlendirme._ayar yapar."""
    ayar = {}
    for yol in (ESLEME_AYAR_YOLU, os.path.join(sd, "is_esleme.json")):
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                ayar.update(d)
        except Exception:
            continue
    return ayar


BAGSIZ_SECIM = ("Bu sohbet bir işe bağlı değil; ilk araç çağrısından önce `orkestra is devam <id>` ya da "
                "`orkestra is ac \"<başlık>\" --klasor <klasör>` ile kullanıcıya sormadan kendin bağlan (bağlanmadan dosya yazılamaz).")


def _bagsiz_secim_satiri(acik: list, puanlar: list, idler=None, devam: bool = False, bas: str = BAGSIZ_SECIM) -> str:
    """Bağsız oturum seçim satırı: en yakın en çok iki iş + bağlanma komutları (P2 'sec', devam türü)."""
    basliklar = {str(g.get("id")): str(g.get("baslik") or "") for g in acik}
    sira = [str(i) for i in (idler or [])] + [str(p.get("id")) for p in puanlar or [] if isinstance(p, dict)] \
        + list(reversed(list(basliklar)))  # puan yoksa en yeni işler
    secim = []
    for i in sira:
        if i in basliklar and i not in secim:
            secim.append(i)
        if len(secim) == 2:
            break
    s = ("Bağsız oturum: kısa/devam mesajında iş açılmadı. " if devam else "") + bas
    if secim:
        s += " En yakın işler: " + "; ".join(f"{i} {basliklar[i][:40]}" for i in secim) + "."
    return s


def _otomatik_is_ac(sd: str, oid, istek: str, proje: str | None = None, etiketler=None, is_id: str | None = None,
                    cwd: str | None = None) -> str:
    """Bağsız oturumu işe bağlar; `is_id` yoksa önce yeni iş açar (kayıp 7ce7e69'un bugünkü hook'a uyarlaması).
    Klasör: eşlemedeki ilk proje altında sıradaki NNN-YYYYMMDD-<slug>; yazılamazsa <durum dizini>/isler altında aynı ad.
    Önce is.json oturumlar[] (is_oturum_bagla), sonra oturum json'u (kilitli oku-birleştir-yaz). Hatada boş: ipucu yolu sürer."""
    try:
        import baglam
        import is_kaydi
        baslik = is_kaydi.baslik_uret(istek)
        klasor = ""
        if is_id:
            kayit = is_kaydi.is_al(sd, is_id)
            if not kayit:
                return ""
        else:
            projeler = [str(p) for p in ((baglam.esleme_oku(sd) or {}).get("projeler") or []) if str(p).strip()]
            yedek_kok = os.path.join(sd, "isler")
            kok = (os.path.normpath(os.path.join(L.baglanti_koku(proje or L.proje_dizini(cwd), cwd),
                                                 projeler[is_kaydi.proje_sec(projeler, istek)]))
                   if projeler else yedek_kok)
            try:
                ad = is_kaydi.klasor_ayir(sd, kok, baslik)
            except OSError:
                if os.path.normcase(os.path.normpath(kok)) == os.path.normcase(os.path.normpath(yedek_kok)):
                    raise
                kok = yedek_kok
                ad = is_kaydi.klasor_ayir(sd, kok, baslik)
            klasor = os.path.join(kok, ad)
            try:
                kayit = is_kaydi.is_ac(sd, baslik, klasor, etiketler)
            except OSError:
                if os.path.normcase(os.path.normpath(kok)) == os.path.normcase(os.path.normpath(yedek_kok)):
                    raise
                klasor = os.path.join(yedek_kok, ad)
                kayit = is_kaydi.is_ac(sd, baslik, klasor, etiketler)
        is_kaydi.is_oturum_bagla(sd, kayit["id"], str(oid))
        yol = os.path.join(sd, "oturumlar", f"{oid}.json")
        with L.kilit(yol):
            try:
                with open(yol, encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:
                d = {}
            d = d if isinstance(d, dict) else {}
            an = L.simdi()
            d["is"], d["is_baglanma"] = kayit["id"], an
            d.setdefault("is_gecmis", []).append({"is": kayit["id"], "zaman": an})
            L.atomik_yaz(yol, json.dumps(d, ensure_ascii=False, indent=2) + "\n")
        L.atif_yaz(sd, str(oid), kayit["id"], "hook-otomatik-baglama")  # bağsız maliyet satırları için tek atif olayı
        if is_id:
            return (f"Orkestra: bu sohbet otomatik bağlandı {kayit['id']} — {str(kayit.get('baslik') or '')[:50]} "
                    "(istek bu işle örtüşüyor). Yanlışsa `orkestra is devam <id>` ya da `orkestra is ac` ile değiştir.")
        etiket = f" [etiket: {', '.join(etiketler)}]" if etiketler else ""
        return (f"Yeni iş otomatik açıldı: {kayit['id']} — {baslik[:50]}{etiket} (klasör: {os.path.basename(klasor)}); "
                "bu sohbet ona bağlandı. Sıradaki adımlar işin todo.md'sine yazılır.")
    except Exception:
        return ""


def _otomatik_yonlendirme(sd: str, oid, istek: str, proje: str | None = None, cwd: str | None = None) -> str:
    """P2-P3: bağsız oturumda her gerçek mesajda eslestir+karar: bagla → bağlar, ac → yeni iş (soru türü 'soru'
    etiketli) açıp bağlar, sec → en yakın iki iş + seçim satırı; devam türünde iş açılmaz. Bağlı oturumda, boş
    mesajda ya da bozuk merkez kayıtta çalışmaz (''). Hata/başarısız açma → '' (çağıran ipucu yoluna düşer)."""
    try:
        if not oid or not str(istek or "").strip() or _oturum_isi(sd, oid):
            return ""
        import is_kaydi
        import is_yonlendirme
        import soru_sinif
        if is_kaydi.merkez_bozuk_mu(sd):
            return ""
        ayar = _esleme_ayari(sd)
        tur = soru_sinif.tur(istek, sd)
        acik = is_kaydi.is_liste(sd, "acik")
        isler = [{"id": g["id"], "baslik": g.get("baslik") or "", "klasor": os.path.basename(str(g.get("klasor") or ""))}
                 for g in acik]
        puanlar = is_yonlendirme.eslestir(istek, isler, ayar)
        if tur == "devam":
            return _bagsiz_secim_satiri(acik, puanlar, devam=True)
        k, deger = is_yonlendirme.karar(puanlar, ayar)
        acik_idler = {str(g["id"]) for g in acik}
        if k == "bagla" and deger is not None and str(deger) in acik_idler:
            return _otomatik_is_ac(sd, oid, istek, proje, is_id=str(deger), cwd=cwd)
        if k == "ac":
            if tur == "soru":  # I-138 P2: bilgi sorusu iş açmaz
                return ""
            return _otomatik_is_ac(sd, oid, istek, proje, cwd=cwd)
        if k == "sec":  # belirsiz eşleşme kullanıcıya sorulmaz: en yakın açık işe bağlanır
            for i in deger if isinstance(deger, (list, tuple)) else []:
                if str(i) in acik_idler:
                    oto = _otomatik_is_ac(sd, oid, istek, proje, is_id=str(i), cwd=cwd)
                    if oto:
                        return oto
                    break
        return _bagsiz_secim_satiri(acik, puanlar, deger if isinstance(deger, (list, tuple)) else None)
    except Exception:
        return ""


def _bagli_is_kaydi(g: dict) -> dict:
    """Bağlı işin eşleştirme kaydı: kimlik, başlık, klasör adı ve todo.md/plan.md metni (ilk 6000 karakter)."""
    klasor = str(g.get("klasor") or "")
    metin = ""
    for ad in ("todo.md", "plan.md"):
        try:
            with open(os.path.join(klasor, ad), encoding="utf-8") as f:
                metin += " " + f.read(6000)
        except Exception:
            pass
    return {"id": g.get("id"), "baslik": g.get("baslik") or "", "klasor": os.path.basename(klasor), "metin": metin}


def _bagli_isle_ilgili(sd: str, bagli, istek: str) -> bool:
    """Mesaj bağlı işin klasörüne/kimliğine gönderme yapıyor ya da iş metniyle örtüşüyor mu (I-061). Hatada False."""
    try:
        import is_kaydi
        import is_yonlendirme
        for g in is_kaydi.is_liste(sd, "acik"):
            if str(g.get("id")) == str(bagli):
                return is_yonlendirme.isle_ilgili_mi(istek, _bagli_is_kaydi(g), _esleme_ayari(sd))
    except Exception:
        pass
    return False


def _yonlendirme_ipucu(sd: str, oid, istek: str, proje: str | None = None, cwd: str | None = None) -> str:
    """Bağsız oturumda önce otomatik bağla/aç/seç (P2-P3); olmazsa ya da bağlı oturumda: yeni görev mesajında
    (soru/devam değil) açık işler + karar kuralı tek satır (K-004). Hatada boş."""
    oto = _otomatik_yonlendirme(sd, oid, istek, proje, cwd=cwd)
    if oto:
        return oto
    try:
        import soru_sinif
        import is_kaydi
        import is_yonlendirme
        bagli = _oturum_isi(sd, oid)
        if bagli:  # I-061 P1: bağlı oturumda açıkça devam / bağlı işle ilgili mesaj susar, geri kalanı belirsizdir
            if soru_sinif.bagli_tur(istek, sd) != "belirsiz":
                return ""
            if _bagli_isle_ilgili(sd, bagli, istek):
                return ""
        elif soru_sinif.tur(istek, sd) != "is":  # soru ve devam mesajı yönlendirme tetiklemez
            return ""
        isler = [{"id": g["id"], "baslik": g.get("baslik") or ""} for g in is_kaydi.is_liste(sd, "acik")]
        if bagli:  # belirsiz: hatırlatma değil zorunlu yönerge; karşılaştırma güncel konuya (son kayıtlı niyet) yapılır
            import niyet
            k = niyet.son_niyet(oid) if oid else None
            return is_yonlendirme.yonlendir(isler, bagli, zorunlu=True, guncel_konu=(k or {}).get("ne", ""))
        return is_yonlendirme.yonlendir(isler, bagli)
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
    preview_start localhost url'sinde yol kabul etmez: launch.json url'si yalnız origin, kök adrese (panel v2) navigate ile gidilir."""
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
        adres = f"http://127.0.0.1:{port or cfg.panel_port()}/"
        if acik:
            on = ""
        else:
            import panel_servis
            on = ("sunucu kapalı, Task Scheduler görevi kurulu: önce `orkestra panel` çalıştır (görevi başlatır, port sabit); sonra "
                  if panel_servis.kurulu() else
                  "sunucu kapalı, önce `orkestra panel` çalıştır (başka port verirse onu kullan); sonra ")
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
    yol = L.kaynaga_cevir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "KURALLAR.md"))
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


def _niyet_otomatik(sd: str, oturum: str | None, proje: str | None, metin: str) -> None:
    """Niyeti model çağırmadan, hook içinde yazar (token maliyeti sıfır): oturumda niyet yoksa ya da bağlı iş değiştiyse
    kural tabanlı kayıt eklenir. ne = isteğin ilk cümlesi (≤12 kelime), neden = bağlı iş başlığı (yoksa 'kullanıcı isteği').
    Modele talimat verilmez; hata hook'u düşürmez."""
    try:
        if not oturum or not metin.strip():
            return
        import niyet
        k = niyet.son_niyet(oturum)
        bagli = _oturum_isi(sd, oturum)
        if k and (not bagli or k.get("is") == bagli):
            return
        ne = " ".join(L.ne_ozeti(metin).split()[:12])
        if not ne:
            return
        baslik, klasor = "", ""
        if bagli:
            import is_kaydi
            g = is_kaydi.is_al(sd, bagli) or {}
            baslik = str(g.get("baslik") or "")
            klasor = str(g.get("klasor") or "")
        neden = " ".join(f"{bagli} {baslik}".split()[:15]) if bagli else "kullanıcı isteği"
        alan = {"ne": ne, "neden": neden, "baglam": os.path.basename(klasor.rstrip("/\\")), "is": bagli}
        niyet.olay(oturum, proje, "niyet", **alan)
    except Exception:
        pass


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
    """Ana ajan modeli politika (ayarlar/model_politikasi.json) dışındaysa TEK uyarı satırı; politika dosyası yoksa proje ayarındaki
    (`.claude/settings.json` model) aileyle karşılaştırır; aksi halde boş. Hata sessiz."""
    try:
        import model_politika as MP
        if os.path.isfile(MP.AYAR_DOSYASI):
            pol = MP.yukle(None)
            o_model = _oturum_modeli(inp)
            o_aile = _model_ailesi(o_model)
            if not o_model:
                return ""
            vars_ = str((pol.get("ana_ajan") or {}).get("varsayilan") or "")
            yasak = [str(y).lower() for y in (pol.get("yasak") or [])]
            if o_model.lower() in yasak:
                return (f"UYARI: ana ajan modeli YASAK (politika): {o_model[:60]}. Uygulamada {vars_[:60]} seç.")[:250]
            izinli = {_model_ailesi(vars_), _model_ailesi((pol.get("planlayici_yukseltme") or {}).get("model"))} - {""}
            if o_aile and izinli and o_aile not in izinli:
                return (f"UYARI: ana ajan modeli politika dışı: oturum {o_model[:60]}, politika varsayılanı {vars_[:60]}.")[:250]
            return ""
    except Exception:
        pass
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


def _doktor_hizli_yol(inp: dict) -> None:
    """Makine config'i yok / makine değişti / eklenti sürümü değişti ise doktoru arka planda başlatır (I-026 K8). Hata sessiz.
    Proje açık olmasa da çalışır; bu yüzden `session_start` içinde `durum_dizini` denetiminden ÖNCE çağrılır."""
    try:
        import cfg
        if cfg.doktor_gerekli():
            cfg.doktor_baslat(inp.get("cwd") or None)
    except Exception:
        pass


def _otomatik_ac(inp: dict) -> str | None:
    """Orkestra kapalı projede durum klasörünü kendiliğinden kurar (`orkestra baslat` karşılığı); kullanıcı klasörü ve kök
    dizinlerde kurmaz. Git deposunda çalışma zamanı klasörünü `.git/info/exclude`a yazar (.gitignore'a dokunmaz).
    `ORKESTRA_OTOMATIK_ACIL=0` kapatır. Hata sessiz: None döner."""
    try:
        if os.environ.get("ORKESTRA_OTOMATIK_ACIL", "1") == "0":
            return None
        proje = L.proje_dizini(inp.get("cwd"))  # durum_dizini ile aynı çözüm: CLAUDE_PROJECT_DIR > cwd (I-151 G9: kaynaklar ayrışmasın)
        if proje == os.path.abspath(os.path.expanduser("~")) or os.path.dirname(proje) == proje:
            return None
        sd = L.durum_dizini(proje, olustur=True)
        if not sd:
            return None
        rd = os.path.join(sd, "README.md")
        if not os.path.exists(rd):
            from komutlar._ortak import README
            L.atomik_yaz(rd, README)
        r = L.git(["rev-parse", "--git-common-dir"], proje)
        if r.returncode == 0 and r.stdout.strip():
            ortak = r.stdout.strip()
            ortak = ortak if os.path.isabs(ortak) else os.path.join(proje, ortak)
            ex = os.path.join(ortak, "info", "exclude")
            mevcut = open(ex, encoding="utf-8", errors="replace").read() if os.path.exists(ex) else ""
            satirlar = [s for s in (".claude/orkestra/", ".claude/agent-memory-local/") if s not in mevcut.splitlines()]
            if satirlar:
                os.makedirs(os.path.dirname(ex), exist_ok=True)
                with open(ex, "a", encoding="utf-8", newline="\n") as f:
                    f.write(("" if not mevcut or mevcut.endswith("\n") else "\n") + "\n".join(satirlar) + "\n")
        return sd
    except Exception:
        return None


def _perspektif_oto() -> bool:
    """Perspektif yalnız elle başlatılır (`orkestra perspektif baslat`, /orkestra:perspektif); oturum açılışı talimatı ve
    kapanıştaki arka plan koşusu yalnız ORKESTRA_PERSPEKTIF_OTO=1 ile çalışır (I-054)."""
    return os.environ.get("ORKESTRA_PERSPEKTIF_OTO") == "1"


def _kisa(s: str, n: int) -> str:
    """Tek satıra indirir, n karakterden uzunsa '…' ile keser."""
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:max(0, n - 1)].rstrip() + "…"


def _kart_yasi(k: dict, simdi=None) -> str:
    """Beklemedeki kartın yaşı ('6 gün' / '5 sa'): beklemede olayından, yoksa oluşturmadan; okunamazsa boş."""
    import datetime as _dt
    simdi = simdi or _dt.datetime.now().astimezone()
    try:
        z = L._beklemede_konumu(k)[1] or k.get("olusturma") or ""
        t = _dt.datetime.fromisoformat(str(z))
        if t.tzinfo is None:
            t = t.astimezone()
        sa = max(0.0, (simdi - t).total_seconds() / 3600)
    except Exception:
        return ""
    return f"{int(sa // 24)} gün" if sa >= 24 else f"{int(sa)} sa"


def _bekleyen_notu(k: dict, tum: dict) -> str:
    """P7: beklemedeki kart için 'G-107(engeli G-101 teslim)' ya da 'G-107(6 gün; G-101 bekliyor)'.
    Tüm bağımlılıkları teslim olan kart engelsizdir; yoksa yaş ve henüz teslim olmayan bağımlılıklar yazılır."""
    kid = str(k.get("id"))
    bag = [str(b) for b in k.get("bagimliliklar") or []]
    acik = [b for b in bag if (tum.get(b) is None or L.kart_durumu_hesapla(tum[b]) != "teslim")]
    if bag and not acik:
        return f"{kid}(engeli {','.join(bag[:2])} teslim)"
    yas = _kart_yasi(k)
    ek = f"; {','.join(acik[:2])} bekliyor" if acik else ""
    return f"{kid}({yas}{ek})" if (yas or ek) else kid


def _bos_is_satiri(sd: str) -> str:
    """P6: bakim.bos_isler ölçütüne uyan, bos_is_saat (is_esleme.json, varsayılan 48) saatten eski işleri tek satırda listeler.
    Yalnız listeler, hiçbir işin durumunu değiştirmez; hatada boş."""
    try:
        from komutlar import bakim
        try:
            saat = float(_esleme_ayari(sd).get("bos_is_saat", 48))
        except (TypeError, ValueError):
            saat = 48.0
        bos = bakim.bos_isler(sd, saat)
        if not bos:
            return ""
        return (f"boş iş {len(bos)} ({saat:g} saatten eski): " + ", ".join(str(g["id"]) for g in bos[:6])
                + "; kapatmak için orkestra bakim --kapat --uygula")
    except Exception:
        return ""


def _ss_birinci_satir(sd: str, bagli: str | None, ks: list) -> tuple[str, str]:
    """SessionStart 1. satır: bağlı iş (ya da açık iş kimlikleri) + kart özeti; ikinci değer yalnız kapanış/bayat notu olan işlerin satırı.
    Ayrıntı `orkestra is liste` / `orkestra kart liste`."""
    parcalar = []
    not_satiri = ""
    try:  # I-145: onaylı ama teslim edilmemiş kartları topla; stdout hook çıktısı olduğundan yutulur, hata sessiz geçer
        import contextlib
        import io
        from komutlar import kart as _kart_komut
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            teslim, bekleyen = _kart_komut.teslim_bekleyenleri_topla(sd)
        if teslim:
            ks = [k for k in ks if k.get("id") not in teslim]
            parcalar.append(f"Teslim edildi (onaylı, toplanmamıştı): {', '.join(teslim[:4])}")
        if bekleyen:
            parcalar.append(f"Teslim bekliyor: {', '.join(bekleyen[:4])} (`orkestra kart teslim-bekleyen`)")
    except Exception:
        pass
    try:
        import is_kaydi
        acik = is_kaydi.is_liste(sd, "acik")
        notlar = _kapanis_notlari(sd, acik[:5])  # kapanış/bayat notu; yan etki: todo'su biten işi otomatik kapatır
        if notlar:
            ps = []
            for x in acik[:5]:
                if x["id"] in notlar:
                    try:
                        t = is_kaydi.todo_ozet(x.get("klasor") or "")
                        tt = f" todo {t['biten']}/{t['toplam']}"
                    except Exception:
                        tt = ""
                    ps.append(f"{x['id']} {_kisa(x.get('baslik'), 24)}{tt}{notlar[x['id']]}")
            not_satiri = "Açık işler: " + " ; ".join(ps)
        g = next((x for x in acik if bagli and str(x.get("id")) == str(bagli)), None)
        if g:
            p = f"Bağlı iş: {g['id']} {str(g.get('baslik') or '')[:40]}"
            try:
                t = is_kaydi.todo_ozet(g.get("klasor") or "")
                p += f" todo {t['biten']}/{t['toplam']}"
            except Exception:
                pass
            if len(acik) > 1:
                p += f" (+{len(acik) - 1} açık iş)"
            parcalar.append(p)
        elif acik:
            parcalar.append(f"Açık iş {len(acik)}: " + ", ".join(str(x["id"]) for x in acik[:4]) + " (`orkestra is devam <id>`)")
    except Exception:
        pass
    if ks:
        aktif = [k for k in ks if L.kart_durumu_hesapla(k) != "beklemede"]
        bekl = [k for k in ks if L.kart_durumu_hesapla(k) == "beklemede"]
        p = "Kart: " + ", ".join(f"{k['id']} [{L.kart_durumu_hesapla(k)}]" for k in aktif[:3])
        if len(aktif) > 3:
            p += f" +{len(aktif) - 3}"
        if bekl:
            tum = {str(k.get("id")): k for k in L.kartlar(sd)}
            p += (" · " if aktif else "") + f"beklemede {len(bekl)}: " + ",".join(_bekleyen_notu(k, tum) for k in bekl[:5])
        parcalar.append(p + " (`orkestra kart liste`)")
    ilk = "Orkestra bu projede açık. " + ". ".join(parcalar) if parcalar else "Orkestra bu projede açık (`orkestra is liste`)."
    return ilk, not_satiri


def _ss_uyarilar(sd: str, inp: dict) -> tuple[list[str], str]:
    """SessionStart 2. satır girdileri (yalnız koşul sağlanırsa, her biri kısa) ve ayrı satıra giden onay yönergesi. Hatada sessiz."""
    u = []
    onay_ek = ""
    try:
        import onay
        m = onay.baglam_metni(sd, inp.get("session_id"), "SessionStart") or ""
    except Exception:
        m = ""
    km = re.fullmatch(r"Kullanıcının panelde vereceği (\d+) karar bekliyor \(/onaylar\)\.", m.strip())
    if km:
        u.append(f"{km.group(1)} panel kararı bekliyor (/onaylar)")
    elif m:
        onay_ek = m  # onaylı karar uygulama yönergesi: ayrı satır
    a = asili_uyari(sd, inp.get("session_id"))
    if a:
        km = re.search(r"ajan\(lar\): (.*?); takıldıysa", a)
        u.append("bitmeyen ajan: " + _kisa(km.group(1) if km else a, 110) + " → TaskStop")
    ms = _model_sapma_satiri(inp)
    if ms:
        u.append(_kisa(ms, 120))
    try:
        import oturum_bakim
        b = oturum_bakim.onbellek(sd).get("bayatlik") if oturum_bakim.etkin() else L.bayatlik()  # ADR-0092
        if b:
            u.append(f"UYARI: çalışan orkestra kopyası kaynaktan {b['farkli']} dosya farklı; `orkestra guncelle`")
    except Exception:
        pass
    try:
        import maliyet_anomali as MA
        olay = [x for x in MA.calistir(sd, 1) if x["kural"] in ("K3", "K4", "K5")]
        if olay:
            u.append("MALİYET: " + ", ".join(f"{x['kural']} {x['kart']}" for x in olay[:3]) + " (`orkestra maliyet anomali --gun 1`)")
    except Exception:
        pass
    try:
        import hata_en_cok as HE
        hs = HE.esik_satiri(sd)
        if hs:
            u.append(hs)
    except Exception:
        pass
    try:
        import iz as IZ
        if IZ.kapsama_satiri(sd):
            u.append("iz kapsama eşik aşımı (`orkestra iz kapsama`)")
    except Exception:
        pass
    try:
        import is_kaydi
        if is_kaydi.todo_denetle_satiri(sd, L.proje_dizini(inp.get("cwd"))):
            u.append("işe bağlı olmayan todo dosyası var (`orkestra is todo-denetle`)")
        if is_kaydi.devral_ipucu(sd, inp.get("cwd")):
            u.append("worktree durum kopyasında devralınmamış kayıt var (`orkestra durum devral`)")
    except Exception:
        pass
    return u, onay_ek


# SessionStart'ta modele verilen kural çekirdeği: KURALLAR.md'nin (32 KB) tamamı okutulmaz; karar kuralı burada, ayrıntı ilgili bölümde.
_CEKIRDEK = ("Çekirdek: çok adımlı, 3+ dosyalı ya da hatası pahalı iş → /orkestra:is; onayı ayrı denetçi verir; "
             "dosyanın yalnız ilgili bölümünü oku.")


def session_start(inp: dict):
    """SessionStart bağlamı: üç sabit satır (bağlı iş + kart; uyarılar; kurallar yolu + izin kipi), tipik durumda ≤600, en kötü durumda ≤700 karakter.
    Perspektif, panel açma, etki izleme ve onay yönergesi yalnız koşul sağlanınca ayrı satır olarak eklenir."""
    _t0 = time.perf_counter()
    _doktor_hizli_yol(inp)
    import oturum_bakim
    bakim = oturum_bakim.etkin()  # ADR-0092: ağır bakım ayrık koşucuda; kapalıysa eski eşzamanlı yol
    if not bakim:
        try:  # ADR-0034: Windows'ta panel görevi (oturum açılışında başlar) yoksa kurulur; hata hook'u düşürmez
            import panel_servis
            panel_servis.otomatik_kur()
        except Exception:
            pass
    sd = L.durum_dizini(inp.get("cwd")) or _otomatik_ac(inp)
    if not sd:
        gec()
    import perspektif
    perspektif.oturum_say(sd, inp.get("source"))
    if bakim:
        oturum_bakim.baslat(sd, inp.get("cwd") or os.getcwd())  # tmp temizliği, artık dal, etki izleme, bayatlık, panel görevi
    else:
        try:  # çöken yazımlardan kalan eski .tmp_* dosyaları (1 saatten eski) silinir
            L.tmp_temizle(sd)
        except Exception:
            pass
        try:  # I-201, ADR-0050: main'e birleşmiş artık dallar (gölge kipte yalnız günlüğe yazar); hook'u asla düşürmez
            import dal_temizle
            dal_temizle.calistir(inp.get("cwd") or os.getcwd(), kaynak="session_start")
        except Exception:
            pass
    ks = [k for k in L.kartlar(sd) if L.kart_durumu_hesapla(k) in L.ACIK_DURUMLAR + ("beklemede",)]
    bagli = None
    try:
        bagli = _oturum_isi(sd, inp.get("session_id"))
    except Exception:
        pass
    satir1, not_satiri = _ss_birinci_satir(sd, bagli, ks)
    ds = _durum_satiri(sd, inp.get("session_id"))  # I-224 P6: satır sayısı değişmesin diye 1. satırın sonuna eklenir
    if ds:
        satir1 = f"{satir1.rstrip('.')}. {ds}"
    uyarilar, onay_ek = _ss_uyarilar(sd, inp)
    satir2 = ("Uyarı: " + "; ".join(uyarilar))[:300] if uyarilar else ""
    ek_satirlar = [not_satiri] if not_satiri else []
    proje_ = L.proje_dizini(inp.get("cwd"))
    r = perspektif.durum(sd, proje_, perspektif.hafiza_dizini(proje_, inp.get("transcript_path")))
    if r.get("okunmamis_rapor"):
        ek_satirlar.append(f"Perspektif raporu hazır: {r['okunmamis_rapor']} — öneriler panelde Onaylar sayfasında; "
                           "kullanıcı orada onaylayabilir ya da /orkestra:perspektif ile sohbette ilerleyebilir.")
    elif _perspektif_oto() and r.get("zamani_geldi") and not r.get("calisiyor"):
        hafiza = perspektif.hafiza_dizini(proje_, inp.get("transcript_path"))
        ek_satirlar.append("PERSPEKTİF ZAMANI: kullanıcının ilk isteğini yanıtlarken AYNI mesajda, kullanıcıyı bölmeden, Agent aracıyla "
                           "`orkestra:perspektif-ajani` ajanını run_in_background: true ile başlat; istem: "
                           f"`#SUREC:perspektif hafıza klasörü: {hafiza}`. Kullanıcıya yalnız tek satırla bildir.")
    else:  # K4 (ADR-0094): oto kapalıyken eşik aşımı görünür olsun; yan etkisiz, hata yutulur
        zu = perspektif.zaman_uyarisi(sd, _perspektif_oto(), r)
        if zu:
            ek_satirlar.append(zu)
    try:  # eklenti kural katmanı değiştiyse bu projenin kural dosyası yenilenir; hata hook'u düşürmez
        import onay
        onay.kural_dosyasi_esitle(sd)
    except Exception:
        pass
    bs = _bos_is_satiri(sd)
    if bs:
        ek_satirlar.append(bs)
    ei = _etki_ipucu(sd)
    if ei:
        ek_satirlar.append(ei)
    im = ""
    try:
        import izin_politikasi as IP
        im = {"genis": "geniş", "kapi": "kapı"}.get(IP.mod_bul(IP.ayar_yukle(sd)), "")
    except Exception:
        pass
    yol = L.kaynaga_cevir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "KURALLAR.md"))
    satir3 = ((f"Kurallar: {yol}. {_CEKIRDEK} " if os.path.isfile(yol) else "") + (f"İzin: {im}." if im else "")).strip()
    pa = "" if os.environ.get("ORKESTRA_PERSPEKTIF") else _panel_ac_satiri(sd, inp.get("session_id"))
    korunan = "\n".join(x for x in (pa, onay_ek) if x)  # panel açma (oturumda bir kez) ve onay yönergesi kesilmez
    ek = "\n".join([x for x in (satir1, satir2, satir3) if x] + ek_satirlar)
    if korunan:
        ek = ek[:max(0, 1800 - len(korunan) - 1)] + "\n" + korunan
    ek = ek[:1800]
    try:  # ADR-0036: compact/resume sonrası PreCompact'ta yazılan devir özeti bağlama eklenir
        import devir_ozeti
        dv = devir_ozeti.baglam(sd, inp)
        if dv:
            ek = ek + chr(10) + dv
    except Exception:
        pass
    try:  # ADR-0113: sürekli açık skill gövdeleri; hata hook'u düşürmez
        import skill_surekli
        sk = skill_surekli.baglam(proje_)
        if sk:
            ek = ek + chr(10) + sk
    except Exception:
        pass
    _sure_yaz(sd, inp.get("session_id"), (time.perf_counter() - _t0) * 1000)
    import baglam_kaydi
    baglam_kaydi.kaydet(sd, "SessionStart", inp.get("session_id"), ek)
    L.hook_cikti({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ek}})


SESSIONSTART_SURE_ESIK_MS = 2000  # I-255 P3: üstü gölge uyarı (P-028); ihlal geçişi ölçümden sonra ayrı kararla


def _sure_yaz(sd: str, oid, ms: float) -> None:
    """SessionStart süresini gunluk.jsonl'a yazar (tur=hook_sure); eşik aşımı ayrıca kapi_golge olur. Hatada sessiz."""
    try:
        yol = os.path.join(sd, "gunluk.jsonl")
        L.jsonl_ekle(yol, {"zaman": L.simdi(), "oturum": oid, "tur": "hook_sure", "olay": "SessionStart", "sure_ms": round(ms)})
        if ms > SESSIONSTART_SURE_ESIK_MS:
            L.jsonl_ekle(yol, {"zaman": L.simdi(), "oturum": oid, "tur": "kapi_golge", "kapi": "sessionstart_sure",
                               "neden": f"SessionStart {round(ms)} ms > {SESSIONSTART_SURE_ESIK_MS} ms"})
    except Exception:
        pass


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
            import oturum_bakim
            if not oturum_bakim.etkin():  # ADR-0092: etkinleştirilmişse izleme bakım koşucusunda
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


def _is_degisimi_uyarisi(sd: str, oid, transkript, istek: str) -> str:
    """G-125: bağlı oturumda istek başka bir açık işe belirgin yakınsa (eslestir+karar 'bagla') ve bağlam büyükse
    engellemeyen uyarı metni (soguk_onbellek.is_degisimi_uyarisi). Hatada ''."""
    try:
        bagli = _oturum_isi(sd, oid)
        if not bagli or not str(istek or "").strip():
            return ""
        import soguk_onbellek
        if not soguk_onbellek.ayarlar(sd).get("is_degisimi"):
            return ""
        import is_kaydi
        import is_yonlendirme
        isler = [{"id": g["id"], "baslik": g.get("baslik") or "", "klasor": os.path.basename(str(g.get("klasor") or ""))}
                 for g in is_kaydi.is_liste(sd, "acik")]
        ayar = _esleme_ayari(sd)
        k, deger = is_yonlendirme.karar(is_yonlendirme.eslestir(istek, isler, ayar), ayar)
        onerilen = deger if k == "bagla" else None
        return soguk_onbellek.is_degisimi_uyarisi(sd, oid, transkript, bagli, onerilen) or ""
    except Exception:
        return ""


def user_prompt_submit(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if sd and not os.environ.get("ORKESTRA_PERSPEKTIF"):
        metin = L.maskele(inp.get("prompt") or "")
        istek = {}
        if not metin.lstrip().startswith("<"):  # sistem iletisi yeni istek sayılmaz (kimlik üretilmez)
            iid = L.istek_id_yeni(sd, inp.get("session_id"))
            if iid:
                istek["istek_id"] = iid
            ne = L.ne_ozeti(metin)  # I-030 P5: kural tabanlı tek satır; boş iletide yazılmaz
            if ne:
                istek["ne"] = ne
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": inp.get("session_id"), "tur": "istek",
                                                         "metin": metin[:300], "uzunluk": len(metin), **istek})
        # Niyet kaydı: kullanıcı yazdı → Claude çalışıyor. Sistem iletileri (<agent-message>, <task-notification>) istek metni sayılmaz.
        import niyet
        sistem = metin.lstrip().startswith("<")
        neden = None
        if not sistem:
            try:  # soğuk önbellek bilgisi: büyük bağlam + uzun ara → systemMessage (ADR-0108, engellemez; hatada sessiz geç)
                import soguk_onbellek
                neden = soguk_onbellek.karar(sd, inp.get("session_id"), inp.get("transcript_path"))
            except Exception:
                neden = None
        niyet.olay(inp.get("session_id"), L.proje_dizini(inp.get("cwd")), "istek", metin=None if sistem else metin[:200])
        if not sistem:
            parcalar = [asili_uyari(sd, inp.get("session_id")),
                        _yonlendirme_ipucu(sd, inp.get("session_id"), metin, L.proje_dizini(inp.get("cwd")),
                                           cwd=inp.get("cwd"))]
            _niyet_otomatik(sd, inp.get("session_id"), L.proje_dizini(inp.get("cwd")), metin)  # iş açıldıktan sonra
            try:  # bilgi sorusu notu (G-120): listenin başına; hata hook'u düşürmez
                import soru_sinif
                sn = soru_sinif.not_metni(metin, sd)
                if sn:
                    parcalar.insert(0, " ".join(sn.split()))
            except Exception:
                sn = ""
            try:  # ADR-0085: kaynak türü sözleşmesi her mesajda, bilgi sorusu notunun hemen ardından
                km = soru_sinif.kaynak_metni(metin, sd)
                if km:
                    parcalar.insert(1 if sn else 0, km)
            except Exception:
                pass
            try:  # ADR-0103: aday yol taraması notu kaynak notunun hemen ardına; gölge modda günlüğe yazılır
                yn = soru_sinif.yol_metni(metin, sd)
                if yn:
                    parcalar.insert((1 if sn else 0) + (1 if km else 0), yn)
                    L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {
                        "zaman": L.simdi(), "oturum": inp.get("session_id"), "tur": "yol_notu",
                        "mod": soru_sinif.ayar_oku(sd).get("yol_mod", "golge"), "uzunluk": len(metin or "")})
            except Exception:
                pass
            try:  # ADR-0009: `/plan` ya da `/auto` mesajı bağlı işin modunu yazar; iş yoksa oturum bekleyen modu tutar
                import is_onay
                yeni_mod = is_onay.mod_mesaji(metin)
                if yeni_mod:
                    mis = _bagli_is(sd, inp.get("session_id"))
                    if mis:
                        is_onay.mod_yaz(sd, mis, yeni_mod)
                    else:
                        is_onay.bekleyen_mod_yaz(sd, inp.get("session_id"), yeni_mod)
                    parcalar.append(f"Orkestra: çalışma modu {yeni_mod} (ADR-0009).")
                    if yeni_mod == "auto":
                        parcalar.append(_AUTO_SOZLESME)
            except Exception:
                pass
            try:  # P-023: kimlik gerektiren servis anılıyorsa 'yok' demeden önce klasöre bak ipucu
                import kimlik_hatirlatma
                ip = kimlik_hatirlatma.mesaj_ipucu(metin, sd)
                if ip:
                    parcalar.append(ip)
            except Exception:
                pass
            try:  # ADR-0068: iş mesajında best in class yöntemi (tek kaynak: standart); hata hook'u düşürmez
                import yontem_enjeksiyonu
                parcalar.append(yontem_enjeksiyonu.ana_ajan_metni(metin, sd, inp.get("session_id")))
            except Exception:
                pass
            try:  # ADR-0101: hata/sorun içeren mesajda kök neden önce yöntemi; hata hook'u düşürmez
                import kok_neden_enjeksiyonu
                parcalar.append(kok_neden_enjeksiyonu.ana_ajan_metni(metin, sd, inp.get("session_id")))
            except Exception:
                pass
            try:  # ADR-0102: kullanıcı kabuğunun komut sözdizimi (ilk mesaj ve komut anan mesaj); hata hook'u düşürmez
                import kabuk_profili
                parcalar.append(kabuk_profili.ana_ajan_metni(metin, sd, inp.get("session_id")))
            except Exception:
                pass
            try:  # ADR-0107: karar cümlesi yazılmadan önce P-029 düğme yönergesi; hata hook'u düşürmez
                import secim_ekrani_hatirlatma
                parcalar.append(secim_ekrani_hatirlatma.tur_basi_metni(sd))
            except Exception:
                pass
            try:  # ADR-0011: açık atama (SERVIS_ANAHTAR=değer) kimlik klasörüne yazılır; bağlama değer girmez
                import sir_yakala
                parcalar.extend(sir_yakala.kaydet(inp.get("prompt") or ""))
            except Exception:
                pass
            try:  # P-016: onay bekleyen işte kullanıcı mesajı onaysa durum yazılır; hata hook'u düşürmez
                import is_onay
                is_onay.git_izni_isle(sd, inp.get("session_id"), metin)  # ADR-0031: commit/push emri bu tur git komutunu açar
                kayit = _onay_kaydi(sd, inp.get("session_id"))
                if kayit:
                    sinif = is_onay.mesaj_sinifi(metin)
                    satir, yeni = is_onay.baglam_satiri(kayit, sinif == "onay", sinif == "belirsiz")
                    if sinif in ("belirsiz", "ret") and is_onay.bekliyor_mu(kayit):
                        is_onay.aday_yaz(sd, metin, sinif)
                    if sinif in ("belirsiz", "ret", "soru") and is_onay.bekleyen_mi(kayit):
                        is_onay.bekleyen_temizle(sd, kayit["id"])  # ADR-0072: saklı onay, onay olmayan yeni mesajla düşer
                    if yeni == is_onay.BEKLEYEN_YENI:
                        is_onay.bekleyen_yaz(sd, kayit["id"])
                        _is_klasorunu_commitle(kayit.get("klasor"), inp.get("cwd"))
                    elif yeni:
                        is_onay.yaz(sd, kayit["id"], yeni, "onay:kullanici")
                        _is_klasorunu_commitle(kayit.get("klasor"), inp.get("cwd"))  # ADR-0038: onay yazımı işin is.json'ını kirli bırakmasın
                    if satir:
                        parcalar.append(satir)
            except Exception:
                pass
            try:  # I-271: önceki tur pahalıysa (önbellek okuması eşik üstü) tek satır devir ipucu; engellemez
                import devir_esigi
                parcalar.append(devir_esigi.ipucu_al(sd, inp.get("session_id")))
            except Exception:
                pass
            parcalar.append(_durum_satiri(sd, inp.get("session_id")))  # I-224 P6: onay işlendikten sonraki güncel durum
            try:  # ADR-0024: göreve özgü ön bağlam; varsayılan kapalı, hata hook'u düşürmez
                import on_baglam
                ob = on_baglam.uret(metin, [L.proje_dizini(inp.get("cwd"))], sd)
                if ob:
                    parcalar.append(ob)
            except Exception:
                pass
            try:  # panel onay kararları: hata hook'u düşürmez
                import onay
                om = onay.baglam_metni(sd, inp.get("session_id"), "UserPromptSubmit")
                if om:
                    parcalar.append(om)
            except TimeoutError:  # I-157: kilit zaman aşımı sessiz düşmesin; gorulen güncellenmediği için sonraki mesajda yeniden denenir
                parcalar.append("Orkestra: panel kararları okunamadı (onay kilidi zaman aşımı); sonraki mesajda yeniden denenir.")
            except Exception:
                pass
            ek = "\n".join(p for p in parcalar if p)
            try:  # G-125: iş değişimi uyarısı systemMessage olur, isteği engellemez
                uyari = _is_degisimi_uyarisi(sd, inp.get("session_id"), inp.get("transcript_path"), metin)
            except Exception:
                uyari = ""
            if not uyari:  # I-159 P5: büyük bağlamda devir uyarısı (iş değişimi uyarısıyla aynı kanal, engellemez)
                try:
                    import soguk_onbellek
                    uyari = soguk_onbellek.devir_uyarisi(sd, inp.get("session_id"), inp.get("transcript_path")) or ""
                except Exception:
                    uyari = ""
            uyari = "\n".join(u for u in (neden, uyari) if u)  # önbellek bilgisi önce (ADR-0108)
            cikti = {"systemMessage": uyari} if uyari else {}
            if ek:  # boş bağlam çıktısı yazılmaz
                import baglam_kaydi
                baglam_kaydi.kaydet(sd, "UserPromptSubmit", inp.get("session_id"), ek)
                cikti["hookSpecificOutput"] = {"hookEventName": "UserPromptSubmit", "additionalContext": ek}
            if cikti:
                L.hook_cikti(cikti)
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


OTURUM_BASLAT = "mcp__ccd_session__start_session"


def _karar_kaydet(sd: str, inp: dict) -> None:
    """ADR-0112: ana ajanın AskUserQuestion sorusunda `[D<n>]` etiketi varsa ve kullanıcı yanıtladıysa bağlı işin `kararlar`
    alanına yazar. Alt ajan çağrısı sayılmaz."""
    import karar_kapisi
    if inp.get("agent_id") or not karar_kapisi.kapi_acik():
        return
    kararlar = karar_kapisi.ekran_kararlari(inp.get("tool_input"), inp.get("tool_response"))
    if not kararlar:
        return
    is_id = _bagli_is(sd, inp.get("session_id"))
    if is_id:
        karar_kapisi.kaydet(sd, is_id, kararlar)


def _ekran_onayi(sd: str, inp: dict) -> None:
    """ADR-0078: bağlı iş onay bekliyorsa ve AskUserQuestion yanıtı onaysa durumu yazar; bağlama tek satır ekler (çıkar).
    Onay vermeyen her yolda sessiz döner; hata onay vermez ve hook'u düşürmez."""
    try:
        _karar_kaydet(sd, inp)
    except Exception:
        pass
    try:
        import is_onay
        kayit = _onay_kaydi(sd, inp.get("session_id"))
        if not kayit:
            return
        yanit = inp.get("tool_response")
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": inp.get("session_id"), "tur": "onay-ekran",
                                                         "bicim": is_onay.ekran_bicimi(yanit)})  # K5: değer yok, yalnız biçim
        if not is_onay.ekran_onayi_mi(inp.get("tool_input"), yanit, inp.get("agent_id")):
            return
        satir = is_onay.ekran_onayi_isle(sd, kayit)
        _is_klasorunu_commitle(kayit.get("klasor"), inp.get("cwd"))
        if satir:
            L.hook_cikti({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": satir}})
    except SystemExit:
        raise
    except Exception:
        return


def detach_hatirlatmasi(sonuc) -> str:
    """K-007: açılan yan oturumu aynı turda detach_session ile ayrı sohbete almayı hatırlatır.

    Kural metni tek başına işlemedi (oturum açılırken akla gelmiyordu); hatırlatma başlatma sonucuyla birlikte gelir.
    Sonuçta `local_…` id varsa hazır çağrı verilir; teklif kartında (id yok) oturum kullanıcı seçene dek açılmaz."""
    idler = sorted(set(re.findall(r"local_[0-9a-f-]{36}", json.dumps(sonuc or "", ensure_ascii=False))))
    if idler:
        hedef = "Açılan oturum: " + ", ".join(idler) + ". Bu turda, başka işten önce "
        komut = f"mcp__ccd_session_mgmt__detach_session(session_id=\"{idler[0]}\")"
    else:
        hedef = ("Sonuçta oturum id'si yok (teklif kartı kullanıcı seçene dek oturum açmaz). "
                 "Oturum gerçekten başlayınca, aynı turda, ")
        komut = "mcp__ccd_session_mgmt__detach_session(session_id=\"<local_… id>\")"
    return ("K-007: " + hedef + komut + " çağır; oturum kenar çubuğunda bu sohbetin altında iç içe değil, "
            "ayrı sohbet olarak görünmeli. Detach edilmeden tur bitirilmez.")


def post_tool_use_failure(inp: dict):
    """ADR-0101: araç başarısızlığında kök neden önce ipucu (seyreltilmiş); engellemez, hata hook'u düşürmez."""
    try:
        sd = L.durum_dizini(inp.get("cwd"))
        if sd:
            import kok_neden_enjeksiyonu
            ipucu = kok_neden_enjeksiyonu.arac_metni(inp, sd)
            if ipucu:
                L.hook_cikti({"hookSpecificOutput": {"hookEventName": "PostToolUseFailure", "additionalContext": ipucu}})
    except Exception:
        pass
    gec()


def post_tool_use(inp: dict):
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    arac = inp.get("tool_name")
    g = inp.get("tool_input") or {}
    _son_arac_yaz(sd, inp.get("agent_id"))  # sessizlik saati: her araç çağrısı ajanın son-araç zamanını tazeler
    if arac == "AskUserQuestion":  # ADR-0078: seçim ekranı yanıtı P-016 onay kanalıdır; kendi dalında çıkar
        _ekran_onayi(sd, inp)
        gec()
    if arac == OTURUM_BASLAT:
        L.hook_cikti({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": detach_hatirlatmasi(inp.get("tool_response"))}})
    kayit = {"zaman": L.simdi(), "oturum": inp.get("session_id"), "ajan_baglami": inp.get("agent_type") or "ana"}
    if arac == "Skill":
        kayit.update(tur="skill", skill=g.get("skill") or g.get("name"))
    elif arac in ("Agent", "Task"):
        kayit.update(tur="ajan", ajan=g.get("subagent_type") or "general-purpose", model=g.get("model"),
                     arka_plan=bool(g.get("run_in_background")), aciklama=L.maskele(g.get("description") or "")[:80])
        try:
            import sayac
            sayac.artir(sd, sayac.anahtar(kayit["ajan"], kayit["aciklama"]))
        except Exception:
            pass  # sayaç ve toast kancayı asla düşürmez
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


def _oturum_satiri_stopta() -> bool:
    """ADR-0038: bağlı worktree'de oturum satırları Stop'ta yazılır ve commit'lenir; ORKESTRA_OTURUM_SATIRI_STOPTA=0 kapatır."""
    return (os.environ.get("ORKESTRA_OTURUM_SATIRI_STOPTA") or "1").strip().lower() not in ("0", "false", "hayir", "hayır", "kapali", "kapalı")


def _bagli_agac_koku(yol: str) -> str | None:
    """Yol bağlı (linked) worktree içindeyse depo kökü; ana ağaçta, depo dışında ya da hata durumunda None."""
    try:
        kok = L.git_koku(yol)
        if not kok:
            return None
        gd = L.git(["rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"], kok).stdout.split("\n")
        if len(gd) < 2 or os.path.normcase(gd[0].strip()) == os.path.normcase(gd[1].strip()):
            return None
        return kok
    except Exception:
        return None


def _oturum_ozet_yolu(sd: str, oid: str | None):
    """Oturumun bağlı olduğu işin oturumlar.md yolu; bağ, iş klasörü ya da dosya yoksa None."""
    is_id = _oturum_isi(sd, oid)
    if not is_id or not oid:
        return None
    import is_kaydi
    kayit = is_kaydi.is_al(sd, is_id)
    klasor = kayit.get("klasor") if isinstance(kayit, dict) else None
    if not klasor:
        return None
    yol = os.path.join(klasor, "oturumlar.md")
    return yol if os.path.isfile(yol) else None


def _oturum_ozet_satiri(sd: str, oid: str) -> str:
    """Oturumun süre, token ve maliyet özeti satırı (SessionEnd ve bağlı worktree'de Stop aynı biçimi yazar)."""
    import niyet
    zaman = [r for r in L.zaman_kayitlari(sd) if r.get("oturum") == oid]
    ana = _dk([r.get("sure_ms") for r in zaman if r.get("tur") == "ana"])
    alt = _dk([r.get("sure_ms") for r in zaman if r.get("tur") == "alt"])
    etkin = _dk([r.get("etkin_ms") if r.get("etkin_ms") is not None else r.get("sure_ms") for r in zaman if r.get("tur") == "ana"])
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
    return (f"- {an} · oturum {oid[:8]} · Claude süresi {ana} · alt ajan süresi {alt} · etkin süre {etkin} · {tok_s} token · ${usd_s}"
            f" · ne: {_tek_satir(ne)} · sonuç/nerede kalındı: {_tek_satir(sonuc)}\n")


def _oturum_satiri_yaz(sd: str, oid: str | None) -> None:
    """T-07: SessionEnd'de oturum bir işe bağlıysa işin oturumlar.md SONUNA tek satır (dosya yoksa/iş yoksa yazmaz).
    Bağlı worktree'de yazmaz: SessionEnd, uygulamanın arşiv temizliğinden sonra çalışır; satır Stop'ta yazılır (ADR-0038)."""
    yol = _oturum_ozet_yolu(sd, oid)
    if not yol or not oid:
        return
    if _oturum_satiri_stopta() and _bagli_agac_koku(yol):
        return
    L.sona_ekle(yol, _oturum_ozet_satiri(sd, oid))
    _oturum_agacinda_commitle(yol)


def _bagli_agacta_satirlari_kaydet(sd: str, oid: str | None, yol: str) -> None:
    """Stop'ta (ADR-0038): bağlı worktree'de tur satırı yazıldıktan sonra oturum özetini oturum başına tek satır olarak
    yeniler ve dosyayı commit'ler; arşiv tur bittikten sonra geldiği için worktree temiz kalır. Ana ağaçta hiçbir şey yapmaz."""
    try:
        if not oid or not _oturum_satiri_stopta() or not _bagli_agac_koku(yol):
            return
        isaret = f"· oturum {oid[:8]} · Claude süresi"
        yeni = _oturum_ozet_satiri(sd, oid)
        with L.kilit(yol):
            with open(yol, encoding="utf-8") as f:
                satirlar = [s for s in f.read().splitlines(keepends=True) if isaret not in s]
            if satirlar and not satirlar[-1].endswith("\n"):
                satirlar[-1] += "\n"
            satirlar.append(yeni)
            L.atomik_yaz(yol, "".join(satirlar))
        _oturum_agacinda_commitle(yol)
    except Exception:  # özet/commit hatası Stop'u bozmasın
        pass


def _oturum_agacinda_commitle(yol: str) -> None:
    """Oturum satırı yazıldıktan sonra Claude oturum worktree'sini "commit edilmemiş değişiklikle arşivlendi" uyarısıyla
    bırakmasın diye dosya yalnız bağlı (linked) worktree'de ve yalnız bu dosya commit'lenir; `index.lock` çakışmasında
    (uygulamanın git işçisi aynı anda çalışır) 5 kez, 1 sn arayla yeniden dener.
    Ana ağaçta, izlenmeyen dosyada ya da hata durumunda hiçbir şey yapmaz."""
    try:
        import time
        kok = _bagli_agac_koku(yol)  # ana ağaç: kullanıcının kendi çalışma ağacına commit atılmaz
        if not kok:
            return
        if L.git(["ls-files", "--error-unmatch", "--", yol], kok).returncode != 0:
            return
        if not L.git(["status", "--porcelain", "--", yol], kok).stdout.strip():
            return
        for _ in range(5):
            c = L.git(["commit", "--only", "-m", "oturumlar.md: oturum satırı", "--", yol], kok)
            if c.returncode == 0 or "index.lock" not in (c.stderr or ""):
                break
            time.sleep(1)
    except Exception:  # commit hatası kapanışı bozmasın
        pass


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


def pre_compact(inp: dict):
    """ADR-0036: compact öncesi modelsiz devir özeti yazılır (devir_ozeti); hata compact'ı engellemez."""
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        gec()
    try:  # I-222 P2: olay sayısı günlüğe yazılır (maliyet taban sayar); hata sıkıştırmayı engellemez
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": inp.get("session_id"), "tur": "sikistirma",
                                                         "tetik": inp.get("trigger")})
    except Exception as e:
        _hata_yaz(sd, "pre_compact", e)
    try:
        import devir_ozeti
        bagli = None
        try:
            oid = _oturum_isi(sd, inp.get("session_id"))
            if oid:
                import is_kaydi
                bagli = is_kaydi.is_al(sd, oid)
        except Exception:
            pass
        devir_ozeti.yaz(sd, inp, bagli)
    except Exception as e:
        _hata_yaz(sd, "pre_compact", e)
    gec()


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
    if _perspektif_oto() and perspektif.durum(sd, proje_, perspektif.hafiza_dizini(proje_, inp.get("transcript_path"))).get("zamani_geldi"):
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
    "PostToolUseFailure": post_tool_use_failure,
    "SessionEnd": session_end, "ConfigChange": config_change, "PreCompact": pre_compact,
}


def main():
    olay = sys.argv[1] if len(sys.argv) > 1 else ""
    inp = L.stdin_json()
    isleyici = OLAYLAR.get(olay)
    if isleyici is None:  # P12: bilinmeyen olay hook'u düşürmez (çıkış 0, hook-hatasi yazılmaz)
        sys.exit(0)
    try:
        isleyici(inp)
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
                import traceback  # yalnız hata yolunda gerekir; hızlı yolda yüklenmez
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
