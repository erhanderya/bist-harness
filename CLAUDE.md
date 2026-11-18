# BIST 100 Agentic Harness (CSE-481) — proje notları
- Kök: D:\bist-harness (eski belgeler C:\Users\burito\Desktop\cse\4\1\Econ'da; kaynak PDF/duyuru docs/ altında)
- Yol haritası: ROADMAP.md (durum kutularını güncel tut). Spec düz metin: docs/project_spec.txt
- Python: .venv\Scripts\python.exe. pip/HF cache: .cache/ (D:). Torch cu126.
- Donanım: RTX 4050 6GB, Ollama kurulu (llama3.2:3b mevcut). Final sistem tamamen yerel/çevrimdışı; bulut LLM API YOK.
- Evren: data/universe.csv (30 hisse). `peer_group` sütunu PDF sektörlerinden bizim türettiğimiz kaba gruplardır (ASELS tek başına → "peer group too small" uyarısı).
- Kural: araç şemaları (mcp/tool_schemas.json) Faz 2'de dondurulmadan eğitim verisi üretme.
- Windows/Git Bash: dosya yolları /d/... ; Python'u `-I` ile değil venv ile çalıştır.
- Çalıştırma: `cd /d/bist-harness && PYTHONPATH=src PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m <modül>`; test: `... -m pytest tests -q` (57 test). Uzun Python dosyalarını bash heredoc yerine Write ile yaz.
- Araçlar: src/bist/tools/ (envelope.py sözleşme; her araç as_of alır, sonrasını görmez; hatalar status=ERROR zarfı). Şema: mcp/tool_schemas.json DONDURULDU (v1.0).

## Harness (Faz 4)
- Paket: `src/bist/harness/` — `states.py` (17 durum + durum→araç izinleri), `machine.py` (Harness), `policy.py` (risk gate, referans karar, doğrulayıcı, açıklama şablonu), `logdb.py` (SQLite), `reference.py` (deterministik referans ajan = etiket kaynağı), `replay.py`, `llm_agent.py` (Ollama), `mcp_server.py`, `survey.py`.
- Referans çalıştırma: `reference.run(soru, "THYAO", focus, human=("APPROVE","neden"))`; MCP: `python -m bist.harness.mcp_server`.
- Karar günlüğü yolu `BIST_DECISION_DB` ile değiştirilebilir. Testler: tests/test_harness.py, test_llm_agent.py, test_mcp_server.py.
- Kural: LLM çıktısı `policy.validate_output`'tan geçmeden kabul edilmez; hiçbir araç emir üretmez.
