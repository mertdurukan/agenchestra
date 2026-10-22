"""Kalıcı 'iş' katmanı: bir iş birden çok sohbete/karta yayılır.

Merkezi dizin: <durum dizini>/isler.json; iş klasöründe is.json.
Kilit ve atomik yazım ork_lib'den gelir.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import is_sirasi as SIRA  # noqa: E402
from is_yonlendirme import devir_onu_at  # noqa: E402

DURUMLAR = ("acik", "beklemede", "kapandi")
_ID = re.compile(r"^I-(\d+)$")
_TODO_ACIK = re.compile(r"^\s*[-*]\s*\[ \]\s*(.*)$")
_TODO_BOS = re.compile(r"^\s*[-*]\s*\[ \]\s*$")
_TODO_BITEN =re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(.*)$")
# Sayım kuralı (tek): yalnız üst düzey kutular; [ ] ve [~] açık, [x] biten (todo_maddeleri ile aynı).
_TODO_UST_ACIK = re.compile(r"^[-*]\s*\[[ ~]\]\s*(.*)$")
_TODO_UST_BITEN = re.compile(r"^[-*]\s*\[[xX]\]\s*(.*)$")
_BOS = {"sayac": 0, "isler": {}}


def _merkez(sd: str) -> str:
    return os.path.join(sd, "isler.json")


_DENEME = 8
_BEKLEME_S = 0.01


def _oku(yol: str, varsayilan):
    if not os.path.exists(yol):
        return json.loads(json.dumps(varsayilan))
    for deneme in range(_DENEME):
        try:
            with open(yol, encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, json.JSONDecodeError):
            if deneme == _DENEME - 1:
                raise
            time.sleep(_BEKLEME_S * 2 ** deneme)


def _yaz(yol: str, veri) -> None:
    """Atomik yazım; Windows'ta hedef anlık tutulursa os.replace PermissionError verir.
    Artan beklemeyle yeniden dener, başarısızlıkta geçici dosyayı siler."""
    metin = json.dumps(veri, ensure_ascii=False, indent=2) + "\n"
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=os.path.dirname(yol), prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
        for deneme in range(_DENEME):
            try:
                os.replace(gecici, yol)
                return
            except PermissionError:
                if deneme == _DENEME - 1:
                    raise
                time.sleep(_BEKLEME_S * 2 ** deneme)
    finally:
        if os.path.exists(gecici):
            try:
                os.remove(gecici)
            except OSError:
                pass


def is_no(is_id: str) -> int:
    m = _ID.match(is_id or "")
    if not m:
        raise ValueError(f"geçersiz iş kimliği: {is_id!r}")
    return int(m.group(1))


def is_sirala(ids) -> list[str]:
    return sorted(ids, key=is_no)


def yeni_is_id(sd: str) -> str:
    """Kilitli sayaç artırımı; I-999 sonrası I-1000."""
    yol = _merkez(sd)
    with L.kilit(yol):
        veri = _oku(yol, _BOS)
        veri["sayac"] = int(veri.get("sayac", 0)) + 1
        veri.setdefault("isler", {})
        _yaz(yol, veri)
        return f"I-{veri['sayac']:03d}"


def _is_json_yolu(klasor: str) -> str:
    return os.path.join(klasor, "is.json")


_SABLON = {
    "plan.md": "# {baslik}\n\n## Amaç\n\n## Kararlar\n",  # sablonlar/plan.md yoksa yedek
    "todo.md": "# Yapılacaklar — {baslik}\n\n- [ ] \n",
    "oturumlar.md": "# Oturumlar — {baslik}\n\n",
}
SABLON_DIZINI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sablonlar")

# tür -> (şablon dosyası, hedef dosya adı kalıbı, sohbet bağlantı etiketi)
BELGE_TURLERI = {
    "mevcut_durum": ("mevcut_durum.md", "mevcut_durum_{gun}.md", "mevcut durum"),
    "plan": ("plan.md", "plan.md", "plan dosyası"),
    "todo": ("todo.md", "todo.md", "to-do dosyası"),
    "ozet": ("calisma_ozeti.md", "calisma_ozeti_{gun}.md", "çalışma özeti"),
    "bulgu": ("bulgu.md", "bulgu.md", "bulgu"),
    "jira": ("jira_onerisi.md", "jira_onerisi.md", "jira önerisi"),
    "rapor": ("rapor.md", "rapor.md", "rapor"),
}
# okunacak belge adları (K-003): bağlantı komutu bu kalıplara uyan dosyaları listeler
_BELGE_KALIPLARI = (
    (re.compile(r"^(?!devir).*ozet.*\.md$", re.I), "çalışma özeti"),
    (re.compile(r"^bulgu.*\.md$", re.I), "bulgu"),
    (re.compile(r"^jira_onerisi.*\.md$", re.I), "jira önerisi"),
    (re.compile(r"^rapor.*\.md$", re.I), "rapor"),
)


def sablon_metni(ad: str, baslik: str, simdi: datetime.datetime | None = None, gun: str | None = None) -> str:
    """sablonlar/<ad> içeriği; {baslik}, {tarih} (GG.AA.YYYY), {saat} (SS:DD), {gun} (YYYYMMDD; `gun` verilmediyse
    bugün) yer tutucuları doldurulur. plan.md dosyası yoksa yerleşik yedek kullanılır; diğer şablonlarda dosya yoksa
    FileNotFoundError."""
    simdi = simdi or datetime.datetime.now()
    try:
        with open(os.path.join(SABLON_DIZINI, ad), encoding="utf-8") as f:
            metin = f.read()
    except FileNotFoundError:
        if ad not in _SABLON:
            raise
        metin = _SABLON[ad]
    return (metin.replace("{baslik}", baslik).replace("{tarih}", simdi.strftime("%d.%m.%Y"))
            .replace("{saat}", simdi.strftime("%H:%M")).replace("{gun}", gun or simdi.strftime("%Y%m%d")))


def _dogrulamali(klasor: str) -> bool:
    try:
        import plan_dogrulama as PD
        return PD.dogrulamali_mi(klasor)
    except Exception:  # kapı şablon seçimini asla bozmaz
        return False


def belge_olustur(klasor: str, baslik: str, tur: str, simdi: datetime.datetime | None = None) -> tuple[str, bool]:
    """İş klasöründe şablondan belge açar. (yol, oluştu_mu); var olan dosya asla ezilmez (oluştu_mu=False).
    Sıralı işte (P-005) plan.md, mevcut durum tamam olmadan açılmaz (ValueError); plan sıralı şablondan açılır."""
    if tur not in BELGE_TURLERI:
        raise ValueError(f"bilinmeyen belge türü: {tur} (geçerli: {', '.join(BELGE_TURLERI)})")
    simdi = simdi or datetime.datetime.now()
    sablon, hedef, _ = BELGE_TURLERI[tur]
    yol = os.path.join(klasor, hedef.format(gun=simdi.strftime("%Y%m%d")))
    gun = None
    if tur == "plan" and SIRA.sirali_mi(klasor):
        if not os.path.exists(yol):
            eksik = SIRA.plan_onkosulu(klasor)
            if eksik:
                raise ValueError(SIRA.mesaj(eksik, "plan.md"))
        sablon = "plan_sirali.md"
        if _dogrulamali(klasor):  # plan doğrulama kapısı: iddia sözdizimli şablon (✅/❌ kapısı)
            sablon = "plan_dogrulamali.md"
        md = SIRA.mevcut_durum_yolu(klasor)
        gun = re.sub(r"\D", "", os.path.basename(md)) if md else None
    os.makedirs(klasor, exist_ok=True)
    try:
        with open(yol, "x", encoding="utf-8", newline="\n") as f:
            f.write(sablon_metni(sablon, baslik, simdi, gun))
    except FileExistsError:
        return yol, False
    return yol, True


def baglanti_satiri(etiket: str, yol: str, proje_koku: str) -> str:
    """'<etiket>: [<ad>](<proje köküne göre yol>)'. Yol her zaman '/' ile yazılır; kök dışındaysa mutlaktır."""
    mutlak = os.path.abspath(yol)
    try:
        goreli = os.path.relpath(mutlak, proje_koku)
    except ValueError:  # farklı sürücü
        goreli = mutlak
    if goreli.startswith(".."):
        goreli = mutlak
    goreli = goreli.replace("\\", "/")
    if re.search(r"[ ()]", goreli):
        goreli = f"<{goreli}>"
    return f"{etiket}: [{os.path.basename(mutlak)}]({goreli})"


def belge_baglantilari(klasor: str, proje_koku: str, son_dk: int = 180, tumu: bool = False,
                       ek: list[str] | None = None, simdi_ts: float | None = None) -> list[str]:
    """K-003 sohbet satırları. plan.md ve todo.md (varsa) her zaman; iş klasöründeki okunacak belgeler
    (özet, bulgu, jira_onerisi, rapor) son `son_dk` dakikada değiştiyse ya da `tumu` ise; `ek` yolları da eklenir."""
    simdi_ts = time.time() if simdi_ts is None else simdi_ts
    satirlar = []
    gorulen = set()
    md = SIRA.mevcut_durum_yolu(klasor)  # P-005: teslim satırlarının en başında
    if md:
        gorulen.add(os.path.normcase(os.path.abspath(md)))
        satirlar.append(baglanti_satiri("mevcut durum", md, proje_koku))
    for ad, etiket in (("plan.md", "plan dosyası"), ("todo.md", "to-do dosyası")):
        yol = os.path.join(klasor, ad)
        if os.path.isfile(yol):
            gorulen.add(os.path.normcase(os.path.abspath(yol)))
            satirlar.append(baglanti_satiri(etiket, yol, proje_koku))
    adaylar = []
    try:
        adlar = sorted(os.listdir(klasor))
    except OSError:
        adlar = []
    for ad in adlar:
        yol = os.path.join(klasor, ad)
        if not os.path.isfile(yol):
            continue
        for kalip, etiket in _BELGE_KALIPLARI:
            if kalip.match(ad):
                if tumu or simdi_ts - os.path.getmtime(yol) <= son_dk * 60:
                    adaylar.append((etiket, yol))
                break
    for yol in ek or []:
        ad = os.path.basename(yol)
        adaylar.append((next((e for k, e in _BELGE_KALIPLARI if k.match(ad)), "belge"), yol))
    for etiket, yol in adaylar:
        anahtar = os.path.normcase(os.path.abspath(yol))
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        satirlar.append(baglanti_satiri(etiket, yol, proje_koku))
    return satirlar


def _dogrulama_varsayilan() -> bool:
    try:
        import plan_dogrulama as PD
        return PD.kapi_acik()
    except Exception:
        return False


def ONAY_KAPISI_ACIK() -> bool:
    return os.environ.get("ORKESTRA_ONAY_KAPISI") != "0"


def _proje_koku_mu(sd: str, klasor: str) -> bool:
    """Klasör, eşlemedeki (baglam.json) bir proje köküyle aynı mı. Eşleme okunamazsa False."""
    try:
        import baglam
        taban = os.path.dirname(os.path.dirname(os.path.abspath(sd)))
        n = lambda y: os.path.normcase(os.path.normpath(y))
        return any(n(os.path.join(taban, str(p))) == n(klasor)
                   for p in ((baglam.esleme_oku(sd) or {}).get("projeler") or []) if str(p).strip())
    except Exception:
        return False


def is_ac(sd: str, baslik: str, klasor: str, etiketler=None, dogrulama: bool | None = None) -> dict:
    """Yeni iş. Kapı açıkken (P-005) iş sıralıdır: ilk dosya mevcut durum iskeletidir, plan.md ve todo.md
    önceki adım tamamlanınca açılır; kapı kapalıyken (ORKESTRA_SIRA_KAPISI=0) eski üç dosya yazılır.
    Sıralı işe ayrıca `dogrulama` bayrağı konur (plan ✅/❌ kapısı); `dogrulama=False` ya da
    ORKESTRA_DOGRULAMA_KAPISI=0 ile konmaz, None varsayılandır (kapı açıksa konur)."""
    klasor = os.path.abspath(klasor)
    if _proje_koku_mu(sd, klasor):  # kök klasör iş klasörü sayılırsa kökteki başka işin kaydı ezilir (I-105)
        raise ValueError(f"iş klasörü proje kökü olamaz: {klasor}; NNN-… biçiminde bir alt klasör ver")
    os.makedirs(klasor, exist_ok=True)
    sirali = SIRA.kapi_acik()
    for ad in (("oturumlar.md",) if sirali else _SABLON):
        yol = os.path.join(klasor, ad)
        if not os.path.exists(yol):  # var olan asla ezilmez
            try:
                with open(yol, "x", encoding="utf-8", newline="\n") as f:
                    f.write(sablon_metni(ad, baslik))
            except FileExistsError:  # var-mı kontrolü ile yazma arası yarış
                pass
    if sirali:
        belge_olustur(klasor, baslik, "mevcut_durum")
    is_id = yeni_is_id(sd)
    an = L.simdi()
    kayit = {
        "id": is_id, "baslik": baslik, "durum": "acik", "klasor": klasor,
        "olusturma": an, "guncelleme": an, "etiketler": list(etiketler or []),
        "kartlar": [], "oturumlar": [], "gecmis": [{"zaman": an, "olay": "acildi"}],
    }
    if sirali:
        kayit["sira"] = SIRA.SIRA_ADI
        if SIRA.kalite_kapisi_acik():
            kayit["kalite"] = True  # P-018: belge çıtası (özet, kabul/geri alma, kanıtlı todo, planla karşılaştıran özet)
        if SIRA.gap_kapisi_acik():
            kayit["gap"] = True  # P-017: gap analizi (mevcut durum §6) ve plan kapsama denetimi
        if SIRA.harita_kapisi_acik():
            kayit["harita"] = True  # ADR-0005: plan maddesi mevcut varlığı sistem haritasından gösterir
        if ONAY_KAPISI_ACIK():
            kayit["onay"] = "bekliyor"  # P-016: kullanıcı onaylamadan uygulama yok
        if dogrulama is None:
            dogrulama = _dogrulama_varsayilan()
        if dogrulama:
            import plan_dogrulama as PD
            kayit["dogrulama"] = PD.DOGRULAMA_ADI
    eski_id = None
    with L.kilit(_is_json_yolu(klasor)):
        if os.path.exists(_is_json_yolu(klasor)):  # klasörde önceki bir işin kaydı varsa ezilmez, yedeklenir
            import shutil
            shutil.copy2(_is_json_yolu(klasor), _is_json_yolu(klasor) + ".eski-" + re.sub(r"\D", "", an)[:14])
            try:  # eski kimlik yeni işe devredilir: oturumlar taşınır, kartlar/harcama takma adla yeni kimliğe bağlanır
                with open(_is_json_yolu(klasor), encoding="utf-8") as f:
                    eski = json.load(f) or {}
                eski_id = eski.get("id") if _ID.match(str(eski.get("id") or "")) else None
                kayit["oturumlar"] = [o for o in eski.get("oturumlar") or [] if isinstance(o, dict)]
                kayit["gecmis"].append({"zaman": an, "olay": "devralindi", "eski_id": eski_id})
            except (OSError, ValueError, AttributeError):
                pass
        _yaz(_is_json_yolu(klasor), kayit)
    yol = _merkez(sd)
    with L.kilit(yol):
        veri = _oku(yol, _BOS)
        if eski_id and eski_id != is_id and eski_id not in veri.get("isler", {}):
            veri.setdefault("takma", {})[eski_id] = is_id
        veri.setdefault("isler", {})[is_id] = {
            "klasor": klasor, "baslik": baslik, "durum": "acik", "olusturma": an}
        _yaz(yol, veri)
    return kayit


_TR = str.maketrans({"ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "I": "i", "İ": "i", "ö": "o", "Ö": "o",
                     "ş": "s", "Ş": "s", "ü": "u", "Ü": "u"})
_NNN = re.compile(r"^(\d{3})-")


def slug(baslik: str, azami: int = 40) -> str:
    """Başlıktan ascii, küçük harf, tireli kısa ad (boşsa 'is')."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(baslik or "").translate(_TR))
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > azami:
        kesik = s[:azami]
        if s[azami] != "-" and "-" in kesik:  # sözcüğün ortasında kesme: son yarım sözcüğü at
            kesik = kesik.rsplit("-", 1)[0]
        s = kesik.rstrip("-")
    return s or "is"


