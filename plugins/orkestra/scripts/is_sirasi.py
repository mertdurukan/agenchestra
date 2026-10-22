"""İş sırası (P-005): mevcut_durum_<gün>.md → plan.md → todo.md. Her adım bir öncekinden beslenir.

Saf Python, yalnız okur; model çağrılmaz. Bir iş `is ac` ile açılırken is.json'a `sira` bayrağı konur;
bayraksız (eski) işler ve `ORKESTRA_SIRA_KAPISI=0` kapıyı atlar.

Ön koşul, önceki adımın TAMAM olmasıdır; tamam tanımı deterministiktir:
- mevcut durum: dosya var, 5 bölümün her birinde yer tutucu dışında içerik var, `**Ölçüm saati:**` dolu,
  §3'te (etki haritası) en az bir madde.
- plan: dosya var, ilk satırlarda mevcut durum dosyasına bağlantı var, en az bir `P<n>` maddesi var,
  her maddede geçerli `MD §<k>` dayanağı var.
- todo satırı: `P<n>` ile başlar ve `P<n>` planda var.

Gap analizi (P-017, is.json `gap: true` olan işlerde; bayraksız işler ve `ORKESTRA_GAP_KAPISI=0` muaf), iki geçiş:
- Birinci geçiş (plandan önce): mevcut durumun `## 6. Gap analizi` bölümünde en az bir `**G<n>**` satırı olmadan
  mevcut durum tamam sayılmaz (plan.md yazılamaz).
- İkinci geçiş (plandan sonra): MD §6'daki her G bir P maddesinin `**Gap:**` alanında anılır ya da plandaki
  `## Gap kapsama` bölümünde `Kapsam dışı: <gerekçe>` ile gerekçelendirilir; her P'nin `**Gap:**` alanı MD'de
  var olan G'leri gösterir.
"""
from __future__ import annotations

import json
import os
import re

SIRA_ADI = "mevcut-durum-plan-todo"
BOLUM_SAYISI = 5
ETKI_BOLUMU = 3
GAP_BOLUMU = 6
BAGLANTI_PENCERE = 20  # plan.md'nin bu kadar ilk satırında mevcut duruma bağlantı aranır

_MD_AD = re.compile(r"^mevcut_durum_\d{8}\.md$")
_YORUM = re.compile(r"<!--.*?-->", re.S)
_BOLUM_BASLIK = re.compile(r"^##\s+(\d+)\.\s.*$", re.M)
_MADDE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+\S", re.M)
_OLCUM = re.compile(r"\*\*Ölçüm saati:\*\*[ \t]*(.*)$", re.M)
_P_SATIRI = re.compile(r"^(?:#{2,4}\s+|[-*]\s+(?:\*\*)?)P(\d+)\b", re.M)
_GAP_SATIRI = re.compile(r"^\s*[-*]\s+\*\*G(\d+):?\*\*", re.M)
_GAP_ALANI = re.compile(r"\*\*Gap:\*\*[ \t]*(.*)$", re.M)
_GAP_NO = re.compile(r"\bG(\d+)\b")
_KAPSAM_DISI = re.compile(r"^\s*[-*]\s+\*\*G(\d+):?\*\*.*?Kapsam dışı:\s*(.*)$", re.M)
_OZET_BOLUMU = re.compile(r"^##[ \t]+Özet[ \t]*$(.*?)(?=^##[ \t]|^\*\*[^\n*]+:\*\*|\Z)", re.M | re.S)
KANIT_MIN = 8  # todo [x] satırında " — " sonrası not en az bu kadar karakter
GAP_GEREKCE_MIN = 8  # "Kapsam dışı:" sonrası gerekçe en az bu kadar karakter
_DAYANAK = re.compile(r"MD\s*§\s*(\d+)")
_TODO_SATIR = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*(.*)$")
_TODO_P = re.compile(r"^P(\d+)\b")


def kapi_acik() -> bool:
    return os.environ.get("ORKESTRA_SIRA_KAPISI") != "0"


def gap_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_GAP_KAPISI") != "0"


