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
import sys

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


_VARLIK_NOT = re.compile(r"\s*(?:;|\(|\s—\s)")
VARLIK_BICIM = "`id1, id2 (not)` ya da `yok — <aranan>`"


def varlik_kimlikleri(deger: str) -> list[str]:
    """Kimlik biçimli `Mevcut varlık` değerinden kayıt kimlikleri: ilk `;`, `(` ya da ` — ` öncesi virgüllü liste; sonrası serbest not."""
    bas = _VARLIK_NOT.split(deger, maxsplit=1)[0]
    return [x.strip(" `") for x in bas.split(",") if x.strip(" `")]


def mevcut_varlik_eksikleri(klasor: str, metin: str | None = None, bos_say: bool = True) -> list[str]:
    """ADR-0005: haritalı işte her P maddesi `**Mevcut varlık:**` taşır: harita kayıt kimlikleri (sonrasında serbest not)
    ya da `yok — <aranan>`. `metin`: plan.md yerine denetlenecek metin (yazım anı, ADR-0072); `bos_say=False`: boş alan
    taslak sayılır, yalnız dolu ama geçersiz alan eksik olur."""
    if not haritali_mi(klasor):
        return []
    import harita
    if metin is None:
        metin = _plan_oku(klasor) or ""
    sd = harita.sd_bul(klasor)
    kimlikler = harita.kayit_kimlikleri(sd) if sd else None
    eksik = []
    for n, blok in sorted(_p_bloklari(metin).items()):
        m = _MEVCUT_VARLIK.search(blok)
        deger = (m.group(1) if m else "").strip()
        if not deger:
            if bos_say:
                eksik.append(f"P{n}: `**Mevcut varlık:**` alanı yok ya da boş (`orkestra harita oku` kayıt kimliği ya da `yok — <aranan>`)")
        elif re.match(r"^yok\b", deger, re.I):
            gerekce = re.sub(r"^yok\s*[—:\-]*\s*", "", deger, flags=re.I)
            if len(gerekce) < VARLIK_GEREKCE_MIN:
                eksik.append(f"P{n}: `yok` için aranan şey yazılmalı (`yok — <aranan>`)")
        elif kimlikler is None:
            eksik.append(f"P{n}: sistem haritası yok; önce `orkestra harita oku` çalıştır")
        else:
            for kid in varlik_kimlikleri(deger):
                if kid not in kimlikler:
                    eksik.append(f"P{n}: `{kid}` haritada yok (`orkestra harita oku` ile kimliği doğrula; alan biçimi {VARLIK_BICIM})")
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
    metin = _plan_oku(klasor)
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


def bic_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_BIC_KAPISI") != "0"


def bic_kapsaminda_mi(klasor: str) -> bool:
    """P-030: iş sıralı ve is.json `kalite: true` taşıyor (P-018 ile aynı kapsam; bayraksız eski işler muaf)."""
    if not bic_kapisi_acik() or not sirali_mi(klasor):
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f).get("kalite") is True
    except (OSError, ValueError):
        return False


def _alternatif_satirlari(blok: str) -> list[str]:
    """`**Alternatifler:**` alanındaki madde satırları (`- ...`)."""
    m = re.search(r"\*\*Alternatifler:\*\*(.*?)(?=^\*\*[^\n*]+:\*\*|\Z)", _YORUM.sub("", blok), re.S | re.M)
    return [s.strip() for s in m.group(1).splitlines() if re.match(r"^\s*[-*]\s+\S", s)] if m else []


BIC_DENETIM_BASLIK = re.compile(r"^##[ \t]+Best in class denetimi[ \t]*$(.*?)(?=^##[ \t]|\Z)", re.M | re.S)
BIC_SORULAR = ("Kök neden", "Alternatifler", "Kapsam özü", "Ölçüm")
# P-032: beşinci soru yalnız plan `**LLM çıktısı:** kullanıcıya gider` beyanı taşıyorsa zorunludur (geriye dönük uyarı yok).
BIC_KOSULLU_SORU = "Yanıt kısıtı"
_LLM_BEYAN = re.compile(r"\*\*LLM çıktısı:\*\*[ \t]*(.*)")
_LLM_GEREKCE_ASGARI = (3, 15)  # en az sözcük, en az karakter


def denetci_kayitli_mi(klasor: str, ajan_kimligi: str) -> bool:
    """SubagentStop hook'unun yazdığı `zaman.jsonl` `tur: alt` kaydında bu kimlikle bir denetçi ajan var mı.
    Plan yazarı kimliği uyduramaz; yazarın ajanı denetçi olamaz (denetçi türü hook kaydından gelir)."""
    import ork_lib as L
    sd = L.durum_dizini(klasor)
    if not sd:
        return False
    try:
        with open(os.path.join(sd, "zaman.jsonl"), encoding="utf-8") as f:
            for satir in f:
                if ajan_kimligi not in satir:
                    continue
                try:
                    o = json.loads(satir)
                except ValueError:
                    continue
                if o.get("tur") == "alt" and str(o.get("agent_id", "")).startswith(ajan_kimligi) and "denetci" in str(o.get("ajan", "")):
                    return True
    except OSError:
        return False
    return False


def _kok_adaylari(klasor: str) -> list[str]:
    """Doğrulama yolunun çözüleceği kökler: `.claude` taşıyan proje kökü (varsa) ve iş klasörü."""
    kokler = []
    d = os.path.abspath(klasor)
    while True:
        if os.path.isdir(os.path.join(d, ".claude")):
            kokler.append(d)
            break
        ust = os.path.dirname(d)
        if ust == d:
            break
        d = ust
    kokler.append(os.path.abspath(klasor))
    return kokler


def llm_beyan_eksikleri(klasor: str, metin: str) -> tuple[list[str], bool]:
    """P-032: plandaki `**LLM çıktısı:**` beyanını denetler. Dönüş: (eksikler, kullanıcıya_gider).

    `yok — <neden>` (gerekçe asgari uzunlukta) ya da `kullanıcıya gider — Doğrulama: <yol>[::<test adı>]`;
    yol proje kökünde ya da iş klasöründe dosya olarak bulunur, test adı dosyada geçer."""
    m = _LLM_BEYAN.search(_YORUM.sub("", metin))
    if m is None:
        return ["plan.md: `**LLM çıktısı:**` beyanı yok: `yok — <neden>` ya da `kullanıcıya gider — Doğrulama: <yol>` (P-032)"], False
    v = m.group(1).strip().strip("`").strip()
    dusuk = v.lower()
    if dusuk.startswith("yok"):
        gerekce = re.sub(r"^[\s—–:\-]+", "", v[3:]).strip()
        if len(gerekce.split()) < _LLM_GEREKCE_ASGARI[0] or len(gerekce) < _LLM_GEREKCE_ASGARI[1]:
            return [f"plan.md: `**LLM çıktısı:** yok` gerekçesi en az {_LLM_GEREKCE_ASGARI[0]} sözcük ve {_LLM_GEREKCE_ASGARI[1]} karakter olmalı (P-032)"], False
        return [], False
    if dusuk.startswith("kullanıcıya gider"):
        d = re.search(r"Doğrulama:\s*(\S+)", v)
        if d is None:
            return ["plan.md: `**LLM çıktısı:** kullanıcıya gider` doğrulama yolu vermiyor: `Doğrulama: <kod veya test yolu>` (P-032)"], True
        yol, _, test = d.group(1).strip("`.,;").partition("::")
        dosya = next((a for a in ([yol] if os.path.isabs(yol) else [os.path.join(k, yol) for k in _kok_adaylari(klasor)]) if os.path.isfile(a)), None)
        if dosya is None:
            return [f"plan.md: doğrulama yolu dosya olarak bulunamadı: `{yol}` (P-032)"], True
        if test and test not in (_oku(dosya) or ""):
            return [f"plan.md: doğrulama dosyasında `{test}` geçmiyor: `{yol}` (P-032)"], True
        return [], True
    return ["plan.md: `**LLM çıktısı:**` biçimi `yok — <neden>` ya da `kullanıcıya gider — Doğrulama: <yol>` olmalı (P-032)"], False


