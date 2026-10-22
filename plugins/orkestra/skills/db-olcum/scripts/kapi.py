"""DB ölçümü öncesi kapı denetimi (T0, DB'ye bağlanmaz).

Denetler:
  1. Saat penceresi  — ortamın ayardaki yasak_saatler aralıkları dışında mı (ör. kopya senkron penceresi);
                       --seviye agir ise ayardaki mesai içinde hafta içi UYARI.
  2. Ağ / VPN        — sistem çözümleyicisiyle DNS (Resolve-DnsName'in kullandığı yol; nslookup değil)
                       ve ayardaki porta TCP bağlantısı (Test-NetConnection eşdeğeri). Host ayarda yoksa UYARI.
  3. Kimlik dosyası  — --db-py klasöründe kimlik dosyası (ayarda kimlik_dosyasi, varsayılan db.py) var mı, klasör
                       proje DIŞINDA mı; projede aynı adlı dosya kalmış mı.
  4. SQL denetimi    — --sql-denetim dosyasındaki SQL metinleri yazma/DDL kalıbı (yasak_komut_kalibi) ve
                       kişisel veri / sır kolon kalıpları (yasak_kolon_kaliplari) için taranır.
  5. Çıktı taraması  — --cikti-tara klasöründeki metin dosyalarında parola/anahtar/token/e-posta kalıbı (değer yazılmaz).

Ayar: eklenti ayarlar/db_olcum.json varsayılanı + proje .claude/orkestra/db_olcum.json ezmesi
(`--ayar` birleşik ayarı yazar). Proje kökü: CLAUDE_PROJECT_DIR ya da çalışma klasörü.

Kullanım:
  python -I kapi.py --ortam kopya [--db-py <klasör>] [--sql-denetim <betik.py|.sql> ...] [--saat HH:MM] [--ag-atla]
  python -I kapi.py --ortam prod --seviye agir --ag-atla --saat 23:30
  python -I kapi.py --ag-atla --cikti-tara <calisma_dizini>/<konu>_<YYYYMMDD>
Çıkış kodu: 0 = geçti (uyarı olabilir), 1 = en az bir KALDI.
"""
import argparse, ast, datetime, ipaddress, json, os, re, socket, sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

PROJE = os.path.abspath(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd())
EKLENTI = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
AYAR_AD = 'db_olcum'
ATLA = {'.git', '__pycache__', 'node_modules'}


def ayar_oku(proje=None):
    """Eklenti varsayılanı + proje ezmesi. Üst düzey anahtarlar yerine konur, `ortamlar` ortam ortam birleşir."""
    proje = proje or PROJE
    sonuc = {}
    for yol in (os.path.join(EKLENTI, 'ayarlar', AYAR_AD + '.json'), os.path.join(proje, '.claude', 'orkestra', AYAR_AD + '.json')):
        try:
            with open(yol, encoding='utf-8-sig') as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            if k == 'ortamlar' and isinstance(v, dict):
                mevcut = sonuc.setdefault('ortamlar', {})
                for ad, o in v.items():
                    mevcut[ad] = {**mevcut.get(ad, {}), **o} if isinstance(o, dict) else o
            else:
                sonuc[k] = v
    return sonuc


AYAR = {}


def _saat(metin):
    return datetime.time.fromisoformat(metin)


sonuclar = []


def kayit(durum, konu, mesaj):
    sonuclar.append(durum)
    print(f"[{durum}] {konu}: {mesaj}")


def pencere_uygun(ortam, saat, seviye='hafif', hafta_ici=True, ayar=None):
    """(durum, mesaj). durum: GEÇTİ / UYARI / KALDI. Test edilebilir saf fonksiyon."""
    o = (ayar if ayar is not None else AYAR).get('ortamlar', {}).get(ortam, {})
    for bas, bit in o.get('yasak_saatler', []):
        b, e = _saat(bas), _saat(bit)
        icinde_mi = (b <= saat < e) if b <= e else (saat >= b or saat < e)
        if icinde_mi:
            return 'KALDI', f"{saat:%H:%M} {ortam} ortamında yasak ({bas}–{bit} arası); bu aralığın dışında çalıştır"
    mesai = o.get('mesai')
    if mesai and 'agir' in seviye and hafta_ici and _saat(mesai[0]) <= saat < _saat(mesai[1]):
        return 'UYARI', f"{saat:%H:%M} mesai içi; ağır sorgular {ortam} ortamında mesai dışında çalıştırılmalı"
    return 'GEÇTİ', f"{saat:%H:%M} {ortam} için uygun"


