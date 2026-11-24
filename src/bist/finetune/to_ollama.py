"""Faz 6 export: merge the LoRA adapter into the bf16 base model and register it in Ollama as a 4-bit (int4) model.

    python -m bist.finetune.to_ollama --run qlora_r16 --name bist-analyst

The Modelfile reuses the chat template and stop tokens of the base Ollama model (`qwen3:4b-instruct-2507-q4_K_M`), so prompts and
tool calls are rendered the same way as for the base model in Faz 7. Everything stays local (Ollama on 127.0.0.1).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request
from pathlib import Path

from .export import MODEL_ID

RUNS = Path("finetune/runs")
BASE_OLLAMA = "qwen3:4b-instruct-2507-q4_K_M"
OLLAMA = "http://127.0.0.1:11434"


def merge(adapter: Path, out: Path) -> Path:
    os.environ.setdefault("HF_HOME", str(Path(".cache/hf").resolve()))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    base = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.bfloat16, device_map={"": "cpu"}, local_files_only=True)
    model = PeftModel.from_pretrained(base, str(adapter)).merge_and_unload()
    model.save_pretrained(str(out), safe_serialization=True)
    AutoTokenizer.from_pretrained(MODEL_ID, local_files_only=True).save_pretrained(str(out))
    return out


def base_modelfile_parts(model: str = BASE_OLLAMA) -> tuple[str, list[str]]:
    req = urllib.request.Request(f"{OLLAMA}/api/show", data=json.dumps({"model": model}).encode(), headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    params = [l.strip() for l in (d.get("parameters") or "").splitlines() if l.strip()]
    return d["template"], params


def modelfile(src: Path, template: str, params: list[str]) -> str:
    lines = [f"FROM {src.resolve()}", f'TEMPLATE """{template}"""']
    lines += [f"PARAMETER {p}" for p in params]
    return "\n".join(lines) + "\n"


def main(run: str, name: str, quant: str = "int4") -> None:
    rd = RUNS / run
    merged = rd / "merged"
    if not (merged / "config.json").exists():
        print(f"merging {rd / 'final_adapter'} -> {merged}", flush=True)
        merge(rd / "final_adapter", merged)
    template, params = base_modelfile_parts()
    mf = rd / "Modelfile"
    mf.write_text(modelfile(merged, template, params), encoding="utf-8")
    subprocess.run(["ollama", "create", name, "--quantize", quant, "-f", str(mf)], check=True)
    print(f"created ollama model {name}", flush=True)


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="qlora_r16")
    ap.add_argument("--name", default="bist-analyst")
    ap.add_argument("--quant", default="int4")   # Ollama >= 0.40 quantize types: int4, int8, nvfp4, mxfp4, mxfp8
    a = ap.parse_args()
    main(a.run, a.name, a.quant)


if __name__ == "__main__":
    _cli()
