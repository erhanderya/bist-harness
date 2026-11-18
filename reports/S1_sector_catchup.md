# S1 - Sektör laggard / catch-up (5/10/20 gün)

Soru: Güçlü bir sektörde geride kalan hisse, sonraki 5/10/20 günde sektör medyanını yakalıyor mu (catch-up) yoksa gerilemeye devam mı ediyor?

## Yöntem
- Evren: 8 hisse, 2 sektör grubu (≥4 üye). Yetersiz grup dışarıda: Auto_Durables, Chemicals, Construction_Materials, Defense_Tech, Energy_Utilities, Healthcare, Metals_Mining, Telecom, Transport.
- Sinyal t kapanışında: geriye bakış L günü getirisinde sektörün en gerisi (lag rank 1). Güçlü sektör = sektör medyanı > XU100 ve > 0.
- Giriş t+1 açılışı, çıkış t+F kapanışı. Sonuç: hissenin getirisi − aynı pencerede sektör medyanı (catch-up ölçüsü) ve − XU100.
- Çakışan gözlem yok: tarihler L günde bir örneklenir; t-istatistiği tarih bazında kümelenir. 9 kombinasyon için Bonferroni.
- Maliyet: 30 bps gidiş-dönüş (yalnızca mutlak getiri sütununda; sektöre göre fazla getiri işlem yapılabilir bir getiri değildir).

## Sonuçlar

| L | F | grup | n | ort. brüt | net (−30bps) | sektöre göre fazla | XU100'e göre fazla | geride kalmaya devam | t | p (Bonf.) | 1.yarı / 2.yarı fazla |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 | 5 | strong | 341 | +0.70% | +0.40% | +0.49% | +0.56% | 47% | 2.35 | 0.18 | +0.49% / +0.49% |
| 5 | 5 | other | 627 | +0.74% | +0.44% | +0.16% | +0.27% | 48% | 1.46 | 1.00 | +0.12% / +0.20% |
| 5 | 10 | strong | 340 | +1.41% | +1.11% | +0.55% | +0.82% | 44% | 2.05 | 0.37 | +0.72% / +0.38% |
| 5 | 10 | other | 626 | +1.62% | +1.32% | +0.25% | +0.51% | 51% | 1.30 | 1.00 | +0.53% / -0.02% |
| 5 | 20 | strong | 339 | +2.83% | +2.53% | +0.34% | +0.79% | 50% | 1.29 | 1.00 | +0.24% / +0.45% |
| 5 | 20 | other | 623 | +3.08% | +2.78% | +0.15% | +0.87% | 53% | 0.79 | 1.00 | +0.64% / -0.34% |
| 10 | 5 | strong | 175 | +0.74% | +0.44% | +0.43% | +0.58% | 43% | 1.83 | 0.63 | +0.53% / +0.33% |
| 10 | 5 | other | 309 | +0.85% | +0.55% | +0.19% | +0.24% | 49% | 0.62 | 1.00 | +0.32% / +0.06% |
| 10 | 10 | strong | 176 | +1.56% | +1.26% | +0.62% | +1.16% | 44% | 1.86 | 0.58 | +0.89% / +0.35% |
| 10 | 10 | other | 310 | +1.96% | +1.66% | +0.51% | +0.70% | 51% | 1.37 | 1.00 | +0.85% / +0.17% |
| 10 | 20 | strong | 176 | +2.97% | +2.67% | +0.60% | +1.39% | 49% | 1.08 | 1.00 | +0.23% / +0.96% |
| 10 | 20 | other | 308 | +3.63% | +3.33% | +0.47% | +0.91% | 52% | 0.72 | 1.00 | +1.18% / -0.24% |
| 20 | 5 | strong | 90 | +1.52% | +1.22% | +0.35% | +0.44% | 57% | 0.91 | 1.00 | +0.38% / +0.33% |
| 20 | 5 | other | 151 | +0.62% | +0.32% | -0.11% | -0.13% | 48% | -1.01 | 1.00 | -0.05% / -0.17% |
| 20 | 10 | strong | 91 | +3.26% | +2.96% | +0.25% | +0.83% | 52% | 0.68 | 1.00 | -0.16% / +0.65% |
| 20 | 10 | other | 152 | +2.01% | +1.71% | +0.21% | +0.34% | 53% | 0.14 | 1.00 | +0.51% / -0.10% |
| 20 | 20 | strong | 91 | +3.81% | +3.51% | +0.36% | +0.91% | 48% | 0.20 | 1.00 | +0.27% / +0.46% |
| 20 | 20 | other | 150 | +2.23% | +1.93% | -0.13% | +0.28% | 51% | -0.72 | 1.00 | +0.46% / -0.71% |

## Yorum
- Bonferroni sonrası anlamlı güçlü-sektör catch-up kombinasyonu: **0 / 9**.
- 'Geride kalmaya devam' oranı %50'ye yakınsa laggard seçimi bilgi taşımıyor (yazı-tura); yanlış-pozitif oranı budur.
- Catch-up sinyali ancak anlamlı VE iki yarıda aynı işaretliyse aday sayılır; aksi halde WATCH/INVESTIGATE, güçlü aday iddiası yok.
- Sınırlama: peer grupları kaba (universe.csv), 30 hisse; küçük gruplarda medyan gürültülü.