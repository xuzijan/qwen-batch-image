#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把主体行为计划渲染成每图一个的最终 Prompt。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from qwen_batch_image import PROMPT as LEGACY_PROMPT


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(encoded)


def render_prompt(plan: dict[str, Any]) -> str:
    description = plan.get("image_description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("plan.image_description must contain one concise subject-action sentence")
    return f"{LEGACY_PROMPT}\n\n{description.strip()}"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSON: {exc}") from exc
    return records


def write_prompts(plans: Iterable[dict[str, Any]], destination: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for plan in plans:
        prompt = render_prompt(plan)
        records.append({
            "sample_id": plan["sample_id"],
            "prompt": prompt,
            "plan_sha256": sha256_json(plan),
            "prompt_sha256": sha256_text(prompt),
            "image_seed": plan.get("image_seed"),
        })
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return records


def write_markdown_prompt_pack(plans: Iterable[dict[str, Any]], destination: Path) -> None:
    """Write full prompts in fenced blocks that are easy to copy into a web UI."""
    sections = [
        "# Prompts for manual image-generation testing",
        "",
        "Copy one complete fenced block at a time. Each block contains the shared prompt followed by one sample-specific subject-action sentence.",
        "",
    ]
    for index, plan in enumerate(plans, start=1):
        subject = plan["entities"][0]
        label = subject.get("name_zh") or subject["name"]
        sections.extend([
            f"## {index:02d}. {label} — `{subject['synset']}` ({plan['taxonomy']['subject_priority']})",
            "",
            "```text",
            render_prompt(plan),
            "```",
            "",
        ])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(sections), encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 plans.jsonl 生成每张图片对应的 Prompt")
    parser.add_argument("--plans", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plans = load_jsonl(args.plans)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = write_prompts(plans, args.output)
    print(f"已渲染 {len(records)} 个 Prompt：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

