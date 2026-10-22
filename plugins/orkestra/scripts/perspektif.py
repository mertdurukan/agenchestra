"""Perspektif: oturumlar arasında arka planda çalışan hafıza bakımı (+ skill avı).

Ne zaman: son perspektiften bu yana ≥7 gün ya da ≥20 oturum geçtiyse, oturum kapanırken (SessionEnd) arka planda.
Nasıl: başsız `claude -p` (Sonnet), YALNIZ OKUMA araçlarıyla; hafızayı değiştirmez, öneri raporu yazar.
Rapor: <durum>/perspektif/perspektif_<tarih>.md ; bir sonraki oturumda ana ajan özetler, kullanıcı onaylarsa `/orkestra:perspektif` uygular.

Maliyet (BIC-3): mekanik ölçümler (hafıza boyutu, ölü yollar, maliyet anomalileri, KPI, günlük ve defter özeti) LLM'e
yaptırılmaz; `girdi_yaz` bunları tek bir perspektif/girdi.json dosyasına yazar. Ajan ve başsız koşu ham kaynakları
taramak yerine bu dosyayı okur. Değişim kapısı: süre/oturum eşiği dolsa bile girdi imzası (hafıza, kurallar, skill'ler,
anomali kümesi, istek kovası) son rapordakiyle aynıysa koşu atlanır ve sayaç sıfırlanır.
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402
import ork_lib as L  # noqa: E402

GUN_ESIGI = 7
OTURUM_ESIGI = 20
CALISMA_ZAMAN_ASIMI_SN = 2 * 3600
GIRDI_GUN = 14
ISTEK_KOVASI = 20  # skill adayı sinyali: istek sayısı bu kadar artınca girdi değişmiş sayılır
YOL_DESENI = re.compile(r"`([^`\n]*[\\/][^`\n]*\.[A-Za-z0-9]{1,5})`")  # ters tırnaklı dosya yolları


def _durum_yolu(sd):
    L.perspektif_goc(sd)  # eski ruya/ klasörü varsa perspektif/'e taşı
    return os.path.join(sd, "perspektif", "durum.json")


def son_rapor_bul(sd) -> str | None:
    """En yeni rapor: perspektif_*.md ya da eski adlı ruya_*.md (hata raporları hariç)."""
    adaylar = [a for on in ("perspektif_2", L.ESKI_AD + "_2") for a in glob.glob(os.path.join(sd, "perspektif", on + "*.md"))
               if "_hata_" not in os.path.basename(a)]
    return max(adaylar, key=os.path.getmtime) if adaylar else None


def _oku(sd) -> dict:
    try:
        with open(_durum_yolu(sd), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {"son_perspektif": None, "oturum_sayaci": 0, "son_rapor": None, "rapor_okundu": True, "calisiyor": None}
    if "son_ruya" in d:  # eski anahtar → yeni anahtar
        d["son_perspektif"] = d.pop("son_ruya")
    return d


def _yaz(sd, d):
    L.atomik_yaz(_durum_yolu(sd), json.dumps(d, ensure_ascii=False, indent=2))


def oturum_say(sd, kaynak):
    if kaynak not in (None, "startup"):
        return
    with L.kilit(_durum_yolu(sd)):
        d = _oku(sd)
        d["oturum_sayaci"] = d.get("oturum_sayaci", 0) + 1
        _yaz(sd, d)


def _girdi_yolu(sd):
    return os.path.join(sd, "perspektif", "girdi.json")


def _metin(yol) -> str:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _hafiza_ozeti(hafiza: str, proje: str) -> tuple[list, list, list, dict]:
    """olu: bulunamayan mutlak yollar; belirsiz: proje ve hafıza köküne göre bulunamayan göreli yollar (bağlamlı olabilir)."""
    dosyalar, olu, belirsiz, imza = [], [], [], {}
    for yol in sorted(glob.glob(os.path.join(hafiza, "*.md"))):
        ad, metin = os.path.basename(yol), _metin(yol)
        dosyalar.append({"ad": ad, "satir": len(metin.splitlines()), "bayt": len(metin.encode("utf-8"))})
        imza[ad] = hashlib.sha256(metin.encode("utf-8")).hexdigest()[:16]
        for m in YOL_DESENI.findall(metin):
            p = os.path.expandvars(os.path.expanduser(m.strip()))
            if any(c in p for c in "*<>{}$"):
                continue
            adaylar = [p] if os.path.isabs(p) else [os.path.join(proje, p), os.path.join(hafiza, p)]
            if not any(os.path.exists(x) for x in adaylar):
                (olu if os.path.isabs(p) else belirsiz).append({"dosya": ad, "yol": m})
    return dosyalar, olu, belirsiz, imza


def _duzeltme_tekrari(hafiza: str) -> dict:
    """Hafıza klasöründe birebir tekrar eden düzeltme notları (ADR-0029); yerler `dosya:satır`. Hatada boş."""
    try:
        import hafiza_duzeltme as HD
        bulgular = [{"not": g["not"][:160], "adet": g["adet"],
                     "yerler": [f"{os.path.basename(y)}:{n}" for y, n in g["yerler"]][:12]} for g in HD.tara(hafiza)]
    except Exception:
        bulgular = []
    return {"sayi": len(bulgular), "bulgular": bulgular[:20]}


def _skiller(proje: str) -> list[str]:
    kokler = [os.path.join(proje, ".claude", "skills"),
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")]
    return sorted({os.path.basename(os.path.dirname(y)) for k in kokler for y in glob.glob(os.path.join(k, "*", "SKILL.md"))})


def girdi(sd: str, proje: str, hafiza: str) -> dict:
    """Perspektifin mekanik girdisi (LLM'siz) ve değişim imzası."""
    import collections
    import kpi
    import maliyet_anomali as MA
    dosyalar, olu, belirsiz, h_imza = _hafiza_ozeti(hafiza, proje)
    kurallar = _metin(os.path.join(proje, "CLAUDE.md")) + "".join(
        _metin(y) for y in sorted(glob.glob(os.path.join(proje, ".claude", "rules", "*.md"))))
    try:
        anomali = MA.calistir(sd, GIRDI_GUN)
    except Exception:
        anomali = []
    try:
        k = kpi.olcum(sd, GIRDI_GUN)
        kpi_ = {"genel": k["genel"], "ana_ajan_payi": k["ana_ajan_payi"]}
    except Exception:
        kpi_ = {}
    esik = (datetime.datetime.now().astimezone() - datetime.timedelta(days=GIRDI_GUN)).isoformat()
    gun = [r for r in L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")) if r.get("zaman", "") >= esik]
    istekler = [r for r in gun if r.get("tur") == "istek"]
    defter = [r for r in L.defter_kayitlari(sd) if r.get("zaman", "") >= esik]
    etiketsiz = sum(1 for r in defter if r.get("gorev") in (None, "", "-") and r.get("ajan") not in (None, "ana-ajan"))
    skiller = _skiller(proje)
    duzeltme = _duzeltme_tekrari(hafiza)
    memory = next((x for x in dosyalar if x["ad"] == "MEMORY.md"), None)
    imza_kaynagi = {"hafiza": h_imza, "kurallar": hashlib.sha256(kurallar.encode("utf-8")).hexdigest()[:16],
                    "skiller": skiller, "anomali": sorted({f"{a['kural']}:{a['kart']}" for a in anomali}),
                    "istek_kovasi": len(istekler) // ISTEK_KOVASI,
                    "duzeltme": sorted(b["not"] for b in duzeltme["bulgular"])}
    return {
        "zaman": L.simdi(), "gun": GIRDI_GUN,
        "imza": hashlib.sha256(json.dumps(imza_kaynagi, sort_keys=True).encode("utf-8")).hexdigest()[:20],
        "hafiza": {"klasor": hafiza, "dosyalar": dosyalar, "memory_md": memory,
                   "olu_yollar": olu[:60], "olu_yol_sayisi": len(olu), "belirsiz_yollar": belirsiz[:60]},
        "skiller": skiller,
        "duzeltme_tekrari": duzeltme,
        "anomali": {"sayim": dict(collections.Counter(a["kural"] for a in anomali)), "ilk": anomali[:25]},
        "kpi": kpi_,
        "gunluk": {"olay": len(gun), "tur": dict(collections.Counter(r.get("tur") for r in gun)),
                   "skill": dict(collections.Counter(r.get("skill") for r in gun if r.get("tur") == "skill").most_common(20)),
                   "ajan": dict(collections.Counter(r.get("ajan") for r in gun if r.get("tur") == "ajan").most_common(20)),
                   "istekler": [f"{r.get('zaman', '')[:16]} {str(r.get('metin', ''))[:160]}" for r in istekler[-40:]]},
        "defter": {"kayit": len(defter), "etiketsiz_ajan": etiketsiz,
                   "son": [{"gorev": r.get("gorev"), "surec": r.get("surec"), "ajan": r.get("ajan"),
                            "sonuc": str(r.get("sonuc", ""))[:200]} for r in defter[-30:]]},
    }


def girdi_yaz(sd: str, proje: str, hafiza: str) -> dict:
    g = girdi(sd, proje, hafiza)
    L.atomik_yaz(_girdi_yolu(sd), L.maskele(json.dumps(g, ensure_ascii=False, indent=1)))
    return g


def durum(sd, proje: str | None = None, hafiza: str | None = None) -> dict:
    """proje ve hafiza verilirse süre/oturum eşiği dolduğunda değişim kapısı da uygulanır (girdi.json yazılır)."""
    d = _oku(sd)
    simdi = datetime.datetime.now().astimezone()
    calisiyor = d.get("calisiyor")
    if calisiyor:
        try:
            if (simdi - datetime.datetime.fromisoformat(calisiyor)).total_seconds() > CALISMA_ZAMAN_ASIMI_SN:
                calisiyor = None
        except Exception:
            calisiyor = None
    gun = None
    if d.get("son_perspektif"):
        try:
            gun = (simdi - datetime.datetime.fromisoformat(d["son_perspektif"])).days
        except Exception:
            gun = None
    oturum = d.get("oturum_sayaci", 0)
    if d.get("yoksay_tarihi"):  # kullanıcı bu alarmı yoksaydı: süre ve oturum eşiği yoksayma anından yeniden sayılır
        try:
            yoksay_gun = (simdi - datetime.datetime.fromisoformat(d["yoksay_tarihi"])).days
            gun = yoksay_gun if gun is None else min(gun, yoksay_gun)
        except Exception:
            pass
        oturum = max(0, oturum - d.get("yoksay_oturum", 0))
    zamani = not calisiyor and (gun is None or gun >= GUN_ESIGI or oturum >= OTURUM_ESIGI)
    atlandi = False
    if zamani and proje and hafiza and d.get("son_girdi_imza"):
        try:
            imza = girdi_yaz(sd, proje, hafiza)["imza"]
        except Exception:
            imza = None
        if imza and imza == d.get("son_girdi_imza"):
            with L.kilit(_durum_yolu(sd)):
                st = _oku(sd)
                st.update(son_perspektif=L.simdi(), oturum_sayaci=0, son_atlama=L.simdi())
                _yaz(sd, st)
            zamani, atlandi = False, True
    son_rapor = d.get("son_rapor")
    if not son_rapor or not os.path.exists(son_rapor):
        son_rapor = son_rapor_bul(sd) or son_rapor  # durum.json'da yol yoksa/eskimişse klasörden bul (ruya_*.md dahil)
    return {"son_perspektif": d.get("son_perspektif"), "gun_once": gun, "oturum_sayaci": d.get("oturum_sayaci", 0),
            "zamani_geldi": bool(zamani), "girdi_degismedi": atlandi, "calisiyor": calisiyor, "son_rapor": son_rapor,
            "okunmamis_rapor": son_rapor if son_rapor and d.get("son_rapor") and not d.get("rapor_okundu") else None}


def yoksay(sd) -> None:
    """Açık alarmı yoksayar: bir sonraki tetikleme (GUN_ESIGI gün ya da OTURUM_ESIGI yeni oturum sonra) gelene kadar sormaz."""
    with L.kilit(_durum_yolu(sd)):
        d = _oku(sd)
        d.update(yoksay_tarihi=L.simdi(), yoksay_oturum=d.get("oturum_sayaci", 0))
        _yaz(sd, d)


def bitti_isaretle(sd):
    with L.kilit(_durum_yolu(sd)):
        d = _oku(sd)
        d["rapor_okundu"] = True
        _yaz(sd, d)


def hafiza_dizini(proje: str, transkript: str | None = None) -> str:
    if transkript:
        return os.path.join(os.path.dirname(transkript), "memory")
    ad = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(proje))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", ad, "memory")


def claude_exe() -> str | None:
    """claude.exe: cfg (CLAUDE_CODE_EXECPATH > makine config'i > keşif)."""
    return cfg.al("claude_exe")


ISTEM = """#SUREC:perspektif
Sen orkestra sisteminin PERSPEKTİF (hafıza bakımı) koşusunsun. Kullanıcı yok; YALNIZ OKU, hiçbir dosyayı değiştirme.
Görev: aşağıdaki kaynakları oku ve tek bir Markdown rapor üret (yanıtın yalnız rapor olsun).

Kaynaklar (önce 1'i oku; sayıları yeniden hesaplama, oradan al):
1. Mekanik girdi: {sd}\\perspektif\\girdi.json — hafıza dosya boyutları ve MEMORY.md satır/bayt, ölü yollar, maliyet
   anomalileri (kural tabanlı, 14 gün), KPI, günlük özeti (istekler, skill/ajan kullanımı), ortak defter özeti.
2. Otomatik hafıza: {hafiza}  (MEMORY.md + konu dosyaları) — yalnız içerik yargısı için (kopya, çelişki, eskimiş iş).
3. Proje kuralları: {proje}\\CLAUDE.md ve {proje}\\.claude\\rules\\ (varsa).

Rapor bölümleri (Türkçe, kısa cümleler):
## 1. Özet — 3-5 madde.
## 2. Birleştirilecek kopyalar — aynı bilgiyi taşıyan hafıza kayıtları; hangi dosyada kalsın.
## 3. Çelişkiler — iki kaydın birbirini yalanladığı yerler; hangisi güncel (tarih/kanıt).
## 4. Eskimiş veya doğrulanamayan — girdi.json'daki ölü yollar; "devam ediyor" denip bitmiş işler.
## 5. Boyut — girdi.json'daki MEMORY.md satır/bayt; 200 satır sınırına yakınsa hangi kayıtlar konu dosyalarına bölünmeli.
## 6. Önerilen değişiklikler — her biri için dosya, ne değişecek, gerekçe; uygulanabilir kısa diff blokları; her önerinin altında Kanıt:, Geçtiği yerler: ve Vaat: satırları.
## 7. Skill adayları — girdi.json günlük isteklerinde skill'siz tekrarlanan (≥3) istek türleri; her aday için ad, tetik cümleleri, girdi→çıktı, başlangıç basamağı (T0-T4), mevcut betik.
## 8. Orkestra sağlığı — ortak defterde etiketsiz (#GOREV yok) ajan oranı, reddedilen/yükseltilen kartlar, dikkat çeken maliyet; girdi.json'daki her anomali kuralı için kök neden ve Vaat satırlı düzeltme önerisi.


## Doğrulama (P-021)
Rapordaki her var/yok/kaç kez/kayıp iddiası ve her öneri yazılmadan önce kanıtlanır; hafızadan ya da varsayımdan yazılmaz.
- Her iddianın ve önerinin altına girintili `Kanıt:` satırı ekle. Biçimler: `Kanıt: ara "regex" dosya => N` (ya da `>=N`), `Kanıt: say glob => N`, `Kanıt: dosya yol:satır "alıntı"`.
- "Kayıp" ya da "eksik" denen dosyayı adıyla Glob'la; bulunmadıysa bu Kanıt satırında göster, bulunduysa iddiayı yazma.
- Sayısal hedefte (satır, bayt, kez) hesabı Kanıt satırında göster; girdi.json'dan alınan sayıyı yeniden hesaplama.
- Bir iddia ya da öneri `Geçtiği yerler:` satırı taşır: iddianın geçtiği tüm hafıza kayıtları, `dosya:satır` listesi olarak (Grep ile bul).
- Düzeltme biçimi: kaynakta yeniden yaz, not ekleme. Düzeltilecek iddia asıl anlatıldığı kayıtta olgu cümlesi olarak yeniden yazılır; geçtiği diğer yerlerde olgu doğru yazılır ya da cümle silinip kaynak kayda bağlantı verilir. Düzeltme notu eklemek öneri sayılmaz.
- girdi.json `duzeltme_tekrari` alanındaki her bulgu (aynı düzeltme notunun birden çok kayıtta tekrarı) bölüm 6'da bir öneri olur.
- Bölüm 2-5'teki her bulgu bölüm 6'daki bir öneriye bağlanır ya da `Öneri yok: <neden>` satırı taşır.
- Rapor yazıldıktan sonra `orkestra perspektif dogrula <rapor yolu>` çalıştırılır; ❌ ile işaretlenen Kanıt satırı düzeltilir ya da iddia "doğrulanamadı" diye işaretlenir. Komut çalıştıramıyorsan atla: `kaydet` aynı doğrulamayı kendisi yapar.

Kurallar: sır değeri, şifre, çalışan adı yazma. Emin olmadığın şeyi "doğrulanamadı" diye işaretle. Değişiklik UYGULAMA.
"""


def headless_mumkun(sd: str, exe: str | None) -> bool:
    """Komut satırı oturum açmış mı? (masaüstü oturumunun kimliği başsız koşuya geçmez).
    Yalnız OLUMLU sonuç 12 saat önbelleğe alınır; olumsuz sonuç her seferinde yeniden sorulur (`auth status` ucuzdur).
    Neden: 16.10'da ağ hatasıyla düşen bir koşu 'oturum yok' diye 12 saat önbelleğe yazıldı; `claude auth login`
    sonrası bile 'Şimdi uygula' reddedildi."""
    if not exe:
        return False
    d = _oku(sd)
    onb = d.get("headless") or {}
    try:
        if onb.get("mumkun") and onb.get("zaman") and (datetime.datetime.now().astimezone() - datetime.datetime.fromisoformat(onb["zaman"])).total_seconds() < 12 * 3600:
            return True
    except Exception:
        pass
    try:
        r = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, encoding="utf-8", timeout=20)
        mumkun = bool(json.loads(r.stdout or "{}").get("loggedIn"))
    except Exception:
        mumkun = False
    with L.kilit(_durum_yolu(sd)):
        st = _oku(sd)
        if mumkun:
            st["headless"] = {"zaman": L.simdi(), "mumkun": True}
        else:
            st.pop("headless", None)
        _yaz(sd, st)
    return mumkun


