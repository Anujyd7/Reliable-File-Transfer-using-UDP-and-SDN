"""
Reliable File Transfer using UDP and SDN
OS-Ken OpenFlow 1.3 Controller

Primary path: h1 -> s1 -> s2 -> s4 -> h2
Backup path:  h1 -> s1 -> s3 -> s4 -> h2

Features:
- OpenFlow 1.3 switch management
- Initial switch-port discovery
- IPv4 forwarding rules
- Primary and backup path selection
- Link failure detection
- Automatic rerouting
- Primary path restoration
"""

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    MAIN_DISPATCHER,
    DEAD_DISPATCHER,
    set_ev_cls
)
from os_ken.ofproto import ofproto_v1_3


class ReliableTransferController(app_manager.OSKenApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    S1 = 1
    S2 = 2
    S3 = 3
    S4 = 4

    HOST1_IP = "10.0.0.1"
    HOST2_IP = "10.0.0.2"

    def __init__(self, *args, **kwargs):
        super(ReliableTransferController, self).__init__(
            *args, **kwargs
        )

        self.datapaths = {}
        self.failed_ports = set()
        self.port_desc_received = set()

        self.initialized = False
        self.current_path = None

        # Ports required by the primary path.
        self.primary_required_ports = {
            (self.S1, 1), (self.S1, 2),
            (self.S2, 1), (self.S2, 2),
            (self.S4, 2), (self.S4, 1)
        }

        # Ports required by the backup path.
        self.backup_required_ports = {
            (self.S1, 1), (self.S1, 3),
            (self.S3, 1), (self.S3, 2),
            (self.S4, 3), (self.S4, 1)
        }

        self.primary_switches = {self.S1, self.S2, self.S4}
        self.backup_switches = {self.S1, self.S3, self.S4}

        # Forward direction: h1 -> h2
        self.primary_forward = {
            self.S1: 2,
            self.S2: 2,
            self.S4: 1
        }

        # Reverse direction: h2 -> h1
        self.primary_reverse = {
            self.S4: 2,
            self.S2: 1,
            self.S1: 1
        }

        self.backup_forward = {
            self.S1: 3,
            self.S3: 2,
            self.S4: 1
        }

        self.backup_reverse = {
            self.S4: 3,
            self.S3: 1,
            self.S1: 1
        }

        self.logger.info(
            "Reliable Transfer SDN Controller initialized"
        )

    # -----------------------------------------------------
    # Switch connection and disconnection
    # -----------------------------------------------------

    @set_ev_cls(
        ofp_event.EventOFPStateChange,
        [MAIN_DISPATCHER, DEAD_DISPATCHER]
    )
    def switch_state_handler(self, event):

        datapath = event.datapath
        dpid = datapath.id

        if dpid not in (self.S1, self.S2, self.S3, self.S4):
            return

        if event.state == MAIN_DISPATCHER:

            if dpid not in self.datapaths:
                self.datapaths[dpid] = datapath

                self.logger.info(
                    "Switch s%d connected", dpid
                )

                # Request the actual port states from this switch.
                parser = datapath.ofproto_parser
                request = parser.OFPPortDescStatsRequest(
                    datapath, 0
                )
                datapath.send_msg(request)

        elif event.state == DEAD_DISPATCHER:

            if dpid in self.datapaths:
                del self.datapaths[dpid]

                self.port_desc_received.discard(dpid)

                self.logger.warning(
                    "Switch s%d disconnected", dpid
                )

                if self.initialized:
                    self.recompute_path()

    # -----------------------------------------------------
    # Initial port discovery response
    # -----------------------------------------------------

    @set_ev_cls(
        ofp_event.EventOFPPortDescStatsReply,
        MAIN_DISPATCHER
    )
    def port_description_handler(self, event):

        datapath = event.msg.datapath
        dpid = datapath.id
        ofp = datapath.ofproto

        # Remove previous status records for this switch.
        self.failed_ports = {
            item for item in self.failed_ports
            if item[0] != dpid
        }

        for desc in event.msg.body:

            port_no = desc.port_no

            if port_no == ofp.OFPP_LOCAL:
                continue

            port_key = (dpid, port_no)

            link_down = bool(
                desc.state & ofp.OFPPS_LINK_DOWN
            )

            administratively_down = bool(
                desc.config & ofp.OFPPC_PORT_DOWN
            )

            if link_down or administratively_down:
                self.failed_ports.add(port_key)

                self.logger.warning(
                    "Port unavailable: s%d port %d",
                    dpid, port_no
                )

        self.port_desc_received.add(dpid)

        self.logger.info(
            "Port discovery completed for s%d", dpid
        )

        # Wait until all four switches have been discovered.
        if (
            not self.initialized
            and len(self.datapaths) == 4
            and len(self.port_desc_received) == 4
        ):
            self.initialized = True

            self.logger.info(
                "All four switches and their ports discovered"
            )

            self.recompute_path()

    # -----------------------------------------------------
    # Detect link failures and restorations
    # -----------------------------------------------------

    @set_ev_cls(
        ofp_event.EventOFPPortStatus,
        MAIN_DISPATCHER
    )
    def port_status_handler(self, event):

        msg = event.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofp = datapath.ofproto

        port_no = msg.desc.port_no
        port_key = (dpid, port_no)

        if msg.reason == ofp.OFPPR_DELETE:

            self.failed_ports.add(port_key)

            self.logger.warning(
                "Port deleted: s%d port %d",
                dpid, port_no
            )

        else:

            link_down = bool(
                msg.desc.state & ofp.OFPPS_LINK_DOWN
            )

            administratively_down = bool(
                msg.desc.config & ofp.OFPPC_PORT_DOWN
            )

            if link_down or administratively_down:

                self.failed_ports.add(port_key)

                self.logger.warning(
                    "LINK FAILURE: s%d port %d",
                    dpid, port_no
                )

            else:

                if port_key in self.failed_ports:
                    self.failed_ports.remove(port_key)

                    self.logger.info(
                        "LINK RESTORED: s%d port %d",
                        dpid, port_no
                    )

        if self.initialized:
            self.recompute_path()

    # -----------------------------------------------------
    # Check path availability
    # -----------------------------------------------------

    def path_is_available(self, required_ports, required_switches):

        # Every switch on the path must be connected.
        if not required_switches.issubset(self.datapaths.keys()):
            return False

        # Every required port must be operational.
        for port_key in required_ports:
            if port_key in self.failed_ports:
                return False

        return True

    # -----------------------------------------------------
    # Delete old forwarding rules
    # -----------------------------------------------------

    def delete_all_flows(self, datapath):

        ofp = datapath.ofproto
        parser = datapath.ofproto_parser

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            cookie=0,
            cookie_mask=0,
            table_id=ofp.OFPTT_ALL,
            command=ofp.OFPFC_DELETE,
            out_port=ofp.OFPP_ANY,
            out_group=ofp.OFPG_ANY,
            match=parser.OFPMatch()
        )

        datapath.send_msg(flow_mod)

    # -----------------------------------------------------
    # Install an IPv4 forwarding rule
    # -----------------------------------------------------

    def add_ipv4_flow(
        self,
        datapath,
        source_ip,
        destination_ip,
        output_port
    ):

        ofp = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch(
            eth_type=0x0800,
            ipv4_src=source_ip,
            ipv4_dst=destination_ip
        )

        actions = [
            parser.OFPActionOutput(output_port)
        ]

        instructions = [
            parser.OFPInstructionActions(
                ofp.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=100,
            match=match,
            instructions=instructions,
            idle_timeout=0,
            hard_timeout=0
        )

        datapath.send_msg(flow_mod)

        self.logger.info(
            "Flow installed on s%d: %s -> %s, output port %d",
            datapath.id,
            source_ip,
            destination_ip,
            output_port
        )

    # -----------------------------------------------------
    # Install forwarding rules for a selected path
    # -----------------------------------------------------

    def install_path(
        self,
        forward_rules,
        reverse_rules,
        path_name
    ):

        # Clear previous rules on all connected switches.
        for datapath in self.datapaths.values():
            self.delete_all_flows(datapath)

        # Install forward and reverse rules.
        for dpid, output_port in forward_rules.items():

            datapath = self.datapaths.get(dpid)

            if datapath is not None:
                self.add_ipv4_flow(
                    datapath,
                    self.HOST1_IP,
                    self.HOST2_IP,
                    output_port
                )

        for dpid, output_port in reverse_rules.items():

            datapath = self.datapaths.get(dpid)

            if datapath is not None:
                self.add_ipv4_flow(
                    datapath,
                    self.HOST2_IP,
                    self.HOST1_IP,
                    output_port
                )

        self.current_path = path_name

        if path_name == "PRIMARY":
            self.logger.info(
                "FORWARDING PATH ACTIVE: PRIMARY "
                "(s1 -> s2 -> s4)"
            )
        else:
            self.logger.info(
                "FORWARDING PATH ACTIVE: BACKUP "
                "(s1 -> s3 -> s4)"
            )

    # -----------------------------------------------------
    # Select the best available path
    # -----------------------------------------------------

    def recompute_path(self):

        if not self.initialized:
            return

        primary_available = self.path_is_available(
            self.primary_required_ports,
            self.primary_switches
        )

        backup_available = self.path_is_available(
            self.backup_required_ports,
            self.backup_switches
        )

        self.logger.info(
            "Path status: primary=%s, backup=%s, failed_ports=%s",
            primary_available,
            backup_available,
            sorted(self.failed_ports)
        )

        # Prefer primary whenever it is available.
        if primary_available:

            if self.current_path != "PRIMARY":
                self.logger.info(
                    "Selecting primary path"
                )

                self.install_path(
                    self.primary_forward,
                    self.primary_reverse,
                    "PRIMARY"
                )

        elif backup_available:

            if self.current_path != "BACKUP":
                self.logger.warning(
                    "Primary path unavailable!"
                )

                self.logger.warning(
                    "Switching to backup route: s1 -> s3 -> s4"
                )

                self.install_path(
                    self.backup_forward,
                    self.backup_reverse,
                    "BACKUP"
                )

        else:

            if self.current_path != "NONE":

                self.logger.error(
                    "No complete path between h1 and h2!"
                )

                for datapath in self.datapaths.values():
                    self.delete_all_flows(datapath)

                self.current_path = "NONE"
