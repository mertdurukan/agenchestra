import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import is_rapor as R  # noqa: E402


def _yaz(yol, satirlar):
    with open(yol, "w", encoding="utf-8") as f:
        for o in satirlar:
            f.write(json.dumps(o) + "\n")


def test_talep_etiket_yok(tmp_path):
    t = R._is_talebi(str(tmp_path))
    assert t["etiket"] == 0 and t["ust"] is None and "gölgede kal" in t["karar"]


def test_talep_yeterli_etiket_ihlal_onerilir(tmp_path):
    sd = str(tmp_path)
    _yaz(os.path.join(sd, "gunluk.jsonl"), [{"tur": "kapi_golge", "kapi": "is_talebi"}] * 3)
    _yaz(os.path.join(sd, "is_talebi_etiket.jsonl"), [{"dogru": True}] * 200)
    t = R._is_talebi(sd)
    assert t["uyari"] == 3 and t["etiket"] == 200 and t["ust"] <= 0.05 and "ihlal" in t["karar"]


def test_talep_yanlis_pozitif_yuksek_ya_da_az_etiket(tmp_path):
    sd = str(tmp_path)
    _yaz(os.path.join(sd, "is_talebi_etiket.jsonl"), [{"dogru": True}] * 90 + [{"dogru": False}] * 10)
    assert "yüksek" in R._is_talebi(sd)["karar"]
    _yaz(os.path.join(sd, "is_talebi_etiket.jsonl"), [{"dogru": True}] * 50)
    assert "50/100" in R._is_talebi(sd)["karar"]
