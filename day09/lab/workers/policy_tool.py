"""
workers/policy_tool.py — Policy & Tool Worker
Sprint 2+3: Kiểm tra policy dựa vào context, gọi MCP tools khi cần.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: context từ retrieval_worker
    - needs_tool: True nếu supervisor quyết định cần tool call

Output (vào AgentState):
    - policy_result: {"policy_applies", "policy_name", "exceptions_found", "source", "rule"}
    - mcp_tools_used: list of tool calls đã thực hiện
    - worker_io_log: log

Gọi độc lập để test:
    python workers/policy_tool.py
"""

"""
workers/policy_tool.py — Policy & Tool Worker (Refactored)

Responsibilities:
    - Analyze refund/access policy
    - Detect exceptions
    - Call MCP tools when needed
    - Update AgentState

Run standalone:
    python workers/policy_tool.py
"""

from datetime import datetime
from typing import Dict, List


WORKER_NAME = "policy_tool_worker"


# ============================================================
# MCP CLIENT LAYER
# ============================================================

def call_mcp_tool(
    tool_name: str,
    tool_input: dict
) -> dict:
    """
    Call MCP tool.

    Sprint 3:
        Replace with HTTP MCP client if needed.
    """

    try:
        from mcp_server import dispatch_tool

        result = dispatch_tool(
            tool_name,
            tool_input
        )

        return {
            "tool": tool_name,
            "input": tool_input,
            "output": result,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:

        return {
            "tool": tool_name,
            "input": tool_input,
            "output": None,
            "error": {
                "code": "MCP_CALL_FAILED",
                "reason": str(e),
            },
            "timestamp": datetime.now().isoformat(),
        }


# ============================================================
# POLICY RULE ENGINE
# ============================================================

FLASH_SALE_KEYWORDS = [
    "flash sale"
]

DIGITAL_PRODUCT_KEYWORDS = [
    "license",
    "license key",
    "subscription",
    "kỹ thuật số",
]

ACTIVATED_PRODUCT_KEYWORDS = [
    "đã kích hoạt",
    "đã đăng ký",
    "đã sử dụng",
]


def detect_flash_sale(task: str, context: str):

    if "flash sale" in task or "flash sale" in context:

        return {
            "type": "flash_sale_exception",
            "rule":
                "Đơn hàng Flash Sale không được hoàn tiền "
                "(Điều 3, policy v4).",
            "source": "policy_refund_v4.txt",
        }

    return None


def detect_digital_product(task: str):

    if any(k in task for k in DIGITAL_PRODUCT_KEYWORDS):

        return {
            "type": "digital_product_exception",
            "rule":
                "Sản phẩm kỹ thuật số không được hoàn tiền "
                "(Điều 3, policy v4).",
            "source": "policy_refund_v4.txt",
        }

    return None


def detect_activated_product(task: str):

    if any(k in task for k in ACTIVATED_PRODUCT_KEYWORDS):

        return {
            "type": "activated_exception",
            "rule":
                "Sản phẩm đã kích hoạt không được hoàn tiền "
                "(Điều 3, policy v4).",
            "source": "policy_refund_v4.txt",
        }

    return None


def detect_policy_version(task: str):

    task_lc = task.lower()

    if (
        "31/01" in task_lc
        or "30/01" in task_lc
        or "trước 01/02" in task_lc
    ):

        return {
            "version": "v3",
            "note":
                "Đơn hàng trước 01/02/2026 "
                "áp dụng policy v3 (không có docs).",
        }

    return {
        "version": "v4",
        "note": "",
    }


# ============================================================
# POLICY ANALYSIS
# ============================================================

def analyze_policy(
    task: str,
    chunks: List[dict]
) -> dict:

    task_lc = task.lower()

    context_text = " ".join(
        c.get("text", "")
        for c in chunks
    ).lower()

    exceptions = []

    # ---------- Exception detection ----------

    flash_ex = detect_flash_sale(
        task_lc,
        context_text
    )

    if flash_ex:
        exceptions.append(flash_ex)

    digital_ex = detect_digital_product(
        task_lc
    )

    if digital_ex:
        exceptions.append(digital_ex)

    activated_ex = detect_activated_product(
        task_lc
    )

    if activated_ex:
        exceptions.append(activated_ex)

    # ---------- Policy version ----------

    version_info = detect_policy_version(
        task
    )

    policy_applies = len(exceptions) == 0

    sources = list({
        c.get("source", "unknown")
        for c in chunks
        if c
    })

    return {

        "policy_applies": policy_applies,

        "policy_name":
            f"refund_policy_{version_info['version']}",

        "exceptions_found": exceptions,

        "source": sources,

        "policy_version_note":
            version_info["note"],

        "explanation":
            "Rule-based policy evaluation",

    }


# ============================================================
# MCP HELPER FUNCTIONS
# ============================================================

def ensure_chunks(
    state: dict
):

    chunks = state.get(
        "retrieved_chunks",
        []
    )

    needs_tool = state.get(
        "needs_tool",
        False
    )

    if not chunks and needs_tool:

        mcp_result = call_mcp_tool(
            "search_kb",
            {
                "query":
                    state.get("task", ""),
                "top_k": 3,
            }
        )

        state["mcp_tools_used"].append(
            mcp_result
        )

        if (
            mcp_result.get("output")
            and
            mcp_result["output"].get("chunks")
        ):

            state["retrieved_chunks"] = (
                mcp_result["output"]["chunks"]
            )

            return state["retrieved_chunks"]

    return chunks


def maybe_fetch_ticket(
    state: dict
):

    task = state.get(
        "task",
        ""
    ).lower()

    if any(
        k in task
        for k in ["ticket", "p1", "jira"]
    ):

        mcp_result = call_mcp_tool(
            "get_ticket_info",
            {
                "ticket_id":
                    "P1-LATEST"
            }
        )

        state["mcp_tools_used"].append(
            mcp_result
        )


# ============================================================
# WORKER ENTRY POINT
# ============================================================

def run(
    state: dict
) -> dict:

    state.setdefault(
        "workers_called",
        []
    )

    state.setdefault(
        "history",
        []
    )

    state.setdefault(
        "mcp_tools_used",
        []
    )

    state.setdefault(
        "worker_io_logs",
        []
    )

    task = state.get("task", "")

    state["workers_called"].append(
        WORKER_NAME
    )

    state["history"].append(
        f"[{WORKER_NAME}] started"
    )

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count":
                len(
                    state.get(
                        "retrieved_chunks",
                        []
                    )
                ),
        },
        "output": None,
        "error": None,
    }

    try:

        # ---------- Ensure context ----------

        chunks = ensure_chunks(state)

        # ---------- Policy analysis ----------

        policy_result = analyze_policy(
            task,
            chunks
        )

        state["policy_result"] = (
            policy_result
        )

        # ---------- Optional ticket info ----------

        maybe_fetch_ticket(state)

        worker_io["output"] = {

            "policy_applies":
                policy_result["policy_applies"],

            "exceptions":
                len(
                    policy_result[
                        "exceptions_found"
                    ]
                ),

            "mcp_calls":
                len(
                    state[
                        "mcp_tools_used"
                    ]
                ),
        }

        state["history"].append(
            f"[{WORKER_NAME}] "
            f"policy_applies="
            f"{policy_result['policy_applies']}"
        )

    except Exception as e:

        worker_io["error"] = {
            "code":
                "POLICY_CHECK_FAILED",
            "reason":
                str(e),
        }

        state["policy_result"] = {
            "error": str(e)
        }

        state["history"].append(
            f"[{WORKER_NAME}] ERROR {e}"
        )

    state["worker_io_logs"].append(
        worker_io
    )

    return state


