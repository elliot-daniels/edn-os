"""Independent deterministic reviewer contract and baseline checks."""

from __future__ import annotations

from typing import Protocol

from edn.development.models import (
    DevelopmentTask,
    ReviewDisposition,
    ReviewFinding,
    ReviewResult,
    ValidationResult,
)


class DevelopmentReviewer(Protocol):
    def review(
        self, task: DevelopmentTask, validation: ValidationResult
    ) -> ReviewResult: ...


class BaselineReviewer:
    def review(
        self, task: DevelopmentTask, validation: ValidationResult
    ) -> ReviewResult:
        if not validation.passed:
            return ReviewResult(
                tuple(
                    ReviewFinding(
                        "validation_failure",
                        failure,
                        ReviewDisposition.REPAIR,
                    )
                    for failure in validation.failures
                )
            )
        if not task.required_tests:
            return ReviewResult(
                (
                    ReviewFinding(
                        "tests_missing",
                        "Task declares no required tests.",
                        ReviewDisposition.OWNER_REQUIRED,
                    ),
                )
            )
        return ReviewResult()
