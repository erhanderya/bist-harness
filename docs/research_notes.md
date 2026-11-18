# Araştırma notları (raporda kullanılacak bulgular)

## 1. Haftanın günü etkisi hisseye özgü değil, piyasa geneli (test_weekday_pattern)
- 30 hisse × 5 gün = 150 test, 2021–2025: Bonferroni + OOS + yıl kararlılığı sonrası 25 "anlamlı ve kararlı" bulgu, bunların 14'ü PERŞEMBE.
- Neden: XU100'ün kendisi aynı dönemde perşembe ortalama +%0,51, çarşamba −%0,12. Yani 25 bulgu bağımsız değil; tek bir piyasa geneli etkinin 30 hissede tekrarı.
- Araç artık XU100 referansı hesaplar; aynı işaretli anlamlı etki varsa `market_wide_effect=true`, `stock_specific_evidence=false`, uyarı MARKET_WIDE_EFFECT.
- Test motoru kalibrasyonu: satırları karıştırılmış (saf gürültü) getirilerde 3000 testte yanlış-pozitif oranı %1,03 (Bonferroni-5 nominal düzeyi %1).

## 2. Strateji varyantları A–D (2017→2026-11, 30 hisse, 10+5 bps/taraf maliyet)
| | sinyal | ort. net getiri/işlem | kazanma | XU100'e fazla (işlem başı) | portföy Sharpe | OOS (test) |
|---|---|---|---|---|---|---|
| A teknik | 6058 | +%0,24 | %49,4 | −%0,22 | 0,12 | +%0,21 (1237 işlem) |
| B +sektör | 604 | +%0,39 | %50,7 | −%0,02 | 0,46 | −%0,32 (111 işlem) → UNSTABLE |
| C +temel | 472 | +%0,37 | %50,4 | −%0,05 | 0,39 | −%0,12 (88 işlem) → UNSTABLE |
| D +makro | 426 | +%0,20 | %49,5 | −%0,17 | 0,19 | +%0,04 (86 işlem) |
- Hiçbir varyant sinyal başına XU100'ü aynı pencerede geçemedi. Eklenen katmanlar (B,C) örneklem içinde iyileşme gösterip testte bozuldu: klasik aşırı uyum işareti.
- Nominal TL'de buy&hold (XU100 ×15,2; EW evren ×55) enflasyon sürüklenmesi taşır ve nakit %0 getirir: portföy toplamı değil, işlem başı fazla getiri karşılaştırılmalı (araç çıktısında `benchmark_note`).
- Dürüst sonuç: bu kural setleri için "aday durum" iddiası güçlü olamaz; sistem bunu REJECT_SIGNAL/WATCH/INVESTIGATE ile ifade etmeli.

## 3. Veri sınırlamaları (özet; ayrıntı docs/data_layer_audit.md)
- TMS 29 dönemi (FY2022→) İş Yatırım değerleri yeniden ifade edilmiş → büyüme geri tutulur, yalnızca oranlar.
- TCMB politika faizi ve TÜFE henüz yok (EVDS anahtarı bekleniyor) → araç MACRO_INCOMPLETE bildirir.
- Haber/konuşma veri seti yok → SOURCE_NOT_AVAILABLE.

## 4. Faz 3 senaryo sonuçları (ayrıntı: reports/S1..S4, variants_A_E; üretim: `python -m bist.scenarios`)
- **S1 sektör catch-up:** 9 (L,F) kombinasyonunda güçlü sektördeki laggard sektör medyanını +%0,25…+%0,62 geçiyor ama Bonferroni sonrası 0/9 anlamlı; "geride kalmaya devam" oranı %43–57 (yazı-tura bandı). → güçlü aday iddiası yok.
- **S2 takvim:** 330 testte 22 anlamlı+kararlı; weekday_return'in perşembe/çarşamba/salı etkisi XU100 ile ortak. Hisseye özgü 15 bulgu beklenen gürültüden (~3) fazla ama kümeli (Salı düşüş sonrası: 6 hisse) ve 3 hissede bilinen veri sorunu var → aday değil, INVESTIGATE.
- **S3 teknik dönüş:** 7 yükseliş olayı + tek/birleşik; tabana (tüm günler) göre edge ≈ 0, Bonferroni sonrası 0/36. İlk sürümde test H0'ı "getiri=0" idi ve taban sapması (+%0,54/10g) yüzünden sahte anlamlılık verdi; H0 "olay=taban" olarak düzeltildi. Birleşik koşul tekten iyi değil.
- **S4 temel → tepki:** Tek anlamlı yapı: ΔROE(TTM) iyileşenler açıklamadan sonra piyasayı/sektörü geçiyor (nominal dönem, n=729; +1g fark +%1,1…+%1,6, ρ≈0,12–0,16, Bonferroni sonrası 4 test anlamlı), etki ilk gün ağırlıklı. TMS29 döneminde (n=408) sektöre göre anlamsız. → FUNDAMENTAL_IMPROVEMENT_CANDIDATE için tek makul kanıt; yine de sürpriz/konsensüs verisi yok.
- **Varyantlar:** A–D tablosu §2'deki gibi; E LAYER_UNAVAILABLE.
- Genel ders (raporda): 4 senaryodan yalnızca S4 bilgi taşıyor; sistemin dürüst çıktısı çoğu sorguda WATCH/INVESTIGATE/REJECT_SIGNAL olmalı, eğitim verisi bunu yansıtmalı.

## 5. Referans karar politikası (harness/policy.py) ve tarama
- Aday etiketi kuralı araştırma bulgularıyla uyumlu tutuldu: bir backtest ancak testte net getirisi > 0 **ve** işlem başı XU100'e göre fazla getirisi > 0 ise "destekliyor" sayılır (nominal TL sürüklenmesi yüzünden ham pozitif getiri yeterli değil). İlk sürümde yalnızca test net getirisi bakılıyordu; bu, S3 ile çelişen 25/30 sahte TECHNICAL_REVERSAL_CANDIDATE üretti ve düzeltildi.
- Backtest ızgarası (A–D × tutma 3/5/10/20 gün): XU100'ü hem tüm örneklemde hem testte geçen tek ayar A@20 gün (+%0,60/işlem, test +%1,02). B, C ve D@10/20 testte bozuluyor (UNSTABLE). Sonuç: POTENTIAL_CATCH_UP_CANDIDATE bu veriyle hiçbir ayarda desteklenmiyor (S1 ile tutarlı); eğitim verisine zorla eklenmeyecek. TECHNICAL_REVERSAL_CANDIDATE yalnızca hold_days=20 taramalarında oluşabilir.
- Tarama (30 hisse × 5 odak, 2026-11-16): REJECT 55%, WATCH 25%, FUNDAMENTAL_IMPROVEMENT 15%, INVESTIGATE 5%, HOLD 1%; 0 çökme, 0 ihlal. ANALYSIS_UNSAFE yalnızca engelleyici veri koşullarında oluşur (sızıntı, bilinmeyen hisse, kaynak yok); Faz 5'te kontrollü senaryolarla üretilecek. Etiket dengesi için Faz 5 as_of tarihlerini ve hold_days'i çeşitlendirecek.