def bic_eksikleri(klasor: str) -> list[str]:
    """P-030: her P maddesi `**Alternatifler:**` taşır (en az iki madde, biri `Elenen`); plan.md ayrı denetçinin
    doldurduğu `## Best in class denetimi` bloğunu taşır (dört soru ✔/✘ ve `**Denetçi:**`). Kapsam dışı iş: boş liste."""
    if not bic_kapsaminda_mi(klasor):
        return []
    metin = _plan_oku(klasor)
    if metin is None:
        return []
    eksik = []
    for n, blok in sorted(_p_bloklari(metin).items()):
        sat = _alternatif_satirlari(blok)
        if len(sat) < 2 or not any(re.match(r"^[-*]\s+Elenen\b", s) for s in sat):
            eksik.append(f"P{n}: `**Alternatifler:**` en az iki madde ve biri `Elenen: ... Neden elendi: ...` olmalı (P-030)")
    m = BIC_DENETIM_BASLIK.search(_YORUM.sub("", metin))
    if m is None:
        eksik.append("plan.md: `## Best in class denetimi` bloğu yok (P-030)")
    else:
        govde = m.group(1)
        for soru in BIC_SORULAR:
            if not re.search(r"\*\*" + re.escape(soru) + r":\*\*\s*[✔✘]", govde):
                bekl = f": {BEKLENIYOR}" if _satir_bekliyor(govde, soru) else ""
                eksik.append(f"best in class denetimi: `**{soru}:**` satırı `✔`/`✘` ile başlamıyor{bekl} (ayrı denetçi doldurur; P-030)")
        d = re.search(r"\*\*Denetçi:\*\*[ \t]*(.*)", govde)
        kimlik = re.search(r"\b([0-9a-f]{8,})\b", d.group(1)) if d else None
        if not kimlik and d is not None and _BEKLIYOR.match(d.group(1)):
            eksik.append(f"best in class denetimi: `**Denetçi:**` satırı denetçi ajan kimliği taşımıyor: {BEKLENIYOR} (`orkestra:denetci <agent_id>`; P-030)")
        elif not kimlik:
            eksik.append("best in class denetimi: `**Denetçi:**` satırı denetçi ajan kimliği taşımıyor (`orkestra:denetci <agent_id>`; P-030)")
        elif not denetci_kayitli_mi(klasor, kimlik.group(1)):
            eksik.append(f"best in class denetimi: `{kimlik.group(1)}` kimliğiyle bir denetçi alt ajan kaydı bulunamadı (zaman.jsonl; P-030)")
    llm_eksik, gider = llm_beyan_eksikleri(klasor, metin)
    eksik += llm_eksik
    if gider and m is not None and not re.search(r"\*\*" + BIC_KOSULLU_SORU + r":\*\*\s*[✔✘]", m.group(1)):
        bekl = f": {BEKLENIYOR}" if _satir_bekliyor(m.group(1), BIC_KOSULLU_SORU) else ""
        eksik.append(f"best in class denetimi: `**{BIC_KOSULLU_SORU}:**` satırı `✔`/`✘` ile başlamıyor{bekl} (LLM çıktısı kullanıcıya gidiyor; P-032)")
    return eksik


# I-271: ayrı denetçinin dolduracağı satır henüz boşsa (`bekliyor` ya da boş değer) bu bir içerik hatası değil, sıranın
# bir sonraki adımıdır: kapı geçmez (bağımsız denetim özü korunur) ama `kapi_ret` yerine `kapi_bekleniyor` kaydı düşer.
BEKLENIYOR = "denetçi bekleniyor"
_BEKLIYOR = re.compile(r"^[ \t]*(?:bekliyor\b.*)?$", re.I)


def _satir_bekliyor(govde: str, alan: str) -> bool:
    """Denetim bloğunda `**<alan>:**` satırı var ve değeri boş ya da `bekliyor` ile başlıyor."""
    s = re.search(r"\*\*" + re.escape(alan) + r":\*\*[ \t]*([^\n]*)", govde)
    return s is not None and bool(_BEKLIYOR.match(s.group(1)))


def bekleyen_mi(eksik: str) -> bool:
    return BEKLENIYOR in eksik


def kapi_durumu(eksik: list[str]) -> str:
    """Kapı sonucu: `tamam` (eksik yok), `bekleniyor` (eksiklerin hepsi denetçinin henüz doldurmadığı satırlar), `ret`."""
    if not eksik:
        return "tamam"
    return "bekleniyor" if all(bekleyen_mi(e) for e in eksik) else "ret"


def bekleniyor_kaydet(klasor: str, kapi: str, neden: str) -> bool:
    """`kapi_bekleniyor` olayı (ret sayılmaz); aynı (iş, kapı, neden) bir kez yazılır. Kapıyı hiçbir koşulda bozmaz."""
    try:
        import kapi_mod as KM
        import ork_lib as L
        sd = L.durum_dizini(klasor)
        if not sd:
            return False
        yol = os.path.join(sd, "gunluk.jsonl")
        is_ad = os.path.basename(os.path.normpath(klasor))
        if KM._zaten_kayitli(yol, is_ad, kapi, neden[:300], "kapi_bekleniyor"):
            return False
        L.jsonl_ekle(yol, {"zaman": L.simdi(), "tur": "kapi_bekleniyor", "kapi": kapi, "is": is_ad, "neden": neden[:300]})
        return True
    except Exception:
        return False


def _bekleyenli_ret(klasor: str, kapi: str, eksik: list[str], ret: bool) -> list[str]:
    """İçerik eksikleri eskisi gibi işlenir (ret=True: `KM.ret_ver` → ihlalde `kapi_ret`; ret=False: `KM.ihlal_ver`).
    Denetçi bekleyen satırlar `kapi_bekleniyor` olarak kaydedilir ve ihlal modunda yine döndürülür (plan geçmez)."""
    import kapi_mod as KM
    icerik = [e for e in eksik if not bekleyen_mi(e)]
    bekleyen = [e for e in eksik if bekleyen_mi(e)]
    sonuc = (KM.ret_ver if ret else KM.ihlal_ver)(klasor, kapi, icerik) if icerik else []
    if bekleyen:
        bekleniyor_kaydet(klasor, kapi, "; ".join(bekleyen))
        if KM.mod(kapi, klasor) == "ihlal":
            sonuc = sonuc + bekleyen
    return sonuc


