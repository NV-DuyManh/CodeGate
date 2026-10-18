from types import SimpleNamespace

import pytest

from codegate.engines.policy.rules import evaluate_test_result
from codegate.engines.policy.schemas import PolicyConfig, PolicyDecision


def policy_config(**overrides):
    values = dict(
        quality_pass_threshold=80.0,
        quality_block_threshold=60.0,
        risk_warning_threshold=40.0,
        risk_block_threshold=70.0,
        max_critical_findings=0,
        max_high_security_findings=0,
        require_quality_score=False,
        require_risk_score=False,
        require_complete_quality=False,
        require_complete_risk=False,
    )
    return PolicyConfig(**(values | overrides))


@pytest.mark.parametrize("execution_status", ["PENDING", "RUNNING", "FAILED", "TIMEOUT", "UNKNOWN"])
@pytest.mark.parametrize("required", [False, True])
def test_incomplete_execution_never_passes_test_gate(execution_status, required):
    config = policy_config(test_gate_enabled=True, require_tests=required)
    run = SimpleNamespace(execution_status=execution_status, test_outcome="UNKNOWN")

    result = evaluate_test_result(config, run)

    assert result.status == (PolicyDecision.BLOCK if required else PolicyDecision.WARNING)
    assert result.actual_value != "Passed"


@pytest.mark.parametrize("outcome", ["TIMEOUT", "ERROR", "UNKNOWN", "SKIPPED"])
@pytest.mark.parametrize("required", [False, True])
def test_completed_execution_requires_explicit_success(outcome, required):
    config = policy_config(test_gate_enabled=True, require_tests=required)
    run = SimpleNamespace(execution_status="COMPLETED", test_outcome=outcome)

    result = evaluate_test_result(config, run)

    assert result.status == (PolicyDecision.BLOCK if required else PolicyDecision.WARNING)


def test_completed_failure_blocks_even_when_tests_optional():
    config = policy_config(test_gate_enabled=True, require_tests=False)
    run = SimpleNamespace(execution_status="COMPLETED", test_outcome="FAILED", tests_failed=1, tests_errors=0)

    result = evaluate_test_result(config, run)

    assert result.status == PolicyDecision.BLOCK


def test_completed_success_passes_enabled_gate():
    config = policy_config(test_gate_enabled=True, require_tests=True)
    run = SimpleNamespace(execution_status="COMPLETED", test_outcome="PASSED")

    assert evaluate_test_result(config, run).status == PolicyDecision.PASS


def test_disabled_gate_does_not_add_a_rule_for_an_incomplete_run():
    assert evaluate_test_result(policy_config(test_gate_enabled=False), None) is None
