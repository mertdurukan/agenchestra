"""G-054: asama_sure.py -- ajan x surec bazinda sure/maliyet dagilimi (PAR-0 olcum tabani)."""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

BETIK = Path(__file__).resolve().parents[1] / "scripts" / "asama_sure.py"

DK = 60000


def _satir(ajan, surec, sure_dk, usd, gorev="G-002", zaman="2026-10-10T10:00:00+03:00", **ek):
    r = {"zaman": zaman, "oturum": "o1", "gorev": gorev, "surec": surec, "ajan": ajan,
         "agent_id": None, "sure_ms": int(sure_dk * DK), "model": "m", "giris": 1, "cikis": 1,
         "maliyet_usd": usd}
    r.update(ek)
    return r


def _yaz(yol, satirlar, ham=()):
    with open(yol, "w", encoding="utf-8") as f:
        for r in satirlar:
            f.write(json.dumps(r) + "\n")
        for h in ham:
            f.write(h + "\n")
    return str(yol)


def _kos(*args):
    return subprocess.run([sys.executable, str(BETIK), *args], capture_output=True, text=True,
                          encoding="utf-8")


def _gruplar(cikti):
    veri = json.loads(cikti)
    if isinstance(veri, dict):
        veri = veri["gruplar"]
    assert isinstance(veri, list)
    return veri


def _bul(gruplar, ajan, surec):
    uy = [g for g in gruplar if g["ajan"] == ajan and g["surec"] == surec]
    assert len(uy) == 1, f"{ajan}/{surec} grubu bulunamadi: {[(g['ajan'], g['surec']) for g in gruplar]}"
    return uy[0]


@pytest.fixture
def defter(tmp_path):
    # Elle dogrulanabilir sabit fixture. Toplam sure = 30 + 12 + 1 + 3 + 1 = 47 dk
    satirlar = [
        _satir("ana-ajan", "orkestrasyon", 10, 1.0, gorev="G-001"),
        _satir("ana-ajan", "orkestrasyon", 20, 2.0, gorev="G-001"),
        _satir("orkestra:denetci", "denetim", 2, 0.1),
        _satir("orkestra:denetci", "denetim", 4, 0.2),
        _satir("orkestra:denetci", "denetim", 6, 0.3),
        _satir("orkestra:isci-t1", "is", 1, 0.05),
        _satir("orkestra:isci-t1", "test-kapisi", 3, 0.02),
        _satir("orkestra:isci-t1", "on-kontrol", 1, 0.01),
    ]
    return _yaz(tmp_path / "maliyet.jsonl", satirlar)


# --- Kriter 1 ---------------------------------------------------------------

def test_json_grup_sayilari_ve_toplamlar(defter):
    p = _kos("--defter", defter, "--json")
    assert p.returncode == 0, p.stderr
    g = _gruplar(p.stdout)
    ana = _bul(g, "ana-ajan", "orkestrasyon")
    assert ana["sayi"] == 2
    assert ana["toplam_dk"] == pytest.approx(30.0, abs=0.05)
    assert ana["medyan_dk"] == pytest.approx(15.0, abs=0.05)
    assert ana["toplam_usd"] == pytest.approx(3.0, abs=1e-6)
    assert 19.0 <= ana["p95_dk"] <= 20.0

    den = _bul(g, "orkestra:denetci", "denetim")
    assert den["sayi"] == 3
    assert den["toplam_dk"] == pytest.approx(12.0, abs=0.05)
    assert den["medyan_dk"] == pytest.approx(4.0, abs=0.05)
    assert den["toplam_usd"] == pytest.approx(0.6, abs=1e-6)
    assert 5.5 <= den["p95_dk"] <= 6.0

    tek = _bul(g, "orkestra:isci-t1", "is")
    assert tek["sayi"] == 1
    assert tek["medyan_dk"] == pytest.approx(1.0, abs=0.05)
    assert tek["p95_dk"] == pytest.approx(1.0, abs=0.05)  # tek satirda p95 = o deger


