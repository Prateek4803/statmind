"""StatMind CAPA workflow engine — schema, state machine, and industry rule packs.

Foundation layer encoding the CAPA Engine Specification (§2 state machine,
§4 gates, §5 packs, §7 rules-as-data). This is the deterministic lifecycle
skeleton; persistence, audit trail, e-signatures, and RBAC (§6) are deployment
infrastructure not yet implemented.
"""
from .state_machine import CAPAState, can_transition, lifecycle_order, TransitionResult
from .schema import RulePack, validate_pack
