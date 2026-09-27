"""Stress test the analysis API at increasing numbers of concurrent users.

Each simulated user uploads the contour map and waits for the result, as
the frontend does. For every concurrency level it prints throughput and
latency percentiles, plus how many requests failed or were turned away
as busy (503).

    python loadtest/load_test.py --url http://10.1.75.53:8080/api
    python loadtest/load_test.py --url http://127.0.0.1:8000 --levels 1,2,4 --requests 8
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _one_request(client: httpx.Client, url: str, file_bytes: bytes, area: str | None) -> tuple[int, float]:
    data = {"area": area} if area else None
    started = time.perf_counter()
    try:
        response = client.post(
            url,
            params={"include_contours": "false"},
            files={"contour_map": ("map.kml", file_bytes, "application/vnd.google-earth.kml+xml")},
            data=data,
        )
        status = response.status_code
    except httpx.HTTPError:
        status = 0  # connection failure or timeout
    return status, time.perf_counter() - started


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def run_level(url: str, file_bytes: bytes, area: str | None, users: int, total: int, timeout: float) -> dict:
    with httpx.Client(timeout=timeout) as client, ThreadPoolExecutor(max_workers=users) as pool:
        started = time.perf_counter()
        results = list(pool.map(lambda _: _one_request(client, url, file_bytes, area), range(total)))
        elapsed = time.perf_counter() - started

    ok_latencies = [latency for status, latency in results if status == 200]
    statuses = Counter(status for status, _ in results)
    return {
        "users": users,
        "requests": total,
        "ok": statuses.get(200, 0),
        "busy_503": statuses.get(503, 0),
        "failed": total - statuses.get(200, 0) - statuses.get(503, 0),
        "throughput": statuses.get(200, 0) / elapsed,
        "p50": statistics.median(ok_latencies) if ok_latencies else float("nan"),
        "p95": _percentile(ok_latencies, 95) if ok_latencies else float("nan"),
        "max": max(ok_latencies) if ok_latencies else float("nan"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="API base URL (the gateway's is .../api)")
    parser.add_argument("--file", default=str(ROOT / "samples" / "contours_1m.kml"), help="contour map to upload")
    parser.add_argument("--area", help="optional GeoJSON file with the area to analyze")
    parser.add_argument("--levels", default="1,4,8,16", help="comma-separated concurrent-user counts")
    parser.add_argument("--requests", type=int, default=16, help="requests per level")
    parser.add_argument("--timeout", type=float, default=180, help="per-request timeout in seconds")
    args = parser.parse_args()

    url = args.url.rstrip("/") + "/analyzeContour"
    file_bytes = pathlib.Path(args.file).read_bytes()
    area = json.dumps(json.loads(pathlib.Path(args.area).read_text())) if args.area else None

    print(f"POST {url}, {len(file_bytes) / 1e6:.1f} MB map, {args.requests} requests per level\n")
    print("| Users | OK | Busy (503) | Failed | Throughput (req/s) | p50 (s) | p95 (s) | Max (s) |")
    print("|---|---|---|---|---|---|---|---|")
    for users in (int(level) for level in args.levels.split(",")):
        r = run_level(url, file_bytes, area, users, max(args.requests, users), args.timeout)
        print(
            f"| {r['users']} | {r['ok']} | {r['busy_503']} | {r['failed']} | {r['throughput']:.2f} "
            f"| {r['p50']:.2f} | {r['p95']:.2f} | {r['max']:.2f} |",
            flush=True,
        )


if __name__ == "__main__":
    main()