def proje_uyusmazligi(istenen: str | None, gercek: str) -> str | None:
    """`--proje` verilmişse ve oturumun projesi farklıysa hata metni döner; yoksa None.

    Neden: düğmeyle açılan sohbet klasörsüz (scratch) açılırsa koşu yanlış projenin durum.json'una yazar.
    """
    if not istenen:
        return None
    norm = lambda p: os.path.normcase(os.path.realpath(p))  # noqa: E731
    if norm(istenen) == norm(gercek):
        return None
    return (f"yanlış klasör: oturum {gercek}, istenen {istenen}; "
            f"change_directory ile {istenen} klasörüne geç ve komutu yeniden çalıştır")


def basladi_isaretle(sd: str) -> None:
    with L.kilit(_durum_yolu(sd)):
        st = _oku(sd)
        st["calisiyor"] = L.simdi()
        _yaz(sd, st)


# ---------------------------------------------------------------- rapor kanıt doğrulaması (ADR-0029, P-021)
# Rapordaki `Kanıt:` satırları plan_dogrulama kanıt dilbilgisiyle yeniden hesaplanır (dosya, ara, say, deneme, kaynak;
# komut koşulmaz: rapor katılımsız ajandan gelir). Tutmayan satırın altına işaret yazılır; kayıt engellenmez.

