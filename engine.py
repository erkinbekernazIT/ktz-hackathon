from __future__ import annotations

import networkx as nx

from src.domain.types import NodeId, TrackId
from src.domain.station.models import StationGraph
from src.domain.station.types import NodeType


class GraphEngine:
    """NetworkX wrapper for station topology graph operations."""

    def build_from_station_graph(self, graph: StationGraph) -> nx.DiGraph:
        """Build a networkx DiGraph from a StationGraph domain model.

        Nodes are NodeIds, edges are Tracks with track_id as an attribute.
        For bidirectional tracks, both directions are added.
        """
        dg = nx.DiGraph()

        # Add all nodes
        for node_id, node in graph.nodes.items():
            dg.add_node(node_id, node_type=node.node_type, name=node.name)

        # Add all tracks as directed edges
        for track_id, track in graph.tracks.items():
            dg.add_edge(
                track.source_node_id,
                track.target_node_id,
                track_id=track_id,
                length_m=track.length_m,
                max_weight_t=track.max_weight_t,
                allowed_train_types=track.allowed_train_types,
                is_bidirectional=track.is_bidirectional,
            )
            if track.is_bidirectional:
                dg.add_edge(
                    track.target_node_id,
                    track.source_node_id,
                    track_id=track_id,
                    length_m=track.length_m,
                    max_weight_t=track.max_weight_t,
                    allowed_train_types=track.allowed_train_types,
                    is_bidirectional=track.is_bidirectional,
                )

        return dg

    def find_paths(
        self,
        graph: nx.DiGraph,
        from_node: NodeId,
        to_node: NodeId,
        exclude_tracks: set[TrackId] | None = None,
    ) -> list[list[TrackId]]:
        """Find all simple paths from from_node to to_node.

        Returns each path as an ordered list of TrackIds.
        Optionally excludes specified tracks from the search.
        """
        exclude_tracks = exclude_tracks or set()

        if from_node not in graph or to_node not in graph:
            return []

        # Build a subgraph excluding the blocked tracks
        if exclude_tracks:
            edges_to_remove = [
                (u, v)
                for u, v, data in graph.edges(data=True)
                if data.get("track_id") in exclude_tracks
            ]
            working_graph = graph.copy()
            working_graph.remove_edges_from(edges_to_remove)
        else:
            working_graph = graph

        paths_as_track_ids: list[list[TrackId]] = []

        try:
            for node_path in nx.all_simple_paths(working_graph, from_node, to_node):
                # Convert node path to track path
                track_path: list[TrackId] = []
                valid = True
                for i in range(len(node_path) - 1):
                    u, v = node_path[i], node_path[i + 1]
                    edge_data = working_graph.get_edge_data(u, v)
                    if edge_data is None:
                        valid = False
                        break
                    track_id = edge_data.get("track_id")
                    if track_id is None:
                        valid = False
                        break
                    track_path.append(TrackId(track_id))
                if valid and track_path:
                    paths_as_track_ids.append(track_path)
        except (nx.NetworkXError, nx.NodeNotFound):
            pass

        return paths_as_track_ids

    def check_connectivity(
        self,
        graph: nx.DiGraph,
        entry_nodes: list[NodeId],
        platform_nodes: list[NodeId],
    ) -> list[NodeId]:
        """Check connectivity: each Entry node must have a path to at least one Platform.

        Returns the list of Entry NodeIds that have NO path to any Platform node.
        (disconnected / isolated entry nodes)
        """
        disconnected: list[NodeId] = []

        for entry_node in entry_nodes:
            if entry_node not in graph:
                disconnected.append(entry_node)
                continue

            has_path_to_platform = False
            for platform_node in platform_nodes:
                if platform_node not in graph:
                    continue
                try:
                    if nx.has_path(graph, entry_node, platform_node):
                        has_path_to_platform = True
                        break
                except (nx.NetworkXError, nx.NodeNotFound):
                    continue

            if not has_path_to_platform:
                disconnected.append(entry_node)

        return disconnected