def bic_durumu(klasor: str) -> str:
    """Best in class kapısının sonucu: `tamam` | `bekleniyor` | `ret`."""
    return kapi_durumu(bic_eksikleri(klasor))


def bic_engeli(klasor: str) -> list[str]:
    """Sessiz kapı: yalnız `ihlal` modunda eksikleri döndürür (plan_eksikleri sık çağrılır)."""
    if not bic_kapsaminda_mi(klasor):
        return []
    import kapi_mod as KM
    return bic_eksikleri(klasor) if KM.mod("best_in_class", klasor) == "ihlal" else []


def _bic_olaylari(klasor: str) -> None:
    """ADR-0068 ölçümü: planın ilk görülüşü (`bic_ilk`) ve ayrı denetçinin ilk dolu bloğu (`bic_denetim_ilk`) iş başına
    bir kez `gunluk.jsonl`'a düşer; kol, planı yazan ilk oturumun kimliğinden türer. Hata kapıyı bozmaz."""
    try:
        import ork_lib as L
        import yontem_enjeksiyonu as Y
        sd = L.durum_dizini(klasor)
        metin = _oku(os.path.join(klasor, "plan.md"))
        if not sd or metin is None or not _p_bloklari(metin):
            return
        yol = os.path.join(sd, "gunluk.jsonl")
        ad = os.path.basename(os.path.normpath(klasor))
        try:
            with open(yol, encoding="utf-8") as f:
                var = {t for satir in f if ad in satir for t in ("bic_ilk", "bic_denetim_ilk") if f'"{t}"' in satir}
        except OSError:
            var = set()
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            oturumlar = json.load(f).get("oturumlar") or []
        oturum = oturumlar[0].get("oturum") if oturumlar else None
        taban = {"zaman": L.simdi(), "oturum": oturum, "is": ad, "kol": Y.kol(oturum, sd)}
        if "bic_ilk" not in var:
            L.jsonl_ekle(yol, {**taban, "tur": "bic_ilk"})
        m = BIC_DENETIM_BASLIK.search(_YORUM.sub("", metin))
        if "bic_denetim_ilk" in var or m is None:
            return
        kararlar = {q: (re.search(r"\*\*" + re.escape(q) + r":\*\*\s*([✔✘])", m.group(1)) or [None, None])[1] for q in BIC_SORULAR}
        d = re.search(r"\*\*Denetçi:\*\*[ \t]*(.*)", m.group(1))
        kimlik = re.search(r"\b([0-9a-f]{8,})\b", d.group(1)) if d else None
        if all(kararlar.values()) and kimlik and denetci_kayitli_mi(klasor, kimlik.group(1)):
            L.jsonl_ekle(yol, {**taban, "tur": "bic_denetim_ilk", "kararlar": kararlar,
                               "hepsi_ok": all(v == "✔" for v in kararlar.values())})
    except Exception:
        pass


def bic_uyari(klasor: str) -> list[str]:
    """Sesli kapı (todo yazımı, `is sira`): gölge modunda uyarır ve `kapi_golge` kaydı düşer, ihlal modunda eksikleri döndürür."""
    if not bic_kapsaminda_mi(klasor):
        return []
    _bic_olaylari(klasor)
    return _bekleyenli_ret(klasor, "best_in_class", bic_eksikleri(klasor), ret=False)


# K-006 / ADR-0069: plan maddesinde `**Üretim noktası:**` alanı (sorunun doğduğu yer ve orada önleme).
URETIM_ALANI = "Üretim noktası"
_URETIM_ASGARI = 15  # önleme / neden / gerekçe metninin en az karakteri
_URETIM_TUR_KELIME = ("kural", "şablon", "skill", "betik", "kart", "istem", "hook", "ayar", "standart")
_URETIM_DUZELTME = re.compile(r"^Düzeltme:\s*(.+?)\s+[—–]\s+(.+)$", re.S)
_URETIM_KONTROL = re.compile(r"^Kontrol:\s*(.+?)\s+[—–]\s+(.+?);\s*Kaynakta çözülmedi çünkü:\s*(.+)$", re.S)
_URETIM_YENI = re.compile(r"^Yeni yetenek\s+[—–]\s+(.+)$", re.S)
_URETIM_YASAK = re.compile(r"(?<![\w/.])(düzelt\w*|hata\w*|kusur\w*|tekrar\w*|ret|reddi\w*)(?![\w/.])", re.I)
URETIM_JACCARD = 0.8


def uretim_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_URETIM_KAPISI") != "0"


def uretim_kapsaminda_mi(klasor: str) -> bool:
    """ADR-0069: iş sıralı ve is.json `uretim: true` taşıyor (bayraksız eski işler muaf)."""
    if not uretim_kapisi_acik() or not sirali_mi(klasor):
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f).get("uretim") is True
    except (OSError, ValueError):
        return False


def _alan_degeri(blok: str, alan: str) -> str:
    """P bloğunda satır başındaki `**<alan>:**` değeri (aynı ve sonraki satırlar, boşluklar tek aralığa indirilmiş); yoksa ''.
    Satır içi anma (başka alanın metninde geçen `**<alan>:**`) alan sayılmaz."""
    m = re.search(r"^[ \t]*\*\*" + re.escape(alan) + r":\*\*(.*?)(?=^\*\*[^\n*]+:\*\*|\Z)", _YORUM.sub("", blok), re.S | re.M)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _uretim_yer_gecerli(yer: str) -> bool:
    """`<yer>` bir yol / dosya adı ya da bir tür kelimesi (kural, şablon, skill, betik, kart, istem, hook, ayar, standart) içerir."""
    dusuk = yer.replace("İ", "i").lower()
    return "/" in yer or re.search(r"\.(py|md|json)\b", dusuk) is not None or any(k in dusuk for k in _URETIM_TUR_KELIME)


def _uretim_kelimeler(metin: str) -> set[str]:
    return {k for k in re.findall(r"\w+", metin.replace("İ", "i").lower()) if len(k) > 1}


