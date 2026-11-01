# ADR-0039: Geniş Bash taraması gölgede uyarılır; zaman aşımıyla arka plana düşen komut izlenir

**Durum:** Kabul edildi

**Tarih:** 22.10.2026

**Bağlam:**

I-190 oturumunda `grep -r` (C:\Work\DemoRoot) ve `find` (C:\Users\PC) ön planda, zaman sınırsız çalıştırıldı; 120 sn sonra harness ikisini arka plana aldı ve gösterge "arka plan görevleri sürüyor" dedi. P-012 madde 4 aramayı aktif işin klasörüyle sınırlar ama yalnız metindir. Orkestra izleyicisi (`hook.py` `_acik_arka_plan`) yalnız `run_in_background: true` çağrılarını sayar, zaman aşımıyla arka plana düşenleri görmez.

**Karar:**

(1) `pre_tool_use` içinde P-023 örüntüsüyle `golge` kipinde bir kapı: geniş köke `grep -r`/`find` ve `timeout` yok ise `gunluk.jsonl`'a `kural_ihlal / genis_tarama` yazılır; kalıplar ve kip `ayarlar/genis_tarama_hatirlatma.json`'da. (2) `_acik_arka_plan`, `tool_result` metnindeki "moved to the background" kalıbını (ayardan) açık görev sayar. (3) P-012 madde 4'e "önce Grep/Glob; Bash aramada `timeout` ve dar kök" cümlesi eklenir.

**Seçenekler:**

- **Yalnız kural cümlesi:** elendi. P-012 madde 4 zaten vardı ve ihlal edildi; ölçüm yok.
- **Doğrudan `block`:** elendi. Yanlış pozitif olasılığı var; P-028 önce gölge ister.
- **Bash `grep`/`find` yasağı:** elendi. Dar kapsamlı kullanım zararsız ve çoğu zaman gerekli.

**Sonuçlar:**

- **Olumlu:** ihlal sayılabilir; arka plana düşen komut görünür olur; tüm projelerde geçerli (P-022).
- **Olumsuz:** `golge` kipinde ajan yalnız tek satır uyarı alır, komut engellenmez; kalıp dışı geniş tarama kaçar.
- **Geri alma:** ayarda `mod: kapali` ya da `ORKESTRA_GENIS_TARAMA=0`; kalıcı: modül, ayar, test ve çağrı silinir; kural cümlesi `orkestra kural duzenle` ile geri alınır.

**İlgili iş:** I-194; kurallar P-012, P-022, P-023, P-028; ADR-0037
