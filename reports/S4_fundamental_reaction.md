# S4 - Çeyreklik temel veri → fiyat tepkisi

Soru: Bilanço açıklandıktan sonra, kârlılık (ROE TTM) bir önceki çeyreğe göre iyileşen şirketler piyasayı/sektörü geçiyor mu? Tepki açıklamayı izleyen günlerde mi görülüyor?

## Yöntem
- Olay: bir çeyreğin ilk KAP yayını → `effective_trade_date` (fiyatların yansıtabileceği ilk işlem günü; point-in-time).
- Tepki: açıklama öncesi kapanıştan k ∈ {1, 5, 10} işlem günü sonrasına hisse getirisi − XU100 (ve − sektör medyanı).
- Değişkenin tanımı: ΔROE(TTM) = bu çeyrek − önceki çeyrek. Dönem sınırları (TMS 29) arasında KARŞILAŞTIRMA YAPILMAZ.
- İki rejim ayrı raporlanır: **nominal** (≤2022Ç3, ana örneklem) ve **tms29_restated** (2022Ç4→, yeniden ifade edilmiş; yalnızca oran değişimi, düzey büyümesi yok).
- Karşılaştırma: ΔROE üst tersil (iyileşme) vs alt tersil (kötüleşme), Welch t; Spearman(ΔROE, tepki).

## Rejim: nominal (n=729, hisse=29)

| tepki penceresi | ölçüt | iyileşen (üst tersil) | kötüleşen (alt tersil) | fark | Welch p | Spearman ρ (p) |
|---|---|---|---|---|---|---|
| +1g | XU100 | +0.37% (n=233) | -0.77% (n=237) | +1.13% | 0.016 | +0.120 (0.001) |
| +1g | sektör | +0.37% (n=180) | -1.27% (n=181) | +1.64% | 0.005 | +0.158 (0.000) |
| +5g | XU100 | +0.64% (n=233) | -0.94% (n=237) | +1.59% | 0.021 | +0.091 (0.016) |
| +5g | sektör | +0.31% (n=180) | -1.69% (n=181) | +1.99% | 0.023 | +0.129 (0.003) |
| +10g | XU100 | +0.78% (n=233) | -0.61% (n=237) | +1.38% | 0.091 | +0.058 (0.124) |
| +10g | sektör | +0.72% (n=180) | -2.22% (n=181) | +2.94% | 0.009 | +0.127 (0.003) |

## Rejim: tms29_restated (n=408, hisse=29)

| tepki penceresi | ölçüt | iyileşen (üst tersil) | kötüleşen (alt tersil) | fark | Welch p | Spearman ρ (p) |
|---|---|---|---|---|---|---|
| +1g | XU100 | -0.04% (n=136) | -1.11% (n=136) | +1.07% | 0.084 | +0.071 (0.154) |
| +1g | sektör | -0.61% (n=103) | -0.99% (n=108) | +0.39% | 0.617 | +0.035 (0.543) |
| +5g | XU100 | +1.19% (n=136) | -0.76% (n=136) | +1.95% | 0.030 | +0.077 (0.121) |
| +5g | sektör | +0.32% (n=103) | -0.29% (n=108) | +0.61% | 0.589 | +0.013 (0.816) |
| +10g | XU100 | +1.67% (n=136) | -0.12% (n=136) | +1.79% | 0.098 | +0.041 (0.408) |
| +10g | sektör | +0.65% (n=103) | -0.09% (n=108) | +0.74% | 0.602 | +0.008 (0.886) |

## Ek: nominal dönemde net kâr YoY (|değişim|<%500)

| grup | n | +5g XU100'e göre | +10g XU100'e göre |
|---|---|---|---|
| net kâr YoY > +%15 | 323 | +0.65% | +0.78% |
| net kâr YoY < −%15 | 157 | -1.20% | -1.44% |

## Yorum
- Welch p<0.05 (düzeltmesiz): 6 / 12. Spearman ρ Bonferroni (12 test) sonrası anlamlı: 4 (bunların 4'i nominal dönemde).
- Yön tutarlı: kârlılığı iyileşenler açıklama sonrası piyasayı/sektörü geçiyor, kötüleşenler geride kalıyor; etkinin büyük kısmı +1 günde görülüyor (hızlı fiyatlama).
- Tepki yönü/zamanı yalnızca nominal dönemde ana kanıttır; TMS 29 dönemi örneklemi küçük ve yeniden ifade edilmiş değerlere dayanır, bu yüzden 'FUNDAMENTAL_IMPROVEMENT_CANDIDATE' için tek başına yetmez.
- Not: ΔROE (TTM) açıklanan sürprizi değil, kârlılık değişimini ölçer; beklenti (konsensüs) verimiz yok, bu yüzden 'sürpriz' iddiası yapılamaz.