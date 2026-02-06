use bao_api::{ToolCallIrV1, ToolCallSourceV1};
use bao_engine::{
    CorrectorHook, DefaultCorrectorHook, DefaultMemoryHook, DefaultRouterHook, Engine, MemoryHook,
    RouterHook,
};

#[test]
fn router_explicit_tool_should_must_trigger() {
    let router = DefaultRouterHook;
    let out = router.route("/tool demo.echo {\"text\":\"hello\"}");

    assert!(out.matched);
    assert_eq!(out.toolName.as_deref(), Some("demo.echo"));
    assert_eq!(out.quote.as_deref(), Some("/tool"));
    assert_eq!(out.policy.as_ref().map(|p| p.mustTrigger), Some(true));

    let args = out.toolArgs.expect("tool args must exist");
    assert_eq!(args.get("text").and_then(|v| v.as_str()), Some("hello"));
}

#[test]
fn router_memory_keyword_should_request_memory() {
    let router = DefaultRouterHook;
    let out = router.route("请回忆我上次设置的 provider");

    assert!(!out.matched);
    assert!(out.needsMemory);
    assert_eq!(
        out.memoryQuery.as_deref(),
        Some("请回忆我上次设置的 provider")
    );
}

#[test]
fn memory_hook_should_truncate_long_input() {
    let hook = DefaultMemoryHook::new(5);
    let injected = hook.inject("123456789");

    assert_eq!(injected, "memory.injected: 12345…");
}

#[test]
fn corrector_should_reject_non_object_args() {
    let hook = DefaultCorrectorHook;
    let tool_call = ToolCallIrV1 {
        id: "tc_1".to_string(),
        name: "demo.echo".to_string(),
        args: serde_json::json!("not-object"),
        quote: Some("/tool".to_string()),
        source: ToolCallSourceV1 {
            provider: "openai".to_string(),
            model: "gpt-4.1".to_string(),
        },
    };

    let result = hook.validate_tool_args(&tool_call);
    assert!(result.is_err());
    assert!(result.expect_err("must be error").contains("JSON object"));
}

#[test]
fn engine_run_turn_with_defaults_should_work() {
    let engine = Engine::new();

    let result = engine
        .run_turn_with_defaults("请回忆上次任务")
        .expect("run turn should succeed");

    assert!(result.router.needsMemory);
    assert_eq!(result.input_for_provider, "请回忆上次任务");
    assert_eq!(result.output, result.input_for_provider);
}
