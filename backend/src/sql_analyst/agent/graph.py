"""The agent graph (BUILD_GUIDE §3 and §8) and the `Agent` entry point.

    guard_input -> retrieve_context -> generate_sql -> validate_sql -> execute
        -> check_result -> write_answer -> render_numbers -> finalize

Nodes leave the default path by setting `goto`: a failed attempt goes back to
generate_sql (at most `max_repairs` times), a refusal goes to refuse, a rejected answer
template goes back to write_answer once. Every edge passes through the budget guard,
which sends the run to budget_stop -> finalize when a limit is reached.
"""

import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

from langgraph.graph import END, START, StateGraph

from sql_analyst.agent.deps import AgentDeps
from sql_analyst.agent.nodes.answer import render_numbers, write_answer
from sql_analyst.agent.nodes.check import check_result
from sql_analyst.agent.nodes.finalize import AgentResult, budget_stop, finalize
from sql_analyst.agent.nodes.guard import guard_input, refuse
from sql_analyst.agent.nodes.retrieve import retrieve_context
from sql_analyst.agent.nodes.sql import execute, generate_sql, validate_sql
from sql_analyst.agent.state import AgentState
from sql_analyst.observability import NodeEvent
from sql_analyst.safety.scope import UserScope

Node = Callable[[AgentState, AgentDeps], dict[str, Any]]

NODES: dict[str, Node] = {
    "guard_input": guard_input,
    "retrieve_context": retrieve_context,
    "generate_sql": generate_sql,
    "validate_sql": validate_sql,
    "execute": execute,
    "check_result": check_result,
    "write_answer": write_answer,
    "render_numbers": render_numbers,
    "refuse": refuse,
    "budget_stop": budget_stop,
    "finalize": finalize,
}

DEFAULT_NEXT = {
    "guard_input": "retrieve_context",
    "retrieve_context": "generate_sql",
    "generate_sql": "validate_sql",
    "validate_sql": "execute",
    "execute": "check_result",
    "check_result": "write_answer",
    "write_answer": "render_numbers",
    "render_numbers": "finalize",
}
_ALWAYS_ALLOWED = {"refuse", "finalize"}  # ending a run never needs budget


def _timed(name: str, fn: Node, deps: AgentDeps) -> Callable[[AgentState], dict[str, Any]]:
    def node(state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        update = fn(state, deps)
        note = update.pop("_note", None)
        update.setdefault("goto", None)
        update["trace"] = [
            NodeEvent(node=name, ms=round((time.perf_counter() - started) * 1000, 1), note=note)
        ]
        return update

    return node


def _guarded(name: str, deps: AgentDeps) -> Callable[[AgentState], str]:
    def route(state: AgentState) -> str:
        dest = state.goto or DEFAULT_NEXT[name]
        if dest in _ALWAYS_ALLOWED:
            return dest
        reason = deps.config.limits.exceeded(
            state.llm_calls, state.started, next_calls_llm=dest in deps.llm_nodes
        )
        return "budget_stop" if reason else dest

    return route


def build_graph(deps: AgentDeps):
    g = StateGraph(AgentState)
    for name, fn in NODES.items():
        g.add_node(name, _timed(name, fn, deps))
    g.add_edge(START, "guard_input")
    targets = [n for n in NODES if n != "guard_input"]
    for name in DEFAULT_NEXT:
        g.add_conditional_edges(name, _guarded(name, deps), targets)
    g.add_edge("refuse", "finalize")
    g.add_edge("budget_stop", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


class Agent:
    """Ask questions as a signed-in user. Thread-safe once built."""

    def __init__(self, deps: AgentDeps):
        self.deps = deps
        self.graph = build_graph(deps)

    def _start(self, question: str, user: UserScope, session_id: str | None) -> AgentState:
        return AgentState(
            run_id=uuid.uuid4().hex,
            question=question,
            user=user,
            session_id=session_id,
            started=time.perf_counter(),
        )

    def ask(self, question: str, user: UserScope, session_id: str | None = None) -> AgentResult:
        start = self._start(question, user, session_id)
        out = self.graph.invoke(start, config={"recursion_limit": 60})
        return out["response"]

    def stream(
        self, question: str, user: UserScope, session_id: str | None = None
    ) -> Iterator[NodeEvent | AgentResult]:
        """Yield each node's NodeEvent as soon as the node finishes, then the AgentResult."""
        result: AgentResult | None = None
        for chunk in self.graph.stream(
            self._start(question, user, session_id),
            config={"recursion_limit": 60},
            stream_mode="updates",
        ):
            for update in chunk.values():
                yield update["trace"][-1]
                result = update.get("response", result)
        if result is None:  # finalize always runs; this would be a graph bug
            raise RuntimeError("The agent finished without a result.")
        yield result
