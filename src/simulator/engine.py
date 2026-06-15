"""
Discrete-Event Simulation engine for TSN with CBS.

Architecture follows the standard DES pattern (DTU 02225 simulation slides,
slides 14-17): event list, timing routine, event routines, statistical
counters, report generator.

Events:
  GENERATE    — create a new frame for a stream at its period boundary
  ARRIVE      — frame arrives at an output port queue
  TX_COMPLETE — frame finishes transmission at a port
  ELIGIBLE    — CBS credit recovers to 0, re-trigger arbitration
"""

import heapq
from collections import defaultdict
from enum import IntEnum, auto

from src.simulator.cbs_port import CBSOutputPort, Frame


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

class EventType(IntEnum):
    """Event types, ordered by processing priority at same timestamp."""
    TX_COMPLETE = 0     # process completions first
    ARRIVE = 1          # then arrivals
    ELIGIBLE = 2        # then credit recovery
    GENERATE = 3        # then new frame generation


class Event:
    """Simulation event, ordered by (time, type, counter).

    Uses a tuple key for heapq comparison; data dict is excluded.
    """
    __slots__ = ('time', 'etype', 'seq', 'data', '_key')

    def __init__(self, time: float, etype: EventType, seq: int,
                 data: dict = None):
        self.time = time
        self.etype = etype
        self.seq = seq
        self.data = data
        self._key = (time, int(etype), seq)

    def __lt__(self, other):
        return self._key < other._key

    def __le__(self, other):
        return self._key <= other._key

    def __eq__(self, other):
        return self._key == other._key


# ---------------------------------------------------------------------------
# Statistics collector
# ---------------------------------------------------------------------------

class Statistics:
    """Tracks per-stream response times (slide 13: statistical counters)."""

    def __init__(self):
        self.response_times = defaultdict(list)

    def record(self, stream_id: int, response_time: float):
        self.response_times[stream_id].append(response_time)

    def wcrt(self, stream_id: int) -> float:
        rts = self.response_times[stream_id]
        return max(rts) if rts else 0.0

    def average_rt(self, stream_id: int) -> float:
        rts = self.response_times[stream_id]
        return sum(rts) / len(rts) if rts else 0.0

    def min_rt(self, stream_id: int) -> float:
        rts = self.response_times[stream_id]
        return min(rts) if rts else 0.0

    def count(self, stream_id: int) -> int:
        return len(self.response_times[stream_id])


# ---------------------------------------------------------------------------
# Simulator engine
# ---------------------------------------------------------------------------

