PRAGMA foreign_keys = ON;

-- Core sessions/messages/tool_calls/tasks/events/audit_events/dimsums/settings/resources

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL UNIQUE,
  title TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL UNIQUE,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);

CREATE TABLE IF NOT EXISTS tool_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool_call_id TEXT NOT NULL UNIQUE,
  session_id TEXT NOT NULL,
  message_id TEXT,
  name TEXT NOT NULL,
  args_json TEXT NOT NULL,
  quote TEXT,
  source_provider TEXT NOT NULL,
  source_model TEXT NOT NULL,
  status TEXT NOT NULL,
  result_json TEXT,
  error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session_id ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_message_id ON tool_calls(message_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_created_at ON tool_calls(created_at);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  enabled INTEGER NOT NULL,

  schedule_kind TEXT NOT NULL,
  run_at_ts INTEGER,
  interval_ms INTEGER,
  cron TEXT,
  timezone TEXT,

  next_run_at INTEGER,
  last_run_at INTEGER,
  last_status TEXT,
  last_error TEXT,

  tool_dimsum_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  tool_args_json TEXT NOT NULL,
  policy_json TEXT,
  kill_switch_group TEXT,

  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_enabled_next_run ON tasks(enabled, next_run_at);
CREATE INDEX IF NOT EXISTS idx_tasks_kill_switch_group ON tasks(kill_switch_group);

CREATE TABLE IF NOT EXISTS events (
  eventId INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  type TEXT NOT NULL,
  session_id TEXT,
  message_id TEXT,
  device_id TEXT,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_session_id ON events(session_id);

CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  action TEXT NOT NULL,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  prev_hash TEXT,
  hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_ts ON audit_events(ts);
CREATE INDEX IF NOT EXISTS idx_audit_events_subject ON audit_events(subject_type, subject_id);

CREATE TABLE IF NOT EXISTS dimsums (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dimsum_id TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL,
  channel TEXT NOT NULL,
  version TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  installed_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL UNIQUE,
  value_json TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS resources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  namespace TEXT NOT NULL,
  path TEXT NOT NULL,
  mime TEXT NOT NULL,
  kind TEXT NOT NULL,
  sha256 TEXT,
  content_text TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(namespace, path)
);
CREATE INDEX IF NOT EXISTS idx_resources_namespace_path ON resources(namespace, path);

-- Memory Native: artifacts/memory_items/memory_versions/memory_links/vector_meta + FTS

CREATE TABLE IF NOT EXISTS artifacts (
  sha256 TEXT PRIMARY KEY,
  mime TEXT NOT NULL,
  size INTEGER NOT NULL,
  blob_path TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  memory_id TEXT NOT NULL UNIQUE,
  namespace TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT,
  json TEXT,
  score REAL NOT NULL,
  status TEXT NOT NULL,
  source_hash TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  last_injected_at INTEGER,
  inject_count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_items_namespace_kind ON memory_items(namespace, kind);
CREATE INDEX IF NOT EXISTS idx_memory_items_status ON memory_items(status);
CREATE INDEX IF NOT EXISTS idx_memory_items_updated_at ON memory_items(updated_at);

CREATE TABLE IF NOT EXISTS memory_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id TEXT NOT NULL UNIQUE,
  memory_id TEXT NOT NULL,
  prev_version_id TEXT,
  op TEXT NOT NULL,
  diff_json TEXT NOT NULL,
  actor TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_versions_memory_id ON memory_versions(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_versions_created_at ON memory_versions(created_at);

CREATE TABLE IF NOT EXISTS memory_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  memory_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  message_id TEXT,
  event_id INTEGER,
  artifact_sha256 TEXT,
  weight REAL NOT NULL,
  note TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_links_memory_id ON memory_links(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_links_kind ON memory_links(kind);
CREATE INDEX IF NOT EXISTS idx_memory_links_message_id ON memory_links(message_id);
CREATE INDEX IF NOT EXISTS idx_memory_links_event_id ON memory_links(event_id);
CREATE INDEX IF NOT EXISTS idx_memory_links_artifact_sha256 ON memory_links(artifact_sha256);

CREATE TABLE IF NOT EXISTS vector_meta (
  memory_id TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vec_id TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(memory_id, embedding_model)
);
CREATE INDEX IF NOT EXISTS idx_vector_meta_updated_at ON vector_meta(updated_at);

-- FTS5 (External content + triggers)

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  content,
  role UNINDEXED,
  session_id UNINDEXED,
  content='messages',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 1'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content, role, session_id) VALUES (new.id, new.content, new.role, new.session_id);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content, role, session_id) VALUES('delete', old.id, old.content, old.role, old.session_id);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content, role, session_id) VALUES('delete', old.id, old.content, old.role, old.session_id);
  INSERT INTO messages_fts(rowid, content, role, session_id) VALUES (new.id, new.content, new.role, new.session_id);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
  title,
  content,
  namespace UNINDEXED,
  kind UNINDEXED,
  content='memory_items',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 1'
);

CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
  INSERT INTO memory_fts(rowid, title, content, namespace, kind) VALUES (new.id, new.title, new.content, new.namespace, new.kind);
END;
CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, title, content, namespace, kind) VALUES('delete', old.id, old.title, old.content, old.namespace, old.kind);
END;
CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, title, content, namespace, kind) VALUES('delete', old.id, old.title, old.content, old.namespace, old.kind);
  INSERT INTO memory_fts(rowid, title, content, namespace, kind) VALUES (new.id, new.title, new.content, new.namespace, new.kind);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
  path,
  content_text,
  namespace UNINDEXED,
  mime UNINDEXED,
  kind UNINDEXED,
  content='resources',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 1'
);

CREATE TRIGGER IF NOT EXISTS resources_ai AFTER INSERT ON resources BEGIN
  INSERT INTO resources_fts(rowid, path, content_text, namespace, mime, kind) VALUES (new.id, new.path, new.content_text, new.namespace, new.mime, new.kind);
END;
CREATE TRIGGER IF NOT EXISTS resources_ad AFTER DELETE ON resources BEGIN
  INSERT INTO resources_fts(resources_fts, rowid, path, content_text, namespace, mime, kind) VALUES('delete', old.id, old.path, old.content_text, old.namespace, old.mime, old.kind);
END;
CREATE TRIGGER IF NOT EXISTS resources_au AFTER UPDATE ON resources BEGIN
  INSERT INTO resources_fts(resources_fts, rowid, path, content_text, namespace, mime, kind) VALUES('delete', old.id, old.path, old.content_text, old.namespace, old.mime, old.kind);
  INSERT INTO resources_fts(rowid, path, content_text, namespace, mime, kind) VALUES (new.id, new.path, new.content_text, new.namespace, new.mime, new.kind);
END;
