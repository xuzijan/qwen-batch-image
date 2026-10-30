#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取冻结的 plans/prompts，按一条 Prompt 生成一张图片。

该脚本不会生成多个候选图来替代一个样本：每条 Prompt 的请求参数固定为 n=1，
并将重试、任务 ID、图片哈希和状态写入 manifest.jsonl。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qwen_batch_image import (
    API_KEY,
    SUBMIT_URL,
    ApiError,
    download,
    get_task_id,
    headers,
    http_json,
    image_urls,
    load_local_api_key,
    wait_for_task,
)
from render_prompts import load_jsonl, sha256_json, sha256_text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def submit_and_get_url(
    api_key: str,
    prompt: str,
    model: str,
    size: str,
    seed: int,
    negative_prompt: str,
    timeout: int,
    poll_interval: float,
) -> tuple[str, str | None, str | None, dict[str, Any]]:
    parameters: dict[str, Any] = {"size": size, "n": 1, "seed": seed}
    if negative_prompt:
        parameters["negative_prompt"] = negative_prompt
    payload: dict[str, Any] = {
        "model": model,
        "input": {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
        },
        "parameters": parameters,
    }
    submitted = http_json(SUBMIT_URL, "POST", headers(api_key), payload)
    provider_request_id = submitted.get("request_id")
    try:
        direct_urls = image_urls(submitted)
    except ApiError:
        direct_urls = []
    task_id: str | None = None
    result = submitted
    if direct_urls:
        url = direct_urls[0]
    else:
        task_id = get_task_id(submitted)
        result = wait_for_task(api_key, task_id, timeout, poll_interval)
        url = image_urls(result)[0]
        provider_request_id = provider_request_id or result.get("request_id")
    return url, task_id, provider_request_id, parameters


def generate_one(
    plan: dict[str, Any],
    prompt_record: dict[str, Any],
    args: argparse.Namespace,
    api_key: str,
    image_dir: Path,
) -> dict[str, Any]:
    sample_id = plan["sample_id"]
    prompt = prompt_record["prompt"]
    output_path = image_dir / f"{sample_id}.png"
    last_error: Exception | None = None
    attempt_records: list[dict[str, Any]] = []
    for attempt in range(1, args.retries + 1):
        started = utc_now()
        task_id = None
        try:
            url, task_id, request_id, parameters = submit_and_get_url(
                api_key=api_key,
                prompt=prompt,
                model=args.model,
                size=args.size,
                seed=int(plan["image_seed"]),
                negative_prompt=args.negative_prompt,
                timeout=args.timeout,
                poll_interval=args.poll_interval,
            )
            download(url, output_path)
            attempt_records.append({
                "attempt": attempt,
                "started_at": started,
                "completed_at": utc_now(),
                "task_id": task_id,
                "provider_request_id": request_id,
                "status": "succeeded",
                "error": None,
            })
            return {
                "sample_id": sample_id,
                "plan_sha256": sha256_json(plan),
                "prompt_sha256": sha256_text(prompt),
                "model": args.model,
                "size": args.size,
                "seed": plan["image_seed"],
                "seed_scope": "image_generation",
                "api_endpoint": SUBMIT_URL,
                "request_parameters": parameters,
                "attempt": attempt,
                "attempts": attempt_records,
                "submitted_at": started,
                "completed_at": utc_now(),
                "task_id": task_id,
                "provider_request_id": request_id,
                "image_path": str(output_path.relative_to(args.output_dir)).replace("\\", "/"),
                "image_sha256": sha256_file(output_path),
                "status": "succeeded",
                "auto_review": "pending",
                "manual_review": "pending",
                "error": None,
            }
        except Exception as exc:  # one sample failure must not cancel the batch
            last_error = exc
            attempt_records.append({
                "attempt": attempt,
                "started_at": started,
                "completed_at": utc_now(),
                "task_id": task_id,
                "status": "failed",
                "error": str(exc),
            })
            if attempt < args.retries:
                time.sleep(min(30, 2 ** (attempt - 1)))
    return {
        "sample_id": sample_id,
        "plan_sha256": sha256_json(plan),
        "prompt_sha256": sha256_text(prompt),
        "model": args.model,
        "size": args.size,
        "seed": plan.get("image_seed"),
        "seed_scope": "image_generation",
        "api_endpoint": SUBMIT_URL,
        "attempt": args.retries,
        "attempts": attempt_records,
        "status": "failed",
        "auto_review": "pending",
        "manual_review": "pending",
        "error": str(last_error),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按计划逐张调用千问生图 API")
    parser.add_argument("--plans", type=Path, required=True)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None, help="只生成前 N 个计划；用于小规模试跑")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--model", default="qwen-image-3.0-pro")
    parser.add_argument("--size", default="1024*1024")
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--api-key", default=API_KEY, help="也可使用 DASHSCOPE_API_KEY 环境变量")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1 or args.retries < 1:
        print("workers 和 retries 必须是正整数", file=sys.stderr)
        return 2
    plans = load_jsonl(args.plans)
    prompt_records = load_jsonl(args.prompts)
    if args.limit is not None:
        if args.limit < 1:
            print("limit 必须是正整数", file=sys.stderr)
            return 2
        plans = plans[:args.limit]
    prompts_by_id = {record["sample_id"]: record for record in prompt_records}
    missing = [plan["sample_id"] for plan in plans if plan["sample_id"] not in prompts_by_id]
    if missing:
        print(f"缺少 Prompt：{', '.join(missing)}", file=sys.stderr)
        return 2

    args.output_dir = args.output_dir or args.plans.parent
    image_dir = args.output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    api_key = args.api_key or os.getenv("DASHSCOPE_API_KEY", "") or load_local_api_key()
    if not api_key:
        api_key = input("请输入 DashScope API Key（不会写入文件）：").strip()
    if not api_key:
        print("没有提供 API Key", file=sys.stderr)
        return 2

    workers = min(args.workers, len(plans))
    print(f"开始生成 {len(plans)} 张图片；每个 Prompt 一张图；并发={workers}")
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(generate_one, plan, prompts_by_id[plan["sample_id"]], args, api_key, image_dir): plan["sample_id"]
            for plan in plans
        }
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            status = record["status"]
            print(f"[{record['sample_id']}] {status}", flush=True)

    records.sort(key=lambda record: record["sample_id"])
    manifest_path = args.output_dir / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    failures = [record for record in records if record["status"] != "succeeded"]
    print(f"完成 {len(records) - len(failures)}/{len(records)} 张；manifest：{manifest_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

