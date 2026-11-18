# S2 - Haftanın günü ve çok günlü desenler

Soru: 'Perşembe güçlü', 'düşüş sonrası sıçrama', 'art arda 3 düşüşten sonra toparlanma' gibi takvim desenleri hisseye özgü mü, piyasa geneli mi, yoksa gürültü mü?

## Yöntem
- Araç: `test_weekday_pattern`; 30 hisse × (5 gün getirisi + 5 gün sonrası sıçrama + 1 art arda 3 düşüş) = 330 test, son 5 yıl.
- Welch t-testi, Bonferroni (aile boyutu 5, art arda-düşüş için 1), %70 örneklem içi / %30 örneklem dışı işaret tutarlılığı, yıl bazında ≥%60 kararlılık.
- XU100 referansı: endeks aynı yönde anlamlıysa etki piyasa geneli sayılır, hisseye özgü kanıt değildir.

## Özet

| desen | test | anlamlı+kararlı | bunlardan piyasa geneli | hisseye özgü | gürültüden beklenen yanlış-pozitif (%1) |
|---|---|---|---|---|---|
| bounce_after_down_day | 150 | 11 | 1 | 10 | 1.5 |
| bounce_after_n_down_days | 30 | 3 | 0 | 3 | 0.3 |
| weekday_return | 150 | 8 | 6 | 2 | 1.5 |

## Gün bazında (weekday_return)

| gün | test | anlamlı+kararlı | piyasa geneli | ort. fark (hisse ort.) |
|---|---|---|---|---|
| FRI | 30 | 2 | 0 | +0.082% |
| MON | 30 | 0 | 0 | +0.183% |
| THU | 30 | 3 | 30 | +0.386% |
| TUE | 30 | 0 | 29 | -0.277% |
| WED | 30 | 3 | 30 | -0.376% |

## Hisseye özgü kalan bulgular

| hisse | desen | gün | n | fark | p (Bonf.) |
|---|---|---|---|---|---|
| TUPRS | bounce_after_down_day | MON | 116 | -0.889% | 0.0025 |
| THYAO | bounce_after_n_down_days | nan | 129 | +0.730% | 0.0159 |
| CCOLA | weekday_return | FRI | 250 | +0.498% | 0.0161 |
| CCOLA | bounce_after_down_day | TUE | 125 | -0.611% | 0.0406 |
| SASA | bounce_after_down_day | TUE | 140 | -0.975% | 0.0054 |
| ENKAI | bounce_after_down_day | THU | 111 | +0.710% | 0.0149 |
| PGSUS | bounce_after_down_day | MON | 117 | -0.671% | 0.0428 |
| PGSUS | bounce_after_down_day | TUE | 145 | -0.689% | 0.0123 |
| PGSUS | bounce_after_n_down_days | nan | 161 | +0.489% | 0.0450 |
| EKGYO | bounce_after_down_day | TUE | 128 | -0.873% | 0.0143 |
| AKSEN | bounce_after_n_down_days | nan | 118 | +0.601% | 0.0346 |
| ECILC | weekday_return | FRI | 250 | +0.588% | 0.0369 |
| ECILC | bounce_after_down_day | TUE | 135 | -1.103% | 0.0005 |
| ECILC | bounce_after_down_day | THU | 96 | +0.838% | 0.0290 |
| MAVI | bounce_after_down_day | TUE | 124 | -0.683% | 0.0175 |

## Yorum
- Piyasa geneli etki: weekday_return anlamlı+kararlı bulgularından 6 tanesi XU100'de de anlamlı ve aynı işaretli; gün bazı tablosunda perşembe/çarşamba/salı'nın neredeyse tüm hisselerde XU100 ile aynı yönde olması ortak etkiyi gösteriyor (bağımsız kanıt değil).
- Hisseye özgü işaretlenen 15 bulgu, saf gürültüden beklenen ≈3.3 yanlış-pozitiften fazla: bu yüzden tamamen 'gürültü' denemez, ama test aynı piyasa verisini paylaşan 30 hissede yapıldığı için bulgular birbirinden bağımsız değildir.
- Aynı desenin birden çok hissede görüldüğü kümeler (ortak faktör şüphesi): bounce_after_down_day/TUE (6 hisse), bounce_after_n_down_days/- (3 hisse).
- Veri kalitesi uyarısı: CCOLA, ECILC, SASA için bilinen veri sorunları var (SASA sıfır hacim günleri, ECILC aşırı hareket, CCOLA split katsayısı doğrulanmadı); bu bulgular önce veri doğrulaması ister.
- Sistem kuralı: hisseye özgü bulgu bile tek başına 'aday' değildir; backtest + kalite kapısı + insan incelemesi gerekir, aksi halde WATCH/INVESTIGATE.