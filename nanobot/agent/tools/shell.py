"""Shell execution tool."""

import asyncio
import os
import re
from typing import Any

from nanobot.agent.tools.base import Tool


# List of potentially dangerous command patterns
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/',  # rm -rf /
    r':\(\)\{\s*:\|:&\s*\};:',  # fork bomb
    r'mkfs\.',  # format filesystem
    r'dd\s+if=.*\s+of=/dev/(sd|hd)',  # overwrite disk
    r'>\s*/dev/(sd|hd)',  # write to raw disk device
]


def _is_dangerous_command(command: str) -> tuple[bool, str | None]:
    """
    Check if a command contains dangerous patterns.
    
    Returns:
        Tuple of (is_dangerous, warning_message)
    """
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, f"Warning: Command contains potentially dangerous pattern: {pattern}"
    return False, None


class ExecTool(Tool):
    """Tool to execute shell commands."""
    
    def __init__(self, timeout: int = 60, working_dir: str | None = None):
        self.timeout = timeout
        self.working_dir = working_dir
    
    @property
    def name(self) -> str:
        return "exec"
    
    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use with caution."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command"
                }
            },
            "required": ["command"]
        }
    
    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        # Check for dangerous command patterns
        is_dangerous, warning = _is_dangerous_command(command)
        if is_dangerous:
            return f"Error: Refusing to execute dangerous command. {warning}"
        
        cwd = working_dir or self.working_dir or os.getcwd()
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return f"Error: Command timed out after {self.timeout} seconds"
            
            output_parts = []
            
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            
            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")
            
            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")
            
            result = "\n".join(output_parts) if output_parts else "(no output)"
            
            # Truncate very long output
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"
            
            return result
            
        except Exception as e:
            return f"Error executing command: {str(e)}"
