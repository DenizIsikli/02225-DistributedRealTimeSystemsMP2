"""
CBS Worst-Case Response Time Analysis.

Implements the eligible-interval-based WCRT analysis from:
  Cao et al., "Independent yet Tight WCRT Analysis for Individual Priority
  Classes in Ethernet AVB", RTNS'16, Theorem 3 & Appendix Lemma 1.

Also follows the summary on DTU 02225 lecture slide 81:

  WCRT_i = Σ_{∀l ∈ L_i} WCRT_i^l          (compositional, slide 60)

  WCRT_i^l = SPI_i^l + HPI_i^l + LPI_i^l + C_i     (slide 64)

  SPI_i^l = Σ_{m_j ≠ m_i, P_j=P_i, l∈L_j} C_j × (1 + α⁻/α⁺)   (slide 68)

  LPI_i^l = max_{m_j: P_j < P_i, l∈L_j} C_j                      (slide 76)

  HPI_i^l:
    AVB Class A:  0                                                  (slide 76)
    AVB Class B:  LPI × (α⁺_H / α⁻_H) + max_{P_j>P_i} C_j        (slide 80)

Where α⁺ = idleSlope, α⁻ = sendSlope (fractions summing to 1, slide 54).
"""

from collections import defaultdict


def compute_wcrt(
    streams: list,
    stream_links: dict,
    idle_slope: float = 0.5,
    send_slope: float = 0.5,
) -> dict:
    """Compute per-stream end-to-end WCRT.

    Args:
        streams: list of Stream objects
        stream_links: dict stream_id → [Link, …] (output ports on path)
        idle_slope: α⁺ as fraction of BW (default 0.5)
        send_slope: α⁻ as fraction of BW (default 0.5)

    Returns:
        dict of stream_id → {
            'wcrt': float (µs),
            'per_link': [{link_id, spi, hpi, lpi, ci, wcrt_l}, …],
            'schedulable': bool
        }
    """
    # -- Step 1: Build per-link stream sets -----------------------------------
    # For each link_id, collect all streams that traverse that link
    link_streams = defaultdict(list)  # link_id → [(stream, tx_time)]
    for stream in streams:
        for link in stream_links.get(stream.id, []):
            c = link.tx_time(stream.size)         # C_j on link l
            link_streams[link.id].append((stream, c))

    # -- Step 2: Compute per-stream, per-link WCRT ----------------------------
    slope_ratio = send_slope / idle_slope   # α⁻/α⁺  (slides 54, 68)
    slope_ratio_h = idle_slope / send_slope # α⁺_H/α⁻_H for HPI (slide 80)

    results = {}

    for stream in streams:
        if stream.pcp == 0:
            # BE traffic — no WCRT guarantee (project spec)
            results[stream.id] = {
                "wcrt": float("inf"),
                "per_link": [],
                "schedulable": False,
            }
            continue

        per_link_details = []
        total_wcrt = 0.0

        for link in stream_links[stream.id]:
            c_i = link.tx_time(stream.size)

            # Streams sharing this link, grouped by relation to stream_i
            same_prio = []   # same priority, different stream
            higher_prio = [] # higher priority
            lower_prio = []  # lower priority

            for other, c_j in link_streams[link.id]:
                if other.id == stream.id:
                    continue
                if other.pcp == stream.pcp:
                    same_prio.append(c_j)
                elif other.pcp > stream.pcp:
                    higher_prio.append(c_j)
                elif other.pcp < stream.pcp:
                    lower_prio.append(c_j)

            # --- SPI (slide 68, Cao Appendix Lemma 1) ---
            # One frame per same-priority stream (D ≤ T assumption)
            spi = sum(c_j * (1 + slope_ratio) for c_j in same_prio)

            # --- LPI (slide 76) ---
            # Max transmission time of any lower-priority frame
            lpi = max(lower_prio) if lower_prio else 0.0

            # --- HPI (slides 76, 80; Cao Theorem 3) ---
            if stream.pcp == 2:
                # Class A (highest CBS priority) → no higher priority
                hpi = 0.0
            elif stream.pcp == 1:
                # Class B → interference from Class A credit build-up
                # HPI = LPI × (α⁺_H / α⁻_H) + max C_j among higher
                c_max_h = max(higher_prio) if higher_prio else 0.0
                hpi = lpi * slope_ratio_h + c_max_h
            else:
                hpi = 0.0

            wcrt_l = spi + hpi + lpi + c_i
            total_wcrt += wcrt_l

            per_link_details.append({
                "link_id": link.id,
                "C_i": round(c_i, 4),
                "SPI": round(spi, 4),
                "HPI": round(hpi, 4),
                "LPI": round(lpi, 4),
                "WCRT_l": round(wcrt_l, 4),
            })

        results[stream.id] = {
            "wcrt": round(total_wcrt, 4),
            "per_link": per_link_details,
            "schedulable": total_wcrt <= stream.deadline,
        }

    return results