_ORKESTRA_ANAHTAR = re.compile(r"orkestra|orchestr|eklenti|plugin|\bhook\b|\bskill\b|claude\.md", re.I)


def baslik_uret(istek, azami: int = 70) -> str:
    """İş başlığı: boşluklar sadeleşir, yan oturum devir önekleri ('Background|Task (from the session…):', art arda) atılır,
    azami uzunlukta sözcük sınırından kesilir (önce 70 karakter ham kesiliyordu: 'Background (from the…' çöp başlık)."""
    metin = devir_onu_at(" ".join(str(istek or "").split()))  # 'Task (…): Background (…): başlık' gibi art arda önekler hepsi atılır
    if len(metin) <= azami:
        return metin.rstrip() or "is"
    kesik = metin[:azami]
    if metin[azami] != " " and " " in kesik:
        kesik = kesik.rsplit(" ", 1)[0]
    return kesik.rstrip(" ,;:-") or "is"


def proje_sec(projeler, istek: str) -> int:
    """Eşlemedeki proje listesinde işin klasör köküne düşen proje dizini: orkestra konulu istek 'orkestra'/'orchestr'
    adlı projeye gider (yoksa ilk proje). Böylece orkestra işleri iş klasörünü RNV altında açmaz."""
    projeler = list(projeler or [])
    if _ORKESTRA_ANAHTAR.search(str(istek or "")):
        for i, p in enumerate(projeler):
            if re.search(r"orkestra|orchestr", str(p), re.I):
                return i
    return 0


