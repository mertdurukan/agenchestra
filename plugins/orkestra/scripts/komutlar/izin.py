"""orkestra komutları: izin politikası (goster, sina)."""
from __future__ import annotations

import izin_politikasi  # noqa: E402


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    izin_politikasi.kaydet(alt)
