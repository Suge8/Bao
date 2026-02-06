use std::io::Write;
use std::process::{Command, Stdio};

use serde_json::{json, Value};

fn run_hook(bin_name: &str, method: &str, params: Value) -> Value {
    let mut cmd = match bin_name {
        "bao-memory-hook" => command_for_bin(
            option_env!("CARGO_BIN_EXE_bao-memory-hook"),
            "bao-memory-hook",
        ),
        "bao-corrector-hook" => command_for_bin(
            option_env!("CARGO_BIN_EXE_bao-corrector-hook"),
            "bao-corrector-hook",
        ),
        other => panic!("unsupported hook bin: {other}"),
    };

    let mut child = cmd
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn hook process");

    let request = json!({
        "jsonrpc": "2.0",
        "id": "1",
        "method": method,
        "params": params,
    })
    .to_string();

    {
        let stdin = child.stdin.as_mut().expect("stdin");
        stdin
            .write_all(format!("{request}\n").as_bytes())
            .expect("write request");
    }

    let output = child.wait_with_output().expect("wait hook process");
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        output.status.success(),
        "hook exit failed\nstdout: {}\nstderr: {}",
        stdout,
        stderr
    );

    for line in stdout.lines().map(str::trim).filter(|line| !line.is_empty()) {
        let parsed: Value = match serde_json::from_str(line) {
            Ok(v) => v,
            Err(_) => continue,
        };

        if parsed.get("jsonrpc").and_then(Value::as_str) != Some("2.0") {
            continue;
        }

        if let Some(err) = parsed.get("error") {
            panic!("json-rpc call failed: {err}");
        }

        if let Some(result) = parsed.get("result") {
            return result.clone();
        }
    }

    panic!("missing json-rpc result, stdout: {stdout}");
}

fn command_for_bin(bin_path: Option<&'static str>, bin_name: &str) -> Command {
    if let Some(path) = bin_path {
        return Command::new(path);
    }

    let mut cmd = Command::new("cargo");
    cmd.args([
        "run",
        "-q",
        "-p",
        "bao-dimsum-process",
        "--bin",
        bin_name,
        "--",
    ]);
    cmd
}

#[test]
fn memory_extract_should_emit_mutation_for_remember_intent() {
    let result = run_hook(
        "bao-memory-hook",
        "memory.extract",
        json!({
            "sessionId": "s1",
            "userInput": "请记住我喜欢乌龙茶",
            "assistantOutput": "好的，我记住了",
            "toolTriggered": false,
            "toolOk": true
        }),
    );

    let plan_id = result
        .get("planId")
        .and_then(Value::as_str)
        .expect("planId should exist");
    assert!(plan_id.starts_with("plan_"));

    let mutations = result
        .get("mutations")
        .and_then(Value::as_array)
        .expect("mutations array");
    assert_eq!(mutations.len(), 1);
    assert_eq!(mutations[0].get("op"), Some(&json!("UPSERT")));
}

#[test]
fn corrector_validate_and_retry_should_return_expected_shape() {
    let validate_result = run_hook(
        "bao-corrector-hook",
        "corrector.validate_tool_result",
        json!({
            "ok": false,
            "error": "command failed"
        }),
    );
    assert_eq!(validate_result.get("ok"), Some(&json!(false)));
    assert!(validate_result.get("error").and_then(Value::as_str).is_some());

    let retry_result = run_hook(
        "bao-corrector-hook",
        "corrector.decide_retry",
        json!({
            "attempt": 1,
            "maxAttempts": 2,
            "toolOk": false,
            "validationOk": false
        }),
    );

    assert_eq!(retry_result.get("shouldRetry"), Some(&json!(true)));
    assert_eq!(retry_result.get("reason"), Some(&json!("tool_and_validation_failed")));
}

#[test]
fn methods_should_expose_new_pipeline_hooks() {
    let memory_methods = run_hook("bao-memory-hook", "memory.methods", json!({}));
    let memory_names: Vec<String> = memory_methods
        .get("methods")
        .and_then(Value::as_array)
        .expect("memory methods array")
        .iter()
        .filter_map(|v| v.get("method").and_then(Value::as_str))
        .map(str::to_string)
        .collect();
    assert!(memory_names.iter().any(|m| m == "memory.inject"));
    assert!(memory_names.iter().any(|m| m == "memory.extract"));

    let corrector_methods = run_hook("bao-corrector-hook", "corrector.methods", json!({}));
    let corrector_names: Vec<String> = corrector_methods
        .get("methods")
        .and_then(Value::as_array)
        .expect("corrector methods array")
        .iter()
        .filter_map(|v| v.get("method").and_then(Value::as_str))
        .map(str::to_string)
        .collect();

    assert!(
        corrector_names
            .iter()
            .any(|m| m == "corrector.validate_tool_args")
    );
    assert!(
        corrector_names
            .iter()
            .any(|m| m == "corrector.validate_tool_result")
    );
    assert!(
        corrector_names
            .iter()
            .any(|m| m == "corrector.decide_retry")
    );
}