def klasor_ayir(sd: str, kok: str, baslik: str, tarih: str | None = None, olustur: bool = True,
                tercih: str | None = None) -> str:
    """sonraki_klasor_adi + klasörü kilit altında oluşturur: eşzamanlı iki oturum aynı NNN'i almaz
    (005, 017, 029 ikişer klasör çıkmıştı). Klasör yazılamazsa OSError. olustur=False: yalnız adı hesaplar (kuru koşu).

    tercih (istenen klasör adı, I-138 P5): 'NNN-…' öneki kilit altında denetlenir; numara kökte başka bir klasörde
    ya da bu adla açık bir işin klasöründe kullanılıyorsa (kapalı iş ya da işsiz klasör yeniden kullanılır), ya da önek yok ve kökte numaralı klasör varsa
    sıradaki numara alınır; aksi halde tercih aynen döner. Ayrılan klasöre oturumlar.md yazılır (yer tutucu: eşzamanlı
    ikinci çağrı dolu görür; is_ac aynı dosyayı zaten var olanı ezmeden yazar)."""
    with L.kilit(os.path.join(sd, "klasor_numara")):
        ad = None
        if tercih:
            m = _NNN.match(tercih)
            try:
                kardesler = os.listdir(kok)
            except OSError:
                kardesler = []
            if m:
                dolu = any(k.startswith(m.group(1) + "-") and k != tercih
                           for k in kardesler if os.path.isdir(os.path.join(kok, k)))
                dolu = dolu or any(k.startswith(m.group(1) + "-") and k != tercih for k in kardes_agac_klasorleri(kok))
                if not dolu and tercih in kardesler:  # aynı ad: yalnız açık bir iş orada çalışıyorsa dolu
                    dolu = is_klasorle_bul(sd, os.path.join(kok, tercih)) is not None
            else:
                dolu = any(_NNN.match(k) for k in kardesler)  # numarasız ad: kök numaralıysa tekil numara al
            if not dolu and m:
                ad = tercih
            elif not dolu:
                return tercih
        if ad is None:
            ad = sonraki_klasor_adi(kok, baslik, tarih)
        if olustur:
            yol = os.path.join(kok, ad)
            os.makedirs(yol, exist_ok=True)
            if tercih:
                try:
                    with open(os.path.join(yol, "oturumlar.md"), "x", encoding="utf-8", newline="\n") as f:
                        f.write(sablon_metni("oturumlar.md", baslik))
                except FileExistsError:
                    pass
    return ad


def kardes_agac_klasorleri(kok: str) -> list[str]:
    """`kok` bir git çalışma ağacındaysa, aynı deponun ÖTEKİ ağaçlarında (oturum ve kart worktree'leri, ana ağaç) aynı göreli
    klasörün alt klasör adları. Ağaçlar arası numara tekilliği için (ADR-0032): birleşmemiş dallarda aynı NNN iki işe verilmesin.
    Git yoksa ya da herhangi bir hatada boş liste."""
    try:
        ust = L.git_koku(kok)
        if not ust:
            return []
        rel = os.path.relpath(os.path.abspath(kok), ust)
        r = L.git(["worktree", "list", "--porcelain"], ust)
        if r.returncode != 0:
            return []
        kendi = os.path.normcase(os.path.realpath(ust))
        adlar: list[str] = []
        for satir in r.stdout.splitlines():
            if not satir.startswith("worktree "):
                continue
            w = satir[len("worktree "):].strip()
            if os.path.normcase(os.path.realpath(w)) == kendi:
                continue
            hedef = os.path.join(w, rel)
            try:
                adlar += [a for a in os.listdir(hedef) if os.path.isdir(os.path.join(hedef, a))]
            except OSError:
                continue
        return adlar
    except Exception:
        return []


