"""Plan paralelliği: P bloklarından `Önce` ve `Yazma alanı` ayrıştırır, dalga / kritik yol / planlanan eşzamanlılık hesaplar.

Kapı (is_sirasi), `orkestra is dalga` ve iş raporu aynı fonksiyonları kullanır (ADR-0080, K2). Kontrol fonksiyonları hata
mesajı listesi döner; boş liste temiz demektir.

`Önce` biçimi: `yok` ya da `P<n> — Çıktı: <gerekçe>` / `P<n> — Çakışma: <gerekçe>` girdileri (`,` ya da `;` ile ayrılır;
ayraç `—`, `–` ya da `-`). `Yazma alanı`: virgülle ayrılmış dosya ya da glob listesi.
"""
from __future__ import annotations

import fnmatch
import re

import jira_bagimlilik as JB

# is_sirasi._p_bloklari / _alan_degeri ile aynı mantık. is_sirasi bu modülü çağıracağı için (P3) döngüsel import
# yerine kopyalandı; desen değişirse ikisi birlikte güncellenir.
_YORUM = re.compile(r"<!--.*?-->", re.S)
_P_SATIRI = re.compile(r"^(?:#{2,4}\s+|[-*]\s+(?:\*\*)?)P(\d+)\b", re.M)

CIKTI, CAKISMA = "Çıktı", "Çakışma"
TAM_SIRALI_MIN = 15  # `Tam sıralı çünkü:` gerekçesi en az bu kadar karakter
TAM_SIRALI_MADDE = 3  # bu kadar ve daha fazla maddelik genişlik-1 plan gerekçe ister

_AYRAC = r"\s*[—–-]\s*"
_GIRDI = re.compile(r"^P(\d+)" + _AYRAC + r"(Çıktı|Çakışma)\s*:\s*(.*)$", re.S)
# Gerekçe metninde virgül geçebilir; yalnız yeni bir `P<n> — Tür:` girdisinden önceki `,` / `;` böler.
_BOL = re.compile(r"\s*[,;]\s*(?=P\d+" + _AYRAC + r"(?:Çıktı|Çakışma)\s*:)")
_TAM_SIRALI = re.compile(r"^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?Tam sıralı çünkü:(?:\*\*)?[ \t]*(.*)$", re.M)
_GLOB = re.compile(r"[*?\[]")
_JIRA = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def _p_bloklari(metin: str) -> dict[int, str]:
    """{P numarası: blok metni}; blok bir sonraki P satırına ya da `## ` başlığına kadar sürer (is_sirasi kopyası)."""
    satirlar = _YORUM.sub("", metin).splitlines()
    bloklar: dict[int, list[str]] = {}
    gecerli = None
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


def _alan_degeri(blok: str, alan: str) -> str:
    """P bloğunda satır başındaki `**<alan>:**` değeri; yoksa '' (is_sirasi kopyası)."""
    m = re.search(r"^[ \t]*\*\*" + re.escape(alan) + r":\*\*(.*?)(?=^\*\*[^\n*]+:\*\*|\Z)", _YORUM.sub("", blok), re.S | re.M)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def once_ayristir(deger: str) -> tuple[list[tuple[int, str, str]], list[str]]:
    """`Önce` değeri → ([(n, tür, gerekçe)], biçim hataları). `yok` boş liste döner; boş değer hatadır."""
    d = deger.strip().strip(".").strip()
    if not d:
        return [], ["değer boş"]
    if d.lower() == "yok":
        return [], []
    bagimliliklar, hatalar = [], []
    for parca in _BOL.split(d):
        parca = parca.strip().strip("`").strip()
        m = _GIRDI.match(parca)
        if not m:
            hatalar.append(f"biçimsiz girdi '{parca[:60]}' (beklenen: P<n> — Çıktı: … ya da P<n> — Çakışma: …)")
            continue
        gerekce = m.group(3).strip()
        if not gerekce:
            hatalar.append(f"P{m.group(1)} girdisinde gerekçe boş")
            continue
        bagimliliklar.append((int(m.group(1)), m.group(2), gerekce))
    return bagimliliklar, hatalar


