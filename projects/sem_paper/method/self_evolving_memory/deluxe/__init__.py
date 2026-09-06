"""Paper-1 Deluxe read-side runtime.

The package is project-owned. It consumes typed read contracts and never
becomes a second evidence authority or an adoption authority.
"""

from .api import (
    CapabilityCard,
    CapabilityLifecycle,
    CapabilityLifecycleConfig,
    CapabilityState,
    DeluxeArchitectureSnapshot,
    DeluxeNodeDescriptor,
    LineageEdge,
    MemoryFault,
    MemoryLineageRecord,
    MemoryRuntimeTier,
    QueryBudget,
    BudgetPolicyConfig,
    WorkingSet,
    WorkingSetEntry,
    WorkingSetPolicyConfig,
)
from .api import DeluxeMemoryRecord, DeluxeReadSnapshot, DeluxeServingSource

__all__ = [
    "BudgetPolicyConfig",
    "CapabilityCard",
    "CapabilityLifecycle",
    "CapabilityLifecycleConfig",
    "CapabilityState",
    "DeluxeArchitectureSnapshot",
    "DeluxeNodeDescriptor",
    "LineageEdge",
    "MemoryFault",
    "MemoryLineageRecord",
    "MemoryRuntimeTier",
    "QueryBudget",
    "WorkingSet",
    "WorkingSetEntry",
    "WorkingSetPolicyConfig",
    "DeluxeMemoryRecord",
    "DeluxeReadSnapshot",
    "DeluxeServingSource",
]
