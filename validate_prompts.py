#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验计划与专属 Prompt 一一对应、结构完整且没有重复语义计划。"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from render_prompts import load_jsonl, render_prompt, sha256_json, sha256_text
from taxonomy import semantic_signature, validate_plan


def validate(plans: list[dict], prompts: list[dict]) -> list[str]:
    errors: list[str] = []
    plans_by_id = {plan.get("sample_id"): plan for plan in plans}
    prompts_by_id = {prompt.get("sample_id"): prompt for prompt in prompts}
    if len(plans_by_id) != len(plans):
        errors.append("plans.jsonl contains duplicate sample_id values")
    if len(prompts_by_id) != len(prompts):
        errors.append("prompts.jsonl contains duplicate sample_id values")
    if set(plans_by_id) != set(prompts_by_id):
        errors.append("plans and prompts must have exactly the same sample_id values")

    seen_signatures: Counter[tuple] = Counter()
    for sample_id, plan in plans_by_id.items():
        for issue in validate_plan(plan):
            errors.append(f"{sample_id}: {issue}")
        signature = semantic_signature(plan)
        seen_signatures[signature] += 1

        prompt_record = prompts_by_id.get(sample_id)
        if prompt_record is None:
            continue
        prompt = prompt_record.get("prompt", "")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(f"{sample_id}: prompt is empty")
            continue
        if prompt != render_prompt(plan):
            errors.append(f"{sample_id}: prompt is not the deterministic rendering of its plan")
        if prompt_record.get("plan_sha256") != sha256_json(plan):
            errors.append(f"{sample_id}: plan_sha256 does not match")
        if prompt_record.get("prompt_sha256") != sha256_text(prompt):
            errors.append(f"{sample_id}: prompt_sha256 does not match")
        if prompt_record.get("image_seed") != plan.get("image_seed"):
            errors.append(f"{sample_id}: image seed differs between plan and prompt")
        for entity in plan.get("entities", []):
            if entity.get("name", "").lower() not in prompt.lower():
                errors.append(f"{sample_id}: prompt is missing entity {entity.get('name')!r}")

    duplicates = sum(count - 1 for count in seen_signatures.values() if count > 1)
    if duplicates:
        errors.append(f"{duplicates} duplicate semantic plan(s) found")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验 plans.jsonl 与 prompts.jsonl")
    parser.add_argument("--plans", type=Path, required=True)
    parser.add_argument("--prompts", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plans = load_jsonl(args.plans)
    prompts = load_jsonl(args.prompts)
    errors = validate(plans, prompts)
    if errors:
        print(f"校验失败：发现 {len(errors)} 个问题")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"校验通过：{len(plans)} 个计划与 Prompt 一一对应，结构、哈希和语义去重均通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

