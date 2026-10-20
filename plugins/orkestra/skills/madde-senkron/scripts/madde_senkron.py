"""madde_senkron.py — aynı madde kimliğini taşıyan kanonik belgeleri birlikte, güvenli biçimde günceller.

plan1\\scriptler\\integrate.py ve plan2_I\\integrate_I.py kalıbının genelleştirilmiş hali:
yedek al · her değişiklik birebir eşleşmeyle · eşleşme yoksa (ya da birden fazlaysa) HİÇBİR ŞEY yazmadan dur.

Alt komutlar:
  tara    <KIMLIK...> [--aile AD]       kimliğin geçtiği belge:satırları (aile belgelerinde) listeler
  uygula  <plan.json> [--kuru]          planı doğrular; --kuru: yalnız fark gösterir; değilse yedek + yaz + kayıt
  dogrula <kayit.json>                  denetçi içindir: yedeğe planı yeniden uygulayıp bugünkü dosyayla karşılaştırır
  geri-al <kayit.json>                  dosyalar kayıttaki "sonra" hâlindeyse yedekten geri yükler

plan.json:
{
  "aciklama": "A7: canlı portal teyidi eklendi",          (zorunlu, tek satır)
  "aile": "oneriler_12",                                   (belgeler.json'daki aile)
  "kimlikler": ["A7"],
  "islemler": [
    {"belge": "belgeler/x.md", "tur": "degistir", "eski": "…", "yeni": "…", "adet": 1},
    {"belge": "belgeler/referans.md", "tur": "isaretci_once", "isaretci": "<!-- G -->", "metin": "…"},
    {"belge": "belgeler/y.md", "tur": "bolum_sonuna", "baslik": "### 12.7 Öneri kesinleşmeden önce bekleyen teyitler", "metin": "- …"}
  ],
  "atlanan": {"belgeler/z.md": "neden bu belge değişmiyor"}
}
Çıkış kodları: 0 tamam · 1 doğrulama başarısız · 2 eşleşme/kapsam/sır kapısı durdurdu · 3 kullanım/yol hatası
"""
import argparse, datetime as dt, difflib, hashlib, io, json, os, re, shutil, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BURASI = os.path.dirname(os.path.abspath(__file__))
VARSAYILAN_PROJE = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
sys.path.insert(0, os.path.join(BURASI, "..", "..", "arsivle", "scripts"))
try:
    import arsivle as _ars  # sır kalıpları tek yerde
except Exception:  # pragma: no cover
    _ars = None
YASAK_AD = re.compile(r"(?i)(^|[\\/])(db\.py|\.env[^\\/]*|[^\\/]*\.(pem|key|pfx|p12))$")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def yukle(yol):
    ham = open(yol, "rb").read()
    bom = ham.startswith(b"\xef\xbb\xbf")
    t = ham.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in t else "\n"
    return t.replace("\r\n", "\n"), bom, nl, ham


def baytlar(metin, bom, nl):
    return (b"\xef\xbb\xbf" if bom else b"") + metin.replace("\n", nl).encode("utf-8")


def kimlik_rx(k):
    return re.compile(rf"(?<![A-Za-z0-9_\-]){re.escape(k)}(?![0-9A-Za-z])")


def proje_yolu(proje, g):
    tam = os.path.abspath(g if os.path.isabs(g) else os.path.join(proje, g))
    p = os.path.normcase(os.path.abspath(proje))
    if not os.path.normcase(tam).startswith(p.rstrip("\\/") + os.sep):
        raise SystemExit(f"YOL HATASI: proje dışında: {g}")
    if YASAK_AD.search(tam):
        raise SystemExit(f"YOL HATASI: kimlik/bağlantı dosyasına dokunulmaz: {g}")
    return tam


def aileler(yol=None):
    return json.load(open(yol, encoding="utf-8"))


