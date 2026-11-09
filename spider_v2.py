import argparse
import asyncio
import json
import math
import os
import time
from pathlib import Path

from pydantic import Field

from src.domain.categories.vehicles import VehicleCategory
from src.domain.models.listing import SourceQuery, StrictModel
from src.infrastructure.sources.demo import DemoAdapter
from src.services.source_scan_service import SourceScanService


class ScanTask(StrictModel):
    task_name: str = Field(min_length=1)
    source: str
    category: str
    enabled: bool = True
    text: str = ""
    filters: dict = Field(default_factory=dict)


async def main():
    app_name = os.getenv("APP_NAME", "Deal Alerts Demo")
    parser = argparse.ArgumentParser(description=f"{app_name}: local source preview (no AI or notifications).")
    parser.add_argument("--source", choices=["demo"], default="demo")
    parser.add_argument("--category", default="vehicles")
    parser.add_argument("--query", default="")
    parser.add_argument("--filters", default="{}", help="Category filters as a JSON object")
    parser.add_argument("--config", type=Path, help="Explicit source-neutral task JSON; legacy tasks are not imported")
    parser.add_argument("--task-name", help="Select a named task from --config")
    parser.add_argument("--debug-limit", type=int, default=0)
    timing = parser.add_mutually_exclusive_group()
    timing.add_argument("--demo-elapsed", type=float, help="Deterministic seconds since demo start")
    timing.add_argument("--demo-epoch", type=float, help="Shared demo start as Unix timestamp; otherwise DEMO_EPOCH or now")
    args = parser.parse_args()
    if args.debug_limit < 0:
        parser.error("--debug-limit cannot be negative")
    if args.task_name and not args.config:
        parser.error("--task-name requires an explicit --config; legacy scheduled tasks are disabled")
    try:
        if args.config:
            raw_tasks = json.loads(args.config.read_text(encoding="utf-8"))
            if not isinstance(raw_tasks, list):
                raise ValueError("Task config must be a JSON array")
            tasks = [ScanTask.model_validate(task) for task in raw_tasks]
            if args.task_name and not any(task.task_name == args.task_name for task in tasks):
                raise ValueError("Unknown task name")
            tasks = [task for task in tasks if task.enabled and (not args.task_name or task.task_name == args.task_name)]
        else:
            tasks = [ScanTask(task_name="demo", source=args.source, category=args.category,
                              text=args.query, filters=json.loads(args.filters))]
        if args.demo_elapsed is not None:
            if args.demo_elapsed < 0 or not math.isfinite(args.demo_elapsed):
                raise ValueError("Demo elapsed seconds must be finite and nonnegative")
            adapter = DemoAdapter(epoch=0.0, clock=lambda: args.demo_elapsed)
        else:
            epoch = args.demo_epoch if args.demo_epoch is not None else float(os.getenv("DEMO_EPOCH", str(time.time())))
            if not math.isfinite(epoch):
                raise ValueError("Demo epoch must be finite")
            adapter = DemoAdapter(epoch=epoch)
        service = SourceScanService(sources=[adapter], categories=[VehicleCategory()])
        for task in tasks:
            results = await service.scan(task.source, SourceQuery(category=task.category, text=task.text), task.filters)
            for result in results[:args.debug_limit or None]:
                print(result.model_dump_json())
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    asyncio.run(main())