def sonraki_klasor_adi(kok: str, baslik: str, tarih: str | None = None) -> str:
    """kök altında sıradaki 'NNN-YYYYMMDD-<slug>' adı: NNN = en büyük ^\\d{3}- numarası + 1 (3 hane); öteki git
    çalışma ağaçlarındaki aynı klasör de sayılır (`kardes_agac_klasorleri`)."""
    import datetime
    en_buyuk = 0
    try:
        for ad in os.listdir(kok):
            m = _NNN.match(ad)
            if m:
                en_buyuk = max(en_buyuk, int(m.group(1)))
    except OSError:
        pass
    for ad in kardes_agac_klasorleri(kok):
        m = _NNN.match(ad)
        if m:
            en_buyuk = max(en_buyuk, int(m.group(1)))
    tarih = tarih or datetime.date.today().strftime("%Y%m%d")
    return f"{en_buyuk + 1:03d}-{tarih}-{slug(baslik)}"


def _ayni_yol(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def klasor_kaydi(klasor: str) -> dict | None:
    """Klasördeki geçerli is.json kaydı (merkeze bakmadan); yok/bozuk/kimliksizse None."""
    try:
        kayit = _oku(_is_json_yolu(klasor), None)
    except (OSError, ValueError):
        return None
    if not isinstance(kayit, dict) or not _ID.match(str(kayit.get("id", ""))):
        return None
    return kayit


def is_klasorden(sd: str, klasor: str) -> dict | None:
    """Klasördeki is.json'un işi merkezde bu klasörle kayıtlıysa güncel kaydı; is.json yok/bozuk/merkezde yoksa
    (ya da aynı kimlik merkezde başka klasöre aitse) None."""
    kayit = klasor_kaydi(klasor)
    if kayit is None:
        return None
    try:
        giris = _oku(_merkez(sd), _BOS).get("isler", {}).get(kayit["id"])
        if not giris or not _ayni_yol(giris.get("klasor") or "", klasor):
            return None
        return is_al(sd, kayit["id"])
    except (OSError, ValueError, AttributeError):
        return None


def yetim_kaydet(sd: str, klasor: str, uygula: bool = True) -> dict | None:
    """Klasörde geçerli is.json var ama işi merkezde kayıtlı değilse merkeze kaydeder (onar; sayaç en büyük I-NNN'e
    çekilir) ve is.json kaydını döndürür. Aynı kimlik merkezde başka klasöre aitse (çakışma) kaydetmez, None döner.
    uygula=False: yalnız kaydı döndürür, dosya yazmaz."""
    kayit = klasor_kaydi(klasor)
    if kayit is None:
        return None
    try:
        giris = _oku(_merkez(sd), _BOS).get("isler", {}).get(kayit["id"])
    except (OSError, ValueError, AttributeError):
        return None
    if giris and not _ayni_yol(giris.get("klasor") or "", klasor):
        return None
    if uygula:
        onar(sd, [klasor], uygula=True)
    return kayit


def merkez_bozuk_mu(sd: str) -> bool:
    """isler.json var ama JSON olarak okunamıyor ya da biçimi geçersizse True (yoksa False)."""
    yol = _merkez(sd)
    if not os.path.exists(yol):
        return False
    try:
        veri = _oku(yol, _BOS)
    except ValueError:  # JSONDecodeError, UnicodeDecodeError
        return True
    except OSError:
        return False
    return not isinstance(veri, dict) or not isinstance(veri.get("isler", {}), dict)


def merkez_kurtar(sd: str, bilinen_klasorler=None) -> dict:
    """isler.json bozuksa isler.json.bozuk-<zaman> adıyla yedeğe alır; merkez yoksa (ya da yedeklendiyse) bilinen
    is.json klasörlerinden yeniden kurar (onar). Merkez sağlamsa hiçbir şey yapmaz.
    Dönüş: {"yedek": yol|None, "kuruldu": bool, "farklar": [...]}."""
    yol = _merkez(sd)
    yedek = None
    if merkez_bozuk_mu(sd):
        with L.kilit(yol):
            if merkez_bozuk_mu(sd):  # kilit altında yeniden bak: başka süreç onarmış olabilir
                damga = time.strftime("%Y%m%dT%H%M%S")
                yedek = f"{yol}.bozuk-{damga}"
                n = 1
                while os.path.exists(yedek):
                    n += 1
                    yedek = f"{yol}.bozuk-{damga}-{n}"
                os.replace(yol, yedek)
    if os.path.exists(yol):
        return {"yedek": yedek, "kuruldu": False, "farklar": []}
    r = onar(sd, bilinen_klasorler or [], uygula=True)
    return {"yedek": yedek, "kuruldu": r["yazildi"], "farklar": r["farklar"]}


def is_al(sd: str, is_id: str) -> dict | None:
    giris = _oku(_merkez(sd), _BOS).get("isler", {}).get(is_id)
    if not giris:
        return None
    return _oku(_is_json_yolu(giris["klasor"]), None)


def is_liste(sd: str, durum: str | None = None) -> list[dict]:
    isler = _oku(_merkez(sd), _BOS).get("isler", {})
    out = []
    for i in is_sirala(isler):
        g = dict(isler[i])
        g["id"] = i
        if durum is None or g.get("durum") == durum:
            out.append(g)
    return out


def sifirla(sd: str) -> dict:
    """Merkezi iş kayıtlarını yedeğe alıp boşaltır → {"silinen": n, "yedek": yol | None}.

    Sayaç, iş klasörleri (is.json, todo.md, ...) ve kartlar yerinde kalır; eski kimlikler yeniden verilmez.
    Yedek: <durum dizini>/yedek/isler_<damga>.json. Kayıt yok ya da zaten boşsa dosya yazılmaz (yedek None)."""
    yol = _merkez(sd)
    with L.kilit(yol):
        veri = _oku(yol, _BOS)
        isler = veri.get("isler") or {}
        if not isler:
            return {"silinen": 0, "yedek": None}
        yedek_dizin = os.path.join(sd, "yedek")
        os.makedirs(yedek_dizin, exist_ok=True)
        yedek = os.path.join(yedek_dizin, f"isler_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json")
        _yaz(yedek, veri)
        veri["isler"] = {}
        veri["sifirlama"] = L.simdi()
        _yaz(yol, veri)
    return {"silinen": len(isler), "yedek": yedek}


def sifirlama_zamani(sd: str) -> str | None:
    """Son sıfırlamanın zamanı; hiç sıfırlanmadıysa None."""
    return _oku(_merkez(sd), _BOS).get("sifirlama")


def _degistir(sd: str, is_id: str, islem) -> dict:
    giris = _oku(_merkez(sd), _BOS).get("isler", {}).get(is_id)
    if not giris:
        raise KeyError(f"iş yok: {is_id}")
    yol = _is_json_yolu(giris["klasor"])
    with L.kilit(yol):
        kayit = _oku(yol, None)
        if kayit is None:
            raise KeyError(f"is.json yok: {yol}")
        islem(kayit)
        kayit["guncelleme"] = L.simdi()
        _yaz(yol, kayit)
    return kayit


def is_durum(sd: str, is_id: str, durum: str) -> dict:
    if durum not in DURUMLAR:
        raise ValueError(f"geçersiz durum: {durum}")

    def islem(k):
        k["durum"] = durum
        k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": f"durum:{durum}"})

    kayit = _degistir(sd, is_id, islem)
    yol = _merkez(sd)
    with L.kilit(yol):
        veri = _oku(yol, _BOS)
        if is_id in veri.get("isler", {}):
            veri["isler"][is_id]["durum"] = durum
            _yaz(yol, veri)
    return kayit


def is_kart_ekle(sd: str, is_id: str, kart_id: str) -> dict:
    def islem(k):
        if kart_id not in k.setdefault("kartlar", []):
            k["kartlar"].append(kart_id)
            k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": f"kart:{kart_id}"})

    return _degistir(sd, is_id, islem)


_JIRA_ONEK = re.compile(r"^[A-Z]{2,}[A-Z0-9]*-\d+:?\s+")
_ADIM = re.compile(r"^(G\d+[a-z]?(?:-[A-Za-z]\d+|/[A-Za-z]?\d+)*)(?=[:\s]|$)")


def adim_coz(baslik) -> str | None:
    """Başlıktaki plan adımı öneki ('PE-636 G7-A1: x' -> 'G7-A1'); yoksa None."""
    b = _JIRA_ONEK.sub("", (baslik or "").strip(), count=1)
    m = _ADIM.match(b)
    return m.group(1) if m else None


def _klasor_anahtari(klasor: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(klasor))).casefold()