def gapli_mi(klasor: str) -> bool:
    """İş sıralı, is.json `gap: true` taşıyor ve gap kapısı açık mı (P-017)."""
    if not gap_kapisi_acik() or not sirali_mi(klasor):
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f).get("gap") is True
    except (OSError, ValueError):
        return False


def harita_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_HARITA_KAPISI") != "0"


def haritali_mi(klasor: str) -> bool:
    """İş sıralı, is.json `harita: true` taşıyor ve harita kapısı açık mı (ADR-0005)."""
    if not harita_kapisi_acik() or not sirali_mi(klasor):
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f).get("harita") is True
    except (OSError, ValueError):
        return False


_MEVCUT_VARLIK = re.compile(r"\*\*Mevcut varlık:\*\*[ \t]*(.*)$", re.M)
VARLIK_GEREKCE_MIN = 8  # `yok — <aranan>` sonrası gerekçe en az bu kadar karakter


def mevcut_varlik_eksikleri(klasor: str) -> list[str]:
    """ADR-0005: haritalı işte her P maddesi `**Mevcut varlık:**` taşır: harita kayıt kimlikleri ya da `yok — <aranan>`."""
    if not haritali_mi(klasor):
        return []
    import harita
    metin = _oku(os.path.join(klasor, "plan.md")) or ""
    sd = harita.sd_bul(klasor)
    kimlikler = harita.kayit_kimlikleri(sd) if sd else None
    eksik = []
    for n, blok in sorted(_p_bloklari(metin).items()):
        m = _MEVCUT_VARLIK.search(blok)
        deger = (m.group(1) if m else "").strip()
        if not deger:
            eksik.append(f"P{n}: `**Mevcut varlık:**` alanı yok ya da boş (`orkestra harita oku` kayıt kimliği ya da `yok — <aranan>`)")
        elif re.match(r"^yok\b", deger, re.I):
            gerekce = re.sub(r"^yok\s*[—:\-]*\s*", "", deger, flags=re.I)
            if len(gerekce) < VARLIK_GEREKCE_MIN:
                eksik.append(f"P{n}: `yok` için aranan şey yazılmalı (`yok — <aranan>`)")
        elif kimlikler is None:
            eksik.append(f"P{n}: sistem haritası yok; önce `orkestra harita oku` çalıştır")
        else:
            for kid in [x.strip(" `") for x in deger.split(",") if x.strip(" `")]:
                if kid not in kimlikler:
                    eksik.append(f"P{n}: `{kid}` haritada yok (`orkestra harita oku` ile kimliği doğrula)")
    return eksik


def kalite_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_KALITE_KAPISI") != "0"


def kaliteli_mi(klasor: str) -> bool:
    """İş sıralı, is.json `kalite: true` taşıyor ve kalite kapısı açık mı (P-018 belge çıtası)."""
    if not kalite_kapisi_acik() or not sirali_mi(klasor):
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f).get("kalite") is True
    except (OSError, ValueError):
        return False


_SOZLESME_AD = re.compile(r"^sozlesme_\d{8}\.md$")
_S_SATIRI = re.compile(r"^\s*[-*]\s+\*\*S(\d+):?\*\*", re.M)
_S_NO = re.compile(r"\bS(\d+)\b")
SOZLESME_BOLUMLERI = ("Problem", "Başarı kriterleri", "Kapsam dışı", "Kısıtlar")


def sozlesme_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_SOZLESME_KAPISI") != "0"


def sozlesmeli_mi(klasor: str) -> bool:
    """İş sıralı, is.json `sozlesme: true` taşıyor ve sözleşme kapısı açık mı (ADR-0035 görev sözleşmesi)."""
    if not sozlesme_kapisi_acik() or not sirali_mi(klasor):
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f).get("sozlesme") is True
    except (OSError, ValueError):
        return False


def sozlesme_yolu(klasor: str) -> str | None:
    """En yeni `sozlesme_<YYYYMMDD>.md`; yoksa None."""
    try:
        adlar = sorted(a for a in os.listdir(klasor) if _SOZLESME_AD.match(a))
    except OSError:
        return None
    return os.path.join(klasor, adlar[-1]) if adlar else None


