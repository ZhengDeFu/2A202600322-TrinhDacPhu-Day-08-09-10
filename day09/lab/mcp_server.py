"""
mcp_server.py — Mock MCP Server (Refactored)

Responsibilities:
    - Tool discovery
    - Tool execution
    - Schema validation
    - Latency logging
    - Safe dispatch

Tools:
    - search_kb
    - get_ticket_info
    - check_access_permission
    - create_ticket

Run:
    python mcp_server.py
"""

import time
from datetime import datetime
from typing import Dict, Any, Callable


# ============================================================
# CONFIG
# ============================================================

SERVER_NAME = "mock_mcp_server"

DEFAULT_TOP_K = 3


# ============================================================
# TOOL SCHEMAS
# ============================================================

TOOL_SCHEMAS = {

    "search_kb": {

        "name": "search_kb",

        "description":
            "Semantic search nội bộ.",

        "required": ["query"],

        "defaults": {
            "top_k": DEFAULT_TOP_K
        },

    },

    "get_ticket_info": {

        "name": "get_ticket_info",

        "description":
            "Tra cứu ticket.",

        "required": ["ticket_id"],

    },

    "check_access_permission": {

        "name": "check_access_permission",

        "description":
            "Kiểm tra quyền truy cập.",

        "required": [
            "access_level",
            "requester_role"
        ],

        "defaults": {
            "is_emergency": False
        },

    },

    "create_ticket": {

        "name": "create_ticket",

        "description":
            "Tạo ticket mock.",

        "required": [
            "priority",
            "title"
        ],

        "defaults": {
            "description": ""
        },

    }

}


# ============================================================
# TOOL IMPLEMENTATIONS
# ============================================================

def tool_search_kb(
    query: str,
    top_k: int = DEFAULT_TOP_K
) -> dict:

    try:

        from workers.retrieval import retrieve_dense

        chunks = retrieve_dense(
            query,
            top_k=top_k
        )

        sources = list({

            c.get("source", "unknown")

            for c in chunks

        })

        return {

            "chunks": chunks,

            "sources": sources,

            "total_found": len(chunks),

        }

    except Exception as e:

        return {

            "error":
                f"search_kb failed: {e}"

        }


# ------------------------------

MOCK_TICKETS = {

    "P1-LATEST": {

        "ticket_id": "IT-9847",

        "priority": "P1",

        "status": "in_progress",

        "assignee": "senior_engineer",

        "created_at":
            "2026-04-13T22:47:00",

        "sla_deadline":
            "2026-04-14T02:47:00",

    }

}


def tool_get_ticket_info(
    ticket_id: str
) -> dict:

    ticket = MOCK_TICKETS.get(
        ticket_id.upper()
    )

    if ticket:

        return ticket

    return {

        "error":
            f"Ticket '{ticket_id}' not found.",

        "available_ids":
            list(MOCK_TICKETS.keys())

    }


# ------------------------------

ACCESS_RULES = {

    1: ["Line Manager"],

    2: ["Line Manager", "IT Admin"],

    3: ["Line Manager", "IT Admin", "IT Security"],

}


def tool_check_access_permission(
    access_level: int,
    requester_role: str,
    is_emergency: bool = False
) -> dict:

    approvers = ACCESS_RULES.get(
        access_level
    )

    if not approvers:

        return {

            "error":
                f"Invalid level {access_level}"

        }

    return {

        "access_level":
            access_level,

        "can_grant": True,

        "required_approvers":
            approvers,

        "emergency_override":
            is_emergency
            and access_level == 2,

        "source":
            "access_control_sop.txt",

    }


# ------------------------------

def tool_create_ticket(
    priority: str,
    title: str,
    description: str = ""
) -> dict:

    ticket_id = (

        f"IT-"

        f"{9900 + hash(title) % 99}"

    )

    return {

        "ticket_id": ticket_id,

        "priority": priority,

        "title": title,

        "description": description[:200],

        "status": "open",

        "created_at":
            datetime.now().isoformat(),

        "url":
            f"https://jira.mock/{ticket_id}",

    }


# ============================================================
# TOOL REGISTRY
# ============================================================

TOOL_REGISTRY: Dict[
    str,
    Callable[..., Dict[str, Any]]
] = {

    "search_kb": tool_search_kb,

    "get_ticket_info":
        tool_get_ticket_info,

    "check_access_permission":
        tool_check_access_permission,

    "create_ticket":
        tool_create_ticket,

}


# ============================================================
# VALIDATION
# ============================================================

def _validate_input(
    tool_name: str,
    tool_input: dict
):

    schema = TOOL_SCHEMAS.get(
        tool_name
    )

    if not schema:

        raise ValueError(
            f"Tool '{tool_name}' unknown."
        )

    required = schema.get(
        "required",
        []
    )

    for key in required:

        if key not in tool_input:

            raise ValueError(
                f"Missing required field: {key}"
            )

    defaults = schema.get(
        "defaults",
        {}
    )

    for key, value in defaults.items():

        tool_input.setdefault(
            key,
            value
        )

    return tool_input


# ============================================================
# DISCOVERY
# ============================================================

def list_tools() -> list:

    return list(

        TOOL_SCHEMAS.values()

    )


# ============================================================
# DISPATCH
# ============================================================

def dispatch_tool(
    tool_name: str,
    tool_input: dict
) -> dict:

    start = time.time()

    try:

        if tool_name not in TOOL_REGISTRY:

            return {

                "error":
                    f"Tool '{tool_name}' not found.",

                "available_tools":
                    list(
                        TOOL_REGISTRY.keys()
                    )

            }

        tool_input = _validate_input(

            tool_name,

            tool_input

        )

        tool_fn = TOOL_REGISTRY[
            tool_name
        ]

        result = tool_fn(
            **tool_input
        )

        latency_ms = int(

            (time.time() - start)
            * 1000

        )

        return {

            "success": True,

            "tool": tool_name,

            "latency_ms":
                latency_ms,

            "result": result,

        }

    except Exception as e:

        latency_ms = int(

            (time.time() - start)
            * 1000

        )

        return {

            "success": False,

            "tool": tool_name,

            "latency_ms":
                latency_ms,

            "error": str(e),

        }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 50)
    print("MCP Server Test")
    print("=" * 50)

    print("\n📋 Tools:")

    for t in list_tools():

        print(
            f" - {t['name']}"
        )

    print("\n🔍 search_kb test")

    r = dispatch_tool(

        "search_kb",

        {

            "query":
                "SLA P1",

            "top_k": 2

        }

    )

    print(r)

    print("\n🎫 ticket test")

    r = dispatch_tool(

        "get_ticket_info",

        {

            "ticket_id":
                "P1-LATEST"

        }

    )

    print(r)

    print("\n❌ invalid test")

    r = dispatch_tool(

        "unknown_tool",

        {}

    )

    print(r)

    print("\n✅ MCP server ready")