_KANIT = re.compile(r"^(?P<g>\s*)(?:[-*]\s+)?Kanıt:[ \t]*(?P<deger>.+?)\s*$")
ISARET = "\u274c Kanıt tutmadı:"
_ISARET_SATIRI = re.compile(r"^\s*" + re.escape(ISARET))
_KOSULMAYAN = ("komut koşulmadı", "komut çalıştırılmadı")


def rapor_dogrula(rapor: str, hafiza: str, proje: str) -> dict:
    """{toplam, tutan, dogrulanmadi, tutmayan: [{satir (1 tabanlı), tur, mesaj}]}. Rapor okunamazsa ValueError."""
    import plan_dogrulama as PD
    try:
        with open(rapor, encoding="utf-8") as f:
            satirlar = f.read().splitlines()
    except OSError as e:
        raise ValueError(f"rapor okunamadı: {rapor}") from e
    kokler = [k for k in (hafiza, proje) if k]
    sonuc = {"toplam": 0, "tutan": 0, "dogrulanmadi": 0, "tutmayan": []}
    for no, satir in enumerate(satirlar, 1):
        if _ISARET_SATIRI.match(satir):
            continue
        m = _KANIT.match(satir)
        if not m:
            continue
        bol = m.group("deger").split(None, 1)
        tur, deger = (bol[0] if bol else "").lower(), (bol[1] if len(bol) > 1 else "")
        sonuc["toplam"] += 1
        ok, _, mesaj = PD.kanit_dogrula({"tur": tur, "deger": deger}, kokler, proje, kos=False)
        if ok is True:
            sonuc["tutan"] += 1
        elif ok is None or mesaj.startswith(_KOSULMAYAN):
            sonuc["dogrulanmadi"] += 1
        else:
            sonuc["tutmayan"].append({"satir": no, "tur": tur, "mesaj": mesaj})
    return sonuc


