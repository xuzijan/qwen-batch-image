#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WordNet 白名单、主体行为句、计划采样和计划级校验。"""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).with_name("taxonomy_subjects.tsv")
PRIORITIES = ("P0", "P1", "unranked")
OCCLUSIONS = ("none", "light", "medium")


def load_subject_catalog(path: Path = CATALOG_PATH) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle, delimiter="\t"))
    required = {"family", "family_zh", "branch", "name_zh", "prompt_term", "synset", "priority"}
    if not records or not required.issubset(records[0]):
        raise ValueError(f"{path} must contain the WordNet subject catalog columns: {sorted(required)}")
    synsets = [record["synset"] for record in records]
    if len(synsets) != len(set(synsets)):
        raise ValueError(f"{path} contains duplicate WordNet synsets")
    for record in records:
        if record["priority"] not in PRIORITIES:
            raise ValueError(f"unsupported priority {record['priority']!r} for {record['synset']}")
    return records


SUBJECT_CATALOG = load_subject_catalog()
SUBJECTS_BY_FAMILY: dict[str, tuple[dict[str, str], ...]] = {}
_grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
for _record in SUBJECT_CATALOG:
    _grouped[_record["family"]].append(_record)
SUBJECTS_BY_FAMILY = {family: tuple(records) for family, records in _grouped.items()}

# Hand-reviewed action sentences are used where available. Other WordNet terms
# receive a short family/branch-level sentence so the whole catalog is usable.
ACTION_DESCRIPTIONS: dict[str, tuple[str, ...]] = {
    "cat": ("A cat is batting a ball across the floor.", "A cat is pawing at a dangling toy."),
    "dog": ("A dog is chasing a rolling ball.", "A dog is carrying a stick."),
    "fox": ("A fox is sniffing a mushroom.", "A fox is stepping over a fallen branch."),
    "bear": ("A bear is reaching for a honey pot.", "A bear is catching a fish."),
    "rabbit": ("A rabbit is nibbling on a leaf.", "A rabbit is hopping over a small stone."),
    "eagle": ("An eagle is carrying a twig to its nest.", "An eagle is watching a fish below."),
    "tortoise": ("A tortoise is stepping over a small stone.", "A tortoise is reaching toward a leaf."),
    "goldfish": ("A goldfish is swimming among aquatic plants.", "A goldfish is blowing a trail of bubbles."),
    "gardener": ("A gardener is watering a row of seedlings.", "A gardener is planting a small flower."),
    "cook": ("A cook is stirring a pot of soup.", "A cook is arranging vegetables on a cutting board."),
    "cyclist": ("A cyclist is riding a bicycle.", "A cyclist is checking a bicycle wheel."),
    "tourist": ("A tourist is unfolding a map.", "A tourist is lifting a suitcase."),
    "musician": ("A musician is playing a guitar.", "A musician is tuning a violin."),
    "child": ("A child is stacking wooden blocks.", "A child is rolling a toy car."),
    "bread": ("A loaf of bread is being sliced on a board.", "A slice of bread is resting beside a small plate."),
    "cake": ("A cake is being decorated with berries.", "A slice of cake is resting on a plate."),
    "apple": ("An apple is rolling beside a basket.", "An apple is being cut into slices."),
    "sandwich": ("A sandwich is being cut in half.", "A sandwich is resting on a small plate."),
    "teacup": ("A teacup of tea is steaming beside a teapot.", "A teacup is being filled from a teapot."),
    "basket": ("A basket is holding several pieces of fruit.", "A basket is being filled with apples."),
    "pine": ("A pine tree is swaying gently in the breeze.", "A pine tree is growing beside a winding path."),
    "rose": ("A rose is bending gently in the breeze.", "A rose is growing beside a garden path."),
    "sunflower": ("A sunflower is turning toward the sunlight.", "A sunflower is bending gently in the breeze."),
    "mushroom": ("A mushroom is growing beside a fallen log.", "A small mushroom is emerging from the soil."),
    "bicycle": ("A bicycle is rolling down a gentle path.", "A bicycle is leaning beside a wooden bench."),
    "motorcycle": ("A motorcycle is rolling along a quiet road.", "A motorcycle is parked beside a wooden fence."),
    "boat": ("A boat is gliding across calm water.", "A boat is passing a floating buoy."),
    "train": ("A train is passing through the countryside.", "A train is moving along the tracks."),
    "balloon": ("A balloon is floating above the hills.", "A balloon is drifting through the sky."),
    "crate": ("A crate is holding a few apples.", "A crate is being carried by its handles."),
    "pot": ("A pot is holding a blooming plant.", "A pot is being filled with soil."),
    "bench": ("A wooden bench stands beside a garden path.", "A wooden bench is being painted."),
    "backpack": ("A backpack is resting beside a pair of shoes.", "A backpack is being lifted by a traveler."),
    "lantern": ("A lantern is glowing beside a woven basket.", "A lantern is being lit."),
    "blender": ("A blender is blending fruit into a smoothie.", "A blender is mixing ingredients on a kitchen counter."),
    "tomato": ("A tomato is being sliced on a cutting board.", "A tomato is resting beside a few fresh herbs."),
    "lavender": ("Lavender is blooming beside a garden path.", "Lavender is swaying gently in the breeze."),
    "shiitake": ("A shiitake mushroom is growing on a piece of wood.", "A shiitake mushroom is resting beside a fallen log."),
    # The WordNet entry remains cattle, but the prompt uses one representative
    # cow so the generator does not turn the sample into a herd scene.
    "cattle": ("A single cartoon cow is grazing on a flat patch of grass.", "A single cartoon cow is standing on a flat patch of grass."),
}


