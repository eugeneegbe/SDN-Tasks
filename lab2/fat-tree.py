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

import os
import subprocess
import time

import mininet
import mininet.clean
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import lg, info
from mininet.link import TCLink
from mininet.node import Node, OVSKernelSwitch, RemoteController
from mininet.topo import Topo
from mininet.util import waitListening, custom

from topo import Fattree


class FattreeNet(Topo):
    """
    Create a fat-tree network in Mininet
    """

    def __init__(self, ft_topo):

        Topo.__init__(self)
        self.build_net_from_topo(ft_topo)

    def build_net_from_topo(self, ft_topo):
        node_map = {}

        # Iterate and add mininet
        for node in ft_topo.nodes:
            # add switches
            if node.type == 'switch':
                dpid_int = self.generate_dpid(node.id)
                dpid_hex = f'{dpid_int:016x}'
                sw = self.addSwitch(f's{node.id}', dpid=dpid_hex)
                node_map[node.id] = sw 

            elif node.type == 'host':
                pod, edge, host = self.parse_host_id(node.id)
                ip = f'10.{pod}.{edge}.{host}/24'
                host_name = f'h_{pod}_{edge}_{host}'
                print('creating host ', host_name)
                h = self.addHost(host_name, ip=ip)
                node_map[node.id] = h


        # Add links
        for node in ft_topo.nodes:
            for edge in node.edges:
                if edge.lnode.id == node.id:
                    src = node_map[edge.lnode.id]
                    dst = node_map[edge.rnode.id]
                else:
                    src = node_map[edge.rnode.id]
                    dst = node_map[edge.lnode.id]

                self.addLink(src, dst, bw=15, delay='5ms')


    def parse_host_id(self, raw_id):
        print('____------>', raw_id)
        # ex h1_0_1 -> pod 1, switch 0, host 1
        parts = raw_id.replace('h', '').split('_')
        pod = int(parts[0])
        edge = int(parts[1])
        host = int(parts[2])
        return pod, edge, host


    def generate_dpid(self, node_id):
        if node_id.startswith('e'):
            # Edge switch, format: e<pod>_<index>
            pod, idx = map(int, node_id[1:].split('_'))

            return 100 + (pod * 10) + idx
        elif node_id.startswith('a'):
            # Aggregation switch
            pod, idx = map(int, node_id[1:].split('_'))
            return 200 + (pod * 10) + idx

        elif node_id.startswith('c'):
            # Core switch, format: c<col>_<row>
            col, row = map(int, node_id[1:].split('_'))
            return 300 + (row * 10) + col
        else:
            # default fallback (not expected)
            return 9999


def make_mininet_instance(graph_topo):

    net_topo = FattreeNet(graph_topo)
    net = Mininet(topo=net_topo, controller=None, autoSetMacs=True)
    net.addController('c0', controller=RemoteController,
                      ip="127.0.0.1", port=6653)
    return net


def run(graph_topo):

    # Run the Mininet CLI with a given topology
    lg.setLogLevel('info')
    mininet.clean.cleanup()
    net = make_mininet_instance(graph_topo)

    info('*** Starting network ***\n')
    net.start()
    info('*** Running CLI ***\n')
    CLI(net)
    info('*** Stopping network ***\n')
    net.stop()


if __name__ == '__main__':
    ft_topo = Fattree(4)
    run(ft_topo)
