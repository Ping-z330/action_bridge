"""Dependency graph engine for project task analysis.

Computes:
  - critical_path: longest chain of dependent tasks
  - downstream_impact: all tasks affected when a given task is delayed
  - risk_score: aggregate project risk (0-100)
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DependencyNode:
    task_id: int
    title: str
    status: str
    planned_days: int = 0
    remaining_days: int = 0
    dependents: list[int] = field(default_factory=list)  # tasks that depend on this one


def build_dependency_graph(tasks: list[dict]) -> dict[int, DependencyNode]:
    """Build a dependency graph from a list of task dicts.

    Each task dict should have:
      - id, title, status
      - dependency_ids: list[int] (tasks this task depends on)
      - planned_end: str (YYYY-MM-DD)
      - deadline_date: str (YYYY-MM-DD, from action_items)
    """
    graph: dict[int, DependencyNode] = {}

    # First pass: create all nodes
    for t in tasks:
        dep_ids = t.get("dependency_ids", [])
        if isinstance(dep_ids, str):
            import json
            try:
                dep_ids = json.loads(dep_ids)
            except (json.JSONDecodeError, TypeError):
                dep_ids = []

        graph[t["id"]] = DependencyNode(
            task_id=t["id"],
            title=t.get("title", ""),
            status=t.get("status", "pending"),
            planned_days=t.get("planned_days", 0),
            remaining_days=t.get("remaining_days", 0),
            dependents=[],
        )

    # Second pass: wire up dependencies
    for t in tasks:
        dep_ids = t.get("dependency_ids", [])
        if isinstance(dep_ids, str):
            import json
            try:
                dep_ids = json.loads(dep_ids)
            except (json.JSONDecodeError, TypeError):
                dep_ids = []

        for dep_id in dep_ids:
            if dep_id in graph:
                graph[dep_id].dependents.append(t["id"])

    return graph


def compute_downstream_impact(
    graph: dict[int, DependencyNode],
    delayed_task_id: int,
) -> list[int]:
    """Find all tasks downstream of a delayed task (BFS traversal)."""
    if delayed_task_id not in graph:
        return []

    visited: set[int] = set()
    queue = deque([delayed_task_id])
    visited.add(delayed_task_id)
    impacted: list[int] = []

    while queue:
        node_id = queue.popleft()
        if node_id != delayed_task_id:
            impacted.append(node_id)
        for dep_id in graph[node_id].dependents:
            if dep_id not in visited:
                visited.add(dep_id)
                queue.append(dep_id)

    return impacted


def compute_critical_path(graph: dict[int, DependencyNode]) -> list[int]:
    """Compute the critical path using topological sort + longest path.

    Returns the sequence of task IDs on the critical path.
    """
    if not graph:
        return []

    # Build in-degree map and adjacency list
    in_degree: dict[int, int] = {nid: 0 for nid in graph}
    adj: dict[int, list[int]] = {nid: [] for nid in graph}

    for nid, node in graph.items():
        for dep_id in node.dependents:
            adj[nid].append(dep_id)
            in_degree[dep_id] = in_degree.get(dep_id, 0) + 1

    # Topological sort
    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    topo: list[int] = []
    while queue:
        nid = queue.popleft()
        topo.append(nid)
        for neighbor in adj[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if not topo:
        # Cyclic graph — return all nodes as a fallback
        return list(graph.keys())

    # Longest path in DAG (weight = planned_days)
    dist: dict[int, float] = {nid: float("-inf") for nid in graph}
    prev: dict[int, int | None] = {nid: None for nid in graph}

    for nid in topo:
        if dist[nid] == float("-inf"):
            dist[nid] = graph[nid].planned_days or 1

    for nid in topo:
        for neighbor in adj[nid]:
            new_dist = dist[nid] + (graph[neighbor].planned_days or 1)
            if new_dist > dist.get(neighbor, float("-inf")):
                dist[neighbor] = new_dist
                prev[neighbor] = nid

    # Find end node
    end_node = max(dist, key=lambda n: dist[n])
    path: list[int] = []
    current: int | None = end_node
    while current is not None:
        path.append(current)
        current = prev.get(current)

    path.reverse()
    return path


def compute_risk_score(tasks: list[dict]) -> int:
    """Compute aggregate project risk score (0-100).

    Factors:
      - Overdue tasks (60% weight)
      - Blocked tasks (30% weight)
      - Dependency chain breadth (10% weight)
    """
    if not tasks:
        return 0

    total = len(tasks)
    overdue = len([t for t in tasks if t.get("due_status") == "overdue" and t.get("status") != "completed"])
    blocked = len([t for t in tasks if t.get("status") in ("failed", "blocked")])

    graph = build_dependency_graph(tasks)
    max_chain = len(compute_critical_path(graph))

    overdue_score = (overdue / total) * 60 if total else 0
    blocked_score = (blocked / total) * 30 if total else 0
    chain_score = min(max_chain / max(total, 1) * 10, 10)

    return min(100, int(overdue_score + blocked_score + chain_score))
