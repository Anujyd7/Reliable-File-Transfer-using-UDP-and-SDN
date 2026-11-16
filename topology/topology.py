#!/usr/bin/env python3

"""
Reliable File Transfer using UDP and SDN
Mininet Network Topology

Hosts:
    h1 = 10.0.0.1
    h2 = 10.0.0.2

Switches:
    s1, s2, s3, s4

Primary path:
    h1 -> s1 -> s2 -> s4 -> h2

Alternate path:
    h1 -> s1 -> s3 -> s4 -> h2

Default mode:
    Standalone switching for Phase 4 connectivity testing.

Remote mode:
    Connects to the SDN controller for later phases.
"""

import argparse
import sys

from mininet.net import Mininet
from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI


CONTROLLER_IP = "127.0.0.1"
CONTROLLER_PORT = 6653

HOST1_IP = "10.0.0.1/24"
HOST2_IP = "10.0.0.2/24"


class ReliableTransferTopo(Topo):

    def build(self):

        # Create hosts
        h1 = self.addHost(
            "h1",
            ip=HOST1_IP,
            mac="00:00:00:00:00:01"
        )

        h2 = self.addHost(
            "h2",
            ip=HOST2_IP,
            mac="00:00:00:00:00:02"
        )

        # Create switches with fixed datapath IDs
        s1 = self.addSwitch(
            "s1",
            dpid="0000000000000001",
            protocols = "OpenFlow13"
        )

        s2 = self.addSwitch(
            "s2",
            dpid="0000000000000002",
            protocols = "OpenFlow13"
        )

        s3 = self.addSwitch(
            "s3",
            dpid="0000000000000003",
            protocols = "OpenFlow13"
        )

        s4 = self.addSwitch(
            "s4",
            dpid="0000000000000004",
            protocols = "OpenFlow13"
        )

        # Connect hosts to switches
        self.addLink(h1, s1, cls=TCLink, bw=100)
        self.addLink(s4, h2, cls=TCLink, bw=100)

        # Primary path: s1 -> s2 -> s4
        self.addLink(
            s1, s2,
            cls=TCLink,
            bw=100,
            delay="2ms"
        )

        self.addLink(
            s2, s4,
            cls=TCLink,
            bw=100,
            delay="2ms"
        )

        # Alternate path: s1 -> s3 -> s4
        self.addLink(
            s1, s3,
            cls=TCLink,
            bw=50,
            delay="5ms"
        )

        self.addLink(
            s3, s4,
            cls=TCLink,
            bw=50,
            delay="5ms"
        )


def start_network(use_remote=False):

    topo = ReliableTransferTopo()

    if use_remote:

        info("*** Starting network with remote SDN controller\n")

        net = Mininet(
            topo=topo,
            switch=OVSSwitch,
            link=TCLink,
            controller=None,
            autoSetMacs=False,
            autoStaticArp=True,
            build=False
        )

        net.addController(
            "c0",
            controller=RemoteController,
            ip=CONTROLLER_IP,
            port=CONTROLLER_PORT
        )

    else:

        info("*** Starting network in standalone mode\n")

        net = Mininet(
            topo=topo,
            switch=OVSSwitch,
            link=TCLink,
            controller=None,
            autoSetMacs=False,
            autoStaticArp=True,
            build=False
        )

    try:

        # Build and start the network
        net.build()
        net.start()

        # IMPORTANT:
        # Set fail mode AFTER switches have started.
        # This fixes the previous 100% packet-loss issue.

        if use_remote:

            for switch in net.switches:
                switch.cmd(
                    "ovs-vsctl set-fail-mode "
                    + switch.name + " secure"
                )

        else:

            for switch in net.switches:
                result = switch.cmd(
                    "ovs-vsctl set-fail-mode "
                    + switch.name + " standalone"
                )

                info(
                    "*** " + switch.name
                    + " set to standalone mode\n"
                )

        # Display host information
        info("\n*** Network started successfully\n")

        h1 = net.get("h1")
        h2 = net.get("h2")

        info("*** Host information\n")
        info("*** h1 IP: " + h1.IP() + "\n")
        info("*** h2 IP: " + h2.IP() + "\n")

        # Configure static ARP entries
        h1.setARP(h2.IP(), h2.MAC())
        h2.setARP(h1.IP(), h1.MAC())

        info("*** Static ARP entries configured\n")
        info("*** Network topology ready\n")

        # Enter Mininet CLI
        info("*** Entering Mininet CLI\n")

        CLI(net)

    finally:

        info("*** Stopping network\n")
        net.stop()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Reliable UDP File Transfer Mininet Topology"
    )

    parser.add_argument(
        "--remote",
        action="store_true",
        help="Connect to remote SDN controller"
    )

    args = parser.parse_args()

    setLogLevel("info")

    try:

        start_network(args.remote)

    except Exception as error:

        print("[ERROR]", error)
        sys.exit(1)
