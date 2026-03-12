"""Configuration schema using Pydantic."""

import warnings
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings, SettingsConfigDict

ExperienceModelLiteral = Literal["utility", "main", "none"]
ContextManagementLiteral = Literal["off", "observe", "auto", "aggressive"]
ExecSandboxModeLiteral = Literal["full-auto", "semi-auto", "read-only"]
SlackGroupPolicyLiteral = Literal["mention", "open", "allowlist"]
SlackDmPolicyLiteral = Literal["open", "allowlist"]
SlackModeLiteral = Literal["socket"]
MochatReplyDelayModeLiteral = Literal["off", "non-mention"]
ProviderTypeLiteral = Literal["openai", "anthropic", "gemini", "openai_codex"]
ToolExposureModeLiteral = Literal["off", "auto"]
TelegramGroupPolicyLiteral = Literal["open", "mention"]
DiscordGroupPolicyLiteral = Literal["mention", "open"]
FeishuGroupPolicyLiteral = Literal["mention", "open"]


def _warn_unknown_policy(
    *, model_name: str, field_name: str, value: str, allowed_values: tuple[str, ...]
) -> None:
    if value in allowed_values:
        return
    allowed_text = ", ".join(allowed_values)
    warnings.warn(
        f"Unknown {model_name}.{field_name} value {value!r}. "
        f"Allowed values: {allowed_text}. Proceeding for compatibility.",
        UserWarning,
        stacklevel=3,
    )


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WhatsAppConfig(Base):
    """WhatsApp channel configuration."""

    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    bridge_token: SecretStr = SecretStr("")  # Shared token for bridge auth (optional, recommended)
    allow_from: list[str] = Field(
        default_factory=list
    )  # Allowed phone numbers; also normalized for proactive startup/heartbeat targets


class TelegramConfig(Base):
    """Telegram channel configuration."""

    enabled: bool = False
    token: SecretStr = SecretStr("")  # Bot token from @BotFather
    allow_from: list[str] = Field(
        default_factory=list
    )  # Allowed sender ids/usernames; use numeric chat_id for proactive startup/heartbeat targets, composite `identity|chat_id` optional
    proxy: str | None = (
        None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"
    )
    reply_to_message: bool = False  # If true, bot replies quote the original message
    group_policy: str = "mention"  # "mention" when @mentioned or replied to, "open" for all

    @model_validator(mode="after")
    def _warn_group_policy(self) -> "TelegramConfig":
        _warn_unknown_policy(
            model_name="TelegramConfig",
            field_name="group_policy",
            value=self.group_policy,
            allowed_values=get_args(TelegramGroupPolicyLiteral),
        )
        return self


class FeishuConfig(Base):
    """Feishu/Lark channel configuration using WebSocket long connection."""

    enabled: bool = False
    app_id: str = ""  # App ID from Feishu Open Platform
    app_secret: SecretStr = SecretStr("")  # App Secret from Feishu Open Platform
    encrypt_key: SecretStr = SecretStr("")  # Encrypt Key for event subscription (optional)
    verification_token: SecretStr = SecretStr(
        ""
    )  # Verification Token for event subscription (optional)
    allow_from: list[str] = Field(
        default_factory=list
    )  # Allowed user open_ids; ordered values also define proactive target priority
    react_emoji: str = (
        "THUMBSUP"  # Emoji type for message reactions (e.g. THUMBSUP, OK, DONE, SMILE)
    )
    group_policy: str = "mention"  # "mention" responds when @mentioned, "open" responds to all

    @model_validator(mode="after")
    def _warn_group_policy(self) -> "FeishuConfig":
        _warn_unknown_policy(
            model_name="FeishuConfig",
            field_name="group_policy",
            value=self.group_policy,
            allowed_values=get_args(FeishuGroupPolicyLiteral),
        )
        return self


class DingTalkConfig(Base):
    """DingTalk channel configuration using Stream mode."""

    enabled: bool = False
    client_id: str = ""  # AppKey
    client_secret: SecretStr = SecretStr("")  # AppSecret
    allow_from: list[str] = Field(
        default_factory=list
    )  # Allowed staff_ids; ordered values also define proactive target priority


class DiscordConfig(Base):
    """Discord channel configuration."""

    enabled: bool = False
    token: SecretStr = SecretStr("")  # Bot token from Discord Developer Portal
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377  # GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT
    group_policy: str = "mention"  # "mention" or "open"

    @model_validator(mode="after")
    def _warn_group_policy(self) -> "DiscordConfig":
        _warn_unknown_policy(
            model_name="DiscordConfig",
            field_name="group_policy",
            value=self.group_policy,
            allowed_values=get_args(DiscordGroupPolicyLiteral),
        )
        return self


