"""close skill'inin mekanik tarafı: sohbet kaydını (jsonl) sıkıştırır ve açık-iş raporunu denetler.

Asıl kaynak eklentidir (plugins/orkestra/skills/close); test: tests/test_close_sohbet_cikar.py.

Kullanım:
  python -I sohbet_cikar.py cikar  --oturum <id> | --dosya <jsonl>  --cikti <girdi.json>
  python -I sohbet_cikar.py denetle <rapor.md> --girdi <girdi.json>
  python -I sohbet_cikar.py liste   <rapor.md>

`cikar` yalnız yerel kayıt dosyasını okur; ağ ve veritabanı yoktur. Karar (yapıldı/açık) vermez:
kullanıcı mesajlarını numaralar, aralarındaki yapılanları (dosya, komut, plan durumu) özetler.
`denetle` raporun her kullanıcı mesajını kapsayıp kapsamadığını, etiket, kanıt ve "Neden:" kurallarını,
sayımı ve YAPILDI satırlarındaki dosya yollarının varlığını mekanik olarak sınar.
`liste` raporun açık maddelerinden sohbette gösterilecek "iş — neden" listesini üretir (teslim biçimi
betikte sabittir; model listeyi yeniden yazmaz, aynen aktarır).
"""
import argparse
import glob
import json
import os
import re
import sys

ETIKETLER = ["YAPILDI", "KISMEN", "YAPILMADI", "KARAR BEKLİYOR", "ELENDİ", "CEVAPLANDI"]
ACIK = {"KISMEN", "YAPILMADI", "KARAR BEKLİYOR"}
KANIT_ISTER = {"YAPILDI", "ELENDİ", "CEVAPLANDI"}
NEDEN_ISTER = ACIK
NEDEN_EN_FAZLA = 240
IS_EN_FAZLA = 220
IKI_CUMLE = re.compile(r"[.!?]\s+[A-ZÇĞİÖŞÜ]")

SISTEM_ETIKET = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
SISTEM_BASLANGIC = ("<task-notification", "<side-sessions-event", "<ci-monitor-event",
                    "<local-command-stdout", "<local-command-caveat")
SISTEM_GOVDE = ("Base directory for this skill:", "This session is being continued")
KOMUT_AD = re.compile(r"<command-name>/?([^<\s]+)</command-name>")
KOMUT_ARG = re.compile(r"<command-args>(.*?)</command-args>", re.S)
KAPANIS_KOMUTU = re.compile(r"^(orkestra:)?close$")
KIRP_KULLANICI = 700
KIRP_YANIT = 300


def kayit_bul(oturum):
    yol = os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", oturum + ".jsonl")
    bulunan = glob.glob(yol)
    if not bulunan:
        sys.exit(f"HATA: {oturum}.jsonl bulunamadı ({yol})")
    return bulunan[0]


def metin_al(icerik):
    """Kullanıcı mesajının düz metni; yalnız araç sonucu ise None."""
    if isinstance(icerik, str):
        parcalar = [icerik]
    else:
        parcalar = [b.get("text", "") for b in icerik if isinstance(b, dict) and b.get("type") == "text"]
        if not parcalar:
            return None
    metin = SISTEM_ETIKET.sub("", "\n".join(parcalar)).strip()
    return metin or None


def sinifla(metin, meta=False):
    """(kaynak, metin): 'kullanici' ya da 'sistem'.

    Sistem: meta mesaj, skill gövdesi, bildirim blokları, argümansız slash komutu (/reload-plugins,
    /orkestra:close çağrısının kendisi). Argümanlı komut kullanıcı isteğidir ("/db-olcum Boyner"),
    close'un kendi çağrısı hariç.
    """
    if meta or metin.startswith(SISTEM_BASLANGIC + SISTEM_GOVDE):
        return "sistem", metin
    ad = KOMUT_AD.search(metin) if metin.startswith(("<command-message>", "<command-name>")) else None
    if ad:
        arg = KOMUT_ARG.search(metin)
        arg = arg.group(1).strip() if arg else ""
        if not arg or KAPANIS_KOMUTU.match(ad.group(1)):
            return "sistem", metin
        return "kullanici", f"/{ad.group(1)} {arg}"
    return "kullanici", metin


