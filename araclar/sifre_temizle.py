"""Oturum kayıtlarından düz metin bir şifreyi temizler (kullanıcının kendisi çalıştırır).

Neden ayrı araç: Claude'un otomatik izin denetimi oturum kayıtlarını değiştirmeyi (haklı olarak) engeller;
bu temizliği yalnız sen, bilerek yaparsın.

Kullanım (PowerShell ya da cmd):
    python araclar/sifre_temizle.py            # önce yalnız sayar
    python araclar/sifre_temizle.py --uygula    # sonra temizler

Şifre ekrana yazılmadan sorulur (getpass). Taranan yerler: ~/.claude (oturum kayıtları, görev çıktıları,
dosya geçmişi), %LOCALAPPDATA%\\Temp\\claude (scratchpad'ler), %APPDATA%\\Claude.
Çalışan bağlantı dosyalarına (db.py ve .pyc) DOKUNULMAZ; onları da temizlemek için --db-dahil ver
(o zaman o db.py'ler çalışmaz, şifreyi ortam değişkenine taşıman gerekir).
Asıl çözüm şifreyi değiştirmektir: temizlik yalnız eski izleri siler.
"""
import argparse
import getpass
import os
import sys

YER_TUTUCU = b"[SIFRE-SILINDI]"


def kokler():
    ev = os.path.expanduser("~")
    return [
        os.path.join(ev, ".claude"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp", "claude"),
        os.path.join(os.environ.get("APPDATA", ""), "Claude"),
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--uygula", action="store_true", help="dosyaları yerinde temizle (yoksa yalnız sayar)")
    p.add_argument("--db-dahil", action="store_true", help="db.py ve .pyc dosyalarını da temizle")
    a = p.parse_args()
    sir = getpass.getpass("Temizlenecek şifre (ekranda görünmez): ").strip()
    if len(sir) < 6:
        sys.exit("Şifre en az 6 karakter olmalı (yanlış eşleşmeyi önlemek için).")
    igne = sir.encode("utf-8")
    bulunan, atlanan, temizlenen = 0, 0, 0
    for kok in kokler():
        if not os.path.isdir(kok):
            continue
        for dp, dn, fn in os.walk(kok):
            for ad in fn:
                yol = os.path.join(dp, ad)
                try:
                    if os.path.getsize(yol) > 300 * 1024 * 1024:
                        continue
                    with open(yol, "rb") as f:
                        b = f.read()
                except OSError:
                    continue
                n = b.count(igne)
                if not n:
                    continue
                bulunan += 1
                db_dosyasi = ad == "db.py" or ad.endswith(".pyc")
                if db_dosyasi and not a.db_dahil:
                    atlanan += 1
                    print(f"  atlandı (bağlantı dosyası): {yol}")
                    continue
                print(f"  {n:3d} geçiş: {yol}")
                if a.uygula:
                    try:
                        with open(yol, "wb") as f:
                            f.write(b.replace(igne, YER_TUTUCU))
                        temizlenen += 1
                    except OSError as e:
                        print(f"     yazılamadı ({e}); dosya açık olabilir, Claude'u kapatıp yeniden dene")
    print(f"\nŞifre {bulunan} dosyada bulundu; {atlanan} bağlantı dosyası atlandı; "
          + (f"{temizlenen} dosya temizlendi." if a.uygula else "temizlemek için --uygula ile yeniden çalıştır."))
    print("Hatırlatma: şifreyi Azure tarafında değiştir; eski değer artık hiçbir yerde geçerli olmasın.")


if __name__ == "__main__":
    main()
