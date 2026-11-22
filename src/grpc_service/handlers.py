import time
from typing import Any, Callable


def _clean_nulls(context: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    rows = context["rows"]
    drop_ratio = float(params.get("drop_ratio", 0.05))
    removed = int(rows * drop_ratio)
    context["rows"] = max(0, rows - removed)
    return {"removed_null_rows": removed, "remaining_rows": context["rows"]}


def _normalize(context: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    method = params.get("method", "z-score")
    return {"method": method, "processed_rows": context["rows"], "normalized": True}


def _aggregate_stats(context: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    group_by = params.get("group_by", "default")
    return {
        "group_by": group_by,
        "total_rows": context["rows"],
        "estimated_groups": max(1, context["rows"] // 100),
    }


def _filter_outliers(context: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    threshold = float(params.get("threshold", 3.0))
    removed = int(context["rows"] * 0.02)
    context["rows"] = max(0, context["rows"] - removed)
    return {"threshold": threshold, "outliers_removed": removed, "remaining_rows": context["rows"]}


HANDLERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "clean_nulls": _clean_nulls,
    "normalize": _normalize,
    "aggregate_stats": _aggregate_stats,
    "filter_outliers": _filter_outliers,
}


def run_handler(handler_name: str, context: dict[str, Any], params: dict[str, Any]) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    handler = HANDLERS.get(handler_name)
    if handler is None:
        result = {"handler": handler_name, "mode": "generic", "processed_rows": context["rows"], "params": params}
    else:
        result = handler(context, params)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    return result, duration_ms