def test_json_pay_yuzde(defter):
    g = _gruplar(_kos("--defter", defter, "--json").stdout)
    ana = _bul(g, "ana-ajan", "orkestrasyon")
    den = _bul(g, "orkestra:denetci", "denetim")
    assert ana["pay_yuzde"] == pytest.approx(30 / 47 * 100, abs=0.2)
    assert den["pay_yuzde"] == pytest.approx(12 / 47 * 100, abs=0.2)
    assert sum(x["pay_yuzde"] for x in g) == pytest.approx(100.0, abs=0.5)


def test_json_toplam_dk_azalan_sirali(defter):
    g = _gruplar(_kos("--defter", defter, "--json").stdout)
    sureler = [x["toplam_dk"] for x in g]
    assert len(sureler) == 5
    assert sureler == sorted(sureler, reverse=True)
    assert (g[0]["ajan"], g[0]["surec"]) == ("ana-ajan", "orkestrasyon")


# --- Kriter 2 ---------------------------------------------------------------

def test_gorev_filtresi_tek_karti_sinirlar(defter):
    g = _gruplar(_kos("--defter", defter, "--json", "--gorev", "G-001").stdout)
    assert [(x["ajan"], x["surec"]) for x in g] == [("ana-ajan", "orkestrasyon")]
    assert g[0]["sayi"] == 2
    assert g[0]["pay_yuzde"] == pytest.approx(100.0, abs=0.1)


def test_gorev_filtresi_olmayan_kart_bos(defter):
    p = _kos("--defter", defter, "--json", "--gorev", "G-999")
    assert p.returncode == 0, p.stderr
    assert _gruplar(p.stdout) == []


def test_gun_filtresi_son_n_gun(tmp_path):
    simdi = datetime.now().astimezone()
    z = lambda gun: (simdi - timedelta(days=gun)).isoformat(timespec="seconds")
    yol = _yaz(tmp_path / "m.jsonl", [
        _satir("ana-ajan", "orkestrasyon", 5, 0.5, zaman=z(0.05)),
        _satir("ana-ajan", "orkestrasyon", 7, 0.7, zaman=z(1)),
        _satir("ana-ajan", "orkestrasyon", 100, 9.0, zaman=z(10)),
    ])
    tum = _bul(_gruplar(_kos("--defter", yol, "--json").stdout), "ana-ajan", "orkestrasyon")
    assert tum["sayi"] == 3
    son3 = _bul(_gruplar(_kos("--defter", yol, "--json", "--gun", "3").stdout), "ana-ajan", "orkestrasyon")
    assert son3["sayi"] == 2
    assert son3["toplam_dk"] == pytest.approx(12.0, abs=0.05)
    assert son3["toplam_usd"] == pytest.approx(1.2, abs=1e-6)
    son30 = _bul(_gruplar(_kos("--defter", yol, "--json", "--gun", "30").stdout), "ana-ajan", "orkestrasyon")
    assert son30["sayi"] == 3


def test_gun_ve_gorev_birlikte(tmp_path):
    simdi = datetime.now().astimezone()
    z = lambda gun: (simdi - timedelta(days=gun)).isoformat(timespec="seconds")
    yol = _yaz(tmp_path / "m.jsonl", [
        _satir("ana-ajan", "orkestrasyon", 5, 0.5, gorev="G-001", zaman=z(1)),
        _satir("ana-ajan", "orkestrasyon", 6, 0.6, gorev="G-002", zaman=z(1)),
        _satir("ana-ajan", "orkestrasyon", 8, 0.8, gorev="G-001", zaman=z(20)),
    ])
    g = _bul(_gruplar(_kos("--defter", yol, "--json", "--gun", "3", "--gorev", "G-001").stdout),
             "ana-ajan", "orkestrasyon")
    assert g["sayi"] == 1
    assert g["toplam_dk"] == pytest.approx(5.0, abs=0.05)


# --- Kriter 3 ---------------------------------------------------------------

def test_ana_ajan_ve_kapilar_ayri_gruplar(defter):
    g = _gruplar(_kos("--defter", defter, "--json").stdout)
    _bul(g, "ana-ajan", "orkestrasyon")
    kapi_tk = _bul(g, "orkestra:isci-t1", "test-kapisi")
    kapi_ok = _bul(g, "orkestra:isci-t1", "on-kontrol")
    assert kapi_tk["toplam_dk"] == pytest.approx(3.0, abs=0.05)
    assert kapi_ok["toplam_dk"] == pytest.approx(1.0, abs=0.05)
    # kapi satirlari isci-t1/is grubuna karismaz
    assert _bul(g, "orkestra:isci-t1", "is")["sayi"] == 1


