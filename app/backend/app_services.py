from __future__ import annotations

from PySide6.QtCore import Property, QObject


class AppServices(QObject):
    def __init__(
        self,
        *,
        chat_service: QObject,
        config_service: QObject,
        profile_service: QObject | None = None,
        session_service: QObject,
        cron_service: QObject,
        heartbeat_service: QObject | None = None,
        profile_supervisor_service: QObject | None = None,
        memory_service: QObject,
        skills_service: QObject,
        tools_service: QObject,
        update_service: QObject,
        diagnostics_service: QObject,
        update_bridge: QObject,
        desktop_preferences: QObject,
        messages_model: QObject,
        system_ui_language: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._chat_service = chat_service
        self._config_service = config_service
        self._profile_service = profile_service or QObject(self)
        self._session_service = session_service
        self._cron_service = cron_service
        self._heartbeat_service = heartbeat_service or QObject(self)
        self._profile_supervisor_service = profile_supervisor_service or QObject(self)
        self._memory_service = memory_service
        self._skills_service = skills_service
        self._tools_service = tools_service
        self._update_service = update_service
        self._diagnostics_service = diagnostics_service
        self._update_bridge = update_bridge
        self._desktop_preferences = desktop_preferences
        self._messages_model = messages_model
        self._system_ui_language = system_ui_language

    @Property(QObject, constant=True)
    def chatService(self) -> QObject:
        return self._chat_service

    @Property(QObject, constant=True)
    def configService(self) -> QObject:
        return self._config_service

    @Property(QObject, constant=True)
    def profileService(self) -> QObject:
        return self._profile_service

    @Property(QObject, constant=True)
    def sessionService(self) -> QObject:
        return self._session_service

    @Property(QObject, constant=True)
    def cronService(self) -> QObject:
        return self._cron_service

    @Property(QObject, constant=True)
    def heartbeatService(self) -> QObject:
        return self._heartbeat_service

    @Property(QObject, constant=True)
    def profileSupervisorService(self) -> QObject:
        return self._profile_supervisor_service

    @Property(QObject, constant=True)
    def memoryService(self) -> QObject:
        return self._memory_service

    @Property(QObject, constant=True)
    def skillsService(self) -> QObject:
        return self._skills_service

    @Property(QObject, constant=True)
    def toolsService(self) -> QObject:
        return self._tools_service

    @Property(QObject, constant=True)
    def updateService(self) -> QObject:
        return self._update_service

    @Property(QObject, constant=True)
    def diagnosticsService(self) -> QObject:
        return self._diagnostics_service

    @Property(QObject, constant=True)
    def updateBridge(self) -> QObject:
        return self._update_bridge

    @Property(QObject, constant=True)
    def desktopPreferences(self) -> QObject:
        return self._desktop_preferences

    @Property(QObject, constant=True)
    def messagesModel(self) -> QObject:
        return self._messages_model

    @Property(str, constant=True)
    def systemUiLanguage(self) -> str:
        return self._system_ui_language
