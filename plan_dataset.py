#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成受约束随机的场景计划、专属 Prompt 和覆盖报告。

这个阶段不会调用生图 API。
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from render_prompts import write_prompts
from taxonomy import build_plan, semantic_signature


def write_jsonl(records: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_coverage(plans: list[dict], seed: int) -> dict:
    def counts(values: list[str | int]) -> dict[str, int]:
        return dict(sorted(Counter(str(value) for value in values).items()))

    return {
        "plan_version": "0.1",
        "count": len(plans),
        "plan_seed": seed,
        "note": "第一轮约 10 张实验只作描述性覆盖统计，不设完整矩阵配额。",
        "layer_count": counts([plan["taxonomy"]["layer_count"] for plan in plans]),
        "scene_type": counts([plan["taxonomy"]["scene_type"] for plan in plans]),
        "complexity": counts([plan["taxonomy"]["complexity"] for plan in plans]),
        "occlusion_level": counts([plan["taxonomy"]["occlusion_level"] for plan in plans]),
        "viewpoint": counts([plan["taxonomy"]["viewpoint"] for plan in plans]),
        "subject_family": counts([
            family
            for plan in plans
            for family in plan["taxonomy"]["subject_families"]
        ]),
        "semantic_signatures": len({semantic_signature(plan) for plan in plans}),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 benchmark 场景计划和专属 Prompt")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261029, help="计划抽样 seed")
    parser.add_argument("--image-seed-base", type=int, default=20261029, help="第一张图片的 seed（须在模型支持范围内）")
    parser.add_argument("--output-dir", type=Path, default=Path("dataset_demo"))
    parser.add_argument("--force", action="store_true", help="允许覆盖输出目录中的计划文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count 必须是正整数")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_files = [
        args.output_dir / "plans.jsonl",
        args.output_dir / "prompts.jsonl",
        args.output_dir / "coverage_report.json",
    ]
    if not args.force:
        existing = [path for path in output_files if path.exists()]
        if existing:
            names = ", ".join(str(path) for path in existing)
            raise SystemExit(f"输出文件已存在：{names}；如需覆盖请加 --force")

    rng = random.Random(args.seed)
    plans: list[dict] = []
    signatures: set[tuple] = set()
    attempts = 0
    while len(plans) < args.count:
        attempts += 1
        if attempts > args.count * 100:
            raise SystemExit("无法在限制次数内生成足够的不重复计划")
        plan = build_plan(len(plans) + 1, rng, args.image_seed_base + len(plans) + 1)
        signature = semantic_signature(plan)
        if signature in signatures:
            continue
        signatures.add(signature)
        plans.append(plan)

    write_jsonl(plans, args.output_dir / "plans.jsonl")
    prompt_records = write_prompts(plans, args.output_dir / "prompts.jsonl")
    coverage = build_coverage(plans, args.seed)
    (args.output_dir / "coverage_report.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已生成 {len(plans)} 个结构化计划和 {len(prompt_records)} 个专属 Prompt。")
    print(f"输出目录：{args.output_dir.resolve()}")
    print(json.dumps(coverage, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

