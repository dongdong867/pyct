"""Control Flow Graph extraction from Python source code.

Builds a graph of nodes and edges from Python AST. Returns pure data —
formatting is handled separately by :mod:`pyct.plugins.llm.analysis.cfg_formatter`.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger("pyct.cfg")


@dataclass(frozen=True)
class CFGNode:
    """A node in the control flow graph."""

    id: int
    line_number: int
    node_type: str
    code_snippet: str
    condition: Optional[str] = None
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "line": self.line_number,
            "type": self.node_type,
            "code": self.code_snippet,
            "condition": self.condition,
            "details": self.details,
        }


@dataclass(frozen=True)
class CFGEdge:
    """An edge in the control flow graph."""

    from_node: int
    to_node: int
    condition: str

    def to_dict(self) -> Dict:
        return {"from": self.from_node, "to": self.to_node, "condition": self.condition}


@dataclass(frozen=True)
class CFGResult:
    """Result of CFG extraction — pure data, no formatting."""

    nodes: List[CFGNode]
    edges: List[CFGEdge]
    entry_node: Optional[int]
    exit_nodes: List[int]


class CFGExtractor:
    """Extract control flow graph from Python source code via AST."""

    def __init__(self) -> None:
        self.nodes: List[CFGNode] = []
        self.edges: List[CFGEdge] = []
        self.next_id = 1

    def extract(self, source_code: str) -> CFGResult:
        """Parse source code and return the CFG as a data object."""
        self._reset()
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            log.debug("Failed to parse source code: %s", e)
            raise

        _CFGVisitor(self).visit(tree)
        return CFGResult(
            nodes=list(self.nodes),
            edges=list(self.edges),
            entry_node=1 if self.nodes else None,
            exit_nodes=self._find_exit_nodes(),
        )

    def _reset(self) -> None:
        self.nodes = []
        self.edges = []
        self.next_id = 1

    def add_node(
        self,
        line_number: int,
        node_type: str,
        code_snippet: str,
        condition: Optional[str] = None,
        **details,
    ) -> int:
        """Add a node, returning its ID."""
        node = CFGNode(
            id=self.next_id,
            line_number=line_number,
            node_type=node_type,
            code_snippet=code_snippet,
            condition=condition,
            details=details,
        )
        self.nodes.append(node)
        self.next_id += 1
        return node.id

    def add_edge(self, from_node: int, to_node: int, condition: str = "unconditional") -> None:
        """Add a directed edge."""
        self.edges.append(CFGEdge(from_node=from_node, to_node=to_node, condition=condition))

    def _find_exit_nodes(self) -> List[int]:
        exits = [n.id for n in self.nodes if n.node_type == "return"]
        if not exits and self.nodes:
            exits = [self.nodes[-1].id]
        return exits


# ======================================================================
# AST Visitor — builds the CFG by walking Python AST nodes
# ======================================================================


class _CFGVisitor(ast.NodeVisitor):
    """AST visitor that populates a CFGExtractor with nodes and edges."""

    def __init__(self, extractor: CFGExtractor) -> None:
        self.ext = extractor
        self.parent: Optional[int] = None

    def _connect(self, node_id: int) -> None:
        if self.parent is not None:
            self.ext.add_edge(self.parent, node_id)

    def _safe_unparse(self, node: ast.expr, fallback: str = "...") -> str:
        try:
            return ast.unparse(node)
        except (ValueError, TypeError):
            return fallback

    def _visit_body(self, stmts: list) -> None:
        for stmt in stmts:
            self.visit(stmt)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.parent = self.ext.add_node(
            node.lineno, "entry", f"def {node.name}(...)", function_name=node.name
        )
        self._visit_body(node.body)
        if not any(isinstance(s, ast.Return) for s in node.body):
            exit_id = self.ext.add_node(
                node.end_lineno or node.lineno, "return", "return None  # implicit"
            )
            self._connect(exit_id)

    def visit_If(self, node: ast.If) -> None:
        cond = self._safe_unparse(node.test, "condition")
        if_id = self.ext.add_node(node.lineno, "if", f"if {cond}", condition=cond)
        self._connect(if_id)
        prev = self.parent
        self._visit_branch(if_id, node.body, "true")
        self._visit_branch(if_id, node.orelse, "false")
        self.parent = prev

    def _visit_branch(self, parent_id: int, stmts: list, label: str) -> None:
        if not stmts:
            return
        self.parent = parent_id
        start = self.parent
        self._visit_body(stmts)
        self.ext.add_edge(parent_id, start, condition=label)

    def visit_While(self, node: ast.While) -> None:
        cond = self._safe_unparse(node.test, "loop_condition")
        loop_id = self.ext.add_node(node.lineno, "while", f"while {cond}", condition=cond)
        self._visit_loop(loop_id, node.body)

    def visit_For(self, node: ast.For) -> None:
        target = self._safe_unparse(node.target, "item")
        loop_id = self.ext.add_node(node.lineno, "for", f"for {target} in ...")
        self._visit_loop(loop_id, node.body)

    def _visit_loop(self, loop_id: int, body: list) -> None:
        self._connect(loop_id)
        self.parent = loop_id
        self._visit_body(body)
        self.ext.add_edge(self.parent, loop_id, condition="loop")
        self.parent = loop_id

    def visit_Return(self, node: ast.Return) -> None:
        value = ast.unparse(node.value) if node.value else "None"
        rid = self.ext.add_node(node.lineno, "return", f"return {value}", return_value=value)
        self._connect(rid)
        self.parent = rid

    def visit_Assign(self, node: ast.Assign) -> None:
        targets = ", ".join(ast.unparse(t) for t in node.targets)
        aid = self.ext.add_node(node.lineno, "assign", f"{targets} = {ast.unparse(node.value)}")
        self._connect(aid)
        self.parent = aid

    def visit_Expr(self, node: ast.Expr) -> None:
        eid = self.ext.add_node(node.lineno, "expr", ast.unparse(node.value))
        self._connect(eid)
        self.parent = eid
