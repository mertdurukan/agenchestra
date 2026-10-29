"""postgres-mcp sarmalayıcısı (scripts/postgres_mcp.py): kapı, parola, salt okunur oturum, izleyici, izin kuralı.

Canlı test (kopya sunucuda gerçek INSERT/UPDATE/CREATE reddi) yalnız ORKESTRA_POSTGRES_CANLI=1 iken koşar; VPN ve
17:15 öncesi/23:15 sonrası saat ister (db-olcum kapısı).
"""
import importlib
import json
import os
import re
import subprocess
import sys
import threading

import pytest

EKLENTI = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(EKLENTI, "scripts"))
pm = importlib.import_module("postgres_mcp")

SIR = "P@ss/w:rd#1?x"


class SahteSurec:
    pid = 1

    def __init__(self):
        self.oldu = False

    def poll(self):
        return 0 if self.oldu else None


def ayar_ornek():
    return {"ortam": "kopya", "kapi": True, "kimlik_servisi": "db", "veritabani": "klibre", "sslmode": "require",
            "anahtarlar": {"host": "H", "port": "P", "kullanici": "U", "parola": "S"},
            "sunucu_komutu": ["postgres-mcp", "--access-mode=restricted"]}


DEGERLER = {"H": "sunucu.example", "P": "5432", "U": "kullanici@sunucu", "S": SIR}


def test_uri_salt_okunur_ve_parola_kodlanir():
    uri = pm.uri_kur(ayar_ornek(), DEGERLER.__getitem__)
    assert "default_transaction_read_only%3Don" in uri
    assert "sslmode=require" in uri
    assert SIR not in uri  # özel karakterler yüzde-kodlanır
    assert re.match(r"^postgresql://kullanici%40sunucu:[^@/?#]+@sunucu\.example:5432/klibre\?", uri)


def test_ayar_restricted_olmadan_reddedilir():
    a = ayar_ornek()
    a["sunucu_komutu"] = ["postgres-mcp", "--access-mode=unrestricted"]
    with pytest.raises(SystemExit):
        pm.ayar_denetle(a)


def test_ayar_eksik_reddedilir():
    a = ayar_ornek()
    a["veritabani"] = ""
    with pytest.raises(SystemExit):
        pm.ayar_denetle(a)


def test_database_uri_ile_kimlik_ve_kapi_olmadan_baslar(monkeypatch, capsys):
    a = {"ortam": "kopya", "kimlik_servisi": "", "anahtarlar": {}, "veritabani": "", "kapi": False,
         "sunucu_komutu": ["postgres-mcp", "--access-mode=restricted"]}
    monkeypatch.setenv("DATABASE_URI", "postgresql://u:p@h/d")
    monkeypatch.setattr(pm, "ayar_oku", lambda proje=None: a)
    monkeypatch.setattr(pm, "kapi_gecti", lambda *x: pytest.fail("kapı çağrılmamalı"))
    monkeypatch.setattr(pm, "kimlik_degeri", lambda ayar: pytest.fail("kimlik okunmamalı"))
    monkeypatch.setattr(pm.shutil, "which", lambda ad: "/bin/postgres-mcp")
    yakalanan = {}

    class P(SahteSurec):
        def __init__(self, komut, env=None, **k):
            super().__init__()
            yakalanan["env"] = env

        def wait(self):
            return 0

    monkeypatch.setattr(pm.subprocess, "Popen", P)
    monkeypatch.setattr(pm, "sonlandir", lambda proc: None)
    assert pm.main() == 0
    assert "default_transaction_read_only=on" in yakalanan["env"]["PGOPTIONS"]


def test_kapi_kapaliyken_kapi_cagrilmaz(monkeypatch):
    a = ayar_ornek()
    a["kapi"] = False
    monkeypatch.setattr(pm, "ayar_oku", lambda proje=None: a)
    monkeypatch.setattr(pm, "kapi_gecti", lambda *x: pytest.fail("kapı çağrılmamalı"))
    monkeypatch.setattr(pm, "kimlik_degeri", lambda ayar: DEGERLER.__getitem__)
    monkeypatch.setattr(pm.shutil, "which", lambda ad: "/bin/postgres-mcp")

    class P(SahteSurec):
        def __init__(self, *a, **k):
            super().__init__()

        def wait(self):
            return 0

    monkeypatch.setattr(pm.subprocess, "Popen", P)
    monkeypatch.setattr(pm, "sonlandir", lambda proc: None)
    assert pm.main() == 0


def _yazma_calistir(monkeypatch, **ayar_ek):
    a = {**ayar_ornek(), **ayar_ek}
    monkeypatch.setattr(pm, "ayar_oku", lambda proje=None: a)
    monkeypatch.setattr(pm, "kapi_gecti", lambda *x: (True, "geçti"))
    monkeypatch.setattr(pm, "kimlik_degeri", lambda ayar: DEGERLER.__getitem__)
    monkeypatch.setattr(pm.shutil, "which", lambda ad: "/bin/postgres-mcp")
    yakalanan = {}

    class P(SahteSurec):
        def __init__(self, komut, env=None, **k):
            super().__init__()
            yakalanan["komut"], yakalanan["env"] = komut, env

        def wait(self):
            return 0

    monkeypatch.setattr(pm.subprocess, "Popen", P)
    monkeypatch.setattr(pm, "sonlandir", lambda proc: None)
    return yakalanan


