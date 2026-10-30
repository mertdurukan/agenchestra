# ADR-0101: Sorun anında kök neden önce, çözüm ilk denemede kalıcı

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

`root-cause-first` skill'i (v2.1.0) eklentide yalnız yönergeydi; "Root-Cause-First Engineering Policy" bloğu ise yalnız McD'nin CLAUDE.md'sindeydi. K-006 kural metniydi, hata anında bağlamda değildi. Başka projedeki eklenti kullanıcıları davranışı almıyordu. Kullanıcı (30.10.2026): orkestra sorun ya da hata çıktığında önce kök nedeni analiz etsin, sorunu ilk aşamada best in class çözsün, her eklenti kullanıcısında etkin olsun.

**Karar:**

Davranış eklenti katmanında, model çağırmadan zorlanır: (1) Kural P-042 (katman plugin). (2) Metin tek kaynaktan, `standartlar/kok_neden.md`: `## Hata anı` ve `## Araç hatası anı`. (3) `scripts/kok_neden_enjeksiyonu.py`: kullanıcı mesajında hata sinyali varsa UserPromptSubmit'te ana ajana, kartlı işçilerde (denetçi hariç) SubagentStart'ta, araç başarısız olunca PostToolUseFailure'da (oturum başına seyreltilmiş) bağlama eklenir. Engellemez; planlı değişiklikte kök neden uydurulmaz. Ayrıntılı protokol `/orkestra:root-cause-first` skill'indedir. Ayar `ayarlar/kok_neden_enjeksiyonu.json`, proje ezmesi `.claude/orkestra/kok_neden_enjeksiyonu.json`, kapatma `ORKESTRA_KOK_NEDEN=0`. Her enjeksiyon `gunluk.jsonl`'a `kok_neden_enjekte` yazılır. Etki ölçümü (kontrol kolu, kol başına 65 plan) ayrı iş olarak en geç 30.11.2026'da başlar.

**Seçenekler:**

- Yalnız kural metni, enjeksiyon yok: elendi. Kural bağlamda durur ama hata anında ajan hatırlamaz (K-006'nın mevcut hâli).
- Skill'i güçlendirmek ya da her mesajda çağırtmak: elendi. Çağrı ajanın kararına bağlı kalır; uzun protokol rutin işte bağlamı şişirir.
- Stop kapısı: elendi. K-006: sonradan yakalamak yerine hata anında yöntem verilir; ölçümsüz ihlal modu P-028'e aykırıdır.
- `hata_kayit.py` defterini beslemek: elendi. Sonradan ölçer, hata anında yöntem vermez.
- `yontem_enjeksiyonu`'na ek mod: elendi. O modül iş mesajı ve kol mantığına bağlı; iki ilgisiz tetik tek dosyada birikir.

**Sonuçlar:**

Olumlu: her eklenti kullanıcısı aynı yöntemi alır; metin tek yerden değişir. Olumsuz: anahtar sözcük tespiti yanlış pozitif verir (kısa, zararsız ipucu); yöntemin davranışa etkisi bu işte ölçülmedi. Geri alma: `ORKESTRA_KOK_NEDEN=0`, ayarda `mod: kapali` ya da `orkestra kural kapat P-042`.

**İlgili iş:** I-267, P-042, K-006, ADR-0068, ADR-0069