def is_klasorle_bul(sd: str, klasor: str, kapali_dahil: bool = False) -> str | None:
    """isler.json'da klasörü eşleşen ilk AÇIK (kapanmamış) iş kimliği; kapali_dahil=True ise durumdan bağımsız."""
    hedef = _klasor_anahtari(klasor)
    for g in is_liste(sd):
        if not g.get("klasor") or _klasor_anahtari(g["klasor"]) != hedef:
            continue
        if kapali_dahil or g.get("durum") != "kapandi":
            return g["id"]
    return None


def sira_ac(sd: str, is_id: str) -> dict:
    """Eski bir işi sıralı yapar (P-005): `sira` bayrağını koyar, mevcut durum yoksa iskeleti açar."""
    def islem(k):
        k["sira"] = SIRA.SIRA_ADI
        k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": "sira:acildi"})

    kayit = _degistir(sd, is_id, islem)
    if SIRA.mevcut_durum_yolu(kayit["klasor"]) is None:
        belge_olustur(kayit["klasor"], kayit.get("baslik") or "", "mevcut_durum")
    return kayit


def is_oturum_bagla(sd: str, is_id: str, oturum: str) -> dict:
    import is_onay
    bekleyen = is_onay.bekleyen_mod_al(sd, oturum)  # ADR-0009: iş bağlanmadan önce yazılan /plan ya da /auto

    def islem(k):
        if bekleyen:
            k[is_onay.MOD_ALANI] = bekleyen
            k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": f"mod:{bekleyen}"})
        if not any(o.get("oturum") == oturum for o in k.setdefault("oturumlar", [])):
            an = L.simdi()
            k["oturumlar"].append({"oturum": oturum, "baglanma": an})
            k.setdefault("gecmis", []).append({"zaman": an, "olay": f"oturum:{oturum}"})

    return _degistir(sd, is_id, islem)


def todo_ozet(klasor: str) -> dict:
    yol = os.path.join(klasor, "todo.md")
    biten, acik = 0, []
    if os.path.exists(yol):
        with open(yol, encoding="utf-8", errors="replace") as f:
            for satir in f:
                satir = satir.rstrip("\r\n")
                if _TODO_UST_BITEN.match(satir):
                    biten += 1
                else:
                    m = _TODO_UST_ACIK.match(satir)
                    if m and m.group(1).strip():
                        acik.append(m.group(1).strip())
    return {"toplam": biten + len(acik), "biten": biten, "acik_maddeler": acik}


def _todo_yol(klasor: str) -> str:
    return os.path.join(klasor, "todo.md")


def _todo_oku(yol: str) -> str:
    with open(yol, encoding="utf-8", newline="") as f:
        return f.read()


def todo_ekle_ihlali(klasor: str, metin: str) -> str | None:
    """Sıralı işte (P-005) madde eklenebilir mi: mevcut durum ve plan tamam, madde `P<n>:` ile planlı. Değilse neden."""
    if not SIRA.sirali_mi(klasor):
        return None
    eksik = SIRA.todo_onkosulu(klasor)
    if eksik:
        return SIRA.mesaj(eksik, "todo.md")
    ihlal = SIRA.todo_satir_ihlalleri(f"- [ ] {metin}", SIRA.plan_maddeleri(klasor))
    if ihlal:
        return "; ".join(ihlal)
    return _dogrulama_ihlali(klasor, f"- [ ] {metin}") or None


def _dogrulama_ihlali(klasor: str, metin: str) -> str:
    """Plan ✅/❌ kapısı: hook `_sira_kapisi` ile aynı işlevleri çağırır. Gölge modda boş döner (uyarı +
    günlük); kapı hata verirse sessiz geçer, yazımı bozmaz."""
    try:
        import plan_dogrulama as PD
        return PD.todo_onkosulu(klasor) or PD.todo_satir_engelleri(klasor, metin)
    except Exception:
        return ""


def todo_ekle(klasor: str, metin: str) -> str:
    """todo.md sonuna '- [ ] <metin>' ekler (kilit altında, atomik). Dönüş: eklenen madde metni.
    Sıralı işte madde `P<n>:` ile başlamalı ve plan tamam olmalı (ValueError)."""
    metin = " ".join(str(metin).split())
    if not metin:
        raise ValueError("madde metni boş")
    neden = todo_ekle_ihlali(klasor, metin)
    if neden:
        raise ValueError(neden)
    yol = _todo_yol(klasor)
    with L.kilit(yol):
        icerik = _todo_oku(yol) if os.path.exists(yol) else "# Yapılacaklar\n\n"
        # şablonun boş yer tutucu maddesi ('- [ ] ') gerçek madde sayılmaz: eklemeden önce atılır
        icerik = "".join(x for x in icerik.splitlines(keepends=True) if not _TODO_BOS.match(x.rstrip("\r\n")))
        if icerik and not icerik.endswith("\n"):
            icerik += "\n"
        L.atomik_yaz(yol, icerik + f"- [ ] {metin}\n")
    return metin


def todo_bitir(klasor: str, secici: str, not_: str | None = None) -> str:
    """Açık maddeyi [x] yapar. secici: 1-tabanlı açık madde sırası ya da tek eşleşen alt dize."""
    yol = _todo_yol(klasor)
    if not os.path.exists(yol):
        raise ValueError("todo.md yok")
    if SIRA.kaliteli_mi(klasor) and len((not_ or "").strip()) < SIRA.KANIT_MIN:
        raise ValueError("bitti işareti kanıt notu ister (P-018): --not \"kanıt: komut çıktısı ya da dosya:satır\"")
    with L.kilit(yol):
        satirlar = _todo_oku(yol).splitlines(keepends=True)
        acik = []  # (satır indeksi, madde metni)
        for i, s in enumerate(satirlar):
            m = _TODO_ACIK.match(s.rstrip("\r\n"))
            if m and m.group(1).strip():
                acik.append((i, m.group(1).strip()))
        secici = str(secici).strip()
        if re.fullmatch(r"\d+", secici):
            n = int(secici)
            if not 1 <= n <= len(acik):
                raise ValueError(f"açık madde sırası aralık dışı: {n} (açık madde: {len(acik)})")
            idx, metin = acik[n - 1]
        else:
            if not secici:
                raise ValueError("seçici boş")
            adaylar = [(i, t) for i, t in acik if secici.lower() in t.lower()]
            if len(adaylar) != 1:
                durum = "eşleşme yok" if not adaylar else f"{len(adaylar)} eşleşme"
                liste = adaylar or acik
                raise ValueError(f"'{secici}': {durum}; adaylar: " + " | ".join(t for _, t in liste))
            idx, metin = adaylar[0]
        satir = satirlar[idx]
        govde = satir.rstrip("\r\n")
        eol = satir[len(govde):]
        govde = re.sub(r"\[ \]", "[x]", govde, count=1)
        ek = f" — {datetime.date.today().isoformat()}: {not_}" if not_ else ""
        satirlar[idx] = govde + ek + eol
        L.atomik_yaz(yol, "".join(satirlar))
    return metin + ek