def test_yazma_izni_yoksa_yazma_sunucusu_baslamaz(monkeypatch):
    yak = _yazma_calistir(monkeypatch)
    with pytest.raises(SystemExit) as e:
        pm.main(["--yazma"])
    assert e.value.code == 4 and yak == {}


def test_prod_ortaminda_yazma_sunucusu_baslamaz(monkeypatch):
    yak = _yazma_calistir(monkeypatch, yazma_izni=True, ortam="prod")
    with pytest.raises(SystemExit) as e:
        pm.main(["--yazma"])
    assert e.value.code == 4 and yak == {}


def test_yazma_sunucusu_unrestricted_ve_salt_okunursuz(monkeypatch):
    yak = _yazma_calistir(monkeypatch, yazma_izni=True)
    assert pm.main(["--yazma"]) == 0
    assert "--access-mode=unrestricted" in yak["komut"] and "--access-mode=restricted" not in yak["komut"]
    assert "default_transaction_read_only" not in yak["env"]["DATABASE_URI"]
    assert "statement_timeout" in yak["env"]["DATABASE_URI"] or "statement_timeout%3D60000" in yak["env"]["DATABASE_URI"]


def test_okuma_sunucusu_yazma_izni_olsa_da_restricted(monkeypatch):
    yak = _yazma_calistir(monkeypatch, yazma_izni=True)
    assert pm.main([]) == 0
    assert "--access-mode=restricted" in yak["komut"]
    assert "default_transaction_read_only%3Don" in yak["env"]["DATABASE_URI"]


def test_kapi_kaldi_ise_sunucu_baslatilmaz(monkeypatch, capsys):
    monkeypatch.setattr(pm, "ayar_oku", lambda proje=None: ayar_ornek())
    monkeypatch.setattr(pm, "kapi_gecti", lambda ortam, proje=None: (False, "[KALDI] saat penceresi: 18:00"))
    cagri = []
    monkeypatch.setattr(pm.subprocess, "Popen", lambda *a, **k: cagri.append(a))
    with pytest.raises(SystemExit) as e:
        pm.main()
    assert e.value.code == 3
    assert cagri == []
    assert "KALDI" in capsys.readouterr().err


def test_parola_komut_satirinda_ve_ciktida_yok(monkeypatch, capsys):
    monkeypatch.setattr(pm, "ayar_oku", lambda proje=None: ayar_ornek())
    monkeypatch.setattr(pm, "kapi_gecti", lambda ortam, proje=None: (True, "geçti"))
    monkeypatch.setattr(pm, "kimlik_degeri", lambda ayar: DEGERLER.__getitem__)
    monkeypatch.setattr(pm.shutil, "which", lambda ad: "/bin/postgres-mcp")
    yakalanan = {}

    class P(SahteSurec):
        def __init__(self, komut, env=None, **k):
            super().__init__()
            yakalanan["komut"], yakalanan["env"] = komut, env

        def wait(self):
            return 0

    monkeypatch.setattr(pm.subprocess, "Popen", P)
    monkeypatch.setattr(pm, "sonlandir", lambda proc: None)
    assert pm.main() == 0
    assert SIR not in " ".join(yakalanan["komut"])
    assert "--access-mode=restricted" in yakalanan["komut"]
    assert "DATABASE_URI" in yakalanan["env"]
    out = capsys.readouterr()
    assert SIR not in out.out + out.err


def test_izleyici_kaldi_olunca_sureci_sonlandirir(monkeypatch):
    proc = SahteSurec()
    monkeypatch.setattr(pm, "sonlandir", lambda p: setattr(p, "oldu", True))
    sonuc = pm.izle(proc, "kopya", 0.01, "x", threading.Event(), kapi=lambda o, p: (False, "[KALDI] saat"))
    assert sonuc is True and proc.oldu


def test_izleyici_kapi_gecerse_dokunmaz(monkeypatch):
    proc = SahteSurec()
    durdur = threading.Event()
    sayac = {"n": 0}

    def kapi(o, p):
        sayac["n"] += 1
        if sayac["n"] == 3:
            durdur.set()
        return True, "geçti"

    assert pm.izle(proc, "kopya", 0.01, "x", durdur, kapi=kapi) is False
    assert not proc.oldu


def _kapi_calistir(tmp_path, saat):
    ayar = tmp_path / ".claude" / "orkestra"
    ayar.mkdir(parents=True, exist_ok=True)
    (ayar / "db_olcum.json").write_text(json.dumps(
        {"ortamlar": {"kopya": {"host": "", "port": 5432, "yasak_saatler": [["17:15", "23:15"]]}}}), encoding="utf-8")
    return subprocess.run([sys.executable, "-I", pm.KAPI, "--ortam", "kopya", "--ag-atla", "--saat", saat,
                           "--proje", str(tmp_path)], capture_output=True, text=True, encoding="utf-8").returncode