def test_isci_t1_is_grubunda_n0_notu(defter):
    g = _gruplar(_kos("--defter", defter, "--json").stdout)
    t1 = _bul(g, "orkestra:isci-t1", "is")
    assert "N0" in str(t1.get("not", ""))
    assert "kapı karışık" in str(t1.get("not", ""))
    # diger gruplarda N0 notu yok
    for x in g:
        if (x["ajan"], x["surec"]) != ("orkestra:isci-t1", "is"):
            assert "N0" not in str(x.get("not", ""))


def test_md_cikti_n0_notunu_gosterir(defter):
    p = _kos("--defter", defter)
    assert "isci-t1/is (kapı karışık, N0)" in p.stdout


# --- Kriter 4 ---------------------------------------------------------------

def test_md_tablo_json_olmadan(defter):
    p = _kos("--defter", defter)
    assert p.returncode == 0, p.stderr
    out = p.stdout
    with pytest.raises(ValueError):
        json.loads(out)
    tablo = [s for s in out.splitlines() if s.strip().startswith("|")]
    assert len(tablo) >= 2 + 5  # baslik + ayirici + 5 grup
    assert any(set(s.replace("|", "").strip()) <= set("-: ") for s in tablo)  # md ayirici satiri
    for ad in ("ana-ajan", "orkestra:denetci", "test-kapisi", "on-kontrol"):
        assert ad in out
    # azalan sira: ana-ajan satiri denetci satirindan once
    assert out.index("ana-ajan") < out.index("orkestra:denetci")


def test_bozuk_ve_bos_satirlar_atlanir(tmp_path):
    yol = _yaz(tmp_path / "m.jsonl",
               [_satir("ana-ajan", "orkestrasyon", 10, 1.0)],
               ham=["", "   ", "{bozuk json", "[1, 2]", "null", '"metin"',
                    json.dumps({"ajan": "orkestra:denetci", "surec": "denetim"}),  # sure_ms yok
                    json.dumps({"zaman": "dun degil", "ajan": "ana-ajan", "surec": "orkestrasyon",
                                "sure_ms": None, "maliyet_usd": None})])
    for ek in (["--json"], []):
        p = _kos("--defter", yol, *ek)
        assert p.returncode == 0, p.stderr
        assert "Traceback" not in p.stderr
    ana = _bul(_gruplar(_kos("--defter", yol, "--json").stdout), "ana-ajan", "orkestrasyon")
    assert ana["toplam_dk"] >= 10.0 - 0.05
    assert ana["toplam_usd"] >= 1.0 - 1e-6


def test_bos_defter_cokmez(tmp_path):
    yol = _yaz(tmp_path / "bos.jsonl", [])
    p = _kos("--defter", yol, "--json")
    assert p.returncode == 0, p.stderr
    assert _gruplar(p.stdout) == []
    p2 = _kos("--defter", yol)
    assert p2.returncode == 0, p2.stderr
    assert "Traceback" not in p2.stderr


# --- Tekillestirme (ork_lib.maliyet_kayitlari) ------------------------------

def test_birikimli_hook_satirlari_tekillestirilir(tmp_path):
    # Ayni (oturum, agent_id) icin 'tur' satiri yokken yalniz en son hook satiri sayilir.
    satirlar = [
        _satir("orkestra:isci-t2", "is", 2, 0.2, agent_id="a1", kaynak="hook",
               zaman="2026-10-10T10:00:00+03:00"),
        _satir("orkestra:isci-t2", "is", 5, 0.5, agent_id="a1", kaynak="hook",
               zaman="2026-10-10T10:05:00+03:00"),
    ]
    yol = _yaz(tmp_path / "maliyet.jsonl", satirlar)
    g = _bul(_gruplar(_kos("--defter", yol, "--json").stdout), "orkestra:isci-t2", "is")
    assert g["sayi"] == 1
    assert g["toplam_dk"] == pytest.approx(5.0, abs=0.05)
    assert g["toplam_usd"] == pytest.approx(0.5, abs=1e-6)
