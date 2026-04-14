"""
graph.py — Supervisor Orchestrator (Refactored)

Architecture:
    Input → Supervisor → Worker → Synthesis → Output

Workers:
    - retrieval_worker
    - policy_tool_worker
    - human_review (HITL)

Run:
    python graph.py
"""

import json
import os
import time

from datetime import datetime
from typing import TypedDict, Literal, Optional


# ============================================================
# 1. Shared State
# ============================================================

class AgentState(TypedDict):
    # Input
    task: str

    # Supervisor decisions
    route_reason: str
    risk_high: bool
    needs_tool: bool
    hitl_triggered: bool

    # Worker outputs
    retrieved_chunks: list
    retrieved_sources: list
    policy_result: dict
    mcp_tools_used: list

    # Final output
    final_answer: str
    sources: list
    confidence: float

    # Trace
    history: list
    workers_called: list
    supervisor_route: str
    latency_ms: Optional[int]
    run_id: str


def make_initial_state(task: str) -> AgentState:
    """Initialize clean state."""

    return {
        "task": task,

        "route_reason": "",
        "risk_high": False,
        "needs_tool": False,
        "hitl_triggered": False,

        "retrieved_chunks": [],
        "retrieved_sources": [],
        "policy_result": {},
        "mcp_tools_used": [],

        "final_answer": "",
        "sources": [],
        "confidence": 0.0,

        "history": [],
        "workers_called": [],
        "supervisor_route": "",

        "latency_ms": None,
        "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
    }


# ============================================================
# 2. Routing Logic (Improved)
# ============================================================

POLICY_KEYWORDS = [
    "hoàn tiền",
    "refund",
    "flash sale",
    "license",
    "cấp quyền",
    "access",
    "level 3",
]

RETRIEVAL_KEYWORDS = [
    "sla",
    "ticket",
    "p1",
    "p2",
    "escalation",
]

RISK_KEYWORDS = [
    "emergency",
    "khẩn cấp",
    "2am",
    "không rõ",
    "err-",
]


def classify_task(task: str):

    task_lc = task.lower()

    route = "retrieval_worker"
    reason = "default retrieval route"
    needs_tool = False
    risk_high = False

    # ---------- POLICY ----------
    if any(k in task_lc for k in POLICY_KEYWORDS):
        route = "policy_tool_worker"
        reason = "policy/access keyword detected"
        needs_tool = True

    # ---------- RETRIEVAL ----------
    elif any(k in task_lc for k in RETRIEVAL_KEYWORDS):
        route = "retrieval_worker"
        reason = "SLA/ticket keyword detected"

    # ---------- RISK ----------
    if any(k in task_lc for k in RISK_KEYWORDS):
        risk_high = True
        reason += " | risk flagged"

    # ---------- HUMAN REVIEW ----------
    if risk_high and "err-" in task_lc:
        route = "human_review"
        reason = "unknown error + risk → human review"

    return route, reason, needs_tool, risk_high


# ============================================================
# 3. Supervisor Node
# ============================================================

def supervisor_node(state: AgentState) -> AgentState:

    task = state["task"]

    state["history"].append(
        f"[supervisor] received: {task[:80]}"
    )

    route, reason, needs_tool, risk_high = classify_task(task)

    state["supervisor_route"] = route
    state["route_reason"] = reason
    state["needs_tool"] = needs_tool
    state["risk_high"] = risk_high

    state["history"].append(
        f"[supervisor] route={route} reason={reason}"
    )

    return state


# ============================================================
# 4. Route Decision
# ============================================================

def route_decision(
    state: AgentState
) -> Literal[
    "retrieval_worker",
    "policy_tool_worker",
    "human_review"
]:

    return state.get(
        "supervisor_route",
        "retrieval_worker"
    )


# ============================================================
# 5. Worker Nodes
# ============================================================

def human_review_node(state: AgentState) -> AgentState:

    state["hitl_triggered"] = True

    state["workers_called"].append(
        "human_review"
    )

    state["history"].append(
        "[human_review] HITL triggered"
    )

    print("\n⚠️ HITL TRIGGERED")
    print(f"Task: {state['task']}")
    print(f"Reason: {state['route_reason']}")
    print("Auto-approve (lab mode)\n")

    # Continue pipeline
    state["supervisor_route"] = "retrieval_worker"

    return state


def retrieval_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi retrieval worker."""
    from workers.retrieval import run as retrieval_run
    return retrieval_run(state)


def policy_tool_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi policy/tool worker."""
    from workers.policy_tool import run as policy_tool_run
    return policy_tool_run(state)


def synthesis_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi synthesis worker."""
    from workers.synthesis import run as synthesis_run
    return synthesis_run(state)


# ============================================================
# 6. Graph Orchestrator
# ============================================================

def build_graph():

    def run(state: AgentState) -> AgentState:

        start = time.time()

        # Step 1 — Supervisor
        state = supervisor_node(state)

        # Step 2 — Routing
        route = route_decision(state)

        if route == "human_review":

            state = human_review_node(state)
            state = retrieval_worker_node(state)

        elif route == "policy_tool_worker":

            state = policy_tool_worker_node(state)

            if not state["retrieved_chunks"]:
                state = retrieval_worker_node(state)

        else:

            state = retrieval_worker_node(state)

        # Step 3 — Synthesis
        state = synthesis_worker_node(state)

        state["latency_ms"] = int(
            (time.time() - start) * 1000
        )

        state["history"].append(
            f"[graph] completed in {state['latency_ms']}ms"
        )

        return state

    return run


_graph = build_graph()


# ============================================================
# 7. Public API
# ============================================================

def run_graph(task: str) -> AgentState:

    state = make_initial_state(task)

    return _graph(state)


def save_trace(
    state: AgentState,
    output_dir: str = "./artifacts/traces"
):

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    filename = (
        f"{output_dir}/{state['run_id']}.json"
    )

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return filename


# ============================================================
# 8. Manual Test
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("Supervisor-Worker Graph Test")
    print("=" * 60)

    test_queries = [

        "SLA xử lý ticket P1 là bao lâu?",

        "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",

        "ERR-443 xảy ra lúc 2AM, cần escalation ngay",

    ]

    for q in test_queries:

        print(f"\n▶ Query: {q}")

        result = run_graph(q)

        print("Route      :", result["supervisor_route"])
        print("Reason     :", result["route_reason"])
        print("Workers    :", result["workers_called"])
        print("Confidence :", result["confidence"])
        print("Latency    :", result["latency_ms"], "ms")

        trace = save_trace(result)

        print("Trace saved:", trace)

    print("\n✅ graph.py ready")