class Simulator:
    """Discrete-event simulator for TSN network with CBS.

    Args:
        streams: list of Stream model objects
        stream_links: dict stream_id → [Link, …]
        idle_slope: CBS idleSlope fraction
        send_slope: CBS sendSlope fraction
        duration: simulation duration in µs (0 = auto from hyperperiod)
        num_hyperperiods: number of hyperperiods to simulate
    """

    def __init__(self, streams, stream_links,
                 idle_slope=0.5, send_slope=0.5,
                 duration=0, num_hyperperiods=100,
                 use_cbs=True):
        self.streams = {s.id: s for s in streams}
        self.stream_links = stream_links
        self.idle_slope = idle_slope
        self.send_slope = send_slope
        self.use_cbs = use_cbs

        # Compute simulation duration
        if duration > 0:
            self.duration = duration
        else:
            self.duration = self._compute_hyperperiod() * num_hyperperiods

        # Create output ports (one per directed link)
        self.ports = {}  # link_id → CBSOutputPort
        all_links = set()
        for links in stream_links.values():
            for link in links:
                all_links.add((link.id, link.bandwidth_mbps))
        for link_id, bw in all_links:
            self.ports[link_id] = CBSOutputPort(
                link_id=link_id,
                bandwidth_mbps=bw,
                idle_slope_frac=idle_slope,
                send_slope_frac=send_slope,
                use_cbs=use_cbs,
            )

        # Event queue and counters
        self.events = []
        self.event_seq = 0
        self.stats = Statistics()
        self.current_time = 0.0

        # Track pending eligible events to avoid duplicates
        self._pending_eligible = {}  # (link_id, pcp) → scheduled_time

    def _compute_hyperperiod(self) -> float:
        """LCM of all stream periods."""
        from math import gcd
        periods = [int(s.period) for s in self.streams.values()]
        lcm = periods[0]
        for p in periods[1:]:
            lcm = lcm * p // gcd(lcm, p)
        return float(lcm)

    def _schedule(self, time: float, etype: EventType, data: dict = None):
        ev = Event(time=time, etype=etype, seq=self.event_seq, data=data)
        self.event_seq += 1
        heapq.heappush(self.events, ev)

    # -- Initialization (slide 15: initialization routine) --------------------

    def initialize(self):
        """Schedule initial GENERATE events for all streams at t=0."""
        for stream in self.streams.values():
            self._schedule(0.0, EventType.GENERATE,
                           {"stream_id": stream.id, "instance": 0})

    # -- Main loop (slide 17: main program + timing routine) ------------------

    def run(self) -> Statistics:
        """Execute the simulation. Returns Statistics object."""
        self.initialize()

        while self.events:
            event = heapq.heappop(self.events)
            if event.time > self.duration:
                break

            self.current_time = event.time
            data = event.data

            if event.etype == EventType.GENERATE:
                self._handle_generate(data)
            elif event.etype == EventType.ARRIVE:
                self._handle_arrive(data)
            elif event.etype == EventType.TX_COMPLETE:
                self._handle_tx_complete(data)
            elif event.etype == EventType.ELIGIBLE:
                self._handle_eligible(data)

        return self.stats

    # -- Event routines (slide 15: event routine i) ---------------------------

    def _handle_generate(self, data: dict):
        """GENERATE: create a frame and send it to first output port."""
        sid = data["stream_id"]
        instance = data["instance"]
        stream = self.streams[sid]

        links = self.stream_links[sid]
        frame = Frame(
            stream_id=sid,
            pcp=stream.pcp,
            size=stream.size,
            generation_time=self.current_time,
            instance=instance,
            current_hop=0,
            total_hops=len(links),
        )

        # Send to first output port immediately
        first_link = links[0]
        self._schedule(self.current_time, EventType.ARRIVE,
                       {"frame": frame, "link_id": first_link.id})

        # Schedule next frame generation (within simulation duration)
        next_gen_time = self.current_time + stream.period
        if next_gen_time <= self.duration:
            self._schedule(next_gen_time, EventType.GENERATE,
                           {"stream_id": sid, "instance": instance + 1})

    def _handle_arrive(self, data: dict):
        """ARRIVE: enqueue frame at port, attempt arbitration."""
        frame = data["frame"]
        link_id = data["link_id"]
        port = self.ports[link_id]

        port.update_credits(self.current_time)
        port.enqueue(frame)
        self._try_arbitrate(port)

    def _handle_tx_complete(self, data: dict):
        """TX_COMPLETE: finish current transmission, forward frame, arbitrate."""
        link_id = data["link_id"]
        port = self.ports[link_id]

        port.update_credits(self.current_time)
        frame = port.complete_tx(self.current_time)

        # Advance frame to next hop
        frame.current_hop += 1

        if frame.current_hop < frame.total_hops:
            # Send to next output port
            links = self.stream_links[frame.stream_id]
            next_link = links[frame.current_hop]
            self._schedule(self.current_time, EventType.ARRIVE,
                           {"frame": frame, "link_id": next_link.id})
        else:
            # Frame reached destination — record response time
            rt = self.current_time - frame.generation_time
            self.stats.record(frame.stream_id, rt)

        # Arbitrate for next transmission at this port
        self._try_arbitrate(port)

    def _handle_eligible(self, data: dict):
        """ELIGIBLE: CBS credit recovered to 0, re-attempt arbitration."""
        link_id = data["link_id"]
        pcp = data["pcp"]
        port = self.ports[link_id]

        # Clear pending tracker
        self._pending_eligible.pop((link_id, pcp), None)

        port.update_credits(self.current_time)
        self._try_arbitrate(port)

    # -- Arbitration helper ---------------------------------------------------

    def _try_arbitrate(self, port: CBSOutputPort):
        """Attempt to start a transmission at the given port."""
        if port.busy:
            return

        port.update_credits(self.current_time)
        frame, tx_time = port.arbitrate(self.current_time)

        if frame is not None:
            # Schedule TX_COMPLETE
            self._schedule(self.current_time + tx_time, EventType.TX_COMPLETE,
                           {"link_id": port.link_id})
        else:
            # No frame could start — check if CBS needs credit recovery
            eligible_time = port.get_earliest_eligible_time(self.current_time)
            if eligible_time is not None and eligible_time > self.current_time:
                # Only schedule if no earlier event already pending.
                # Strictly future events only — never re-fire at the same
                # timestamp (that would be an infinite loop; if a class is
                # eligible *now* but arbitrate() couldn't pick it, the next
                # state-changing event will retrigger arbitration).
                for pcp in (2, 1):
                    if port.queues[pcp] and port.credit[pcp] < -1e-9:
                        key = (port.link_id, pcp)
                        if key not in self._pending_eligible or \
                                self._pending_eligible[key] > eligible_time:
                            self._pending_eligible[key] = eligible_time
                            self._schedule(eligible_time, EventType.ELIGIBLE,
                                           {"link_id": port.link_id, "pcp": pcp})
