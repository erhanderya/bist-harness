# S3 - Teknik dönüşler: tek koşul vs birleşik koşul, rejim kırılımı

Soru: Tek bir teknik dönüş olayı (RSI aşırı satımdan çıkış, Bollinger alt bant geri alma, Supertrend/KAMA/MACD/Ichimoku yukarı kesişim) sonraki günlerde XU100'ü geçen getiri üretiyor mu? Birden fazla koşul birlikte gelince iyileşiyor mu? Piyasa rejimine göre değişiyor mu?

## Yöntem
- 7 yükseliş olay türü × 30 hisse, 2017→; olay sonrası 5 gün cooldown. Birleşik: aynı gün biri tetiklenirken son 3 barda ≥2 farklı tür.
- Getiri: olay kapanışından h gün sonraki hisse getirisi − XU100 (aracın `detect_reversal_events` kuralı; yalnızca tamamlanmış ufuklar).
- Taban: aynı hissenin tüm günlerindeki ortalama fazla getiri. 'Edge' = olay − taban. t-testi tarih bazında kümelenmiş ve H0: olay getirisi = taban (sıfır değil); Bonferroni test sayısı: 36.
- Rejim: XU100 kapanışı 200 günlük ortalamanın üstünde = boğa, altında = ayı.

## 5 günlük ufuk

| olay | n | ort. fazla getiri | taban | edge | isabet | boğa | ayı | pozitif yıl payı | p (Bonf.) |
|---|---|---|---|---|---|---|---|---|---|
| ANY_single | 6611 | +0.24% | +0.27% | -0.03% | 53% | +0.21% | +0.34% | 100% (10y) | 1.000 |
| COMBINED_2plus_in_3d | 4213 | +0.19% | +0.27% | -0.08% | 54% | +0.17% | +0.24% | 90% (10y) | 1.000 |
| bollinger_lower_reclaim | 1351 | -0.04% | +0.27% | -0.31% | 54% | -0.07% | +0.01% | 40% (10y) | 1.000 |
| ichimoku_cloud_breakout_up | 1493 | +0.25% | +0.27% | -0.02% | 53% | +0.23% | +0.31% | 70% (10y) | 1.000 |
| ichimoku_tk_cross_up | 1670 | +0.27% | +0.27% | +0.00% | 54% | +0.28% | +0.23% | 70% (10y) | 1.000 |
| kama_cross_up | 3928 | +0.22% | +0.27% | -0.05% | 54% | +0.20% | +0.29% | 80% (10y) | 1.000 |
| macd_cross_up | 2745 | +0.29% | +0.27% | +0.02% | 52% | +0.25% | +0.40% | 90% (10y) | 1.000 |
| rsi_oversold_exit | 560 | +0.30% | +0.27% | +0.03% | 55% | +0.36% | +0.25% | 60% (10y) | 1.000 |
| supertrend_flip_up | 1016 | +0.23% | +0.27% | -0.04% | 56% | +0.23% | +0.24% | 60% (10y) | 1.000 |

## Tek vs birleşik (tüm ufuklar)

| grup | h | n | ort. fazla | edge | p (Bonf.) |
|---|---|---|---|---|---|
| ANY_single | 1 | 6629 | +0.08% | +0.03% | 1.000 |
| ANY_single | 3 | 6616 | +0.09% | -0.06% | 0.754 |
| ANY_single | 5 | 6611 | +0.24% | -0.03% | 1.000 |
| ANY_single | 10 | 6594 | +0.50% | -0.03% | 1.000 |
| COMBINED_2plus_in_3d | 1 | 4218 | +0.04% | -0.01% | 1.000 |
| COMBINED_2plus_in_3d | 3 | 4215 | +0.07% | -0.08% | 1.000 |
| COMBINED_2plus_in_3d | 5 | 4213 | +0.19% | -0.08% | 1.000 |
| COMBINED_2plus_in_3d | 10 | 4178 | +0.45% | -0.08% | 1.000 |

## Yorum
- Bonferroni sonrası tabanın üstünde anlamlı kombinasyon sayısı: **0 / 36**.
- Edge ≈ 0 ise olay, rastgele bir günden ayırt edilemez; 'dönüş adayı' ancak anlamlı, rejimler arası aynı işaretli ve çoğu yılda pozitif ise söylenebilir.
- Birleşik koşulun tek koşuldan farkı tablodan okunur; fark yoksa 'daha fazla gösterge = daha güçlü kanıt' iddiası desteklenmez.
- Not: olaylar hisseler arasında ve zamanda kümelenir (özellikle piyasa dönüşlerinde); tarih bazlı kümeleme bunu kısmen hesaba katar.