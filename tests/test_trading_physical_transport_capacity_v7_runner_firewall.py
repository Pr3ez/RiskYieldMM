from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from riskyieldmm.trading import (
    physical_transport_capacity_measurement_v49f as measurement,
)
from riskyieldmm.trading import physical_transport_capacity_sampler_v49f as sampler
from riskyieldmm.trading.canonical import CanonicalizationError


class _InjectedAssemblyFailure(RuntimeError):
    pass


class _RecordingCampaign:
    def __init__(self) -> None:
        self.completed: list[dict[str, Any]] = []
        self.latched: list[dict[str, Any]] = []

    def _complete_operation_v49f(self, **values: Any) -> None:
        self.completed.append(values)

    def _mark_unpublishable_v49f(self, **values: Any) -> None:
        self.latched.append(values)


def _firewall_runner(campaign: Any) -> Any:
    runner = object.__new__(sampler.CapacityMeasurementSessionRunnerV49FV7)
    runner._campaign = campaign  # noqa: SLF001
    runner._runner_authority = object()  # noqa: SLF001
    runner._runs = []  # noqa: SLF001
    runner._samples_artifact_byte_count = 0  # noqa: SLF001
    return runner


@pytest.mark.parametrize(
    "failure_point",
    ("observation", "sample", "serialization", "sample_run"),
)
def test_post_terminal_assembly_firewall_consumes_prefix_and_latches(
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    campaign = _RecordingCampaign()
    runner = _firewall_runner(campaign)
    declaration = object()
    prefix = object()
    failure = _InjectedAssemblyFailure(failure_point)

    def observation_factory() -> object:
        return object()

    if failure_point == "observation":

        def observation_factory() -> Any:
            raise failure

    elif failure_point == "sample":

        def fail_sample(**_: Any) -> Any:
            raise failure

        monkeypatch.setattr(
            sampler,
            "_capacity_measurement_v7_sample_from_prefix",
            fail_sample,
        )
    else:
        sample = SimpleNamespace(
            terminal=SimpleNamespace(surfaced_exception_class=None)
        )
        monkeypatch.setattr(
            sampler,
            "_capacity_measurement_v7_sample_from_prefix",
            lambda **_: sample,
        )
        if failure_point == "serialization":

            def fail_serialization(_: Any) -> int:
                raise failure

            runner._sample_artifact_byte_count = fail_serialization  # noqa: SLF001
        else:
            runner._sample_artifact_byte_count = lambda _: 1  # noqa: SLF001

            def fail_sample_run(**_: Any) -> Any:
                raise failure

            monkeypatch.setattr(
                sampler,
                "CapacityMeasurementSampleRunV49FV7",
                fail_sample_run,
            )

    with pytest.raises(_InjectedAssemblyFailure) as raised:
        runner._assemble_and_record_prefix(  # noqa: SLF001
            declaration=declaration,
            prefix=prefix,
            observation_factory=observation_factory,
        )
    assert raised.value is failure
    assert len(campaign.completed) == 1
    assert campaign.completed[0] == {
        "declaration": declaration,
        "prefix": prefix,
        "sample": None,
        "runner_authority": runner._runner_authority,  # noqa: SLF001
    }
    assert len(campaign.latched) == 1
    assert campaign.latched[0]["runner_authority"] is runner._runner_authority  # noqa: SLF001
    assert runner._runs == []  # noqa: SLF001


@pytest.mark.parametrize(
    "primary",
    (
        asyncio.CancelledError(),
        KeyboardInterrupt(),
        SystemExit(7),
        RuntimeError("target operation failed"),
    ),
)
def test_target_exception_identity_survives_post_terminal_assembly_failure(
    primary: BaseException,
) -> None:
    class _Campaign:
        @staticmethod
        def has_next_operation_v49f(**_: Any) -> bool:
            return True

    class _Authorization:
        committed_attempt_id = "attempt-id"

    class _Runtime:
        @staticmethod
        def issue_capacity_measurement_ingress_authorization_v49f_v7(
            **_: Any,
        ) -> tuple[object, _Authorization]:
            return object(), _Authorization()

        @staticmethod
        async def process_next_ingress_for_capacity_measurement_v49f(
            **_: Any,
        ) -> Any:
            raise primary

        @staticmethod
        def load_capacity_measurement_operation_prefix_v49f_v7(**_: Any) -> object:
            return object()

    runner = _firewall_runner(_Campaign())
    runner._runtime = _Runtime()  # noqa: SLF001

    async def no_currentness() -> None:
        return None

    async def before() -> tuple[object, object, object, object]:
        return object(), object(), object(), object()

    assembly = _InjectedAssemblyFailure("post-terminal assembly")

    def fail_assembly(**_: Any) -> Any:
        raise assembly

    runner._ensure_initial_currentness = no_currentness  # noqa: SLF001
    runner._assert_next_sample_capacity = lambda: None  # noqa: SLF001
    runner._before_observations = before  # noqa: SLF001
    runner._assemble_and_record_prefix = fail_assembly  # noqa: SLF001

    async def scenario() -> None:
        with pytest.raises(type(primary)) as raised:
            await runner.run_next_ingress()
        assert raised.value is primary
        assert any(
            "exception-prefix sample assembly failed" in note
            for note in getattr(primary, "__notes__", ())
        )

    asyncio.run(scenario())


def test_closed_context_latch_failure_cannot_mask_primary() -> None:
    class _ClosedCampaign:
        @staticmethod
        def _mark_unpublishable_v49f(**_: Any) -> None:
            raise CanonicalizationError("campaign is closed")

    runner = _firewall_runner(_ClosedCampaign())
    primary = KeyboardInterrupt()
    runner._try_latch_unpublishable(primary=primary)  # noqa: SLF001
    assert any(
        "campaign latch failed" in note for note in getattr(primary, "__notes__", ())
    )


@pytest.mark.parametrize("terminal_state", ("COMPLETE", "FATAL_PREFIX"))
def test_post_terminal_run_next_rejects_without_destroying_artifact(
    terminal_state: str,
) -> None:
    class _EndedCampaign:
        artifact_eligible = True

        @staticmethod
        def has_next_operation_v49f(**_: Any) -> bool:
            return False

        @staticmethod
        def _mark_unpublishable_v49f(**_: Any) -> None:
            raise AssertionError("post-terminal rejection must not latch")

    campaign = _EndedCampaign()
    runner = _firewall_runner(campaign)
    runner._runtime = object()  # noqa: SLF001

    async def scenario() -> None:
        with pytest.raises(
            sampler.CapacityMeasurementSamplerErrorV49F,
            match="no admissible next operation",
        ):
            await runner.run_next_ingress()

    asyncio.run(scenario())
    assert terminal_state in {"COMPLETE", "FATAL_PREFIX"}
    assert campaign.artifact_eligible is True


def test_run_campaign_finalizes_a_previously_recorded_run_ending_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Campaign:
        @staticmethod
        async def assert_current() -> None:
            return None

    runner = _firewall_runner(_Campaign())
    runner._runtime = object()  # noqa: SLF001
    runner._manifest = SimpleNamespace(lifecycle_contract=object())  # noqa: SLF001
    runner._final_bundle = None  # noqa: SLF001
    terminal = object()
    runner._runs = [  # noqa: SLF001
        SimpleNamespace(sample=SimpleNamespace(terminal=terminal))
    ]
    monkeypatch.setattr(
        measurement,
        "_expected_schedule_v49f_v7",
        lambda _: tuple(range(5)),
    )
    monkeypatch.setattr(
        measurement,
        "_terminal_is_run_ending_v49f_v7",
        lambda candidate, **_: candidate is terminal,
    )
    bundle = object()
    monkeypatch.setattr(
        sampler,
        "build_provisional_capacity_measurement_bundle_v49f_v7",
        lambda **_: bundle,
    )

    async def scenario() -> None:
        assert await runner.run_campaign() is bundle
        assert await runner.run_campaign() is bundle

    asyncio.run(scenario())
