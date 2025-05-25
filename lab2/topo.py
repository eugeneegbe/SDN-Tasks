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

# Class for an edge in the graph
class Edge:
	def __init__(self):
		self.lnode = None
		self.rnode = None
	
	def remove(self):
		self.lnode.edges.remove(self)
		self.rnode.edges.remove(self)
		self.lnode = None
		self.rnode = None

# Class for a node in the graph
class Node:
	def __init__(self, id, type):
		self.edges = []
		self.id = id
		self.type = type

	# Add an edge connected to another node
	def add_edge(self, node):
		edge = Edge()
		edge.lnode = self
		edge.rnode = node
		self.edges.append(edge)
		node.edges.append(edge)
		return edge

	# Remove an edge from the node
	def remove_edge(self, edge):
		self.edges.remove(edge)

	# Decide if another node is a neighbor
	def is_neighbor(self, node):
		for edge in self.edges:
			if edge.lnode == node or edge.rnode == node:
				return True
		return False


class Fattree:

	def __init__(self, num_ports):
		self.servers = []
		self.nodes = []
		self.generate(num_ports)
		self.check_nodes_degree()
		self.num_ports = num_ports

	def generate(self, num_ports):
		pods = num_ports
		num_agg_per_pod = num_ports // 2
		num_edge_per_pod = num_ports // 2
		num_host_per_edge = num_ports // 2
		self.core = []

		for i in range(num_ports // 2):
			for j in range(num_ports // 2):
				self.core.append(Node(f'c{j}_{i}', 'switch'))

		self.nodes.extend(self.core)

		for pod in range(pods):
			agg = [Node(f'a{pod}_{i}', "switch")  for i in range(num_agg_per_pod)]
			edge = [Node(f'e{pod}_{i}', "switch") for i in range(num_edge_per_pod)]
			
			# add agg and edge to list of switches
			self.nodes.extend(agg + edge)

			# add edge to host
			for i, e in enumerate(edge):
				for j in range(num_host_per_edge):
					h = Node(f'h{pod}_{i}_{j}', "host")
					e.add_edge(h)

					# Add h as a host and as a node
					self.servers.append(h)
					self.nodes.append(h)

				# connect edge to agg in same pod
				for e in edge:
					for a in agg:
						e.add_edge(a)
				
				# Connect agg to core
				for i, a in enumerate(agg):
					for j in range(num_ports // 2):
						conn_index = i * (num_ports // 2) + j
						a.add_edge(self.core[conn_index])


	def check_nodes_degree(self):
		"""
			stores edges globally and count uniqe
		"""
		print('\n====Node Degree Check ===')
		for node in self.nodes:
			connected = set()
			for edge in node.edges:
				other = edge.rnode if edge.lnode == node else edge.lnode
				connected.add(other.id)
			print(f'Node ID: {node.id:10} | Type: {node.type:6} | Degree: {len(connected)}')