_TODO_AD = re.compile(r"(^|[-_.])todo([-_.].*)?\.md$", re.IGNORECASE)
_TODO_ATLA = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", "_arsiv"}
_TODO_DERINLIK = 6
_TODO_SURE_S = 1.5


def _norm(yol: str) -> str:
    return os.path.normcase(os.path.abspath(yol))


def _worktree_mi(yol: str, kok: str) -> bool:
    """Yol bir git worktree ya da kart çalışma ağacı içinde mi (`worktrees` yol parçası ya da üst dizinde `.git` DOSYASI)."""
    d = os.path.dirname(os.path.abspath(yol))
    kok = _norm(kok)
    parcalar = [p.lower() for p in d.replace("\\", "/").split("/")]
    if "worktrees" in parcalar:
        return True
    while d and _norm(d) != kok:
        if os.path.isfile(os.path.join(d, ".git")):
            return True
        ust = os.path.dirname(d)
        if ust == d:
            break
        d = ust
    return False


def _agac_koku_bul(yol: str, kok: str) -> str | None:
    """Yolun bulunduğu git çalışma ağacının kökü (üst dizinlerde `.git` DOSYASI olan; `kok`a kadar); yoksa None."""
    d = os.path.dirname(os.path.abspath(yol))
    kok = _norm(kok)
    while d and _norm(d) != kok:
        if os.path.isfile(os.path.join(d, ".git")):
            return d
        ust = os.path.dirname(d)
        if ust == d:
            break
        d = ust
    return None


def _worktree_kopyasi_gecerli_mi(yol: str, kok: str) -> bool:
    """Worktree içindeki todo kopyası bayat sayılmaz: ağacın durum kopyası devralınmış (`.devralindi`) ya da dosya
    ana ağaçtaki aynı göreli yolla bayt bayt aynı (yalnız dal çıkışı, taşınacak bir şey yok). ADR-0032."""
    agac = _agac_koku_bul(yol, kok)
    if not agac:
        return False
    if os.path.isfile(os.path.join(agac, ".claude", "orkestra", "devralindi_yok_say")):
        return True
    if os.path.isfile(os.path.join(agac, ".claude", "orkestra", ".devralindi")):
        return True
    ana = os.path.join(kok, os.path.relpath(yol, agac))
    try:
        with open(yol, "rb") as f1, open(ana, "rb") as f2:
            return f1.read() == f2.read()
    except OSError:
        return False


def devral_ipucu(sd: str, cwd: str | None = None) -> str:
    """Oturum ağacındaki durum kopyasında ana durum klasöründe olmayan kayıt varsa TEK satır öneri, yoksa boş metin."""
    try:
        agac = L.git_koku(cwd or os.getcwd())
        if not agac:
            return ""
        kaynak = os.path.join(agac, ".claude", "orkestra")
        if not os.path.isdir(kaynak) or os.path.normcase(os.path.realpath(kaynak)) == os.path.normcase(os.path.realpath(sd)):
            return ""
        import durum_devral
        n = durum_devral.devralinmamis_sayisi(kaynak, sd)
        if not n:
            return ""
        return (f"Orkestra: bu worktree'nin durum kopyasında ana klasörde olmayan {n} kayıt var; "
                "`orkestra durum devral --uygula` ile ana klasöre al.")
    except Exception:
        return ""


def todo_denetle(sd: str, kok: str | None = None) -> list[dict]:
    """isler.json'a bağlı olmayan todo dosyaları: [{'yol', 'tur': 'bagsiz'|'worktree'}].

    Bağlı sayılan: bir işin klasöründeki `todo.md`. Diğer `todo.md` / `todo*.md` kopyaları (iş klasörü dışında ya da
    farklı adla) ve worktree içindekiler listelenir; ana ağaçla aynı olan ya da durumu devralınmış worktree kopyaları
    listelenmez. `kok` varsayılanı projedir; derinlik ve süre sınırlıdır (hatada sessiz)."""
    kok = os.path.abspath(kok or L.proje_dizini())
    bagli = {_norm(os.path.join(g.get("klasor") or "", "todo.md")) for g in is_liste(sd) if g.get("klasor")}
    atla_sd = _norm(sd)
    son = time.monotonic() + _TODO_SURE_S
    out = []

    def gez(d, derinlik):
        if derinlik > _TODO_DERINLIK or time.monotonic() > son:
            return
        try:
            girdiler = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            return
        for e in girdiler:
            try:
                if e.is_dir(follow_symlinks=False):
                    if e.name in _TODO_ATLA or _norm(e.path) == atla_sd:
                        continue
                    gez(e.path, derinlik + 1)
                elif _TODO_AD.search(e.name) and _norm(e.path) not in bagli:
                    out.append({"yol": e.path, "tur": "worktree" if _worktree_mi(e.path, kok) else "bagsiz"})
            except OSError:
                continue

    gez(kok, 0)
    return out


def todo_denetle_satiri(sd: str, kok: str | None = None) -> str:
    """Sorun varsa TEK satırlık uyarı, yoksa boş metin."""
    r = todo_denetle(sd, kok)
    if not r:
        return ""
    w = sum(1 for x in r if x["tur"] == "worktree")
    return (f"Orkestra: {len(r)} todo dosyası işe bağlı değil ({w} worktree kopyası) — bayatlar; "
            "`orkestra is todo-denetle` ile gör, işin todo.md'sine taşı.")


def todo_madde_bitir(sd: str, is_id: str, madde: str, gid: str) -> tuple[bool, str]:
    """Kartın `madde` alanını işin todo.md'sinde [x] yapar. (başarılı, ileti); eşleşme yok/çok ise (False, uyarı). Asla atmaz."""
    try:
        kayit = is_al(sd, is_id) if is_id else None
        if not kayit:
            return False, f"madde işaretlenemedi: iş bulunamadı ({is_id or 'bağsız'})"
        m = todo_bitir(kayit["klasor"], madde, f"{gid} teslim")
        return True, f"todo [x]: {m}"
    except (ValueError, OSError, TimeoutError, KeyError) as e:
        return False, f"madde işaretlenemedi: {e}"


def todo_bitmis_kartli(sd: str, is_id: str) -> list[tuple[int, str, str]]:
    """İşin açık todo maddelerinde anılan ve kartı teslim/iptal olan G-NNN'ler: [(açık madde sırası, kart id, durum)]."""
    kayit = is_al(sd, is_id) if is_id else None
    if not kayit:
        return []
    out = []
    for n, m in enumerate(todo_ozet(kayit["klasor"])["acik_maddeler"], 1):
        for gid in dict.fromkeys(re.findall(r"(?<![\w-])G-\d+(?!\w)", m)):
            k = L.kart_oku(sd, gid)
            if k:
                d = L.kart_durumu_hesapla(k)
                if d in ("teslim", "iptal"):
                    out.append((n, gid, d))
    return out