def rapor_isaretle(rapor: str, hafiza: str, proje: str) -> dict:
    """Önceki işaretleri siler, tutmayan her `Kanıt:` satırının altına işaret yazar (idempotent). rapor_dogrula sonucunu döner."""
    with open(rapor, encoding="utf-8") as f:
        satirlar = [s for s in f.read().splitlines() if not _ISARET_SATIRI.match(s)]
    temiz = rapor + ".tmp"
    with open(temiz, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(satirlar) + "\n")
    try:
        sonuc = rapor_dogrula(temiz, hafiza, proje)
    finally:
        os.remove(temiz)
    islenen = {t["satir"]: t for t in sonuc["tutmayan"]}
    yeni = []
    for no, satir in enumerate(satirlar, 1):
        yeni.append(satir)
        if no in islenen:
            girinti = _KANIT.match(satir).group("g")
            yeni.append(f"{girinti}  {ISARET} {islenen[no]['mesaj']}")
    L.atomik_yaz(rapor, "\n".join(yeni) + "\n")
    return sonuc


def kaydet(sd: str, rapor: str, proje: str | None = None) -> dict | None:
    with L.kilit(_durum_yolu(sd)):
        st = _oku(sd)
        st.update(son_perspektif=L.simdi(), oturum_sayaci=0, son_rapor=os.path.abspath(rapor), rapor_okundu=False, calisiyor=None)
        st.pop("yoksay_tarihi", None)
        st.pop("yoksay_oturum", None)
        try:
            with open(_girdi_yolu(sd), encoding="utf-8") as f:
                st["son_girdi_imza"] = json.load(f).get("imza")
        except Exception:
            pass
        _yaz(sd, st)
    L.defter_ekle(sd, {"gorev": "-", "surec": "perspektif", "ajan": "orkestra:perspektif-ajani", "model": "sonnet",
                       "yaptim": "Hafıza bakımı ve skill avı (yalnız okuma).", "sonuc": f"Rapor: {rapor}", "kaynak": "perspektif"})
    try:  # kanıtı tutmayan iddialar işaretlenir; hata kaydı bozmaz
        proje = proje or L.proje_dizini()
        with open(_girdi_yolu(sd), encoding="utf-8") as f:
            klasor = (json.load(f).get("hafiza") or {}).get("klasor")
        return rapor_isaretle(rapor, klasor or hafiza_dizini(proje), proje)
    except Exception:
        return None