def uretim_alan_ayristir(deger: str) -> tuple[str | None, str, str, str | None]:
    """(tür, yer, gerekçe_metni, hata): tür 'duzeltme' | 'kontrol' | 'yeni' | None. `gerekçe_metni` kopya denetimi içindir
    (tür öneki ve yer çıkarılmış kalan metin); hata biçim ya da asgari uzunluk kusurunu söyler."""
    d = deger.strip()
    m = _URETIM_KONTROL.match(d)
    if m:
        yer, ne, neden = (g.strip(" `") for g in m.groups())
        if len(ne) < 8 or len(neden) < _URETIM_ASGARI:
            return "kontrol", yer, ne + " " + neden, f"`Kontrol:` ne en az 8, `Kaynakta çözülmedi çünkü:` en az {_URETIM_ASGARI} karakter olmalı"
        return "kontrol", yer, ne + " " + neden, None
    m = _URETIM_DUZELTME.match(d)
    if m:
        yer, onleme = m.group(1).strip(" `"), m.group(2).strip()
        if len(onleme) < _URETIM_ASGARI:
            return "duzeltme", yer, onleme, f"`Düzeltme:` önleme metni en az {_URETIM_ASGARI} karakter olmalı"
        return "duzeltme", yer, onleme, None
    m = _URETIM_YENI.match(d)
    if m:
        gerekce = m.group(1).strip()
        if len(gerekce) < _URETIM_ASGARI:
            return "yeni", "", gerekce, f"`Yeni yetenek` gerekçesi en az {_URETIM_ASGARI} karakter olmalı"
        return "yeni", "", gerekce, None
    return None, "", d, "biçim `Düzeltme: <yer> — <önleme>`, `Kontrol: <yer> — <ne>; Kaynakta çözülmedi çünkü: <neden>` ya da `Yeni yetenek — <gerekçe>` olmalı"


def uretim_eksikleri(klasor: str) -> list[str]:
    """ADR-0069: `uretim: true` taşıyan sıralı işte her P maddesi `**Üretim noktası:**` alanını üç türden birinde taşır;
    gerekçeler tekrarlanmaz; hata/ret/kusur/tekrar başlıklı maddede `Yeni yetenek` kullanılmaz; plan.md ayrı denetçinin
    `**Üretim noktası:** ✔` satırını (kayıtlı denetçi kimliğiyle) taşır. Kapsam dışı iş: boş liste."""
    if not uretim_kapsaminda_mi(klasor):
        return []
    metin = _plan_oku(klasor)
    if metin is None:
        return []
    eksik: list[str] = []
    turler: dict[int, str | None] = {}
    kelimeler: dict[int, set[str]] = {}
    for n, blok in sorted(_p_bloklari(metin).items()):
        deger = _alan_degeri(blok, URETIM_ALANI)
        if not deger:
            eksik.append(f"P{n}: `**{URETIM_ALANI}:**` alanı yok ya da boş (K-006; ADR-0069)")
            continue
        tur, yer, gerekce, hata = uretim_alan_ayristir(deger)
        turler[n] = tur
        if hata:
            eksik.append(f"P{n}: `**{URETIM_ALANI}:**` {hata} (ADR-0069)")
            continue
        if tur != "yeni" and not _uretim_yer_gecerli(yer):
            eksik.append(f"P{n}: `**{URETIM_ALANI}:**` yer bir yol/dosya adı ya da kural, şablon, skill, betik, kart, istem, hook, ayar, standart olmalı: `{yer}` (ADR-0069)")
        if tur == "yeni":
            baslik = re.sub(r"`[^`]*`", " ", blok.splitlines()[0] if blok else "")
            ne = re.sub(r"`[^`]*`", " ", _alan_degeri(blok, "Ne"))
            bulunan = _URETIM_YASAK.search(baslik) or _URETIM_YASAK.search(ne)
            if bulunan:
                eksik.append(f"P{n}: `Yeni yetenek` başlıkta ya da `Ne:` metninde `{bulunan.group(1)}` geçen maddede kullanılamaz; kusur düzeltiyorsa `Düzeltme:`/`Kontrol:` yaz (ADR-0069)")
        kw = _uretim_kelimeler(gerekce)
        for onceki, kw0 in sorted(kelimeler.items()):
            birlesim = kw | kw0
            if birlesim and (kw == kw0 or len(kw & kw0) / len(birlesim) >= URETIM_JACCARD):
                eksik.append(f"P{n}: `**{URETIM_ALANI}:**` gerekçesi P{onceki} ile aynı ya da çok benzer; her madde kendi yerini ve nedenini yazar (ADR-0069)")
                break
        kelimeler[n] = kw
    m = BIC_DENETIM_BASLIK.search(_YORUM.sub("", metin))
    if m is None:
        eksik.append("plan.md: `## Best in class denetimi` bloğu yok (ayrı denetçi `**Üretim noktası:**` satırını doldurur; ADR-0069)")
        return eksik
    govde = m.group(1)
    satir = re.search(r"\*\*" + URETIM_ALANI + r":\*\*[ \t]*([^\n]*)", govde)
    if satir is not None and _BEKLIYOR.match(satir.group(1)):
        eksik.append(f"best in class denetimi: `**{URETIM_ALANI}:**` satırı `✔` ile başlamıyor: {BEKLENIYOR} (ayrı denetçi doldurur; ADR-0069)")
    elif satir is None or not satir.group(1).lstrip().startswith("✔"):
        eksik.append(f"best in class denetimi: `**{URETIM_ALANI}:**` satırı `✔` ile başlamıyor (ayrı denetçi doldurur; ADR-0069)")
    elif turler and all(t == "yeni" for t in turler.values()) and "tümü yeni yetenek onaylandı" not in satir.group(1).lower():
        eksik.append(f"best in class denetimi: tüm maddeler `Yeni yetenek`; `**{URETIM_ALANI}:**` satırı `tümü yeni yetenek onaylandı` ifadesini taşımalı (ADR-0069)")
    d = re.search(r"\*\*Denetçi:\*\*[ \t]*(.*)", govde)
    kimlik = re.search(r"\b([0-9a-f]{8,})\b", d.group(1)) if d else None
    if not kimlik and d is not None and _BEKLIYOR.match(d.group(1)):
        eksik.append(f"best in class denetimi: `**Denetçi:**` satırı denetçi ajan kimliği taşımıyor: {BEKLENIYOR} (ADR-0069)")
    elif not kimlik:
        eksik.append("best in class denetimi: `**Denetçi:**` satırı denetçi ajan kimliği taşımıyor (ADR-0069)")
    elif not denetci_kayitli_mi(klasor, kimlik.group(1)):
        eksik.append(f"best in class denetimi: `{kimlik.group(1)}` kimliğiyle bir denetçi alt ajan kaydı bulunamadı (zaman.jsonl; ADR-0069)")
    return eksik


def uretim_engeli(klasor: str) -> list[str]:
    """`plan_eksikleri` bağlantısı: ihlal modunda eksikleri döndürür ve her reddi `kapi_ret` olarak kaydeder (gölgede `kapi_golge`)."""
    if not uretim_kapsaminda_mi(klasor):
        return []
    return _bekleyenli_ret(klasor, "uretim_noktasi", uretim_eksikleri(klasor), ret=True)


def uretim_durumu(klasor: str) -> str:
    """Üretim noktası kapısının sonucu: `tamam` | `bekleniyor` (yalnız ayrı denetçinin satırları boş) | `ret`."""
    return kapi_durumu(uretim_eksikleri(klasor))