def _baslik_bolumu(metin: str, ad: str) -> str:
    m = re.search(rf"^##[ \t]+{re.escape(ad)}[ \t]*$(.*?)(?=^##[ \t]|\Z)", metin or "", re.M | re.S)
    return _YORUM.sub("", m.group(1)).strip() if m else ""


def sozlesme_kriterleri(klasor: str) -> set[int]:
    """Sözleşme `## Başarı kriterleri` altındaki S numaraları."""
    yol = sozlesme_yolu(klasor)
    metin = _oku(yol) if yol else None
    return {int(n) for n in _S_SATIRI.findall(_baslik_bolumu(metin or "", "Başarı kriterleri"))}


def sozlesme_eksikleri(klasor: str, baglanti: bool = False) -> list[str]:
    """Sözleşmeli işte sözleşmenin eksikleri (boş liste = tamam). `baglanti`: plan maddelerinin sözleşme kriterine
    bağını da denetler (P2). Sözleşmesiz iş için boş liste."""
    if not sozlesmeli_mi(klasor):
        return []
    yol = sozlesme_yolu(klasor)
    if yol is None:
        return ["sozlesme_<YYYYMMDD>.md yok (`orkestra is belge <id> sozlesme`)"]
    metin = _oku(yol) or ""
    eksik = []
    e = ozet_eksigi(metin, "sözleşme")
    if e:
        eksik.append(e)
    for ad in SOZLESME_BOLUMLERI:
        if not _baslik_bolumu(metin, ad):
            eksik.append(f"sözleşme: `## {ad}` bölümü yok ya da boş")
    if not sozlesme_kriterleri(klasor) and _baslik_bolumu(metin, "Başarı kriterleri"):
        eksik.append("sözleşme: `## Başarı kriterleri` altında `- **S1:** …` satırı yok")
    if baglanti:
        eksik += sozlesme_baglanti_eksikleri(klasor)
    return eksik


def sozlesme_baglanti_eksikleri(klasor: str) -> list[str]:
    """P2: her P maddesi `**Sözleşme:** S<n>` ile sözleşmedeki bir kriteri gösterir; her S bir P'de anılır."""
    metin = _oku(os.path.join(klasor, "plan.md"))
    if metin is None:
        return []
    kriterler = sozlesme_kriterleri(klasor)
    if not kriterler:
        return []
    eksik, anilan = [], set()
    for n, blok in sorted(_p_bloklari(metin).items()):
        m = re.search(r"\*\*Sözleşme:\*\*[ \t]*(.*)$", _YORUM.sub("", blok), re.M)
        nolar = {int(x) for x in _S_NO.findall(m.group(1))} if m else set()
        if not nolar:
            eksik.append(f"P{n}: `**Sözleşme:**` alanı yok ya da S<n> içermiyor (sözleşme kriteri: {', '.join(f'S{k}' for k in sorted(kriterler))})")
        elif not nolar <= kriterler:
            eksik.append(f"P{n}: `**Sözleşme:**` alanındaki S{sorted(nolar - kriterler)[0]} sözleşmede yok")
        anilan |= nolar
    eksik += [f"S{k}: hiçbir plan maddesinin `**Sözleşme:**` alanında anılmıyor" for k in sorted(kriterler - anilan)]
    return eksik


def sozlesme_engeli(klasor: str, baglanti: bool = False) -> list[str]:
    """Sessiz kapı: yalnız `ihlal` modunda sözleşme eksiklerini döndürür (adim ve ön koşullar sık çağrılır, gölge kayıt düşmez)."""
    if not sozlesmeli_mi(klasor):
        return []
    import kapi_mod as KM
    return sozlesme_eksikleri(klasor, baglanti) if KM.mod("sozlesme", klasor) == "ihlal" else []


