#!/usr/bin/env python3
"""
Entry point for CBS WCRT analytical tool (R1).

Usage:
    python -m src.run_analysis <test_case_dir> [--idle-slope 0.5] [--send-slope 0.5]

Example:
    python -m src.run_analysis mini-project-2/test-case-1
"""

import argparse
import csv
import os
import sys

from src.common.parser import parse_topology, parse_streams, parse_routes, resolve_stream_links
from src.analysis.cbs_analysis import compute_wcrt


def load_reference_wcrts(filepath: str) -> dict:
    """Load reference WCRTs from CSV (test-case-1-WCRTs.csv format)."""
    ref = {}
    with open(filepath) as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for row in reader:
            if len(row) >= 2:
                sid = int(row[0].strip())
                # Handle comma decimal separator (European locale)
                wcrt_str = row[1].strip().replace(",", ".")
                ref[sid] = float(wcrt_str)
    return ref


def main():
    parser = argparse.ArgumentParser(description="CBS WCRT Analysis Tool")
    parser.add_argument("test_dir", help="Path to test case directory")
    parser.add_argument("--idle-slope", type=float, default=0.5,
                        help="idleSlope fraction (default: 0.5)")
    parser.add_argument("--send-slope", type=float, default=0.5,
                        help="sendSlope fraction (default: 0.5)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-link breakdown")
    args = parser.parse_args()

    d = args.test_dir

    # Auto-detect file names (with or without prefix)
    def find(pattern):
        for f in os.listdir(d):
            if pattern in f.lower():
                return os.path.join(d, f)
        return None

    topo_file = find("topology")
    streams_file = find("streams")
    routes_file = find("routes")

    if not all([topo_file, streams_file, routes_file]):
        print("Error: could not find topology, streams, or routes files in", d)
        sys.exit(1)

    # -- Parse inputs ---------------------------------------------------------
    topology = parse_topology(topo_file)
    streams = parse_streams(streams_file)
    routes = parse_routes(routes_file)
    stream_links = resolve_stream_links(streams, routes, topology)

    # -- Run analysis ---------------------------------------------------------
    results = compute_wcrt(
        streams, stream_links,
        idle_slope=args.idle_slope,
        send_slope=args.send_slope,
    )

    # -- Load reference (if available) ----------------------------------------
    ref_file = find("wcrts")
    ref_wcrts = load_reference_wcrts(ref_file) if ref_file else {}

    # -- Print results --------------------------------------------------------
    print("=" * 72)
    print("CBS Worst-Case Response Time Analysis")
    print(f"  idleSlope = {args.idle_slope}, sendSlope = {args.send_slope}")
    print("=" * 72)
    print(f"{'ID':>4} {'Class':>6} {'Size':>6} {'Period':>8} {'Deadline':>9} "
          f"{'WCRT':>10} {'Ref':>10} {'Match':>6} {'Sched':>6}")
    print("-" * 72)

    all_match = True
    for stream in sorted(streams, key=lambda s: s.id):
        r = results[stream.id]
        wcrt = r["wcrt"]
        ref_val = ref_wcrts.get(stream.id)
        if ref_val is not None:
            match = "✓" if abs(wcrt - ref_val) < 0.01 else "✗"
            if match == "✗":
                all_match = False
            ref_str = f"{ref_val:.2f}"
        else:
            match = "-"
            ref_str = "-"

        sched = "yes" if r["schedulable"] else "NO"
        if stream.pcp == 0:
            wcrt_str = "N/A"
            sched = "-"
        else:
            wcrt_str = f"{wcrt:.2f}"

        print(f"{stream.id:>4} {stream.priority_class:>6} {stream.size:>6} "
              f"{stream.period:>8.0f} {stream.deadline:>9.0f} "
              f"{wcrt_str:>10} {ref_str:>10} {match:>6} {sched:>6}")

        if args.verbose and stream.pcp > 0:
            for pl in r["per_link"]:
                print(f"       └─ {pl['link_id']:>8}: C={pl['C_i']:.2f}  "
                      f"SPI={pl['SPI']:.2f}  HPI={pl['HPI']:.2f}  "
                      f"LPI={pl['LPI']:.2f}  → {pl['WCRT_l']:.2f} µs")

    print("-" * 72)
    if ref_wcrts:
        status = "ALL MATCH ✓" if all_match else "MISMATCH ✗"
        print(f"Validation against reference: {status}")

    # -- Write CSV output -----------------------------------------------------
    out_csv = os.path.join(d, "computed-WCRTs.csv")
    with open(out_csv, "w") as f:
        f.write("ID\tWCRT\n")
        for stream in sorted(streams, key=lambda s: s.id):
            r = results[stream.id]
            if stream.pcp > 0:
                f.write(f"{stream.id}\t{r['wcrt']:.2f}\n")
    print(f"\nResults written to {out_csv}")


if __name__ == "__main__":
    main()
