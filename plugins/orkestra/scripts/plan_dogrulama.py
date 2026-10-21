"""Plan yapılabilirlik doğrulaması: plan.md'deki her olgusal iddia kanıtla yeniden doğrulanır.

Saf Python, model çağırmaz. İşaret (doğrulandı / doğrulanamadı) yazarın değil bu modülün çıktısıdır.

Plan sözdizimi (plan.md, her bölümde):

    - ⬜ **C1** İddia metni.
      - Kanıt: dosya <yol>:<satır> "<alıntı>"
      - Kanıt: ara "<regex>" <dosya veya glob>... => <N | >=N>
      - Kanıt: say <glob> => <N | >=N>
      - Kanıt: komut `<komut>` => <beklenen | çıkış 0>
      - Kanıt: deneme <yol> "<alıntı>"
      - Kanıt: kaynak <https://...> "<alıntı>" <GG.AA.YYYY>
      - Alternatif: ... | Spike: ... | Risk: ...      (❌ iddia için en az biri zorunlu)

Plan maddesi (`### P<n>`) bloğunda `**İddialar:** C1, C2` (bu iddialara dayanır) ve/veya `**Kapatır:** C3`
(bu iddiayı kapatan spike; ona dayanmış sayılmaz). `**Kök:** <dizin>` satırı dosya yollarının ek kökleridir.

Kanıt derecesi: K = makine yeniden hesaplar (dosya, ara, say, komut); D = kayıtlı deneme dosyası (var ve alıntı tutuyor);
B = yalnız belge (URL) - tek başına işaret vermez. Makine kanıtın var olduğunu ve alıntının tuttuğunu doğrular;
kanıtın iddiayı anlamca desteklediğine ayrı denetçi bakar (karar bloğunda yazılı sınır).
"""
from __future__ import annotations

import fnmatch
import glob as _glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402
import is_sirasi as _SIRA  # noqa: E402

DOGRULAMA_ADI = "plan-iddia"
TAMAM, YOK, BEKLEYEN = "\u2705", "\u274c", "\u2b1c"  # ✅ ❌ ⬜
KARAR_UYGULANABILIR, KARAR_KOSULLU, KARAR_UYGULANAMAZ, KARAR_TAMAMLANMAMIS = (
    "UYGULANABİLİR", "KOŞULLU", "UYGULANAMAZ", "TAMAMLANMAMIŞ")
CIKIS_KODU = {KARAR_UYGULANABILIR: 0, KARAR_KOSULLU: 1, KARAR_UYGULANAMAZ: 2, KARAR_TAMAMLANMAMIS: 3}
BLOK_BASLA, BLOK_BITIS = "<!-- plan-dogrulama:basla -->", "<!-- plan-dogrulama:bitis -->"
PENCERE = 2
MIN_ALINTI = 4
VARSAYILAN_ZAMAN_ASIMI = 30
SINIR_METNI = ("Makine kanıtın var olduğunu ve alıntının tuttuğunu doğrular; kanıtın iddiayı anlamca desteklediğine ayrı "
               "denetçi bakar. Tahminler ve tercihler doğrulanmaz.")

_MD_BAGLANTI = re.compile(r"\(mevcut_durum_\d+\.md\)")
_YORUM = re.compile(r"<!--.*?-->", re.S)
_CIT = re.compile(r"^\s*(```|~~~)")
_IDDIA = re.compile(r"^(?P<g>\s*)[-*]\s+(?:(?P<i>\u2705|\u274c|\u2b1c)\s+)?\*\*C(?P<no>\d+)\*\*[:.]?\s*(?P<metin>.*)$")
_ALT = re.compile(r"^(?P<g>\s*)[-*]\s+(?P<alan>Kanıt|Alternatif|Spike|Risk):\s*(?P<deger>.*?)\s*$")
_DOSYA = re.compile(r'^(?P<yol>\S+?):(?P<satir>\d+)\s+"(?P<alinti>.+)"$')
_ARA = re.compile(r'^"(?P<re>.+?)"\s+(?P<dosyalar>.+?)\s*=>\s*(?P<bek>>=\s*\d+|\d+)$')
_SAY = re.compile(r'^(?P<glob>\S+)\s*=>\s*(?P<bek>>=\s*\d+|\d+)$')
_KOMUT = re.compile(r'^`(?P<k>.+)`\s*=>\s*(?P<bek>.+)$')
_DENEME = re.compile(r'^(?P<yol>\S+)\s+"(?P<alinti>.+)"$')
_KAYNAK = re.compile(r'^(?P<url>https?://\S+)\s+"(?P<alinti>.+?)"\s+(?P<tarih>\d{2}\.\d{2}\.\d{4})$')
_P_ALAN = {"iddia": re.compile(r"\*\*İddialar:\*\*[ \t]*(.*)"), "kapatir": re.compile(r"\*\*Kapatır:\*\*[ \t]*(.*)")}
_KOK = re.compile(r"^\*\*Kök:\*\*[ \t]*(.+)$", re.M)
_C_NO = re.compile(r"\bC(\d+)\b")

