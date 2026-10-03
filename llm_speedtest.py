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
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "llm_speedtest_results.csv"
WORDS_FILE = BASE_DIR / "common_words.txt"
RANDOM_WORD_COUNT = 4

PROMPTS = {
    "brinks_story": (
        "Write a story about Balthasar Brinks, a knight of the middle ages, who rose to power "
        "during an eclipse. The story shall have around 1000 words."
    ),
    "quotes_guide": (
        "Write a tutorial about how to quote correctly in scientific publications. The tutorial "
        "shall have around 1000 words. Format it using latex syntax."
    ),
}

CSV_FIELDS = [
    "timestamp_utc",
    "model",
    "prompt_name",
    "ttft_s",
    "duration_s",
    "duration_api_s",
    "wall_duration_s",
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
    """Returns the random words and the prompt with several random words prepended."""
    words = WORDS_FILE.read_text(encoding="utf-8").split()
    random_words = " ".join(random.sample(words, RANDOM_WORD_COUNT))
    prefix = (
        "Do not use reasoning for this task. Answer it naturally.\n"
        f"This line of text is a technicality to avoid caching. Ignore it completely. {random_words}.\n"
    )
    return random_words, f"{prefix}\n{prompt}"


def run_claude(prompt, model):
    """Runs the prompt through Claude Code in headless mode and returns the parsed JSON result and
    the wall-clock duration of the claude process in seconds, measured by this script."""
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    start = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    wall_duration_s = time.perf_counter() - start
    if not proc.stdout.strip():
        raise SystemExit(f"claude produced no output (exit {proc.returncode}): {proc.stderr}")
    return json.loads(proc.stdout), wall_duration_s


def build_row(prompt_name, random_words, result, wall_duration_s):
    """Extracts the speed metrics from a Claude Code JSON result into a CSV row."""
    usage = result.get("usage", {})
    output_tokens = usage.get("output_tokens", 0)
    thinking_tokens = usage.get("output_tokens_details", {}).get("thinking_tokens", 0)
    text_tokens = output_tokens - thinking_tokens
    ttft_s = result.get("ttft_ms", 0) / 1000
    duration_s = result.get("duration_ms", 0) / 1000
    duration_api_s = result.get("duration_api_ms", 0) / 1000
    decode_s = (result.get("duration_ms", 0) - result.get("ttft_ms", 0)) / 1000
    models = list(result.get("modelUsage", {}).keys())
    return {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "model": ";".join(models),
        "prompt_name": prompt_name,
        "ttft_s": f"{ttft_s:.3f}",
        "duration_s": f"{duration_s:.3f}",
        "duration_api_s": f"{duration_api_s:.3f}",
        "wall_duration_s": f"{wall_duration_s:.3f}",
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "text_tokens": text_tokens,
        "decode_tok_s": f"{text_tokens / decode_s:.3f}" if decode_s > 0 else "",
        "end_to_end_tok_s": f"{output_tokens / duration_api_s:.3f}" if duration_api_s > 0 else "",
        "num_turns": result.get("num_turns", ""),
        "cost_usd": f"{result.get('total_cost_usd', 0):.8f}",
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
        print(f"=== {prompt_name} prompt ===\n{full_prompt}\n", flush=True)
        result, wall_duration_s = run_claude(full_prompt, args.model)
        print(f"=== {prompt_name} response ===\n{result.get('result', '')}\n")
        row = build_row(prompt_name, random_words, result, wall_duration_s)
        append_log(row)
        print(f"{prompt_name}: {row['output_tokens']} tokens ({row['thinking_tokens']} thinking), "
              f"TTFT {row['ttft_s']} s, decode {row['decode_tok_s']} tok/s")


if __name__ == "__main__":
    main()
