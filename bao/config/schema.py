"""Configuration schema using Pydantic."""

from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WhatsAppConfig(Base):
    """WhatsApp channel configuration."""

    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    bridge_token: str = ""  # Shared token for bridge auth (optional, recommended)
    allow_from: list[str] = Field(default_factory=list)  # Allowed phone numbers


class TelegramConfig(Base):
    """Telegram channel configuration."""

    enabled: bool = False
    token: str = ""  # Bot token from @BotFather
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs or usernames
    proxy: str | None = (
        None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"
    )
    reply_to_message: bool = False  # If true, bot replies quote the original message


class FeishuConfig(Base):
    """Feishu/Lark channel configuration using WebSocket long connection."""

    enabled: bool = False
    app_id: str = ""  # App ID from Feishu Open Platform
    app_secret: str = ""  # App Secret from Feishu Open Platform
    encrypt_key: str = ""  # Encrypt Key for event subscription (optional)
    verification_token: str = ""  # Verification Token for event subscription (optional)
    allow_from: list[str] = Field(default_factory=list)  # Allowed user open_ids


class DingTalkConfig(Base):
    """DingTalk channel configuration using Stream mode."""

    enabled: bool = False
    client_id: str = ""  # AppKey
    client_secret: str = ""  # AppSecret
    allow_from: list[str] = Field(default_factory=list)  # Allowed staff_ids


class DiscordConfig(Base):
    """Discord channel configuration."""

    enabled: bool = False
    token: str = ""  # Bot token from Discord Developer Portal
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377  # GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT


class EmailConfig(Base):
    """Email channel configuration (IMAP inbound + SMTP outbound)."""

    enabled: bool = False
    consent_granted: bool = False  # Explicit owner permission to access mailbox data

    # IMAP (receive)
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True

    # SMTP (send)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = ""

    # Behavior
    auto_reply_enabled: bool = (
        True  # If false, inbound email is read but no automatic reply is sent
    )
    poll_interval_seconds: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    allow_from: list[str] = Field(default_factory=list)  # Allowed sender email addresses


class MochatMentionConfig(Base):
    """Mochat mention behavior configuration."""

    require_in_groups: bool = False


class MochatGroupRule(Base):
    """Mochat per-group mention requirement."""

    require_mention: bool = False


class MochatConfig(Base):
    """Mochat channel configuration."""

    enabled: bool = False
    base_url: str = "https://mochat.io"
    socket_url: str = ""
    socket_path: str = "/socket.io"
    socket_disable_msgpack: bool = False
    socket_reconnect_delay_ms: int = 1000
    socket_max_reconnect_delay_ms: int = 10000
    socket_connect_timeout_ms: int = 10000
    refresh_interval_ms: int = 30000
    watch_timeout_ms: int = 25000
    watch_limit: int = 100
    retry_delay_ms: int = 500
    max_retry_attempts: int = 0  # 0 means unlimited retries
    claw_token: str = ""
    agent_user_id: str = ""
    sessions: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    allow_from: list[str] = Field(default_factory=list)
    mention: MochatMentionConfig = Field(default_factory=MochatMentionConfig)
    groups: dict[str, MochatGroupRule] = Field(default_factory=dict)
    reply_delay_mode: str = "non-mention"  # off | non-mention
    reply_delay_ms: int = 120000


class SlackDMConfig(Base):
    """Slack DM policy configuration."""

    enabled: bool = True
    policy: str = "open"  # "open" or "allowlist"
    allow_from: list[str] = Field(default_factory=list)  # Allowed Slack user IDs


class SlackConfig(Base):
    """Slack channel configuration."""

    enabled: bool = False
    mode: str = "socket"  # "socket" supported
    webhook_path: str = "/slack/events"
    bot_token: str = ""  # xoxb-...
    app_token: str = ""  # xapp-...
    user_token_read_only: bool = True
    reply_in_thread: bool = True
    react_emoji: str = "eyes"
    group_policy: str = "mention"  # "mention", "open", "allowlist"
    group_allow_from: list[str] = Field(default_factory=list)  # Allowed channel IDs if allowlist
    dm: SlackDMConfig = Field(default_factory=SlackDMConfig)


class QQConfig(Base):
    """QQ channel configuration using botpy SDK."""

    enabled: bool = False
    app_id: str = ""
    secret: str = ""
    allow_from: list[str] = Field(default_factory=list)


class IMessageConfig(Base):
    """iMessage channel configuration (macOS only)."""

    enabled: bool = False
    poll_interval: float = 2.0
    service: str = "iMessage"
    allow_from: list[str] = Field(default_factory=list)


