"""Channel configuration models."""

from pydantic import Field, SecretStr, model_validator

from ._schema_base import (
    Base,
    DiscordGroupPolicyLiteral,
    FeishuGroupPolicyLiteral,
    MochatReplyDelayModeLiteral,
    PolicyWarningSpec,
    SlackDmPolicyLiteral,
    SlackGroupPolicyLiteral,
    SlackModeLiteral,
    TelegramGroupPolicyLiteral,
    get_args,
    warn_unknown_policy,
)


class WhatsAppConfig(Base):
    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    bridge_token: SecretStr = SecretStr("")
    allow_from: list[str] = Field(default_factory=list)


class TelegramConfig(Base):
    enabled: bool = False
    token: SecretStr = SecretStr("")
    allow_from: list[str] = Field(default_factory=list)
    proxy: str | None = None
    reply_to_message: bool = False
    group_policy: str = "mention"

    @model_validator(mode="after")
    def _warn_group_policy(self) -> "TelegramConfig":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="TelegramConfig",
                field_name="group_policy",
                value=self.group_policy,
                allowed_values=get_args(TelegramGroupPolicyLiteral),
            )
        )
        return self


class FeishuConfig(Base):
    enabled: bool = False
    app_id: str = ""
    app_secret: SecretStr = SecretStr("")
    encrypt_key: SecretStr = SecretStr("")
    verification_token: SecretStr = SecretStr("")
    allow_from: list[str] = Field(default_factory=list)
    react_emoji: str = "THUMBSUP"
    group_policy: str = "mention"

    @model_validator(mode="after")
    def _warn_group_policy(self) -> "FeishuConfig":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="FeishuConfig",
                field_name="group_policy",
                value=self.group_policy,
                allowed_values=get_args(FeishuGroupPolicyLiteral),
            )
        )
        return self


class DingTalkConfig(Base):
    enabled: bool = False
    client_id: str = ""
    client_secret: SecretStr = SecretStr("")
    allow_from: list[str] = Field(default_factory=list)


class DiscordConfig(Base):
    enabled: bool = False
    token: SecretStr = SecretStr("")
    allow_from: list[str] = Field(default_factory=list)
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377
    group_policy: str = "mention"

    @model_validator(mode="after")
    def _warn_group_policy(self) -> "DiscordConfig":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="DiscordConfig",
                field_name="group_policy",
                value=self.group_policy,
                allowed_values=get_args(DiscordGroupPolicyLiteral),
            )
        )
        return self


class EmailConfig(Base):
    enabled: bool = False
    consent_granted: bool = False
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: SecretStr = SecretStr("")
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = ""
    auto_reply_enabled: bool = True
    poll_interval_seconds: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    allow_from: list[str] = Field(default_factory=list)


class MochatMentionConfig(Base):
    require_in_groups: bool = False


class MochatGroupRule(Base):
    require_mention: bool = False


class MochatConfig(Base):
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
    max_retry_attempts: int = 0
    claw_token: SecretStr = SecretStr("")
    agent_user_id: str = ""
    sessions: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    allow_from: list[str] = Field(default_factory=list)
    mention: MochatMentionConfig = Field(default_factory=MochatMentionConfig)
    groups: dict[str, MochatGroupRule] = Field(default_factory=dict)
    reply_delay_mode: str = "non-mention"
    reply_delay_ms: int = 120000

    @model_validator(mode="after")
    def _warn_reply_delay_mode(self) -> "MochatConfig":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="MochatConfig",
                field_name="reply_delay_mode",
                value=self.reply_delay_mode,
                allowed_values=get_args(MochatReplyDelayModeLiteral),
            )
        )
        return self


class SlackDMConfig(Base):
    enabled: bool = True
    policy: str = "open"
    allow_from: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _warn_policy(self) -> "SlackDMConfig":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="SlackDMConfig",
                field_name="policy",
                value=self.policy,
                allowed_values=get_args(SlackDmPolicyLiteral),
            )
        )
        return self


class SlackConfig(Base):
    enabled: bool = False
    mode: str = "socket"
    webhook_path: str = "/slack/events"
    bot_token: SecretStr = SecretStr("")
    app_token: SecretStr = SecretStr("")
    user_token_read_only: bool = True
    reply_in_thread: bool = True
    react_emoji: str = "eyes"
    group_policy: str = "mention"
    group_allow_from: list[str] = Field(default_factory=list)
    dm: SlackDMConfig = Field(default_factory=SlackDMConfig)

    @model_validator(mode="after")
    def _warn_policies(self) -> "SlackConfig":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="SlackConfig",
                field_name="mode",
                value=self.mode,
                allowed_values=get_args(SlackModeLiteral),
            )
        )
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="SlackConfig",
                field_name="group_policy",
                value=self.group_policy,
                allowed_values=get_args(SlackGroupPolicyLiteral),
            )
        )
        return self


class QQConfig(Base):
    enabled: bool = False
    app_id: str = ""
    secret: SecretStr = SecretStr("")
    allow_from: list[str] = Field(default_factory=list)


class IMessageConfig(Base):
    enabled: bool = False
    poll_interval: float = 2.0
    service: str = "iMessage"
    allow_from: list[str] = Field(default_factory=list)


class ChannelsConfig(Base):
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
