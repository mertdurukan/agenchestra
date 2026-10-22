"""Salt okuma ölçüm betiği iskeleti üretir (T0).

Kullanım:
  python -I iskelet.py --klasor <calisma_dizini>/<konu>_<YYYYMMDD> --ad v1_konu --soru "..." [--hipotez "..."] [--zaman-asimi 600]
Üretilen betik:
  python -I <klasör>\\<ad>.py <db.py klasörü (proje dışı)> <klasör>\\ciktilar [şema ...]
İskelet olduğu gibi çalışır (yalnız ortam ve saat sorgusu); asıl sorguları T3 (sorgu tasarımı) SORGULAR'a yazar.
Var olan dosyanın üstüne yazmaz.
"""
import argparse, json, os, sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

SABLON = '''"""{ad} — {soru}
Hipotez: {hipotez}
Salt okuma. Çalıştırma: python -I {ad}.py <db.py klasörü (proje dışı)> <çıktı klasörü> [şema ...]
Güvenli saat: ortamın ayardaki yasak_saatler aralıkları dışı. Önce: db-olcum skill'inin kapi.py kapı denetimi
Üretildi: {tarih} (db-olcum iskeleti)
"""
import sys, io, csv, os, datetime
sys.path.insert(0, sys.argv[1]); OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
SEMALAR = sys.argv[3:]
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from db import connect, qc  # db.py proje DIŞINDA; asla kopyalama

ZAMAN_ASIMI = {zaman_asimi}
c = connect(timeout_s=ZAMAN_ASIMI)
LOG = []


def saat():
    return datetime.datetime.now().strftime('%H:%M:%S')


def log(m):
    s = f"[{{saat()}}] {{m}}"; print(s, flush=True); LOG.append(s)


def safe(etiket, sql, params=None):
    """Tek sorgu; hata olursa boş döner, betik durmaz. VPN koptuysa dur."""
    try:
        return qc(c, sql, params)
    except Exception as e:
        ilk = str(e).splitlines()[0][:200]
        log(f"{{etiket}} HATA: {{ilk}}")
        if 'could not translate host name' in ilk or 'server closed the connection' in ilk:
            log("Bağlantı/VPN koptu: o ana kadarki çıktılar yazılıyor ve durduruluyor.")
            yaz_meta(); sys.exit(2)
        return [], []


def var_mi(s, t):
    return qc(c, "select to_regclass(%s) is not null", (f'"{{s}}".{{t}}',))[1][0][0]


def yaklasik_satir(s, t):
    """Büyük tablolarda count(*) yerine pg_class.reltuples (boş kararı için count(*) kullan)."""
    _, r = safe('reltuples', "select reltuples::bigint from pg_class where oid = to_regclass(%s)", (f'"{{s}}".{{t}}',))
    return r[0][0] if r else None


def dok(ad, kolonlar, satirlar):
    with open(os.path.join(OUT, ad), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(kolonlar); w.writerows(satirlar)
    log(f"-> {{ad}} {{len(satirlar)}} satır")


def yaz_meta():
    with open(os.path.join(OUT, '{ad}_kosu.txt'), 'w', encoding='utf-8') as f:
        f.write("\\n".join(LOG) + "\\n")


# --- Ortam ve saat (her çıktı sorgu saatiyle yazılır) ---
_, r = safe('ortam', "select current_database(), now()::timestamp(0), current_setting('default_transaction_read_only')")
if r:
    log(f"db={{r[0][0]}} sunucu_saati={{r[0][1]}} salt_okuma={{r[0][2]}}")
    if r[0][2] != 'on':
        log("Oturum salt okuma değil: durduruldu."); yaz_meta(); sys.exit(3)
{senkron_blok}
# --- Sorgular (T3 doldurur). Kurallar: yalnız SELECT/EXPLAIN/katalog; customer_id, e-posta, sır kolonları yok;
#     büyük tabloda LIMIT ya da tarih aralığı; şema döngüsünde var_mi() ile tablo kontrolü. ---
SORGULAR = {{
    # 'etiket': \'\'\'select ... from "{{s}}".tablo ...\'\'\',   # {{s}} = şema
}}

for s in SEMALAR or [None]:
    for etiket, sql in SORGULAR.items():
        log(f"{{s or '-'}} {{etiket}}")
        kolonlar, satirlar = safe(etiket, sql.replace('{{s}}', s) if s else sql)
        if kolonlar:
            dok(f"{ad}_{{etiket}}{{'_' + s if s else ''}}.csv", ['sorgu_saati'] + kolonlar,
                [(saat(),) + tuple(x) for x in satirlar])

log("bitti")
yaz_meta()
c.close()
'''


def senkron_blok(proje):
    """Ayarda senkron_kullanici varsa o hesabın aktif sorgusunu uyarı olarak denetleyen kod parçası; yoksa boş."""
    kok = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
    kullanici = ''
    for yol in (os.path.join(kok, 'ayarlar', 'db_olcum.json'), os.path.join(proje, '.claude', 'orkestra', 'db_olcum.json')):
        try:
            with open(yol, encoding='utf-8-sig') as f:
                kullanici = json.load(f).get('senkron_kullanici', kullanici)
        except (OSError, ValueError, AttributeError):
            pass
    if not kullanici or not all(c.isalnum() or c in '_.-' for c in kullanici):
        return ''
    return ("_, r = safe('senkron', \"select count(*) from pg_stat_activity where usename = '" + kullanici + "' and state = 'active'\")\n"
            "if r and r[0][0]:\n"
            "    log(f\"UYARI: senkron hesabının {r[0][0]} aktif sorgusu var (sayılar değişiyor olabilir)\")\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--klasor', required=True)
    ap.add_argument('--ad', required=True, help='betik adı, uzantısız (ör. v1_ml_cokus)')
    ap.add_argument('--soru', required=True)
    ap.add_argument('--hipotez', default='(T3 yazar)')
    ap.add_argument('--zaman-asimi', type=int, default=300, help='tek sorgu üst sınırı, sn')
    a = ap.parse_args()
    if not a.ad.replace('_', '').isalnum():
        sys.exit("--ad yalnız harf, rakam ve _ içermeli")
    os.makedirs(a.klasor, exist_ok=True)
    yol = os.path.join(a.klasor, a.ad + '.py')
    if os.path.exists(yol):
        sys.exit(f"Var: {yol} (üstüne yazılmaz; yeni ad ver)")
    import datetime
    with open(yol, 'w', encoding='utf-8') as f:
        f.write(SABLON.format(ad=a.ad, soru=a.soru.replace('"""', "'"), hipotez=a.hipotez.replace('"""', "'"),
                              zaman_asimi=a.zaman_asimi, tarih=datetime.date.today().isoformat(),
                              senkron_blok=senkron_blok(os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))))
    print(yol)


if __name__ == '__main__':
    main()
