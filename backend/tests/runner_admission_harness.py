"""Trusted test-only bridge. No product import, RPC or receipt acceptance.

Every launch starts with independent DB admission. Ongoing private-capability
checks cannot be used as the public entry point for a second launch.
"""
from workforce.reviewed_runner_contract import canonical_manifest
from workforce.runner_admission import (RunnerAdmissionDenied, admit_runner_attempt,
                                         check_runner_authority)
from workforce.runner_fixture_job import job_code_digest
from runner_isolation_harness import run_job


def run_admitted_job(invocation_id, *, journal, experiment_enabled=False,
                     after_commit=None, after_create=None, after_job=None, result_key=None):
    admission = admit_runner_attempt(invocation_id, experiment_enabled=experiment_enabled,
                                     after_commit=after_commit)
    if admission.job_sha256 != job_code_digest():
        raise RunnerAdmissionDenied('Reviewed host job pin unavailable')
    def authorize(_stage, manifest):
        if canonical_manifest(manifest) != admission.manifest_raw:
            raise RunnerAdmissionDenied('Runner manifest substituted')
        return check_runner_authority(admission, experiment_enabled=experiment_enabled)
    receipt = run_job(admission.manifest_raw, expected_sha256=admission.manifest_sha256,
        image_id=admission.image_id, journal=journal, authorize=authorize,
        experiment_enabled=experiment_enabled, after_create=after_create, after_job=after_job)

    if result_key is None:
        return receipt
    # The host key is never part of job stdin/command/env/mounts. Signing is
    # transient metadata only and must not change the application's outcome.
    from workforce.runner_fixture_job import canonical_receipt
    from workforce.runner_result_contract import sign_runner_result
    check_runner_authority(admission, experiment_enabled=experiment_enabled)
    envelope = sign_runner_result(canonical_receipt(receipt), admission,
        key=result_key, experiment_enabled=experiment_enabled)
    check_runner_authority(admission, experiment_enabled=experiment_enabled)
    return admission, envelope