class EmailConfig(Base):
    """Email channel configuration (IMAP inbound + SMTP outbound)."""

    enabled: bool = False
    consent_granted: bool = False  # Explicit owner permission to access mailbox data

    # IMAP (receive)
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: SecretStr = SecretStr("")
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True

    # SMTP (send)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
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
    allow_from: list[str] = Field(
        default_factory=list
    )  # Allowed sender email addresses; ordered values also define proactive target priority


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
    claw_token: SecretStr = SecretStr("")
    agent_user_id: str = ""
    sessions: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    allow_from: list[str] = Field(default_factory=list)
    mention: MochatMentionConfig = Field(default_factory=MochatMentionConfig)
    groups: dict[str, MochatGroupRule] = Field(default_factory=dict)
    reply_delay_mode: str = "non-mention"  # off | non-mention
    reply_delay_ms: int = 120000

    @model_validator(mode="after")
    def _warn_reply_delay_mode(self) -> "MochatConfig":
        _warn_unknown_policy(
            model_name="MochatConfig",
            field_name="reply_delay_mode",
            value=self.reply_delay_mode,
            allowed_values=get_args(MochatReplyDelayModeLiteral),
        )
        return self


class SlackDMConfig(Base):
    """Slack DM policy configuration."""

    enabled: bool = True
    policy: str = "open"  # "open" or "allowlist"
    allow_from: list[str] = Field(default_factory=list)  # Allowed Slack user IDs

    @model_validator(mode="after")
    def _warn_policy(self) -> "SlackDMConfig":
        _warn_unknown_policy(
            model_name="SlackDMConfig",
            field_name="policy",
            value=self.policy,
            allowed_values=get_args(SlackDmPolicyLiteral),
        )
        return self


class SlackConfig(Base):
    """Slack channel configuration."""

    enabled: bool = False
    mode: str = "socket"  # "socket" supported
    webhook_path: str = "/slack/events"
    bot_token: SecretStr = SecretStr("")  # xoxb-...
    app_token: SecretStr = SecretStr("")  # xapp-...
    user_token_read_only: bool = True
    reply_in_thread: bool = True
    react_emoji: str = "eyes"
    group_policy: str = "mention"  # "mention", "open", "allowlist"
    group_allow_from: list[str] = Field(default_factory=list)  # Allowed channel IDs if allowlist
    dm: SlackDMConfig = Field(default_factory=SlackDMConfig)

    @model_validator(mode="after")
    def _warn_policies(self) -> "SlackConfig":
        _warn_unknown_policy(
            model_name="SlackConfig",
            field_name="mode",
            value=self.mode,
            allowed_values=get_args(SlackModeLiteral),
        )
        _warn_unknown_policy(
            model_name="SlackConfig",
            field_name="group_policy",
            value=self.group_policy,
            allowed_values=get_args(SlackGroupPolicyLiteral),
        )
        return self


class QQConfig(Base):
    """QQ channel configuration using botpy SDK."""

    enabled: bool = False
    app_id: str = ""
    secret: SecretStr = SecretStr("")
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
    model: str = ""
    utility_model: str = ""
    experience_model: str = "utility"  # "utility" | "main" | "none"
    models: list[str] = Field(default_factory=list)
    max_tokens: int = 16000
    temperature: float = 0.1
    max_tool_iterations: int = 50
    memory_window: int = 100
    reasoning_effort: str | None = None
    context_management: str = "auto"  # off | observe | auto | aggressive
    tool_output_preview_chars: int = 3000
    tool_output_offload_chars: int = 8000
    tool_output_hard_chars: int = 6000
    context_compact_bytes_est: int = 240000
    context_compact_keep_recent_tool_blocks: int = 6
    artifact_retention_days: int = 7
    send_progress: bool = True
    send_tool_hints: bool = True

    @model_validator(mode="after")
    def _warn_policies(self) -> "AgentDefaults":
        _warn_unknown_policy(
            model_name="AgentDefaults",
            field_name="experience_model",
            value=self.experience_model,
            allowed_values=get_args(ExperienceModelLiteral),
        )
        _warn_unknown_policy(
            model_name="AgentDefaults",
            field_name="context_management",
            value=self.context_management,
            allowed_values=get_args(ContextManagementLiteral),
        )
        return self


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
    """LLM provider configuration."""

    type: str = "openai"
    api_key: SecretStr = SecretStr("")
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None

    @model_validator(mode="after")
    def _warn_policies(self) -> "ProviderConfig":
        _warn_unknown_policy(
            model_name="ProviderConfig",
            field_name="type",
            value=self.type,
            allowed_values=get_args(ProviderTypeLiteral),
        )
        return self


class HeartbeatConfig(Base):
    """Heartbeat service configuration."""

    enabled: bool = True
    interval_s: int = 30 * 60  # 30 minutes


class GatewayConfig(Base):
    """Gateway/server configuration."""

    host: str = "0.0.0.0"
    port: int = 18790
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)