# P-044 / ADR-0106: kullanıcıya görünen yerleşim, hizalama ya da konum değiştiren P maddesinin `**Kabul:**` alanı ölçüm taşır
# (gerçek tarayıcı, getBoundingClientRect, ekran görüntüsü, px); "yapıldı" ya da kod okuması kabul sayılmaz. Gölge kapı (P-028).
_GORUNUM_KONU = re.compile(r"yerleşim|hizala|konum|düğme|buton|\.css\b|görünüm|layout|flex|sağ kenar|alt satır", re.I)
_GORUNUM_OLCUM = re.compile(r"getBoundingClientRect|tarayıcı|ekran görüntüsü|screenshot|headless|ölçüm|ölçül|\bpx\b|piksel", re.I)


def gorunum_olcumu_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_GORUNUM_OLCUMU_KAPISI") != "0"


def gorunum_olcumu_kapsaminda_mi(klasor: str) -> bool:
    return gorunum_olcumu_kapisi_acik() and sirali_mi(klasor)


def _alan_metni(blok: str, alan: str) -> str:
    m = re.search(r"\*\*" + re.escape(alan) + r":\*\*(.*?)(?=^\*\*[^\n*]+:\*\*|\Z)", _YORUM.sub("", blok), re.S | re.M)
    return m.group(1).strip() if m else ""


def gorunum_olcumu_eksikleri(klasor: str) -> list[str]:
    metin = _plan_oku(klasor)
    if metin is None:
        return []
    eksik = []
    for n, blok in sorted(_p_bloklari(metin).items()):
        konu = " ".join(_alan_metni(blok, a) for a in ("Ne", "Dokunulan yer", "Kabul"))
        if _GORUNUM_KONU.search(konu) and not _GORUNUM_OLCUM.search(_alan_metni(blok, "Kabul")):
            eksik.append(f"P{n}: görünen yerleşim/konum değişikliği; `**Kabul:**` gerçek tarayıcı ölçümü içermeli (getBoundingClientRect, ekran görüntüsü; P-044)")
    return eksik


def gorunum_olcumu_uyari(klasor: str) -> list[str]:
    """Sesli kapı: gölge modunda uyarır ve `kapi_golge` kaydı düşer; ihlal modunda eksikleri döndürür."""
    if not gorunum_olcumu_kapsaminda_mi(klasor):
        return []
    import kapi_mod as KM
    return KM.ihlal_ver(klasor, "gorunum_olcumu", gorunum_olcumu_eksikleri(klasor))


# ADR-0080: plan paralellik kapısı (`**Önce:**` gerekçeli bağımlılık, `**Yazma alanı:**`, dalga kesişimi, tam sıralı gerekçe).
def paralellik_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_PARALELLIK_KAPISI") != "0"


def paralellik_kapsaminda_mi(klasor: str) -> bool:
    """ADR-0080: iş sıralı ve is.json `paralel: true` taşıyor (bayraksız eski işler muaf)."""
    if not paralellik_kapisi_acik() or not sirali_mi(klasor):
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f).get("paralel") is True
    except (OSError, ValueError):
        return False


def paralellik_eksikleri(klasor: str) -> list[str]:
    """ADR-0080: `paralel: true` taşıyan sıralı işte plan.md paralellik analizinin eksikleri: alan yok/biçimsiz, geçersiz
    başvuru (ileri başvuru izinli, döngü yasak), sahte `Çakışma:`, aynı dalgada kesişen yazma alanı, gerekçesiz tam sıralı
    plan. Kapsam dışı iş ya da plan.md yok: boş liste."""
    if not paralellik_kapsaminda_mi(klasor):
        return []
    metin = _plan_oku(klasor)
    if metin is None:
        return []
    import paralellik as PAR
    return [f"{e} (ADR-0080)" for e in PAR.analiz(metin, ileri_yasak=False)["eksikler"]]


def paralellik_engeli(klasor: str) -> list[str]:
    """`plan_eksikleri` bağlantısı: ihlal modunda eksikleri döndürür ve her reddi `kapi_ret` olarak kaydeder (gölgede `kapi_golge`)."""
    if not paralellik_kapsaminda_mi(klasor):
        return []
    import kapi_mod as KM
    return KM.ret_ver(klasor, "paralellik", paralellik_eksikleri(klasor))


# ADR-0112: plan etki kapısı. İsteğin konu kartlarına eşlenen yüzeyleri plan maddelerinin `**Etki:**` alanında anılmalı
# (`orkestra harita istek`); kapı `ayarlar/harita_etki.json` modunda çalışır (başlangıç: golge, P-028).
def etki_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_ETKI_KAPISI") != "0"


def etki_kapsaminda_mi(klasor: str) -> bool:
    """ADR-0112: iş sıralı ve is.json `etki: true` taşıyor (bayraksız eski işler muaf)."""
    if not etki_kapisi_acik() or not sirali_mi(klasor):
        return False
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f).get("etki") is True
    except (OSError, ValueError):
        return False


def _etki_istegi(klasor: str) -> str:
    """İsteğin metni: iş başlığı ve sözleşmenin `## Problem` bölümü."""
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            parca = [str(json.load(f).get("baslik") or "")]
    except (OSError, ValueError):
        parca = []
    for ad in sorted(os.listdir(klasor)) if os.path.isdir(klasor) else []:
        if _SOZLESME_AD.match(ad):
            m = re.search(r"^##\s+Problem\s*$(.*?)(?=^##\s|\Z)", _oku(os.path.join(klasor, ad)) or "", re.S | re.M)
            if m:
                parca.append(m.group(1))
    return "\n".join(parca)


def etki_sonucu(klasor: str) -> dict | None:
    """İsteğin etki kümesi (`harita_istek.etki`); graf dizini yoksa None."""
    import harita
    import harita_istek as HI
    sd = harita.sd_bul(klasor)
    graf = os.path.join(harita.klasor_yolu(sd), HI.GRAF_DIZINI) if sd else ""
    if not graf or not os.path.isdir(graf):
        return None
    return HI.etki(_etki_istegi(klasor), graf)


def etki_bolumu(klasor: str) -> str:
    """Plan iskeletine eklenen `## Etki kümesi` bölümü (`orkestra harita istek` çıktısı); kapsam dışı ya da eşleşme yoksa ''."""
    if not etki_kapsaminda_mi(klasor):
        return ""
    s = etki_sonucu(klasor)
    if not s or not s["eslesti"]:
        return ""
    import harita_istek as HI
    return "\n## Etki kümesi\n\n<!-- orkestra harita istek çıktısı: her yüzey en az bir P maddesinin `**Etki:**` alanında anılır -->\n\n" + HI.metin(s) + "\n"


def etki_eksikleri(klasor: str, metin: str | None = None) -> list[str]:
    """Etki kümesinde olup hiçbir P maddesinin `**Etki:**` alanında anılmayan yüzeyler."""
    if not etki_kapsaminda_mi(klasor):
        return []
    metin = metin if metin is not None else _plan_oku(klasor)
    s = etki_sonucu(klasor)
    if metin is None or not s or not s["eslesti"]:
        return []
    alan = " ".join(_alan_degeri(b, "Etki") for b in _p_bloklari(metin).values()).lower()
    return [f"etki kümesindeki yüzey plan maddelerinin `**Etki:**` alanında anılmıyor: {y['ad']}" + (f" ({y['yol']})" if y["yol"] else "")
            + " (ADR-0112)" for y in s["yuzeyler"]
            if y["ad"].lower() not in alan and not (y["yol"] and y["yol"].lower() in alan)]


