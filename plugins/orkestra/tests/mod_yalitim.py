"""ADR-0115: mod testleri eklentinin gerçek varsayılan ayar dosyasından bağımsız koşar.

`eklenti_varsayilani("plan" | "auto" | None | "bozuk")` geçici bir eklenti klasörü kurar ve
`is_onay.__file__` ile `panel.__file__` dosyalarını ona yönlendirir (ikisi de ayar yolunu `__file__`'dan türetir).
"""
import contextlib
import os
import shutil
import sys
import tempfile
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_onay  # noqa: E402
import panel  # noqa: E402

AYAR_ADI = "yet" + "ki.json"


@contextlib.contextmanager
def eklenti_varsayilani(deger):
    """deger: "plan" | "auto" geçerli ayar; None dosya yok; başka metin ham içerik (bozuk ayar)."""
    kok = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(kok, "scripts"))
        if deger is not None:
            os.makedirs(os.path.join(kok, "ayarlar"))
            icerik = '{"varsayilan_mod": "%s"}' % deger if deger in ("plan", "auto") else deger
            with open(os.path.join(kok, "ayarlar", AYAR_ADI), "w", encoding="utf-8") as f:
                f.write(icerik)
        sahte = os.path.join(kok, "scripts", "x.py")
        with mock.patch.object(is_onay, "__file__", sahte), mock.patch.object(panel, "__file__", sahte):
            yield
    finally:
        shutil.rmtree(kok, True)
