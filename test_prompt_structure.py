#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checks that image-specific plans add only their subject-action sentence."""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from render_prompts import LEGACY_PROMPT, render_prompt, write_markdown_prompt_pack
from taxonomy import SUBJECT_CATALOG, action_descriptions, available_subjects, build_plan, semantic_signature, validate_plan
from validate_prompts import validate


class PromptStructureTests(unittest.TestCase):
    def test_rendering_appends_only_action_description(self) -> None:
        plan = build_plan(1, random.Random(20261101), 20261102)
        prompt = render_prompt(plan)

        self.assertEqual(prompt, f"{LEGACY_PROMPT}\n\n{plan['image_description']}")
        self.assertEqual(prompt.count(plan["image_description"]), 1)
        self.assertNotIn("intended occlusion level", prompt.lower())
        self.assertNotIn("setting with one clear focal point centered on", prompt.lower())

    def test_plan_metadata_does_not_change_prompt_deduplication(self) -> None:
        first = build_plan(1, random.Random(2), 101)
        second = dict(first)
        second["taxonomy"] = dict(first["taxonomy"], layer_count_target=6, occlusion_level_target="medium")

        self.assertEqual(semantic_signature(first), semantic_signature(second))
        self.assertEqual(render_prompt(first), render_prompt(second))

    def test_generated_plan_and_prompt_validate(self) -> None:
        plan = build_plan(1, random.Random(3), 102)
        prompt = render_prompt(plan)
        from render_prompts import sha256_json, sha256_text

        prompt_record = {
            "sample_id": plan["sample_id"],
            "prompt": prompt,
            "plan_sha256": sha256_json(plan),
            "prompt_sha256": sha256_text(prompt),
            "image_seed": plan["image_seed"],
        }
        self.assertEqual(validate_plan(plan), [])
        self.assertEqual(validate([plan], [prompt_record]), [])

    def test_wordnet_catalog_has_batchable_prompts_for_each_term(self) -> None:
        families = {record["family"] for record in SUBJECT_CATALOG}
        self.assertEqual(
            families,
            {"person", "animal", "plant", "fungus", "artifact", "natural_object", "solid_food", "beverage"},
        )
        self.assertGreater(len(available_subjects("P0")), 100)
        for subject in SUBJECT_CATALOG:
            descriptions = action_descriptions(subject)
            self.assertTrue(descriptions)
            self.assertTrue(all(description.count(".") == 1 for description in descriptions))

    def test_markdown_pack_contains_complete_copyable_prompts(self) -> None:
        plans = [build_plan(index, random.Random(index), 200 + index) for index in range(1, 4)]
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "prompts_for_web.md"
            write_markdown_prompt_pack(plans, destination)
            markdown = destination.read_text(encoding="utf-8")

        self.assertEqual(markdown.count("```text"), len(plans))
        for plan in plans:
            self.assertIn(f"{LEGACY_PROMPT}\n\n{plan['image_description']}", markdown)


if __name__ == "__main__":
    unittest.main()