# ============================================================
# Standalone Test
# ============================================================

if __name__ == "__main__":

    print("=" * 50)
    print("Policy Tool Worker — Test")
    print("=" * 50)

    tests = [

        {
            "task":
                "Khách Flash Sale yêu cầu hoàn tiền",
            "retrieved_chunks": [
                {
                    "text":
                        "Flash Sale không hoàn tiền",
                    "source":
                        "policy_refund_v4.txt",
                }
            ],
        },

        {
            "task":
                "Hoàn tiền license key đã kích hoạt",
            "retrieved_chunks": [
                {
                    "text":
                        "License không hoàn tiền",
                    "source":
                        "policy_refund_v4.txt",
                }
            ],
        },

        {
            "task":
                "Hoàn tiền sản phẩm lỗi",
            "retrieved_chunks": [
                {
                    "text":
                        "Hoàn tiền trong 7 ngày",
                    "source":
                        "policy_refund_v4.txt",
                }
            ],
        },

    ]

    for t in tests:

        print("\n▶", t["task"])

        state = run(t.copy())

        pr = state.get(
            "policy_result",
            {}
        )

        print(
            "policy_applies:",
            pr.get("policy_applies")
        )

        if pr.get("exceptions_found"):

            for ex in pr["exceptions_found"]:

                print(
                    " exception:",
                    ex["type"]
                )

        print(
            "mcp_calls:",
            len(
                state.get(
                    "mcp_tools_used",
                    []
                )
            )
        )

    print("\n✅ policy_tool_worker ready")