use std::collections::{HashMap, HashSet};
use std::io::Read;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

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
    stdin_text: Option<String>,
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

        let command = obj
            .get("command")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .map(ToOwned::to_owned)
            .ok_or_else(|| PluginHostError {
                code: "invalid_args".to_string(),
                message: "tool args.command is required".to_string(),
            })?;

        let mut cmd_args = vec![];
        if let Some(raw_args) = obj.get("args") {
            let arr = raw_args.as_array().ok_or_else(|| PluginHostError {
                code: "invalid_args".to_string(),
                message: "tool args.args must be an array of strings".to_string(),
            })?;
            for item in arr {
                let s = item.as_str().ok_or_else(|| PluginHostError {
                    code: "invalid_args".to_string(),
                    message: "tool args.args must be an array of strings".to_string(),
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
            })?;
            for (k, v) in env_obj {
                let value = v.as_str().ok_or_else(|| PluginHostError {
                    code: "invalid_args".to_string(),
                    message: format!("tool args.env.{k} must be a string"),
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
            return Err(PluginHostError {
                code: "killed".to_string(),
                message: format!("killed by kill switch group '{}'", spec.group),
            });
        }

        let started_at = Instant::now();

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

        let mut child = command.spawn().map_err(|err| PluginHostError {
            code: "spawn_failed".to_string(),
            message: format!("spawn failed for '{}': {err}", spec.command),
        })?;

        let mut stdout_reader = spawn_pipe_reader(child.stdout.take());
        let mut stderr_reader = spawn_pipe_reader(child.stderr.take());

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
                    return Err(PluginHostError {
                        code: "stdin_write_failed".to_string(),
                        message: format!("stdin write failed: {err}"),
                    });
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
                return Err(PluginHostError {
                    code: "killed".to_string(),
                    message: format!("killed by kill switch group '{}'", spec.group),
                });
            }

            if started_at.elapsed() > Duration::from_millis(spec.timeout_ms) {
                Self::kill_pid_group(child_pid);
                let _ = child.kill();
                let _ = child.wait();
                let _ = join_pipe_reader(stdout_reader.take());
                let _ = join_pipe_reader(stderr_reader.take());
                self.clear_running_pid(&spec.group);
                return Err(PluginHostError {
                    code: "timeout".to_string(),
                    message: format!("tool execution timeout after {}ms", spec.timeout_ms),
                });
            }

            match child.try_wait().map_err(|err| PluginHostError {
                code: "wait_failed".to_string(),
                message: format!("wait failed: {err}"),
            })? {
                Some(status) => {
                    self.clear_running_pid(&spec.group);
                    let elapsed_ms = started_at.elapsed().as_millis() as u64;
                    let stdout = join_pipe_reader(stdout_reader.take());
                    let stderr = join_pipe_reader(stderr_reader.take());
                    return Ok(ToolRunResult {
                        ok: status.success(),
                        output: serde_json::json!({
                            "dimsumId": dimsum_id,
                            "toolName": tool_name,
                            "group": spec.group,
                            "command": spec.command,
                            "args": spec.args,
                            "exitCode": status.code(),
                            "success": status.success(),
                            "durationMs": elapsed_ms,
                            "stdout": stdout,
                            "stderr": stderr,
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

fn spawn_pipe_reader(
    pipe: Option<impl Read + Send + 'static>,
) -> Option<thread::JoinHandle<Vec<u8>>> {
    pipe.map(|mut stream| {
        thread::spawn(move || {
            let mut bytes = Vec::new();
            let _ = stream.read_to_end(&mut bytes);
            bytes
        })
    })
}

fn join_pipe_reader(reader: Option<thread::JoinHandle<Vec<u8>>>) -> String {
    let bytes = match reader {
        Some(handle) => handle.join().unwrap_or_default(),
        None => Vec::new(),
    };
    String::from_utf8_lossy(&bytes).to_string()
}
