"""
JSON parsers for TSN configuration files.

Parses topology.json, streams.json, and routes.json as specified in
file_format_specs.v2.md.
"""

import json
from .models import Stream, Link, Route, Topology


def parse_topology(filepath: str) -> Topology:
    """Parse topology.json → Topology with Links indexed by (source, port)."""
    with open(filepath) as f:
        data = json.load(f)

    topo = data["topology"]
    default_bw = topo.get("default_bandwidth_mbps", 1000)

    links = {}
    for ld in topo["links"]:
        bw = ld.get("bandwidth_mbps", default_bw)
        delay = ld.get("delay", 0.0)
        link = Link(
            id=ld["id"],
            source=ld["source"],
            source_port=ld["sourcePort"],
            destination=ld["destination"],
            destination_port=ld["destinationPort"],
            bandwidth_mbps=bw,
            delay_us=delay,
        )
        links[link.id] = link

    topology = Topology(
        switches=topo.get("switches", []),
        end_systems=topo.get("end_systems", []),
        links=links,
        default_bandwidth_mbps=default_bw,
    )
    topology.build_index()
    return topology


def parse_streams(filepath: str) -> list:
    """Parse streams.json → list of Stream objects."""
    with open(filepath) as f:
        data = json.load(f)

    streams = []
    for sd in data["streams"]:
        dest = sd["destinations"][0]  # first (and typically only) destination
        stream = Stream(
            id=sd["id"],
            name=sd["name"],
            source=sd["source"],
            destination=dest["id"],
            pcp=sd["PCP"],
            size=sd["size"],
            period=sd["period"],
            deadline=dest["deadline"],
        )
        streams.append(stream)
    return streams


def parse_routes(filepath: str) -> dict:
    """Parse routes.json → dict of flow_id → Route."""
    with open(filepath) as f:
        data = json.load(f)

    routes = {}
    for rd in data["routes"]:
        fid = rd["flow_id"]
        path = rd["paths"][0]  # first (primary) path
        hops = [(hop["node"], hop["port"]) for hop in path]
        routes[fid] = Route(flow_id=fid, hops=hops)
    return routes


def resolve_stream_links(
    streams: list, routes: dict, topology: Topology
) -> dict:
    """For each stream, resolve its route to an ordered list of Link objects.

    Returns: dict of stream_id → [Link, Link, …]
    """
    stream_links = {}
    for stream in streams:
        route = routes[stream.id]
        links = []
        for source_node, source_port in route.link_sources:
            link = topology.get_link_by_source_port(source_node, source_port)
            if link is None:
                raise ValueError(
                    f"No link found for ({source_node}, port {source_port}) "
                    f"in stream {stream.id}"
                )
            links.append(link)
        stream_links[stream.id] = links
    return stream_links
