"""
 Copyright (c) 2025 Computer Networks Group @ UPB

 Permission is hereby granted, free of charge, to any person obtaining a copy of
 this software and associated documentation files (the "Software"), to deal in
 the Software without restriction, including without limitation the rights to
 use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
 the Software, and to permit persons to whom the Software is furnished to do so,
 subject to the following conditions:

 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
 FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
 COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
 IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
 CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 """

#!/usr/bin/env python3

from ryu.base import app_manager
from ryu.controller import mac_to_port
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.lib.packet import ipv4
from ryu.lib.packet import arp

from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
from ryu.app.wsgi import ControllerBase

import topo
import heapq

class SPRouter(app_manager.RyuApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SPRouter, self).__init__(*args, **kwargs)
        
        # Initialize the topology with #ports=4
        self.num_ports = 4
        self.topo_net = topo.Fattree(self.num_ports)
        self.graph = {}                 # dpid -> list of (neighbor, weight, port)
        self.switch_datapaths = {}      # dpid -> datapath
        self.arp_table = {}             # ip -> mac
        self.hosts = {}                 # ip -> (dpid -> port)
        self.agg_switches_by_pod = {}   # pod -> list of dpids
        self.core_dpids = []
        self.edge_labelled_graph = {}
        self.arp_replies = []


    @set_ev_cls(ofp_event.EventOFPStateChange, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def _state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.switch_datapaths[dp.id] = dp


    # Topology discovery
    @set_ev_cls(event.EventSwitchEnter)
    def get_topology_data(self, ev):

        # Switches and links in the network
        switches = get_switch(self, None)
        links = get_link(self, None)
        self.graph.clear()

        for link in links:
            src = link.src.dpid
            dst = link.dst.dpid
            out_port = link.src.port_no
            in_port = link.dst.port_no

            self.graph.setdefault(src, []).append((dst, 1, out_port))
            self.graph.setdefault(dst, []).append((src, 1, in_port))


    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install entry-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)


    # Add a flow entry to the flow-table
    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Construct flow_mod message and send it
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)


    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # # TODO: handle new packets at the controller
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            arp_pkt = pkt.get_protocol(arp.arp)
            src_ip = arp_pkt.src_ip
            dst_ip = arp_pkt.dst_ip
            src_mac = arp_pkt.src_mac
            opcode = arp_pkt.opcode

            self.hosts[src_ip] = (dpid, in_port)
            self.arp_table[src_ip] = src_mac

            if opcode == arp.ARP_REQUEST:
                self.logger.error('ARP_REQUEST: %s ---> %s', src_ip, dst_ip)
                self.logger.error('%s', self.hosts)
                self.handle_arp_request(dpid, src_ip, dst_ip, msg.data)

            elif opcode == arp.ARP_REPLY:

                self.logger.error('ARP_REPLY: %s ---> %s', src_ip, dst_ip)
                self.handle_arp_reply(dpid, src_ip, dst_ip, msg.data)
            
            # return                    

            # if dst_ip in self.hosts and dst_ip in self.arp_table: 
            #     self.logger.error('dst_ip learnt : %s ---> %s', dst_ip, self.hosts)
            #     # self.route_two_level(dpid, dst_ip, src_ip, msg.data)
            #     self.send_proxy_arp_reply(datapath, in_port, src_ip, dst_ip)
            #     self.logger.error('<---------- Proxy arp reply sent: ---> %s', src_ip)
            # else:
            #     self.logger.error('<------------- dst_ip not learnt ARP route attempt ---------->',)
            #     self.route_two_level(dpid, dst_ip, src_ip, msg.data)    
            # return

        if eth.ethertype == ether_types.ETH_TYPE_IP:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            src_ip = ip_pkt.src
            dst_ip = ip_pkt.dst
            self.hosts[src_ip] = (dpid, in_port)

            self.logger.error('IP packet detected: from %s ---> %s',src_ip, dst_ip)

            if dst_ip in self.hosts:
                self.logger.error('Host is known forwarding: ---> %s', dst_ip)
                dst_dpid, dst_port = self.hosts[dst_ip]
                path = self.dijsktra_shortest_path(dpid, dst_dpid)
                self.install_packet_flow(path, dst_ip, dst_port)
                self.forward_request_on_path(msg.data, path, dst_port)

            else:
                self.logger.error('IP packet dst NOT known: ---> %s', dst_ip)
                self.route_two_level(dpid, dst_ip, src_ip, msg.data)


    def handle_arp_request(self, src_dpid, src_ip, dst_ip, data):
        if dst_ip in self.arp_table and dst_ip in self.hosts:
            self.send_arp_reply_to_requester(dst_ip, src_ip)
        else:
            # TODO: Fix route for dst_ip not known
            self.logger.error('Dest ip: %s not learnt yeat: on to two %s ', dst_ip, self.hosts)
            self.route_two_level(src_dpid, dst_ip, src_ip,data)


    def handle_arp_reply(self, src_dpid, src_ip, dst_ip, data):
        if dst_ip in self.hosts:
            dst_dpid, dst_port = self.hosts[dst_ip]
            path = self.dijsktra_shortest_path(src_dpid, dst_dpid)
            self.logger.error('Sending ARP reply src: %s -> %s on path %s', src_ip, dst_ip, path)
            if path:
                self.forward_request_on_path(data, path, dst_port)


    def parse_ip_info(self, ip):
        parts = ip.split('.')
        pod, edge, host = int(parts[1]), int(parts[2]), int(parts[3])
        return pod, edge, host

    def get_pod_from_dpid(self, dpid):
        if 100 <= dpid < 200:
            return (dpid - 100) // 10
        elif 200 <= dpid < 300:
            return (dpid - 200) // 10
        else: 
            return None


    def route_two_level(self, dpid, dst_ip, src_ip, data):
        try:
            src_pod, _, _ = self.parse_ip_info(src_ip)
            dst_pod, _, _ = self.parse_ip_info(dst_ip)

            if src_pod == dst_pod:
                self.logger.error('-------- SAME POD: %s -> %s ------------>', src_pod, dst_pod)

                # Intra pod routing
                for dst_ip in self.hosts:
                    dst_dpid, _ = self.hosts[dst_ip]
                    self.logger.error('For dst %s compared to src %s:', dst_dpid, dpid)
                    
                    computed_dst_pod = self.get_pod_from_dpid(dst_dpid)
                    self.logger.error('Found a matching dst dpath %s compared to src %s:', dst_dpid, dpid)

                    if computed_dst_pod == dst_pod:
                        path = self.dijsktra_shortest_path(dpid, dst_dpid)
                        self.logger.error('-------- navigating same pod: %s  using path: %s------------>',computed_dst_pod, path)
                        out_port = self.get_out_port(path)
                        if path and out_port:
                            self.forward_request_on_path(data, path, out_port)
                            return
            else:
                # inter-pod routing
                self.logger.error('-------- different pods ------------> src: %s -- dst: %s ',src_pod, dst_pod)
                self.logger.error('---------2-LEVEL ACCROSS PODS ------------> %s to %s',src_pod, dst_pod)
                self.route_arp_requests_to_core_then_edge(dpid, dst_ip, data)
                return

        except Exception as e:
            self.logger.error('two-level routing failed: %s', str(e))

    def get_switch_role(self, dpid):
        if 100 <= dpid < 200:
            return 'edge'
        elif 200 <= dpid < 300:
            return 'agg'
        elif 300 <= dpid < 400:
            return 'core'
        return 'unknown'


    def get_out_port(self, path):
        if not path or len(path) < 2:
            return None
        src, dst = path[0], path[1]
        for neighbor, _, port in self.graph.get(src, []):
            if neighbor == dst:
                return port
        return None

    def route_arp_requests_to_core_then_edge(self, src_dpid, dst_ip, data):
        # go up to core
        core_switches = [dpid for dpid in self.switch_datapaths if self.get_switch_role(dpid) == 'core']
        edge_switches = [dpid for dpid in self.switch_datapaths if self.get_switch_role(dpid) == 'edge']

        for core in core_switches:
            path_up = self.dijsktra_shortest_path(src_dpid, core)
            out_port = self.get_out_port(path_up)
            if path_up and out_port:
                self.forward_request_on_path(data, path_up, out_port)

            for edge in edge_switches:
                path_down = self.dijsktra_shortest_path(core, edge)
                out_port = self.get_out_port(path_down)
                if path_down and out_port:
                    self.forward_request_on_path(data, path_down, out_port)


    def install_packet_flow(self, path, dst_ip, dst_port):
        self.logger.error('-------- installing packet flow for ------------> src: %s ',path)

        for i in range(len(path) - 1):
            curr_sw = path[i]
            next_sw = path[i + 1]
            out_port = self.get_out_port([curr_sw, next_sw])

            if out_port is None:
                continue
            
            dp = self.switch_datapaths[curr_sw]
            parser = dp.ofproto_parser
            match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
            actions = [parser.OFPActionOutput(out_port)]
            self.add_flow(dp, 10, match, actions)
        

        # IP packet reached final destination
        last_dp = self.switch_datapaths[path[-1]]
        parser = last_dp.ofproto_parser
        match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
        actions = [parser.OFPActionOutput(dst_port)]
        self.add_flow(last_dp, 10, match, actions)


    def send_arp_reply_to_requester(self, target_ip,  requester_ip):
        req_dpid, req_port  = self.hosts[requester_ip]
        target_mac = self.arp_table[target_ip]
        requester_mac = self.arp_table[requester_ip]

        dp = self.switch_datapaths[req_dpid]
        e = ethernet.ethernet(dst=requester_mac, src=target_mac, ethertype=ether_types.ETH_TYPE_ARP)
        a = arp.arp(hwtype=1, proto=0x0800, hlen=6, plen=4, opcode=arp.ARP_REPLY,
                    src_mac=target_mac, src_ip=target_ip,
                    dst_mac=requester_mac, dst_ip=requester_ip)
        pkt = packet.Packet()
        pkt.add_protocol(e)
        pkt.add_protocol(a)
        pkt.serialize()
        actions = [dp.ofproto_parser.OFPActionOutput(req_port)]
        out = dp.ofproto_parser.OFPPacketOut(
            datapath=dp, buffer_id=dp.ofproto.OFP_NO_BUFFER,
            in_port=dp.ofproto.OFPP_CONTROLLER, actions=actions, data=pkt.data)
        dp.send_msg(out)
        self.logger.error('-------- ARP reply reached ------------> src: %s ',requester_ip)



    def forward_request_on_path(self, data, path, final_out_port):
        # Add Forwared rules
        for i in range(len(path) - 1):
            curr_sw = path[i]
            next_sw = path[i + 1]
            out_port = self.get_out_port([curr_sw, next_sw])
            dp = self.switch_datapaths[curr_sw]

            if out_port:
                parser = dp.ofproto_parser
                actions = [parser.OFPActionOutput(out_port)]
                out = parser.OFPPacketOut(
                    datapath=dp,
                    buffer_id=dp.ofproto.OFP_NO_BUFFER,
                    in_port=dp.ofproto.OFPP_CONTROLLER,
                    actions=actions,
                    data=data
                )
                dp.send_msg(out)


        last_dp = self.switch_datapaths[path[-1]]
        actions = [last_dp.ofproto_parser.OFPActionOutput(final_out_port)]
        out = last_dp.ofproto_parser.OFPPacketOut(
                datapath=last_dp,
                buffer_id=last_dp.ofproto.OFP_NO_BUFFER,
                in_port=last_dp.ofproto.OFPP_CONTROLLER,
                actions=actions,
                data=data
        )
        last_dp.send_msg(out)
        self.logger.info('<------ packet reached Destination ---> on path %s', path)


    def dijsktra_shortest_path(self, start, goal):
        # graph: {node: [neighbor, weight, outport], ...]}
        visited = set()
        min_heap = [(0, start, [])] # (cost, node, path_so_far)

        while min_heap:
            cost, current_node, path = heapq.heappop(min_heap)

            if current_node in visited:
                continue

            visited.add(current_node)
            path = path + [current_node]

            if current_node == goal:
                return path
            
            for neighbor, weight, _ in self.graph.get(current_node, []):
                if neighbor not in visited:
                    heapq.heappush(min_heap, (cost + weight, neighbor, path))

        return [] # no path found
