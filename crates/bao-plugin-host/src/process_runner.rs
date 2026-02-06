use std::collections::{HashMap, HashSet};
use std::io::Read;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

#[cfg(unix)]
use std::os::unix::process::CommandExt;

use serde_json::{Map, Value};

use crate::{PluginHostError, ToolRunResult, ToolRunner};

#[derive(Clone, Default)]
pub struct ProcessToolRunner {
    killed_groups: Arc<Mutex<HashSet<String>>>,
    running_pids: Arc<Mutex<HashMap<String, u32>>>,
}

#[derive(Debug, Clone)]
struct CommandSpec {
    group: String,
    command: String,
    args: Vec<String>,
    cwd: Option<PathBuf>,
    env: Vec<(String, String)>,
    timeout_ms: u64,
    max_output_bytes: usize,
    stdin_text: Option<String>,
}

const DEFAULT_MAX_OUTPUT_BYTES: usize = 256 * 1024;
const MAX_OUTPUT_BYTES_FLOOR: usize = 256;
const MAX_OUTPUT_BYTES_CEIL: usize = 16 * 1024 * 1024;

#[derive(Debug, Clone)]
struct OutputLimitBreach {
    stream: &'static str,
    limit_bytes: usize,
    observed_bytes: usize,
}

fn plugin_error(code: &str, message: String, metadata: Option<Value>) -> PluginHostError {
    PluginHostError {
        code: code.to_string(),
        message,
        metadata,
    }
}

impl ProcessToolRunner {
    pub fn new() -> Self {
        Self::default()
    }

    #[cfg(unix)]
    fn kill_pid_group(pid: u32) {
        unsafe {
            libc::kill(-(pid as i32), libc::SIGKILL);
        }
    }

    #[cfg(windows)]
    fn kill_pid_group(pid: u32) {
        let _ = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }

    #[cfg(not(any(unix, windows)))]
    fn kill_pid_group(_pid: u32) {}

    fn parse_spec(
        &self,
        dimsum_id: &str,
        tool_name: &str,
        args: &Value,
    ) -> Result<CommandSpec, PluginHostError> {
        let obj = args.as_object().ok_or_else(|| PluginHostError {
            code: "invalid_args".to_string(),
            message: "tool args must be an object".to_string(),
            metadata: None,
        })?;

        let meta = obj
            .get("__bao")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_else(Map::new);

        let group = meta
            .get("killSwitchGroup")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned)
            .unwrap_or_else(|| format!("{}::{}", dimsum_id, tool_name));

        let timeout_ms = obj
            .get("timeoutMs")
            .and_then(Value::as_u64)
            .map(|v| v.clamp(50, 60_000))
            .unwrap_or(1_000);

        let max_output_bytes = obj
            .get("maxOutputBytes")
            .and_then(Value::as_u64)
            .map(|v| {
                let as_usize = usize::try_from(v).unwrap_or(MAX_OUTPUT_BYTES_CEIL);
                as_usize.clamp(MAX_OUTPUT_BYTES_FLOOR, MAX_OUTPUT_BYTES_CEIL)
            })
            .unwrap_or(DEFAULT_MAX_OUTPUT_BYTES);

        let command = obj
            .get("command")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .map(ToOwned::to_owned)
            .ok_or_else(|| PluginHostError {
                code: "invalid_args".to_string(),
                message: "tool args.command is required".to_string(),
                metadata: None,
            })?;

        let mut cmd_args = vec![];
        if let Some(raw_args) = obj.get("args") {
            let arr = raw_args.as_array().ok_or_else(|| PluginHostError {
                code: "invalid_args".to_string(),
                message: "tool args.args must be an array of strings".to_string(),
                metadata: None,
            })?;
            for item in arr {
                let s = item.as_str().ok_or_else(|| PluginHostError {
                    code: "invalid_args".to_string(),
                    message: "tool args.args must be an array of strings".to_string(),
                    metadata: None,
                })?;
                cmd_args.push(s.to_string());
            }
        }

        let cwd = obj.get("cwd").and_then(Value::as_str).map(PathBuf::from);

        let mut env = vec![];
        if let Some(raw_env) = obj.get("env") {
            let env_obj = raw_env.as_object().ok_or_else(|| PluginHostError {
                code: "invalid_args".to_string(),
                message: "tool args.env must be an object".to_string(),
                metadata: None,
            })?;
            for (k, v) in env_obj {
                let value = v.as_str().ok_or_else(|| PluginHostError {
                    code: "invalid_args".to_string(),
                    message: format!("tool args.env.{k} must be a string"),
                    metadata: None,
                })?;
                env.push((k.clone(), value.to_string()));
            }
        }