def baslat(sd: str, proje: str, transkript: str | None = None, zorla: bool = False) -> str:
    d = durum(sd)
    if d["calisiyor"]:
        return f"zaten çalışıyor (başlangıç {d['calisiyor']})"
    if not zorla and not d["zamani_geldi"]:
        return "zamanı gelmedi"
    exe = claude_exe()
    if not headless_mumkun(sd, exe):
        return ("HEADLESS-YOK: komut satırı oturum açmamış. Perspektifi oturum içinde başlat: Agent aracı, "
                "subagent_type `orkestra:perspektif-ajani`, run_in_background true, istem `#SUREC:perspektif hafıza klasörü: "
                + hafiza_dizini(proje, transkript) + "`. (Kalıcı çözüm: bir kez `claude auth login`.)")
    with L.kilit(_durum_yolu(sd)):
        st = _oku(sd)
        st["calisiyor"] = L.simdi()
        _yaz(sd, st)
    hafiza = hafiza_dizini(proje, transkript)
    try:
        girdi_yaz(sd, proje, hafiza)
    except Exception:
        pass
    args = [sys.executable, os.path.abspath(__file__), "_kos", sd, proje, hafiza, exe]
    subprocess.Popen(args, cwd=proje, creationflags=cfg.ARKA_PLAN_BAYRAK, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    return f"perspektif arka planda başladı → {os.path.join(sd, 'perspektif')}"


def _kos(sd: str, proje: str, hafiza: str, exe: str):
    ortam = dict(os.environ, ORKESTRA_PERSPEKTIF="1", PYTHONUTF8="1")
    istem = ISTEM.format(hafiza=hafiza, proje=proje, sd=sd)
    damga = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    rapor = os.path.join(sd, "perspektif", f"perspektif_{damga}.md")
    komut = [exe, "-p", istem, "--model", "sonnet", "--effort", "medium", "--max-turns", "60",
             "--allowedTools", "Read", "Glob", "Grep", "--add-dir", hafiza, "--add-dir", sd, "--output-format", "text"]
    basarili = False
    try:
        r = subprocess.run(komut, cwd=proje, env=ortam, capture_output=True, text=True, encoding="utf-8", timeout=3600)
        metin = r.stdout.strip()
        basarili = r.returncode == 0 and len(metin) > 200 and "Not logged in" not in metin
        if not basarili:
            metin = f"(çıkış kodu {r.returncode})\n\n{metin[-2000:]}\n\n{r.stderr[-2000:]}"
    except Exception as e:
        metin = f"(perspektif koşusu başarısız: {type(e).__name__}: {e})"
    if not basarili:
        hata_yolu = os.path.join(sd, "perspektif", f"perspektif_hata_{damga}.md")
        L.atomik_yaz(hata_yolu, f"# Perspektif koşusu başarısız — {L.simdi()[:16]}\n\n" + L.maskele(metin) + "\n")
        with L.kilit(_durum_yolu(sd)):
            st = _oku(sd)
            st["calisiyor"] = None
            st.pop("headless", None)  # koşu başarısızlığı (ağ/DNS dahil) 'oturum yok' kanıtı değildir; bir sonraki kontrol yeniden sorar
            _yaz(sd, st)
        return
    L.atomik_yaz(rapor, f"# Perspektif raporu — {L.simdi()[:16]}\n\n" + L.maskele(metin) + "\n")
    kaydet(sd, rapor)


if __name__ == "__main__":
    if len(sys.argv) >= 6 and sys.argv[1] == "_kos":
        _kos(*sys.argv[2:6])
