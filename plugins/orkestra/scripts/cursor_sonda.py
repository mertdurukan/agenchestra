"""Cursor CLI ile dinamik sonda (`orkestra doktor --cursor-sonda`, ADR-0172).

Neden: Cursor kurulumunun sessiz kırıkları (Shell'de `orkestra` komutu yok, oturum kimliği uyuşmuyor, kopya bayat) dosya
okuyarak kesin söylenemez; ölçüm Claude oturumunun ortamını devralınca 'komut var' diye yanıltır (08.11.2026). Sonda gerçek
bir Cursor ajan koşusu yapar: temiz ortam (CLAUDE*/ORKESTRA*/ANTHROPIC* değişkenleri ve eklenti bin yolu çıkarılmış), geçici
proje, kullanıcının gerçek Cursor kurulumu. Model kullanır ve süre alır (~1 dk), bu yüzden yalnız açık istekle çalışır.

Kanıt hook ve dosya tarafındadır, modelin anlatımına güvenilmez: Cursor'a kurulu adaptör komutu açık yola yazdı mı, Shell'in
CURSOR_CONVERSATION_ID değeri hook yükündeki session_id ile aynı mı, komut gerçekten çıktı verdi mi. Sonda proje hook'u olarak
yalnız bir yük kayıtçısı ekler; Orkestra adaptörü kullanıcının gerçek Cursor kurulumundan (yerel kopya) gelir, böylece 'kurulu mu'
sorusu da yanıtlanır. Hook komutları `python -c "..."` biçimindedir: Cursor Shell'i PowerShell olduğundan baştaki tırnaklı yol
(`"<python yolu>" -c ...`) söz dizimi hatasıdır."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISARET = "kok_neden.md"
KIMLIK_DOSYASI = "kimlik.txt"


_BASH_DEGISKENLERI = {"SHELL", "TERM", "SHLVL", "EXEPATH", "ORIGINAL_PATH", "CHERE_INVOKING", "_"}


def _temiz_ortam(ek):
    """Claude/Orkestra/Anthropic değişkenleri ve Git Bash izleri çıkarılır. Git Bash'ten başlatılan Cursor CLI hook komutlarını
    bash'te çalıştırır ve PowerShell sözdizimi (08.11.2026 ölçümü: 'hook hatası', Shell aracı tamamen engellendi) hata verir;
    kullanıcının Cursor'u PowerShell/IDE'den açtığı gerçek durumu ölçmek için bu izler taşınmaz."""
    ortam = {k: v for k, v in os.environ.items()
             if not k.upper().startswith(("CLAUDE", "ORKESTRA", "ANTHROPIC", "MSYS", "BASH")) and k.upper() not in _BASH_DEGISKENLERI}
    bin_yolu = os.path.normcase(os.path.join(KOK, "bin"))
    ortam["PATH"] = os.pathsep.join(
        d for d in ortam.get("PATH", "").split(os.pathsep)
        if d and os.path.normcase(d.rstrip("\\/")) != bin_yolu
        and not any(s in d.lower() for s in ("plugin_yayin", "orkestra", "claude-orchestration", os.sep + ".claude"))
    )
    ortam.update(ek)
    return ortam


def _hooks_json():
    kod = "import sys,os;open(os.environ['ORK_SONDA_YUK'],'ab').write(sys.stdin.buffer.read()+bytes([10]))"
    return {"version": 1, "hooks": {"preToolUse": [{"command": f'python -c "{kod}"', "matcher": "Shell"}]}}


_KIMLIK_BETIGI = "\n".join([
    "import os",
    "yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), %r)" % KIMLIK_DOSYASI,
    "open(yol, 'w', encoding='utf-8').write(os.environ.get('CURSOR_CONVERSATION_ID') or '')",
    "",
])


def _satirlar(yol):
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return [s for s in f.read().splitlines() if s.strip()]
    except OSError:
        return []


def _json(satir):
    try:
        return json.loads(satir)
    except ValueError:
        return {}


def degerlendir(ajan_cikti, yuk_satirlari, hata_ayiklama_satirlari, kimlik="", kurulu=True):
    """Ölçümleri üç kanıttan çıkarır. Dönüş: [(ad, durum, ayrıntı)], durum: gecti | basarisiz | belirsiz."""
    sonuc = []
    yukler = [_json(s) for s in yuk_satirlari]
    kabuk = [y for y in yukler if y.get("tool_name") == "Shell"]
    # 1) adaptör komutu açık yola yazdı mı
    yazilan = []
    for s in hata_ayiklama_satirlari:
        o = _json(s)
        if o.get("olay") != "preToolUse":
            continue
        komut = o.get("yeni_komut") or ""
        if "orkestra.py" in komut:
            yazilan.append(komut)
    if yazilan:
        sonuc.append(("komut_yeniden_yazildi", "gecti", "adaptör `orkestra` komutunu eklentinin CLI betiğine yazdı"))
    elif kabuk and not kurulu:
        sonuc.append(("komut_yeniden_yazildi", "basarisiz", "yerel Cursor kopyası kurulu değil (~/.cursor/plugins/local/orkestra yok); "
                      "Cursor Shell'inde `orkestra` komutu çalışmaz. Kur: `orkestra doktor --duzelt` ya da scripts/cursor_kur.py"))
    elif kabuk:
        sonuc.append(("komut_yeniden_yazildi", "basarisiz", "Shell çağrısı geldi ama adaptör çıktısında orkestra.py yolu yok (kopya bayat ya da ORKESTRA_CURSOR_KOMUT_YAZ=0)"))
    else:
        sonuc.append(("komut_yeniden_yazildi", "belirsiz", "ajan Shell aracını çağırmadı"))
    # 2) komut gerçekten çalıştı mı
    if ISARET in ajan_cikti:
        sonuc.append(("komut_calisti", "gecti", "`orkestra` komutu Shell'de çıktı verdi"))
    else:
        sonuc.append(("komut_calisti", "basarisiz" if kabuk else "belirsiz", "ajan çıktısında komut sonucu yok"))
    # 3) Shell oturum kimliği = hook session_id
    kimlik = (kimlik or "").strip()
    hook_idleri = {y.get("session_id") or y.get("conversation_id") for y in kabuk} - {None, ""}
    if kimlik and hook_idleri:
        sonuc.append(("oturum_kimligi_esit", "gecti" if kimlik in hook_idleri else "basarisiz",
                      "CURSOR_CONVERSATION_ID hook session_id ile " + ("aynı" if kimlik in hook_idleri else "farklı")))
    else:
        sonuc.append(("oturum_kimligi_esit", "belirsiz", "Shell değişkeni ya da hook yükü okunamadı"))
    return sonuc


def calistir(zaman_asimi=300, ajan_komutu=None):
    """Sondayı koşar. Dönüş: {"durum": atlandi|gecti|basarisiz|belirsiz, "mesaj", "olcumler"}."""
    ajan = ajan_komutu or shutil.which("agent") or shutil.which("cursor-agent")
    if not ajan:
        return {"durum": "atlandi", "mesaj": "Cursor CLI (`agent`) PATH'te yok; dinamik sonda koşulamaz", "olcumler": []}
    gecici = tempfile.mkdtemp(prefix="ork_cursor_sonda_")
    try:
        os.makedirs(os.path.join(gecici, ".cursor"))
        with open(os.path.join(gecici, ".cursor", "hooks.json"), "w", encoding="utf-8") as f:
            json.dump(_hooks_json(), f)
        with open(os.path.join(gecici, "kimlik_yaz.py"), "w", encoding="utf-8") as f:
            f.write(_KIMLIK_BETIGI)
        yuk, ayiklama = os.path.join(gecici, "yuk.jsonl"), os.path.join(gecici, "ayiklama.jsonl")
        istem = ("Run these two shell commands one after the other and print the raw output of each. "
                 "Command 1: orkestra standart yol kok_neden  Command 2: python kimlik_yaz.py")
        ortam = _temiz_ortam({"ORK_SONDA_YUK": yuk, "ORKESTRA_CURSOR_DEBUG": ayiklama, "PYTHONUTF8": "1"})
        try:
            p = subprocess.run([ajan, "-p", "--force", "--trust", "--output-format", "text", istem], cwd=gecici, env=ortam,
                               capture_output=True, timeout=zaman_asimi,
                               **({"creationflags": 0x08000000} if os.name == "nt" else {}))  # CREATE_NO_WINDOW (cfg.PENCERESIZ)
        except subprocess.TimeoutExpired:
            return {"durum": "belirsiz", "mesaj": f"Cursor ajanı {zaman_asimi} sn içinde bitmedi", "olcumler": []}
        except OSError as e:
            return {"durum": "belirsiz", "mesaj": f"Cursor CLI başlatılamadı: {e}", "olcumler": []}
        cikti = p.stdout.decode("utf-8", "replace")
        try:
            with open(os.path.join(gecici, KIMLIK_DOSYASI), encoding="utf-8") as f:
                kimlik = f.read()
        except OSError:
            kimlik = ""
        sys.path.insert(0, os.path.join(KOK, "scripts"))
        import cursor_kur
        olcumler = degerlendir(cikti, _satirlar(yuk), _satirlar(ayiklama), kimlik, os.path.isdir(cursor_kur.varsayilan_hedef()))
        durumlar = [d for _, d, _ in olcumler]
        durum = "basarisiz" if "basarisiz" in durumlar else ("belirsiz" if "belirsiz" in durumlar else "gecti")
        ozet = "; ".join(f"{a}: {d}" for a, d, _ in olcumler)
        sonuc = {"durum": durum, "mesaj": "Cursor sondası: " + ozet,
                 "olcumler": [{"ad": a, "durum": d, "ayrinti": y} for a, d, y in olcumler]}
        if durum != "gecti":  # kanıt eksikse ajanın söylediği tanı için görünür kalır (kanıt sayılmaz)
            sonuc["ajan_cikti"] = (cikti.strip() or p.stderr.decode("utf-8", "replace").strip())[:600]
        return sonuc
    finally:
        shutil.rmtree(gecici, ignore_errors=True)
