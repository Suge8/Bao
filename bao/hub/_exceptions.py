"""Hub 异常体系"""
from __future__ import annotations


class HubError(Exception):
    """Hub 基础异常"""


class HubSessionNotFoundError(HubError):
    """Session 不存在"""


class HubRuntimeNotReadyError(HubError):
    """Runtime 未就绪"""


class HubDispatcherMissingError(HubError):
    """Dispatcher 缺少必需组件"""
