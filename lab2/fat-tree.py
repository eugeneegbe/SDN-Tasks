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
                sw = self.addSwitch(f's{node.id}')
                node_map[node.id] = sw
            elif node.type == 'host':
                pod, edge, host = self.parse_host_id(node.id)
                ip = f'10.{pod}.{edge}.{host}/24'
                host_name = f'h{pod}_{edge}_{host}'
                h = self.addHost(host_name, ip=ip, defaultRoute=None)
                node_map[node.id] = h
        
        # Add links
        for node in ft_topo.nodes:
            for edge in node.edges:
                if edge.lnode.id == node.id:
                    src = node_map[edge.lnode.id]
                    dst = node_map[edge.rnode.id]
                    self.addLink(src, dst, cls=TCLink,  bw=15, delay='5ms')


    def parse_host_id(self, raw_id):
        # ex h1_0_1 -> pod 1, switch 0, host 1
        pod, edge, host = raw_id.replace('h', '').replace('_', ' ').split()
        pod = int(pod)
        edge = int(edge)
        host = int(host) + 2  #offset to start at .2
        return pod, edge, host


def make_mininet_instance(graph_topo):

    net_topo = FattreeNet(graph_topo)
    net = Mininet(topo=net_topo, controller=None, autoSetMacs=True)
    assign_switch_ips(net, graph_topo)
    net.addController('c0', controller=RemoteController,
                      ip="127.0.0.1", port=6653)
    return net


def assign_switch_ips(net, graph_topo):
    for node in graph_topo.nodes:
        if node.type == 'switch':
            sw_name = f's{node.id}'
            sw = net.get(sw_name)

            # Add support for ip management using loopback
            ip = generate_switch_ip(node.id, graph_topo.num_ports)
            sw.cmd(f'ip addr add {ip} dev lo')
            sw.cmd('ip link set lo up')
            print(f"Assigned {ip} to {sw_name}")


def generate_switch_ip(sw_id, num_ports):
    if sw_id.startswith('e'):
        pod, i = map(int, sw_id.replace('e', '').replace('_', ' ').split())
        return f'10.{pod}.{i}.1/32'

    elif sw_id.startswith('a'):
        pod, i = map(int, sw_id.replace('a', '').replace('_', ' ').split())
        return f'10.{pod}.{i+2}.1/32'

    elif sw_id.startswith('c'):
        print('core sw_id', sw_id)
        j, i = map(int, sw_id.replace('c', '').replace('_', ' ').split())
        return f'10.{num_ports}.{j+1}.{i+1}/32'


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
