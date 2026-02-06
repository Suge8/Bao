use std::thread;
use std::time::Duration;

use bao_plugin_host::{process_runner::ProcessToolRunner, ToolRunner};

#[test]
fn run_tool_captures_stdout_and_stderr() {
    let runner = ProcessToolRunner::new();
    let out = runner
        .run_tool("d1", "t1", &output_command_args())
        .expect("run tool");

    assert!(out.ok, "tool should succeed: {}", out.output);
    let stdout = out
        .output
        .get("stdout")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("");
    let stderr = out
        .output
        .get("stderr")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("");
    assert!(stdout.contains("bao-stdout"), "stdout missing: {stdout}");
    assert!(stderr.contains("bao-stderr"), "stderr missing: {stderr}");
    assert!(
        out.output
            .get("pid")
            .and_then(serde_json::Value::as_u64)
            .is_some(),
        "pid missing: {}",
        out.output
    );
    let started = out
        .output
        .get("startedAtMs")
        .and_then(serde_json::Value::as_u64)
        .expect("startedAtMs missing");
    let finished = out
        .output
        .get("finishedAtMs")
        .and_then(serde_json::Value::as_u64)
        .expect("finishedAtMs missing");
    assert!(finished >= started, "finishedAtMs should be >= startedAtMs");
    let process_tree = out
        .output
        .get("processTree")
        .and_then(serde_json::Value::as_object)
        .expect("processTree missing");
    assert!(
        process_tree
            .get("rootPid")
            .and_then(serde_json::Value::as_u64)
            .is_some(),
        "processTree.rootPid missing: {process_tree:?}"
    );
}

#[test]
fn run_tool_times_out() {
    let runner = ProcessToolRunner::new();
    let err = runner
        .run_tool("d1", "t-timeout", &timeout_command_args())
        .expect_err("should timeout");
    assert_eq!(err.code, "timeout");
    let metadata = err
        .metadata
        .as_ref()
        .and_then(serde_json::Value::as_object)
        .expect("timeout should include metadata");
    assert_eq!(
        metadata.get("reason").and_then(serde_json::Value::as_str),
        Some("TIMEOUT_EXCEEDED")
    );
    assert_eq!(
        metadata
            .get("limitType")
            .and_then(serde_json::Value::as_str),
        Some("time")
    );
    assert!(
        metadata
            .get("timeoutMs")
            .and_then(serde_json::Value::as_u64)
            .unwrap_or_default()
            >= 100
    );
    assert!(
        metadata
            .get("pid")
            .and_then(serde_json::Value::as_u64)
            .is_some(),
        "timeout metadata should include pid: {metadata:?}"
    );
    assert!(
        metadata
            .get("startedAtMs")
            .and_then(serde_json::Value::as_u64)
            .is_some(),
        "timeout metadata should include startedAtMs: {metadata:?}"
    );
    let process_tree = metadata
        .get("processTree")
        .and_then(serde_json::Value::as_object)
        .expect("timeout metadata should include processTree");
    assert!(
        process_tree
            .get("rootPid")
            .and_then(serde_json::Value::as_u64)
            .is_some(),
        "timeout processTree.rootPid missing: {process_tree:?}"
    );
}

#[test]
fn run_tool_rejects_oversized_stdout() {
    let runner = ProcessToolRunner::new();
    let err = runner
        .run_tool("d1", "t-over-stdout", &oversized_stdout_command_args())
        .expect_err("should reject oversized stdout");

    assert_eq!(err.code, "resource_exceeded");
    let metadata = err
        .metadata
        .as_ref()
        .and_then(serde_json::Value::as_object)
        .expect("resource exceeded should include metadata");
    assert_eq!(
        metadata.get("reason").and_then(serde_json::Value::as_str),
        Some("OUTPUT_LIMIT_EXCEEDED")
    );
    assert_eq!(
        metadata
            .get("limitType")
            .and_then(serde_json::Value::as_str),
        Some("output")
    );
    assert_eq!(
        metadata.get("stream").and_then(serde_json::Value::as_str),
        Some("stdout")
    );
}

