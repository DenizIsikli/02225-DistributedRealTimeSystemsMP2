#!/usr/bin/env python3
"""
Entry point for TSN CBS network simulator (R2).

Usage:
    python3 -m src.run_simulator <test_case_dir> [options]

Example:
    python3 -m src.run_simulator mini-project-2/test-case-1 --hyperperiods 500
"""

import argparse
import os
import sys
import time as wall_time

from src.common.parser import (
    parse_topology, parse_streams, parse_routes, resolve_stream_links,
)
from src.simulator.engine import Simulator


def main():
    parser = argparse.ArgumentParser(description="TSN CBS Network Simulator")
    parser.add_argument("test_dir", help="Path to test case directory")
    parser.add_argument("--idle-slope", type=float, default=0.5)
    parser.add_argument("--send-slope", type=float, default=0.5)
    parser.add_argument("--hyperperiods", type=int, default=200,
                        help="Number of hyperperiods to simulate (default: 200)")
    parser.add_argument("--duration", type=float, default=0,
                        help="Explicit duration in µs (overrides hyperperiods)")
    args = parser.parse_args()

    d = args.test_dir

    def find(pattern):
        for f in os.listdir(d):
            if pattern in f.lower():
                return os.path.join(d, f)
        return None

    topo_file = find("topology")
    streams_file = find("streams")
    routes_file = find("routes")

    if not all([topo_file, streams_file, routes_file]):
        print("Error: missing input files in", d)
        sys.exit(1)

    # -- Parse ----------------------------------------------------------------
    topology = parse_topology(topo_file)
    streams = parse_streams(streams_file)
    routes = parse_routes(routes_file)
    stream_links = resolve_stream_links(streams, routes, topology)

    # -- Simulate -------------------------------------------------------------
    print("=" * 68)
    print("TSN CBS Network Simulator")
    print(f"  idleSlope={args.idle_slope}, sendSlope={args.send_slope}")
    print(f"  hyperperiods={args.hyperperiods}")
    print("=" * 68)

    t0 = wall_time.time()
    sim = Simulator(
        streams=streams,
        stream_links=stream_links,
        idle_slope=args.idle_slope,
        send_slope=args.send_slope,
        duration=args.duration,
        num_hyperperiods=args.hyperperiods,
    )
    stats = sim.run()
    elapsed = wall_time.time() - t0

    print(f"Simulation completed in {elapsed:.2f}s  "
          f"(sim time: {sim.duration:.0f} µs = {sim.duration/1e6:.3f} s)")
    print()

    # -- Results --------------------------------------------------------------
    print(f"{'ID':>4} {'Class':>6} {'Size':>6} {'Period':>8} "
          f"{'Frames':>7} {'MinRT':>10} {'AvgRT':>10} {'MaxRT':>10} {'Deadline':>9}")
    print("-" * 82)

    for stream in sorted(streams, key=lambda s: s.id):
        sid = stream.id
        n = stats.count(sid)
        cls = stream.priority_class
        if n == 0:
            print(f"{sid:>4} {cls:>6} {stream.size:>6} {stream.period:>8.0f} "
                  f"{'0':>7} {'-':>10} {'-':>10} {'-':>10} {stream.deadline:>9.0f}")
            continue
        min_rt = stats.min_rt(sid)
        avg_rt = stats.average_rt(sid)
        max_rt = stats.wcrt(sid)
        print(f"{sid:>4} {cls:>6} {stream.size:>6} {stream.period:>8.0f} "
              f"{n:>7} {min_rt:>10.2f} {avg_rt:>10.2f} {max_rt:>10.2f} "
              f"{stream.deadline:>9.0f}")

    # -- Write CSV ------------------------------------------------------------
    out_csv = os.path.join(d, "simulated-results.csv")
    with open(out_csv, "w") as f:
        f.write("ID\tClass\tFrames\tMinRT\tAvgRT\tMaxRT\tDeadline\n")
        for stream in sorted(streams, key=lambda s: s.id):
            sid = stream.id
            n = stats.count(sid)
            if n > 0:
                f.write(f"{sid}\t{stream.priority_class}\t{n}\t"
                        f"{stats.min_rt(sid):.4f}\t{stats.average_rt(sid):.4f}\t"
                        f"{stats.wcrt(sid):.4f}\t{stream.deadline}\n")
    print(f"\nResults written to {out_csv}")


if __name__ == "__main__":
    main()
