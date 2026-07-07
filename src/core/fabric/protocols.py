"""Open protocols AOS uses as glue between engines.

AOS does NOT invent a private integration bus. It rides OPEN standards so
any compliant engine drops in. Today's three: MCP (tool calls), A2A
(cross-agent collaboration), ACP (enterprise agent addressing). Adapters
may implement these so plumbing is standard, not bespoke.

Note: this is the resolution to the earlier "private bridge" tension.
Writing a thin adapter to an OPEN protocol is not "building your own
architecture" - it is speaking the common tongue.
"""
from __future__ import annotations

OPEN_PROTOCOLS: Dict[str, str] = {
    "MCP": "Model Context Protocol (Anthropic) - tool / resource calling.",
    "A2A": "Agent2Agent (Google) - cross-agent collaboration.",
    "ACP": "Agent Communication Protocol (IBM) - enterprise agent addressing.",
    "AG-UI": "Agent-User UI protocol (CopilotKit) - agent<->frontend streaming, "
             "2026's 4th major protocol. AOS keeps this open slot ready.",
}

# 2026 reality check (searched 2026-07): the field is "the year of protocols"
# but NONE has won. MCP has documented production pain; A2A/ACP/AG-UI are all
# still evolving. So adapters must be PROTOCOL-READY, never protocol-welded:
# speak whichever the engine supports, degrade gracefully otherwise.
PROTOCOL_LANDSCAPE_NOTE = (
    "No single protocol has won in 2026. AOS rides open standards but treats "
    "them as swappable transport, not a fixed dependency."
)


def describe() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in OPEN_PROTOCOLS.items())