def _biten_yazma_alanlari(klasor: str) -> list[str]:
    """todo.md'de biten P maddelerinin plan `**Yazma alanı:**` yolları (virgüllü liste)."""
    todo = _oku(os.path.join(klasor, "todo.md")) or ""
    biten = {int(n) for n in re.findall(r"^\s*[-*]\s*\[[xX]\]\s*P(\d+)", todo, re.M)}
    yollar = []
    for n, blok in _p_bloklari(_plan_oku(klasor) or "").items():
        if n in biten:
            yollar += [x.strip(" `") for x in _alan_degeri(blok, "Yazma alanı").split(",") if x.strip(" `")]
    return yollar


def degisen_dosyalar(klasor: str) -> set[str]:
    """İş açıldığından beri proje deposunda değişen dosyalar (git log + çalışma ağacı); git yoksa boş küme."""
    import subprocess
    import harita
    sd = harita.sd_bul(klasor)
    if not sd:
        return set()
    kok = os.path.dirname(os.path.dirname(sd))
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            baslangic = json.load(f).get("olusturma") or ""
        cmd = ["git", "-c", "safe.directory=*"]
        log = subprocess.run(cmd + ["log", f"--since={baslangic}", "--name-only", "--pretty=format:"], cwd=kok,
                             capture_output=True, text=True, encoding="utf-8", timeout=60).stdout
        durum = subprocess.run(cmd + ["status", "--porcelain"], cwd=kok, capture_output=True, text=True,
                               encoding="utf-8", timeout=60).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return set()
    return {s.strip() for s in log.splitlines() if s.strip()} | {s[3:].strip().strip('"') for s in durum.splitlines() if len(s) > 3}


def etki_kapanis_eksikleri(klasor: str, degisen: set[str] | None = None) -> list[str]:
    """Kapanış son ağı: etki kümesindeki yollu yüzeyin hiçbir değişen dosyası (iş açıldığından beri git) ve hiçbir biten
    P maddesinin yazma alanı yoksa işlenmemiş sayılır. Yolsuz yüzey doğrulanamaz, atlanır."""
    if not etki_kapsaminda_mi(klasor):
        return []
    s = etki_sonucu(klasor)
    if not s or not s["eslesti"]:
        return []
    import harita_istek as HI
    var = (degisen if degisen is not None else degisen_dosyalar(klasor)) | set(_biten_yazma_alanlari(klasor))
    return [f"etki kümesindeki yüzey işlenmedi: {y['ad']} ({y['yol']}) (ADR-0112)" for y in s["yuzeyler"]
            if y["yol"] and not any(HI._uyar(y["yol"], d) or HI._uyar(d, y["yol"]) for d in var)]


def etki_kapanis_kaydi(klasor: str) -> list[str]:
    """Kapanış bağlantısı: gölgede `kapi_golge` kaydı düşer; kapanışı hiçbir modda engellemez (ADR-0112, P-028)."""
    if not etki_kapsaminda_mi(klasor):
        return []
    import kapi_mod as KM
    return KM.ihlal_ver(klasor, "harita_etki", etki_kapanis_eksikleri(klasor))


def etki_engeli(klasor: str) -> list[str]:
    """`plan_eksikleri` bağlantısı: gölgede `kapi_golge` kaydı düşer ve boş döner; ihlal modunda eksikleri döndürür."""
    if not etki_kapsaminda_mi(klasor):
        return []
    import kapi_mod as KM
    return KM.ret_ver(klasor, "harita_etki", etki_eksikleri(klasor))


# ADR-0086: Jira görev bağımlılığı girdi kapısı (`**Jira:**` taşıyan plan, işin klasöründeki `jira_bagimlilik.json` ile sınanır).
_HAZIRLANMA = re.compile(r"\*\*Hazırlanma saati:\*\*\s*(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})")


def jira_bagimlilik_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_JIRA_BAGIMLILIK_KAPISI") != "0"


def _jira_maddeleri(klasor: str) -> dict[int, dict]:
    metin = _plan_oku(klasor)
    if metin is None:
        return {}
    import paralellik as PAR
    return PAR.maddeler(metin)


def jira_bagimlilik_kapsaminda_mi(klasor: str) -> bool:
    """ADR-0086: sıralı iş ve plan.md'de en az bir `**Jira:**` alanı var (alanı olmayan eski planlar muaf)."""
    if not jira_bagimlilik_kapisi_acik() or not sirali_mi(klasor):
        return False
    return any(m.get("jira") for m in _jira_maddeleri(klasor).values())


def jira_bagimlilik_eksikleri(klasor: str) -> list[str]:
    """ADR-0086 (K4a/K4b + açık öncül sınaması): `**Jira:**` alanı var ama `jira_bagimlilik.json` yok ya da bozuk; plandaki
    bir anahtarın kendi kaydı dosyada yok (bağlantısı okunmamış görev 'bağımsız' sayılamaz); açık öncül plan kümesinde
    ya da `**Önce:**` içinde yok; Jira döngüsü. Eski okuma saati (K4c) eksik sayılmaz, `jira_bagimlilik_engeli` uyarır."""
    md = _jira_maddeleri(klasor)
    anahtarlar = sorted({m["jira"] for m in md.values() if m.get("jira")})
    if not anahtarlar:
        return []
    import jira_bagimlilik as JB
    import paralellik as PAR
    try:
        g = JB.yukle(klasor)
    except ValueError as e:
        return [f"{e} (ADR-0086)"]
    if g is None:
        return [f"plan `**Jira:**` alanı taşıyor ama {JB.DOSYA} yok: Jira bağlantıları okunmadan öncül sınanamaz; "
                f"Atlassian bağlayıcısındaki tek JQL yanıtı bu dosyaya yazılır (`orkestra is dalga <iş> --jira`) (ADR-0086)"]
    okunmayan = [k for k in anahtarlar if not JB.okundu_mu(g, k)]
    if okunmayan:
        return [f"{', '.join(okunmayan)}: {JB.DOSYA} içinde kendi kaydı yok; bağlantıları okunmamış görev bağımsız sayılamaz, "
                f"JQL'e ekleyip dosyayı yenile (ADR-0086)"]
    return [f"{e} (ADR-0086)" for e in PAR.jira_eksikleri(md, g)]


def _jira_referans_saati(klasor: str):
    """Plan `**Hazırlanma saati:**` (GG.AA.YYYY SS:DD); okunamazsa şimdi."""
    from datetime import datetime
    m = _HAZIRLANMA.search(_plan_oku(klasor) or "")
    if m:
        g, a, y, s, d = (int(x) for x in m.groups())
        try:
            return datetime(y, a, g, s, d)
        except ValueError:
            pass
    return datetime.now()


