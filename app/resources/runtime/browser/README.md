Managed browser runtime bundle lives here for desktop distribution.

The repository only tracks the manifest and helper docs in this directory.
Generated payloads under `platforms/` and the vendored
`node_modules/agent-browser` home are created locally or in CI before
packaging, and are intentionally ignored by Git.

Expected layout:

- `runtime.json`
- `platforms/<platform>/bin/agent-browser[.exe]`
- `platforms/<platform>/browser/...`

`runtime.json` may define:

```json
{
  "source": "agent-browser",
  "version": "0.19.0",
  "platforms": {
    "darwin-arm64": {
      "agentBrowserPath": "platforms/darwin-arm64/bin/agent-browser",
      "browserExecutablePath": "platforms/darwin-arm64/browser/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    }
  }
}
```

Bao resolves this directory from the desktop bundle first, then falls back to
`BAO_BROWSER_RUNTIME_ROOT` for source and test environments.

Recommended refresh path during development:

```bash
uv run python app/scripts/update_agent_browser_runtime.py
```

This command refreshes the browser bundle for the current host platform and keeps
the vendored `agent-browser` platform binaries in sync. If you plan to publish
another platform, run the same command on that platform before packaging.

Desktop release artifacts still embed the generated runtime, so end users keep
browser automation out of the box.

If you already have a prepared runtime directory, you can also sync it in:

```bash
uv run python app/scripts/sync_browser_runtime.py --source /path/to/runtime
```
