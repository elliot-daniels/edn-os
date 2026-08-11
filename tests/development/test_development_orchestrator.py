from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from edn.development import (
    AgentResult,
    AutonomousDevelopmentOrchestrator,
    BaselineReviewer,
    DevelopmentAuthorityPolicy,
    DevelopmentRoadmap,
    DevelopmentState,
    DevelopmentStateStore,
    DevelopmentTask,
    DevelopmentTaskStatus,
    InMemoryDevelopmentAudit,
    RepositorySnapshot,
    ReviewDisposition,
    ReviewFinding,
    ReviewResult,
    RunLimits,
    ValidationResult,
)
from edn.development import (
    TestStatus as DevelopmentTestStatus,
)

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)


def _task(
    identifier: str,
    *,
    actions: tuple[str, ...] = ("code.development.write",),
    prerequisites: tuple[str, ...] = (),
    status: DevelopmentTaskStatus = DevelopmentTaskStatus.PENDING,
) -> DevelopmentTask:
    return DevelopmentTask(
        identifier,
        f"Implement {identifier}",
        prerequisites,
        actions,
        "low",
        ("src/edn/development",),
        ("Acceptance passes",),
        ("python -m pytest",),
        ("authority ambiguity",),
        (),
        status,
    )


def _state(*, next_task: str | None = "TASK-1") -> DevelopmentState:
    return DevelopmentState(
        "1.0.0",
        "Synthetic Core",
        "0.1.0",
        "feature/test",
        "Synthetic milestone",
        (),
        None,
        (),
        (),
        (),
        DevelopmentTestStatus("passed", ("pytest",), 1, 0, NOW),
        "clean",
        (),
        "a" * 40,
        next_task,
        (),
        (),
        ("docs/architecture.md",),
        NOW,
        "synthetic-test",
    )


def _policy() -> DevelopmentAuthorityPolicy:
    return DevelopmentAuthorityPolicy(
        "test-policy",
        "1",
        frozenset({"code.development.write", "test.development.write"}),
        frozenset({"external.permission.new", "architecture.material_change"}),
        frozenset({"production.deploy"}),
    )


class StaticRepository:
    def __init__(self, dirty: tuple[str, ...] = ()) -> None:
        self.dirty = dirty

    def snapshot(self) -> RepositorySnapshot:
        return RepositorySnapshot("feature/test", "a" * 40, self.dirty)


class ScriptedAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def implement(self, task: DevelopmentTask, *, repair_cycle: int) -> AgentResult:
        self.calls.append((task.task_id, repair_cycle))
        return AgentResult(
            True,
            "Synthetic implementation complete.",
            ("src/edn/development/example.py",),
            f"feat(development): complete {task.task_id.lower()}",
        )


class SequencedValidator:
    def __init__(self, results: list[ValidationResult]) -> None:
        self.results = results

    def validate(self, task: DevelopmentTask) -> ValidationResult:
        del task
        return self.results.pop(0)


class MaterialChangeReviewer:
    def review(
        self, task: DevelopmentTask, validation: ValidationResult
    ) -> ReviewResult:
        del task, validation
        return ReviewResult(
            (
                ReviewFinding(
                    "architecture.material_change",
                    "Proposed work changes the approved architecture.",
                    ReviewDisposition.OWNER_REQUIRED,
                ),
            )
        )


def _run(
    tmp_path: Path,
    roadmap: DevelopmentRoadmap,
    agent: ScriptedAgent,
    validator: SequencedValidator,
    *,
    reviewer: object = BaselineReviewer(),
) -> tuple[object, InMemoryDevelopmentAudit, DevelopmentStateStore]:
    state_store = DevelopmentStateStore(tmp_path / "state.json")
    state_store.save(_state(next_task=roadmap.tasks[0].task_id))
    audit = InMemoryDevelopmentAudit()
    orchestrator = AutonomousDevelopmentOrchestrator(
        state_store,
        roadmap,
        _policy(),
        StaticRepository(),
        agent,
        validator,
        reviewer,  # type: ignore[arg-type]
        audit,
        limits=RunLimits(max_tasks=1, max_repair_cycles=2),
    )
    return orchestrator.run(), audit, state_store