def sozlesme_uyari(klasor: str, baglanti: bool = True) -> list[str]:
    """Sesli kapı (plan yazımı, `is sira`): gölge modunda uyarır ve `kapi_golge` kaydı düşer, ihlal modunda eksikleri döndürür."""
    if not sozlesmeli_mi(klasor):
        return []
    import kapi_mod as KM
    return KM.ihlal_ver(klasor, "sozlesme", sozlesme_eksikleri(klasor, baglanti))


def ozet_eksigi(metin: str, ad: str) -> str | None:
    """Belgede `## Özet` bölümü var ve yer tutucu dışında içerik taşıyor mu; değilse neden."""
    m = _OZET_BOLUMU.search(metin or "")
    if m is None:
        return f"{ad}: `## Özet` bölümü yok (P-018)"
    if not _YORUM.sub("", m.group(1)).strip():
        return f"{ad}: `## Özet` bölümü boş (P-018)"
    return None


def alan_dolu(blok: str, alan: str) -> bool:
    """P bloğunda `**<alan>:**` etiketi var ve yer tutucu dışında değeri var mı (değer aynı ya da sonraki satırda olabilir)."""
    m = re.search(r"\*\*" + re.escape(alan) + r":\*\*(.*?)(?=^\*\*[^\n*]+:\*\*|\Z)", _YORUM.sub("", blok), re.S | re.M)
    return bool(m and m.group(1).strip())


def sirali_mi(klasor: str) -> bool:
    """Klasördeki is.json `sira` bayrağı taşıyor ve kapı açık mı."""
    if not kapi_acik():
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            veri = json.load(f)
        return isinstance(veri, dict) and veri.get("sira") == SIRA_ADI
    except (OSError, ValueError):
        return False


def mevcut_durum_yolu(klasor: str) -> str | None:
    """En yeni `mevcut_durum_<YYYYMMDD>.md` (ad sıralaması = tarih sıralaması); yoksa None."""
    try:
        adlar = sorted(a for a in os.listdir(klasor) if _MD_AD.match(a))
    except OSError:
        return None
    return os.path.join(klasor, adlar[-1]) if adlar else None


def _oku(yol: str) -> str | None:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _bolumler(metin: str) -> dict[int, str]:
    parcalar = _BOLUM_BASLIK.split(metin)
    return {int(parcalar[i]): parcalar[i + 1] for i in range(1, len(parcalar) - 1, 2)}


def _icerik(govde: str) -> str:
    return _YORUM.sub("", govde).strip()


def mevcut_durum_eksikleri(klasor: str) -> list[str]:
    """Boş liste = mevcut durum tamam."""
    yol = mevcut_durum_yolu(klasor)
    if yol is None:
        return ["mevcut_durum_<YYYYMMDD>.md yok (`orkestra is belge <id> mevcut_durum`)"]
    metin = _oku(yol) or ""
    eksik = []
    sade = _YORUM.sub("", metin)
    m = _OLCUM.search(sade)
    if not m:
        eksik.append("mevcut durum: `**Ölçüm saati:**` alanı yok")
    else:
        sonra = sade[m.end():].lstrip("\n")
        dolu = m.group(1).strip() or (sonra.split("\n\n", 1)[0].strip() if not sonra.startswith("**") else "")
        if not dolu or dolu.startswith("#"):
            eksik.append("mevcut durum: `**Ölçüm saati:**` boş")
    bolumler = _bolumler(metin)
    for n in range(1, BOLUM_SAYISI + 1):
        if n not in bolumler:
            eksik.append(f"mevcut durum: `## {n}.` bölümü yok")
        elif not _icerik(bolumler[n]):
            eksik.append(f"mevcut durum §{n} boş")
        elif n == ETKI_BOLUMU and not _MADDE.search(_icerik(bolumler[n])):
            eksik.append(f"mevcut durum §{n} (etki haritası) madde içermiyor")
    if kaliteli_mi(klasor):
        e = ozet_eksigi(metin, "mevcut durum")
        if e:
            eksik.append(e)
    if gapli_mi(klasor):
        g = bolumler.get(GAP_BOLUMU)
        if g is None:
            eksik.append(f"mevcut durum: `## {GAP_BOLUMU}. Gap analizi` bölümü yok (P-017 birinci geçiş)")
        elif not _GAP_SATIRI.search(_icerik(g)):
            eksik.append(f"mevcut durum §{GAP_BOLUMU} (gap analizi) `- **G1:** hedef → mevcut → fark` satırı içermiyor")
    return eksik


