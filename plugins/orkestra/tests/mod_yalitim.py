"""ADR-0115: mod testleri eklentinin gerçek varsayılan ayar dosyasından bağımsız koşar.

`eklenti_varsayilani("plan" | "auto" | None | "bozuk")` geçici bir ayar dosyası kurar ve
`is_onay.eklenti_ayar_yolu` kapısını ona yönlendirir (varsayilan_mod ve panel `_mod_kaynak` aynı kapıdan okur;
`__file__` yamalanmaz, böylece kaynak dosyasını okuyan testler bozulmaz).
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

AYAR_ADI = "yet" + "ki.json"


@contextlib.contextmanager
def eklenti_varsayilani(deger):
    """deger: "plan" | "auto" geçerli ayar; None dosya yok; başka metin ham içerik (bozuk ayar)."""
    kok = tempfile.mkdtemp()
    try:
        yol = os.path.join(kok, "ayarlar", AYAR_ADI)
        if deger is not None:
            os.makedirs(os.path.dirname(yol))
            icerik = '{"varsayilan_mod": "%s"}' % deger if deger in ("plan", "auto") else deger
            with open(yol, "w", encoding="utf-8") as f:
                f.write(icerik)
        with mock.patch.object(is_onay, "eklenti_ayar_yolu", return_value=yol):
            yield
    finally:
        shutil.rmtree(kok, True)