def _jira_eski_uyari(klasor: str) -> None:
    """K4c: okuma saati plan hazırlanma saatinden 24 saatten eskiyse iki modda da yalnız uyarır (`kapi_golge` olarak kaydeder)."""
    import jira_bagimlilik as JB
    import kapi_mod as KM
    try:
        g = JB.yukle(klasor)
    except ValueError:
        return
    if g is None or not JB.eski_mi(g, _jira_referans_saati(klasor)):
        return
    neden = f"{JB.DOSYA} okuma saati ({g.get('okuma_saati') or 'yok'}) plan hazırlanma saatinden {JB.ESKI_SAAT} saatten eski; bağlantıları yeniden oku (ADR-0086)"
    if KM.kaydet(klasor, "jira_bagimlilik", neden):
        print(f"orkestra (uyarı, jira_bagimlilik): {neden}", file=sys.stderr)


def jira_bagimlilik_engeli(klasor: str) -> list[str]:
    """`plan_eksikleri` bağlantısı: ihlal modunda eksikleri döndürür ve her reddi `kapi_ret` olarak kaydeder (gölgede `kapi_golge`)."""
    if not jira_bagimlilik_kapsaminda_mi(klasor):
        return []
    import kapi_mod as KM
    _jira_eski_uyari(klasor)
    return KM.ret_ver(klasor, "jira_bagimlilik", jira_bagimlilik_eksikleri(klasor))


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
    deger = m.group(1).strip() if m else ""
    # `plan alan` iskeletinin `<doldur>` yer tutucusu (değerin tamamı ya da başı) boş sayılır; metin içindeki alıntı sayılmaz.
    return bool(deger) and not _YER_TUTUCU.match(deger)


_YER_TUTUCU = re.compile(r"^`?<doldur\b[^>]*>", re.I)


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


_PLAN_ESI: dict[str, str] = {}  # I-224: yazım anında denetlenecek plan metni (klasör → yazılacak metin); diskteki plan.md yerine


def _anahtar(klasor: str) -> str:
    return os.path.normcase(os.path.abspath(klasor))


def _plan_oku(klasor: str) -> str | None:
    """plan.md metni: yazım anı denetiminde yazılacak metin (`_PLAN_ESI`), yoksa diskteki dosya."""
    k = _anahtar(klasor)
    return _PLAN_ESI[k] if k in _PLAN_ESI else _oku(os.path.join(klasor, "plan.md"))


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
    metin = _plan_oku(klasor) or ""
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
    metin = _plan_oku(klasor)
    if metin is None:
        return ["plan.md yok (`orkestra is belge <id> plan`)"]
    return (_plan_temel_eksikleri(klasor, metin) + mevcut_varlik_eksikleri(klasor) + gap_kapsama_eksikleri(klasor)
            + bic_engeli(klasor) + uretim_engeli(klasor) + paralellik_engeli(klasor) + jira_bagimlilik_engeli(klasor)
            + karar_engeli(klasor) + istek_engeli(klasor) + etki_engeli(klasor))


def istek_engeli(klasor: str) -> list[str]:
    """ADR-0112: istek defterindeki karşılanmamış madde (kapsam: is.json `istek: true`; mod: ayarlar/istek_defteri.json)."""
    import istek_defteri
    return istek_defteri.engel(klasor, "istek_defteri:plan")


def karar_engeli(klasor: str) -> list[str]:
    """ADR-0112: yanıtsız `Karar gerekir` maddesi plan yazımını engeller (kapsam: is.json `karar: true`)."""
    import karar_kapisi
    return karar_kapisi.engel(klasor)


def _plan_temel_eksikleri(klasor: str, metin: str) -> list[str]:
    """Kapısız (her sıralı işte) plan eksikleri: mevcut durum bağlantısı, P maddeleri, MD dayanağı; kalite işinde Özet/Kabul/Geri alma."""
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
    return eksik


# I-224: plan.md yazım anı raporu. Ret koşulu değişmez (ön koşul ya da bu yazımın getirdiği `Mevcut varlık` hatası);
# değişen, aynı yazımda planın todo / `plan dogrula` anında ret verecek tüm alan eksiklerinin tek iletide, düzeltme
# satırıyla görünmesidir. Gölgedeki kapılar yalnız bilgi satırı olur. Kayıt (kapi_ret / kapi_golge) düşmez: metin henüz yazılmadı.
PLAN_MESAJ_SINIR = 2000
_MODLU_KAPILAR = (("best_in_class", "bic_kapsaminda_mi", "bic_eksikleri"),
                  ("uretim_noktasi", "uretim_kapsaminda_mi", "uretim_eksikleri"),
                  ("gorunum_olcumu", "gorunum_olcumu_kapsaminda_mi", "gorunum_olcumu_eksikleri"),
                  ("paralellik", "paralellik_kapsaminda_mi", "paralellik_eksikleri"),
                  ("jira_bagimlilik", "jira_bagimlilik_kapsaminda_mi", "jira_bagimlilik_eksikleri"),
                  ("sozlesme", "sozlesmeli_mi", "sozlesme_baglanti_eksikleri"))


def plan_yazim_eksikleri(klasor: str, metin: str) -> tuple[list[str], list[str]]:
    """Yazılacak plan metni için (ret veren, gölge) eksikler: ret veren = kapısız alanlar + ihlal modundaki kapılar
    (todo yazımında ve `plan dogrula`da reddedilir); gölge = gölge modundaki kapıların eksikleri (engellemez)."""
    import kapi_mod as KM
    k = _anahtar(klasor)
    onceki = _PLAN_ESI.get(k)
    _PLAN_ESI[k] = metin
    try:
        sert = _plan_temel_eksikleri(klasor, metin) + mevcut_varlik_eksikleri(klasor, metin) + gap_kapsama_eksikleri(klasor)
        golge: list[str] = []
        for kapi, kapsam, islev in _MODLU_KAPILAR:
            if not globals()[kapsam](klasor):
                continue
            e = globals()[islev](klasor)
            (sert if KM.mod(kapi, klasor) == "ihlal" else golge).extend(e)
    finally:
        if onceki is None:
            _PLAN_ESI.pop(k, None)
        else:
            _PLAN_ESI[k] = onceki
    return sert, golge


