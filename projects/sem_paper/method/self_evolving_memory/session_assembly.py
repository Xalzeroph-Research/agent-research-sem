from __future__ import annotations

from dataclasses import dataclass

from research_platform.participant.method.api import (
    MethodObservationOutboxFactoryPort,
    MethodObservationSink,
    MethodRuntimeBinding,
)

from .evolution import TelemetryBook
from .session_state_api import SEMSessionStateFactory
from .session_context import SEMSessionContextTracker
from .session_evolution_api import SessionEvolutionFactory
from .session_evolution_api import EvolutionSessionBinding
from .session_evolution_runtime import CellSessionAdoptionAuthority, ReadOnlyEvolutionSessionSource
from .session_ingest import SEMSessionIngestor
from .session_lifecycle_view import SEMSessionLifecycleView
from .session_observation import SessionMutationObservationPublisher
from .session_persistence import SEMSessionPersistence
from .session_recall_api import SEMSessionRecallAPI
from .session_serving_api import SessionServingFactory
from .session_serving_api import DeluxeSnapshotFactory
from .session_serving import ReadOnlyDeluxeServingSessionSource, ReadOnlyServingSessionSource
from .session_task_api import SEMSessionTaskAPI
from .session_task_ports import CellTaskScientificMutationPort
from .task_coordination import SEMTaskCompletionCoordinator


@dataclass(frozen=True, slots=True)
class SEMSessionRuntime:
    ingest: SEMSessionIngestor
    serving: SEMSessionRecallAPI
    tasks: SEMSessionTaskAPI
    persistence: SEMSessionPersistence
    lifecycle: SEMSessionLifecycleView


class SEMSessionAssembly:
    """The single internal composition root for a SEM Method session."""

    def __init__(
        self,
        serving_factory: SessionServingFactory,
        evolution_factory: SessionEvolutionFactory,
        state_factory: SEMSessionStateFactory,
        observation_outbox_factory: MethodObservationOutboxFactoryPort,
        deluxe_snapshot_factory: DeluxeSnapshotFactory | None = None,
    ) -> None:
        self._serving_factory = serving_factory
        self._evolution_factory = evolution_factory
        self._state_factory = state_factory
        self._observation_outbox_factory = observation_outbox_factory
        self._deluxe_snapshot_factory = deluxe_snapshot_factory

    def build(
        self,
        session_id: str,
        observation_sink: MethodObservationSink,
        method_binding: MethodRuntimeBinding,
    ) -> SEMSessionRuntime:
        cell = self._state_factory.create(session_id)
        context = SEMSessionContextTracker()
        telemetry = TelemetryBook()
        serving_source = (
            ReadOnlyServingSessionSource(cell)
            if self._deluxe_snapshot_factory is None
            else ReadOnlyDeluxeServingSessionSource(cell, self._deluxe_snapshot_factory)
        )
        serving = SEMSessionRecallAPI(self._serving_factory(serving_source), telemetry)
        evolution = self._evolution_factory(EvolutionSessionBinding(
            ReadOnlyEvolutionSessionSource(cell, telemetry),
            CellSessionAdoptionAuthority(session_id, cell),
        ))
        observations = SessionMutationObservationPublisher(
            session_id,
            observation_sink,
            self._observation_outbox_factory,
        )
        tasks = SEMTaskCompletionCoordinator(
            CellTaskScientificMutationPort(cell),
            evolution,
            observations,
            telemetry,
        )
        persistence = SEMSessionPersistence(
            session_id,
            cell,
            observations,
            tasks,
            context,
            method_binding,
            telemetry,
            serving,
        )
        return SEMSessionRuntime(
            SEMSessionIngestor(cell, observations, context),
            serving,
            SEMSessionTaskAPI(tasks, context, cell.current_generation),
            persistence,
            SEMSessionLifecycleView(cell, observations, tasks, persistence, context),
        )


__all__ = ["SEMSessionAssembly", "SEMSessionRuntime"]
