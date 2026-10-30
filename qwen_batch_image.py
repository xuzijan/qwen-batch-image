#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用阿里云 DashScope / 千问生图接口批量生成图片。

最简单的用法：
    1. 设置环境变量 DASHSCOPE_API_KEY，或在下面的 API_KEY 留空时运行时输入。
    2. 修改 PROMPT、COUNT，然后执行：python qwen_batch_image.py

也支持命令行参数，完整示例见同目录 README_qwen_batch.md。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


# ====== 你可以直接修改这里 ======
API_KEY = ""  # 建议使用环境变量 DASHSCOPE_API_KEY，或运行时输入
PROMPT = r"""Task

Create exactly one original, visually appealing illustration in a clean, modern 2D vector-art style. The illustration belongs to a large, diverse collection designed for semantic object-level layer separation. Independently invent the subject, scene, characters, setting, and composition. The final result must feel like polished standalone artwork, not a segmentation diagram.

## 1. Scene and creativity

Freely explore everyday life, animals, nature, food, travel, fantasy, leisure, and other recognizable concepts. Favor a clear visual focal point and a simple, understandable relationship among a few entities. A bear in a boat, a cat beside a flowerpot, and a cottage next to a tree are illustrative examples only; do not repeatedly recreate them. Across samples, vary subject categories, settings, perspectives, palettes, and composition.

## 2. Semantic layer structure

The entire illustration must naturally decompose into 2–6 semantic layers, including background regions. Each layer corresponds to one complete meaningful entity: a character, animal, physical object, or coherent environmental region such as sky, sea, ground, or hillside. An entity may contain several internal shapes or paths, but facial features, clothing, color patches, and structural details remain part of that same entity. Plan the entity list and stacking order before rendering; do not exceed six layers.

## 3. Entity independence and occlusion

Give each entity a recognizable identity, clear boundary, and coherent silhouette. Design the scene so that each entity can be managed as one semantic layer. Natural occlusion is allowed if the depth order remains clear—for example, a character seated in a boat or a cloud covering the sun. Avoid heavily interlocking silhouettes, ambiguous fused boundaries, and tiny decorative entities. Only the final composite illustration is required: hidden portions of occluded objects do not need amodal completion.

## 4. Visual style

Use polished, charming, minimalist 2D vector aesthetics: smooth geometric and organic shapes, solid flat fills, a harmonious restrained palette, crisp contours, coherent design language, minimal identity-preserving details, and balanced negative space. Keep objects expressive but uncomplicated. No photorealism, painterly textures, intricate patterns, gradients, or elaborate lighting.

## 5. Complexity control

Prioritize clarity at a glance over dense detail. Avoid complicated buildings and machines, crowds, numerous repeated items, tiny accessories, decorative particles, busy environments, and overly intricate silhouettes. Prefer a few well-designed entities to many superficial ones.

## 6. Composition

Present a single coherent scene with one strong focal point. Arrange entities with plausible spatial and support relationships. Keep backgrounds simple but supportive, maintain a clear visual hierarchy, and leave comfortable margins inside the canvas.

## 7. Output requirements

Prefer one complete editable SVG image with viewBox="0 0 1536 1024" (landscape 3:2). Optionally render a matching 1536 × 1024 PNG preview. In the SVG, place each semantic entity in its own named <g> group when possible. Show only the final composite illustration, not separated/exploded layers. No text, captions, labels, watermarks, frame, layer numbers, construction guides, or displayed segmentation masks.

## 8. Final check

Before output, verify that the scene is recognizable and coherent; there are exactly 2–6 semantic entities including background; each entity maps to one layer; internal details stay with their parent; depth relationships are plausible; the artwork is simple yet visually complete; and the sample contributes diversity to a larger dataset. If not, simplify or redesign before rendering."""
COUNT = 5
MODEL = "qwen-image-3.0-pro"
OUTPUT_DIR = "qwen_outputs"
SIZE = "1024*1024"
NEGATIVE_PROMPT = ""
WORKERS = 3  # 并发数；遇到限流时改小，例如 1 或 2
POLL_INTERVAL = 2.0
TIMEOUT = 300
RETRIES = 3
BASE_SEED = 20261027

SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"


class ApiError(RuntimeError):
    pass


