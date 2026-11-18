"""Survey of the reference decision policy: 30 tickers x 5 foci (x as_of dates). Shows which of the 8 actions actually occur,
why, and whether any run violated the harness. Feeds the label balance of the training data (Faz 5).

python -m bist.harness.survey [as_of ...]       -> reports/reference_action_survey.md/json
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from ..paths import ROOT
from ..tools import store
from . import reference
from .logdb import DecisionLog

FOCI = ["general", "sector_catchup", "technical_reversal", "fundamental_reaction", "calendar_pattern"]


def main():
    dates = sys.argv[1:] or [None]
    db = DecisionLog(Path(tempfile.mkdtemp()) / "survey.sqlite")
    rows = []
    for d in dates:
        for tk in store.tickers():
            for f in FOCI:
                try:
                    h = reference.run(f"survey {tk} {f}", tk, f, as_of=d, db=db)
                    rows.append({"as_of": h.as_of, "ticker": tk, "focus": f, "action": h.final["action"], "gate": h.gate["verdict"], "why": h.decision["rationale"],
                                 "violations": len(h.violations), "n_committed": h.evidence["n_committed"]})
                except Exception as e:  # a crash is a finding, not something to hide
                    rows.append({"as_of": d, "ticker": tk, "focus": f, "action": "CRASH", "why": f"{type(e).__name__}: {e}"[:200]})
    acts = Counter(r["action"] for r in rows)
    md = ["# Referans karar politikası taraması", "", f"{len(rows)} analiz ({len(store.tickers())} hisse × {len(FOCI)} odak × {len(dates)} tarih). Eylem dağılımı:", "",
          "| eylem | adet | pay |", "|---|---|---|"]
    md += [f"| {a} | {n} | {n / len(rows):.0%} |" for a, n in acts.most_common()]
    md += ["", "## Odak × eylem", "", "| odak | " + " | ".join(sorted(acts)) + " |", "|---|" + "---|" * len(acts)]
    for f in FOCI:
        c = Counter(r["action"] for r in rows if r["focus"] == f)
        md.append(f"| {f} | " + " | ".join(str(c.get(a, 0)) for a in sorted(acts)) + " |")
    md += ["", "## Gerekçeler", ""] + [f"- {w}: {n}" for w, n in Counter(r["why"] for r in rows).most_common(12)]
    md += ["", f"İhlal içeren analiz: {sum(1 for r in rows if r.get('violations'))}; çökme: {acts.get('CRASH', 0)}."]
    out = ROOT / "reports"
    (out / "reference_action_survey.md").write_text("\n".join(md), encoding="utf-8")
    (out / "reference_action_survey.json").write_text(json.dumps(rows, ensure_ascii=False, default=str), encoding="utf-8")
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
