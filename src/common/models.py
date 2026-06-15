"""
Data models for TSN CBS analysis and simulation.

Notation follows Cao et al. RTNS'16 (Independent yet Tight WCRT Analysis
for Individual Priority Classes in Ethernet AVB) and DTU 02225 lecture slides.

Stream model (slide 58):
  Γ = {m_i (C_i, T_i, D_i, P_i, L_i) | i = 1…N}
  C_i = transmission time (frame.size / BW)
  T_i = period
  D_i = deadline
  P_i = priority (PCP)
  L_i = path (ordered set of links)
"""

from dataclasses import dataclass, field


@dataclass
class Stream:
    """A periodic real-time stream (traffic flow)."""
    id: int
    name: str
    source: str
    destination: str
    pcp: int            # Priority Code Point: 2=AVB_A, 1=AVB_B, 0=BE
    size: int           # Frame size in bytes
    period: float       # Period in µs
    deadline: float     # Relative deadline in µs

    @property
    def priority_class(self) -> str:
        """Map PCP to class name per slide 53."""
        return {2: "A", 1: "B", 0: "BE"}.get(self.pcp, "BE")


@dataclass
class Link:
    """A unidirectional link (models one output port), per slide 48-51."""
    id: str
    source: str
    source_port: int
    destination: str
    destination_port: int
    bandwidth_mbps: float
    delay_us: float = 0.0   # Propagation delay in µs

    def tx_time(self, size_bytes: int) -> float:
        """Transmission time C = (size × 8) / BW, in µs (slide 58)."""
        return (size_bytes * 8) / self.bandwidth_mbps


@dataclass
class Route:
    """Pre-computed route for a stream: ordered list of (node, port) hops."""
    flow_id: int
    hops: list          # [(node_id, port), …]

    @property
    def link_sources(self) -> list:
        """Return (source_node, source_port) for each output port traversed.

        The last hop is the destination ES (no output port from there).
        """
        return [(node, port) for node, port in self.hops[:-1]]


@dataclass
class Topology:
    """Network topology: nodes and directed links."""
    switches: list
    end_systems: list
    links: dict                     # link_id -> Link
    default_bandwidth_mbps: float

    # Lookup: (source_node, source_port) -> Link
    _source_port_map: dict = field(default_factory=dict, repr=False)

    def build_index(self):
        """Build lookup from (source, port) -> Link."""
        self._source_port_map = {
            (link.source, link.source_port): link
            for link in self.links.values()
        }

    def get_link_by_source_port(self, source: str, port: int) -> Link:
        """Find the link originating from (source, port)."""
        return self._source_port_map.get((source, port))
