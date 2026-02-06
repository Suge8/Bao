use bao_storage::compute_task_next_run_at;

#[test]
fn compute_task_next_run_once_should_use_run_at_or_now() {
    let from_run_at = compute_task_next_run_at("once", Some(123), None, None, None, 10);
    assert_eq!(from_run_at, Some(123));

    let fallback_now = compute_task_next_run_at("once", None, None, None, None, 10);
    assert_eq!(fallback_now, Some(10));
}

#[test]
fn compute_task_next_run_interval_should_use_now_plus_interval() {
    let next = compute_task_next_run_at("interval", None, Some(5_000), None, None, 10);
    assert_eq!(next, Some(15));
}

#[test]
fn compute_task_next_run_cron_should_use_next_tick() {
    let next = compute_task_next_run_at("cron", None, None, Some("0 * * * * *"), None, 10);
    assert_eq!(next, Some(60));
}