# komut kanıtında çalıştırılmayan kalıplar (yazma, silme, ağ, git yazma, kabuk yazımı); liste tam değildir,
# komut yine ajanın zaten sahip olduğu yetkiyle koşar
_YASAK = [re.compile(p, re.I) for p in (
    r"(^|[\s;&|(])(rm|rmdir|del|erase|mv|move|cp|copy|chmod|chown|kill|taskkill|shutdown|dd|mkfs|format|truncate|touch)\b",
    r"\bgit\s+(push|commit|reset|checkout|clean|rebase|merge|stash|add|rm|mv|tag|restore|switch|pull|fetch)\b",
    r"\b(curl|wget|Invoke-WebRequest|iwr|Invoke-RestMethod|scp|ssh|nc|ncat|ftp)\b",
    r"\b(Remove-Item|Set-Content|Add-Content|Out-File|New-Item|Move-Item|Copy-Item|Set-ItemProperty)\b",
    r"\bsed\s+-[a-z]*i", r"\btee\b", r"\bpip\s+install\b", r"\bnpm\s+(install|i|publish)\b",
    r"\b(os\.remove|os\.unlink|shutil\.|rmtree|\.write\(|\.write_text|subprocess|os\.system|__import__)",
    r"\borkestra\s+(is|kart|kural|onay|baslat|plan\s+dogrula\b.*--yaz)\b",
)]
_IZINLI_YONLENDIRME = re.compile(r"\d*>\s*/dev/null|\d?>&\d|\d>\s*NUL\b", re.I)


def kapi_acik() -> bool:
    return os.environ.get("ORKESTRA_DOGRULAMA_KAPISI") != "0"


def komut_acik() -> bool:
    return os.environ.get("ORKESTRA_PLAN_KOMUT") != "0"


def _oku(yol: str) -> str | None:
    try:
        with open(yol, encoding="utf-8", errors="replace", newline="") as f:
            return f.read().replace("\r\n", "\n")
    except OSError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


# ---------------------------------------------------------------- ayrıştırma