NO_INDEFINITE_ARTICLE = {
    "bamboo", "broccoli", "butter", "cattle", "cheese", "chicken", "clothing",
    "coffee", "corn", "cream", "furniture", "grass", "hair", "ice", "ice cream",
    "lightning", "luggage", "milk", "moonlight", "music", "pork", "rain", "rice",
    "salad", "scenery", "seaweed", "soup", "sushi", "tea", "thunder", "underwear",
    "wheat", "yogurt",
}
PLURAL_SUBJECTS = {"cattle", "people"}
DEFINITE_ARTICLE = {"moon", "sun", "earth"}


def _subject_phrase(term: str) -> tuple[str, bool]:
    """Return a natural subject phrase and whether it takes a plural verb."""
    normalized = term.lower()
    plural = normalized in PLURAL_SUBJECTS
    if normalized in DEFINITE_ARTICLE:
        return f"the {term}", plural
    if normalized in NO_INDEFINITE_ARTICLE:
        return term, plural
    first = normalized.split()[0]
    article = "an" if first[:1] in "aeiou" and first not in {"unicorn", "university"} else "a"
    return f"{article} {term}", plural


def action_descriptions(subject: dict[str, str]) -> tuple[str, ...]:
    """Return two concise, grammatical actions suitable for a copyable prompt."""
    term = subject["prompt_term"]
    curated = ACTION_DESCRIPTIONS.get(term)
    if curated:
        return curated

    family = subject["family"]
    branch = subject.get("branch", "")
    phrase, plural = _subject_phrase(term)
    be = "are" if plural else "is"
    if family == "animal" and term.lower() == "chicken":
        phrase = "a chicken"

    if family == "person":
        return (f"{phrase} {be} tending a small plant.", f"{phrase} {be} carrying a shopping bag.")
    if family == "animal":
        if term.lower() in {"bat", "dolphin", "seal", "whale"}:
            if term.lower() == "bat":
                return (f"{phrase} {be} hanging upside down from a branch.", f"{phrase} {be} flying through the dusk sky.")
            return (f"{phrase} {be} swimming through clear water.", f"{phrase} {be} surfacing beside a gentle wave.")
        actions = {
            "鸟类": ("perched on a branch", "gathering material for a nest"),
            "鱼类": ("swimming among aquatic plants", "gliding through clear water"),
            "昆虫": ("resting on a leaf", "moving across a flower"),
            "蛛形动物": ("resting on a leaf", "moving across a flower"),
            "两栖动物": ("crossing a sunlit stone", "resting beside a pond"),
            "爬行动物": ("crossing a sunlit stone", "resting beside a pond"),
            "甲壳动物": ("walking along the shore", "exploring a tide pool"),
            "软体动物": ("moving slowly across a leaf", "resting beside a shell"),
            "棘皮动物": ("resting on the seafloor", "moving among underwater rocks"),
        }
        if term.lower() == "chicken":
            return ("A chicken is scratching in the grass.", "A chicken is pecking at a few grains.")
        first, second = actions.get(branch, ("walking through a natural setting", "reaching toward nearby food"))
        return (f"{phrase} {be} {first}.", f"{phrase} {be} {second}.")
    if family == "plant":
        if branch == "树木" and term.lower() in {"apple", "cherry", "lemon", "orange"}:
            phrase = f"a {term} tree"
        elif term.lower() in {"lavender", "rosemary", "bamboo", "duckweed", "corn", "rice", "wheat"}:
            phrase = term
        actions = {
            "树木": ("swaying gently in the breeze", "growing beside a path"),
            "观花植物": ("blooming beside a garden path", "swaying gently in the breeze"),
            "灌木": ("blooming beside a garden path", "swaying gently in the breeze"),
            "水生植物": ("floating on a pond", "growing along the water's edge"),
        }
        first, second = actions.get(branch, ("growing in a patch of sunlight", "bending gently in the breeze"))
        return (f"{phrase} {be} {first}.", f"{phrase} {be} {second}.")
    if family == "fungus":
        return (f"{phrase} {be} growing beside a fallen log.", f"{phrase} {be} emerging from the forest floor.")
    if family == "beverage":
        return (f"{phrase} {be} being poured into a cup.", f"{phrase} {be} steaming in a mug.")
    if family == "solid_food":
        if term.lower() in NO_INDEFINITE_ARTICLE:
            return (f"{phrase} {be} being served in a small bowl.", f"{phrase} {be} being prepared on a kitchen counter.")
        if term.lower() in {"ice cream", "mousse", "pudding", "custard", "cream", "milk", "yogurt"}:
            return (f"{phrase} {be} being scooped into a bowl.", f"{phrase} {be} being served for dessert.")
        if term.lower() in {"soup", "stew", "salad", "sushi", "broccoli", "pork", "chicken"}:
            return (f"{phrase} {be} being served in a bowl.", f"{phrase} {be} being prepared for a meal.")
        return (f"{phrase} {be} being served on a small plate.", f"{phrase} {be} being prepared for a meal.")
    if family == "natural_object":
        actions = {
            "天体": ("shining above the landscape", "appearing over a distant horizon"),
            "巢": ("resting among the branches", "holding a few nesting materials"),
        }
        first, second = actions.get(branch, ("resting beside a winding path", "catching a patch of sunlight"))
        return (f"{phrase} {be} {first}.", f"{phrase} {be} {second}.")
    if family == "artifact":
        actions = {
            "轮式交通工具": ("moving along a quiet path", "passing a roadside tree"),
            "水上交通工具": ("gliding across calm water", "passing a floating buoy"),
            "航空器": ("flying across the sky", "passing above the landscape"),
            "建筑物": ("standing beside an open space", "casting a simple shadow on the ground"),
            "其他构筑物": ("standing beside an open space", "casting a simple shadow on the ground"),
            "服装": ("hanging neatly on a hook", "being folded on a table"),
            "家具": ("standing beside a window", "holding a few everyday items"),
            "乐器": ("being played during a simple activity", "resting within easy reach"),
            "玩具": ("being used during play", "resting within easy reach"),
            "照明灯具": ("glowing in a softly lit room", "resting on a table"),
            "容器与箱包": ("holding a few everyday items", "being carried by its handle"),
        }
        first, second = actions.get(branch, ("being used for a simple everyday task", "resting on a tidy work surface"))
        return (f"{phrase} {be} {first}.", f"{phrase} {be} {second}.")
    return (f"{phrase} {be} resting in a natural setting.", f"{phrase} {be} catching a patch of sunlight.")