def yazma_ayristir(deger: str) -> set[str]:
    """`Yazma alanı` değeri → normalize yol kümesi (ters bölü `/`, ters tırnak ve baştaki `./` atılır)."""
    kume = set()
    for parca in deger.split(","):
        p = parca.strip().strip("`").strip().replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        if p and p.lower() != "yok":
            kume.add(p)
    return kume


def maddeler(plan_metni: str) -> dict[int, dict]:
    """{n: {n, once, once_ham, once_hatalari, yazma, yazma_ham, jira}} — her P bloğu için ayrıştırılmış alanlar.

    `jira`: `**Jira:**` alanındaki ilk anahtar (PE-770); alan yoksa '' (ADR-0086)."""
    sonuc = {}
    for n, blok in sorted(_p_bloklari(plan_metni).items()):
        once_ham = _alan_degeri(blok, "Önce")
        yazma_ham = _alan_degeri(blok, "Yazma alanı")
        once, hatalar = once_ayristir(once_ham) if once_ham else ([], [])
        jira = _JIRA.search(_alan_degeri(blok, "Jira"))
        sonuc[n] = {"n": n, "once": once, "once_ham": once_ham, "once_hatalari": hatalar,
                    "yazma": yazma_ayristir(yazma_ham), "yazma_ham": yazma_ham, "jira": jira.group(0) if jira else ""}
    return sonuc


def _norm(yol: str) -> str:
    """Küçük harf (Windows yolları); `/` ile biten klasör girdisi `klasör/**` sayılır."""
    yol = yol.lower()
    return yol + "**" if yol.endswith("/") else yol


def _yol_kesisir(a: str, b: str) -> bool:
    """İki yazma alanı girdisi aynı dosyaya düşebilir mi (glob için fnmatch ve önek; temkinli: şüphede kesişir)."""
    a, b = _norm(a), _norm(b)
    if a == b:
        return True
    ga, gb = _GLOB.search(a), _GLOB.search(b)
    if ga and fnmatch.fnmatchcase(b, a):
        return True
    if gb and fnmatch.fnmatchcase(a, b):
        return True
    if ga or gb:
        # Glob'un sabit öneki (ilk joker karakterden önceki kısım) öbürünün önekiyse alan altına düşer sayılır.
        oa = a[:ga.start()] if ga else a
        ob = b[:gb.start()] if gb else b
        if ga and gb:
            return oa.startswith(ob) or ob.startswith(oa)
        if ga and "**" in a:
            return b.startswith(oa)
        if gb and "**" in b:
            return a.startswith(ob)
    return False


def alan_kesisir(a: set[str], b: set[str]) -> bool:
    """İki yazma alanı kümesinde ortak dosyaya düşen bir girdi çifti var mı."""
    return any(_yol_kesisir(x, y) for x in a for y in b)


def _gecerli_kenarlar(md: dict[int, dict]) -> dict[int, set[int]]:
    """{n: bağımlı olduğu var olan ve kendisi olmayan maddeler}; geçersiz başvurular hesaba girmez."""
    return {n: {d for d, _, _ in m["once"] if d in md and d != n} for n, m in md.items()}


def dongu_var_mi(md: dict[int, dict]) -> list[str]:
    """Geçerli bağımlılıklarda döngü varsa döngüdeki maddeleri söyleyen tek mesaj."""
    kenar = _gecerli_kenarlar(md)
    durum: dict[int, int] = {}  # 1 ziyarette, 2 bitti
    yigin: list[int] = []

    def gez(n: int) -> list[int] | None:
        durum[n] = 1
        yigin.append(n)
        for d in sorted(kenar[n]):
            if durum.get(d) == 1:
                return yigin[yigin.index(d):] + [d]
            if d not in durum:
                bulunan = gez(d)
                if bulunan:
                    return bulunan
        yigin.pop()
        durum[n] = 2
        return None

    for n in sorted(md):
        if n not in durum:
            dongu = gez(n)
            if dongu:
                return ["bağımlılık döngüsü: " + " → ".join(f"P{x}" for x in dongu)]
    return []


