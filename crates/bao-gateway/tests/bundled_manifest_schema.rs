use std::fs;
use std::path::Path;

#[test]
fn bundled_manifests_should_be_valid_and_runnable() {
    let crate_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
    let root = crate_dir.join("../..");

    let schema_path = root.join("schemas/dimsum_manifest_v1.schema.json");
    let schema_text = fs::read_to_string(&schema_path)
        .unwrap_or_else(|e| panic!("read schema failed ({}): {e}", schema_path.display()));
    let mut schema: serde_json::Value = serde_json::from_str(&schema_text)
        .unwrap_or_else(|e| panic!("parse schema failed ({}): {e}", schema_path.display()));

    if let Some(obj) = schema.as_object_mut() {
        obj.insert(
            "$id".to_string(),
            serde_json::json!("https://bao.local/schemas/dimsum_manifest_v1.schema.json"),
        );
    }

    let dimsums_root = root.join("dimsums/bundled");
    for entry in fs::read_dir(&dimsums_root).unwrap_or_else(|e| {
        panic!(
            "read bundled dimsums failed ({}): {e}",
            dimsums_root.display()
        )
    }) {
        let entry = entry.expect("read dir entry");
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }

        let manifest_path = path.join("manifest.json");
        if !manifest_path.exists() {
            continue;
        }

        let manifest_text = fs::read_to_string(&manifest_path)
            .unwrap_or_else(|e| panic!("read manifest failed ({}): {e}", manifest_path.display()));
        let manifest: serde_json::Value = serde_json::from_str(&manifest_text)
            .unwrap_or_else(|e| panic!("parse manifest failed ({}): {e}", manifest_path.display()));

        bao_api::validate_json_schema(&schema, &manifest).unwrap_or_else(|e| {
            panic!(
                "manifest schema invalid ({}): {}",
                manifest_path.display(),
                e.message
            )
        });

        let runtime_kind = manifest
            .get("runtime")
            .and_then(|v| v.get("kind"))
            .and_then(serde_json::Value::as_str)
            .unwrap_or("");

        if runtime_kind == "process" {
            let process = manifest
                .get("runtime")
                .and_then(|v| v.get("process"))
                .cloned()
                .unwrap_or(serde_json::Value::Null);
            let command = process
                .get("command")
                .and_then(serde_json::Value::as_str)
                .unwrap_or("");
            let args = process
                .get("args")
                .and_then(serde_json::Value::as_array)
                .cloned()
                .unwrap_or_default();

            assert!(
                !command.trim().is_empty(),
                "process command cannot be empty: {}",
                manifest_path.display()
            );

            let known_process_bins = [
                "bao-provider-openai",
                "bao-provider-anthropic",
                "bao-provider-gemini",
                "bao-provider-xai",
                "bao-skills-adapter",
                "bao-mcp-bridge",
                "bao-router-hook",
                "bao-memory-hook",
                "bao-corrector-hook",
            ];

            assert!(
                !(known_process_bins.contains(&command) && args.is_empty()),
                "process manifest uses bin command without args: {}",
                manifest_path.display()
            );
        }
    }
}
