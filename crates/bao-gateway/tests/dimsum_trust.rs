use bao_gateway::GatewayServer;
use rusqlite::{params, Connection};
use serde_json::json;

const TRUSTED_COMMUNITY_SIGNER: &str = "bao.community.release";

fn signed_manifest(dimsum_id: &str, version: &str, channel: &str, sha256: &str) -> String {
    let signature = format!(
        "bao.sig.v1:{}:{}:{}:{}",
        dimsum_id, version, sha256, TRUSTED_COMMUNITY_SIGNER
    );
    json!({
        "apiVersion": "bao.dimsum/v1",
        "id": dimsum_id,
        "name": "test dimsum",
        "version": version,
        "types": ["tool"],
        "runtime": {
            "kind": "process",
            "process": {
                "command": "echo",
                "args": ["ok"],
                "protocol": "bao-jsonrpc/v1"
            }
        },
        "compat": {
            "baoCore": ">=0.0.0",
            "os": ["macos"],
            "arch": ["arm64"]
        },
        "permissionsRequested": [],
        "distribution": {
            "channel": channel,
            "integrity": {
                "sha256": sha256,
                "signedBy": TRUSTED_COMMUNITY_SIGNER,
                "signature": signature
            }
        }
    })
    .to_string()
}

#[tokio::test]
async fn trusted_signed_dimsum_enable_succeeds() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let sqlite_path_str = sqlite_path.to_string_lossy().to_string();
    let (_gateway, handle) = GatewayServer::open(sqlite_path_str.clone()).expect("open gateway");

    let dimsum_id = "community.signed.ok";
    let version = "1.2.3";
    let sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    let manifest = signed_manifest(dimsum_id, version, "community", sha256);

    let conn = Connection::open(sqlite_path_str).expect("open sqlite");
    conn.execute(
        "INSERT INTO dimsums(dimsum_id, enabled, channel, version, manifest_json, installed_at, updated_at) VALUES (?1, 0, 'community', ?2, ?3, 1, 1)",
        params![dimsum_id, version, manifest],
    )
    .expect("insert dimsum");

    let evt = handle
        .enable_dimsum(dimsum_id.to_string())
        .await
        .expect("enable trusted dimsum");
    assert_eq!(evt.r#type, "dimsums.enable");
}

#[tokio::test]
async fn tampered_signature_is_blocked_with_code_and_audit_event() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let sqlite_path_str = sqlite_path.to_string_lossy().to_string();
    let (_gateway, handle) = GatewayServer::open(sqlite_path_str.clone()).expect("open gateway");

    let dimsum_id = "community.signed.bad";
    let version = "1.2.3";
    let sha256 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    let mut manifest: serde_json::Value =
        serde_json::from_str(&signed_manifest(dimsum_id, version, "community", sha256))
            .expect("manifest json");
    manifest["distribution"]["integrity"]["signature"] = json!("bao.sig.v1:tampered");

    let conn = Connection::open(sqlite_path_str.clone()).expect("open sqlite");
    conn.execute(
        "INSERT INTO dimsums(dimsum_id, enabled, channel, version, manifest_json, installed_at, updated_at) VALUES (?1, 0, 'community', ?2, ?3, 1, 1)",
        params![dimsum_id, version, manifest.to_string()],
    )
    .expect("insert tampered dimsum");

    let err = handle
        .enable_dimsum(dimsum_id.to_string())
        .await
        .expect_err("tampered signature must be rejected");
    let err_text = err.to_string();
    assert!(
        err_text.contains("DIMSUM_TRUST_INVALID_SIGNATURE"),
        "unexpected error: {err_text}"
    );

    let (event_type, payload_json): (String, String) = conn
        .query_row(
            "SELECT type, payload_json FROM events ORDER BY eventId DESC LIMIT 1",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .expect("query latest event");
    assert_eq!(event_type, "dimsums.reject");
    let payload: serde_json::Value = serde_json::from_str(&payload_json).expect("parse payload");
    assert_eq!(payload["code"], "DIMSUM_TRUST_INVALID_SIGNATURE");

    let (action, audit_payload_json): (String, String) = conn
        .query_row(
            "SELECT action, payload_json FROM audit_events ORDER BY id DESC LIMIT 1",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .expect("query latest audit");
    assert_eq!(action, "dimsum.trust.reject");
    let audit_payload: serde_json::Value =
        serde_json::from_str(&audit_payload_json).expect("parse audit payload");
    assert_eq!(audit_payload["code"], "DIMSUM_TRUST_INVALID_SIGNATURE");
}

#[test]
fn downgrade_attempt_is_blocked_on_seed_install() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let sqlite_path_str = sqlite_path.to_string_lossy().to_string();

    let (gateway, _handle) = GatewayServer::open(sqlite_path_str.clone()).expect("first open");
    drop(gateway);

    let conn = Connection::open(sqlite_path_str.clone()).expect("open sqlite");
    conn.execute(
        "UPDATE dimsums SET version='9.9.9', updated_at=updated_at+1 WHERE dimsum_id='bao.bundled.router'",
        [],
    )
    .expect("raise installed version");
    drop(conn);

    let err = match GatewayServer::open(sqlite_path_str.clone()) {
        Ok(_) => panic!("downgrade should be blocked"),
        Err(err) => err,
    };
    let err_text = err.to_string();
    assert!(
        err_text.contains("DIMSUM_TRUST_DOWNGRADE_BLOCKED"),
        "unexpected error: {err_text}"
    );

    let conn = Connection::open(sqlite_path_str).expect("reopen sqlite");
    let (action, payload_json): (String, String) = conn
        .query_row(
            "SELECT action, payload_json FROM audit_events ORDER BY id DESC LIMIT 1",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .expect("query install reject audit");
    assert_eq!(action, "dimsum.install.reject");
    let payload: serde_json::Value = serde_json::from_str(&payload_json).expect("parse payload");
    assert_eq!(payload["code"], "DIMSUM_TRUST_DOWNGRADE_BLOCKED");
}
