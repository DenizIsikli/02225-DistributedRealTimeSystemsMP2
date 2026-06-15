#!/usr/bin/env python3
"""
Comparison tool: Analytical WCRT (R1) vs. Simulated response times (R2).

Runs both the CBS WCRT analysis and the DES simulation, then produces a
side-by-side comparison table and summary statistics.

Reference: Cao et al. RTNS'16 — the analytical WCRT is a proven upper bound
on the observed response time.  The gap represents analysis pessimism.

Usage:
    python3 -m src.run_comparison <test_case_dir> [options]
"""

import argparse
import os
import sys

from src.common.parser import (
    parse_topology, parse_streams, parse_routes, resolve_stream_links,
)
from src.analysis.cbs_analysis import compute_wcrt
from src.simulator.engine import Simulator


def main():
    parser = argparse.ArgumentParser(
        description="Compare CBS analytical WCRT with simulation")
    parser.add_argument("test_dir", help="Path to test case directory")
    parser.add_argument("--idle-slope", type=float, default=0.5)
    parser.add_argument("--send-slope", type=float, default=0.5)
    parser.add_argument("--hyperperiods", type=int, default=500,
                        help="Simulation hyperperiods (default: 500)")
    args = parser.parse_args()

    d = args.test_dir

    def find(pattern):
        for f in os.listdir(d):
            if pattern in f.lower():
                return os.path.join(d, f)
        return None

    # -- Parse inputs ---------------------------------------------------------
    topology = parse_topology(find("topology"))
    streams = parse_streams(find("streams"))
    routes = parse_routes(find("routes"))
    stream_links = resolve_stream_links(streams, routes, topology)

    # -- R1: Analytical -------------------------------------------------------
    analytical = compute_wcrt(
        streams, stream_links,
        idle_slope=args.idle_slope, send_slope=args.send_slope,
    )

    # -- R2: Simulation -------------------------------------------------------
    print(f"Running simulation ({args.hyperperiods} hyperperiods)...", flush=True)
    sim = Simulator(
        streams=streams,
        stream_links=stream_links,
        idle_slope=args.idle_slope,
        send_slope=args.send_slope,
        num_hyperperiods=args.hyperperiods,
    )
    stats = sim.run()
    print(f"Done (sim time: {sim.duration:.0f} µs)\n")

    # -- Comparison table -----------------------------------------------------
    avb_streams = [s for s in sorted(streams, key=lambda s: s.id) if s.pcp > 0]

    hdr = (f"{'ID':>4} {'Class':>6} {'Analytical':>11} {'Sim Max':>10} "
           f"{'Sim Avg':>10} {'Sim Min':>10} {'Gap%':>7} {'Bound':>6} "
           f"{'Deadline':>9} {'Sched':>6}")
    sep = "=" * len(hdr)

    print(sep)
    print("CBS Analysis vs. Simulation  —  Response Time Comparison (µs)")
    print(f"  idleSlope={args.idle_slope}, sendSlope={args.send_slope}")
    print(sep)
    print(hdr)
    print("-" * len(hdr))

    all_bounded = True
    for stream in avb_streams:
        sid = stream.id
        a_wcrt = analytical[sid]["wcrt"]
        s_max = stats.wcrt(sid)
        s_avg = stats.average_rt(sid)
        s_min = stats.min_rt(sid)
        n = stats.count(sid)

        if n == 0:
            continue

        bounded = s_max <= a_wcrt + 0.01  # tolerance for fp
        if not bounded:
            all_bounded = False

        gap_pct = ((a_wcrt - s_max) / a_wcrt * 100) if a_wcrt > 0 else 0
        sched_a = "yes" if analytical[sid]["schedulable"] else "NO"
        bound_str = "✓" if bounded else "✗"

        print(f"{sid:>4} {stream.priority_class:>6} {a_wcrt:>11.2f} "
              f"{s_max:>10.2f} {s_avg:>10.2f} {s_min:>10.2f} "
              f"{gap_pct:>6.1f}% {bound_str:>6} "
              f"{stream.deadline:>9.0f} {sched_a:>6}")

    print("-" * len(hdr))

    # -- Summary --------------------------------------------------------------
    print("\nKey observations:")
    print(f"  • Simulated WCRT ≤ Analytical WCRT for all streams: "
          f"{'YES ✓' if all_bounded else 'NO ✗'}")
    print(f"    (Analytical bound is proven tight by Cao et al. RTNS'16, Thm 3)")
    if all_bounded:
        gaps = []
        for s in avb_streams:
            a = analytical[s.id]["wcrt"]
            m = stats.wcrt(s.id)
            if a > 0 and stats.count(s.id) > 0:
                gaps.append((a - m) / a * 100)
        if gaps:
            print(f"  • Average pessimism gap: {sum(gaps)/len(gaps):.1f}%")
            print(f"  • The gap arises because the worst-case interference")
            print(f"    pattern (Cao Fig. 4: max-size L frame + H burst just")
            print(f"    before credit recovery) does not occur with purely")
            print(f"    periodic synchronous traffic.")

    # -- Write CSV ------------------------------------------------------------
    out_csv = os.path.join(d, "comparison-results.csv")
    with open(out_csv, "w") as f:
        f.write("ID\tClass\tAnalytical_WCRT\tSim_MaxRT\tSim_AvgRT\t"
                "Sim_MinRT\tGap_Pct\tDeadline\tSchedulable\n")
        for stream in avb_streams:
            sid = stream.id
            a = analytical[sid]["wcrt"]
            n = stats.count(sid)
            if n > 0:
                gap = (a - stats.wcrt(sid)) / a * 100 if a > 0 else 0
                f.write(f"{sid}\t{stream.priority_class}\t{a:.4f}\t"
                        f"{stats.wcrt(sid):.4f}\t{stats.average_rt(sid):.4f}\t"
                        f"{stats.min_rt(sid):.4f}\t{gap:.2f}\t"
                        f"{stream.deadline}\t"
                        f"{analytical[sid]['schedulable']}\n")
    print(f"\nResults written to {out_csv}")


if __name__ == "__main__":
    main()