# ------------------------------------------------------------------ işlemler
def islem_uygula(metin, op):
    """Tek işlemi uygular. Hata -> ValueError (mesaj Türkçe)."""
    tur = op.get("tur")
    if tur == "degistir":
        eski, yeni, adet = op["eski"], op["yeni"], int(op.get("adet", 1))
        if not eski or eski == yeni:
            raise ValueError("degistir: 'eski' boş ya da 'yeni' ile aynı")
        n = metin.count(eski)
        if n != adet:
            raise ValueError(f"ESLESME HATASI ({n} != {adet}): {eski[:90]!r}")
        return metin.replace(eski, yeni)
    if tur == "isaretci_once":
        isr, ek = op["isaretci"], op["metin"]
        n = metin.count(isr)
        if n != 1:
            raise ValueError(f"ISARETCI HATASI ({n} != 1): {isr!r}")
        return metin.replace(isr, ek.strip("\n") + "\n\n" + isr, 1)
    if tur == "bolum_sonuna":
        baslik, ek = op["baslik"].strip(), op["metin"].strip("\n")
        satirlar = metin.split("\n")
        idx = [i for i, s in enumerate(satirlar) if s.strip() == baslik]
        if len(idx) != 1:
            raise ValueError(f"BASLIK HATASI ({len(idx)} != 1): {baslik!r}")
        m = re.match(r"^(#+)\s", baslik)
        if not m:
            raise ValueError(f"baslik bir Markdown başlığı olmalı: {baslik!r}")
        seviye, i, fence = len(m.group(1)), idx[0] + 1, False
        son = len(satirlar)
        for j in range(i, len(satirlar)):
            if satirlar[j].lstrip().startswith("```"):
                fence = not fence
            h = re.match(r"^(#+)\s", satirlar[j])
            if not fence and h and len(h.group(1)) <= seviye:
                son = j
                break
        k = son
        while k > i and satirlar[k - 1].strip() in ("", "---"):
            k -= 1
        satirlar[k:k] = ek.split("\n")
        return "\n".join(satirlar)
    raise ValueError(f"bilinmeyen tur: {tur!r} (degistir | isaretci_once | bolum_sonuna)")


def eklenen_metin(op):
    return op.get("yeni") or op.get("metin") or ""


def plan_yukle(yol):
    plan = json.load(open(yol, encoding="utf-8"))
    for alan in ("aciklama", "islemler"):
        if not plan.get(alan):
            raise SystemExit(f"PLAN HATASI: '{alan}' zorunlu")
    if "\n" in plan["aciklama"]:
        raise SystemExit("PLAN HATASI: aciklama tek satır olmalı")
    return plan


