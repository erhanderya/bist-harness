# Strateji varyantları A–E karşılaştırması

30 hisse, 2017→2026-11, sinyal t kapanışı / giriş t+1 açılışı, 5 gün tutma, 10+5 bps/taraf, maks 5 eşzamanlı pozisyon. Aynı kurallar `run_backtest` aracıyla.

| varyant | durum | sinyal | ort. net/işlem | kazanma | XU100'e fazla/işlem | portföy Sharpe | maks DD | test (OOS) ort. | bayraklar |
|---|---|---|---|---|---|---|---|---|---|
| A | WARN | 6058 | +0.24% | 49.4% | -0.22% | 0.12 | -67% | +0.21% | ZERO_VOLUME_ENTRY_SKIPPED |
| B | WARN | 604 | +0.39% | 50.7% | -0.02% | 0.46 | -23% | -0.32% | UNSTABLE_OUT_OF_SAMPLE, PEER_GROUP_TOO_SMALL, ZERO_VOLUME_ENTRY_SKIPPED |
| C | WARN | 472 | +0.37% | 50.4% | -0.05% | 0.39 | -18% | -0.12% | UNSTABLE_OUT_OF_SAMPLE, PEER_GROUP_TOO_SMALL, FUNDAMENTAL_FILTER_RATIOS_ONLY, ZERO_VOLUME_ENTRY_SKIPPED |
| D | WARN | 426 | +0.20% | 49.5% | -0.17% | 0.19 | -20% | +0.04% | PEER_GROUP_TOO_SMALL, FUNDAMENTAL_FILTER_RATIOS_ONLY, ZERO_VOLUME_ENTRY_SKIPPED |
| E | ERROR | - | - | - | - | - | - | - | LAYER_UNAVAILABLE |

- E (haber/konuşma katmanı) backtest edilemez: tarihsel haber/konuşma veri seti yok → `LAYER_UNAVAILABLE`. Veri uydurulmadı.
- Nominal TL buy&hold karşılaştırmaları enflasyon sürüklenmesi taşır ve nakit %0 getirir: bu yüzden işlem başı fazla getiri esas alınır.
- Sonuç ve yorum: docs/research_notes.md §2.