class EmbeddingConfig(Base):
    """Embedding model configuration for semantic search."""

    model: str = ""
    api_key: SecretStr = SecretStr("")
    base_url: str = ""
    dim: int = 0
    timeout_seconds: int = 15
    retry_attempts: int = 2
    retry_backoff_ms: int = 200

    @property
    def enabled(self) -> bool:
        return bool(self.model and self.api_key.get_secret_value())


class WebSearchConfig(Base):
    """Web search tool configuration."""

    provider: str = ""
    brave_api_key: SecretStr = SecretStr("")
    tavily_api_key: SecretStr = SecretStr("")
    exa_api_key: SecretStr = SecretStr("")
    max_results: int = 5


class WebToolsConfig(Base):
    """Web tools configuration."""

    proxy: str | None = None
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(Base):
    """Shell exec tool configuration."""

    timeout: int = 60
    path_append: str = ""
    sandbox_mode: str = "semi-auto"  # full-auto | semi-auto | read-only

    @model_validator(mode="after")
    def _warn_sandbox_mode(self) -> "ExecToolConfig":
        _warn_unknown_policy(
            model_name="ExecToolConfig",
            field_name="sandbox_mode",
            value=self.sandbox_mode,
            allowed_values=get_args(ExecSandboxModeLiteral),
        )
        return self


class MCPServerConfig(Base):
    """MCP server connection configuration (stdio or HTTP)."""

    type: str = ""  # Optional: stdio | sse | streamableHttp. Empty = infer from command/url
    command: str = ""  # Stdio: command to run (e.g. "npx")
    args: list[str] = Field(default_factory=list)  # Stdio: command arguments
    env: dict[str, str] = Field(default_factory=dict)  # Stdio: extra env vars
    url: str = ""  # HTTP: streamable HTTP endpoint URL
    headers: dict[str, str] = Field(default_factory=dict)  # HTTP: Custom HTTP Headers
    tool_timeout_seconds: int = 30  # Timeout for individual MCP tool calls
    slim_schema: bool | None = None
    max_tools: int | None = None


class ImageGenerationConfig(Base):
    """Image generation tool config. Leave api_key empty to disable."""

    api_key: SecretStr = SecretStr("")
    model: str = ""  # Empty → default to gemini-2.0-flash-exp-image-generation inside tool
    base_url: str = ""  # Empty → Google official endpoint


class DesktopConfig(Base):
    """Desktop automation tools config. Enabled by default."""

    enabled: bool = True


class ToolExposureConfig(Base):
    mode: str = "auto"
    bundles: list[str] = Field(default_factory=lambda: ["core", "web", "desktop", "code"])

    @model_validator(mode="after")
    def _warn_mode(self) -> "ToolExposureConfig":
        _warn_unknown_policy(
            model_name="ToolExposureConfig",
            field_name="mode",
            value=self.mode,
            allowed_values=get_args(ToolExposureModeLiteral),
        )
        return self


class ToolsConfig(Base):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    restrict_to_workspace: bool = False  # If true, restrict all tool access to workspace directory
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    mcp_max_tools: int = 50
    mcp_slim_schema: bool = True
    image_generation: ImageGenerationConfig = Field(default_factory=ImageGenerationConfig)
    desktop: DesktopConfig = Field(default_factory=DesktopConfig)
    tool_exposure: ToolExposureConfig = Field(default_factory=ToolExposureConfig)


class UIConfig(Base):
    class UpdateConfig(Base):
        enabled: bool = True
        auto_check: bool = True
        channel: str = "stable"
        feed_url: str = "https://suge8.github.io/Bao/desktop-update.json"

    update: UpdateConfig = Field(default_factory=UpdateConfig)


class Config(BaseSettings):
    """Root configuration for Bao."""

    config_version: int = Field(default=3, alias="config_version")
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self, model: str | None = None
    ) -> tuple["ProviderConfig | None", str | None]:
        model_str = model or self.agents.defaults.model
        if not model_str:
            return None, None
        model_prefix = model_str.split("/", 1)[0] if "/" in model_str else ""
        normalized_prefix = model_prefix.lower().replace("-", "_")

        def _has_usable_key(p: ProviderConfig) -> bool:
            return p.type == "openai_codex" or bool(p.api_key.get_secret_value())

        if normalized_prefix:
            for provider_name, provider in self.providers.items():
                if provider_name.lower().replace("-", "_") == normalized_prefix:
                    return (provider if _has_usable_key(provider) else None), provider_name
            return None, None

        for provider_name, provider in self.providers.items():
            if _has_usable_key(provider):
                return provider, provider_name
        return None, None

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the matched provider config name (dict key under providers)."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model)
        return p.api_key.get_secret_value() if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        p, _ = self._match_provider(model)
        if p and p.api_base:
            return p.api_base

        if not p:
            return None
        if p.type == "openai":
            return "https://api.openai.com/v1"
        if p.type == "anthropic":
            return "https://api.anthropic.com"
        if p.type == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/models"
        return None

    model_config = SettingsConfigDict(env_prefix="bao_", env_nested_delimiter="__")