def kirp(s, n):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


class Plan:
    """update_plan çağrılarından son görev listesi durumunu yeniden kurar."""

    def __init__(self):
        self.maddeler = []

    def uygula(self, g):
        if "items" in g:
            self.maddeler = [{"icerik": m.get("content", ""), "durum": m.get("status", "pending")}
                             for m in g["items"]]
        if g.get("advance"):
            for m in self.maddeler:
                if m["durum"] == "in_progress":
                    m["durum"] = "completed"
                    break
            for m in self.maddeler:
                if m["durum"] == "pending":
                    m["durum"] = "in_progress"
                    break
        for i in g.get("done", []) or []:
            if 1 <= i <= len(self.maddeler):
                self.maddeler[i - 1]["durum"] = "completed"
        if g.get("start"):
            i = g["start"]
            if 1 <= i <= len(self.maddeler):
                self.maddeler[i - 1]["durum"] = "in_progress"


def cikar(dosya, cikti):
    satirlar = []
    with open(dosya, encoding="utf-8") as f:
        for l in f:
            try:
                satirlar.append(json.loads(l))
            except ValueError:
                continue

    turlar = []
    plan = Plan()
    mevcut = None

    def yeni_tur(metin, ts, kaynak):
        nonlocal mevcut
        mevcut = {"id": None, "zaman": ts, "kaynak": kaynak, "metin": kirp(metin, KIRP_KULLANICI),
                  "dosyalar": [], "komutlar": [], "araclar": {}, "hatalar": [], "oturumlar": [],
                  "beceriler": [], "ozet": [], "son_yanit": "", "asistan_sordu": False, "kapsam_disi": False}
        turlar.append(mevcut)

    for o in satirlar:
        if o.get("isSidechain"):
            continue
        t = o.get("type")
        m = o.get("message") if isinstance(o.get("message"), dict) else None
        if t == "attachment":
            # Tur sürerken gönderilen kullanıcı mesajı kayda böyle girer (queue-operation tekrar sayılmaz).
            ek = o.get("attachment") or {}
            kok = (ek.get("origin") or {}).get("kind", "")
            if ek.get("type") == "queued_command" and kok.startswith("hum") and ek.get("prompt"):
                metin = metin_al(ek["prompt"])
                if metin:
                    yeni_tur(metin, o.get("timestamp"), "kullanici")
            continue
        if t == "user" and m:
            c = m.get("content")
            metin = metin_al(c)
            if metin is None:
                for b in (c if isinstance(c, list) else []):
                    if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error") and mevcut:
                        ic = b.get("content")
                        ic = ic if isinstance(ic, str) else json.dumps(ic, ensure_ascii=False)
                        mevcut["hatalar"].append(kirp(ic, 140))
                continue
            kaynak, metin = sinifla(metin, bool(o.get("isMeta")))
            yeni_tur(metin, o.get("timestamp"), kaynak)
        elif t == "assistant" and m and mevcut is not None:
            for b in m.get("content", []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    mevcut["son_yanit"] = kirp(b["text"], KIRP_YANIT)
                    mevcut["asistan_sordu"] = b["text"].rstrip().endswith("?")
                elif b.get("type") == "tool_use":
                    ad, g = b.get("name", ""), b.get("input", {}) or {}
                    mevcut["araclar"][ad] = mevcut["araclar"].get(ad, 0) + 1
                    if ad in ("Write", "Edit", "NotebookEdit") and g.get("file_path"):
                        mevcut["dosyalar"].append(g["file_path"])
                    elif ad in ("Bash", "PowerShell"):
                        mevcut["komutlar"].append(kirp(g.get("description") or g.get("command", ""), 100))
                    elif ad == "Agent":
                        mevcut["komutlar"].append("ajan: " + kirp(g.get("description", ""), 80))
                    elif ad == "Skill":
                        mevcut["beceriler"].append(g.get("skill", ""))
                    elif ad.endswith("update_plan"):
                        plan.uygula(g)
                    elif ad.endswith("wrap_up"):
                        mevcut["ozet"].append(kirp(g.get("recap", "") + " " + g.get("ask", ""), 300))
                    elif ad.endswith(("start_session", "hand_off_to_session")):
                        mevcut["oturumlar"].append(kirp(g.get("title", ""), 80))

    n = 0
    for tur in turlar:
        if tur["kaynak"] == "kullanici":
            n += 1
            tur["id"] = f"U{n}"
            tur["dosyalar"] = sorted(set(tur["dosyalar"]))
            # Modelin Glob/Test-Path ile yeniden bakmaması için varlık kontrolü burada yapılır.
            tur["dosyalar_yok"] = [d for d in tur["dosyalar"] if not os.path.exists(d)]
            # Salt soru-cevap turu: dosya, komut, ajan, oturum, skill ve hata yok (CEVAPLANDI adayı).
            tur["eylem_yok"] = not (tur["dosyalar"] or tur["komutlar"] or tur["oturumlar"]
                                    or tur["beceriler"] or tur["hatalar"] or tur["ozet"])
    # Çağrı mesajının kendisi (/close) rapora girmez.
    for tur in reversed(turlar):
        if tur["kaynak"] == "kullanici":
            if re.match(r"^(/(orkestra:)?close\b|<command-name>/?(orkestra:)?close\b)", tur["metin"]):
                tur["kapsam_disi"] = True
            break

    kullanici = [t for t in turlar if t["kaynak"] == "kullanici"]
    # Asistanın sorusu yalnız kapanıştan önceki son turda kesin cevapsızdır; öncekileri sonraki mesaj yanıtlar.
    kapsamda = [t for t in kullanici if not t["kapsam_disi"]]
    cevapsiz = kapsamda[-1]["id"] if kapsamda and kapsamda[-1]["asistan_sordu"] else None
    cikis = {
        "dosya": os.path.basename(dosya),
        "oturum": os.path.splitext(os.path.basename(dosya))[0],
        "ilk": kullanici[0]["zaman"] if kullanici else None,
        "son": kullanici[-1]["zaman"] if kullanici else None,
        "kullanici_mesaji": len(kullanici),
        "plan_son_durum": plan.maddeler,
        "cevapsiz_soru": cevapsiz,
        "turlar": [t for t in turlar if t["kaynak"] == "kullanici"],
        "sistem_olaylari": sum(1 for t in turlar if t["kaynak"] == "sistem"),
    }
    os.makedirs(os.path.dirname(os.path.abspath(cikti)), exist_ok=True)
    with open(cikti, "w", encoding="utf-8") as f:
        json.dump(cikis, f, ensure_ascii=False, indent=1)
    acik_plan = [m["icerik"] for m in plan.maddeler if m["durum"] != "completed"]
    eylemsiz = sum(1 for t in kullanici if t["eylem_yok"])
    print(f"kullanıcı mesajı: {len(kullanici)} (eylemsiz {eylemsiz}) · elenen sistem mesajı: "
          f"{cikis['sistem_olaylari']} · plan maddesi: {len(plan.maddeler)} "
          f"(tamamlanmayan {len(acik_plan)}) · cevapsız asistan sorusu: {cevapsiz or 'yok'} · çıktı: {cikti}")


SATIR = re.compile(r"^- \[(" + "|".join(ETIKETLER) + r")\] (U\d+(?:[–-]U\d+)?(?:\s*,\s*U\d+(?:[–-]U\d+)?)*): (.+)$")
YER_TUTUCU = re.compile(r"<[^<>\n]{2,40}>|\bTODO\b|\bXXX\b|\.\.\.\.")
EPOSTA = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
YOL_UZANTI = re.compile(r"`([^`\n]*[\\/][^`\n]*\.(?:md|py|json|csv|xlsx|txt|jsonl))`")


def kimlikler(s):
    """'U3', 'U1, U4', 'U2–U5' ya da 'U1–U3, U7' ifadesini kimlik kümesine açar."""
    kume = set()
    for parca in s.split(","):
        ar = re.match(r"\s*U(\d+)[–-]U(\d+)\s*$", parca)
        if ar:
            kume |= {f"U{i}" for i in range(int(ar.group(1)), int(ar.group(2)) + 1)}
        else:
            kume.add(parca.strip())
    return kume


def acik_ayristir(govde):
    """'iş | Kanıt: … | Neden: …' gövdesini {is, kanit, neden} olarak ayırır."""
    parca = [p.strip() for p in govde.split(" | ")]
    sonuc = {"is": parca[0], "kanit": "", "neden": ""}
    for p in parca[1:]:
        if p.startswith("Kanıt:"):
            sonuc["kanit"] = p[6:].strip()
        elif p.startswith("Neden:"):
            sonuc["neden"] = p[6:].strip()
    return sonuc


def liste(rapor):
    """Raporun açık maddelerinden sohbette gösterilecek listeyi yazdırır (model aynen aktarır)."""
    konu, gruplar = "", []
    for l in open(rapor, encoding="utf-8").read().splitlines():
        if l.startswith("## Konu"):
            konu = re.sub(r"^## Konu \d+\s*[—-]\s*", "", l).strip()
            continue
        m = SATIR.match(l)
        if not m or m.group(1) not in ACIK:
            continue
        ac = acik_ayristir(m.group(3))
        onek = "Karar sizde: " if m.group(1) == "KARAR BEKLİYOR" else ""
        madde = f"- **{onek}{ac['is'].rstrip('.')}** — {ac['neden'].rstrip('.')}."
        if not gruplar or gruplar[-1][0] != konu:
            gruplar.append((konu, []))
        gruplar[-1][1].append(madde)
    toplam = sum(len(g[1]) for g in gruplar)
    if not toplam:
        print("Açık iş yok: sohbetteki tüm istekler kapandı.")
        return 0
    print(f"Açık kalan işler ({toplam}):\n")
    for konu, maddeler in gruplar:
        if len(gruplar) > 1:
            print(f"**{konu}**\n")
        print("\n".join(maddeler) + "\n")
    return 0


def denetle(rapor, girdi):
    veri = json.load(open(girdi, encoding="utf-8"))
    beklenen = {t["id"] for t in veri["turlar"] if not t["kapsam_disi"]}
    satirlar = open(rapor, encoding="utf-8").read().splitlines()
    hatalar, uyarilar = [], []
    sayim, gorulen, yapildi_yollar = {e: 0 for e in ETIKETLER}, set(), []

    for no, l in enumerate(satirlar, 1):
        if l.startswith("- ["):
            m = SATIR.match(l)
            if not m:
                hatalar.append(f"satır {no}: madde biçimi bozuk (beklenen: - [ETİKET] U3: istek | Kanıt: … | Neden: …)")
                continue
            etiket, ids, govde = m.group(1), kimlikler(m.group(2)), m.group(3)
            sayim[etiket] += 1
            gorulen |= ids
            bilinmeyen = ids - {t["id"] for t in veri["turlar"]}
            if bilinmeyen:
                hatalar.append(f"satır {no}: kayıtta olmayan kimlik {sorted(bilinmeyen)}")
            if etiket in KANIT_ISTER and "Kanıt:" not in govde:
                hatalar.append(f"satır {no}: {etiket} maddesinde 'Kanıt:' yok")
            if etiket in NEDEN_ISTER:
                ac = acik_ayristir(govde)
                if not ac["neden"]:
                    hatalar.append(f"satır {no}: {etiket} maddesinde 'Neden:' yok (bu işin neden yapılması gerektiği, tek cümle)")
                else:
                    if len(ac["neden"]) > NEDEN_EN_FAZLA or IKI_CUMLE.search(ac["neden"].rstrip(". ")):
                        hatalar.append(f"satır {no}: 'Neden:' tek ve kısa cümle olmalı (≤{NEDEN_EN_FAZLA} karakter)")
                    if ac["neden"].lower().startswith(("eksik", "yapılmadı", "kısmen")):
                        hatalar.append(f"satır {no}: 'Neden:' durum tekrarı; işin gerekçesini yaz (yapılmazsa ne olur / neye bağlı)")
                if len(ac["is"]) > IS_EN_FAZLA:
                    hatalar.append(f"satır {no}: iş cümlesi {IS_EN_FAZLA} karakteri aşıyor; kısalt")
            if etiket == "YAPILDI":
                yapildi_yollar += [(no, y) for y in YOL_UZANTI.findall(govde)]
        if YER_TUTUCU.search(l) and not l.startswith("#"):
            hatalar.append(f"satır {no}: yer tutucu ya da TODO kalıbı")
        if EPOSTA.search(l):
            hatalar.append(f"satır {no}: e-posta kalıbı (rapora yazılmaz)")

    eksik = sorted(beklenen - gorulen, key=lambda x: int(x[1:]))
    if eksik:
        hatalar.append("rapora girmeyen kullanıcı mesajları: " + ", ".join(eksik))

    # Sayım bölümü: '- ETİKET: n' satırları, betik sayısıyla birebir olmalı.
    yazilan = {}
    for l in satirlar:
        m = re.match(r"^- (" + "|".join(ETIKETLER) + r"): (\d+)\s*$", l)
        if m:
            yazilan[m.group(1)] = int(m.group(2))
    if not yazilan:
        hatalar.append("'## Sayım' bölümü yok (- YAPILDI: n biçiminde, her etiket ayrı satır)")
    else:
        for e in ETIKETLER:
            if yazilan.get(e, -1) != sayim[e]:
                hatalar.append(f"sayım tutarsız: {e} raporda {yazilan.get(e, 'yok')}, maddelerde {sayim[e]}")

    for no, y in yapildi_yollar:
        if not os.path.exists(y):
            hatalar.append(f"satır {no}: YAPILDI kanıtı olan yol yok: {y}")

    print(f"kapsanan mesaj: {len(gorulen & beklenen)}/{len(beklenen)} · sayım: " +
          " ".join(f"{e}={sayim[e]}" for e in ETIKETLER))
    for h in hatalar:
        print("HATA:", h)
    for u in uyarilar:
        print("UYARI:", u)
    print("GEÇTİ" if not hatalar else f"KALDI ({len(hatalar)} hata)")
    return 0 if not hatalar else 1


def main():
    ap = argparse.ArgumentParser()
    alt = ap.add_subparsers(dest="komut", required=True)
    c = alt.add_parser("cikar")
    c.add_argument("--oturum")
    c.add_argument("--dosya")
    c.add_argument("--cikti", required=True)
    d = alt.add_parser("denetle")
    d.add_argument("rapor")
    d.add_argument("--girdi", required=True)
    li = alt.add_parser("liste")
    li.add_argument("rapor")
    a = ap.parse_args()
    if a.komut == "liste":
        return liste(a.rapor)
    if a.komut == "cikar":
        if not (a.oturum or a.dosya):
            sys.exit("HATA: --oturum ya da --dosya gerekli")
        cikar(a.dosya or kayit_bul(a.oturum), a.cikti)
        return 0
    return denetle(a.rapor, a.girdi)


if __name__ == "__main__":
    sys.exit(main())