def load_local_api_key() -> str:
    """Load a local, gitignored DashScope key without requiring python-dotenv."""
    candidates = [Path(__file__).with_name(".env"), Path.cwd() / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "DASHSCOPE_API_KEY":
                return value.strip().strip("\"'")
    return ""


def http_json(url: str, method: str, headers: dict[str, str], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"网络错误：{exc.reason}") from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(f"接口返回的不是 JSON：{raw[:500]}") from exc
    if not isinstance(result, dict):
        raise ApiError(f"接口返回格式异常：{result!r}")
    return result


def headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def get_task_id(result: dict[str, Any]) -> str:
    task_id = result.get("output", {}).get("task_id")
    if not task_id:
        message = result.get("message") or result.get("code") or repr(result)
        raise ApiError(f"提交任务失败：{message}")
    return str(task_id)


def wait_for_task(api_key: str, task_id: str, timeout: int, poll_interval: float) -> dict[str, Any]:
    started = time.monotonic()
    url = TASK_URL.format(task_id=task_id)
    while time.monotonic() - started < timeout:
        result = http_json(url, "GET", headers(api_key))
        output = result.get("output", {})
        status = output.get("task_status")
        if status == "SUCCEEDED":
            return result
        if status in {"FAILED", "CANCELED", "UNKNOWN"}:
            message = output.get("message") or result.get("message") or repr(result)
            raise ApiError(f"任务 {task_id} {status}：{message}")
        time.sleep(poll_interval)
    raise ApiError(f"任务 {task_id} 超过 {timeout} 秒仍未完成")


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "qwen-batch-image/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise ApiError(f"下载图片失败：{exc}") from exc
    if not data:
        raise ApiError("下载到的图片为空")
    destination.write_bytes(data)


def image_urls(result: dict[str, Any]) -> list[str]:
    results = result.get("output", {}).get("results", [])
    urls = [item.get("url") for item in results if isinstance(item, dict) and item.get("url")]
    if not urls:
        choices = result.get("output", {}).get("choices", [])
        for choice in choices:
            content = choice.get("message", {}).get("content", []) if isinstance(choice, dict) else []
            urls.extend(item.get("image") for item in content if isinstance(item, dict) and item.get("image"))
    if not urls:
        raise ApiError(f"任务成功但没有图片 URL：{result}")
    return [str(url) for url in urls]


def generate_one(index: int, args: argparse.Namespace, api_key: str, output_dir: Path) -> Path:
    seed = args.base_seed + index
    payload: dict[str, Any] = {
        "model": args.model,
        "input": {
            "messages": [{
                "role": "user",
                "content": [{"text": args.prompt}],
            }],
        },
        "parameters": {"size": args.size, "n": 1, "seed": seed},
    }
    if args.negative_prompt:
        payload["parameters"]["negative_prompt"] = args.negative_prompt

    last_error: Exception | None = None
    for attempt in range(1, args.retries + 1):
        try:
            submitted = http_json(SUBMIT_URL, "POST", headers(api_key), payload)
            url = image_urls(submitted)[0]
            destination = output_dir / f"qwen_{index:04d}.png"
            download(url, destination)
            return destination
        except ApiError as exc:
            last_error = exc
            if attempt < args.retries:
                delay = min(30, 2 ** (attempt - 1))
                print(f"[{index}/{args.count}] 第 {attempt} 次失败：{exc}；{delay} 秒后重试", flush=True)
                time.sleep(delay)
    raise ApiError(f"第 {index} 张生成失败：{last_error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量调用千问/DashScope 生图接口")
    parser.add_argument("--prompt", default=PROMPT)
    parser.add_argument("--count", type=int, default=COUNT)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--size", default=SIZE, help="例如 1024*1024")
    parser.add_argument("--negative-prompt", default=NEGATIVE_PROMPT)
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--poll-interval", type=float, default=POLL_INTERVAL)
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    parser.add_argument("--retries", type=int, default=RETRIES)
    parser.add_argument("--base-seed", type=int, default=BASE_SEED)
    parser.add_argument("--api-key", default=API_KEY, help="也可使用 DASHSCOPE_API_KEY 环境变量")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count < 1 or args.workers < 1 or args.retries < 1:
        print("count、workers、retries 必须是正整数", file=sys.stderr)
        return 2
    api_key = args.api_key or os.getenv("DASHSCOPE_API_KEY", "") or load_local_api_key()
    if not api_key:
        api_key = input("请输入 DashScope API Key（不会写入文件）：").strip()
    if not api_key:
        print("没有提供 API Key", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    workers = min(args.workers, args.count)
    print(f"开始生成 {args.count} 张图片，模型={args.model}，并发={workers}，保存到：{output_dir.resolve()}")

    completed: list[Path] = []
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(generate_one, index, args, api_key, output_dir): index
            for index in range(1, args.count + 1)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                path = future.result()
                completed.append(path)
                print(f"[{index}/{args.count}] 完成：{path}", flush=True)
            except Exception as exc:  # 单张失败不影响其余任务
                failures.append(f"第 {index} 张：{exc}")
                print(f"[{index}/{args.count}] 失败：{exc}", file=sys.stderr, flush=True)

    print(f"完成 {len(completed)}/{args.count} 张。")
    if failures:
        print("失败列表：", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
