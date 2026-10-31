"""orkestra komutları: plan alan (P maddesi iskeleti; model çağırmaz). I-224 P4, kök neden R1.

`orkestra plan alan <iş-kimliği|iş klasörü> --gap G3 [--soz S3,S4] [--iddia C5] [--onceki P2] [--yazma "a,b"]
                    [--baslik B] [--dayanak-ek R1] [--no N] [--once-tur Çıktı|Çakışma] [--yaz] [--json]`

Zincir alanları (Gap, Sözleşme, Dayanak, İddialar, Önce, Yazma alanı) iş belgelerinden doğrulanıp türetilir:
G'ler mevcut durum §6'dan, S'ler sözleşmenin `## Başarı kriterleri` bölümünden, C'ler ve P'ler plan.md'den okunur.
Dayanak, seçilen G satırlarının andığı `MD §k` bölümünden türer (anma yoksa `MD §6 G<n>`). Serbest alanlar
(Ne, Kabul, Geri alma, Alternatifler, Üretim noktası …) `<doldur>` yer tutucusuyla kalır. Alan sırası işin plan
şablonundan gelir (`is_kaydi.plan_alan_sirasi`); plan biçimi değişmez, elle yazılmış planlar aynen geçerlidir.
Var olmayan G/S/C/P numarası çıkış 2 ile reddedilir. `--yaz` olmadan dosya değişmez (yalnız stdout).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys

from komutlar._ortak import hata

DOLDUR = "<doldur>"
ZINCIR = ("Gap", "Sözleşme", "Dayanak", "İddialar", "Önce", "Yazma alanı")
_NO = re.compile(r"^([A-Za-z])?(\d+)$")
_GAP_SATIR = re.compile(r"^\s*[-*]\s+\*\*G(\d+):?\*\*(.*)$", re.M)
_MD_ANMA = re.compile(r"MD\s*§\s*(\d+)")


def _nolar(deger: str | None, harf: str) -> list[int]:
    """'G3' / 'S3,S4' / '3 4' → [3, 4] (sıra korunur, tekrar atılır). Biçimsiz girdi ValueError."""
    sonuc: list[int] = []
    for parca in re.split(r"[,\s;]+", (deger or "").strip()):
        if not parca:
            continue
        m = _NO.match(parca)
        if not m or (m.group(1) and m.group(1).upper() != harf):
            raise ValueError(f"'{parca}' biçimsiz ({harf}<n> bekleniyor)")
        n = int(m.group(2))
        if n not in sonuc:
            sonuc.append(n)
    return sonuc


def _klasor_bul(hedef: str) -> str:
    if re.fullmatch(r"I-\d+", hedef):
        import is_kaydi
        from komutlar._ortak import sd_gerekli
        kayit = is_kaydi.is_al(sd_gerekli(), hedef)
        if not kayit:
            raise ValueError(f"iş yok: {hedef}")
        return kayit["klasor"]
    yol = os.path.abspath(hedef)
    if os.path.isfile(yol):
        yol = os.path.dirname(yol)
    if not os.path.isdir(yol):
        raise ValueError(f"iş klasörü bulunamadı: {hedef}")
    return yol


def kaynaklar(klasor: str) -> dict:
    """İş belgelerinden zincir kaynakları: {gaplar: {n: satır}, kriterler: set, iddialar: set, maddeler: set, plan: metin}."""
    import is_sirasi as SIRA
    md = SIRA.mevcut_durum_yolu(klasor)
    md_metin = SIRA._oku(md) if md else None
    g_bolum = SIRA._icerik(SIRA._bolumler(md_metin).get(SIRA.md_duzen(md_metin)[1], "")) if md_metin else ""
    gaplar = {int(n): metin.strip() for n, metin in _GAP_SATIR.findall(g_bolum)}
    plan = SIRA._oku(os.path.join(klasor, "plan.md"))
    iddialar: set[int] = set()
    if plan:
        import plan_dogrulama as PD
        iddialar = {c["no"] for c in PD.iddialari_ayristir(plan)}
    return {"gaplar": gaplar, "kriterler": SIRA.sozlesme_kriterleri(klasor), "iddialar": iddialar,
            "maddeler": set(SIRA._p_bloklari(plan)) if plan else set(), "plan": plan,
            "sozlesmeli": SIRA.sozlesme_yolu(klasor) is not None, "gapli": bool(gaplar),
            "paralel": SIRA.paralellik_kapsaminda_mi(klasor),
            "gap_bolum": SIRA.md_duzen(md_metin)[1]}


def dayanak_turet(gaplar: dict[int, str], secilen: list[int], ek: str = "", gap_bolum: int = 5) -> str:
    """Seçilen G satırlarının andığı MD bölümleri (sıralı, tekrarsız); anma yoksa `MD §<gap bölümü> G<n>`."""
    bolumler: list[int] = []
    for g in secilen:
        for k in _MD_ANMA.findall(gaplar.get(g, "")):
            if int(k) not in bolumler:
                bolumler.append(int(k))
    if bolumler:
        deger = ", ".join(f"MD §{k}" for k in bolumler)
    else:
        deger = f"MD §{gap_bolum} " + ", ".join(f"G{g}" for g in secilen)
    return f"{deger} {ek.strip()}".strip()


def iskelet(klasor: str, gap=None, soz=None, iddia=None, onceki=None, yazma=None, baslik=None, dayanak_ek="",
            no=None, once_tur="Çıktı", simdi: datetime.datetime | None = None) -> dict:
    """P maddesi iskeleti. Dönüş: {no, blok, turetilen, elle, tutarsizlik}. Geçersiz numara ya da eksik zorunlu zincir
    girdisi ValueError (mesaj her geçersiz öğeyi ve geçerli aralığı söyler)."""
    import is_kaydi
    k = kaynaklar(klasor)
    if k["plan"] is None:
        raise ValueError("plan.md yok (`orkestra is belge <id> plan`)")
    gap_n, soz_n, iddia_n = _nolar(gap, "G"), _nolar(soz, "S"), _nolar(iddia, "C")
    once_n = _nolar(onceki, "P")
    yeni_no = int(no) if no else max(k["maddeler"] | {0}) + 1
    hatalar = []

    def denetle(etiket, harf, istenen, gecerli, kaynak):
        yok = [n for n in istenen if n not in gecerli]
        if yok:
            aralik = ", ".join(f"{harf}{n}" for n in sorted(gecerli)) or "yok"
            hatalar.append(f"{etiket}: {', '.join(f'{harf}{n}' for n in yok)} {kaynak} içinde yok (geçerli: {aralik})")

    denetle("--gap", "G", gap_n, set(k["gaplar"]), f"mevcut durum §{k['gap_bolum']}")
    denetle("--soz", "S", soz_n, k["kriterler"], "sözleşme `## Başarı kriterleri`")
    denetle("--iddia", "C", iddia_n, k["iddialar"], "plan.md iddiaları")
    denetle("--onceki", "P", once_n, k["maddeler"], "plan.md maddeleri")
    if yeni_no in k["maddeler"]:
        hatalar.append(f"P{yeni_no} plan.md'de zaten var")
    if yeni_no in once_n:
        hatalar.append(f"--onceki: P{yeni_no} kendine başvuruyor")
    if k["gapli"] and not gap_n:
        hatalar.append(f"--gap zorunlu: mevcut durum §{k['gap_bolum']}'te gap var (P-017)")
    if k["sozlesmeli"] and k["kriterler"] and not soz_n:
        hatalar.append("--soz zorunlu: iş sözleşmeli (her P bir S kriterine bağlanır)")
    if once_tur not in ("Çıktı", "Çakışma"):
        hatalar.append(f"--once-tur: '{once_tur}' geçersiz (Çıktı | Çakışma)")
    yazma_l = [y.strip().strip("`") for y in re.split(r"[,;]", yazma or "") if y.strip().strip("`")]
    if hatalar:
        raise ValueError("; ".join(hatalar))

    deger: dict[str, str] = {}
    turetilen: list[str] = []
    if gap_n:
        deger["Gap"] = ", ".join(f"G{n}" for n in gap_n)
        deger["Dayanak"] = dayanak_turet(k["gaplar"], gap_n, dayanak_ek, k["gap_bolum"])
        turetilen += ["Gap", "Dayanak"]
    if soz_n:
        deger["Sözleşme"] = ", ".join(f"S{n}" for n in soz_n)
        turetilen.append("Sözleşme")
    if iddia_n:
        deger["İddialar"] = ", ".join(f"C{n}" for n in iddia_n)
        turetilen.append("İddialar")
    elle_ek: list[str] = []
    if onceki is not None:
        deger["Önce"] = ", ".join(f"P{n} — {once_tur}: {DOLDUR}" for n in once_n) if once_n else "yok"
        turetilen.append("Önce")
        if once_n:
            elle_ek.append("Önce gerekçesi")
    if yazma_l:
        deger["Yazma alanı"] = ", ".join(f"`{y}`" for y in yazma_l)
        turetilen.append("Yazma alanı")

    sira = [a for a in is_kaydi.plan_alan_sirasi(klasor) if a != "Kapatır"]
    if not sira:
        sira = ["Ne", "Dayanak", "Dokunulan yer", "Kabul", "Geri alma", "Önce", "Gap", "Sözleşme", "Mevcut varlık",
                "Alternatifler", "Üretim noktası"]
    if "Yazma alanı" not in sira and ("Yazma alanı" in deger or k["paralel"]):
        sira.insert(sira.index("Önce") + 1 if "Önce" in sira else len(sira), "Yazma alanı")
    if "İddialar" not in sira and ("İddialar" in deger or k["iddialar"]):
        sira.insert(sira.index("Gap") + 1 if "Gap" in sira else len(sira), "İddialar")
    if not k["sozlesmeli"] and "Sözleşme" not in deger and "Sözleşme" in sira:
        sira.remove("Sözleşme")

    simdi = simdi or datetime.datetime.now()
    damga = simdi.strftime("%d.%m.%Y %H:%M")
    satirlar = [f"### P{yeni_no} {baslik.strip() if baslik and baslik.strip() else DOLDUR}", "",
                f"<!-- orkestra plan alan · {damga} -->", ""]
    elle: list[str] = [] if baslik and baslik.strip() else ["Başlık"]
    for alan in sira:
        if alan in deger:
            satirlar += [f"**{alan}:** {deger[alan]}", ""]
        else:
            satirlar += [f"**{alan}:** {DOLDUR}", ""]
            elle.append(alan)
    blok = "\n".join(satirlar).rstrip() + "\n"
    return {"no": yeni_no, "blok": blok, "turetilen": turetilen + ["saat damgası"], "elle": elle + elle_ek,
            "saat": damga, "tutarsizlik": zincir_tutarsizliklari(klasor, blok, k)}


def zincir_tutarsizliklari(klasor: str, blok: str, k: dict | None = None) -> list[str]:
    """Blokta zincir alanları iş belgeleriyle tutarlı mı: Gap ⊆ MD gap bölümü, Sözleşme ⊆ S, İddialar ⊆ C, Önce ⊆ P,
    Dayanak MD bölümü geçerli ve seçilen G'lerin andığı bölümü içeriyor. Boş liste = tutarlı."""
    import is_sirasi as SIRA
    k = k or kaynaklar(klasor)
    sorun = []

    def alan(ad):
        return SIRA._alan_degeri(blok, ad)

    def kume(ad, harf):
        return {int(x) for x in re.findall(rf"\b{harf}(\d+)\b", alan(ad))}

    g = kume("Gap", "G")
    for ad, harf, gecerli in (("Gap", "G", set(k["gaplar"])), ("Sözleşme", "S", k["kriterler"]),
                              ("İddialar", "C", k["iddialar"]), ("Önce", "P", k["maddeler"])):
        for n in sorted(kume(ad, harf) - gecerli):
            sorun.append(f"{ad}: {harf}{n} kaynakta yok")
    bolumler = {int(x) for x in _MD_ANMA.findall(alan("Dayanak"))}
    if not bolumler or not any(1 <= b <= k["gap_bolum"] for b in bolumler):
        sorun.append("Dayanak: geçerli MD §k yok")
    beklenen = {int(x) for n in g for x in _MD_ANMA.findall(k["gaplar"].get(n, ""))}
    if beklenen - bolumler:
        sorun.append(f"Dayanak: G satırlarının andığı MD §{', §'.join(str(b) for b in sorted(beklenen - bolumler))} yok")
    return sorun


