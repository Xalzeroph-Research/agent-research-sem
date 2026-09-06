from __future__ import annotations
from dataclasses import dataclass
from .contracts import EvolutionEligibility

class AlwaysEligible:
    def check(self)->EvolutionEligibility: return EvolutionEligibility(True,"eligible")

@dataclass(frozen=True, slots=True)
class ExposureClock:
    architecture_exposures: int
    persistent_blocks: int
    tasks_since_adoption: int
    tasks_since_last_meta: int
    workload_shift: bool=False

    def __post_init__(self) -> None:
        values = (
            self.architecture_exposures,
            self.persistent_blocks,
            self.tasks_since_adoption,
            self.tasks_since_last_meta,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("evolution exposure clock counters must be non-negative integers")
        if not isinstance(self.workload_shift, bool):
            raise ValueError("evolution exposure workload_shift must be boolean")

@dataclass(frozen=True, slots=True)
class EligibilityPolicy:
    min_exposures: int=1
    min_persistent_blocks: int=2
    minimum_dwell_tasks: int=3
    refractory_tasks: int=2
    require_workload_shift: bool=False

    def __post_init__(self) -> None:
        values = (
            self.min_exposures,
            self.min_persistent_blocks,
            self.minimum_dwell_tasks,
            self.refractory_tasks,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("evolution eligibility thresholds must be non-negative integers")
        if not isinstance(self.require_workload_shift, bool):
            raise ValueError("evolution eligibility require_workload_shift must be boolean")

class DeterministicEligibility:
    """Mechanical scheduling only. It emits no structural edit hint."""
    def __init__(self,clock:ExposureClock,policy:EligibilityPolicy)->None: self.clock=clock; self.policy=policy
    def check(self)->EvolutionEligibility:
        c=self.clock; p=self.policy
        if c.architecture_exposures<p.min_exposures: return EvolutionEligibility(False,"insufficient_exposure")
        if c.persistent_blocks<p.min_persistent_blocks: return EvolutionEligibility(False,"insufficient_persistence")
        if c.tasks_since_adoption<p.minimum_dwell_tasks: return EvolutionEligibility(False,"minimum_dwell")
        if c.tasks_since_last_meta<p.refractory_tasks: return EvolutionEligibility(False,"refractory")
        if p.require_workload_shift and not c.workload_shift: return EvolutionEligibility(False,"no_workload_shift")
        return EvolutionEligibility(True,"eligible")
