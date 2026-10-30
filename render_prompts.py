#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把结构化场景计划渲染成每图一个的最终 Prompt。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from qwen_batch_image import PROMPT as LEGACY_PROMPT
from taxonomy import RELATION_LABELS


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(encoded)


def _main_subject_family(plan: dict[str, Any]) -> str:
    entities = plan.get("entities", [])
    for entity in entities[1:]:
        if entity.get("role") == "main_subject":
            return str(entity.get("category", "recognizable subject"))
    return "recognizable subject"


def _with_article(value: str) -> str:
    return ("an " if value[:1].lower() in "aeiou" else "a ") + value


def _relation_sentence(relation: dict[str, Any], entities: dict[str, dict[str, Any]]) -> str:
    source = entities[relation["source"]]["name"]
    target = entities[relation["target"]]["name"]
    relation_type = relation["type"]
    label = RELATION_LABELS.get(relation_type, relation_type)
    occlusion = relation.get("occlusion", "none")
    if relation_type == "in_front_of":
        return f"The {source} is in front of and partially occludes the {target} with {occlusion} occlusion."
    if relation_type == "on":
        source_category = entities[relation["source"]].get("category")
        verb = {
            "person": "stands on",
            "animal": "stands on",
            "vehicle": "rests on",
            "plant": "grows on",
            "food": "rests on",
        }.get(source_category, "is placed on")
        return f"The {source} {verb} the {target}."
    if relation_type == "beside":
        return f"The {source} is beside the {target}; keep both forms visually distinct."
    if relation_type == "behind":
        return f"The {source} is behind the {target} with {occlusion} occlusion."
    return f"The {source} is {label} the {target}; keep both forms recognizable and separate."


def render_prompt(plan: dict[str, Any]) -> str:
    taxonomy = plan["taxonomy"]
    entities = plan["entities"]
    entity_by_id = {entity["id"]: entity for entity in entities}
    main_subject_family = _with_article(_main_subject_family(plan))
    occlusion_level = taxonomy["occlusion_level"]

    return f"""{LEGACY_PROMPT}

For this particular sample, use a {taxonomy['scene_type']} setting with one clear focal point centered on a {main_subject_family}. Aim for about {taxonomy['layer_count']} semantic entities including the background, but prioritize a harmonious, naturally related scene over filling a quota. Choose the specific subject and any supporting entities yourself so they belong together and make sense in this setting. A single main subject is acceptable when it creates the strongest illustration. The intended occlusion level is {occlusion_level}; use it only when a natural overlap helps the composition. Do not force unrelated objects or artificial interactions.

Keep the scene naturally composed and recognizable. Let the model decide the exact object list, palette, viewpoint, composition, object sizes, positions, spacing, and visual details. Show only the final composite illustration with no labels, masks, guides, captions, frame, or extra independent objects.
""".strip()


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

