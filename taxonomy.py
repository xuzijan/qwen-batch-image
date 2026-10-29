#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词表、计划采样和计划级校验。

计划先于 Prompt 和图片存在。随机数只负责选择结构化条件；语义条件不会
从图片或 seed 反推，便于复现实验和统计覆盖情况。
"""

from __future__ import annotations

import random
from typing import Any


SUBJECTS: dict[str, tuple[str, ...]] = {
    "animal": ("cat", "dog", "fox", "bear", "rabbit", "bird", "turtle", "fish"),
    "person": ("gardener", "cook", "cyclist", "traveler", "musician", "child"),
    "food": ("bread", "cake", "apple", "sandwich", "tea cup", "fruit basket"),
    "plant": ("tree", "potted plant", "mushroom", "bush", "flowering plant"),
    "vehicle": ("bicycle", "scooter", "small boat", "train carriage", "hot-air balloon"),
    "object": ("wooden crate", "flower pot", "bench", "umbrella", "backpack", "lantern", "basket"),
}

ENVIRONMENTS: dict[str, tuple[str, ...]] = {
    "indoor": ("wooden table", "simple floor"),
    "garden": ("grassy ground", "garden ground"),
    "street": ("simple pavement", "quiet roadside ground"),
    "shore": ("calm sea", "simple sandy shore"),
    "forest": ("forest floor", "simple hillside"),
    "workshop": ("wooden workbench", "plain workshop floor"),
    "market": ("simple market counter", "plain stall floor"),
    "fantasy": ("simple green hill", "calm blue ground plane"),
}

SCENE_CANDIDATES: dict[str, tuple[tuple[str, str], ...]] = {
    "indoor": (
        ("person", "cook"), ("animal", "cat"), ("food", "cake"),
        ("plant", "potted plant"), ("object", "basket"), ("object", "lantern"),
        ("food", "tea cup"), ("person", "musician"),
    ),
    "garden": (
        ("animal", "rabbit"), ("animal", "bird"), ("person", "gardener"),
        ("plant", "flowering plant"), ("plant", "mushroom"), ("object", "basket"),
        ("food", "apple"), ("object", "watering can"),
    ),
    "street": (
        ("vehicle", "bicycle"), ("vehicle", "scooter"), ("person", "cyclist"),
        ("animal", "dog"), ("object", "umbrella"), ("plant", "bush"),
        ("object", "backpack"), ("person", "traveler"),
    ),
    "shore": (
        ("vehicle", "small boat"), ("person", "traveler"), ("animal", "bird"),
        ("object", "umbrella"), ("object", "basket"),
        ("plant", "bush"), ("food", "sandwich"),
    ),
    "forest": (
        ("animal", "fox"), ("animal", "rabbit"), ("animal", "bird"),
        ("person", "traveler"), ("plant", "mushroom"), ("plant", "bush"),
        ("object", "lantern"), ("food", "bread"),
    ),
    "workshop": (
        ("person", "gardener"), ("person", "cook"), ("object", "wooden crate"),
        ("object", "lantern"), ("vehicle", "bicycle"), ("plant", "potted plant"),
        ("animal", "cat"), ("food", "bread"),
    ),
    "market": (
        ("person", "cook"), ("person", "traveler"), ("food", "bread"),
        ("food", "cake"), ("food", "fruit basket"), ("object", "basket"),
        ("plant", "potted plant"), ("animal", "bird"),
    ),
    "fantasy": (
        ("animal", "bear"), ("animal", "fox"), ("person", "traveler"),
        ("plant", "flowering plant"), ("plant", "mushroom"), ("object", "lantern"),
        ("vehicle", "hot-air balloon"), ("object", "umbrella"),
    ),
}

SCENE_TYPES = tuple(ENVIRONMENTS)
PALETTES = ("warm", "cool", "natural", "pastel", "high contrast")
COMPOSITIONS = ("centered", "left-right", "diagonal", "foreground-background", "triangular")
VIEWPOINTS = ("front", "three-quarter", "side", "slightly top-down")
OCCLUSIONS = ("none", "light", "medium")

RELATION_TYPES = ("beside", "in_front_of", "on", "inside", "holding", "riding", "covering")
RELATION_LABELS = {
    "beside": "beside",
    "in_front_of": "in front of",
    "on": "on",
    "inside": "inside",
    "holding": "holding",
    "riding": "riding",
    "covering": "covering",
}


def _choose_unique(rng: random.Random, values: tuple[str, ...], used: set[str]) -> str:
    available = [value for value in values if value not in used]
    if not available:
        available = list(values)
    choice = rng.choice(available)
    used.add(choice)
    return choice


def _base_relation(source: dict[str, Any], background_name: str) -> str:
    if background_name == "calm sea":
        if source["name"] == "fish":
            return "inside"
        if source["name"] == "small boat":
            return "on"
        return "beside"
    if source["category"] in {"animal", "person", "plant", "vehicle", "object", "food"}:
        return "on"
    return "beside"


def _complexity(layer_count: int, relation_types: list[str]) -> str:
    if layer_count <= 3 and not {"riding", "holding"}.intersection(relation_types):
        return "simple"
    if layer_count >= 6 or {"riding", "holding"}.intersection(relation_types):
        return "challenging"
    return "moderate"


def build_plan(index: int, rng: random.Random, image_seed: int) -> dict[str, Any]:
    """Create one legal object-level scene plan."""

    layer_count = rng.choices([2, 3, 4, 5, 6], weights=[1, 3, 3, 2, 1], k=1)[0]
    scene_type = rng.choice(SCENE_TYPES)
    background_name = rng.choice(ENVIRONMENTS[scene_type])
    palette = rng.choice(PALETTES)
    composition = rng.choice(COMPOSITIONS)
    viewpoint = rng.choice(VIEWPOINTS)

    entities: list[dict[str, Any]] = [{
        "id": "e1",
        "name": background_name,
        "category": "environment",
        "appearance": [f"simple {palette} palette"],
        "role": "background",
        "depth": 0,
    }]

    used_names = {background_name}
    candidates = list(SCENE_CANDIDATES[scene_type])
    main_candidates = [candidate for candidate in candidates if candidate[0] in {"animal", "person", "vehicle"}]
    if not main_candidates:
        main_candidates = candidates[:]
    main_subject = rng.choice(main_candidates)
    candidates.remove(main_subject)
    rng.shuffle(candidates)
    relation_types: list[str] = []
    selected_candidates = [main_subject, *candidates[: max(0, layer_count - 2)]]
    for offset, (category, name) in enumerate(selected_candidates, start=1):
        used_names.add(name)
        role = "main_subject" if offset == 1 else "supporting_subject"
        entities.append({
            "id": f"e{offset + 1}",
            "name": name,
            "category": category,
            "appearance": [f"recognizable illustrated form", f"coordinated {palette} color details"],
            "role": role,
            "depth": offset,
        })

    relations: list[dict[str, Any]] = []
    if layer_count >= 2:
        first_entity = entities[1]
        base_relation = _base_relation(first_entity, background_name)
        relations.append({
            "source": "e2",
            "type": base_relation,
            "target": "e1",
            "occlusion": "none",
        })
        relation_types.append(base_relation)
    for source_index in range(3, layer_count + 1):
        source = entities[source_index - 1]
        target = entities[1]
        relation = "in_front_of" if rng.random() < 0.65 else "beside"
        relation_types.append(relation)
        relations.append({
            "source": source["id"],
            "type": relation,
            "target": target["id"],
            "occlusion": "none",
        })

    occluding_relations = [relation for relation in relations if relation["type"] == "in_front_of"]
    occlusion_level = rng.choice(OCCLUSIONS[1:]) if occluding_relations else "none"
    for relation in occluding_relations:
        relation["occlusion"] = occlusion_level

    complexity = _complexity(layer_count, relation_types)
    plan: dict[str, Any] = {
        "plan_version": "0.1",
        "sample_id": f"sample_{index:04d}",
        "image_seed": image_seed,
        "taxonomy": {
            "layer_count": layer_count,
            "subject_families": sorted({entity["category"] for entity in entities}),
            "scene_type": scene_type,
            "relation_pattern": "support_and_depth_order",
            "occlusion_level": occlusion_level,
            "complexity": complexity,
            "composition": composition,
            "viewpoint": viewpoint,
            "palette": palette,
        },
        "entities": entities,
        "relations": relations,
        "prompt_policy": {
            "allow_extra_objects": False,
            "allow_text": False,
            "allow_gradients": False,
            "background_detail": "low",
        },
    }
    errors = validate_plan(plan)
    if errors:
        raise ValueError(f"generated invalid plan {plan['sample_id']}: {'; '.join(errors)}")
    return plan


def semantic_signature(plan: dict[str, Any]) -> tuple[Any, ...]:
    taxonomy = plan["taxonomy"]
    names = tuple(entity["name"] for entity in plan["entities"])
    relation_types = tuple(relation["type"] for relation in plan["relations"])
    return (
        taxonomy["layer_count"],
        names,
        taxonomy["scene_type"],
        relation_types,
        taxonomy["occlusion_level"],
        taxonomy["viewpoint"],
    )


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    taxonomy = plan.get("taxonomy", {})
    entities = plan.get("entities", [])
    target = taxonomy.get("layer_count")
    if not isinstance(target, int) or not 2 <= target <= 6:
        errors.append("taxonomy.layer_count must be an integer from 2 to 6")
    if target != len(entities):
        errors.append("layer_count must equal the number of entities")
    image_seed = plan.get("image_seed")
    if not isinstance(image_seed, int) or not 0 <= image_seed <= 2147483647:
        errors.append("image_seed must be an integer from 0 to 2147483647")

    ids = [entity.get("id") for entity in entities]
    if len(ids) != len(set(ids)):
        errors.append("entity IDs must be unique")
    depths = sorted(entity.get("depth") for entity in entities)
    if depths != list(range(len(entities))):
        errors.append("depth must be continuous from 0 (back) to N-1 (front)")
    if not entities or entities[0].get("category") != "environment":
        errors.append("the back-most entity must be an environment region")

    entity_by_id = {entity.get("id"): entity for entity in entities}
    for relation in plan.get("relations", []):
        source = entity_by_id.get(relation.get("source"))
        target_entity = entity_by_id.get(relation.get("target"))
        if source is None or target_entity is None:
            errors.append("relations must reference existing entities")
            continue
        relation_type = relation.get("type")
        if relation_type not in RELATION_TYPES:
            errors.append(f"unsupported relation type: {relation_type}")
        if relation_type == "in_front_of" and source["depth"] <= target_entity["depth"]:
            errors.append("in_front_of must point from a larger depth to a smaller depth")
        if relation_type == "behind" and source["depth"] >= target_entity["depth"]:
            errors.append("behind must point from a smaller depth to a larger depth")
        if relation.get("occlusion") not in OCCLUSIONS:
            errors.append("relation occlusion must be none, light, or medium")
    relation_occlusions = {
        relation.get("occlusion")
        for relation in plan.get("relations", [])
        if relation.get("type") == "in_front_of"
    }
    expected_occlusion = next(iter(relation_occlusions)) if relation_occlusions else "none"
    if len(relation_occlusions) > 1:
        errors.append("all planned in_front_of relations must use the same occlusion level")
    if taxonomy.get("occlusion_level") != expected_occlusion:
        errors.append("taxonomy.occlusion_level must match planned in_front_of relations")
    return errors

