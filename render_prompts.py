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


def _entity_description(entity: dict[str, Any]) -> str:
    name = entity["name"]
    article = "an" if name[:1].lower() in "aeiou" else "a"
    return f"{article} {name}"


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
    ordered = sorted(entities, key=lambda entity: entity["depth"])
    entity_names = ", ".join(_entity_description(entity) for entity in ordered)
    relations = "\n".join(
        f"- {_relation_sentence(relation, entity_by_id)}"
        for relation in plan.get("relations", [])
    )
    occluding_relations = [
        relation for relation in plan.get("relations", [])
        if relation.get("type") in {"in_front_of", "behind", "covering"}
    ]
    if occluding_relations:
        depth_note = "Honor the specified occlusion relationships; place each occluding entity naturally in front of its target. Let the model choose the remaining depth arrangement."
    else:
        depth_note = "Choose the remaining depth arrangement naturally while keeping all listed entities distinct."
    if not relations:
        relations = "- Keep all listed entities separate and clearly recognizable."

    subject_families = ", ".join(taxonomy.get("subject_families", []))
    matrix_conditions = (
        f"- semantic layer count: {taxonomy['layer_count']} including the background\n"
        f"- subject families: {subject_families}\n"
        f"- scene type: {taxonomy['scene_type']}\n"
        f"- relation pattern: {taxonomy.get('relation_pattern', 'mixed')}\n"
        f"- occlusion level: {taxonomy['occlusion_level']}\n"
        f"- complexity: {taxonomy['complexity']}\n"
        f"- palette tendency: {taxonomy['palette']}\n"
        f"- viewpoint: {taxonomy['viewpoint']}\n"
        f"- composition tendency: {taxonomy['composition']}"
    )

    return f"""{LEGACY_PROMPT}

For this particular sample, use the following selected benchmark conditions:
{matrix_conditions}

Use these planned entities in the scene: {entity_names}. Keep them as the main semantic objects and do not add a busy collection of extra objects. Required spatial relationships:

{depth_note}
{relations}

Treat the matrix conditions as high-level constraints, not as a rigid diagram. Keep the scene naturally composed and recognizable. Let the model decide exact object sizes, positions, spacing, and visual details. Show only the final composite illustration with no labels, masks, guides, captions, frame, or extra independent objects.
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

