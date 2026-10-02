#!/usr/bin/env python3
"""Measures Claude Code token speed for a fixed set of prompts.

Each run executes all prompts in PROMPTS one after another. Each prompt gets a prepended line with
4 random common English words so that no two runs send the same prompt. The prompt runs through
`claude -p --output-format json`, and the timing results are appended to
llm_speedtest_results.csv. All files live next to this script.
"""

import argparse
import csv
import json
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "llm_speedtest_results.csv"
WORDS_FILE = BASE_DIR / "common_words.txt"
RANDOM_WORD_COUNT = 4

PROMPTS = {
    "brinks_story": (
        "Write a story about Balthasar Brinks, a knight of the middle ages, who rose to power during"
        " an eclipse. The story shall have around 1000 words."
    ),
    "quoting_tutorial": (
        "Write a tutorial about how to quote correctly in scientific publications. The tutorial"
        " shall have around 1000 words. Format use latex syntax."
    ),
}

CSV_FIELDS = [
    "timestamp_utc",
    "prompt_name",
    "model",
    "ttft_s",
    "duration_s",
    "duration_api_s",
    "output_tokens",
    "thinking_tokens",
    "text_tokens",
    "decode_tok_s",
    "end_to_end_tok_s",
    "num_turns",
    "cost_usd",
    "is_error",
    "random_words",
]


def add_cache_buster(prompt):
    """Returns the random words and the prompt with a line of random words prepended."""
    words = WORDS_FILE.read_text(encoding="utf-8").split()
    random_words = " ".join(random.sample(words, RANDOM_WORD_COUNT))
    prefix = f"Ignore this line of text. It's a technicality to avoid caching: {random_words}"
    return random_words, f"{prefix}\n{prompt}"


def run_claude(prompt, model):
    """Runs the prompt through Claude Code in headless mode and returns the parsed JSON result."""
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if not proc.stdout.strip():
        raise SystemExit(f"claude produced no output (exit {proc.returncode}): {proc.stderr}")
    return json.loads(proc.stdout)


def build_row(prompt_name, random_words, result):
    """Extracts the speed metrics from a Claude Code JSON result into a CSV row."""
    usage = result.get("usage", {})
    output_tokens = usage.get("output_tokens", 0)
    thinking_tokens = usage.get("output_tokens_details", {}).get("thinking_tokens", 0)
    text_tokens = output_tokens - thinking_tokens
    ttft_s = result.get("ttft_ms", 0) / 1000
    duration_s = result.get("duration_ms", 0) / 1000
    duration_api_s = result.get("duration_api_ms", 0) / 1000
    decode_s = duration_s - ttft_s
    models = list(result.get("modelUsage", {}).keys())
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prompt_name": prompt_name,
        "model": ";".join(models),
        "ttft_s": round(ttft_s, 3),
        "duration_s": round(duration_s, 3),
        "duration_api_s": round(duration_api_s, 3),
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "text_tokens": text_tokens,
        "decode_tok_s": round(text_tokens / decode_s, 1) if decode_s > 0 else "",
        "end_to_end_tok_s": round(output_tokens / duration_api_s, 1) if duration_api_s > 0 else "",
        "num_turns": result.get("num_turns", ""),
        "cost_usd": round(result.get("total_cost_usd", 0), 6),
        "is_error": result.get("is_error", ""),
        "random_words": random_words,
    }


def append_log(row):
    """Appends one row to the CSV log and writes the header if the file is new."""
    is_new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="model passed to claude --model, e.g. claude-sonnet-5-5")
    args = parser.parse_args()

    for prompt_name, prompt in PROMPTS.items():
        random_words, full_prompt = add_cache_buster(prompt)
        result = run_claude(full_prompt, args.model)
        row = build_row(prompt_name, random_words, result)
        append_log(row)
        print(f"{prompt_name}: {row['output_tokens']} tokens ({row['thinking_tokens']} thinking), "
              f"TTFT {row['ttft_s']} s, decode {row['decode_tok_s']} tok/s")


if __name__ == "__main__":
    main()
