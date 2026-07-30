"""Format a CFG as human-readable text for LLM prompts.

Separated from CFGExtractor (which builds the graph) to follow SRP.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyct.plugins.llm.analysis.cfg_extractor import CFGEdge, CFGNode


def format_cfg_for_llm(
    nodes: list[CFGNode],
    edges: list[CFGEdge],
    missing_lines: list[int] | None = None,
) -> str:
    """Format CFG nodes/edges as LLM-friendly text."""
    lines: list[str] = ["## Control Flow Graph\n"]
    _append_nodes_table(lines, nodes)
    _append_edges_table(lines, edges)
    _append_path_summary(lines, nodes, edges, missing_lines)
    return "\n".join(lines)


def _append_nodes_table(lines: list[str], nodes: list[CFGNode]) -> None:
    lines.append("### Nodes (Execution Points)")
    lines.append("```")
    lines.append("ID  | Line | Type       | Code")
    lines.append("----|------|------------|" + "-" * 40)
    for node in nodes:
        lines.append(
            f"{node.id:3} | {node.line_number:4} | {node.node_type:10} | {node.code_snippet[:40]}"
        )
        if node.condition:
            lines.append(f"    |      |            | → Condition: {node.condition}")
    lines.append("```\n")


def _append_edges_table(lines: list[str], edges: list[CFGEdge]) -> None:
    lines.append("### Edges (Control Flow)")
    lines.append("```")
    lines.append("From → To | Condition")
    lines.append("----------|" + "-" * 40)
    for edge in edges:
        lines.append(f"{edge.from_node:4} → {edge.to_node:2} | {edge.condition}")
    lines.append("```\n")


def _append_path_summary(
    lines: list[str],
    nodes: list[CFGNode],
    edges: list[CFGEdge],
    missing_lines: list[int] | None,
) -> None:
    lines.append("### Possible Execution Paths")
    all_paths = _enumerate_simple_paths(nodes, edges)
    if not all_paths:
        lines.append("(Linear execution, no branches)")
        return

    paths_to_show = _select_paths(all_paths, nodes, missing_lines, lines)
    for i, path in enumerate(paths_to_show, 1):
        lines.append(f"{i}. {' → '.join(str(n) for n in path)}")


def _select_paths(
    all_paths: list[list[int]],
    nodes: list[CFGNode],
    missing_lines: list[int] | None,
    lines: list[str],
) -> list[list[int]]:
    if missing_lines:
        return _filter_by_coverage(all_paths, nodes, missing_lines, lines)
    if len(all_paths) > 30:
        lines.append(f"**Showing first 30 of {len(all_paths)} total paths:**")
        return all_paths[:30]
    lines.append(f"**All {len(all_paths)} execution paths:**")
    return all_paths


def _filter_by_coverage(
    all_paths: list[list[int]],
    nodes: list[CFGNode],
    missing_lines: list[int],
    lines: list[str],
) -> list[list[int]]:
    node_to_line = {n.id: n.line_number for n in nodes}
    missing_set = set(missing_lines)
    relevant = [
        path for path in all_paths if any(node_to_line.get(nid) in missing_set for nid in path)
    ]
    if relevant:
        lines.append(f"**Showing {len(relevant)} paths containing uncovered lines:**")
        return relevant
    lines.append("**No paths for uncovered lines, showing first 10:**")
    return all_paths[:10]


# ------------------------------------------------------------------
# Path enumeration
# ------------------------------------------------------------------


@dataclass(frozen=True)
class _GraphContext:
    """Immutable context for DFS path enumeration."""

    adj: dict[int, list[int]]
    exits: set[int]
    max_paths: int


def _enumerate_simple_paths(
    nodes: list[CFGNode],
    edges: list[CFGEdge],
    max_paths: int = 50,
) -> list[list[int]]:
    """Enumerate simple (cycle-free) paths via DFS."""
    if not nodes or not edges:
        return [[n.id for n in nodes]]

    adj = _build_adjacency_list(nodes, edges)
    exits = _find_exit_ids(nodes)
    if not exits:
        return []

    ctx = _GraphContext(adj=adj, exits=exits, max_paths=max_paths)
    paths: list[list[int]] = []
    _dfs(1, [1], set(), ctx, paths)
    return paths


def _build_adjacency_list(nodes: list[CFGNode], edges: list[CFGEdge]) -> dict[int, list[int]]:
    adj: dict[int, list[int]] = {n.id: [] for n in nodes}
    for e in edges:
        adj[e.from_node].append(e.to_node)
    return adj


def _find_exit_ids(nodes: list[CFGNode]) -> set[int]:
    exits = {n.id for n in nodes if n.node_type == "return"}
    if not exits and nodes:
        exits = {nodes[-1].id}
    return exits


def _dfs(
    current: int,
    path: list[int],
    visited: set[int],
    ctx: _GraphContext,
    paths: list[list[int]],
) -> None:
    if len(paths) >= ctx.max_paths or current in visited:
        return
    if current in ctx.exits:
        paths.append(path[:])
        return
    visited.add(current)
    for nxt in ctx.adj.get(current, []):
        path.append(nxt)
        _dfs(nxt, path, visited, ctx, paths)
        path.pop()
    visited.remove(current)
