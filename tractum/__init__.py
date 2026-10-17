"""
Tractum Core - Multi-agent coordination that actually agrees.

A clean, efficient implementation of multi-agent Claude orchestration.
Real consensus, real decomposition, real concurrency.
"""

from .agent import Agent, AgentConfig, Message
from .consensus import (
    ConsensusResult,
    ConsensusStrategy,
    Debate,
    WeightedVote,
)
from .coordinator import Coordinator, CoordinatorConfig, SubTask
from .curt_link import (
    CurtLinkError,
    CurtLinkVerification,
    TranscriptLink,
    build_curt_transcript,
    emit_curt_decision,
    link_receipt,
    parse_curt,
    receipt_from_curt_decision,
    validate_curt,
    verify_curt_link,
)
from .runtime import Runtime
from .signing import (
    ConsensusReceipt,
    Ed25519Backend,
    ReceiptVerification,
    SignatureBackend,
    StatementVerification,
    sign_statement,
    statement_hash,
    verify_receipt_detailed,
    verify_statement,
)
from .signing_pq import MLDSABackend
from .swarm import AgentResponse, Swarm, SwarmConfig, Task

__version__ = "0.5.0"

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentResponse",
    "ConsensusReceipt",
    "ConsensusResult",
    "ConsensusStrategy",
    "Coordinator",
    "CoordinatorConfig",
    "CurtLinkError",
    "CurtLinkVerification",
    "Debate",
    "Ed25519Backend",
    "MLDSABackend",
    "Message",
    "ReceiptVerification",
    "Runtime",
    "SignatureBackend",
    "StatementVerification",
    "SubTask",
    "Swarm",
    "SwarmConfig",
    "Task",
    "TranscriptLink",
    "WeightedVote",
    "build_curt_transcript",
    "emit_curt_decision",
    "link_receipt",
    "parse_curt",
    "receipt_from_curt_decision",
    "sign_statement",
    "statement_hash",
    "validate_curt",
    "verify_curt_link",
    "verify_receipt_detailed",
    "verify_statement",
]
