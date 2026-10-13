---
name: defter
description: Orkestra ortak defterini göster — herkesin (ana ajan, işçiler, denetçiler, rüya) ne yaptığının son kayıtları; isteğe bağlı olarak tek bir görevin geçmişi.
argument-hint: "[görev id, ör. G-007] [son N]"
disable-model-invocation: true
---
# /orkestra:defter

- `$ARGUMENTS` bir görev kimliği içeriyorsa: `orkestra defter oku --gorev <id> --son 20`.
- Yoksa: önce `orkestra defter ozet` (görev başına son durum), sonra `orkestra defter oku --son 10`.

Kullanıcıya kayıtları kısaltmadan değil, okunur biçimde ver: zaman, görev, süreç, ajan, ne yaptı, sonuç.