def test_routine_task_repairs_test_failure_without_owner(tmp_path: Path) -> None:
    task = _task("TASK-1")
    agent = ScriptedAgent()

    report, audit, state_store = _run(
        tmp_path,
        DevelopmentRoadmap("test", "1", (task,)),
        agent,
        SequencedValidator(
            [
                ValidationResult(False, ("synthetic failure",), failure_signature="F1"),
                ValidationResult(True, evidence=("pytest:passed",)),
            ]
        ),
    )

    assert report.completed_tasks == ("TASK-1",)
    assert agent.calls == [("TASK-1", 0), ("TASK-1", 1)]
    assert any(item.event_type == "repair_attempted" for item in audit.events)
    assert state_store.load().completed_increments == ("TASK-1",)


def test_new_external_permission_stops_for_owner(tmp_path: Path) -> None:
    task = _task("TASK-1", actions=("external.permission.new",))
    report, _, _ = _run(
        tmp_path,
        DevelopmentRoadmap("test", "1", (task,)),
        ScriptedAgent(),
        SequencedValidator([]),
    )

    assert report.stopped_reason == "owner_authority_required"
    assert report.escalation is not None
    assert report.escalation.minimum_authority == "external.permission.new"


def test_indeterminate_authority_fails_closed(tmp_path: Path) -> None:
    task = _task("TASK-1", actions=("unknown.action",))
    report, _, _ = _run(
        tmp_path,
        DevelopmentRoadmap("test", "1", (task,)),
        ScriptedAgent(),
        SequencedValidator([]),
    )

    assert report.stopped_reason == "owner_authority_required"
    assert report.escalation is not None
    assert "unknown.action" in report.escalation.minimum_authority


def test_material_architecture_finding_escalates(tmp_path: Path) -> None:
    task = _task("TASK-1")
    report, _, _ = _run(
        tmp_path,
        DevelopmentRoadmap("test", "1", (task,)),
        ScriptedAgent(),
        SequencedValidator([ValidationResult(True)]),
        reviewer=MaterialChangeReviewer(),
    )

    assert report.stopped_reason == "owner_authority_required"
    assert report.escalation is not None
    assert report.escalation.minimum_authority == "architecture.material_change"


def test_owner_blocked_task_allows_another_eligible_task(tmp_path: Path) -> None:
    blocked = _task("TASK-1", actions=("external.permission.new",))
    routine = _task("TASK-2")
    roadmap = DevelopmentRoadmap("test", "1", (blocked, routine))
    agent = ScriptedAgent()

    report, _, _ = _run(
        tmp_path,
        roadmap,
        agent,
        SequencedValidator([ValidationResult(True)]),
    )

    assert report.completed_tasks == ("TASK-2",)
    assert agent.calls == [("TASK-2", 0)]


def test_restart_reconstructs_state_and_roadmap_from_json(tmp_path: Path) -> None:
    state_store = DevelopmentStateStore(tmp_path / "state.json")
    state_store.save(_state())
    roadmap_path = tmp_path / "roadmap.json"
    roadmap_path.write_text(
        '{"roadmap_id":"test","version":"1","tasks":['
        + __import__("json").dumps(_task("TASK-1").to_dict())
        + "]}",
        encoding="utf-8",
    )

    reconstructed_state = DevelopmentStateStore(tmp_path / "state.json").load()
    reconstructed_roadmap = DevelopmentRoadmap.load(roadmap_path)

    assert reconstructed_state.product == "Synthetic Core"
    assert reconstructed_state.next_recommended_increment == "TASK-1"
    assert reconstructed_roadmap.task("TASK-1").objective == "Implement TASK-1"


def test_real_policy_state_and_roadmap_reconstruct_current_project() -> None:
    root = Path(__file__).parents[2]
    state = DevelopmentStateStore(
        root / "config/intelligence-core-development-state.json"
    ).load()
    roadmap = DevelopmentRoadmap.load(root / "config/intelligence-core-roadmap.json")
    policy = DevelopmentAuthorityPolicy.load(
        root / "config/development-authority-policy.json"
    )

    assert state.product == "EDN Intelligence Core"
    assert state.next_recommended_increment == "PA-006"
    assert roadmap.task("IC-009-LIVE").status is DevelopmentTaskStatus.BLOCKED
    assert roadmap.task("IC-012").status is DevelopmentTaskStatus.COMPLETED
    for task_id in ("PA-001", "PA-002", "PA-003", "PA-004"):
        assert roadmap.task(task_id).status is DevelopmentTaskStatus.COMPLETED
    assert roadmap.select_next(state, policy).task_id == "PA-006"
