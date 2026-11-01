"""I-324 P4: test_paralel.py düşen testi sahip oturuma atfeder (S3-S5), is_kaydi.todo_ekle iş talebi alır (S1, S8).

Çıkış kodu değişmez, geçen koşuya satır eklenmez, atıf/talep hatası koşucuyu ve todo komutunu düşürmez.
"""
import json
import os
import subprocess
import sys
import time
from unittest import mock

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import is_kaydi as IK  # noqa: E402
import oturum_farkindalik as F  # noqa: E402
import test_paralel as TP  # noqa: E402

KOSUCU = os.path.join(SCRIPTS, "test_paralel.py")
SAHIP = "aaaa1111-sahip-oturum"
KOSAN = "bbbb2222-kosan-oturum"
DUSEN = "def test_dusen_ozel():\n    assert 1 == 2\n"
GECEN = "def test_a():\n    assert True\n"


def _proje(tmp_path):
    sd = tmp_path / ".claude" / "orkestra"
    (sd / "oturumlar").mkdir(parents=True)
    return sd


def _oturum(sd, oturum, yazilan, gorulme, is_id="I-9"):
    kayit = {"konum": {"yazilan": [F._norm(str(y)) for y in yazilan], "gorulme": gorulme, "is": is_id,
                       "dal": "main", "depo": "x", "worktree": "x"}}
    (sd / "oturumlar" / f"{oturum}.json").write_text(json.dumps(kayit), encoding="utf-8")


def _gelen(sd, oturum):
    yol = sd / "oturumlar" / f"{oturum}.gelen.jsonl"
    return yol.read_text(encoding="utf-8").splitlines() if yol.exists() else []


def _sonuc(dosya, cikti, kod=1):
    return [(str(dosya), kod, cikti, 0.1, False)]


# ---------------------------------------------------------------- test_paralel.sahip_satirlari

def test_canli_sahip_satiri_ve_paket_sahibin_kutusuna(tmp_path):
    sd = _proje(tmp_path)
    t = tmp_path / "test_dus.py"
    t.write_text(DUSEN, encoding="utf-8")
    _oturum(sd, SAHIP, [t], time.time())
    s = TP.sahip_satirlari(_sonuc(t, f"FAILED {t}::test_dusen_ozel - assert 1 == 2"), sd=str(sd), kosan=KOSAN)
    assert len(s) == 1 and s[0].startswith(f"sahip: {SAHIP[:8]} test_dus.py::test_dusen_ozel"), s
    assert "gelen kutusuna bırakıldı" in s[0]
    assert len(_gelen(sd, SAHIP)) == 1


def test_olu_sahip_paket_kosana_doner_kutuya_yazilmaz(tmp_path):
    sd = _proje(tmp_path)
    t = tmp_path / "test_dus.py"
    t.write_text(DUSEN, encoding="utf-8")
    _oturum(sd, SAHIP, [t], time.time() - 3 * 3600)
    s = TP.sahip_satirlari(_sonuc(t, f"FAILED {t}::test_dusen_ozel"), sd=str(sd), kosan=KOSAN)
    assert s and "koşan çözer" in s[0] and "Bağlam paketi" in s[0], s
    assert _gelen(sd, SAHIP) == [] and _gelen(sd, KOSAN) == []


def test_sahipsiz_ve_en_cok_on_satir(tmp_path):
    sd = _proje(tmp_path)
    cikti = "\n".join(f"FAILED {tmp_path / 'test_x.py'}::test_{i}" for i in range(15))
    s = TP.sahip_satirlari(_sonuc(tmp_path / "test_x.py", cikti), sd=str(sd), kosan=KOSAN)
    assert len(s) == TP.SAHIP_EN_COK and all("sahipsiz" in x for x in s)


def test_gecen_sonuc_ve_kapali_modda_satir_yok(tmp_path, monkeypatch):
    sd = _proje(tmp_path)
    t = tmp_path / "test_dus.py"
    _oturum(sd, SAHIP, [t], time.time())
    assert TP.sahip_satirlari(_sonuc(t, "1 passed", kod=0), sd=str(sd), kosan=KOSAN) == []
    monkeypatch.setenv("ORKESTRA_IS_TALEBI", "0")
    assert TP.sahip_satirlari(_sonuc(t, f"FAILED {t}::test_a"), sd=str(sd), kosan=KOSAN) == []


def test_atif_hatasi_yutulur(tmp_path):
    sd = _proje(tmp_path)
    import test_atif
    with mock.patch.object(test_atif, "atfet", side_effect=RuntimeError("boom")):
        s = TP.sahip_satirlari(_sonuc(tmp_path / "t.py", "FAILED t.py::x"), sd=str(sd), kosan=KOSAN)
    assert s == ["sahip: atıf yapılamadı (RuntimeError)"]