VARSAYILAN_TODO_ISI = "Orkestra açık maddeler"


def todo_varsayilan_is(sd: str) -> str | None:
    """Panel Yapılacaklar için varsayılan iş: açık işlerde 'Orkestra açık maddeler' başlıklısı, yoksa ilk açık iş."""
    acik = is_liste(sd, "acik")
    for g in acik:
        if (g.get("baslik") or "").strip().lower() == VARSAYILAN_TODO_ISI.lower():
            return g["id"]
    return acik[0]["id"] if acik else None


def todo_liste(klasor: str) -> dict:
    """todo.md'nin açık ve biten maddeleri (metin listeleri); dosya yoksa boş."""
    yol = _todo_yol(klasor)
    acik, biten = [], []
    if os.path.exists(yol):
        for satir in _todo_oku(yol).splitlines():
            m = _TODO_UST_BITEN.match(satir)
            if m:
                if m.group(1).strip():
                    biten.append(m.group(1).strip())
                continue
            m = _TODO_UST_ACIK.match(satir)
            if m and m.group(1).strip():
                acik.append(m.group(1).strip())
    return {"acik_maddeler": acik, "biten_maddeler": biten}



_TODO_KUTU = re.compile(r"^[-*]\s*\[( |x|X|~)\]\s*(.*)$")
_TODO_ALT = re.compile(r"^\s+[-*]\s+(?:\[[ xX~]\]\s*)?(.*)$")
_TODO_ADIM = re.compile(r"(?<![\w-])G\d+[a-z]?(?:-[A-Za-z]\d+|/[A-Za-z]?\d+|-G\d+)*(?![\w])")
_TODO_TARIH = re.compile(r"\s*\(\d{1,2}\.\d{1,2}[^)]*\)\s*$")


def _todo_dosyasi(klasor: str) -> str | None:
    if not os.path.isdir(klasor):
        return None
    for ad in sorted(os.listdir(klasor)):
        if ad.lower() == "todo.md":
            return os.path.join(klasor, ad)
    return None


def _todo_metin(ham: str) -> str:
    t = ham.replace("**", "").replace("`", "")
    t = t.split(" → ", 1)[0].strip()
    while True:
        y = _TODO_TARIH.sub("", t)
        if y == t:
            break
        t = y
    t = t.strip()
    return t if len(t) <= 100 else t[:99] + "…"


def todo_maddeleri(klasor: str) -> list[dict]:
    """TODO.md'nin üst düzey onay kutulu maddeleri (dosya sırası)."""
    yol = _todo_dosyasi(klasor)
    if not yol:
        return []
    out, bolum, son = [], "", None
    with open(yol, encoding="utf-8-sig", errors="replace") as f:
        for satir in f:
            satir = satir.rstrip("\r\n")
            if satir.startswith("##"):
                bolum = satir.lstrip("#").strip()
                son = None
                continue
            m = _TODO_KUTU.match(satir)
            if not m:
                a = _TODO_ALT.match(satir)
                if a and son is not None and len(son["alt"]) < 8:
                    t = _todo_metin(a.group(1))
                    if t:
                        son["alt"].append(t)
                elif satir.strip() and not satir[0].isspace():
                    son = None
                continue
            ham = m.group(2).replace("**", "").replace("`", "")
            if not ham.strip():
                son = None
                continue  # boş şablon maddesi
            adimlar = []
            for a in _TODO_ADIM.findall(ham):
                if a not in adimlar:
                    adimlar.append(a)
            out.append({"durum": {" ": "acik", "~": "suruyor"}.get(m.group(1), "bitti"),
                        "metin": _todo_metin(m.group(2)), "adimlar": adimlar, "bolum": bolum,
                        "alt": []})
            son = out[-1]
    return out


_KOVA = {"teslim": "yapildi", "isleniyor": "simdi", "denetimde": "simdi", "onaylandi": "simdi",
         "planlandi": "sirada", "beklemede": "sirada", "reddedildi": "sirada", "iptal": "iptal"}


def _eslesir(madde_adim: str, kart_adim: str) -> bool:
    return (madde_adim == kart_adim or kart_adim.startswith(madde_adim + "-")
            or madde_adim.startswith(kart_adim + "-"))


def _kart_no(k: dict):
    m = re.search(r"\d+", str(k.get("id", "")))
    return (int(m.group()) if m else 0, str(k.get("id", "")))


def is_serit(sd: str, is_id: str, alt: bool = False, tum_kartlar: list[dict] | None = None) -> dict:
    """Bir iş için yapıldı/şimdi/sırada/planda-kart-yok/iptal kovaları (deterministik)."""
    kayit = is_al(sd, is_id)
    giris = next((g for g in is_liste(sd) if g["id"] == is_id), None)
    if not kayit or not giris:
        raise KeyError(f"iş yok: {is_id}")
    klasor = giris["klasor"]
    maddeler = todo_maddeleri(klasor)
    tum = tum_kartlar if tum_kartlar is not None else L.kartlar(sd, derin=False)  # yalnız okunur
    kartlar = sorted((k for k in tum if k.get("is") == is_id), key=_kart_no)
    durumlar = {k.get("id"): k.get("durum") for k in tum}
    kovalar = {"yapildi": [], "simdi": [], "sirada": [], "planda_kart_yok": [], "iptal": []}
    kart_adimlari = [(k["adim"], k.get("durum")) for k in kartlar if k.get("adim")]
    for md in maddeler:
        esl = [d for a in md["adimlar"] for ka, d in kart_adimlari if _eslesir(a, ka)]
        if md["durum"] == "bitti":
            if any(d != "iptal" for d in esl):
                continue
        else:
            # bitmemiş kart yalnız metni o adımla BAŞLAYAN açık/süren maddeyi gizler
            esl_bas = [d for a in md["adimlar"] if md["metin"].startswith(a)
                       for ka, d in kart_adimlari if _eslesir(a, ka)]
            if any(d not in ("teslim", "iptal") for d in esl_bas):
                continue
        kova = {"bitti": "yapildi", "suruyor": "simdi"}.get(md["durum"], "planda_kart_yok")
        oge = {"tur": "madde", "metin": md["metin"], "adimlar": md["adimlar"],
               "bolum": md["bolum"], "durum": md["durum"]}
        if alt:  # yalnız panel /isler.json; CLI çıktısı değişmez
            oge["alt"] = list(md.get("alt") or [])
        kovalar[kova].append(oge)
    for k in kartlar:
        kova = _KOVA.get(k.get("durum"))
        if not kova:
            continue
        bek = [b for b in (k.get("bagimliliklar") or [])
               if durumlar.get(b) not in ("teslim", "onaylandi")]
        kovalar[kova].append({"tur": "kart", "kart": k["id"], "adim": k.get("adim"),
                              "metin": (k.get("teslim_ozeti") if k.get("durum") == "teslim" else None)
                              or k.get("baslik", ""),
                              "durum": k.get("durum"), "bekledigi": bek})
    biten = sum(1 for m in maddeler if m["durum"] == "bitti")
    return {"is": {"id": is_id, "baslik": giris.get("baslik", ""), "durum": giris.get("durum"),
                   "klasor": klasor},
            "ilerleme": {"biten": biten, "toplam": len(maddeler)}, **kovalar}


_IS_ONEK = re.compile(r"^(?:\d{1,4}-)?\d{8}-")


