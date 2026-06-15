#!/usr/bin/env python3
"""
CBS vs. Strict Priority comparison tool.

Runs both CBS and SP analysis + simulation, then highlights how CBS
prevents starvation of lower-priority queues compared to pure SP.

Usage:
    python3 -m src.run_sp_comparison <test_case_dir> [options]
"""

import argparse
import csv
import os
import sys

from src.common.parser import (
    parse_topology, parse_streams, parse_routes, resolve_stream_links,
)
from src.analysis.cbs_analysis import compute_wcrt as cbs_wcrt
from src.analysis.sp_analysis import compute_sp_wcrt as sp_wcrt
from src.simulator.engine import Simulator


def main():
    parser = argparse.ArgumentParser(
        description="Compare CBS vs Strict Priority scheduling")
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

    # -- Analysis: CBS --------------------------------------------------------
    a_cbs = cbs_wcrt(streams, stream_links,
                     idle_slope=args.idle_slope, send_slope=args.send_slope)

    # -- Analysis: SP ---------------------------------------------------------
    a_sp = sp_wcrt(streams, stream_links)

    # -- Simulation: CBS ------------------------------------------------------
    print(f"Running CBS simulation ({args.hyperperiods} hyperperiods)...",
          flush=True)
    sim_cbs = Simulator(
        streams=streams, stream_links=stream_links,
        idle_slope=args.idle_slope, send_slope=args.send_slope,
        num_hyperperiods=args.hyperperiods, use_cbs=True,
    )
    stats_cbs = sim_cbs.run()
    print(f"  CBS sim done (sim time: {sim_cbs.duration:.0f} µs)")

    # -- Simulation: SP -------------------------------------------------------
    print(f"Running SP simulation  ({args.hyperperiods} hyperperiods)...",
          flush=True)
    sim_sp = Simulator(
        streams=streams, stream_links=stream_links,
        idle_slope=args.idle_slope, send_slope=args.send_slope,
        num_hyperperiods=args.hyperperiods, use_cbs=False,
    )
    stats_sp = sim_sp.run()
    print(f"  SP sim done  (sim time: {sim_sp.duration:.0f} µs)\n")

    # -- Comparison table -----------------------------------------------------
    sorted_streams = sorted(streams, key=lambda s: (-s.pcp, s.id))

    hdr = (f"{'ID':>4} {'Cls':>4} "
           f"{'CBS_Ana':>9} {'CBS_Sim':>9} "
           f"{'SP_Ana':>9} {'SP_Sim':>9} "
           f"{'Deadline':>9} {'CBS_OK':>7} {'SP_OK':>7}")
    sep = "=" * len(hdr)

    print(sep)
    print("CBS vs. Strict Priority  —  WCRT Comparison (µs)")
    print(f"  idleSlope={args.idle_slope}, sendSlope={args.send_slope}")
    print(sep)
    print(hdr)
    print("-" * len(hdr))

    cbs_all_sched = True
    sp_all_sched = True
    be_cbs_max = {}
    be_sp_max = {}

    for stream in sorted_streams:
        sid = stream.id
        cls = stream.priority_class

        # CBS results
        cbs_a = a_cbs[sid]["wcrt"]
        cbs_s = stats_cbs.wcrt(sid)
        cbs_n = stats_cbs.count(sid)
        cbs_ok = (cbs_a <= stream.deadline) if stream.pcp > 0 else None

        # SP results
        sp_a = a_sp[sid]["wcrt"]
        sp_s = stats_sp.wcrt(sid)
        sp_n = stats_sp.count(sid)
        sp_ok = (sp_a <= stream.deadline) if stream.pcp > 0 else None

        if stream.pcp > 0:
            if cbs_ok is False:
                cbs_all_sched = False
            if sp_ok is False:
                sp_all_sched = False

        cbs_a_str = f"{cbs_a:.2f}" if stream.pcp > 0 else "N/A"
        sp_a_str = f"{sp_a:.2f}" if stream.pcp > 0 else "N/A"
        cbs_s_str = f"{cbs_s:.2f}" if cbs_n > 0 else "-"
        sp_s_str = f"{sp_s:.2f}" if sp_n > 0 else "-"
        cbs_ok_str = ("yes" if cbs_ok else "NO") if cbs_ok is not None else "-"
        sp_ok_str = ("yes" if sp_ok else "NO") if sp_ok is not None else "-"

        if stream.pcp == 0:
            be_cbs_max[sid] = cbs_s
            be_sp_max[sid] = sp_s

        print(f"{sid:>4} {cls:>4} "
              f"{cbs_a_str:>9} {cbs_s_str:>9} "
              f"{sp_a_str:>9} {sp_s_str:>9} "
              f"{stream.deadline:>9.0f} {cbs_ok_str:>7} {sp_ok_str:>7}")

    print("-" * len(hdr))

    # -- Summary & starvation analysis ----------------------------------------
    print("\n┌─ Key Observations ─────────────────────────────────────────────┐")
    print(f"│  CBS schedulable (all AVB streams): "
          f"{'YES ✓' if cbs_all_sched else 'NO ✗':>10}                    │")
    print(f"│  SP  schedulable (all AVB streams): "
          f"{'YES ✓' if sp_all_sched else 'NO ✗':>10}                    │")

    # Compare BE response times (starvation indicator)
    print("│                                                               │")
    print("│  Best Effort (BE) traffic — starvation indicator:             │")
    for sid in sorted(be_cbs_max.keys()):
        cbs_be = be_cbs_max[sid]
        sp_be = be_sp_max[sid]
        ratio = sp_be / cbs_be if cbs_be > 0 else float('inf')
        print(f"│    Stream {sid}: CBS max={cbs_be:>9.2f}  SP max={sp_be:>9.2f}"
              f"  (SP/CBS = {ratio:.1f}x)   │")

    # Compare Class B response times
    print("│                                                               │")
    print("│  Class B (lower AVB priority) — CBS credit protection:        │")
    for stream in sorted_streams:
        if stream.pcp != 1:
            continue
        sid = stream.id
        cbs_s = stats_cbs.wcrt(sid)
        sp_s = stats_sp.wcrt(sid)
        ratio = sp_s / cbs_s if cbs_s > 0 else float('inf')
        print(f"│    Stream {sid}: CBS max={cbs_s:>9.2f}  SP max={sp_s:>9.2f}"
              f"  (SP/CBS = {ratio:.1f}x)   │")

    print("│                                                               │")
    print("│  CBS shapes high-priority traffic via credit, protecting      │")
    print("│  lower priorities from starvation. SP lets high-priority      │")
    print("│  traffic monopolize the link.                                 │")
    print("└───────────────────────────────────────────────────────────────┘")

    # -- Write CSV ------------------------------------------------------------
    out_csv = os.path.join(d, "sp-vs-cbs-comparison.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["ID", "Class", "CBS_Analytical", "CBS_SimMax",
                     "SP_Analytical", "SP_SimMax", "Deadline",
                     "CBS_Schedulable", "SP_Schedulable"])
        for stream in sorted(streams, key=lambda s: s.id):
            sid = stream.id
            cls = stream.priority_class
            w.writerow([
                sid, cls,
                f"{a_cbs[sid]['wcrt']:.4f}" if stream.pcp > 0 else "N/A",
                f"{stats_cbs.wcrt(sid):.4f}",
                f"{a_sp[sid]['wcrt']:.4f}" if stream.pcp > 0 else "N/A",
                f"{stats_sp.wcrt(sid):.4f}",
                stream.deadline,
                a_cbs[sid]["schedulable"] if stream.pcp > 0 else "N/A",
                a_sp[sid]["schedulable"] if stream.pcp > 0 else "N/A",
            ])
    print(f"\nResults written to {out_csv}")


if __name__ == "__main__":
    main()
