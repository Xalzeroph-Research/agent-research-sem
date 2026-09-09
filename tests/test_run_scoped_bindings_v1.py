from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

from projects.sem_paper.composition import environment as environment_module


class _FakeBinding:
    def __init__(self, *, artifact_digest: str = "fake-digest") -> None:
        self.identity = SimpleNamespace(artifact_digest=artifact_digest)
        self.model_requests = object()
        self.close_count = 0
        self.bind_count = 0

    def bind(self, requirement: object) -> object:
        self.bind_count += 1
        return SimpleNamespace(requirement=requirement)

    def close(self) -> None:
        self.close_count += 1


def test_environment_binding_is_cached_and_closed_once() -> None:
    binding = _FakeBinding()
    with patch.object(
        environment_module,
        "bind_bundled_minecraft_environment",
        return_value=binding,
    ) as factory:
        environment = environment_module.RealMinecraftEnvironment("run-1")
        assert environment._ensure_environment_binding() is binding
        assert environment._ensure_environment_binding() is binding
        factory.assert_called_once()
        environment.close()
        environment.close()

    assert binding.close_count == 1


def test_model_planner_binding_is_cached_for_the_run() -> None:
    binding = _FakeBinding()
    planner = object()
    with patch.dict(
        os.environ,
        {
            "SEM_PLANNER_MODE": "model",
            "SEM_MODEL_QUALIFIED_CLOSURE": "/tmp/qualified-closure.json",
            "SEM_MODEL_REQUEST_ROOT": "/tmp/model-requests",
        },
        clear=False,
    ), patch.object(
        environment_module,
        "bind_qualified_project_model",
        return_value=binding,
    ) as factory, patch.object(
        environment_module,
        "planner_model_requirement",
        return_value="generation",
    ) as requirement, patch.object(
        environment_module,
        "ModelActionPlanner",
        return_value=planner,
    ) as planner_type:
        environment = environment_module.RealMinecraftEnvironment("run-2")
        assert environment._ensure_model_planner() is planner
        assert environment._ensure_model_planner() is planner
        environment.close()

    factory.assert_called_once()
    requirement.assert_called_once()
    planner_type.assert_called_once()
    assert binding.bind_count == 1
    assert binding.close_count == 1