def planla(plan, proje, belgeler_yolu=None):
    """Bellekte uygular. -> (durum{belge: dict}, hatalar[], uyarilar[])"""
    hatalar, uyarilar, durum = [], [], {}
    for n, op in enumerate(plan["islemler"], 1):
        g = op.get("belge", "")
        try:
            tam = proje_yolu(proje, g)
        except SystemExit as e:
            hatalar.append(f"işlem {n}: {e}")
            continue
        if not os.path.exists(tam):
            hatalar.append(f"işlem {n}: belge yok: {g}")
            continue
        if g not in durum:
            t, bom, nl, ham = yukle(tam)
            durum[g] = {"tam": tam, "once": t, "sonra": t, "bom": bom, "nl": nl, "sha_once": sha(ham), "islem": []}
        try:
            durum[g]["sonra"] = islem_uygula(durum[g]["sonra"], op)
            durum[g]["islem"].append(n)
        except (ValueError, KeyError) as e:
            hatalar.append(f"işlem {n} ({g}): {e}")
        # sır / e-posta kapısı: eklenen metin
        ek = eklenen_metin(op)
        if _ars:
            d, _ = _ars.metni_tara(ek, _ars.ortam_sirlari())
            if d:
                hatalar.append(f"işlem {n}: eklenen metinde sır kalıbı ({', '.join(sorted({x[0] for x in d}))}) — değer yazılmaz")
            if any(not _ars.GORMEZDEN.search(m.group(0)) for m in _ars.EPOSTA.finditer(ek)):
                hatalar.append(f"işlem {n}: eklenen metinde e-posta var; maskele (<e-posta>)")
        else:
            uyarilar.append("arsivle.py bulunamadı: sır kapısı çalışmadı")
    # kapsam kapısı
    aile_ad = plan.get("aile")
    if plan.get("kimlikler"):
        if not aile_ad:
            hatalar.append("kimlikler verildi ama 'aile' yok (belgeler.json'daki ailelerden biri)")
        else:
            A = aileler(belgeler_yolu)
            if aile_ad not in A:
                hatalar.append(f"bilinmeyen aile: {aile_ad} (var olanlar: {', '.join(k for k in A if not k.startswith('_'))})")
            else:
                aile = A[aile_ad]
                for k in plan["kimlikler"]:
                    if not re.match(aile["kalip"], k):
                        hatalar.append(f"kimlik {k} '{aile_ad}' ailesinin kalıbına uymuyor ({aile['kalip']})")
                    if not any(kimlik_rx(k).search(eklenen_metin(op) + op.get("eski", "")) for op in plan["islemler"]):
                        uyarilar.append(f"kimlik {k} hiçbir işlemin metninde geçmiyor")
                for tur, liste in (("zorunlu", aile.get("zorunlu", [])), ("izle", aile.get("izle", []))):
                    for g in liste:
                        tam = os.path.join(proje, g)
                        if not os.path.exists(tam):
                            (hatalar if tur == "zorunlu" and g not in plan.get("atlanan", {}) else uyarilar).append(
                                f"{tur} belge YOK: {g}" + ("" if tur == "izle" else " (taşınmış olabilir; 'atlanan'a gerekçeyle yaz ya da belgeyi yerine koy)"))
                            continue
                        metin = yukle(tam)[0]
                        gecen = [k for k in plan["kimlikler"] if kimlik_rx(k).search(metin)]
                        if gecen and g not in durum and g not in plan.get("atlanan", {}):
                            msg = f"KAPSAM: {', '.join(gecen)} '{g}' içinde geçiyor ama planda işlem ya da 'atlanan' gerekçesi yok"
                            (hatalar if tur == "zorunlu" else uyarilar).append(msg)
    return durum, hatalar, uyarilar


def fark_yazdir(durum, sinir=120):
    for g, d in durum.items():
        if d["once"] == d["sonra"]:
            continue
        satir = list(difflib.unified_diff(d["once"].split("\n"), d["sonra"].split("\n"), f"a/{g}", f"b/{g}", n=1, lineterm=""))
        print("\n".join(s[:300] for s in satir[:sinir]))
        if len(satir) > sinir:
            print(f"… {len(satir) - sinir} fark satırı daha")


# ------------------------------------------------------------------ alt komutlar
def k_tara(a):
    A = aileler(a.belgeler)
    adaylar = [a.aile] if a.aile else [k for k in A if not k.startswith("_")]
    for ad in adaylar:
        aile = A[ad]
        kimlikler = [k for k in a.kimlik if re.match(aile["kalip"], k)]
        if not kimlikler:
            continue
        print(f"== aile {ad} ({', '.join(kimlikler)})")
        for tur in ("zorunlu", "izle"):
            for g in aile.get(tur, []):
                tam = os.path.join(a.proje, g)
                if not os.path.exists(tam):
                    print(f"  [{tur}] {g}: YOK")
                    continue
                satirlar = yukle(tam)[0].split("\n")
                bulgu = [(i, s) for i, s in enumerate(satirlar, 1) if any(kimlik_rx(k).search(s) for k in kimlikler)]
                print(f"  [{tur}] {g}: {len(bulgu)} satır")
                for i, s in bulgu[: a.sinir]:
                    print(f"      {i}: {s.strip()[:160]}")
                if len(bulgu) > a.sinir:
                    print(f"      … {len(bulgu) - a.sinir} satır daha")