#[test]
fn run_tool_rejects_oversized_stderr() {
    let runner = ProcessToolRunner::new();
    let err = runner
        .run_tool("d1", "t-over-stderr", &oversized_stderr_command_args())
        .expect_err("should reject oversized stderr");

    assert_eq!(err.code, "resource_exceeded");
    let metadata = err
        .metadata
        .as_ref()
        .and_then(serde_json::Value::as_object)
        .expect("resource exceeded should include metadata");
    assert_eq!(
        metadata.get("reason").and_then(serde_json::Value::as_str),
        Some("OUTPUT_LIMIT_EXCEEDED")
    );
    assert_eq!(
        metadata
            .get("limitType")
            .and_then(serde_json::Value::as_str),
        Some("output")
    );
    assert_eq!(
        metadata.get("stream").and_then(serde_json::Value::as_str),
        Some("stderr")
    );
}

#[test]
fn kill_group_interrupts_running_tool() {
    let runner = ProcessToolRunner::new();
    let killer = runner.clone();
    thread::spawn(move || {
        thread::sleep(Duration::from_millis(120));
        killer.kill_group("g-kill");
    });

    let err = runner
        .run_tool(
            "d1",
            "t-kill",
            &serde_json::json!({
                "__bao": { "killSwitchGroup": "g-kill" },
                "timeoutMs": 10_000,
                "command": long_sleep_command(),
                "args": long_sleep_args(),
            }),
        )
        .expect_err("should be killed");

    assert_eq!(err.code, "killed");
}

#[test]
fn run_tool_requires_command() {
    let runner = ProcessToolRunner::new();
    let err = runner
        .run_tool("d1", "t-invalid", &serde_json::json!({}))
        .expect_err("command required");
    assert_eq!(err.code, "invalid_args");
    assert!(err.message.contains("tool args.command is required"));
}

#[cfg(unix)]
fn output_command_args() -> serde_json::Value {
    serde_json::json!({
        "command": "sh",
        "args": ["-lc", "printf 'bao-stdout'; printf 'bao-stderr' 1>&2"],
        "timeoutMs": 2000,
    })
}

#[cfg(windows)]
fn output_command_args() -> serde_json::Value {
    serde_json::json!({
        "command": "cmd",
        "args": ["/C", "echo bao-stdout && echo bao-stderr 1>&2"],
        "timeoutMs": 2000,
    })
}

#[cfg(unix)]
fn timeout_command_args() -> serde_json::Value {
    serde_json::json!({
        "command": "sh",
        "args": ["-lc", "sleep 1"],
        "timeoutMs": 100,
    })
}

#[cfg(unix)]
fn oversized_stdout_command_args() -> serde_json::Value {
    serde_json::json!({
        "command": "sh",
        "args": ["-lc", "i=0; while [ $i -lt 2048 ]; do printf x; i=$((i+1)); done"],
        "timeoutMs": 2_000,
        "maxOutputBytes": 256,
    })
}

#[cfg(windows)]
fn oversized_stdout_command_args() -> serde_json::Value {
    serde_json::json!({
        "command": "powershell",
        "args": ["-NoProfile", "-Command", "[Console]::Out.Write(('x' * 2048))"],
        "timeoutMs": 2_000,
        "maxOutputBytes": 256,
    })
}

#[cfg(unix)]
fn oversized_stderr_command_args() -> serde_json::Value {
    serde_json::json!({
        "command": "sh",
        "args": ["-lc", "i=0; while [ $i -lt 2048 ]; do printf x 1>&2; i=$((i+1)); done"],
        "timeoutMs": 2_000,
        "maxOutputBytes": 256,
    })
}

#[cfg(windows)]
fn oversized_stderr_command_args() -> serde_json::Value {
    serde_json::json!({
        "command": "powershell",
        "args": ["-NoProfile", "-Command", "[Console]::Error.Write(('x' * 2048))"],
        "timeoutMs": 2_000,
        "maxOutputBytes": 256,
    })
}

#[cfg(windows)]
fn timeout_command_args() -> serde_json::Value {
    serde_json::json!({
        "command": "powershell",
        "args": ["-NoProfile", "-Command", "Start-Sleep -Seconds 1"],
        "timeoutMs": 100,
    })
}

#[cfg(unix)]
fn long_sleep_command() -> &'static str {
    "sh"
}

#[cfg(unix)]
fn long_sleep_args() -> Vec<&'static str> {
    vec!["-lc", "sleep 5"]
}

#[cfg(windows)]
fn long_sleep_command() -> &'static str {
    "powershell"
}

#[cfg(windows)]
fn long_sleep_args() -> Vec<&'static str> {
    vec!["-NoProfile", "-Command", "Start-Sleep -Seconds 5"]
}