def is_adi(baslik) -> str:
    """Okunur iş adı: 'NNN-YYYYMMDD-' öneki atılır, kalan '-' boşluk olur (Jira kodu tireli kalır).
    Öneksiz başlık aynen döner."""
    b = baslik or ""
    if not _IS_ONEK.match(b):
        return b
    kalan = _IS_ONEK.sub("", b, count=1)
    m = re.match(r"^([A-Z][A-Z0-9]+-\d+)(?:-(.*))?$", kalan)
    if m:
        return m.group(1) + (" " + m.group(2).replace("-", " ") if m.group(2) else "")
    return kalan.replace("-", " ")


def onar(sd: str, ek_klasorler=None, uygula: bool = False) -> dict:
    """Merkez isler.json'u iş klasörlerindeki is.json kayıtlarından yeniden kurar.

    Bilinen klasörler: merkezdeki girişler + ek_klasorler. is.json okunamayan klasör atlanır
    (merkezdeki girişi silinmez). Sayaç düşmez: max(mevcut sayaç, en büyük I-NNN).
    Varsayılan kuru koşu: dosya yazmaz. Dönüş: {"farklar": [metin], "uyarilar": [metin], "yazildi": bool}.
    """
    yol = _merkez(sd)
    with (L.kilit(yol) if uygula else contextlib.nullcontext()):  # kuru koşu kilit/dosya oluşturmaz
        var_mi = os.path.exists(yol)
        mevcut = _oku(yol, _BOS)
        isler = {i: dict(g) for i, g in (mevcut.get("isler") or {}).items()}
        klasorler = []
        for g in isler.values():
            if g.get("klasor"):
                klasorler.append(os.path.abspath(g["klasor"]))
        klasorler += [os.path.abspath(k) for k in (ek_klasorler or [])]
        farklar, uyarilar = [], []
        gorulen = set()
        for k in klasorler:
            if k in gorulen:
                continue
            gorulen.add(k)
            try:
                kayit = _oku(_is_json_yolu(k), None)
            except (OSError, ValueError):
                kayit = None
            if not isinstance(kayit, dict) or not _ID.match(str(kayit.get("id", ""))):
                uyarilar.append(f"atlandı (geçerli is.json yok): {k}")
                continue
            i = kayit["id"]
            yeni = {"klasor": k, "baslik": kayit.get("baslik", ""), "durum": kayit.get("durum", "acik"),
                    "olusturma": kayit.get("olusturma", "")}
            eski = isler.get(i)
            if eski is None:
                farklar.append(f"{i}: merkezde eksik, eklenecek ({k})")
                isler[i] = yeni
                continue
            for alan, deger in yeni.items():
                onceki = eski.get(alan)
                if alan == "klasor" and onceki:
                    onceki = os.path.abspath(onceki)
                if onceki != deger:
                    farklar.append(f"{i}: {alan} {onceki!r} -> {deger!r}")
                    eski[alan] = deger
        en_buyuk = max([is_no(i) for i in isler] or [0])
        sayac = int(mevcut.get("sayac", 0))
        if sayac < en_buyuk:
            farklar.append(f"sayac: {sayac} -> {en_buyuk}")
            sayac = en_buyuk
        yazildi = False
        if uygula and (farklar or not var_mi) and (farklar or isler):
            _yaz(yol, {**mevcut, "sayac": sayac, "isler": isler})
            yazildi = True
    return {"farklar": farklar, "uyarilar": uyarilar, "yazildi": yazildi}


def is_usd_ve_harcama_son(sd: str, kartlar: list[dict]) -> tuple[dict, dict]:
    """({iş: usd}, {iş: son harcama zamanı}) — İşler ve Teknik sayfaları aynı atama kuralını (L.satir_isi) kullanır."""
    kart_is = {k["id"]: k.get("is") for k in kartlar if k.get("id") and k.get("is")}
    usd: dict = {}
    son: dict = {}
    for r in L.maliyet_kayitlari(sd):
        i = L.satir_isi(r, kart_is)
        usd[i] = usd.get(i, 0.0) + (r.get("maliyet_usd", 0) or 0)
        z = r.get("zaman") or ""
        if z > son.get(i, ""):
            son[i] = z
    return usd, son


def is_pencere_toplamlari(sd: str, kartlar: list[dict], bugun: datetime.date | None = None) -> dict:
    """{iş: {pencere: {usd, token}}} — is_usd_ve_harcama_son ile aynı atama kuralı, L.pencere_icinde ile aynı pencere (I-137)."""
    kart_is = {k["id"]: k.get("is") for k in kartlar if k.get("id") and k.get("is")}
    return L.pencere_toplamlari(L.maliyet_kayitlari(sd), bugun or datetime.date.today(), lambda r: L.satir_isi(r, kart_is))


def kart_pencere_toplamlari(sd: str, bugun: datetime.date | None = None) -> dict:
    """{kart: {pencere: {usd, token}}} — kartın defter satırlarından (gorev alanı)."""
    return L.pencere_toplamlari(L.maliyet_kayitlari(sd), bugun or datetime.date.today(),
                                lambda r: r.get("gorev") if r.get("gorev") not in (None, "-") else None)


def is_kalem(sd: str, kartlar: list[dict]) -> dict:
    """{iş: L.kalemler(satırlar)} — is_usd_ve_harcama_son ile aynı atama kuralı (I-064: token ve USD dört kalemle)."""
    kart_is = {k["id"]: k.get("is") for k in kartlar if k.get("id") and k.get("is")}
    grup: dict = {}
    for r in L.maliyet_kayitlari(sd):
        grup.setdefault(L.satir_isi(r, kart_is), []).append(r)
    return {i: L.kalemler(s) for i, s in grup.items()}


def is_son_etkinlik(g: dict, kart_guncellemeleri, harcama_son: str = "") -> str:
    """İşin son etkinlik zamanı: kartların güncellemesi, işin is.json güncellemesi, son harcama ve todo.md değişikliğinin
    en geçidir; hiçbiri yoksa oluşturma zamanı. Panelde sıralama ve 'x gün önce' etiketi bunu kullanır."""
    adaylar = [z for z in kart_guncellemeleri if z]
    if harcama_son:
        adaylar.append(harcama_son)
    klasor = g.get("klasor") or ""
    if klasor and os.path.isdir(klasor):
        try:
            with open(_is_json_yolu(klasor), encoding="utf-8") as f:
                z = (json.load(f) or {}).get("guncelleme")
            if z:
                adaylar.append(str(z))
        except (OSError, ValueError, AttributeError):
            pass
        try:
            mt = os.path.getmtime(os.path.join(klasor, "todo.md"))
            adaylar.append(datetime.datetime.fromtimestamp(mt).astimezone().isoformat(timespec="seconds"))
        except OSError:
            pass
    return max(adaylar) if adaylar else (g.get("olusturma") or "")


def is_oturumlari(g: dict) -> list[str]:
    """İşin is.json'unda bağlı oturum kimlikleri (kart açılmamış işlerde sohbet–iş bağının tek kaynağı)."""
    klasor = g.get("klasor") or ""
    try:
        with open(_is_json_yolu(klasor), encoding="utf-8") as f:
            return [o["oturum"] for o in (json.load(f) or {}).get("oturumlar") or [] if isinstance(o, dict) and o.get("oturum")]
    except (OSError, ValueError, AttributeError):
        return []
