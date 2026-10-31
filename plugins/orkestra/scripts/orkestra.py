"""orkestra — görev kartları, ortak defter, token defteri ve perspektif için komut satırı aracı.

Kullanım (ajanlar Bash'ten çağırır; `orkestra` plugin bin/ ile PATH'tedir):
  orkestra baslat                                   bu projede durum klasörünü açar
  orkestra kart yeni --baslik T --soru "kartın cevaplayacağı tek soru" --basamak T2 [--sinif S] [--girdi M] [--kabul K]... [--yazma GLOB]... [--bagimli G-001]...
                     [--test-komutu M] [--test-alani GLOB]...     (--sinif kod ise ikisi ZORUNLU; glob proje köküne göre)
                     [--test-koku MUTLAK_DIZIN]                    (kod kartı, isteğe bağlı: test kökü proje yerine bu dizin)
                     [--genislet-onay]   (analiz kartında geniş tarama uyarısını kullanıcı onayıyla kaldırır; --soru ZORUNLU, tek cümle)
  orkestra kart toplu plan.json | --json-dosya plan.json   (liste: [{baslik, basamak, kabul_kriterleri, yazma_alani, bagimliliklar,
                                                    test_komutu, test_alani, ...}])
  orkestra kart goster G-001 | liste [--hepsi] [--json]
  orkestra kart durum G-001 isleniyor|is-bitti|beklemede|iptal|planlandi [--ozet M] [--cikti YOL]... [--not M]
  orkestra kart test-kos G-001 --asama kirmizi|yesil [--zaman-asimi SN]     (kod kartı; geçti → 0, geçmedi → 4)
        kirmizi: kod yokken test BAŞARISIZ olmalı; olursa test dosyaları sha256 ile kilitlenir (kilitliyken hata)
        yesil:   test GEÇMELİ ve test dosyaları kilitle birebir aynı olmalı
  orkestra kart test-kilit-ac G-001 --neden M                                (yalnız ana ajan)
  orkestra kart test-ayar G-001 [--test-koku YOL] [--test-komutu M] [--test-alani GLOB]...   (yalnız ana ajan;
        kilitliyken yalnız test_koku değişir ve yeni kökteki test dosyaları kilitle birebir aynı olmalı)
  orkestra kart denetim G-001 --karar onay|ret --gerekce M [--talimat M]      (yalnız denetçi ajan;
        kod kartında onay için son is-bitti'den sonraki en son test koşusu geçen yeşil olmalı ve dosyalar kilitle aynı)
  orkestra kart yukselt G-001 --basamak T3 --neden M
  orkestra kart teslim G-001 [--ozet M]                                        (yalnız ana ajan, onaylı kart)
  orkestra kart agac G-001 [--taban HEAD]         kart başına git çalışma ağacı (<depo>/.claude/worktrees/kart-<id>; ORKESTRA_AGAC_KOKU varsa
        <kök>/<depo-adı>/kart-<id>; dal kart/<id>). İptalde temiz ağaç kaldırılır (force yok)
  orkestra kart agac-temizle [--uygula]          biten/kartsız kart ağaçlarını listeler (--uygula: kaldırır; kirli ağaç atlanır)
  orkestra kart birlestir G-001                  kart dalını --no-ff birleştirir; çatışmada geri alır, kart beklemede
  orkestra defter ekle G-001 --surec is [--yaptim M] [--sonuc M] [--not M]
  orkestra defter baglam G-001 [--max 2000]     ihtiyacın olan kayıtlar: kart + bağımlılıklar + aynı kartın geçmişi
  orkestra defter oku [--gorev G] [--son N] | ozet
  orkestra maliyet rapor [--gun N] [--md|--csv] [--cikti YOL] | ozet [--json] | anomali [--gun N] [--json] | yeniden-etiketle [--uygula]
  orkestra hata en-cok [--gun N] [--kaynak hook|cli|ozet|kart|kural] [--ilk N] [--json] | liste [--ilk N] [--json]   tekrar eden hatalar (salt okuma)
  orkestra onbellek kacak [--gun N] [--defter] [--olay] [--json]   önbellek kaçaklarını sınıfla (5 dk katman, model, boşluk, sıkıştırma) ve USD ile dök
  orkestra iz <istek_id|I-nnn|oturum> [--json|--csv] | iz kapsama [--json]   süre/token ağacı (toplam = defter) ve atıf kapsama ölçümü
  orkestra perspektif durum | basla | bitti | dogrula <rapor> | duzeltme-tara [klasör]   (dogrula: rapordaki Kanıt satırlarını yeniden hesaplar, tutmayan varsa çıkış 1; duzeltme-tara: hafızada tekrar eden düzeltme notları, bulgu varsa çıkış 1)
  orkestra gunluk ozet [--gun 7]
  orkestra onay liste [--durum D] [--tur T] [--json] | goster ID | iste --baslik B --metin M [--secenek S]... [--oturum O]
  orkestra onay karar ID (--onay|--ret) [--secim S] [--not N] | al ID [--oturum O] | uygulandi ID --ozet Z | iptal ID --not N | esitle
  orkestra kural liste [--json] [--katman proje|plugin] | oner --metin M [--neden N] | ekle --metin M [--neden N] [--katman proje|plugin] | duzenle ID --metin M | kaldir ID --not N
  orkestra kural tasi ID --katman proje|plugin [--kimligi-koru] | kapat ID [--not N] | ac ID | esitle   (katmanlar: KURALLAR.md, Kural katmanları)
  orkestra standart liste | goster AD | yol AD | ekle AD   (ekip yapı standartları: PR, commit, dal, review, Jira yorumu; ADR-0006)
  orkestra niyet --ne "şu an ne yapılıyor" --neden "neye yarayacak" | --sonuc "ne çıktı" | --goster   (yalnız ana ajan)
  orkestra is istek I-nnn [--mesaj-dosya DOSYA | --mesaj METİN] [--talep METİN]...   kullanıcı mesajındaki bağlantıları ve taleplerini istek_defteri.md'ye R1…Rn yazar (ADR-0112)
  orkestra is dalga I-nnn|KLASÖR|plan.md [--yaz] [--json-cikti DOSYA] [--basamak T2]   plan → dalgalar, kritik yol, `## Dalgalar`, kart JSON'u
  orkestra plan dogrula I-nnn|PLAN.md [--yaz] [--json] [--kok DİZİN]... [--komut-kosma] [--ac]   (plan.md iddialarını kanıtla doğrular, ✅/❌ koyar;
        çıkış 0 uygulanabilir, 1 koşullu, 2 uygulanamaz, 3 tamamlanmamış)
`--ajan-id/--ajan-tipi` argümanlarını PreToolUse hook'u ekler; elle verilenler silinir.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import hashlib
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import ret_nedeni as RN  # noqa: E402
import soru_sinif as SS  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from komutlar import _ortak, kurulum, kart, defter, maliyet, onay, gosterge, isler, teknik, saglik, plan, izin, iz, politika, bakim, harita, standart, kimlik, mcp, push_kapisi, ara, isabet, onbellek, durum, kanit, ortam  # noqa: E402
from komutlar import hata as hata_komut  # noqa: E402  (ad `_ortak.hata` işlevini gölgelemesin)
from komutlar import plan_alan  # noqa: E402  (`plan` grubuna `alan` ekler; plan'dan sonra kaydedilir)
from komutlar import dalga  # noqa: E402  (`is dalga`; isler'den SONRA kaydedilir)
from komutlar import adr  # noqa: E402  (`orkestra adr`; ADR-0097)
from komutlar import istek  # noqa: E402  (`is istek`; ADR-0112, isler'den SONRA kaydedilir)
from komutlar import kapi  # noqa: E402  (`orkestra kapi durum`; ADR-0095)

# Kayıt sırası = `--help` sırası.
MODULLER = (kurulum, kart, defter, maliyet, onay, gosterge, isler, teknik, saglik, plan, izin, iz, politika, bakim, harita, standart, kimlik, mcp, push_kapisi, ara, isabet, onbellek, durum, kanit, ortam, hata_komut, plan_alan, dalga, adr, istek)

# Geriye uyum: eski `orkestra.<ad>` erişimleri (testler, betikler) modüllerden yeniden dışa aktarılır.
for _m in (_ortak,) + MODULLER:
    for _ad, _deger in vars(_m).items():
        if not _ad.startswith("__") and _ad not in globals():
            globals()[_ad] = _deger


def main():
    p = argparse.ArgumentParser(prog="orkestra", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ajan-id", dest="ajan_id", help=argparse.SUPPRESS)
    p.add_argument("--ajan-tipi", dest="ajan_tipi", help=argparse.SUPPRESS)
    alt = p.add_subparsers(dest="komut", required=True)

    for _m in MODULLER:
        _m.kaydet(alt)

    # Hook, kimlik argümanlarını komutun SONUNA ekler; argparse'tan önce her yerden ayıkla.
    argv, kimlik = [], {}
    it = iter(sys.argv[1:])
    for x in it:
        if x in ("--ajan-id", "--ajan-tipi"):
            kimlik[x] = next(it, "")
        elif x.startswith(("--ajan-id=", "--ajan-tipi=")):
            k, v = x.split("=", 1)
            kimlik[k] = v
        else:
            argv.append(x)
    a = p.parse_args(argv)
    a.ajan_id = kimlik.get("--ajan-id") or None
    a.ajan_tipi = kimlik.get("--ajan-tipi") or None
    a.f(a)
    # Durumu değiştiren komutlardan sonra arayüz anlık görüntüsünü yenile.
    alt_komut = getattr(a, "alt", None)
    degistiren = {"kart", "perspektif", "ruya", "baslat"}
    if a.komut in degistiren or (a.komut, alt_komut) in {("defter", "ekle"), ("maliyet", "tur"), ("maliyet", "gecmis"), ("maliyet", "yeniden-etiketle")}:
        sd = L.durum_dizini()
        if sd and not (a.komut == "kart" and alt_komut in ("goster", "liste")):
            import ozet
            ozet.yaz(sd, L.proje_dizini())
    if a.komut in ("is", "plan"):
        # İş belgelerini yazan komutlardan sonra belgeleri commit et (ORKESTRA_OTO_COMMIT açıksa); komutu bozmaz.
        try:
            sd = L.durum_dizini()
            if sd:
                import is_kaydi
                import oto_commit
                oto_commit.cli_sonrasi([g.get("klasor") for g in is_kaydi.is_liste(sd)])
        except Exception:
            pass


if __name__ == "__main__":
    main()