def temiz_satirlar(metin: str) -> list[str]:
    """Yorum (<!-- -->) ve kod çiti içini boşaltır, satır numaralarını korur."""
    def bosalt(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    metin = _YORUM.sub(bosalt, metin)
    cikti, cit = [], False
    for s in metin.split("\n"):
        if _CIT.match(s):
            cit = not cit
            cikti.append("")
        else:
            cikti.append("" if cit else s)
    return cikti


def blok_ayikla(metin: str) -> str:
    """Karar bloğu çıkarılmış plan metni (özet hesabı ve ayrıştırma için)."""
    a, b = metin.find(BLOK_BASLA), metin.find(BLOK_BITIS)
    if a == -1 or b == -1 or b < a:
        return metin
    return metin[:a] + metin[b + len(BLOK_BITIS):]


def ozet(metin: str) -> str:
    """Plan özeti: karar bloğu hariç içeriğin 12 haneli sha256'sı. İşaretler dahildir: `--yaz` işaretleri koyduktan
    sonra hesaplanır, elle değiştirilen işaret özeti bozar ve todo kapısı planı bayat sayar."""
    govde = blok_ayikla(metin)
    govde = "\n".join(s.rstrip() for s in govde.replace("\r\n", "\n").split("\n")).strip()
    govde = re.sub(r" {2,}", " ", govde)
    govde = re.sub(r"\n{3,}", "\n\n", govde)  # blok çıkarılınca kalan boş satırlar özeti değiştirmesin
    return hashlib.sha256(govde.encode("utf-8")).hexdigest()[:12]


def iddialari_ayristir(metin: str) -> list[dict]:
    """[{no, satir (0 tabanlı), isaret, metin, girinti, kanitlar[{tur, deger, satir}], cikis[{alan, deger}]}]."""
    satirlar = temiz_satirlar(blok_ayikla(metin))
    iddialar = []
    i = 0
    while i < len(satirlar):
        m = _IDDIA.match(satirlar[i])
        if not m:
            i += 1
            continue
        girinti = len(m.group("g").replace("\t", "    "))
        c = {"no": int(m.group("no")), "satir": i, "isaret": m.group("i") or BEKLEYEN, "metin": m.group("metin").strip(),
             "girinti": girinti, "kanitlar": [], "cikis": []}
        j = i + 1
        while j < len(satirlar):
            s = satirlar[j]
            if not s.strip():
                j += 1
                continue
            g = len(s) - len(s.lstrip())
            if g <= girinti:
                break
            a = _ALT.match(s)
            if a:
                if a.group("alan") == "Kanıt":
                    bol = a.group("deger").split(None, 1)
                    c["kanitlar"].append({"tur": (bol[0] if bol else "").lower(), "deger": bol[1] if len(bol) > 1 else "",
                                          "satir": j})
                else:
                    c["cikis"].append({"alan": a.group("alan"), "deger": a.group("deger")})
            j += 1
        iddialar.append(c)
        i = j
    return iddialar


def plan_maddeleri(metin: str) -> dict[int, dict]:
    """{P no: {iddia: [C no], kapatir: [C no]}}; blok yapısı is_sirasi ile aynıdır."""
    import is_sirasi as SR
    sonuc = {}
    for n, blok in SR._p_bloklari(blok_ayikla(metin)).items():
        d = {"iddia": [], "kapatir": []}
        for ad, rx in _P_ALAN.items():
            for m in rx.finditer(blok):
                d[ad] += [int(x) for x in _C_NO.findall(m.group(1))]
        sonuc[n] = d
    return sonuc


def kokler_plan(metin: str, plan_klasoru: str, proje: str, ek: list[str] | None = None) -> list[str]:
    kokler = [plan_klasoru]
    for m in _KOK.finditer(blok_ayikla(metin)):
        for parca in re.split(r"[;,]", m.group(1)):
            p = parca.strip().strip("`")
            if p:
                kokler.append(p if os.path.isabs(p) else os.path.join(proje, p))
    kokler += [k if os.path.isabs(k) else os.path.join(proje, k) for k in (ek or [])]
    kokler.append(proje)
    gorulen, sonuc = set(), []
    for k in kokler:
        k = os.path.abspath(k)
        if k not in gorulen:
            gorulen.add(k)
            sonuc.append(k)
    return sonuc


def proje_koku(plan_yolu: str) -> str:
    d = os.path.dirname(os.path.abspath(plan_yolu))
    while True:
        if os.path.isdir(os.path.join(d, ".claude")):
            return d
        ust = os.path.dirname(d)
        if ust == d:
            return os.getcwd()
        d = ust


# ---------------------------------------------------------------- kanıt doğrulayıcılar
# Dönüş: (gecti: bool | None, derece, mesaj). gecti None = doğrulanmadı (yalnız B derecesi ya da koşulmadı).

def _coz(yol: str, kokler: list[str]) -> str | None:
    if os.path.isabs(yol):
        return yol if os.path.isfile(yol) else None
    for k in kokler:
        a = os.path.join(k, yol)
        if os.path.isfile(a):
            return a
    return None


def _dosyalar(desen: str, kokler: list[str]) -> list[str]:
    if os.path.isabs(desen):
        return sorted(_glob.glob(desen))
    for k in kokler:
        bulunan = sorted(p for p in _glob.glob(os.path.join(k, desen)) if os.path.isfile(p))
        if bulunan:
            return bulunan
    return []


def _sayi_tut(deger: int, bek: str) -> bool:
    bek = bek.replace(" ", "")
    return deger >= int(bek[2:]) if bek.startswith(">=") else deger == int(bek)


def _k_dosya(deger, kokler):
    m = _DOSYA.match(deger)
    if not m:
        return False, "K", 'bozuk: `dosya <yol>:<satır> "<alıntı>"` olmalı'
    yol = _coz(m.group("yol"), kokler)
    if yol is None:
        return False, "K", f"dosya bulunamadı: {m.group('yol')}"
    metin = _oku(yol) or ""
    satirlar = metin.split("\n")
    n = int(m.group("satir"))
    if n < 1 or n > len(satirlar):
        return False, "K", f"{m.group('yol')}: satır {n} yok (dosyada {len(satirlar)} satır)"
    alinti = _norm(m.group("alinti"))
    if len(alinti) < MIN_ALINTI:
        return False, "K", f"alıntı çok kısa (en az {MIN_ALINTI} karakter)"
    pencere = _norm(" ".join(satirlar[max(0, n - 1 - PENCERE):n + PENCERE]))
    if alinti not in pencere:
        return False, "K", f"{m.group('yol')}:{n} çevresinde (±{PENCERE} satır) alıntı bulunamadı"
    return True, "K", f"{m.group('yol')}:{n} alıntı tuttu"


def _k_ara(deger, kokler):
    m = _ARA.match(deger)
    if not m:
        return False, "K", 'bozuk: `ara "<regex>" <dosya>... => <N|>=N>` olmalı'
    try:
        rx = re.compile(m.group("re"), re.M)
    except re.error as e:
        return False, "K", f"regex geçersiz: {e}"
    dosyalar = []
    for d in m.group("dosyalar").split():
        dosyalar += _dosyalar(d, kokler)
    if not dosyalar:
        return False, "K", f"dosya bulunamadı: {m.group('dosyalar')}"
    toplam = sum(len(rx.findall(_oku(p) or "")) for p in dosyalar)
    ok = _sayi_tut(toplam, m.group("bek"))
    return ok, "K", f"{len(dosyalar)} dosyada {toplam} eşleşme; beklenen {m.group('bek')}"


def _k_say(deger, kokler):
    m = _SAY.match(deger)
    if not m:
        return False, "K", "bozuk: `say <glob> => <N|>=N>` olmalı"
    n = len(_dosyalar(m.group("glob"), kokler))
    return _sayi_tut(n, m.group("bek")), "K", f"{n} dosya; beklenen {m.group('bek')}"


def _bash() -> str | None:
    return cfg.al("bash")


def komut_yasakli(komut: str) -> str | None:
    sade = _IZINLI_YONLENDIRME.sub(" ", komut)
    if ">" in sade:
        return "çıktı yönlendirme (>) yasak"
    for rx in _YASAK:
        if rx.search(sade):
            return f"yasaklı kalıp: {rx.pattern[:40]}"
    return None


def _k_komut(deger, kokler, proje, kos, zaman_asimi):
    m = _KOMUT.match(deger)
    if not m:
        return False, "K", "bozuk: `komut `<komut>` => <beklenen|çıkış 0>` olmalı"
    komut, bek = m.group("k").strip(), m.group("bek").strip()
    yasak = komut_yasakli(komut)
    if yasak:
        return False, "K", f"komut çalıştırılmadı ({yasak})"
    if not kos or not komut_acik():
        return False, "K", "komut koşulmadı (--komut-kosma ya da ORKESTRA_PLAN_KOMUT=0)"
    bash = _bash()
    arg = [bash, "-c", komut] if bash else komut
    env = dict(os.environ, PYTHONUTF8="1", ORKESTRA_DOGRULAMA_KAPISI="0")
    try:
        r = subprocess.run(arg, shell=not bash, cwd=proje, capture_output=True, timeout=zaman_asimi, env=env)
    except subprocess.TimeoutExpired:
        return False, "K", f"komut {zaman_asimi} sn içinde bitmedi"
    except OSError as e:
        return False, "K", f"komut başlatılamadı: {e}"
    cikti = _norm((r.stdout or b"").decode("utf-8", "replace") or (r.stderr or b"").decode("utf-8", "replace"))
    if bek.lower() in ("çıkış 0", "cikis 0"):
        return r.returncode == 0, "K", f"çıkış {r.returncode}"
    if re.fullmatch(r"\d+", bek):
        ok = re.search(rf"(?<![\w.]){re.escape(bek)}(?![\w.])", cikti) is not None
    else:
        ok = _norm(bek) in cikti
    return ok, "K", f"çıktı: {cikti[:80]!r}; beklenen {bek[:40]!r}"


def _d_deneme(deger, kokler):
    m = _DENEME.match(deger)
    if not m:
        return False, "D", 'bozuk: `deneme <yol> "<alıntı>"` olmalı'
    yol = _coz(m.group("yol"), kokler)
    if yol is None:
        return False, "D", f"deneme dosyası bulunamadı: {m.group('yol')}"
    alinti = _norm(m.group("alinti"))
    if len(alinti) < MIN_ALINTI:
        return False, "D", f"alıntı çok kısa (en az {MIN_ALINTI} karakter)"
    try:
        if os.path.getsize(yol) > 8_000_000:
            return False, "D", "deneme dosyası 8 MB'tan büyük"
    except OSError:
        return False, "D", "deneme dosyası okunamadı"
    if alinti not in _norm(_oku(yol) or ""):
        return False, "D", f"alıntı {m.group('yol')} içinde yok"
    return True, "D", f"{m.group('yol')} alıntı tuttu"


def _b_kaynak(deger):
    if not _KAYNAK.match(deger):
        return False, "B", 'bozuk: `kaynak <https://...> "<alıntı>" <GG.AA.YYYY>` olmalı'
    return None, "B", "yalnız belge kanıtı: makine doğrulamaz, tek başına işaret vermez"


def kanit_dogrula(kanit: dict, kokler: list[str], proje: str, kos: bool = True, zaman_asimi: int = VARSAYILAN_ZAMAN_ASIMI):
    tur, deger = kanit["tur"], kanit["deger"].strip()
    if tur == "dosya":
        return _k_dosya(deger, kokler)
    if tur == "ara":
        return _k_ara(deger, kokler)
    if tur == "say":
        return _k_say(deger, kokler)
    if tur == "komut":
        return _k_komut(deger, kokler, proje, kos, zaman_asimi)
    if tur == "deneme":
        return _d_deneme(deger, kokler)
    if tur == "kaynak":
        return _b_kaynak(deger)
    return False, "?", f"bilinmeyen kanıt türü: {tur or '(boş)'} (dosya|ara|say|komut|deneme|kaynak)"


# ---------------------------------------------------------------- iddia ve plan kararı

def iddia_degerlendir(c: dict, kokler, proje, kos=True, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI) -> dict:
    """c'ye `hesap` (✅/❌), `neden`, `sonuclar`, `bozuk` ekler ve döndürür."""
    sonuclar, bozuk = [], []
    for k in c["kanitlar"]:
        ok, derece, mesaj = kanit_dogrula(k, kokler, proje, kos, zaman_asimi)
        sonuclar.append({"tur": k["tur"], "derece": derece, "gecti": ok, "mesaj": mesaj})
        if mesaj.startswith("bozuk") or derece == "?":
            bozuk.append(f"C{c['no']} kanıt satırı {k['satir'] + 1}: {mesaj}")
    gecen = [s for s in sonuclar if s["derece"] in ("K", "D") and s["gecti"] is True]
    kalan = [s for s in sonuclar if s["derece"] in ("K", "D") and s["gecti"] is False]
    if not c["kanitlar"]:
        hesap, neden = YOK, "kanıt satırı yok"
    elif kalan:
        hesap, neden = YOK, "kanıt tutmuyor: " + "; ".join(f"{s['tur']}: {s['mesaj']}" for s in kalan[:2])
    elif gecen:
        hesap, neden = TAMAM, "; ".join(f"{s['derece']}:{s['tur']}" for s in gecen)
    else:
        hesap, neden = YOK, "yalnız belge kanıtı; ölçülmedi"
    c["hesap"], c["neden"], c["sonuclar"], c["bozuk"] = hesap, neden, sonuclar, bozuk
    return c


def _yol_sonucu(metin: str, plan_yolu: str, kokler: list[str]) -> list[dict]:
    """Serbest yol anmalarının varlık denetimi (uyarı; karara girmez)."""
    import yol_denetimi as YD
    sonuc = [dict(k, dosya=os.path.basename(plan_yolu)) for k in YD.denetle_metin(blok_ayikla(metin), kokler)]
    klasor = os.path.dirname(os.path.abspath(plan_yolu))
    sonuc += YD.denetle_dosyalar(sorted(_glob.glob(os.path.join(klasor, "mevcut_durum_*.md"))), kokler)
    return sonuc


def degerlendir(plan_yolu: str, ek_kokler: list[str] | None = None, kos: bool = True, zaman_asimi: int | None = None) -> dict:
    """Planı baştan sona değerlendirir; dosyaya yazmaz. Dönüş sözlüğü karar_blogu() ve CLI için yeterlidir."""
    metin = _oku(plan_yolu)
    if metin is None:
        raise ValueError(f"plan okunamadı: {plan_yolu}")
    proje = proje_koku(plan_yolu)
    kokler = kokler_plan(metin, os.path.dirname(os.path.abspath(plan_yolu)), proje, ek_kokler)
    zaman_asimi = zaman_asimi or ayar(proje).get("zaman_asimi_sn", VARSAYILAN_ZAMAN_ASIMI)
    iddialar = [iddia_degerlendir(c, kokler, proje, kos, zaman_asimi) for c in iddialari_ayristir(metin)]
    maddeler = plan_maddeleri(metin)
    eksik, bayat = [], []
    kimlikler = {}
    for c in iddialar:
        if c["no"] in kimlikler:
            eksik.append(f"C{c['no']} iki kez tanımlı")
        kimlikler[c["no"]] = c
        eksik += c["bozuk"]
        if c["hesap"] == YOK and not c["cikis"]:
            eksik.append(f"C{c['no']} ❌ ama çıkış yolu yok (`Alternatif:`, `Spike:` ya da `Risk:` satırı ekle)")
        if c["isaret"] != c["hesap"]:
            bayat.append(f"C{c['no']}")
    if not iddialar:
        eksik.append("plan.md'de iddia satırı yok (`- ⬜ **C1** ...`)")
    if not maddeler:
        eksik.append("plan.md'de `P<n>` maddesi yok")
    engelli, engelsiz = {}, []
    for n, d in sorted(maddeler.items()):
        if not d["iddia"] and not d["kapatir"]:
            eksik.append(f"P{n}: `**İddialar:**` ya da `**Kapatır:**` satırı yok")
        for no in d["iddia"] + d["kapatir"]:
            if no not in kimlikler:
                eksik.append(f"P{n}: C{no} planda tanımlı değil")
        sebep = [no for no in d["iddia"] if no in kimlikler and kimlikler[no]["hesap"] == YOK]
        if sebep:
            engelli[n] = sebep
        else:
            engelsiz.append(n)
    gap = None
    klasor = os.path.dirname(os.path.abspath(plan_yolu))
    if _SIRA.gapli_mi(klasor):  # P-017 ikinci geçiş: MD §6 gap'leri plan maddeleriyle kapsanıyor mu
        gap_eksik = _SIRA.gap_kapsama_eksikleri(klasor)
        eksik += [f"gap kapsaması: {e}" for e in gap_eksik]
        gap = {"toplam": len(_SIRA.mevcut_durum_gapleri(klasor)), "eksik": len(gap_eksik)}
    bagli = {no for d in maddeler.values() for no in d["iddia"] + d["kapatir"]}
    yetim = [c for c in iddialar if c["hesap"] == YOK and c["no"] not in {no for d in maddeler.values() for no in d["iddia"]}]
    if eksik:
        karar = KARAR_TAMAMLANMAMIS
    elif not engelli:
        karar = KARAR_UYGULANABILIR
    elif not engelsiz:
        karar = KARAR_UYGULANAMAZ
    else:
        karar = KARAR_KOSULLU
    return {"plan": os.path.abspath(plan_yolu), "ozet": ozet(metin), "karar": karar, "eksik": eksik, "bayat": bayat, "iddialar": iddialar,
            "engelli": engelli, "engelsiz": engelsiz, "yetim": [c["no"] for c in yetim], "bagli": sorted(bagli),
            "gap": gap, "yol": _yol_sonucu(metin, plan_yolu, kokler),
            "tahmin_sayisi": len(re.findall(r"^\s*[-*]\s+\*\*T\d+\*\*", "\n".join(temiz_satirlar(blok_ayikla(metin))), re.M))}


# ---------------------------------------------------------------- yazma

def isaretleri_yaz(metin: str, iddialar: list[dict]) -> str:
    satirlar = metin.replace("\r\n", "\n").split("\n")
    for c in iddialar:
        s = satirlar[c["satir"]]
        m = _IDDIA.match(s)
        if not m:
            continue
        bas = s[:m.start("i")] if m.group("i") else s[:s.index("**C")]
        kalan = s[m.end("i") + 1:] if m.group("i") else s[s.index("**C"):]
        satirlar[c["satir"]] = f"{bas}{c['hesap']} {kalan.lstrip()}"
    return "\n".join(satirlar)


def _zaman() -> str:
    import datetime
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


def karar_blogu(sonuc: dict, ozet_degeri: str) -> str:
    iddialar = sonuc["iddialar"]
    t, y = sum(c["hesap"] == TAMAM for c in iddialar), sum(c["hesap"] == YOK for c in iddialar)
    n_p = len(sonuc["engelli"]) + len(sonuc["engelsiz"])
    if sonuc["karar"] == KARAR_TAMAMLANMAMIS:
        gerekce = f"{len(sonuc['eksik'])} yapısal eksik var; eksikler giderilmeden karar verilmez."
    elif sonuc["karar"] == KARAR_UYGULANABILIR:
        gerekce = f"{n_p} plan maddesinin hiçbiri ❌ iddiaya dayanmıyor."
    elif sonuc["karar"] == KARAR_UYGULANAMAZ:
        gerekce = f"{n_p} plan maddesinin hepsi ❌ iddiaya dayanıyor; önce iddialar kapatılmalı."
    else:
        gerekce = (f"{n_p} plan maddesinden {len(sonuc['engelsiz'])}'i başlayabilir, {len(sonuc['engelli'])}'i ❌ iddiaya "
                   "dayandığı için bekler.")
    s = [BLOK_BASLA, "## Uygulanabilirlik kararı", "", f"**Karar:** {sonuc['karar']}", "", f"**Gerekçe:** {gerekce}", "",
         f"**Ölçüm saati:** {_zaman()} (yerel)", "", f"**Plan özeti:** {ozet_degeri}", "",
         f"**İddialar:** {len(iddialar)} (✅ {t}, ❌ {y}); tahmin: {sonuc['tahmin_sayisi']}", ""]
    if sonuc.get("gap"):
        g = sonuc["gap"]
        s += [f"**Gap kapsaması:** {'tam' if not g['eksik'] else str(g['eksik']) + ' eksik'} (MD §6: {g['toplam']} gap)", ""]
    if sonuc["eksik"]:
        s += ["**Yapısal eksikler:**", ""] + [f"- {e}" for e in sonuc["eksik"][:12]] + [""]
    kayip = [f"{k['dosya']}:{k['satir']} {k['yol']}" for k in sonuc.get("yol", []) if not k["var"]]
    if kayip:
        s += ["**Bulunamayan yollar (uyarı):**", ""] + [f"- {e}" for e in kayip[:12]] + [""]
    s += ["**Engelsiz plan maddeleri:**", ""] + ([f"- Madde P{n}" for n in sonuc["engelsiz"]] or ["- (yok)"]) + [""]
    s += ["**Engelli plan maddeleri:**", ""]
    kim = {c["no"]: c for c in iddialar}
    if sonuc["engelli"]:
        for n, sebepler in sonuc["engelli"].items():
            ayr = "; ".join(f"C{no} ({kim[no]['neden']})" for no in sebepler)
            s.append(f"- Madde P{n} ← {ayr}")
    else:
        s.append("- (yok)")
    s.append("")
    acik = [c for c in iddialar if c["hesap"] == YOK]
    if acik:
        s += ["**Açık ❌ iddialar ve çıkış yolları:**", ""]
        for c in acik:
            cikis = " | ".join(f"{x['alan']}: {x['deger']}"[:140] for x in c["cikis"]) or "(çıkış yolu yok)"
            s.append(f"- C{c['no']} ❌ {c['metin'][:90]} → {cikis}")
        s.append("")
    s += [f"**Sınır:** {SINIR_METNI}", BLOK_BITIS]
    return "\n".join(s)


def blogu_yerlestir(metin: str, blok: str) -> str:
    """Karar bloğunu plan başına koyar; varsa eskisini önce çıkarır (konum kendini onarır). P-005 plan kapısı
    mevcut durum bağlantısını planın ilk satırlarında arar (SR.BAGLANTI_PENCERE): blok o bağlantının paragrafından
    SONRA girer."""
    import is_sirasi as SR
    metin = re.sub(r"\n{3,}", "\n\n", blok_ayikla(metin.replace("\r\n", "\n")))
    satirlar = metin.split("\n")
    son = -1
    for i, s in enumerate(satirlar[:SR.BAGLANTI_PENCERE]):
        if _MD_BAGLANTI.search(s):
            son = i
    if son == -1:
        son = next((i for i, s in enumerate(satirlar) if s.startswith("# ")), -1)
    else:
        while son + 1 < len(satirlar) and satirlar[son + 1].strip():
            son += 1
    return "\n".join(satirlar[:son + 1] + ["", blok, ""] + satirlar[son + 1:])


def yaz(plan_yolu: str, ek_kokler: list[str] | None = None, kos: bool = True) -> dict:
    """İşaretleri günceller, karar bloğunu yazar; güncel sonucu döndürür. Yazım atomiktir."""
    sonuc = degerlendir(plan_yolu, ek_kokler, kos)
    metin = _oku(plan_yolu) or ""
    yeni = isaretleri_yaz(blok_ayikla(metin), sonuc["iddialar"]) if sonuc["iddialar"] else blok_ayikla(metin)
    sonuc["bayat"] = []  # işaretler yazıldı
    for c in sonuc["iddialar"]:
        c["isaret"] = c["hesap"]
    ozet_degeri = ozet(yeni)
    yeni = blogu_yerlestir(yeni, karar_blogu(sonuc, ozet_degeri))
    gecici = plan_yolu + ".tmp"
    with open(gecici, "w", encoding="utf-8", newline="\n") as f:
        f.write(yeni)
    os.replace(gecici, plan_yolu)
    sonuc["ozet"] = ozet_degeri
    return sonuc


# ---------------------------------------------------------------- todo kapısı (is_kaydi ve hook ortak)

def ayar(proje: str | None = None) -> dict:
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    veri = {"mod": "golge", "zaman_asimi_sn": VARSAYILAN_ZAMAN_ASIMI}
    for yol in (os.path.join(kok, "ayarlar", "plan_dogrulama.json"),
                os.path.join(proje or os.getcwd(), ".claude", "orkestra", "plan_dogrulama.json")):
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                veri.update({k: d[k] for k in ("mod", "zaman_asimi_sn") if k in d})
        except (OSError, ValueError):
            pass
    return veri


def dogrulamali_mi(klasor: str) -> bool:
    if not kapi_acik():
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            v = json.load(f)
        return isinstance(v, dict) and v.get("dogrulama") == DOGRULAMA_ADI
    except (OSError, ValueError):
        return False


def blok_oku(plan_yolu: str) -> dict | None:
    """Karar bloğundan {karar, ozet, guncel, engelli:[P no]}; blok yoksa None."""
    metin = _oku(plan_yolu)
    if metin is None:
        return None
    a, b = metin.find(BLOK_BASLA), metin.find(BLOK_BITIS)
    if a == -1 or b == -1 or b < a:
        return None
    blok = metin[a:b]
    k = re.search(r"\*\*Karar:\*\*\s*(\S+)", blok)
    o = re.search(r"\*\*Plan özeti:\*\*\s*(\w+)", blok)
    bol = blok.split("**Engelli plan maddeleri:**", 1)
    engelli = sorted({int(x) for x in re.findall(r"^- Madde P(\d+) ←", bol[1], re.M)}) if len(bol) == 2 else []
    return {"karar": k.group(1) if k else "", "ozet": o.group(1) if o else "", "engelli": engelli,
            "guncel": bool(o) and o.group(1) == ozet(metin)}


def _ihlal_ver(klasor: str, neden: str) -> str:
    """İhlal modunda nedeni döndürür; gölge modunda günlüğe yazar ve boş döndürür."""
    if ayar(proje_koku(os.path.join(klasor, "plan.md"))).get("mod") == "ihlal":
        return neden
    try:
        import ork_lib as L
        sd = L.durum_dizini(klasor)
        if sd:
            L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "tur": "kural_ihlal",
                                                         "kural": "plan_dogrulama", "mod": "golge", "neden": neden[:300]})
    except Exception:
        pass
    print(f"orkestra (gölge): {neden}", file=sys.stderr)
    return ""


