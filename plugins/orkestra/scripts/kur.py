#!/usr/bin/env python3
"""Orkestra kurulum denetimi: gereksinimleri yoklar, hiçbir şey kurmaz.

  kur.py            pytest seçilen yorumlayıcıda yoksa uyarı satırı basar; çıkış kodu her durumda 0.
Tam sağlık denetimi ve onarım: `orkestra doktor` (scripts/doktor.py); kur.py yalnız hızlı pytest yoklamasıdır.
Yorumlayıcı seçimi: ork_lib.python_yorumlayici() (ORKESTRA_PYTHON -> py -3.13 -> sys.executable).
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402


def pytest_var_mi(yorumlayici: str) -> bool:
    try:
        r = subprocess.run([yorumlayici, "-c", "import pytest"], capture_output=True, timeout=60)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def uyari_uret(yorumlayici: str) -> str | None:
    if pytest_var_mi(yorumlayici):
        return None
    return (f"UYARI: pytest bulunamadı ({yorumlayici}). Test kapısı pytest ister; kurulum yapılmadı. "
            f"Kur: \"{yorumlayici}\" -m pip install pytest  (ya da ORKESTRA_PYTHON ile pytest'li bir Python göster)")


def main() -> int:
    y = L.python_yorumlayici()
    print(f"Python yorumlayıcı: {y}")
    u = uyari_uret(y)
    print(u if u else "pytest: var")
    print("Tam sağlık denetimi ve onarım için: orkestra doktor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