def dalgalar(md: dict[int, dict]) -> dict:
    """Topolojik seviyeler ve ölçüler. Dalga = en uzun bağımlılık zinciri derinliği; döngüde dalgalar boş döner.

    planlanan_agirliksiz = P sayısı ÷ kritik yol; planlanan_agirlikli = Σ ağırlık ÷ ağırlıklı kritik yol
    (ağırlık = yazma alanı girdi sayısı, en az 1; ağırlıklı kritik yol = ağırlık toplamı en büyük zincir; K6)."""
    bos = {"dalgalar": [], "seviye": {}, "kritik_yol": 0, "genislik": 0, "agirlik": {},
           "agirlikli_kritik_yol": 0, "planlanan_agirliksiz": 0.0, "planlanan_agirlikli": 0.0}
    if not md or dongu_var_mi(md):
        return bos
    kenar = _gecerli_kenarlar(md)
    agirlik = {n: max(1, len(m["yazma"])) for n, m in md.items()}
    seviye: dict[int, int] = {}
    zincir: dict[int, int] = {}  # n'de biten en ağır zincirin ağırlığı

    def hesapla(n: int) -> None:
        if n in seviye:
            return
        for d in kenar[n]:
            hesapla(d)
        seviye[n] = 1 + max((seviye[d] for d in kenar[n]), default=0)
        zincir[n] = agirlik[n] + max((zincir[d] for d in kenar[n]), default=0)

    for n in sorted(md):
        hesapla(n)
    kritik = max(seviye.values())
    katlar = [sorted(n for n in md if seviye[n] == k) for k in range(1, kritik + 1)]
    agir_kritik = max(zincir.values())
    return {"dalgalar": katlar, "seviye": seviye, "kritik_yol": kritik, "genislik": max(len(k) for k in katlar),
            "agirlik": agirlik, "agirlikli_kritik_yol": agir_kritik,
            "planlanan_agirliksiz": round(len(md) / kritik, 3),
            "planlanan_agirlikli": round(sum(agirlik.values()) / agir_kritik, 3)}


def alan_eksikleri(md: dict[int, dict]) -> list[str]:
    """`Önce` ya da `Yazma alanı` alanı yok, boş ya da biçimsiz olan maddeler."""
    hatalar = []
    for n, m in sorted(md.items()):
        if not m["once_ham"]:
            hatalar.append(f"P{n}: **Önce:** alanı yok (yok | P<n> — Çıktı: … | P<n> — Çakışma: …)")
        hatalar.extend(f"P{n}: **Önce:** {h}" for h in m["once_hatalari"])
        if not m["yazma"]:
            hatalar.append(f"P{n}: **Yazma alanı:** alanı yok ya da boş (virgülle ayrılmış dosya/glob listesi)")
    return hatalar


def gecersiz_basvuru(md: dict[int, dict], ileri_yasak: bool = True) -> list[str]:
    """Var olmayan maddeye, maddenin kendisine ya da (ileri_yasak iken) daha büyük numaralı maddeye başvuru."""
    hatalar = []
    for n, m in sorted(md.items()):
        for d, _, _ in m["once"]:
            if d not in md:
                hatalar.append(f"P{n}: **Önce:** var olmayan P{d} maddesine başvuruyor")
            elif d == n:
                hatalar.append(f"P{n}: **Önce:** kendine başvuruyor")
            elif ileri_yasak and d > n:
                hatalar.append(f"P{n}: **Önce:** sonraki P{d} maddesine (ileri) başvuruyor")
    return hatalar


def cakisma_sahtesi(md: dict[int, dict]) -> list[str]:
    """`Çakışma:` gerekçeli bağımlılıkta iki maddenin yazma alanı kesişmiyorsa gerekçe sahtedir."""
    hatalar = []
    for n, m in sorted(md.items()):
        for d, tur, _ in m["once"]:
            if tur == CAKISMA and d in md and d != n and not alan_kesisir(m["yazma"], md[d]["yazma"]):
                hatalar.append(f"P{n}: **Önce:** P{d} — Çakışma gerekçesi sahte; yazma alanları kesişmiyor")
    return hatalar


