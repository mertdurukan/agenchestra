"""Okunacak belgelerin (plan, todo, özet, bulgu, jira_onerisi, rapor) K-005 biçimi ve K-003 bağlantı satırı kontrolü.

Saf Python; model çağrılmaz. Kurallar ve mod `ayarlar/belge_bicim.json` (eklenti varsayılanı) ve proje durum
dizinindeki `belge_bicim.json` (alan alan ezer) içinden okunur. Bozuk ya da eksik dosya varsayılana düşer.

Yazım anı kapısı (`yazim_ihlalleri`): PreToolUse içinde yazılacak metni tarar; ihlalli içerik diske inmeden bilinir.
Güvenli düzeltme (`guvenli_duzelt`, I-224 P9): ihlallerin tümü anlamı değiştirmeyen dönüşümle gideriliyorsa
düzeltilmiş metni verir; hook bunu Write'ta ret yerine updatedInput olarak kullanır (`ayarlar/belge_duzelt.json`).
Bağlantı kapısı (`baglantisiz_belgeler`): Stop içinde dokunulan belgelerin yanıtta bağlantısı var mı bakar.
Kapsam dışı (kullanıcı kararı bekliyor, rapor Ö7): tablo satırları, kod blokları ve Given/When/Then satırları sayılmaz.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "belge_bicim.json")
PROJE_DOSYA = "belge_bicim.json"
MODLAR = ("golge", "ihlal")

_SATIR_ICI_KOD = re.compile(r"`[^`\n]*`")
_BAGLANTI_HEDEFI = re.compile(r"\]\([^)\n]*\)")
_HARF_ISARETI = re.compile(r"\((?:[a-zA-Z]|\d{1,2})\)")
_LISTE_MADDESI = re.compile(r"^\s*(?:[-*]|\d+[.)])\s")


def _json_oku(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def ayar_oku(sd=None) -> dict:
    ayar = _json_oku(VARSAYILAN_YOL) or {}
    proje = _json_oku(os.path.join(sd, PROJE_DOSYA)) if sd else None
    for kapi, deger in (proje or {}).items():
        if isinstance(deger, dict) and isinstance(ayar.get(kapi), dict):
            ayar[kapi] = {**ayar[kapi], **deger}
        else:
            ayar[kapi] = deger
    return ayar


def mod(ayar: dict, kapi: str) -> str:
    m = (ayar.get(kapi) or {}).get("mod", "golge")
    return m if m in MODLAR else "golge"


def belge_mi(yol: str, kapi_ayari: dict) -> bool:
    """Okunacak belge adı (.md; plan/todo/bulgu/jira_onerisi/rapor/özet) ve hariç tutulanlardan değil."""
    if not yol:
        return False
    yol = yol.replace("\\", "/")
    ad = os.path.basename(yol).lower()
    if not ad.endswith(".md"):
        return False
    try:
        if re.search(kapi_ayari.get("haric_ad_kalibi") or r"(?!x)x", ad):
            return False
        if re.search(kapi_ayari.get("haric_yol_kalibi") or r"(?!x)x", yol):
            return False
        return bool(re.search(kapi_ayari.get("belge_adi_kalibi") or r"(?!x)x", ad))
    except re.error:
        return False


_SATIR_ICI_YORUM = re.compile(r"<!--.*?-->")


def _temizle(metin: str) -> str:
    """Sayımda satır içi kod, bağlantı hedefi ve satır içi HTML yorumu yok sayılır (içindeki ;, · ve ** sayılmaz)."""
    return _BAGLANTI_HEDEFI.sub("]", _SATIR_ICI_KOD.sub("``", _SATIR_ICI_YORUM.sub("", metin)))


def _yorum_acar(s: str) -> bool:
    """Satır kapanmamış bir HTML yorumu açıyor mu (son `<!--`'dan sonra `-->` yok)."""
    i = s.rfind("<!--")
    return i >= 0 and "-->" not in s[i + 4:]


def _bloklar(metin: str, yok_say: re.Pattern | None):
    """(ilk_satır_no, metin, tur) — tur: liste | paragraf. Başlık, tablo, kod bloğu, HTML yorumu (çok satırlı
    yorumun devam satırları dahil; I-224 P9) ve yok sayılan satırlar atlanır."""
    cikti, tampon, bas, kod, yorum = [], [], None, False, False

    def bosalt():
        nonlocal tampon, bas
        if tampon:
            cikti.append((bas, " ".join(tampon), "paragraf"))
        tampon, bas = [], None

    for no, ham in enumerate(metin.split("\n"), 1):
        s = ham.rstrip("\r")
        if yorum:  # yorum içi: kod çiti de dahil hiçbir şey sayılmaz; `-->` satırı da atlanır
            bosalt()
            if "-->" in s:
                yorum = _yorum_acar(s[s.index("-->") + 3:])
            continue
        if not kod and _yorum_acar(s):
            yorum = True
            if s.lstrip().startswith("<!--"):
                bosalt()
                continue
            s = s[:s.rfind("<!--")]  # yorumdan önceki metin sayılır
            if not s.strip():
                bosalt()
                continue
        if s.strip().startswith("```"):
            bosalt()
            kod = not kod
            continue
        if kod:
            continue
        if not s.strip():
            bosalt()
            continue
        if s.lstrip().startswith("#") or s.lstrip().startswith("|") or s.lstrip().startswith("<!--"):
            bosalt()
            continue
        if yok_say and yok_say.search(s):
            bosalt()
            continue
        if _LISTE_MADDESI.match(s):
            bosalt()
            cikti.append((no, s.strip(), "liste"))
            continue
        if bas is None:
            bas = no
        tampon.append(s.strip())
    bosalt()
    return cikti


def yazim_ihlalleri(metin: str, dosya_adi: str, ayar: dict) -> list[dict]:
    """Yazılacak metindeki K-005 ihlalleri: [{satir, kural, ayrinti}]. Satır, metnin kendi içinde 1'den sayılır."""
    k = ayar.get("yazim_kapisi") or {}
    if not metin:
        return []
    bastirma = k.get("bastirma_isareti") or "<!-- biçim-tamam -->"
    try:
        yok_say = re.compile(k["yok_say_satir_kalibi"]) if k.get("yok_say_satir_kalibi") else None
        etiket = re.compile(k.get("etiket_kalibi") or r"\*\*[^*\n]{1,40}?:?\*\*:?")
    except re.error:
        return []
    paragraf_azami = int(k.get("paragraf_azami") or 300)
    todo_azami = int(k.get("todo_madde_azami") or 200)
    en_az = int(k.get("sikisik_liste_en_az") or 2)
    noktali_en_az = int(k.get("noktali_virgul_en_az") or 3)  # düz cümlede iki ; olağan; üç ve üzeri liste
    todo = "todo" in os.path.basename(dosya_adi).lower()
    ihlaller = []
    for no, blok, tur in _bloklar(metin, yok_say):
        if bastirma in blok:
            continue
        t = _temizle(blok)
        if len(etiket.findall(t)) >= 2:
            ihlaller.append({"satir": no, "kural": "coklu_etiket",
                             "ayrinti": "bir paragrafta birden çok etiket; her etiketli alan ayrı paragrafa"})
        if t.count(";") >= noktali_en_az or t.count(" · ") >= en_az or len(_HARF_ISARETI.findall(t)) >= en_az:
            ihlaller.append({"satir": no, "kural": "sikisik_liste",
                             "ayrinti": "satır içi liste (;, ·, (a)(b)); her maddeyi ayrı satıra, madde işaretiyle yaz"})
        todo_maddesi = todo and tur == "liste"
        azami = todo_azami if todo_maddesi else paragraf_azami
        if len(blok) > azami:
            ihlaller.append({"satir": no, "kural": "uzun_todo_madde" if todo_maddesi else "uzun_paragraf",
                             "ayrinti": f"{len(blok)} karakter, en çok {azami}; "
                                        + ("ayrıntıyı plan.md ya da özete yaz" if todo_maddesi else "kısa paragraflara böl")})
    return ihlaller


# ---------------------------------------------------------------- güvenli düzeltme (I-224 P9)
# Yalnız anlamı değiştirmeyen, ayırıcısı kesin dönüşümler. Uzun paragraf / uzun todo maddesi (kısaltma ister),
# `;` ve (a)(b) listeleri (ayırıcı belirsiz) düzeltilmez. Kod bloğu, HTML yorumu, tablo, başlık, alıntı, HTML satırı,
# YAML ön bilgisi, girintili satır ve liste maddesine dokunulmaz.

_KESIN_ETIKET = re.compile(r"\*\*[^*\n]{1,40}?:\*\*(?=\s|$)")  # yalnız '**Etiket:**' biçimi
_NOKTA_AYIRICI = " · "
_NOKTA_MADDE_AZAMI = 120
_ONEK = re.compile(r"^(?:\*\*[^*\n]{1,40}?:\*\*|[^\s:*`][^:*`]{0,38}:)(?=\s)")  # '**Durum:**' ya da 'Durum:' öneki


def _maske(s: str) -> str:
    """Satır içi kod, bağlantı hedefi ve satır içi yorum aynı uzunlukta '\\0' ile örtülür (konum korunur)."""
    for r in (_SATIR_ICI_KOD, _BAGLANTI_HEDEFI, _SATIR_ICI_YORUM):
        s = r.sub(lambda m: "\0" * len(m.group(0)), s)
    return s


def _korunan_satirlar(satirlar: list[str]) -> list[bool]:
    """Dönüştürülmeyecek satırlar: YAML ön bilgisi, kod bloğu, HTML yorumu (çok satırlı dahil)."""
    korunan, kod, yorum = [False] * len(satirlar), False, False
    bas = 0
    if satirlar and satirlar[0].strip() == "---":
        for j in range(1, len(satirlar)):
            if satirlar[j].strip() in ("---", "..."):
                for k in range(j + 1):
                    korunan[k] = True
                bas = j + 1
                break
    for i in range(bas, len(satirlar)):
        s = satirlar[i]
        if yorum:
            korunan[i] = True
            if "-->" in s:
                yorum = _yorum_acar(s[s.index("-->") + 3:])
            continue
        if not kod and _yorum_acar(s):
            korunan[i], yorum = True, True
            continue
        if s.strip().startswith("```"):
            korunan[i], kod = True, not kod
            continue
        korunan[i] = kod or "<!--" in s
    return korunan


def _duz_paragraf_satiri(s: str, yok_say: re.Pattern | None, bastirma: str) -> bool:
    """Girintisiz, düz paragraf satırı (başlık, tablo, alıntı, HTML, liste, Given/When ve bastırmalı satır değil)."""
    if not s.strip() or s[0].isspace() or bastirma in s:
        return False
    if s.startswith(("#", "|", ">", "<", "```")) or _LISTE_MADDESI.match(s):
        return False
    return not (yok_say and yok_say.search(s))


def _etiket_bol(s: str) -> list[str] | None:
    """'**A:** x **B:** y' → ['**A:** x', '**B:** y']. Satır etiketle başlamıyorsa ya da tek etiket varsa None."""
    yerler = [m.start() for m in _KESIN_ETIKET.finditer(_maske(s))]
    if len(yerler) < 2 or yerler[0] != 0:
        return None
    parca = [s[a:b].strip() for a, b in zip(yerler, yerler[1:] + [len(s)])]
    return parca if all(_KESIN_ETIKET.fullmatch(p) is None for p in parca) else None  # boş alan bırakılmaz


def _nokta_bol(s: str, en_az: int) -> list[str] | None:
    """'Önek: a · b · c' → ['Önek:', '', '- a', '- b', '- c']; ayırıcı kesin değilse None.
    Kesinlik: en az `en_az` ayırıcı, her madde dolu ve kısa, maske dışında başka '·' yok, satır cümle gibi bitmiyor."""
    m = _maske(s)
    if m.count(_NOKTA_AYIRICI) < en_az or m.count("·") != m.count(_NOKTA_AYIRICI):
        return None
    yerler, i = [], m.find(_NOKTA_AYIRICI)
    while i >= 0:
        yerler.append(i)
        i = m.find(_NOKTA_AYIRICI, i + len(_NOKTA_AYIRICI))
    sinir = [0] + [y + len(_NOKTA_AYIRICI) for y in yerler]
    maddeler = [s[a:(yerler[k] if k < len(yerler) else len(s))].strip() for k, a in enumerate(sinir)]
    onek = ""
    o = _ONEK.match(maddeler[0])
    if o:
        onek, maddeler[0] = o.group(0), maddeler[0][o.end():].strip()
    if any(not x or len(x) > _NOKTA_MADDE_AZAMI for x in maddeler):
        return None
    return ([onek, ""] if onek else []) + [f"- {x}" for x in maddeler]


def _donustur(metin: str, ayar: dict) -> tuple[str, list[dict]]:
    k = ayar.get("yazim_kapisi") or {}
    bastirma = k.get("bastirma_isareti") or "<!-- biçim-tamam -->"
    try:
        yok_say = re.compile(k["yok_say_satir_kalibi"]) if k.get("yok_say_satir_kalibi") else None
    except re.error:
        yok_say = None
    en_az = int(k.get("sikisik_liste_en_az") or 2)
    satirlar = metin.split("\n")
    korunan = _korunan_satirlar(satirlar)
    bloklar: list[tuple[list[str], bool]] = []  # (kaynak satırın yerini alan satırlar, ardına boş satır gerekir mi)
    uygulanan: list[dict] = []
    for no, s in enumerate(satirlar, 1):
        if korunan[no - 1] or not _duz_paragraf_satiri(s, yok_say, bastirma):
            bloklar.append(([s], False))
            continue
        parcalar, donusum = _etiket_bol(s) or [s], []
        if len(parcalar) > 1:
            donusum.append("etiket_ayir")
        yeni: list[str] = []
        for p in parcalar:
            nb = _nokta_bol(p, en_az)
            if nb:
                donusum.append("nokta_liste")
            if yeni:
                yeni.append("")
            yeni.extend(nb or [p])
        onceki = satirlar[no - 2] if no > 1 else ""
        if _KESIN_ETIKET.match(s) and onceki.strip() and not korunan[no - 2] \
                and _duz_paragraf_satiri(onceki, yok_say, bastirma):
            donusum.append("bos_satir")  # bir önceki paragraf satırına yapışık etiketli alan: ayrı paragraf
            yeni.insert(0, "")
        if donusum:
            uygulanan.extend({"satir": no, "donusum": d} for d in donusum)
        bloklar.append((yeni, "nokta_liste" in donusum))
    # Üretilen madde listesinin ardındaki dolu satır son maddeye yapışmasın (Markdown tembel devam): araya boş satır.
    cikti: list[str] = []
    for i, (b, _) in enumerate(bloklar):
        if cikti and cikti[-1].strip() and b[0].strip() and (bloklar[i - 1][1] or (len(b) > 1 and b[-1].startswith("- "))):
            cikti.append("")
        cikti.extend(b)
    return "\n".join(cikti), uygulanan


def guvenli_duzelt(metin: str, dosya_adi: str = "plan.md", ayar: dict | None = None) -> tuple[str, list[dict]]:
    """K-005 ihlalli metne yalnız güvenli dönüşümleri uygular → (yeni_metin, uygulananlar).
    Uygulananlar: [{satir, donusum}] (donusum: etiket_ayir | bos_satir | nokta_liste). Hepsi ya da hiçbiri:
    metin ihlalsizse, dönüşüm yoksa ya da dönüşüm sonrası hâlâ ihlal kalıyorsa orijinal metin ve [] döner.
    İdempotent: sonuç ihlalsiz olduğundan ikinci uygulama metni değiştirmez."""
    ayar = ayar if ayar is not None else ayar_oku(None)
    if not metin or not yazim_ihlalleri(metin, dosya_adi, ayar):
        return metin, []
    crlf = "\r\n" in metin
    yeni, uygulanan = _donustur(metin.replace("\r\n", "\n") if crlf else metin, ayar)
    if crlf:
        yeni = yeni.replace("\n", "\r\n")
    if not uygulanan or yeni == metin or yazim_ihlalleri(yeni, dosya_adi, ayar):
        return metin, []
    return yeni, uygulanan


def duzelt_acik(sd=None) -> bool:
    """`ayarlar/belge_duzelt.json` mod (`acik` | `kapali`; proje ezmesi `<durum>/belge_duzelt.json`);
    ORKESTRA_BELGE_DUZELT=0 kapatır."""
    if os.environ.get("ORKESTRA_BELGE_DUZELT") == "0":
        return False
    m = "acik"
    for yol in (os.path.join(_KOK, "ayarlar", "belge_duzelt.json"), os.path.join(sd, "belge_duzelt.json") if sd else ""):
        d = _json_oku(yol) if yol else None
        if d and d.get("mod") in ("acik", "kapali"):
            m = d["mod"]
    return m == "acik"


def ozet_satiri(dosya_adi: str, ihlaller: list[dict], en_cok: int = 3) -> str:
    """Tek satırlık uyarı: ilk ihlaller satır numarasıyla."""
    parca = ", ".join(f"satır {i['satir']} {i['kural']}" for i in ihlaller[:en_cok])
    ek = f" (+{len(ihlaller) - en_cok})" if len(ihlaller) > en_cok else ""
    return f"Orkestra biçim (K-005, gölge): {dosya_adi}: {parca}{ek}. Ayrıntı: {ihlaller[0]['ayrinti']}."


def baglantisiz_belgeler(dokunulan, yanit: str, ayar: dict) -> list[str]:
    """Dokunulan okunacak belgelerden yanıtta bağlantısı (`](…<dosya adı>…)`) olmayanlar; yol sırası korunur."""
    k = ayar.get("baglanti_kapisi") or {}
    yanit = (yanit or "").replace("\\", "/")
    sonuc, gorulen = [], set()
    for yol in dokunulan or []:
        tam = str(yol).replace("\\", "/")
        if tam in gorulen or not belge_mi(tam, k):
            continue
        gorulen.add(tam)
        ad = os.path.basename(tam)
        if not re.search(r"\]\([^)\n]*" + re.escape(ad) + r"[^)\n]*\)", yanit):
            sonuc.append(tam)
    return sonuc