def k_uygula(a):
    plan = plan_yukle(a.plan)
    durum, hatalar, uyarilar = planla(plan, a.proje, a.belgeler)
    for u in uyarilar:
        print("UYARI:", u)
    if hatalar:
        print("DURDU — hiçbir dosya yazılmadı:")
        for h in hatalar:
            print("  -", h)
        sys.exit(2)
    degisen = {g: d for g, d in durum.items() if d["once"] != d["sonra"]}
    print(f"plan geçerli: {len(plan['islemler'])} işlem, {len(degisen)} belge değişecek")
    fark_yazdir(degisen)
    if a.kuru:
        print("KURU MOD: hiçbir şey yazılmadı.")
        return
    # yeniden oku: plan sırasında başka oturum yazdıysa dur
    for g, d in degisen.items():
        if sha(open(d["tam"], "rb").read()) != d["sha_once"]:
            print(f"DURDU: {g} okunduktan sonra değişti (paralel yazım). Yeniden çalıştır.")
            sys.exit(2)
    zaman = dt.datetime.now()
    yedek_kok = a.yedek_kok or os.path.join(a.proje, ".claude", "madde_senkron", "yedek", f"madde_senkron_{zaman:%Y%m%d}")
    yedek = os.path.join(yedek_kok, f"{zaman:%H%M%S}")
    os.makedirs(yedek, exist_ok=False)
    kayit = {"zaman": zaman.isoformat(timespec="seconds"), "aciklama": plan["aciklama"], "aile": plan.get("aile"),
             "kimlikler": plan.get("kimlikler", []), "plan": "plan.json", "belgeler": {}}
    for g, d in degisen.items():
        hedef = os.path.join(yedek, g.replace("/", os.sep))
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        shutil.copy2(d["tam"], hedef)
    for g, d in degisen.items():
        b = baytlar(d["sonra"], d["bom"], d["nl"])
        open(d["tam"], "wb").write(b)
        kayit["belgeler"][g] = {"sha_once": d["sha_once"], "sha_sonra": sha(b), "yedek": os.path.relpath(
            os.path.join(yedek, g.replace("/", os.sep)), yedek), "islemler": d["islem"]}
    json.dump(plan, open(os.path.join(yedek, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    kayit_yolu = os.path.join(yedek, "kayit.json")
    json.dump(kayit, open(kayit_yolu, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"YAZILDI: {len(degisen)} belge. Yedek ve kayıt: {kayit_yolu}")
    print(f"Denetim: python \"{os.path.abspath(__file__)}\" --proje \"{a.proje}\" dogrula \"{kayit_yolu}\"")


def k_dogrula(a):
    kayit = json.load(open(a.kayit, encoding="utf-8"))
    yedek = os.path.dirname(os.path.abspath(a.kayit))
    plan = plan_yukle(os.path.join(yedek, kayit["plan"]))
    sorun = []
    # 1) yedeğe planı yeniden uygula -> bugünkü dosyayla aynı mı
    yeniden = {}
    for n, op in enumerate(plan["islemler"], 1):
        g = op["belge"]
        if g not in kayit["belgeler"]:
            continue
        if g not in yeniden:
            yeniden[g] = list(yukle(os.path.join(yedek, kayit["belgeler"][g]["yedek"]))[:3])
        try:
            yeniden[g][0] = islem_uygula(yeniden[g][0], op)
        except ValueError as e:
            sorun.append(f"{g}: yedeğe işlem {n} uygulanamadı: {e}")
    for g, b in kayit["belgeler"].items():
        tam = os.path.join(a.proje, g)
        yb = open(os.path.join(yedek, b["yedek"]), "rb").read()
        bugun = open(tam, "rb").read() if os.path.exists(tam) else b""
        sat = []
        sat.append(("yedek = önceki hâl", sha(yb) == b["sha_once"]))
        sat.append(("dosya = kayıttaki sonraki hâl", sha(bugun) == b["sha_sonra"]))
        if g in yeniden:
            t, bom, nl = yeniden[g]
            sat.append(("yedek + plan = dosya (plan dışı değişiklik yok)", sha(baytlar(t, bom, nl)) == b["sha_sonra"]))
        for ad, ok in sat:
            print(f"  [{'TAMAM' if ok else 'HATA '}] {g}: {ad}")
            if not ok:
                sorun.append(f"{g}: {ad}")
    # 2) kapsam ve sır kapısını yedek üzerinde yeniden çalıştır
    _, hatalar, uyarilar = planla_yedekte(plan, yedek, kayit, a)
    for u in uyarilar:
        print("  UYARI:", u)
    sorun += hatalar
    print("SONUÇ:", "GEÇTİ" if not sorun else "KALDI")
    for s in sorun:
        print("  -", s)
    sys.exit(1 if sorun else 0)


def planla_yedekte(plan, yedek, kayit, a):
    """Kapsam/sır kapısını değişiklikten önceki hâle göre yeniden değerlendirir (yedek + değişmeyen belgeler)."""
    gecici = dict(plan)
    hatalar, uyarilar = [], []
    # değişen belgeler için yedekteki önceki hâli kullan: planla() dosyadan okur; bu yüzden kapsamı ayrıca hesapla
    if plan.get("kimlikler") and plan.get("aile"):
        aile = aileler(a.belgeler).get(plan["aile"], {})
        for g in aile.get("zorunlu", []):
            if g in kayit["belgeler"] or g in plan.get("atlanan", {}):
                continue
            tam = os.path.join(a.proje, g)
            if not os.path.exists(tam):
                hatalar.append(f"zorunlu belge YOK ve 'atlanan'da değil: {g}")
                continue
            metin = yukle(tam)[0]
            gecen = [k for k in plan["kimlikler"] if kimlik_rx(k).search(metin)]
            if gecen:
                hatalar.append(f"KAPSAM: {', '.join(gecen)} '{g}' içinde geçiyor ama değişmedi ve gerekçe yok")
    if _ars:
        for n, op in enumerate(gecici["islemler"], 1):
            d, _ = _ars.metni_tara(eklenen_metin(op), _ars.ortam_sirlari())
            if d:
                hatalar.append(f"işlem {n}: eklenen metinde sır kalıbı")
    for g, r in plan.get("atlanan", {}).items():
        if len(r.strip()) < 10:
            uyarilar.append(f"'atlanan' gerekçesi çok kısa: {g}")
    return None, hatalar, uyarilar


def k_geri_al(a):
    kayit = json.load(open(a.kayit, encoding="utf-8"))
    yedek = os.path.dirname(os.path.abspath(a.kayit))
    for g, b in kayit["belgeler"].items():
        tam = os.path.join(a.proje, g)
        if sha(open(tam, "rb").read()) != b["sha_sonra"]:
            print(f"DURDU: {g} senkrondan sonra yeniden değişmiş; elle bak (geri alma ezerdi).")
            sys.exit(2)
    for g, b in kayit["belgeler"].items():
        shutil.copy2(os.path.join(yedek, b["yedek"]), os.path.join(a.proje, g))
        print("geri alındı:", g)


def main():
    ap = argparse.ArgumentParser(description="Madde kimliği senkronu (yedekli, birebir eşleşmeli)")
    ap.add_argument("--proje", default=VARSAYILAN_PROJE)
    ap.add_argument("--belgeler", help="aile tanımı JSON (varsayılan: <proje>/.claude/madde_senkron/belgeler.json)")
    alt = ap.add_subparsers(dest="komut", required=True)
    t = alt.add_parser("tara"); t.add_argument("kimlik", nargs="+"); t.add_argument("--aile"); t.add_argument("--sinir", type=int, default=15)
    u = alt.add_parser("uygula"); u.add_argument("plan"); u.add_argument("--kuru", action="store_true"); u.add_argument("--yedek-kok")
    d = alt.add_parser("dogrula"); d.add_argument("kayit")
    g = alt.add_parser("geri-al"); g.add_argument("kayit")
    a = ap.parse_args()
    a.proje = os.path.abspath(a.proje)
    a.belgeler = a.belgeler or os.path.join(a.proje, ".claude", "madde_senkron", "belgeler.json")
    a.proje = os.path.abspath(a.proje)
    {"tara": k_tara, "uygula": k_uygula, "dogrula": k_dogrula, "geri-al": k_geri_al}[a.komut](a)


if __name__ == "__main__":
    main()