class ChannelsConfig(Base):
    """Configuration for chat channels."""

    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    mochat: MochatConfig = Field(default_factory=MochatConfig)
    dingtalk: DingTalkConfig = Field(default_factory=DingTalkConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    qq: QQConfig = Field(default_factory=QQConfig)
    imessage: IMessageConfig = Field(default_factory=IMessageConfig)


class AgentDefaults(Base):
    """Default agent configuration."""

    workspace: str = "~/.bao/workspace"
    model: str = "anthropic/claude-opus-4-5"
    utility_model: str = ""
    experience_model: str = "utility"  # "utility" | "main" | "none"
    models: list[str] = Field(default_factory=list)
    max_tokens: int = 8192
    temperature: float = 0.1
    max_tool_iterations: int = 20
    memory_window: int = 50
    context_management: str = "observe"  # off | observe | auto | aggressive
    tool_output_preview_chars: int = 3000
    tool_output_offload_chars: int = 8000
    context_compact_bytes_est: int = 240000
    context_compact_keep_recent_tool_blocks: int = 4
    artifact_retention_days: int = 7


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None
    api_mode: str = "auto"


class ProvidersConfig(Base):
    """Configuration for LLM providers."""
    openai_compatible: ProviderConfig = Field(default_factory=ProviderConfig)
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    openai_codex: ProviderConfig = Field(default_factory=ProviderConfig)


class GatewayConfig(Base):
    """Gateway/server configuration."""

    host: str = "0.0.0.0"
    port: int = 18790


class EmbeddingConfig(Base):
    """Embedding model configuration for semantic search."""

    model: str = ""
    api_key: str = ""
    base_url: str = ""
    dim: int = 0

    @property
    def enabled(self) -> bool:
        return bool(self.model and self.api_key)


class WebSearchConfig(Base):
    """Web search tool configuration."""

    provider: str = ""
    brave_api_key: str = ""
    tavily_api_key: str = ""
    max_results: int = 5


class WebToolsConfig(Base):
    """Web tools configuration."""

    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(Base):
    """Shell exec tool configuration."""

    timeout: int = 60


class MCPServerConfig(Base):
    """MCP server connection configuration (stdio or HTTP)."""

    command: str = ""  # Stdio: command to run (e.g. "npx")
    args: list[str] = Field(default_factory=list)  # Stdio: command arguments
    env: dict[str, str] = Field(default_factory=dict)  # Stdio: extra env vars
    url: str = ""  # HTTP: streamable HTTP endpoint URL
    headers: dict[str, str] = Field(default_factory=dict)  # HTTP: Custom HTTP Headers
    tool_timeout_seconds: int = 30  # Timeout for individual MCP tool calls


class ToolsConfig(Base):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    restrict_to_workspace: bool = False  # If true, restrict all tool access to workspace directory
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


class Config(BaseSettings):
    """Root configuration for bao."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self, model: str | None = None
    ) -> tuple["ProviderConfig | None", str | None]:
        from bao.providers.registry import PROVIDERS, ProviderType

        model_str = model or self.agents.defaults.model
        model_lower = model_str.lower()
        model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
        normalized_prefix = model_prefix.replace("-", "_")

        # Map registry spec names to config field names
        # The simplified config only has 4 fields: openai_compatible, anthropic, gemini, openai_codex
        def get_config_field_for_spec(spec_name: str, provider_type: ProviderType) -> str:
            """Map registry spec name to config field name."""
            if provider_type == ProviderType.ANTHROPIC:
                return "anthropic"
            elif provider_type == ProviderType.GEMINI:
                return "gemini"
            elif provider_type == ProviderType.OAUTH:
                return "openai_codex"
            else:  # OPENAI_COMPATIBLE
                # Map specific providers to openai_compatible field
                # These all use the same config field with different api_base
                return "openai_compatible"

        # Find provider spec by model
        spec = None
        for s in PROVIDERS:
            if normalized_prefix == s.name:
                spec = s
                break
        if not spec:
            # Try keyword match
            for s in PROVIDERS:
                for kw in s.keywords:
                    if kw in model_lower or kw.replace("-", "_") in model_lower:
                        spec = s
                        break
                if spec:
                    break
        if not spec:
            spec = next((s for s in PROVIDERS if s.name == "openai"), None)

        if not spec:
            return None, None

        config_field = get_config_field_for_spec(spec.name, spec.provider_type)
        p = getattr(self.providers, config_field, None)

        # Priority 1: exact prefix match with api_key
        if p and p.api_key:
            return p, spec.name

        # Priority 2: fallback to first available provider with api_key
        for s in PROVIDERS:
            if s.provider_type == ProviderType.OAUTH:
                continue
            field = get_config_field_for_spec(s.name, s.provider_type)
            cfg = getattr(self.providers, field, None)
            if cfg and cfg.api_key:
                return cfg, s.name

        return p if p else None, spec.name

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the registry name of the matched provider (e.g. "deepseek", "openrouter")."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model)
        return p.api_key if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        from bao.providers.registry import find_by_name

        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base

        if name:
            spec = find_by_name(name)
            if spec and spec.default_api_base:
                return spec.default_api_base

        return None

    model_config = SettingsConfigDict(env_prefix="bao_", env_nested_delimiter="__")