        let stdin_text = obj
            .get("stdin")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned);

        Ok(CommandSpec {
            group,
            command,
            args: cmd_args,
            cwd,
            env,
            timeout_ms,
            max_output_bytes,
            stdin_text,
        })
    }

    fn is_group_killed(&self, group: &str) -> bool {
        self.killed_groups
            .lock()
            .expect("killed_groups mutex poisoned")
            .contains(group)
    }

    fn clear_group_kill(&self, group: &str) {
        self.killed_groups
            .lock()
            .expect("killed_groups mutex poisoned")
            .remove(group);
    }

    fn register_running_pid(&self, group: &str, pid: u32) {
        self.running_pids
            .lock()
            .expect("running_pids mutex poisoned")
            .insert(group.to_string(), pid);
    }

    fn clear_running_pid(&self, group: &str) {
        self.running_pids
            .lock()
            .expect("running_pids mutex poisoned")
            .remove(group);
    }

    fn running_pid(&self, group: &str) -> Option<u32> {
        self.running_pids
            .lock()
            .expect("running_pids mutex poisoned")
            .get(group)
            .copied()
    }
}

impl ToolRunner for ProcessToolRunner {
    fn run_tool(
        &self,
        dimsum_id: &str,
        tool_name: &str,
        args: &Value,
    ) -> Result<ToolRunResult, PluginHostError> {
        let spec = self.parse_spec(dimsum_id, tool_name, args)?;
        if self.is_group_killed(&spec.group) {
            self.clear_group_kill(&spec.group);
            return Err(plugin_error(
                "killed",
                format!("killed by kill switch group '{}'", spec.group),
                Some(serde_json::json!({
                    "reason": "KILL_SWITCH_TRIGGERED",
                    "group": spec.group,
                })),
            ));
        }

        let started_at = Instant::now();
        let started_at_ms = now_unix_ms();

        let mut command = Command::new(&spec.command);
        command
            .args(&spec.args)
            .stdin(if spec.stdin_text.is_some() {
                Stdio::piped()
            } else {
                Stdio::null()
            })
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        if let Some(cwd) = spec.cwd.as_ref() {
            command.current_dir(cwd);
        }
        for (key, value) in &spec.env {
            command.env(key, value);
        }

        #[cfg(unix)]
        unsafe {
            command.pre_exec(|| {
                libc::setpgid(0, 0);
                Ok(())
            });
        }

        let mut child = command.spawn().map_err(|err| {
            plugin_error(
                "spawn_failed",
                format!("spawn failed for '{}': {err}", spec.command),
                None,
            )
        })?;

        let output_limit_breach = Arc::new(Mutex::new(None::<OutputLimitBreach>));
        let mut stdout_reader = spawn_pipe_reader(
            child.stdout.take(),
            "stdout",
            spec.max_output_bytes,
            Arc::clone(&output_limit_breach),
        );
        let mut stderr_reader = spawn_pipe_reader(
            child.stderr.take(),
            "stderr",
            spec.max_output_bytes,
            Arc::clone(&output_limit_breach),
        );

        let child_pid = child.id();
        self.register_running_pid(&spec.group, child_pid);

        if let Some(stdin_text) = spec.stdin_text {
            if let Some(mut stdin) = child.stdin.take() {
                use std::io::Write;
                if let Err(err) = stdin.write_all(stdin_text.as_bytes()) {
                    Self::kill_pid_group(child_pid);
                    let _ = child.kill();
                    let _ = child.wait();
                    let _ = join_pipe_reader(stdout_reader.take());
                    let _ = join_pipe_reader(stderr_reader.take());
                    self.clear_running_pid(&spec.group);
                    return Err(plugin_error(
                        "stdin_write_failed",
                        format!("stdin write failed: {err}"),
                        Some(serde_json::json!({
                            "group": spec.group,
                            "pid": child_pid,
                            "startedAtMs": started_at_ms,
                            "elapsedMs": started_at.elapsed().as_millis() as u64,
                        })),
                    ));
                }
            }
        }

        loop {
            if self.is_group_killed(&spec.group) {
                Self::kill_pid_group(child_pid);
                let _ = child.kill();
                let _ = child.wait();
                let _ = join_pipe_reader(stdout_reader.take());
                let _ = join_pipe_reader(stderr_reader.take());
                self.clear_running_pid(&spec.group);
                self.clear_group_kill(&spec.group);
                return Err(plugin_error(
                    "killed",
                    format!("killed by kill switch group '{}'", spec.group),
                    Some(serde_json::json!({
                        "reason": "KILL_SWITCH_TRIGGERED",
                        "group": spec.group,
                        "pid": child_pid,
                        "startedAtMs": started_at_ms,
                        "elapsedMs": started_at.elapsed().as_millis() as u64,
                    })),
                ));
            }

            if let Some(breach) = take_output_limit_breach(&output_limit_breach) {
                Self::kill_pid_group(child_pid);
                let _ = child.kill();
                let _ = child.wait();
                let _ = join_pipe_reader(stdout_reader.take());
                let _ = join_pipe_reader(stderr_reader.take());
                self.clear_running_pid(&spec.group);
                return Err(plugin_error(
                    "resource_exceeded",
                    format!(
                        "{stream} exceeded maxOutputBytes limit ({observed}>{limit})",
                        stream = breach.stream,
                        observed = breach.observed_bytes,
                        limit = breach.limit_bytes
                    ),
                    Some(serde_json::json!({
                        "reason": "OUTPUT_LIMIT_EXCEEDED",
                        "limitType": "output",
                        "stream": breach.stream,
                        "maxOutputBytes": breach.limit_bytes,
                        "observedBytes": breach.observed_bytes,
                        "group": spec.group,
                        "pid": child_pid,
                        "startedAtMs": started_at_ms,
                        "elapsedMs": started_at.elapsed().as_millis() as u64,
                    })),
                ));
            }

            if started_at.elapsed() > Duration::from_millis(spec.timeout_ms) {
                let elapsed_ms = started_at.elapsed().as_millis() as u64;
                Self::kill_pid_group(child_pid);
                let _ = child.kill();
                let _ = child.wait();
                let _ = join_pipe_reader(stdout_reader.take());
                let _ = join_pipe_reader(stderr_reader.take());
                self.clear_running_pid(&spec.group);
                return Err(plugin_error(
                    "timeout",
                    format!("tool execution timeout after {}ms", spec.timeout_ms),
                    Some(serde_json::json!({
                        "reason": "TIMEOUT_EXCEEDED",
                        "limitType": "time",
                        "timeoutMs": spec.timeout_ms,
                        "elapsedMs": elapsed_ms,
                        "group": spec.group,
                        "pid": child_pid,
                        "startedAtMs": started_at_ms,
                    })),
                ));
            }

            match child
                .try_wait()
                .map_err(|err| plugin_error("wait_failed", format!("wait failed: {err}"), None))?
            {
                Some(status) => {
                    self.clear_running_pid(&spec.group);
                    let elapsed_ms = started_at.elapsed().as_millis() as u64;
                    let finished_at_ms = now_unix_ms();
                    let stdout = join_pipe_reader(stdout_reader.take());
                    let stderr = join_pipe_reader(stderr_reader.take());
                    return Ok(ToolRunResult {
                        ok: status.success(),
                        output: serde_json::json!({
                            "dimsumId": dimsum_id,
                            "toolName": tool_name,
                            "group": spec.group,
                            "pid": child_pid,
                            "command": spec.command,
                            "args": spec.args,
                            "exitCode": status.code(),
                            "success": status.success(),
                            "startedAtMs": started_at_ms,
                            "finishedAtMs": finished_at_ms,
                            "durationMs": elapsed_ms,
                            "stdout": stdout,
                            "stderr": stderr,
                            "limits": {
                                "timeoutMs": spec.timeout_ms,
                                "maxOutputBytes": spec.max_output_bytes,
                            },
                        }),
                    });
                }
                None => thread::sleep(Duration::from_millis(20)),
            }
        }
    }

