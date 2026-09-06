from __future__ import annotations

from dataclasses import dataclass

from research_platform.environment.minecraft.api import (
    MinecraftBranchRuntimeRequest,
    MinecraftEnvironmentSpec,
    MinecraftServerSpec,
    MinecraftWorldBranch,
)
from research_platform.resource.allocation.api import EndpointAllocationRequest
from research_platform.scope.api import PLATFORM_SCOPE, ScopeIdentity, ScopeKind

from projects.sem_paper.method.self_evolving_memory.evolution import BranchRole, CandidateArchitecture

from .minecraft_binding import SemPaperBranchRuntimeRequestFactoryPort


@dataclass(frozen=True, slots=True)
class SemPaperMinecraftHostInputs:
    """Host-composed immutable inputs for Paper branch runtime requests."""

    environment_template: MinecraftEnvironmentSpec
    server_template: MinecraftServerSpec
    server_candidate_ports: tuple[int, ...]
    rcon_candidate_ports: tuple[int, ...] = ()
    owner_scope: ScopeIdentity = PLATFORM_SCOPE

    def __post_init__(self) -> None:
        if not self.server_candidate_ports:
            raise ValueError("Paper host inputs require explicit server port candidates")
        if len(set(self.server_candidate_ports)) != len(self.server_candidate_ports):
            raise ValueError("Paper server port candidates must be unique")
        if any(not 1 <= port <= 65535 for port in self.server_candidate_ports):
            raise ValueError("Paper server port candidates must be valid TCP ports")
        if self.server_template.rcon_endpoint is not None and not self.rcon_candidate_ports:
            raise ValueError("Paper RCON-enabled host inputs require explicit RCON port candidates")
        if len(set(self.rcon_candidate_ports)) != len(self.rcon_candidate_ports):
            raise ValueError("Paper RCON port candidates must be unique")
        if any(not 1 <= port <= 65535 for port in self.rcon_candidate_ports):
            raise ValueError("Paper RCON port candidates must be valid TCP ports")


class SemPaperMinecraftBranchRequestFactory(SemPaperBranchRuntimeRequestFactoryPort):
    """Create branch requests from host inputs without allocating resources itself."""

    def __init__(self, inputs: SemPaperMinecraftHostInputs) -> None:
        self.inputs = inputs

    def build(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        branch: MinecraftWorldBranch,
    ) -> MinecraftBranchRuntimeRequest:
        if role is BranchRole.CONTROL and candidate is not None:
            raise ValueError("control branch request received a candidate")
        if role is BranchRole.CANDIDATE and candidate is None:
            raise ValueError("candidate branch request has no candidate")
        holder = ScopeIdentity(ScopeKind.BRANCH, branch.branch_id)
        prefix = f"sem-paper:{role.value}:{branch.branch_id}"
        server_allocation = EndpointAllocationRequest(
            allocation_id=f"{prefix}:server-endpoint",
            holder_scope=holder,
            purpose=f"Minecraft {role.value} branch server endpoint",
            host=self.inputs.server_template.host,
            candidate_ports=self.inputs.server_candidate_ports,
            owner_scope=self.inputs.owner_scope,
        )
        rcon_allocation = None
        if self.inputs.server_template.rcon_endpoint is not None:
            rcon_allocation = EndpointAllocationRequest(
                allocation_id=f"{prefix}:rcon-endpoint",
                holder_scope=holder,
                purpose=f"Minecraft {role.value} branch RCON endpoint",
                host=self.inputs.server_template.rcon_endpoint.host,
                candidate_ports=self.inputs.rcon_candidate_ports,
                owner_scope=self.inputs.owner_scope,
            )
        return MinecraftBranchRuntimeRequest(
            branch=branch,
            endpoint_allocation=server_allocation,
            environment_template=self.inputs.environment_template,
            server_template=self.inputs.server_template,
            session_id=f"{prefix}:environment-session",
            rcon_endpoint_allocation=rcon_allocation,
        )


__all__ = ["SemPaperMinecraftBranchRequestFactory", "SemPaperMinecraftHostInputs"]
