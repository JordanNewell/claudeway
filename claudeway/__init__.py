"""
Claudeway Core - Multi-agent coordination that actually agrees.

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

__version__ = "0.4.0"

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentResponse",
    "ConsensusReceipt",
    "ConsensusResult",
    "ConsensusStrategy",
    "Coordinator",
    "CoordinatorConfig",
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
    "WeightedVote",
    "sign_statement",
    "statement_hash",
    "verify_receipt_detailed",
    "verify_statement",
]
