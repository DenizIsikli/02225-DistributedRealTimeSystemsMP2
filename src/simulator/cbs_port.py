"""
CBS Output Port model for the discrete-event simulator.

Models the Credit-Based Shaper (CBS) per IEEE 802.1Qav at a single output
port, following the credit rules from:
  - "TSN for Dummies" / Johas Teener et al. (IEEE Proc. 2013), Section IV-B
  - Cao et al. RTNS'16, Section 2 (system model)
  - DTU 02225 lecture slides 53-56

Credit rules (IEEE 802.1Qav, simplified):
  1. Positive credit → reset to 0 when queue has no pending frames.
  2. During TX of own class → credit decreases at sendSlope rate.
  3. Credit < 0 and no own TX → credit increases at idleSlope rate (cap at 0).
  4. Pending frames blocked by other class → credit increases at idleSlope
     (can exceed 0, enabling burst catch-up).
"""

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Frame:
    """A frame instance traversing the network."""
    stream_id: int
    pcp: int
    size: int           # bytes
    generation_time: float
    instance: int
    current_hop: int = 0
    total_hops: int = 0


CBS_CLASSES = (2, 1)  # PCP values with CBS (Class A, Class B)

# Tolerance for floating-point comparisons on the credit counter.
# Without this, accumulated rounding can leave credit at e.g. -1e-15 just
# after recovery, which would cause arbitrate() to reject an otherwise
# eligible frame and the engine to reschedule ELIGIBLE forever at the
# same timestamp (infinite event loop).
_CREDIT_EPS = 1e-9


class CBSOutputPort:
    """Single output port with 3-queue CBS + SP scheduling.

    Queues: PCP 2 (AVB A), PCP 1 (AVB B), PCP 0 (BE).
    CBS applied to queues 2 and 1; BE is strict-priority lowest.
    """

    def __init__(self, link_id: str, bandwidth_mbps: float,
                 idle_slope_frac: float = 0.5, send_slope_frac: float = 0.5,
                 use_cbs: bool = True):
        self.link_id = link_id
        self.bandwidth_mbps = bandwidth_mbps
        self.use_cbs = use_cbs

        # Slope rates in bits/µs  (bandwidth_mbps = bits/µs)
        self.idle_slope = idle_slope_frac * bandwidth_mbps   # α⁺
        self.send_slope = send_slope_frac * bandwidth_mbps   # α⁻

        # Per-class FIFO queues
        self.queues = {2: deque(), 1: deque(), 0: deque()}

        # Per-CBS-class credit (in bits)
        self.credit = {2: 0.0, 1: 0.0}
        self.credit_last_update = {2: 0.0, 1: 0.0}

        # Port transmission state
        self.busy = False
        self.current_frame = None
        self.current_tx_pcp = None
        self.tx_end_time = 0.0

    def tx_time(self, size_bytes: int) -> float:
        """Frame transmission time in µs."""
        return (size_bytes * 8) / self.bandwidth_mbps

    def enqueue(self, frame: Frame):
        """Add a frame to the appropriate priority queue."""
        self.queues[frame.pcp].append(frame)

    def update_credits(self, current_time: float):
        """Lazily update CBS credit for both classes based on port state.

        Called before any decision is made at the port.
        """
        for pcp in CBS_CLASSES:
            elapsed = current_time - self.credit_last_update[pcp]
            if elapsed <= 0:
                self.credit_last_update[pcp] = current_time
                continue

            has_pending = len(self.queues[pcp]) > 0

            if self.busy and self.current_tx_pcp == pcp:
                # Rule 2: own class transmitting → credit decreases
                self.credit[pcp] -= self.send_slope * elapsed

            elif self.busy and self.current_tx_pcp != pcp:
                # Rule 4: another class is transmitting
                if has_pending:
                    # Blocked by other traffic → credit increases (no cap)
                    self.credit[pcp] += self.idle_slope * elapsed
                else:
                    # No pending → positive credit resets to 0
                    if self.credit[pcp] > 0:
                        self.credit[pcp] = 0.0
                    elif self.credit[pcp] < 0:
                        self.credit[pcp] += self.idle_slope * elapsed
                        self.credit[pcp] = min(self.credit[pcp], 0.0)

            else:
                # Port is idle
                if has_pending:
                    if self.credit[pcp] < 0:
                        # Rule 3: recovering toward 0
                        self.credit[pcp] += self.idle_slope * elapsed
                        self.credit[pcp] = min(self.credit[pcp], 0.0)
                    else:
                        # Rule 1: positive credit, idle → should have been
                        # reset; this handles edge cases
                        pass
                else:
                    # Rule 1: no pending frames
                    if self.credit[pcp] > 0:
                        self.credit[pcp] = 0.0
                    elif self.credit[pcp] < 0:
                        self.credit[pcp] += self.idle_slope * elapsed
                        self.credit[pcp] = min(self.credit[pcp], 0.0)

            self.credit_last_update[pcp] = current_time

    def arbitrate(self, current_time: float):
        """Select the next frame to transmit (non-preemptive strict priority + CBS).

        Returns: (frame, tx_time) if a frame can start, else None.
        Also returns earliest_eligible_time if a CBS class is waiting.
        """
        if self.busy:
            return None, None

        # Priority order: 2 (A) > 1 (B) > 0 (BE)
        for pcp in (2, 1, 0):
            if not self.queues[pcp]:
                continue

            if pcp in CBS_CLASSES and self.use_cbs:
                if self.credit[pcp] >= -_CREDIT_EPS:
                    # Snap to exactly zero on the boundary so subsequent
                    # send-slope decrement starts from a clean state.
                    if self.credit[pcp] < 0:
                        self.credit[pcp] = 0.0
                    # Eligible: start transmission
                    frame = self.queues[pcp].popleft()
                    tt = self.tx_time(frame.size)
                    self._start_tx(frame, pcp, current_time, tt)
                    return frame, tt
                # Has frames but credit < 0 → wait for recovery
            else:
                # SP mode or BE: no credit check
                frame = self.queues[pcp].popleft()
                tt = self.tx_time(frame.size)
                self._start_tx(frame, pcp, current_time, tt)
                return frame, tt

        return None, None

    def get_earliest_eligible_time(self, current_time: float):
        """If CBS classes have pending frames with negative credit,
        return earliest time any becomes eligible."""
        if not self.use_cbs:
            return None
        earliest = None
        for pcp in CBS_CLASSES:
            if self.queues[pcp] and self.credit[pcp] < -_CREDIT_EPS:
                time_to_zero = -self.credit[pcp] / self.idle_slope
                eligible_time = current_time + time_to_zero
                if earliest is None or eligible_time < earliest:
                    earliest = eligible_time
        return earliest

    def _start_tx(self, frame: Frame, pcp: int, start_time: float,
                  tx_time: float):
        """Mark the port as busy transmitting a frame."""
        self.busy = True
        self.current_frame = frame
        self.current_tx_pcp = pcp
        self.tx_end_time = start_time + tx_time

    def complete_tx(self, current_time: float) -> Frame:
        """Complete the current transmission. Returns the transmitted frame."""
        frame = self.current_frame
        self.busy = False
        self.current_frame = None
        self.current_tx_pcp = None
        self.tx_end_time = 0.0

        # Rule 1: reset positive credit for classes with empty queues
        for pcp in CBS_CLASSES:
            if not self.queues[pcp] and self.credit[pcp] > 0:
                self.credit[pcp] = 0.0

        return frame