# ---------------------------------------------------------------- uçtan uca koşucu

def _kos(proje, *yollar, env_ek=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proje), CLAUDE_CODE_SESSION_ID=KOSAN,
               ORKESTRA_KAYNAK_KIRA_DIZINI=str(proje / ".kira"), ORKESTRA_DURUM_YEREL="1")
    env.pop("ORKESTRA_IS_TALEBI", None)
    env.update(env_ek or {})
    p = subprocess.run([sys.executable, KOSUCU, *map(str, yollar)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def test_kosucu_dusende_sahip_satiri_cikis_kodu_ayni(tmp_path):
    sd = _proje(tmp_path)
    td = tmp_path / "t"
    td.mkdir()
    t = td / "test_dus.py"
    t.write_text(DUSEN, encoding="utf-8")
    _oturum(sd, SAHIP, [t], time.time() + 600)  # koşu süresince canlı
    kod, cikti = _kos(tmp_path, t)
    assert kod == 1, cikti
    assert f"sahip: {SAHIP[:8]}" in cikti, cikti
    kod0, cikti0 = _kos(tmp_path, t, env_ek={"ORKESTRA_IS_TALEBI": "0"})
    assert kod0 == 1 and "sahip:" not in cikti0


def test_kosucu_gecende_satir_yok(tmp_path):
    sd = _proje(tmp_path)
    td = tmp_path / "t"
    td.mkdir()
    t = td / "test_iyi.py"
    t.write_text(GECEN, encoding="utf-8")
    _oturum(sd, SAHIP, [t], time.time() + 600)
    kod, cikti = _kos(tmp_path, t)
    assert kod == 0 and "sahip:" not in cikti, cikti


# ---------------------------------------------------------------- is_kaydi.todo_ekle talebi

def _is(tmp_path, ad, is_id):
    k = tmp_path / ad
    k.mkdir()
    (k / "is.json").write_text(json.dumps({"id": is_id, "baslik": ad}), encoding="utf-8")
    (k / "todo.md").write_text("# Yapılacaklar\n\n", encoding="utf-8")
    return str(k)


MADDE = "oturumlar arası todo çakışması için talep kaydı yaz"


def test_todo_ikinci_talepte_uyari_golge(tmp_path, monkeypatch, capsys):
    _proje(tmp_path)
    k1, k2 = _is(tmp_path, "is1", "I-001"), _is(tmp_path, "is2", "I-002")
    monkeypatch.delenv("ORKESTRA_IS_TALEBI", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SAHIP)
    IK.todo_ekle(k1, MADDE)
    assert "UYARI" not in capsys.readouterr().err
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", KOSAN)
    IK.todo_ekle(k2, MADDE)
    err = capsys.readouterr().err
    assert f"UYARI: bu iş I-001#1 altında oturum {SAHIP[:8]}'de" in err, err
    assert "devredildi → I-001#1" in err
    assert MADDE in open(os.path.join(k2, "todo.md"), encoding="utf-8").read()  # gölge: engellemez
    g = [json.loads(x) for x in (tmp_path / ".claude" / "orkestra" / "gunluk.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(x.get("tur") == "kapi_golge" and x.get("kapi") == "is_talebi" for x in g)


def test_todo_ihlalde_ret_ve_devir(tmp_path, monkeypatch):
    sd = _proje(tmp_path)
    (sd / "is_talebi.json").write_text(json.dumps({"mod": "ihlal"}), encoding="utf-8")
    k1, k2 = _is(tmp_path, "is1", "I-001"), _is(tmp_path, "is2", "I-002")
    monkeypatch.delenv("ORKESTRA_IS_TALEBI", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SAHIP)
    IK.todo_ekle(k1, MADDE)
    _oturum(sd, SAHIP, [], time.time())  # hedef_coz için sahip oturum kaydı
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", KOSAN)
    try:
        IK.todo_ekle(k2, MADDE)
        raise AssertionError("ihlalde ret beklenirdi")
    except ValueError as e:
        assert "talep reddedildi" in str(e) and "devredildi → I-001#1" in str(e), e
    assert MADDE not in open(os.path.join(k2, "todo.md"), encoding="utf-8").read()
    assert len(_gelen(sd, SAHIP)) == 1


def test_todo_talep_hatasi_todoyu_dusurmez(tmp_path, monkeypatch, capsys):
    _proje(tmp_path)
    k = _is(tmp_path, "is1", "I-001")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SAHIP)
    import is_talebi
    with mock.patch.object(is_talebi, "talep_al", side_effect=RuntimeError("boom")):
        IK.todo_ekle(k, MADDE)
    assert "iş talebi denetlenemedi (RuntimeError)" in capsys.readouterr().err
    assert MADDE in open(os.path.join(k, "todo.md"), encoding="utf-8").read()
