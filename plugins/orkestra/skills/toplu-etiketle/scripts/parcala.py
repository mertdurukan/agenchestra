# -*- coding: utf-8 -*-
"""Toplu etiketleme, adım 1 (T0): veriyi T1 işçilerine verilecek parçalara böler.

Kullanım:
  python -X utf8 -I parcala.py --girdi veri.csv --id-sutun RID \
      --sutunlar "Firma,Alan,Ozellik" --kurallar kurallar.md --etiketler etiketler.txt \
      --klasor <çalışma klasörü>/<konu>_<YYYYMMDD>/etiket \
      [--parca-boyutu 230 | --parca-sayisi 4] [--maks-uzunluk 300]

Girdi: CSV (ayraç otomatik), JSON nesne listesi ya da xlsx (--sayfa, --baslik-satiri).
Kimlik sütunu tekil ve dolu olmalı; kimliksiz satırlar (ara başlık, toplam) önceden ayıklanmalı.
Çıktılar (--klasor altında):
  parca_01.txt …     ilk satır "# alanlar: id|...", sonra "id|alan1|alan2" satırları (| ve satır sonu temizlenir)
  manifest.json      kaynak, kimlik sütunu, parça → kimlik listesi, izinli etiketler, beklenen çıktı adları
  plan.json          `orkestra kart toplu --json-dosya` için kartlar: parça başına T1 + birleştirme/örneklem T0
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import sys

GUVEN = ["Yüksek", "Orta", "Düşük"]
CIKTI_BASLIK = ["id", "etiket", "guven", "gerekce"]


def oku(yol, sayfa=None, baslik_satiri=1):
    uz = os.path.splitext(yol)[1].lower()
    if uz in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(yol, read_only=True, data_only=True)
        ws = wb[sayfa] if sayfa else wb.worksheets[0]
        it = ws.iter_rows(min_row=baslik_satiri, values_only=True)
        kol = [("" if c is None else str(c)).strip() for c in next(it)]
        while kol and not kol[-1]:
            kol.pop()
        satirlar = []
        for r in it:
            r = list(r[:len(kol)]) + [None] * (len(kol) - len(r))
            if any(v not in (None, "") for v in r):
                satirlar.append({k: ("" if v is None else str(v)) for k, v in zip(kol, r) if k})
        wb.close()
        return [k for k in kol if k], satirlar
    if uz == ".json":
        with open(yol, encoding="utf-8-sig") as f:
            veri = json.load(f)
        if isinstance(veri, dict):
            veri = veri.get("satirlar", veri.get("rows"))
        kol = []
        for x in veri:
            for k in x:
                if k not in kol:
                    kol.append(k)
        return kol, [{k: ("" if x.get(k) is None else str(x.get(k))) for k in kol} for x in veri]
    with open(yol, encoding="utf-8-sig", newline="") as f:
        metin = f.read()
    try:
        lehce = csv.Sniffer().sniff(metin[:20000], delimiters=",;|\t")
    except csv.Error:
        lehce = csv.excel
    r = csv.DictReader(io.StringIO(metin, newline=""), dialect=lehce)
    return list(r.fieldnames or []), [x for x in r if any((v or "").strip() for v in x.values())]


def temiz(v, maks):
    s = " ".join(str(v or "").replace("|", "/").split())
    return s if len(s) <= maks else s[: maks - 1] + "…"


def etiket_listesi(yol):
    with open(yol, encoding="utf-8-sig") as f:
        et = [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
    # "etiket — açıklama" biçimine izin ver; etiket ilk alandır
    et = [e.split(" — ")[0].split("\t")[0].strip() for e in et]
    if len(set(et)) != len(et):
        sys.exit("HATA: etiket listesinde tekrar var")
    return et


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--girdi", required=True)
    ap.add_argument("--id-sutun", required=True)
    ap.add_argument("--sutunlar", required=True, help="işçiye gösterilecek alanlar, virgülle")
    ap.add_argument("--kurallar", required=True, help="T3'ün yazdığı kural dosyası (md)")
    ap.add_argument("--etiketler", required=True, help="satır başına bir izinli etiket")
    ap.add_argument("--klasor", required=True)
    ap.add_argument("--sayfa", help="xlsx girdide sayfa adı (varsayılan ilk sayfa)")
    ap.add_argument("--baslik-satiri", type=int, default=1, help="xlsx girdide başlık satırı (1'den)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--parca-boyutu", type=int, default=230)
    g.add_argument("--parca-sayisi", type=int)
    ap.add_argument("--maks-uzunluk", type=int, default=300, help="alan başına karakter sınırı")
    ap.add_argument("--proje", default=os.getcwd(), help="yazma alanı globları bu köke göre göreli yazılır (varsayılan: çalışma klasörü)")
    ap.add_argument("--orneklem", type=int, default=30, help="denetçi örneklem büyüklüğü")
    ap.add_argument("--esik", type=int, default=5, help="örneklemde kabul edilen en yüksek yanlış oranı (%)")
    a = ap.parse_args()

    for y in (a.girdi, a.kurallar, a.etiketler):
        if not os.path.isfile(y):
            sys.exit(f"HATA: dosya yok: {y}")
    kol, satirlar = oku(a.girdi, a.sayfa, a.baslik_satiri)
    alanlar = [s.strip() for s in a.sutunlar.split(",") if s.strip()]
    eksik = [s for s in [a.id_sutun] + alanlar if s not in kol]
    if eksik:
        sys.exit(f"HATA: sütun yok: {eksik}. Var olanlar: {kol}")
    ids = [str(x[a.id_sutun]).strip() for x in satirlar]
    if any(not i for i in ids):
        sys.exit("HATA: boş kimlik var")
    tekrar = sorted({i for i in ids if ids.count(i) > 1})
    if tekrar:
        sys.exit(f"HATA: tekrarlayan kimlik: {tekrar[:10]}")
    etiketler = etiket_listesi(a.etiketler)
    if len(etiketler) < 2:
        sys.exit("HATA: en az 2 izinli etiket gerekli")

    n = len(satirlar)
    k = a.parca_sayisi or max(1, math.ceil(n / a.parca_boyutu))
    boy = math.ceil(n / k)
    os.makedirs(a.klasor, exist_ok=True)
    parcalar = []
    for p in range(k):
        dilim = satirlar[p * boy:(p + 1) * boy]
        if not dilim:
            continue
        no = len(parcalar) + 1
        ad = f"parca_{no:02d}.txt"
        with open(os.path.join(a.klasor, ad), "w", encoding="utf-8", newline="\n") as f:
            f.write("# alanlar: " + "|".join(["id"] + alanlar) + "\n")
            for x in dilim:
                f.write("|".join([str(x[a.id_sutun]).strip()] + [temiz(x[c], a.maks_uzunluk) for c in alanlar]) + "\n")
        parcalar.append({"no": no, "parca": ad, "cikti": f"etiket_{no:02d}.csv",
                         "idler": [str(x[a.id_sutun]).strip() for x in dilim]})

    with open(a.girdi, "rb") as f:
        ozet = hashlib.sha256(f.read()).hexdigest()[:16]
    manifest = {"kaynak": os.path.abspath(a.girdi), "kaynak_sha256_16": ozet, "id_sutun": a.id_sutun,
                "sayfa": a.sayfa, "baslik_satiri": a.baslik_satiri,
                "alanlar": alanlar, "kurallar": os.path.abspath(a.kurallar), "etiketler": etiketler,
                "guven": GUVEN, "cikti_baslik": CIKTI_BASLIK, "toplam": n, "parcalar": parcalar}
    with open(os.path.join(a.klasor, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    klasor = os.path.abspath(a.klasor)
    proje = os.path.abspath(a.proje)

    def rel(yol):  # orkestra yazma alanı proje köküne göre göreli glob ister
        r = os.path.relpath(os.path.abspath(yol), proje).replace("\\", "/")
        return r if not r.startswith("..") else os.path.abspath(yol).replace("\\", "/")

    betik = rel(os.path.join(os.path.dirname(os.path.abspath(__file__)), "birlestir.py"))
    kartlar = []
    for p in parcalar:
        kartlar.append({
            "ref": f"parca{p['no']:02d}", "baslik": f"Toplu etiketle: parça {p['no']:02d}/{len(parcalar)} ({len(p['idler'])} satır)",
            "sinif": "toplu-etiketle", "basamak": "T1",
            "girdi": (f"Parça: {rel(os.path.join(klasor, p['parca']))} · Kurallar: {rel(a.kurallar)} · "
                      f"İzinli etiketler: {rel(a.etiketler)}. Her satıra kurallara göre TEK etiket ver; "
                      f"çıktıyı {rel(os.path.join(klasor, p['cikti']))} olarak yaz (UTF-8 CSV, virgül ayraç)."),
            "yazma_alani": [rel(os.path.join(klasor, p["cikti"]))],
            "bagimliliklar": [],
            "kabul_kriterleri": [
                f"{p['cikti']} başlığı tam olarak: {','.join(CIKTI_BASLIK)}",
                f"{len(p['idler'])} veri satırı; {p['parca']} içindeki her id tam bir kez, başka id yok",
                "etiket yalnız izinli listeden; hiçbir kurala uymayan satırda en yakın etiket + guven=Düşük",
                f"guven yalnız {'/'.join(GUVEN)}; gerekce ≤ 15 kelime ve dayandığı kural numarasını verir",
                "başka dosyaya yazılmaz; parça ve kural dosyası değiştirilmez"],
        })
    kartlar.append({
        "ref": "birlestir", "baslik": f"Toplu etiketle: birleştir, say ve örneklemi denetle ({n} satır)",
        "sinif": "toplu-etiketle", "basamak": "T0",
        "girdi": (f"T0 betik: python -X utf8 -I {betik} --klasor {rel(klasor)} --orneklem {a.orneklem}. "
                  f"Kurallar: {rel(a.kurallar)}. Betik çıkış kodu 2 verirse denetim_sayim.json'daki "
                  "yeniden_kosulacak_parcalar listesini raporla, elle düzeltme yapma."),
        "yazma_alani": [rel(os.path.join(klasor, f)) for f in ("birlesik.csv", "orneklem.csv", "denetim_sayim.json")],
        "bagimliliklar": [k["ref"] for k in kartlar],
        "kabul_kriterleri": [
            f"birlestir.py çıkış kodu 0 ve 'TUTARLI: {n}/{n}' satırı (komut çıktısı kanıt)",
            f"birlesik.csv {n} veri satırı; etiket dağılımı denetim_sayim.json ile aynı",
            f"DENETÇİ: orneklem.csv'nin her satırını {rel(a.kurallar)} kurallarına karşı kendisi kontrol eder; "
            f"yanlış etiket oranı ≤ %{a.esik}; yanlışlar bulgularda id + doğru etiket + kural no ile yazılır",
            "işçi Düşük güvenli satır oranını raporlar; oran %30'u aşıyorsa 'kural boşluğu' diye işaretler"],
    })
    with open(os.path.join(a.klasor, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(kartlar, f, ensure_ascii=False, indent=1)

    print(f"{n} satır -> {len(parcalar)} parça ({', '.join(str(len(p['idler'])) for p in parcalar)}); "
          f"{len(etiketler)} etiket; klasör: {klasor}")


if __name__ == "__main__":
    main()