def ayni_dalga_kesisim(md: dict[int, dict], dalga: dict | None = None) -> list[str]:
    """Aynı dalgadaki iki maddenin yazma alanı kesişiyorsa (paralel koşamazlar; `Çakışma:` bağımlılığı gerekir)."""
    dalga = dalga or dalgalar(md)
    hatalar = []
    for k, kat in enumerate(dalga["dalgalar"], 1):
        for i, a in enumerate(kat):
            for b in kat[i + 1:]:
                if alan_kesisir(md[a]["yazma"], md[b]["yazma"]):
                    hatalar.append(f"Dalga {k}: P{a} ve P{b} yazma alanı kesişiyor; `Önce: P{a} — Çakışma: …` gerekir")
    return hatalar


def tam_sirali_mi(md: dict[int, dict], dalga: dict | None = None) -> bool:
    """Genişlik 1 ve TAM_SIRALI_MADDE ya da daha fazla madde: plan hiç paralellik taşımıyor."""
    dalga = dalga or dalgalar(md)
    return len(md) >= TAM_SIRALI_MADDE and dalga["genislik"] == 1


def tam_sirali_eksigi(plan_metni: str, md: dict[int, dict], dalga: dict | None = None) -> list[str]:
    """Tam sıralı planda `Tam sıralı çünkü:` satırı yok ya da gerekçesi TAM_SIRALI_MIN karakterden kısa."""
    if not tam_sirali_mi(md, dalga):
        return []
    m = _TAM_SIRALI.search(_YORUM.sub("", plan_metni))
    if m and len(m.group(1).strip()) >= TAM_SIRALI_MIN:
        return []
    return [f"Plan tam sıralı ({len(md)} madde, genişlik 1): `Tam sıralı çünkü:` satırına en az "
            f"{TAM_SIRALI_MIN} karakter gerekçe gerekir"]


def analiz(plan_metni: str, ileri_yasak: bool = True) -> dict:
    """Planın tam paralellik analizi: maddeler, dalgalar, ölçüler ve tüm kontrollerin birleşik eksik listesi."""
    md = maddeler(plan_metni)
    dalga = dalgalar(md)
    eksikler = (alan_eksikleri(md) + gecersiz_basvuru(md, ileri_yasak) + dongu_var_mi(md) + cakisma_sahtesi(md)
                + ayni_dalga_kesisim(md, dalga) + tam_sirali_eksigi(plan_metni, md, dalga))
    return {"maddeler": md, "dalgalar": dalga["dalgalar"], "kritik_yol": dalga["kritik_yol"],
            "genislik": dalga["genislik"], "agirlikli_kritik_yol": dalga["agirlikli_kritik_yol"],
            "planlanan_agirliksiz": dalga["planlanan_agirliksiz"],
            "planlanan_agirlikli": dalga["planlanan_agirlikli"], "eksikler": eksikler}


def jira_eksikleri(md: dict[int, dict], g: dict) -> list[str]:
    """`**Jira:**` taşıyan maddelerde açık Jira öncülünün plan kümesinde ve `**Önce:**` içinde olmasını sınar (ADR-0086).

    Kapalı öncül kümede olmak zorunda değildir; plan anahtarlarını içeren Jira döngüsü ret sebebidir. Bilerek `analiz()`
    içinde değil: `is_sirasi.paralellik_eksikleri` o listeyi ihlal modunda döndürür, Jira kontrolü gölgeden başlar
    (P-028); yalnız `is_sirasi.jira_bagimlilik_eksikleri` çağırır. `g`: `jira_bagimlilik.coz/yukle` çıktısı."""
    anahtar_p = {m["jira"]: n for n, m in md.items() if m.get("jira")}
    hatalar = []
    dongu = JB.dongu(g)
    if dongu and any(k in anahtar_p for k in dongu):
        hatalar.append("Jira bağımlılık döngüsü: " + " → ".join(dongu))
    for n, m in sorted(md.items()):
        j = m.get("jira")
        if not j:
            continue
        onceki = {d for d, _, _ in m["once"]}
        for o in sorted(JB.acik_onculler(g, j)):
            k = anahtar_p.get(o)
            if k is None:
                hatalar.append(f"P{n} ({j}): açık öncülü {o} plan kümesinde yok; {o} plana eklenmeden {j} tek başına seçilemez")
            elif k not in onceki:
                hatalar.append(f"P{n} ({j}): açık öncülü {o} (P{k}) **Önce:** içinde anılmıyor (`P{k} — Çıktı: {o}`)")
    return hatalar