    fn kill_group(&self, group: &str) {
        self.killed_groups
            .lock()
            .expect("killed_groups mutex poisoned")
            .insert(group.to_string());

        if let Some(pid) = self.running_pid(group) {
            Self::kill_pid_group(pid);
        }
    }
}

fn now_unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

fn spawn_pipe_reader(
    pipe: Option<impl Read + Send + 'static>,
    stream_name: &'static str,
    max_output_bytes: usize,
    output_limit_breach: Arc<Mutex<Option<OutputLimitBreach>>>,
) -> Option<thread::JoinHandle<Vec<u8>>> {
    pipe.map(|mut pipe_stream| {
        thread::spawn(move || {
            let mut bytes = Vec::new();
            let mut chunk = [0_u8; 4096];
            let mut total = 0_usize;

            loop {
                let read = match pipe_stream.read(&mut chunk) {
                    Ok(0) => break,
                    Ok(n) => n,
                    Err(_) => break,
                };

                total = total.saturating_add(read);
                if total > max_output_bytes {
                    let mut guard = output_limit_breach
                        .lock()
                        .expect("output_limit_breach mutex poisoned");
                    if guard.is_none() {
                        *guard = Some(OutputLimitBreach {
                            stream: stream_name,
                            limit_bytes: max_output_bytes,
                            observed_bytes: total,
                        });
                    }
                    break;
                }

                bytes.extend_from_slice(&chunk[..read]);
            }

            bytes
        })
    })
}

fn take_output_limit_breach(
    output_limit_breach: &Arc<Mutex<Option<OutputLimitBreach>>>,
) -> Option<OutputLimitBreach> {
    output_limit_breach
        .lock()
        .expect("output_limit_breach mutex poisoned")
        .clone()
}

fn join_pipe_reader(reader: Option<thread::JoinHandle<Vec<u8>>>) -> String {
    let bytes = match reader {
        Some(handle) => handle.join().unwrap_or_default(),
        None => Vec::new(),
    };
    String::from_utf8_lossy(&bytes).to_string()
}