def test_gercek_kapi_yasak_saatte_kaldi_verir(tmp_path):
    assert _kapi_calistir(tmp_path, "18:00") == 1


def test_gercek_kapi_pencere_sinirlari(tmp_path):
    assert _kapi_calistir(tmp_path, "17:14") == 0
    assert _kapi_calistir(tmp_path, "17:16") == 1


def test_izin_kurali_okuma_ve_execute_sql_ayrimi():
    with open(os.path.join(EKLENTI, "ayarlar", "izin_politikasi.json"), encoding="utf-8") as f:
        kural = next(k for k in json.load(f)["mcp"] if "postgres-mcp" in k["ad"])
    okuma = ["list_schemas", "list_objects", "get_object_details", "explain_query", "analyze_db_health",
             "analyze_query_indexes"]
    for ad in okuma:
        arac = "mcp__plugin_orkestra_postgres__" + ad
        assert re.search(kural["arac"], arac) and re.search(kural["okuma"], arac), ad
    arac = "mcp__plugin_orkestra_postgres__execute_sql"
    assert re.search(kural["arac"], arac) and not re.search(kural["okuma"], arac)


@pytest.mark.skipif(os.environ.get("ORKESTRA_POSTGRES_CANLI") != "1", reason="canlı kopya testi; ORKESTRA_POSTGRES_CANLI=1")
def test_canli_kopyada_yazma_reddedilir_select_gecer():
    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2 import errors
    ayar = pm.ayar_oku()
    pm.ayar_denetle(ayar)
    gecti, ozet = pm.kapi_gecti(ayar.get("ortam", "kopya"))
    assert gecti, ozet
    c = psycopg2.connect(pm.uri_kur(ayar, pm.kimlik_degeri(ayar)), connect_timeout=15)
    try:
        cur = c.cursor()
        cur.execute("select 1")
        assert cur.fetchone() == (1,)
        cur.execute("show transaction_read_only")
        assert cur.fetchone() == ("on",)
        c.rollback()
        with pytest.raises(errors.ReadOnlySqlTransaction):
            cur.execute("create table postgres_mcp_deneme(x int)")
        c.rollback()
        # INSERT ve UPDATE: kullanıcının yazma yetkisi olduğu bir tablo seçilir (yetki hatası ret sayılmaz)
        cur.execute(
            "select p.table_schema, p.table_name, k.column_name from information_schema.table_privileges p "
            "join information_schema.table_privileges u on u.table_schema = p.table_schema and u.table_name = p.table_name "
            "and u.grantee = p.grantee and u.privilege_type = 'UPDATE' "
            "join information_schema.columns k on k.table_schema = p.table_schema and k.table_name = p.table_name "
            "where p.grantee = current_user and p.privilege_type = 'INSERT' "
            "and p.table_schema not in ('pg_catalog', 'information_schema') limit 1")
        satir = cur.fetchone()
        c.rollback()
        if not satir:
            pytest.skip("kullanıcının INSERT+UPDATE yetkisi olduğu tablo yok; yalnız CREATE reddi sınandı")
        sema, tablo, kolon = satir
        for sql in (f'insert into "{sema}"."{tablo}" default values',
                    f'update "{sema}"."{tablo}" set "{kolon}" = "{kolon}" where false'):
            with pytest.raises(errors.ReadOnlySqlTransaction):
                cur.execute(sql)
            c.rollback()
    finally:
        c.close()


@pytest.mark.skipif(os.environ.get("ORKESTRA_POSTGRES_CANLI") != "1", reason="canlı kopya testi; ORKESTRA_POSTGRES_CANLI=1")
def test_canli_yazma_modunda_gecici_tabloda_insert_update_delete():
    psycopg2 = pytest.importorskip("psycopg2")
    ayar = pm.ayar_oku()
    pm.ayar_denetle(ayar)
    assert ayar.get("ortam", "kopya") != "prod"
    gecti, ozet = pm.kapi_gecti(ayar.get("ortam", "kopya"))
    assert gecti, ozet
    c = psycopg2.connect(pm.uri_kur(ayar, pm.kimlik_degeri(ayar), yazma=True), connect_timeout=15)
    try:
        cur = c.cursor()
        cur.execute("show transaction_read_only")
        assert cur.fetchone() == ("off",)
        cur.execute("create temp table postgres_mcp_yazma_deneme(x int)")  # oturumla gider, kalıcı iz bırakmaz
        cur.execute("insert into postgres_mcp_yazma_deneme values (1), (2)")
        assert cur.rowcount == 2
        cur.execute("update postgres_mcp_yazma_deneme set x = x + 10 where x = 1")
        assert cur.rowcount == 1
        cur.execute("delete from postgres_mcp_yazma_deneme")
        assert cur.rowcount == 2
        c.rollback()
    finally:
        c.close()
