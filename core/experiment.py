"""
core/experiment.py — Experiment System for KuroAgent

Provides a foundation for controlled experimentation:
  Problem
    ↓
  Solution A / Solution B / Solution C candidates
    ↓
  Evaluate against criteria (speed, tokens, correctness, verification)
    ↓
  Record & select winning approach

Clean abstraction designed for expansion.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class CandidateSolution:
    """Represents a candidate solution/approach to a problem."""
    name: str
    description: str
    handler: Optional[Callable[..., Dict[str, Any]]] = None
    prompt_variant: Optional[str] = None
    results: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    passed: bool = False
    duration_seconds: float = 0.0


@dataclass
class ExperimentReport:
    """Report summarizing an experiment across candidate solutions."""
    experiment_id: str
    problem_statement: str
    candidates: List[Dict[str, Any]]
    winner_name: Optional[str]
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "problem_statement": self.problem_statement,
            "candidates": self.candidates,
            "winner_name": self.winner_name,
            "created_at": self.created_at,
        }


class ExperimentRunner:
    """
    Executes and compares alternative solutions to a problem.
    """

    def run_experiment(
        self,
        experiment_id: str,
        problem_statement: str,
        candidates: List[CandidateSolution],
        evaluation_fn: Optional[Callable[[CandidateSolution], float]] = None,
    ) -> ExperimentReport:
        """
        Executes candidate solutions, evaluates them, and records the winner.
        """
        candidate_records = []
        best_score = -1.0
        winner_name = None

        for cand in candidates:
            start = time.time()
            try:
                if cand.handler:
                    res = cand.handler()
                    cand.results = res if isinstance(res, dict) else {"output": res}
                    cand.passed = res.get("success", True) if isinstance(res, dict) else True
                else:
                    cand.passed = True
            except Exception as e:
                cand.results = {"error": str(e)}
                cand.passed = False

            cand.duration_seconds = round(time.time() - start, 3)

            # Score candidate
            if evaluation_fn:
                cand.score = evaluation_fn(cand)
            else:
                # Default scoring: 100 if passed, penalty for duration
                cand.score = 100.0 if cand.passed else 0.0
                cand.score -= min(50.0, cand.duration_seconds * 5.0)

            if cand.score > best_score and cand.passed:
                best_score = cand.score
                winner_name = cand.name

            candidate_records.append({
                "name": cand.name,
                "description": cand.description,
                "passed": cand.passed,
                "score": cand.score,
                "duration_seconds": cand.duration_seconds,
                "results": cand.results,
            })

        report = ExperimentReport(
            experiment_id=experiment_id,
            problem_statement=problem_statement,
            candidates=candidate_records,
            winner_name=winner_name,
        )

        return report


# Global instance
experiment_runner = ExperimentRunner()
