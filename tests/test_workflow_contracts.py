from app.schemas.tenant import JobRetryRequest, ProvisionJobRequest, WorkerTickRequest


def test_provision_job_request_defaults_are_safe():
    payload = ProvisionJobRequest()
    assert payload.run_inline is True
    assert payload.verify_domains is True
    assert payload.dry_run is None
    assert payload.max_attempts == 3
    assert payload.simulate_failure_phase is None


def test_provision_job_request_accepts_idempotency_key():
    payload = ProvisionJobRequest(idempotency_key='demo-provision-v1', dry_run=True)
    assert payload.idempotency_key == 'demo-provision-v1'
    assert payload.dry_run is True


def test_provision_job_request_supports_mock_failure_injection():
    payload = ProvisionJobRequest(simulate_failure_phase='bind_upstream', max_attempts=2)
    assert payload.simulate_failure_phase == 'bind_upstream'
    assert payload.max_attempts == 2


def test_retry_request_defaults_clear_mock_failure():
    payload = JobRetryRequest()
    assert payload.run_inline is True
    assert payload.clear_simulated_failure is True
    assert payload.worker_id == 'mock-worker-retry'


def test_worker_tick_request_defaults_are_bounded():
    payload = WorkerTickRequest()
    assert payload.worker_id == 'mock-worker-tick'
    assert payload.limit == 5