def cmd_plan_alan(a):
    try:
        klasor = _klasor_bul(a.hedef)
        s = iskelet(klasor, a.gap, a.soz, a.iddia, a.onceki, a.yazma, a.baslik, a.dayanak_ek or "", a.no, a.once_tur)
        if a.yaz:
            import is_kaydi
            s["yol"] = is_kaydi.plan_madde_ekle(klasor, s["no"], s["blok"])
    except ValueError as e:
        hata(str(e))
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        print(s["blok"])
        print("türetilen: " + ", ".join(s["turetilen"]))
        print("elle kalan: " + (", ".join(s["elle"]) or "yok"))
        print(f"zincir tutarsızlığı: {len(s['tutarsizlik'])}")
        for t in s["tutarsizlik"]:
            print(f"  - {t}")
        if a.yaz:
            print(f"yazıldı: {s['yol']} (P{s['no']})")
    sys.exit(1 if s["tutarsizlik"] else 0)


def kaydet(alt):
    """`plan` alt komut grubuna `alan` ekler (grup komutlar/plan.py'de açılır; bu modül ondan sonra kaydedilir)."""
    import argparse
    plan = alt.choices["plan"]
    grup = next(x for x in plan._actions if isinstance(x, argparse._SubParsersAction))
    p = grup.add_parser("alan", help="P maddesi iskeleti: Gap/Sözleşme/Dayanak/İddialar/Önce/Yazma alanı zincirini iş belgelerinden doğrulayıp türetir")
    p.add_argument("hedef", help="iş kimliği (I-nnn) ya da iş klasörü")
    p.add_argument("--gap", help="G numaraları (G3 ya da G3,G4); gap'li işte zorunlu")
    p.add_argument("--soz", help="S numaraları (S3,S4); sözleşmeli işte zorunlu")
    p.add_argument("--iddia", help="C numaraları (C5)")
    p.add_argument("--onceki", help="önce bitmesi gereken P'ler (P2,P3; 'yok' için boş ver: --onceki \"\")")
    p.add_argument("--once-tur", dest="once_tur", default="Çıktı", help="Önce bağımlılık türü: Çıktı (varsayılan) | Çakışma")
    p.add_argument("--yazma", help="yazma alanı: virgülle dosya/glob listesi")
    p.add_argument("--baslik", help="P başlığı (yoksa <doldur>)")
    p.add_argument("--dayanak-ek", dest="dayanak_ek", help="Dayanak'a eklenecek ayrıntı (örn. R1)")
    p.add_argument("--no", type=int, help="P numarası (varsayılan: en büyük + 1)")
    p.add_argument("--yaz", action="store_true", help="iskeleti plan.md §4 sonuna ekler")
    p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_plan_alan)