_DUZELTMELER = (  # (eksik metninde aranan, düzeltme şablonu); {h} = madde (P<n>) ya da "plan.md"; ilk eşleşen kullanılır
    (r"^G(\d+): hiçbir P", "bir P'nin `**Gap:**` alanına G{1} ekle ya da `## Gap kapsama` altına `- **G{1}:** Kapsam dışı: <gerekçe>` yaz"),
    (r"^P\d+: G(\d+) mevcut durum", "{h} `**Gap:**` alanından G{1}'i çıkar ya da mevcut durum §6'ya `- **G{1}:** …` ekle"),
    (r"\*\*Gap:\*\*", "{h} altına yaz: `**Gap:** G1` (mevcut durum §6'daki gap)"),
    (r"^S(\d+): hiçbir", "bir P'nin `**Sözleşme:**` alanına S{1} ekle"),
    (r"\*\*Sözleşme:\*\*", "{h} altına yaz: `**Sözleşme:** S1` (sözleşmedeki başarı kriteri)"),
    (r"Mevcut varlık|haritada yok|`yok` için aranan|sistem haritası yok",
     "{h} altına yaz: `**Mevcut varlık:** <harita kimliği>` ya da `**Mevcut varlık:** yok — <aranan>` (kimlik: `orkestra harita oku`)"),
    (r"\*\*Alternatifler:\*\*", "{h} altına yaz: `**Alternatifler:**` ve alt satırlarda `- Seçilen: …` ile `- Elenen: … Neden elendi: …`"),
    (r"^P\d+: `\*\*Üretim noktası:\*\*|^P\d+: `Yeni yetenek`",
     "{h} altına yaz: `**Üretim noktası:** Düzeltme: <yer> — <önleme, en az 15 karakter>` (ya da `Kontrol: … ; Kaynakta çözülmedi çünkü: …`)"),
    (r"Best in class denetimi` bloğu yok", "plan sonuna `## Best in class denetimi` bloğunu aç; satırlarını ayrı orkestra:denetci doldurur"),
    (r"^best in class denetimi:", "plan yazarı yazmaz: bu satırı ayrı orkestra:denetci doldurur (`**Denetçi:** <agent_id>`)"),
    (r"LLM çıktısı", "plan.md'ye yaz: `**LLM çıktısı:** yok — <en az 3 sözcük neden>` ya da `kullanıcıya gider — Doğrulama: <test yolu>`"),
    (r"\*\*Kabul:\*\*", "{h} altına yaz: `**Kabul:** <ölçülebilir ölçüt>`"),
    (r"\*\*Geri alma:\*\*", "{h} altına yaz: `**Geri alma:** <geri alma yolu, örn. git revert>`"),
    (r"yazma alanı kesişiyor", "sonraki maddeye yaz: `**Önce:** P<önceki> — Çakışma: <gerekçe>`"),
    (r"\*\*Yazma alanı:\*\*", "{h} altına yaz: `**Yazma alanı:** scripts/a.py, tests/test_a.py`"),
    (r"\*\*Önce:\*\*", "{h} altına yaz: `**Önce:** yok` ya da `**Önce:** P1 — Çıktı: <gerekçe>`"),
    (r"dayanağı yok|dayanak MD", "{h} altına yaz: `**Dayanak:** MD §3` (geçerli mevcut durum bölümü)"),
    (r"bağlantısı yok", "plan.md'nin ilk satırlarına eksikte verilen `[mevcut_durum_….md](…)` bağlantısını yaz"),
    (r"`P<n>` maddesi yok", "plan.md'ye `### P1 <başlık>` maddesi ekle"),
    (r"`## Özet`", "belgenin en üstüne `## Özet` ve 3-4 cümle yaz"),
    (r"^mevcut durum|^mevcut_durum", "mevcut durum belgesinde eksik bölüm ya da alanı doldur (`orkestra is sira <id>`)"),
    (r"sözleşme|sozlesme_", "sözleşme belgesinde eksik bölümü doldur (`orkestra is belge <id> sozlesme`)"),
)


def duzeltme_satiri(eksik: str) -> str:
    """Eksik satırı için hazır düzeltme: hangi madde, hangi alan, ne yazılacak (örnek biçimle)."""
    m = re.match(r"^(P\d+):", eksik)
    h = m.group(1) if m else "plan.md"
    for desen, sablon in _DUZELTMELER:
        d = re.search(desen, eksik)
        if d:
            return sablon.replace("{h}", h).replace("{1}", d.group(1) if d.groups() else "")
    return "ayrıntı: `orkestra plan dogrula <iş>`"


def plan_yazim_mesaji(klasor: str, ret: list[str], metin: str | None) -> str:
    """Tek ileti: önce ret nedenleri (ön koşul ya da bu yazımın getirdiği eksik), sonra planın todo/`plan dogrula`da ret
    verecek diğer alan eksikleri, en sonda gölge kapı bilgisi; her madde bir satır + düzeltme satırı, toplam en çok
    PLAN_MESAJ_SINIR karakter. `ret` boşsa ileti bilgi amaçlıdır (yazım engellenmez). Eksik yoksa boş metin."""
    sert, golge = plan_yazim_eksikleri(klasor, metin) if metin is not None else ([], [])
    sert = [e for e in sert if e not in ret]
    if not (ret or sert or golge):
        return ""
    if ret:
        bas = "plan.md yazılamaz (P-005; kapatma: ORKESTRA_SIRA_KAPISI=0)."
    else:
        bas = "plan.md yazıldı; todo yazımında ve `orkestra plan dogrula`da ret verecek eksikler (bu yazımı engellemez):"
    gruplar = [(f"Ret nedeni ({len(ret)}):", ret), (f"Diğer eksikler ({len(sert)}):" if ret else "", sert),
               (f"Bilgi, gölge kapı ({len(golge)}; engellemez):", golge)]
    satirlar, kalan, no = [bas], 0, 0
    kuyruk = "+{} eksik daha: orkestra plan dogrula <iş>"
    for baslik, liste in gruplar:
        if not liste:
            continue
        if kalan:
            kalan += len(liste)
            continue
        if baslik:
            satirlar.append(baslik)
        for i, e in enumerate(liste):
            no += 1
            parca = [f"{no}. {e}", f"   → {duzeltme_satiri(e)}"]
            if len("\n".join(satirlar + parca)) + len(kuyruk) + 8 > PLAN_MESAJ_SINIR:
                kalan = len(liste) - i
                break
            satirlar += parca
    if kalan:
        satirlar.append(kuyruk.format(kalan))
    return "\n".join(satirlar)


def adim(klasor: str) -> tuple[str, list[str]]:
    """(şu anki adım, o adımın eksikleri): 'sozlesme' | 'mevcut_durum' | 'plan' | 'todo' (todo = ön koşullar tamam).
    'sozlesme' adımı yalnız sözleşmeli işte ve `ihlal` modunda çıkar (ADR-0035); gölge modunda sessizce atlanır."""
    e = sozlesme_engeli(klasor)
    if e:
        return "sozlesme", e
    e = mevcut_durum_eksikleri(klasor)
    if e:
        return "mevcut_durum", e
    e = plan_eksikleri(klasor)
    if e:
        return "plan", e
    e = sozlesme_engeli(klasor, baglanti=True)
    if e:
        return "plan", e
    return "todo", []


def plan_onkosulu(klasor: str) -> list[str]:
    """plan.md yazımı için ön koşul: sözleşme (ihlal modunda) ve mevcut durum tamam; gölge modunda sözleşme eksiği uyarılır."""
    return sozlesme_uyari(klasor, baglanti=False) + mevcut_durum_eksikleri(klasor)


def todo_onkosulu(klasor: str) -> list[str]:
    """todo.md yazımı için ön koşul: sözleşme (ihlal modunda), mevcut durum ve plan tamam."""
    engel = sozlesme_engeli(klasor, baglanti=True) or mevcut_durum_eksikleri(klasor) or plan_eksikleri(klasor)
    if not engel:
        bic_uyari(klasor)  # P-030 gölge: uyarır ve kaydeder, todo yazımını engellemez
        gorunum_olcumu_uyari(klasor)  # P-044 gölge: aynı biçimde
    return engel


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