def todo_onkosulu(klasor: str) -> str:
    """Doğrulamalı işte todo yazımı için ön koşul. Boş metin = serbest."""
    if not dogrulamali_mi(klasor):
        return ""
    b = blok_oku(os.path.join(klasor, "plan.md"))
    if b is None:
        return _ihlal_ver(klasor, "plan doğrulaması yok: `orkestra plan dogrula <iş> --yaz` ile planı doğrula, sonra todo yaz.")
    if not b["guncel"]:
        return _ihlal_ver(klasor, "plan doğrulaması güncel değil (plan sonradan değişti): `orkestra plan dogrula <iş> --yaz`.")
    if b["karar"] == KARAR_TAMAMLANMAMIS:
        return _ihlal_ver(klasor, "plan doğrulaması TAMAMLANMAMIŞ: `orkestra plan dogrula <iş>` eksikleri listeler.")
    return ""


def todo_satir_engelleri(klasor: str, metin: str) -> str:
    """Metindeki `P<n>:` todo satırı engelli (❌ iddiaya dayanan) plan maddesine aitse neden; yoksa boş."""
    if not dogrulamali_mi(klasor):
        return ""
    b = blok_oku(os.path.join(klasor, "plan.md"))
    if b is None or not b["guncel"] or not b["engelli"]:
        return ""
    for s in str(metin).splitlines():
        m = re.match(r"^\s*(?:[-*]\s*\[[ xX]\]\s*)?P(\d+)\b", s)
        if m and int(m.group(1)) in b["engelli"]:
            return _ihlal_ver(klasor, f"P{m.group(1)} ❌ iddiaya dayanıyor (plan.md karar bloğu); önce iddiayı kapat "
                                      "(`**Kapatır:**` spike maddesi) ya da planı değiştirip yeniden doğrula.")
    return ""