def mevcut_durum_gapleri(klasor: str) -> set[int]:
    """Mevcut durum §6'daki G numaraları."""
    yol = mevcut_durum_yolu(klasor)
    metin = _oku(yol) if yol else None
    g = _bolumler(metin).get(GAP_BOLUMU) if metin else None
    return {int(n) for n in _GAP_SATIRI.findall(_icerik(g))} if g else set()


def gap_kapsama_eksikleri(klasor: str) -> list[str]:
    """İkinci geçiş (P-017): MD §6 gap'leri ile plan maddeleri arasında kapsama. Gap'siz işte boş liste."""
    if not gapli_mi(klasor):
        return []
    metin = _oku(os.path.join(klasor, "plan.md")) or ""
    gaplar = mevcut_durum_gapleri(klasor)
    if not gaplar:
        return []  # birinci geçiş eksiği mevcut_durum_eksikleri'nde raporlanır
    sade = _YORUM.sub("", metin)
    kapanan: set[int] = set()
    eksik = []
    for n, blok in sorted(_p_bloklari(metin).items()):
        m = _GAP_ALANI.search(blok)
        no = {int(x) for x in _GAP_NO.findall(m.group(1))} if m else set()
        if not no:
            eksik.append(f"P{n}: `**Gap:** G<n>` alanı yok (hangi gap'i kapatıyor)")
            continue
        for x in sorted(no - gaplar):
            eksik.append(f"P{n}: G{x} mevcut durum §{GAP_BOLUMU}'da yok")
        kapanan |= no & gaplar
    disi = {int(n): g.strip() for n, g in _KAPSAM_DISI.findall(sade)}
    for n in sorted(gaplar - kapanan):
        if len(disi.get(n, "")) < GAP_GEREKCE_MIN:
            eksik.append(f"G{n}: hiçbir P kapatmıyor ve `## Gap kapsama` bölümünde gerekçeli `Kapsam dışı:` yok")
    return eksik


def _p_bloklari(metin: str) -> dict[int, str]:
    """{P numarası: blok metni}; blok bir sonraki P satırına ya da `## ` başlığına kadar sürer."""
    satirlar = _YORUM.sub("", metin).splitlines()  # şablonun yer tutucu yorumundaki örnek P satırı sayılmaz
    bloklar: dict[int, list[str]] = {}
    gecerli = None
    # Başlık biçimli (`### P1`) madde varsa yalnız başlıklar madde başlatır; gövdedeki "- P1 testleri…" gibi madde işaretli
    # satırlar bir önceki maddeyi bölmez (I-057). Başlık yoksa eski madde işaretli biçim geçerlidir.
    baslik_var = any(re.match(r"^#{2,4}\s+P\d+", s) for s in satirlar)
    for s in satirlar:
        m = _P_SATIRI.match(s)
        if m and baslik_var and not s.lstrip().startswith("#"):
            m = None
        if m:
            gecerli = int(m.group(1))
            bloklar.setdefault(gecerli, []).append(s)
        elif re.match(r"^##\s", s):
            gecerli = None
        elif gecerli is not None:
            bloklar[gecerli].append(s)
    return {n: "\n".join(b) for n, b in bloklar.items()}


def plan_maddeleri(klasor: str) -> set[int]:
    metin = _oku(os.path.join(klasor, "plan.md"))
    return set(_p_bloklari(metin)) if metin else set()