def available_subjects(priority: str = "P0", family: str | None = None) -> list[dict[str, str]]:
    if priority not in {"P0", "P1", "all"}:
        raise ValueError("priority must be P0, P1, or all")
    return [
        subject for subject in SUBJECT_CATALOG
        if (priority == "all" or subject["priority"] == priority)
        and (family is None or subject["family"] == family)
    ]


def _complexity(layer_count: int) -> str:
    if layer_count <= 2:
        return "simple"
    if layer_count >= 4:
        return "challenging"
    return "moderate"


def build_plan(
    index: int,
    rng: random.Random,
    image_seed: int,
    priority: str = "P0",
) -> dict[str, Any]:
    """Create one plan by cycling through available families and sampling a WordNet term."""

    catalog = available_subjects(priority)
    families = sorted({subject["family"] for subject in catalog})
    if not families:
        raise ValueError(f"no WordNet subjects found for priority {priority!r}")
    main_family = families[(index - 1) % len(families)]
    family_subjects = [subject for subject in catalog if subject["family"] == main_family]
    subject = rng.choice(family_subjects)
    image_description = rng.choice(action_descriptions(subject))
    image_description = image_description[0].upper() + image_description[1:]
    layer_count = rng.choices([2, 3, 4], weights=[3, 4, 1], k=1)[0]
    occlusion_level = rng.choice(OCCLUSIONS)
    plan: dict[str, Any] = {
        "plan_version": "0.3",
        "sample_id": f"sample_{index:04d}",
        "image_seed": image_seed,
        "image_description": image_description,
        "taxonomy": {
            "subject_families": [main_family],
            "subject_priority": subject["priority"],
            "layer_count_target": layer_count,
            "occlusion_level_target": occlusion_level,
            "complexity": _complexity(layer_count),
        },
        "entities": [{
            "id": "e1",
            "name": subject["prompt_term"],
            "name_zh": subject["name_zh"],
            "category": main_family,
            "synset": subject["synset"],
            "role": "main_subject",
        }],
        "prompt_policy": {
            "allow_extra_objects": False,
            "allow_text": False,
            "allow_gradients": False,
            "background_selection": "model_selected",
        },
    }
    errors = validate_plan(plan)
    if errors:
        raise ValueError(f"generated invalid plan {plan['sample_id']}: {'; '.join(errors)}")
    return plan


