"""
Strict Priority (SP) Worst-Case Response Time Analysis.

Standard non-preemptive fixed-priority analysis applied per output port,
then summed across the stream's path (compositional).

For a stream m_i with priority P_i on link l:

  WCRT_i^l = C_i + B_i + SPI_i^l + HPI_i^l

Where (non-preemptive, constrained deadlines D ≤ T):
  B_i   = max_{j: P_j < P_i, l ∈ L_j} C_j   (one lower-priority frame blocking)
  SPI   = Σ_{j≠i: P_j = P_i, l ∈ L_j} C_j   (one frame per same-prio stream)
  HPI   = Σ_{j: P_j > P_i, l ∈ L_j} ⌈R/T_j⌉ × C_j  (higher-prio arrivals during R)

Solved via fixed-point iteration on R until convergence.

Unlike CBS, there is NO credit-based shaping — higher-priority traffic is
unlimited, which can starve lower priorities.
"""

from collections import defaultdict
from math import ceil


def compute_sp_wcrt(
    streams: list,
    stream_links: dict,
    max_iterations: int = 1000,
) -> dict:
    """Compute per-stream end-to-end WCRT under Strict Priority (no CBS).

    Args:
        streams: list of Stream objects
        stream_links: dict stream_id → [Link, …]
        max_iterations: iteration limit for fixed-point convergence

    Returns:
        dict of stream_id → {
            'wcrt': float (µs),
            'per_link': [{link_id, ci, spi, hpi, lpi, wcrt_l}, …],
            'schedulable': bool
        }
    """
    # Build per-link stream info: link_id → [(stream, C_j on this link)]
    link_streams = defaultdict(list)
    for stream in streams:
        for link in stream_links.get(stream.id, []):
            c = link.tx_time(stream.size)
            link_streams[link.id].append((stream, c))

    results = {}

    for stream in streams:
        per_link_details = []
        total_wcrt = 0.0
        schedulable = True

        for link in stream_links[stream.id]:
            c_i = link.tx_time(stream.size)

            same_prio = []    # (C_j,) for same priority, different stream
            higher_prio = []  # (C_j, T_j) for higher priority
            lower_prio = []   # (C_j,) for lower priority

            for other, c_j in link_streams[link.id]:
                if other.id == stream.id:
                    continue
                if other.pcp == stream.pcp:
                    same_prio.append(c_j)
                elif other.pcp > stream.pcp:
                    higher_prio.append((c_j, other.period))
                elif other.pcp < stream.pcp:
                    lower_prio.append(c_j)

            # B_i: non-preemptive blocking from max lower-priority frame
            b_i = max(lower_prio) if lower_prio else 0.0

            # SPI: one frame from each same-priority stream (D ≤ T)
            spi = sum(same_prio)

            # Fixed-point iteration for HPI
            r_prev = c_i
            converged = False
            for _ in range(max_iterations):
                hpi = sum(ceil(r_prev / t_j) * c_j
                          for c_j, t_j in higher_prio)
                r_new = c_i + b_i + spi + hpi
                if r_new == r_prev:
                    converged = True
                    break
                if r_new > stream.deadline:
                    converged = True
                    schedulable = False
                    break
                r_prev = r_new

            wcrt_l = r_new if converged else r_prev

            per_link_details.append({
                "link_id": link.id,
                "C_i": round(c_i, 4),
                "SPI": round(spi, 4),
                "HPI": round(hpi, 4),
                "LPI": round(b_i, 4),
                "WCRT_l": round(wcrt_l, 4),
            })
            total_wcrt += wcrt_l

        if total_wcrt > stream.deadline:
            schedulable = False

        results[stream.id] = {
            "wcrt": round(total_wcrt, 4),
            "per_link": per_link_details,
            "schedulable": schedulable,
        }

    return results