def plan_eksikleri(klasor: str) -> list[str]:
    """Boş liste = plan tamam (mevcut durum ayrıca denetlenir)."""
    metin = _oku(os.path.join(klasor, "plan.md"))
    if metin is None:
        return ["plan.md yok (`orkestra is belge <id> plan`)"]
    eksik = []
    md = mevcut_durum_yolu(klasor)
    if md is not None:
        bas = "\n".join(metin.splitlines()[:BAGLANTI_PENCERE])
        if f"]({os.path.basename(md)})" not in bas:
            eksik.append(f"plan.md ilk {BAGLANTI_PENCERE} satırında `[{os.path.basename(md)}]({os.path.basename(md)})` bağlantısı yok")
    bloklar = _p_bloklari(metin)
    if not bloklar:
        eksik.append("plan.md'de `P<n>` maddesi yok (örn. `### P1 Başlık`)")
    for n, blok in sorted(bloklar.items()):
        dayanaklar = [int(k) for k in _DAYANAK.findall(blok)]
        if not dayanaklar:
            eksik.append(f"P{n}: `MD §<k>` dayanağı yok (mevcut durum bölümü)")
        elif not any(1 <= k <= (GAP_BOLUMU if gapli_mi(klasor) else BOLUM_SAYISI) for k in dayanaklar):
            eksik.append(f"P{n}: dayanak MD §{dayanaklar[0]} geçersiz (§1-§{GAP_BOLUMU if gapli_mi(klasor) else BOLUM_SAYISI})")
    if kaliteli_mi(klasor):
        e = ozet_eksigi(metin, "plan")
        if e:
            eksik.append(e)
        for n, blok in sorted(bloklar.items()):
            for alan in ("Kabul", "Geri alma"):
                if not alan_dolu(blok, alan):
                    eksik.append(f"P{n}: `**{alan}:**` alanı yok ya da boş (P-018)")
    return eksik + mevcut_varlik_eksikleri(klasor) + gap_kapsama_eksikleri(klasor)


def adim(klasor: str) -> tuple[str, list[str]]:
    """(şu anki adım, o adımın eksikleri): 'mevcut_durum' | 'plan' | 'todo' (todo = ön koşullar tamam)."""
    e = mevcut_durum_eksikleri(klasor)
    if e:
        return "mevcut_durum", e
    e = plan_eksikleri(klasor)
    if e:
        return "plan", e
    return "todo", []


def plan_onkosulu(klasor: str) -> list[str]:
    """plan.md yazımı için ön koşul: mevcut durum tamam."""
    return mevcut_durum_eksikleri(klasor)


def todo_onkosulu(klasor: str) -> list[str]:
    """todo.md yazımı için ön koşul: mevcut durum ve plan tamam."""
    return mevcut_durum_eksikleri(klasor) or plan_eksikleri(klasor)


def todo_satir_ihlalleri(metin: str, planli: set[int], kanit: bool = False) -> list[str]:
    """Metindeki her onay kutusu satırı `P<n>` ile başlamalı ve P<n> planda olmalı."""
    ihlal = []
    for s in str(metin).splitlines():
        m = _TODO_SATIR.match(s)
        if not m or not m.group(1).strip():
            continue
        p = _TODO_P.match(m.group(1).strip())
        kisa = m.group(1).strip()[:60]
        if kanit and re.match(r"^\s*[-*]\s*\[[xX]\]", s) and len(s.partition(" — ")[2].strip()) < KANIT_MIN:
            ihlal.append(f"`{kisa}`: bitti satırı kanıt notu taşımalı (` — <tarih>: <komut | dosya:satır>`; P-018)")
        if not p:
            ihlal.append(f"`{kisa}`: satır `P<n>:` ile başlamalı (plan maddesi)")
        elif int(p.group(1)) not in planli:
            ihlal.append(f"`{kisa}`: P{p.group(1)} plan.md'de yok; önce planı güncelle")
    return ihlal


def mesaj(neden: list[str], hedef: str) -> str:
    """Kullanıcıya/ajana tek paragraf: hangi dosya, neden yazılamıyor, ne yapılacak."""
    return (f"{hedef} yazılamaz: sıra mevcut durum → plan → todo (P-005). Eksik: " + "; ".join(neden[:6])
            + (f" (+{len(neden) - 6} eksik daha)" if len(neden) > 6 else "")
            + ". Önceki adımı tamamla, sonra yaz (kapatma: ORKESTRA_SIRA_KAPISI=0).")