def semantic_signature(plan: dict[str, Any]) -> tuple[Any, ...]:
    main_subject = next(entity for entity in plan["entities"] if entity["role"] == "main_subject")
    return (main_subject["synset"], plan["image_description"])


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    taxonomy = plan.get("taxonomy", {})
    entities = plan.get("entities", [])
    target = taxonomy.get("layer_count_target")
    if not isinstance(target, int) or not 2 <= target <= 4:
        errors.append("taxonomy.layer_count_target must be an integer from 2 to 4")
    if not isinstance(plan.get("image_description"), str) or not plan["image_description"].strip():
        errors.append("image_description must be a non-empty sentence")
    elif plan["image_description"].count(".") != 1:
        errors.append("image_description must contain exactly one sentence")
    image_seed = plan.get("image_seed")
    if not isinstance(image_seed, int) or not 0 <= image_seed <= 2147483647:
        errors.append("image_seed must be an integer from 0 to 2147483647")

    ids = [entity.get("id") for entity in entities]
    if len(ids) != len(set(ids)):
        errors.append("entity IDs must be unique")
    main_subjects = [entity for entity in entities if entity.get("role") == "main_subject"]
    if len(main_subjects) != 1:
        errors.append("plans must contain exactly one main subject")
    else:
        subject = next((entry for entry in SUBJECT_CATALOG if entry["synset"] == main_subjects[0].get("synset")), None)
        if subject is None:
            errors.append("main subject synset must exist in the WordNet whitelist catalog")
        else:
            if main_subjects[0].get("category") != subject["family"]:
                errors.append("main subject category must match its WordNet catalog family")
            if plan.get("image_description", "").lower() not in {action.lower() for action in action_descriptions(subject)}:
                errors.append("image_description must be a predefined action for the main subject")
    if any(entity.get("category") == "environment" for entity in entities):
        errors.append("background must be selected by the model, not listed as a planned entity")
    if taxonomy.get("occlusion_level_target") not in OCCLUSIONS:
        errors.append("taxonomy.occlusion_level_target must be none, light, or medium")
    return errors