def ag_kontrol(host, port, sure=5):
    try:
        ipler = sorted({a[4][0] for a in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)})
    except socket.gaierror as e:
        kayit('KALDI', 'DNS', f"{host} çözülemedi ({e}); VPN bağlı mı?")
        return
    ozel = all(ipaddress.ip_address(i).is_private for i in ipler)
    kayit('GEÇTİ', 'DNS', f"{host} → {len(ipler)} adres ({'özel ağ' if ozel else 'genel ağ'})")
    try:
        with socket.create_connection((host, port), timeout=sure):
            pass
        kayit('GEÇTİ', 'TCP', f"{host}:{port} erişilebilir")
    except OSError as e:
        kayit('KALDI', 'TCP', f"{host}:{port} bağlanılamadı ({e.__class__.__name__}); VPN'i kontrol et")


def icinde(yol, kok):
    try:
        return os.path.commonpath([os.path.abspath(yol).lower(), kok.lower()]) == kok.lower()
    except ValueError:  # farklı sürücü
        return False


def db_py_kontrol(klasor):
    ad = AYAR.get('kimlik_dosyasi') or 'db.py'
    if klasor:
        p = os.path.join(klasor, ad)
        if not os.path.isfile(p):
            kayit('KALDI', ad, f"{klasor} içinde {ad} yok (önceki oturum scratchpad'ine bak; kullanıcıya sor)")
        elif icinde(klasor, PROJE):
            kayit('KALDI', ad, f"{ad} proje İÇİNDE; proje dışına (scratchpad ya da kimlik klasörü) taşınmalı, projeden silinmeli")
        else:
            kayit('GEÇTİ', ad, "proje dışında")
    bulunan = []
    for dp, dn, fn in os.walk(PROJE):
        dn[:] = [d for d in dn if d not in ATLA]
        if ad in fn:
            bulunan.append(os.path.relpath(os.path.join(dp, ad), PROJE))
    if bulunan:
        kayit('KALDI', f'projede {ad}', ', '.join(bulunan) + " — şifre taşıyabilir, kaldırılmalı")
    else:
        kayit('GEÇTİ', f'projede {ad}', "yok")


