from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from edn.development import (
    AuthorityOutcome,
    DevelopmentAuthorityPolicy,
    GitCheckpointRequest,
)


def _policy() -> DevelopmentAuthorityPolicy:
    root = Path(__file__).parents[2]
    return DevelopmentAuthorityPolicy.load(
        root / "config/development-authority-policy.json"
    )


def _request() -> GitCheckpointRequest:
    return GitCheckpointRequest(
        branch="feature/intelligence-core-v0.1",
        upstream_remote="origin",
        upstream_branch="feature/intelligence-core-v0.1",
        target_remote="origin",
        target_branch="feature/intelligence-core-v0.1",
        operations=("stage", "commit", "push"),
        completed_reviewed_increment=True,
        increment_only_changes=True,
        validation_passed=True,
        commit_message_matches_increment=True,
        hooks_and_validation_enabled=True,
        contains_no_secrets_protected_data_or_live_evidence=True,
        audit_state_recording_planned=True,
        verify_head_equals_upstream_after_push=True,
    )


def test_validated_current_feature_upstream_checkpoint_is_routine_authority() -> None:
    policy = _policy()

    decision = policy.evaluate_git_checkpoint(_request())

    assert decision.outcome is AuthorityOutcome.ALLOWED
    assert decision.reason_code == "validated_feature_checkpoint"
    assert (
        policy.evaluate(
            (
                "git.stage.validated_increment",
                "git.commit.validated_increment",
                "git.push.current_upstream",
            )
        ).outcome
        is AuthorityOutcome.ALLOWED
    )
    assert policy.git_checkpoint is not None
    assert policy.git_checkpoint.required_record_fields == (
        "task_id",
        "commit_hash",
        "commit_message",
        "branch",
        "upstream",
        "validation_evidence",
        "pushed_at",
        "local_head_equals_upstream",
    )


@pytest.mark.parametrize(
    "operation",
    (
        "branch-delete",
        "bypass-hooks",
        "bypass-validation",
        "commit-amend-pushed",
        "destructive-reset",
        "force-push",
        "force-with-lease",
        "history-rewrite",
        "merge",
        "push-different-remote",
        "rebase",
        "remote-change",
        "tag-create",
        "tag-delete",
        "upstream-change",
    ),
)
def test_dangerous_git_operations_are_permanently_prohibited(operation: str) -> None:
    decision = _policy().evaluate_git_checkpoint(
        replace(_request(), operations=("stage", operation))
    )

    assert decision.outcome is AuthorityOutcome.PROHIBITED
    assert decision.reason_code == "git_operation_prohibited"


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        (
            {"branch": "main", "upstream_branch": "main", "target_branch": "main"},
            "git_branch_not_authorised",
        ),
        (
            {
                "branch": "master",
                "upstream_branch": "master",
                "target_branch": "master",
            },
            "git_branch_not_authorised",
        ),
        (
            {
                "branch": "release/v1",
                "upstream_branch": "release/v1",
                "target_branch": "release/v1",
            },
            "git_branch_not_authorised",
        ),
        (
            {
                "branch": "protected/test",
                "upstream_branch": "protected/test",
                "target_branch": "protected/test",
            },
            "git_branch_not_authorised",
        ),
        (
            {
                "branch": "topic/test",
                "upstream_branch": "topic/test",
                "target_branch": "topic/test",
            },
            "git_branch_not_authorised",
        ),
        ({"target_remote": "fork"}, "git_upstream_mismatch"),
        ({"upstream_remote": "fork", "target_remote": "fork"}, "git_upstream_mismatch"),
        ({"target_branch": "feature/other"}, "git_upstream_mismatch"),
        ({"upstream_branch": "feature/other"}, "git_upstream_mismatch"),
    ),
)
def test_only_current_nonprotected_feature_branch_existing_origin_upstream_is_allowed(
    changes: dict[str, object], reason: str
) -> None:
    decision = _policy().evaluate_git_checkpoint(replace(_request(), **changes))

    assert decision.outcome is AuthorityOutcome.PROHIBITED
    assert decision.reason_code == reason


@pytest.mark.parametrize(
    "field",
    (
        "completed_reviewed_increment",
        "increment_only_changes",
        "validation_passed",
        "commit_message_matches_increment",
        "hooks_and_validation_enabled",
        "contains_no_secrets_protected_data_or_live_evidence",
        "audit_state_recording_planned",
        "verify_head_equals_upstream_after_push",
    ),
)
def test_every_checkpoint_precondition_is_mandatory(field: str) -> None:
    decision = _policy().evaluate_git_checkpoint(replace(_request(), **{field: False}))

    assert decision.outcome is AuthorityOutcome.PROHIBITED
    assert decision.reason_code == "git_checkpoint_precondition_failed"


def test_policy_action_vocabulary_permanently_prohibits_git_boundaries() -> None:
    policy = _policy()
    prohibited = (
        "git.push.force",
        "git.push.force_with_lease",
        "git.merge",
        "git.rebase",
        "git.branch.delete",
        "git.tag.delete",
        "git.history.rewrite",
        "git.remote.change",
        "git.upstream.change",
        "git.hooks.bypass",
        "git.validation.bypass",
        "git.secret_or_protected_data.commit",
        "git.destructive_recovery",
    )

    assert policy.evaluate(prohibited).outcome is AuthorityOutcome.PROHIBITED
