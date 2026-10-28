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
    return {"ortam": "kopya", "kimlik_servisi": "db", "veritabani": "klibre", "sslmode": "require",
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
    ayar.mkdir(parents=True)
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
    psycopg = pytest.importorskip("psycopg")
    ayar = pm.ayar_oku()
    pm.ayar_denetle(ayar)
    gecti, ozet = pm.kapi_gecti(ayar.get("ortam", "kopya"))
    assert gecti, ozet
    with psycopg.connect(pm.uri_kur(ayar, pm.kimlik_degeri(ayar)), connect_timeout=15) as c:
        assert c.execute("select 1").fetchone() == (1,)
        for sql in ("create table postgres_mcp_deneme(x int)",
                    "insert into postgres_mcp_deneme values (1)",
                    "update pg_catalog.pg_class set relname = relname where false"):
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                c.execute(sql)
            c.rollback()