def sql_metinleri(yol):
    metin = open(yol, encoding='utf-8', errors='replace').read()
    if yol.lower().endswith('.sql'):
        return [metin]
    out = []
    agac = ast.parse(metin)
    fparca = {id(v) for d in ast.walk(agac) if isinstance(d, ast.JoinedStr) for v in d.values}
    for dugum in ast.walk(agac):
        if id(dugum) in fparca:
            continue
        if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
            s = dugum.value
        elif isinstance(dugum, ast.JoinedStr):  # f-string: sabit parçaları birleştir
            s = ' '.join(v.value for v in dugum.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
        else:
            continue
        low = s.lower()
        if 'select' in low or 'from ' in low or low.strip().startswith(('with', 'set ', 'explain')):
            out.append(s)
    return out


def yasak_kontrol(sql):
    """Yazma/DDL komutu (tırnak içi metin yok sayılır) ya da yasak kolon kalıbı varsa eşleşen kalıbı döndürür."""
    low = sql.lower()
    komutsuz = re.sub(r"'(?:[^']|'')*'", "''", low)
    komut = AYAR.get('yasak_komut_kalibi')
    if komut and re.search(komut, komutsuz):
        return komut
    for pat in AYAR.get('yasak_kolon_kaliplari', []):
        if re.search(pat, low):
            return pat
    return None


def sql_denetim(yollar):
    for yol in yollar:
        metinler = sql_metinleri(yol)
        ihlaller = []
        for s in metinler:
            # SET satırları oturum ayarıdır (statement_timeout, read_only); komut denetimine sokma
            if s.strip().lower().startswith('set '):
                continue
            h = yasak_kontrol(s)
            if h:
                ihlaller.append((h, ' '.join(s.split())[:80]))
        ad = os.path.basename(yol)
        if ihlaller:
            for h, ornek in ihlaller:
                kayit('KALDI', f'SQL {ad}', f"yasak kalıp '{h}' → {ornek}")
        else:
            kayit('GEÇTİ', f'SQL {ad}', f"{len(metinler)} SQL metni temiz")


SIR = {
    'parola': re.compile(r"(?i)(password|pwd|passwd)\s*[=:]\s*[\"']?(?!<|\*|\$|%|\{|null|none)[^\s\"',;|]{4,}"),
    'hesap_anahtari': re.compile(r"(?i)account_?key\s*[=:\"']+\s*[A-Za-z0-9+/]{20,}"),
    'auth_token': re.compile(r"(?i)auth_?token[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9\-_.]{12,}"),
    'bearer': re.compile(r'(?i)bearer\s+[A-Za-z0-9\-_.]{20,}'),
    'e-posta': re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
}


def cikti_tara(klasor):
    """Arşive girecek metin dosyalarında sır / e-posta kalıbı arar; eşleşen değeri yazmaz."""
    bulgu, n = [], 0
    for dp, dn, fn in os.walk(klasor):
        for f in fn:
            if f == (AYAR.get('kimlik_dosyasi') or 'db.py') or not f.lower().endswith(('.md', '.txt', '.csv', '.py', '.sql', '.json', '.log')):
                continue
            n += 1
            metin = open(os.path.join(dp, f), encoding='utf-8', errors='replace').read()
            for ad, rx in SIR.items():
                for m in rx.finditer(metin):
                    if ad == 'e-posta' and '***' in m.group(0):
                        continue
                    bulgu.append(f"{os.path.relpath(os.path.join(dp, f), klasor)} satır {metin.count(chr(10), 0, m.start()) + 1} [{ad}]")
    if bulgu:
        for b in bulgu[:30]:
            kayit('KALDI', 'çıktı taraması', b)
    else:
        kayit('GEÇTİ', 'çıktı taraması', f"{n} dosya temiz")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--ortam', default='kopya', help='ayardaki ortam adı (varsayılan kopya)')
    ap.add_argument('--ayar', action='store_true', help='birleşik ayarı JSON yaz ve çık')
    ap.add_argument('--seviye', default='hafif', help='hafif/orta/agir (prod mesai uyarısı için)')
    ap.add_argument('--saat', help='HH:MM (test için; verilmezse şimdi)')
    ap.add_argument('--db-py', help='kimlik dosyasını (ayarda kimlik_dosyasi) içeren proje DIŞI klasör')
    ap.add_argument('--sql-denetim', nargs='*', default=[], help='taranacak .py/.sql dosyaları')
    ap.add_argument('--ag-atla', action='store_true', help='DNS/TCP denetimini atla')
    ap.add_argument('--cikti-tara', help='arşivlemeden önce sır/e-posta taraması yapılacak klasör')
    ap.add_argument('--proje', help=argparse.SUPPRESS)  # test için proje kökünü değiştir
    a = ap.parse_args()
    global PROJE, AYAR
    if a.proje:
        PROJE = os.path.abspath(a.proje)
    AYAR = ayar_oku()
    if a.ayar:
        print(json.dumps(AYAR, ensure_ascii=False, indent=2))
        return
    if a.ortam not in AYAR.get('ortamlar', {}):
        sys.exit(f"HATA: '{a.ortam}' ortamı ayarda yok (tanımlı: {', '.join(AYAR.get('ortamlar', {})) or 'hiçbiri'}); "
                 f".claude/orkestra/{AYAR_AD}.json içine ekle")

    simdi = datetime.datetime.now()
    saat = datetime.time.fromisoformat(a.saat) if a.saat else simdi.time()
    durum, mesaj = pencere_uygun(a.ortam, saat, a.seviye, simdi.weekday() < 5)
    kayit(durum, 'saat penceresi', mesaj)
    if not a.ag_atla:
        o = AYAR['ortamlar'][a.ortam]
        if o.get('host'):
            ag_kontrol(o['host'], int(o.get('port', 5432)))
        else:
            kayit('UYARI', 'ağ', f"{a.ortam} ortamında host ayarı yok; DNS/TCP denetimi atlandı")
    db_py_kontrol(a.db_py)
    if a.sql_denetim:
        sql_denetim(a.sql_denetim)
    if a.cikti_tara:
        cikti_tara(a.cikti_tara)
    kaldi = sonuclar.count('KALDI')
    print(f"\nSONUÇ: {'KALDI' if kaldi else 'GEÇTİ'} ({kaldi} kaldı, {sonuclar.count('UYARI')} uyarı)")
    sys.exit(1 if kaldi else 0)


if __name__ == '__main__':
    main()
