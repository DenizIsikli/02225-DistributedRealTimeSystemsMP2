WCRTs.csv contains the worst-case response times (WCRTs) of the AVB streams for the test case, computed assuming identical parameters for both Class A and Class B, with idleSlope and sendingSlope set to 0.5 for simplicity.

All links in topology.json use a uniform bandwidth of 100 Mbps, set via the topology-level "default_bandwidth_mbps" field. No per-link "bandwidth_mbps" overrides are used; the WCRT values were computed under this 100 Mbps assumption.

WCRTs.csv is tab-separated and uses "." (dot) as the decimal separator. Time values are in microseconds (consistent with the "delay_units" of the other input files).
