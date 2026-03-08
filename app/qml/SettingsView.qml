import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    color: "transparent"

    property var appRoot: null
    property bool onboardingMode: false
    property bool _pendingManualUpdateCheck: false
    property string updateStateUi: updateService ? updateService.state : "idle"
    property string updateErrorUi: updateService ? updateService.errorMessage : ""
    readonly property bool updateBusy: updateStateUi === "checking" || updateStateUi === "downloading" || updateStateUi === "installing"
    readonly property string updateActionText: updateBusy ? strings.update_action_checking : strings.update_action_check
    readonly property bool isZh: appRoot ? appRoot.effectiveLang === "zh" : false
    property var _providerList: []
    property bool _updateAutoCheckDraft: false
    property int _activeTab: 0
    property string _helpTitle: ""
    property var _helpSections: []
    property var _tabLabels: [
        {"label": tr("快速开始", "Quick Start")},
        {"label": tr("渠道", "Channels")},
        {"label": tr("高级", "Advanced")}
    ]
    property int _pendingTab: -1
    property int _tabDirection: 1
    property real _savedScrollY: -1
    property string _pendingExpandProviderName: ""
    property var _supportedUiLanguages: ["auto", "zh", "en"]
    property var _supportedThemeModes: ["system", "light", "dark"]
    property var _onboardingProviderApiKeyFieldRef: null
    property var _onboardingProviderTypeFieldRef: null
    property var _onboardingProviderApiBaseFieldRef: null
    readonly property string configFilePath: configService ? configService.getConfigFilePath() : ""
    readonly property bool languageConfigured: {
        if (!desktopPreferences)
            return false
        var value = desktopPreferences.uiLanguage
        return _isSupportedUiLanguage(value)
    }
    readonly property bool providerConfigured: _hasConfiguredProvider()
    readonly property bool modelConfigured: _hasConfiguredModel()
    readonly property var onboardingPrimaryProvider: _primaryProviderDraft()
    readonly property string onboardingDraftModel: {
        var field = onboardingPrimaryModelField
        if (field && field.currentValue !== undefined && field.currentValue !== null)
            return String(field.currentValue)
        if (!configService)
            return ""
        var value = configService.getValue("agents.defaults.model")
        return (typeof value === "string" && value !== "") ? value : ""
    }
    readonly property bool onboardingModelReady: onboardingDraftModel.trim() !== ""
    readonly property int onboardingCompletedCount: (languageConfigured ? 1 : 0)
                                                  + (providerConfigured ? 1 : 0)
                                                  + (modelConfigured ? 1 : 0)
    readonly property real onboardingProgress: onboardingCompletedCount / 3
    readonly property int onboardingStepIndex: {
        if (!languageConfigured)
            return 0
        if (!providerConfigured)
            return 1
        return 2
    }
    readonly property string onboardingUiLanguage: {
        if (!desktopPreferences)
            return "auto"
        var value = desktopPreferences.uiLanguage
        return _isSupportedUiLanguage(value) ? value : "auto"
    }
    readonly property string currentThemeMode: {
        if (!desktopPreferences)
            return "system"
        var value = desktopPreferences.themeMode
        return _isSupportedThemeMode(value) ? value : "system"
    }
    readonly property var onboardingProviderPresets: [
        {
            "id": "openai",
            "title": tr("OpenAI / 官方", "OpenAI / Official"),
            "subtitle": tr("最稳妥的默认起点", "The safest default starting point"),
            "type": "openai",
            "name": "openai",
            "apiBase": "",
            "accent": isZh ? "官方" : "Official"
        },
        {
            "id": "openrouter",
            "title": "OpenRouter",
            "subtitle": tr("一处接多模型，最省事", "One endpoint for many models"),
            "type": "openai",
            "name": "openrouter",
            "apiBase": "https://openrouter.ai/api/v1",
            "accent": tr("聚合", "Multi-model")
        },
        {
            "id": "anthropic",
            "title": tr("Claude 官方", "Official Claude"),
            "subtitle": tr("只在直连 Anthropic 时选", "Choose only for direct Anthropic"),
            "type": "anthropic",
            "name": "anthropic",
            "apiBase": "",
            "accent": "Claude"
        },
        {
            "id": "gemini",
            "title": tr("Gemini 官方", "Official Gemini"),
            "subtitle": tr("只在直连 Gemini 时选", "Choose only for direct Gemini"),
            "type": "gemini",
            "name": "gemini",
            "apiBase": "",
            "accent": "Gemini"
        },
        {
            "id": "custom",
            "title": tr("自定义兼容接口", "Custom compatible API"),
            "subtitle": tr("适合代理、自建或公司网关", "Best for proxies, self-hosting, or company gateways"),
            "type": "openai",
            "name": "primary",
            "apiBase": "",
            "accent": tr("自定义", "Custom")
        }
    ]
    readonly property var onboardingModelPresets: _suggestedModelPresets()

    function tr(zh, en) {
        return isZh ? zh : en
    }

    function _cloneValue(value) {
        return JSON.parse(JSON.stringify(value))
    }

    function _isSupportedUiLanguage(value) {
        return typeof value === "string" && _supportedUiLanguages.indexOf(value) >= 0
    }

    function _isSupportedThemeMode(value) {
        return typeof value === "string" && _supportedThemeModes.indexOf(value) >= 0
    }

    function _getProviderMap() {
        var providers = configService ? configService.getValue("providers") : null
        if (providers && typeof providers === "object" && !Array.isArray(providers))
            return providers
        return {}
    }

    function _nextProviderName() {
        var used = {}
        for (var i = 0; i < _providerList.length; i++) {
            if (_providerList[i] && _providerList[i].name)
                used[_providerList[i].name] = true
        }

        if (!used["primary"])
            return "primary"

        var idx = _providerList.length + 1
        var name = "provider" + idx
        while (used[name]) {
            idx += 1
            name = "provider" + idx
        }
        return name
    }

    function _mergeUiChanges(changes) {
        var hasUpdatePatch = false
        for (var key in changes) {
            if (key.indexOf("ui.update.") === 0) {
                hasUpdatePatch = true
                break
            }
        }
        if (!hasUpdatePatch)
            return

        var updateValue = configService ? configService.getValue("ui.update") : null
        var updateNode = (updateValue && typeof updateValue === "object" && !Array.isArray(updateValue))
                       ? _cloneValue(updateValue) : {}
        for (var updateKey in changes) {
            if (updateKey.indexOf("ui.update.") !== 0)
                continue
            updateNode[updateKey.substring("ui.update.".length)] = changes[updateKey]
            delete changes[updateKey]
        }
        changes["ui"] = {"update": updateNode}
    }

    function _translateError(msg) {
        if (msg.indexOf("token_required:") === 0) {
            var channel = msg.split(":")[1]
            var names = {"telegram": "Telegram", "discord": "Discord", "slack": "Slack"}
            var name = names[channel] || channel
            return tr(name + " 启用时需要填写 Token", name + " requires a token when enabled")
        }
        return msg
    }

    function _loadUpdateDraft() {
        var current = configService ? configService.getValue("ui.update.autoCheck") : undefined
        _updateAutoCheckDraft = current === true
    }

    function _rememberScrollPosition() {
        var flick = settingsScroll && settingsScroll.contentItem ? settingsScroll.contentItem : null
        if (flick && flick.contentY !== undefined)
            _savedScrollY = flick.contentY
    }

    function _restoreScrollPosition() {
        var flick = settingsScroll && settingsScroll.contentItem ? settingsScroll.contentItem : null
        if (!flick || _savedScrollY < 0 || flick.contentY === undefined || flick.contentHeight === undefined)
            return
        var maxY = Math.max(0, flick.contentHeight - flick.height)
        flick.contentY = Math.max(0, Math.min(maxY, _savedScrollY))
        _savedScrollY = -1
    }

    function _switchTab(index) {
        if (index === _activeTab)
            return
        _tabDirection = index > _activeTab ? 1 : -1
        _pendingTab = index
        tabSwitchAnim.restart()
    }

    function _reloadLocalState() {
        _loadProviders()
        _loadUpdateDraft()
    }

    function _hasConfiguredProvider() {
        var providers = _getProviderMap()
        for (var name in providers) {
            var provider = providers[name]
            if (provider && typeof provider === "object" && !Array.isArray(provider)) {
                var apiKey = provider.apiKey
                if (typeof apiKey === "string" && apiKey.trim() !== "")
                    return true
            }
        }
        return false
    }

    function _hasConfiguredModel() {
        if (!configService)
            return false
        var value = configService.getValue("agents.defaults.model")
        return typeof value === "string" && value.trim() !== ""
    }

    function _scrollToItem(item, topOffset) {
        if (!item || !settingsScroll || !settingsScroll.contentItem)
            return
        var flick = settingsScroll.contentItem
        var top = item.mapToItem(scrollContent, 0, 0).y
        var maxY = Math.max(0, flick.contentHeight - flick.height)
        var offset = (topOffset !== undefined && topOffset !== null) ? topOffset : 20
        flick.contentY = Math.max(0, Math.min(maxY, top - offset))
    }

    function _focusLanguageStep() {
        _scrollToItem(appSection)
    }

    function _focusProviderStep() {
        _scrollToItem(providerSection)
    }

    function _focusModelStep() {
        _scrollToItem(onboardingModelSection)
    }

    function _openOnboardingStep(step) {
        if (step === 0) {
            _focusLanguageStep()
            return
        }
        if (step === 1) {
            _focusProviderStep()
            return
        }
        _focusModelStep()
    }

    function _applyUiLanguageChoice(value) {
        return desktopPreferences ? desktopPreferences.setUiLanguage(value) : false
    }

    function _applyThemeModeChoice(value) {
        return desktopPreferences ? desktopPreferences.setThemeMode(value) : false
    }

    function _applyProviderPreset(preset) {
        if (!preset)
            return
        var nextProviders = []
        for (var i = 0; i < _providerList.length; i++)
            nextProviders.push(_cloneValue(_providerList[i]))

        var baseName = preset.name || "primary"
        var chosenName = baseName
        var suffix = 2
        var currentName = nextProviders.length > 0 && nextProviders[0] ? nextProviders[0].name : ""
        var used = {}
        for (var j = 0; j < nextProviders.length; j++) {
            var item = nextProviders[j]
            if (item && item.name && item.name !== currentName)
                used[item.name] = true
        }
        while (used[chosenName]) {
            chosenName = baseName + suffix
            suffix += 1
        }

        var providerDraft = {
            "name": chosenName,
            "type": preset.type || "openai",
            "apiKey": _currentOnboardingProviderApiKey(),
            "apiBase": preset.apiBase !== undefined ? preset.apiBase : (nextProviders.length > 0 && nextProviders[0] ? nextProviders[0].apiBase || "" : "")
        }

        if (nextProviders.length === 0)
            nextProviders.push(providerDraft)
        else
            nextProviders[0] = providerDraft

        _providerList = nextProviders
    }

    function _currentOnboardingProviderApiKey() {
        if (_onboardingProviderApiKeyFieldRef && _onboardingProviderApiKeyFieldRef.currentValue !== undefined)
            return _onboardingProviderApiKeyFieldRef.currentValue
        if (_providerList.length > 0 && _providerList[0] && _providerList[0].apiKey)
            return _providerList[0].apiKey
        return ""
    }

    function _syncOnboardingProviderFields(provider) {
        if (!root.onboardingMode || !provider)
            return
        if (_onboardingProviderApiKeyFieldRef)
            _onboardingProviderApiKeyFieldRef.setCurrentText(provider.apiKey || "")
        if (_onboardingProviderTypeFieldRef)
            _onboardingProviderTypeFieldRef.presetValue(provider.type || "openai")
        if (_onboardingProviderApiBaseFieldRef)
            _onboardingProviderApiBaseFieldRef.setCurrentText(provider.apiBase || "")
    }

    function _providerDisplayName(provider) {
        if (!provider || typeof provider !== "object")
            return tr("服务连接", "Service connection")
        var type = typeof provider.type === "string" ? provider.type : "openai"
        var apiBase = typeof provider.apiBase === "string" ? provider.apiBase.toLowerCase() : ""
        if (apiBase.indexOf("openrouter") >= 0)
            return "OpenRouter"
        if (type === "anthropic")
            return tr("Claude 官方", "Official Claude")
        if (type === "gemini")
            return tr("Gemini 官方", "Official Gemini")
        if (apiBase !== "")
            return tr("自定义兼容接口", "Custom compatible API")
        return tr("OpenAI / 官方", "OpenAI / Official")
    }

    function _primaryProviderDraft() {
        if (_providerList.length > 0 && _providerList[0])
            return _providerList[0]
        return {"type": "openai", "apiBase": ""}
    }

    function _normalizeProviderApiBase(value) {
        if (typeof value !== "string")
            return ""
        var normalized = value.trim().toLowerCase()
        while (normalized.length > 0 && normalized.charAt(normalized.length - 1) === "/")
            normalized = normalized.slice(0, normalized.length - 1)
        if (normalized === "https://api.openai.com" || normalized === "https://api.openai.com/v1")
            return ""
        if (normalized === "https://openrouter.ai/api" || normalized === "https://openrouter.ai/api/v1")
            return "https://openrouter.ai/api/v1"
        return normalized
    }

    function _liveOnboardingProviderDraft() {
        var provider = root.onboardingPrimaryProvider || {}
        var providerType = typeof provider.type === "string" ? provider.type : "openai"
        var providerApiBase = typeof provider.apiBase === "string" ? provider.apiBase : ""
        if (_onboardingProviderTypeFieldRef && _onboardingProviderTypeFieldRef.currentValue !== undefined && _onboardingProviderTypeFieldRef.currentValue !== null)
            providerType = String(_onboardingProviderTypeFieldRef.currentValue)
        if (_onboardingProviderApiBaseFieldRef && _onboardingProviderApiBaseFieldRef.currentValue !== undefined && _onboardingProviderApiBaseFieldRef.currentValue !== null)
            providerApiBase = String(_onboardingProviderApiBaseFieldRef.currentValue)
        return {
            "type": providerType,
            "apiBase": _normalizeProviderApiBase(providerApiBase)
        }
    }

    function _suggestedModelPresets() {
        var provider = _liveOnboardingProviderDraft()
        var type = provider && typeof provider.type === "string" ? provider.type : "openai"
        var apiBase = provider && typeof provider.apiBase === "string" ? provider.apiBase : ""
        if (type === "anthropic") {
            return [
                {"label": tr("Claude Sonnet", "Claude Sonnet"), "value": "anthropic/claude-sonnet-4-20250514", "hint": tr("最稳妥的 Claude 起点", "The safest Claude default")},
                {"label": tr("Claude Haiku", "Claude Haiku"), "value": "anthropic/claude-3-5-haiku-latest", "hint": tr("更轻更快", "Lighter and faster")},
                {"label": tr("自己填写", "Custom"), "value": "", "hint": tr("如果你知道自己的模型名", "If you already know your exact model name")}
            ]
        }
        if (type === "gemini") {
            return [
                {"label": tr("Gemini Flash", "Gemini Flash"), "value": "gemini/gemini-2.0-flash", "hint": tr("推荐先从这个开始", "Recommended default")},
                {"label": tr("Gemini Pro", "Gemini Pro"), "value": "gemini/gemini-1.5-pro", "hint": tr("更适合复杂任务", "Better for heavier tasks")},
                {"label": tr("自己填写", "Custom"), "value": "", "hint": tr("如果你知道自己的模型名", "If you already know your exact model name")}
            ]
        }
        if (apiBase.indexOf("openrouter") >= 0) {
            return [
                {"label": "GPT-4o", "value": "openai/gpt-4o", "hint": tr("OpenRouter 上最省心的起点", "An easy OpenRouter default")},
                {"label": tr("Claude Sonnet", "Claude Sonnet"), "value": "anthropic/claude-sonnet-4-20250514", "hint": tr("如果你更喜欢 Claude 风格", "If you prefer Claude-style answers")},
                {"label": tr("Gemini Flash", "Gemini Flash"), "value": "gemini/gemini-2.0-flash", "hint": tr("更快更轻量", "Faster and lighter")}
            ]
        }
        return [
            {"label": "GPT-4o", "value": "openai/gpt-4o", "hint": tr("推荐先从这个开始", "Recommended default")},
            {"label": "GPT-4.1 mini", "value": "openai/gpt-4.1-mini", "hint": tr("更轻更快", "Lighter and faster")},
            {"label": tr("自己填写", "Custom"), "value": "", "hint": tr("如果你有自己的模型名", "If you already have a model name")}
        ]
    }

    function _applyModelPreset(preset) {
        if (!preset || !onboardingPrimaryModelField)
            return
        if (preset.value === "") {
            activateCustomModelInput()
            return
        }
        onboardingPrimaryModelField.presetText(preset.value)
    }

    function activateCustomModelInput() {
        if (!onboardingPrimaryModelField)
            return
        onboardingModelManualField.expanded = true
        onboardingPrimaryModelField.setCurrentText("")
        _focusModelStep()
    }

    function _displayModelLabel(modelId) {
        if (typeof modelId !== "string" || modelId.trim() === "")
            return tr("还没选默认聊天 AI", "No default chat AI selected yet")
        var value = modelId.trim()
        if (value === "openai/gpt-4o")
            return "GPT-4o"
        if (value === "openai/gpt-4.1-mini")
            return "GPT-4.1 mini"
        if (value === "anthropic/claude-sonnet-4-20250514")
            return tr("Claude Sonnet", "Claude Sonnet")
        if (value === "anthropic/claude-3-5-haiku-latest")
            return tr("Claude Haiku", "Claude Haiku")
        if (value === "gemini/gemini-2.0-flash")
            return tr("Gemini Flash", "Gemini Flash")
        if (value === "gemini/gemini-1.5-pro")
            return tr("Gemini Pro", "Gemini Pro")
        var slash = value.lastIndexOf("/")
        return slash >= 0 ? value.slice(slash + 1) : value
    }

    function _providerPresetSelected(preset) {
        if (!preset)
            return false
        var provider = root._liveOnboardingProviderDraft()
        var providerType = typeof provider.type === "string" ? provider.type : "openai"
        var providerApiBase = typeof provider.apiBase === "string" ? provider.apiBase : ""
        var presetApiBase = _normalizeProviderApiBase(preset.apiBase)
        if (preset.id === "openrouter")
            return providerType === "openai" && providerApiBase === presetApiBase
        if (preset.id === "custom")
            return providerType === "openai" && providerApiBase !== "" && providerApiBase !== "https://openrouter.ai/api/v1"
        if (preset.type === "anthropic" || preset.type === "gemini")
            return providerType === preset.type
        return providerType === (preset.type || "openai") && providerApiBase === presetApiBase
    }

    function _modelPresetSelected(preset) {
        if (!preset)
            return false
        if (preset.value === "")
            return onboardingPrimaryModelField && onboardingPrimaryModelField.currentValue === ""
        return root.onboardingDraftModel === preset.value
    }

    function _commitChanges(changes) {
        _rememberScrollPosition()
        var ok = configService.save(changes)
        if (!ok) {
            _savedScrollY = -1
            return false
        }
        Qt.callLater(function() { root._restoreScrollPosition() })
        return true
    }

    function _saveChanges(changes, onSuccess) {
        if (!configService)
            return false
        _mergeUiChanges(changes)
        if (!_commitChanges(changes))
            return false
        if (updateBridge)
            updateBridge.reloadRequested()
        toast.show(strings.settings_saved_hint, true)
        if (onSuccess)
            onSuccess()
        return true
    }

    function _saveImmediate(changes, onSuccess) {
        if (!configService)
            return false
        if (!_commitChanges(changes))
            return false
        if (onSuccess)
            onSuccess()
        return true
    }

    function _saveSection(sectionBody, overrides, onSuccess) {
        var changes = {}
        collectFields(sectionBody, changes)
        if (overrides && typeof overrides === "object" && !Array.isArray(overrides)) {
            for (var overrideKey in overrides)
                changes[overrideKey] = overrides[overrideKey]
        }
        return _saveChanges(changes, onSuccess)
    }

    onUpdateStateUiChanged: {
        if (!_pendingManualUpdateCheck)
            return
        if (updateStateUi === "available") {
            _pendingManualUpdateCheck = false
            updateConfirmModal.open()
            return
        }
        if (updateStateUi === "up_to_date") {
            toast.show(strings.update_status_up_to_date, true)
            _pendingManualUpdateCheck = false
            return
        }
        if (updateStateUi === "error") {
            toast.show(updateErrorUi || strings.update_status_error, false)
            _pendingManualUpdateCheck = false
        }
    }
    onOnboardingPrimaryProviderChanged: _syncOnboardingProviderFields(onboardingPrimaryProvider)

    function _loadProviders() {
        if (!configService) return
        _providerList = configService.getProviders() || []
    }

    function _addNewProvider() {
        var name = _nextProviderName()
        var providerValue = {"type": "openai", "apiKey": ""}
        var nextProviders = []
        for (var i = 0; i < _providerList.length; i++)
            nextProviders.push(_providerList[i])
        nextProviders.push({
            "name": name,
            "type": providerValue.type,
            "apiKey": providerValue.apiKey,
            "apiBase": ""
        })
        _providerList = nextProviders
        _pendingExpandProviderName = name
    }

    function _removeProviderDraft(name) {
        var nextProviders = []
        for (var i = 0; i < _providerList.length; i++) {
            if (_providerList[i] && _providerList[i].name !== name)
                nextProviders.push(_providerList[i])
        }
        _providerList = nextProviders
    }

    function _saveProvidersSection(onSuccess) {
        var changes = {}
        collectFields(providerSectionBody, changes)
        var allProviders = _getProviderMap()
        var seenProviderNames = {}
        var nextProviders = {}
        for (var i = 0; i < root._providerList.length; i++) {
            var prefix = "_prov_" + i + "_"
            var original = root._providerList[i] || ({})
            var origName = original.name
            var requestedName = changes[prefix + "name"]
            var newName = origName
            if (requestedName !== undefined) {
                var trimmedName = String(requestedName).trim()
                if (trimmedName !== "") newName = trimmedName
            }
            if (seenProviderNames[newName]) {
                toast.show(tr("保存失败：提供商名称重复（" + newName + "）", "Save failed: duplicate provider name (" + newName + ")"), false)
                return
            }
            seenProviderNames[newName] = true

            var sourceProvider = original
            if (allProviders && typeof allProviders === "object" && !Array.isArray(allProviders)
                    && allProviders[origName] && typeof allProviders[origName] === "object") {
                sourceProvider = allProviders[origName]
            }

            var merged = _cloneValue(sourceProvider)
            if (merged["type"] === undefined || merged["type"] === null || merged["type"] === "") {
                merged["type"] = original.type || "openai"
            }
            if (merged["apiKey"] === undefined || merged["apiKey"] === null) {
                merged["apiKey"] = (original.apiKey !== undefined && original.apiKey !== null) ? original.apiKey : ""
            }
            delete merged["order"]

            var fieldNames = ["type", "apiKey", "apiBase"]
            for (var j = 0; j < fieldNames.length; j++) {
                var fk = prefix + fieldNames[j]
                if (changes[fk] !== undefined) {
                    merged[fieldNames[j]] = changes[fk]
                }
                delete changes[fk]
            }
            delete changes[prefix + "name"]

            nextProviders[newName] = merged
        }
        return _saveChanges({"providers": nextProviders}, function() {
            root._loadProviders()
            if (onSuccess)
                onSuccess()
        })
    }

    function saveOnboardingProviderStep() {
        return _saveProvidersSection(function() {
            if (root.onboardingMode)
                root._focusModelStep()
        })
    }

    function _openHelp(title, sections) {
        _helpTitle = title
        _helpSections = sections
        helpModal.open()
    }

    function _providerHelpSections() {
        return [
            {
                "title": tr("先完成这 3 项", "Start with these 3 items"),
                "body": tr(
                    "1. 先选一个 AI 服务预设。\n2. 大多数平台保持 openai；只有直连 Claude 或 Gemini 官方时再改。\n3. 填好 API Key，再到下一步选默认聊天 AI。",
                    "1. Start with one AI service preset.\n2. Keep openai for most services; only switch when using the official Claude or Gemini endpoints.\n3. Enter the API key, then move to the next step and choose the default chat AI."
                )
            },
            {
                "title": tr("每个字段是什么意思", "What each field means"),
                "body": tr(
                    "名称：你自己起的别名，只是给配置里区分用途。\n类型：决定 Bao 用哪套 SDK 协议。大多数第三方都选 openai。\nAPI 密钥：平台发给你的密钥，通常在 API Keys 页面生成。\nAPI 地址：官方或代理的基础地址；用官方默认就留空。",
                    "Name: your local alias in the config.\nType: selects the SDK protocol Bao should use. Most third-party services use openai.\nAPI Key: the secret generated by the platform, usually from an API Keys page.\nAPI Base URL: the official or proxy base endpoint; leave empty for the official default."
                )
            },
            {
                "title": tr("常见提供商怎么拿 Key", "Where to get common provider keys"),
                "body": tr(
                    "OpenAI：去 platform.openai.com → API Keys。\nAnthropic：去 console.anthropic.com → API Keys。\nGemini：去 aistudio.google.com → Get API key。\nOpenRouter：去 openrouter.ai/keys。\n如果你用硅基流动、DeepSeek、Groq、火山、DashScope、Moonshot、LM Studio、Ollama 之类，通常都按 openai 类型填写，并把它们提供的接口地址填到 API 地址。",
                    "OpenAI: platform.openai.com → API Keys.\nAnthropic: console.anthropic.com → API Keys.\nGemini: aistudio.google.com → Get API key.\nOpenRouter: openrouter.ai/keys.\nFor SiliconFlow, DeepSeek, Groq, Volcengine, DashScope, Moonshot, LM Studio, Ollama, and similar services, keep the type as openai and put their endpoint into API Base URL."
                )
            },
            {
                "title": tr("模型名怎么填", "How to fill model names"),
                "body": tr(
                    "默认聊天 AI 在 onboarding 第 3 步里选。最简单的方式是先点推荐卡片；如果你走代理平台，再按那个平台要求的模型名手动填写。",
                    "The default chat AI is chosen in onboarding step 3. The easiest path is using one of the recommended cards first; when you use a proxy or aggregator, manually enter the exact model name required by that service."
                )
            }
        ]
    }

    function _channelHelpSections() {
        return [
            {
                "title": tr("怎么启用一个渠道", "How to enable a channel"),
                "body": tr(
                    "先展开你要接入的渠道，填完必需字段，再打开开关并点击本卡保存。保存后重启网关生效。\n如果只是想先聊天，不需要立刻配所有渠道。新用户通常先配 Provider + 主模型就够了。",
                    "Expand one channel, fill the required fields, then turn it on and save that section. Restart the gateway after saving.\nIf you only want to start chatting, you do not need every channel right away. New users usually only need a provider plus a primary model."
                )
            },
            {
                "title": "Telegram / Discord / Slack",
                "body": tr(
                    "Telegram：去 @BotFather 创建机器人，拿到 Bot Token。\nDiscord：去 Discord Developer Portal 创建应用和 Bot，开启 Message Content Intent，拿 Bot Token。\nSlack：去 api.slack.com 创建 App，安装到工作区后拿 Bot Token；如果用 Socket Mode，还要再拿 App Token。",
                    "Telegram: create a bot via @BotFather and copy the Bot Token.\nDiscord: create an app in Discord Developer Portal, enable Message Content Intent, then copy the Bot Token.\nSlack: create an app on api.slack.com, install it to your workspace, copy the Bot Token, and add an App Token if you use Socket Mode."
                )
            },
            {
                "title": tr("WhatsApp / 飞书 / 钉钉 / QQ", "WhatsApp / Feishu / DingTalk / QQ"),
                "body": tr(
                    "WhatsApp：先部署 bridge，再把 bridge 地址填到 Bridge URL；如果 bridge 配了鉴权，再填 Bridge Token。\n飞书：去飞书开放平台创建应用，拿 App ID / App Secret；如启用事件订阅，再按后台提示配置 Encrypt Key / Verification Token。\n钉钉：去钉钉开放平台创建应用，拿 Client ID / Client Secret。\nQQ：去 QQ 开放平台创建机器人或应用，拿 App ID / Secret。",
                    "WhatsApp: deploy the bridge first, then enter its Bridge URL; fill Bridge Token only if the bridge requires auth.\nFeishu: create an app in the Feishu developer console and copy App ID / App Secret; add Encrypt Key / Verification Token when event subscriptions require them.\nDingTalk: create an app in DingTalk Open Platform and copy Client ID / Client Secret.\nQQ: create the bot/app in the QQ developer platform and copy App ID / Secret."
                )
            },
            {
                "title": tr("Email / iMessage / Mochat", "Email / iMessage / Mochat"),
                "body": tr(
                    "Email：准备好 IMAP/SMTP 地址、端口、用户名和密码；很多邮箱需要单独开启 IMAP，或使用应用专用密码。\niMessage：仅 macOS 可用，通常不需要 Key，只要设置轮询间隔、服务名和允许列表。\nMochat：按你自己的 Mochat/Claw 部署文档填写 Base URL、Token 和 Agent User ID。",
                    "Email: prepare IMAP/SMTP hosts, ports, usernames, and passwords; many providers require IMAP to be enabled or an app password.\niMessage: macOS only; usually no key is needed, only poll interval, service name, and allowlist.\nMochat: follow your own Mochat/Claw deployment docs for Base URL, Token, and Agent User ID."
                )
            },
            {
                "title": tr("Allow From 是什么", "What Allow From means"),
                "body": tr(
                    "Allow From 是白名单。只有列表里的用户、群组或邮箱可以和 Bao 通信。拿不准时可以先留空，确认跑通后再逐步收紧。",
                    "Allow From is the allowlist. Only the users, groups, or email addresses in the list can talk to Bao. If you are unsure, leave it empty first and lock it down after everything works."
                )
            }
        ]
    }

    function _agentHelpSections() {
        return [
            {
                "title": tr("这一块是干什么的", "What this section does"),
                "body": tr(
                    "这里决定 Bao 默认用哪个模型、怎么回复，以及新会话里默认启用哪些能力。你先填主模型就能开始聊天，其它项都可以之后再细调。",
                    "This section decides which model Bao uses by default, how it responds, and which abilities new chats start with. Filling the primary model is enough to get started; everything else can be tuned later."
                )
            },
            {
                "title": tr("最重要的是哪几项", "Which fields matter most"),
                "body": tr(
                    "主模型：最重要，Bao 平时聊天主要用它。\n轻量模型：做标题生成、经验提取这类后台小任务时更省钱。\n模型列表：聊天里可切换的候选模型，不填也能正常使用。",
                    "Primary Model: the most important field; Bao uses it for normal conversations.\nUtility Model: a cheaper model for background tasks such as title generation or experience extraction.\nModels: optional quick-switch choices available in chat; Bao still works if you leave this empty."
                )
            },
            {
                "title": tr("哪些先别动", "What to leave alone at first"),
                "body": tr(
                    "如果你是第一次配置，温度、最大 Token、上下文管理、推理强度这些先保持默认就好。等你已经能稳定聊天，再根据效果慢慢调。",
                    "If this is your first setup, leave Temperature, Max Tokens, Context Management, and Reasoning Effort at their defaults. Once chat works reliably, tune them based on the results you want."
                )
            }
        ]
    }

    function collectFields(item, changes) {
        if (!item || !item.children) return
        for (var i = 0; i < item.children.length; i++) {
            var child = item.children[i]
            if (child && typeof child.dotpath === "string" && child.dotpath !== "" && child.currentValue !== undefined) {
                var v = child.currentValue
                changes[child.dotpath] = v
            }
            // Traverse Loader loaded item for ChannelRow fields
            if (child && child.item) {
                var loaded = child.item
                if (typeof loaded.dotpath === "string" && loaded.dotpath !== "" && loaded.currentValue !== undefined) {
                    var lv = loaded.currentValue
                    changes[loaded.dotpath] = lv
                }
                collectFields(loaded, changes)
            }
            collectFields(child, changes)
        }
    }

    Component.onCompleted: _reloadLocalState()

    WheelHandler {
        id: settingsWheelProxy
        target: null
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function(event) {
            var flick = settingsScroll.contentItem
            if (!flick) return
            var maxY = Math.max(0, flick.contentHeight - flick.height)
            if (maxY <= 0) return
            var deltaY = event.pixelDelta.y !== 0 ? -event.pixelDelta.y : (-event.angleDelta.y / 3)
            var nextY = flick.contentY + deltaY
            if (nextY < 0) nextY = 0
            if (nextY > maxY) nextY = maxY
            flick.contentY = nextY
            event.accepted = true
        }
    }

    SequentialAnimation {
        id: tabSwitchAnim
        ParallelAnimation {
            NumberAnimation {
                target: pagesWrap
                property: "opacity"
                to: 0.12
                duration: 110
                easing.type: easeStandard
            }
            NumberAnimation {
                target: pagesWrap
                property: "x"
                to: -root._tabDirection * 30
                duration: 110
                easing.type: easeStandard
            }
        }
        ScriptAction {
            script: {
                if (root._pendingTab >= 0) {
                    root._activeTab = root._pendingTab
                    pagesWrap.x = root._tabDirection * 30
                }
            }
        }
        ParallelAnimation {
            NumberAnimation {
                target: pagesWrap
                property: "opacity"
                to: 1
                duration: 200
                easing.type: easeEmphasis
            }
            NumberAnimation {
                target: pagesWrap
                property: "x"
                to: 0
                duration: 200
                easing.type: easeEmphasis
            }
        }
        ScriptAction {
            script: {
                root._pendingTab = -1
                pagesWrap.x = 0
            }
        }
    }

    ScrollView {
        id: settingsScroll
        anchors.fill: parent
        contentWidth: scrollContent.width
        contentHeight: scrollContent.height
        ScrollBar.vertical.policy: ScrollBar.AlwaysOn
        clip: true

        Item {
            id: scrollContent
            width: settingsScroll.width
            height: innerCol.implicitHeight + 96
            implicitHeight: height

            ColumnLayout {
                id: innerCol
                width: Math.min(Math.max(settingsScroll.availableWidth - 64, 320), 820)
                height: implicitHeight
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top
                anchors.topMargin: root.onboardingMode ? 22 : 32
                spacing: root.onboardingMode ? spacingLg : spacingXl

                Rectangle {
                    visible: !root.onboardingMode
                    Layout.fillWidth: true
                    implicitHeight: 46
                    radius: 23
                    color: isDark ? "#12FFFFFF" : "#08000000"
                    border.color: borderSubtle
                    border.width: 1

                    readonly property real tabSpacing: 6
                    readonly property real trackPadding: 6
                    readonly property real segmentWidth: (width - (trackPadding * 2) - (tabSpacing * (_tabLabels.length - 1))) / _tabLabels.length

                    Rectangle {
                        id: tabHighlight
                        y: 6
                        height: parent.height - 12
                        width: parent.segmentWidth
                        x: 6 + (parent.segmentWidth + parent.tabSpacing) * root._activeTab
                        radius: height / 2
                        color: accent

                        Behavior on x { NumberAnimation { duration: 220; easing.type: easeEmphasis } }
                        Behavior on width { NumberAnimation { duration: 220; easing.type: easeStandard } }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 6
                        spacing: parent.tabSpacing

                        Repeater {
                            model: root._tabLabels

                            delegate: Rectangle {
                                required property int index
                                required property var modelData

                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                color: tabHover.containsMouse && root._activeTab !== index
                                       ? (isDark ? "#10FFFFFF" : "#08000000")
                                       : "transparent"
                                radius: 17

                                Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    color: root._activeTab === index ? "#FFFFFFFF" : textSecondary
                                    font.pixelSize: typeLabel
                                    font.weight: Font.DemiBold
                                }

                                MouseArea {
                                    id: tabHover
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root._switchTab(index)
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    id: pagesWrap
                    Layout.fillWidth: true
                    spacing: spacingXl

                SettingsSection {
                    id: onboardingHeroSection
                    Layout.fillWidth: true
                    visible: root.onboardingMode
                    title: tr("三步开始和 Bao 聊天", "Three quick steps to start chatting with Bao")
                    description: tr(
                        "首次使用只保留一条线：先选界面语言，再连一个 AI 服务，最后确认默认模型。完成后会自动进入聊天界面。",
                        "First launch now follows one path: choose your UI language, connect one AI service, then confirm the default model. Once done, the app drops you straight into chat."
                    )

                    ColumnLayout {
                        width: parent.width
                        spacing: spacingMd

                        CalloutPanel {
                            Layout.fillWidth: true
                            radius: radiusLg
                            padding: 14
                            panelColor: isDark ? "#12FFB33D" : "#10FFB33D"
                            panelBorderColor: isDark ? "#28FFD699" : "#20D0892C"
                            overlayVisible: true
                            overlayColor: isDark ? "#08FFFFFF" : "#10FFFFFF"
                            sideGlowVisible: true
                            sideGlowColor: isDark ? "#10FFFFFF" : "#0EFFFFFF"
                            sideGlowWidthFactor: 0.3
                            accentBlobVisible: true
                            accentBlobColor: isDark ? "#14FFD699" : "#10FFD699"
                            accentBlobWidthFactor: 0.2

                            ColumnLayout {
                                id: onboardingIntroCol
                                width: parent.width
                                spacing: 8

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 10

                                    Rectangle {
                                        implicitWidth: introBadge.implicitWidth + 18
                                        implicitHeight: 28
                                        radius: 14
                                        color: accent

                                        Text {
                                            id: introBadge
                                            anchors.centerIn: parent
                                            text: tr("新用户引导", "New user flow")
                                            color: "#FFFFFFFF"
                                            font.pixelSize: typeMeta
                                            font.weight: Font.DemiBold
                                            font.letterSpacing: letterWide
                                        }
                                    }

                                    Item { Layout.fillWidth: true }

                                    Text {
                                        text: onboardingCompletedCount + "/3"
                                        color: textSecondary
                                        font.pixelSize: typeLabel
                                        font.weight: weightDemiBold
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 16

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        Text {
                                            Layout.fillWidth: true
                                            text: tr("把 Bao 准备好，马上就能开始聊天", "Get Bao ready and start chatting in a minute")
                                            color: textPrimary
                                            font.pixelSize: typeTitle + 1
                                            font.weight: Font.Bold
                                            wrapMode: Text.WordWrap
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: tr("先选语言，再选一个 AI 服务，最后确认默认模型。做完就能直接开始聊天。", "Choose your language, pick one AI service, then confirm the default model. After that, you can start chatting right away.")
                                            color: textPrimary
                                            font.pixelSize: typeBody
                                            font.weight: weightMedium
                                            wrapMode: Text.WordWrap
                                        }

                                        Flow {
                                            width: parent.width
                                            spacing: spacingSm

                                            Repeater {
                                                model: [
                                                    tr("预计 1 分钟", "About 1 minute"),
                                                    tr("只要 1 个 AI 服务", "Only 1 AI service needed"),
                                                    tr("完成后自动进入聊天", "Auto-enters chat when done")
                                                ]

                                                delegate: Rectangle {
                                                    required property string modelData
                                                    implicitWidth: chipLabel.implicitWidth + 18
                                                    implicitHeight: 28
                                                    radius: 14
                                                    color: isDark ? "#12FFFFFF" : "#10FFFFFF"
                                                    border.color: isDark ? "#18FFFFFF" : "#12000000"
                                                    border.width: 1

                                                    Text {
                                                        id: chipLabel
                                                        anchors.centerIn: parent
                                                        text: modelData
                                                        color: textSecondary
                                                        font.pixelSize: typeMeta
                                                        font.weight: Font.DemiBold
                                                    }
                                                }
                                            }
                                        }
                                    }

                                    Rectangle {
                                        Layout.alignment: Qt.AlignTop
                                        Layout.preferredWidth: 92
                                        Layout.preferredHeight: 92
                                        radius: 46
                                        color: isDark ? "#0DFFFFFF" : "#10FFFFFF"
                                        border.color: isDark ? "#18FFFFFF" : "#14FFFFFF"
                                        border.width: 1

                                        Rectangle {
                                            width: 66
                                            height: 66
                                            radius: 33
                                            anchors.centerIn: parent
                                            color: isDark ? "#18FFB33D" : "#14FFB33D"
                                        }

                                        Image {
                                            anchors.centerIn: parent
                                            width: 52
                                            height: 52
                                            source: "../resources/logo-circle.png"
                                            fillMode: Image.PreserveAspectFit
                                            smooth: true
                                            antialiasing: true
                                        }
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 8
                                    radius: 4
                                    color: isDark ? "#10FFFFFF" : "#10000000"

                                    Rectangle {
                                        height: parent.height
                                        width: parent.width * onboardingProgress
                                        radius: parent.radius
                                        color: accent
                                        Behavior on width { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }
                                    }
                                }
                            }
                        }

                        Flow {
                            id: onboardingStepsFlow
                            width: parent.width
                            spacing: spacingMd

                            Repeater {
                                model: [
                                    {
                                        "step": 0,
                                        "title": tr("界面语言", "UI language"),
                                        "body": tr("先把界面切到你读起来最舒服的语言。", "Start by switching the interface to the language that feels natural to you."),
                                        "cta": tr("去选择", "Choose"),
                                        "done": root.languageConfigured,
                                        "current": root.onboardingStepIndex === 0
                                    },
                                    {
                                        "step": 1,
                                        "title": tr("选择 AI 服务", "Choose an AI service"),
                                        "body": tr("只要连好一个能用的服务和 API Key，就能继续下一步。", "You only need one working service and API key to move on."),
                                        "cta": tr("去连接", "Connect it"),
                                        "done": root.providerConfigured,
                                        "current": root.onboardingStepIndex === 1
                                    },
                                    {
                                        "step": 2,
                                        "title": tr("确认默认模型", "Confirm the default model"),
                                        "body": tr("选一个默认模型，保存后会自动回到聊天界面。", "Choose the default model and the app will drop you into chat after saving."),
                                        "cta": tr("去确认", "Confirm it"),
                                        "done": root.modelConfigured,
                                        "current": root.onboardingStepIndex === 2
                                    }
                                ]

                                delegate: OnboardingStepCard {
                                    required property var modelData
                                    readonly property bool compact: onboardingStepsFlow.width < 720

                                    width: compact
                                           ? onboardingStepsFlow.width
                                           : Math.floor((onboardingStepsFlow.width - (onboardingStepsFlow.spacing * 2)) / 3)
                                    stepNumber: modelData.step || 0
                                    overlineText: modelData.done === true ? tr("已完成", "Done") : (modelData.current === true ? tr("现在就做", "Do this now") : tr("接下来", "Up next"))
                                    title: modelData.title || ""
                                    description: modelData.body || ""
                                    ctaText: modelData.cta || ""
                                    done: modelData.done === true
                                    current: modelData.current === true
                                    onClicked: root._openOnboardingStep(modelData.step)
                                }
                            }
                        }
                    }
                }

                SettingsSection {
                    id: appSection
                    Layout.fillWidth: true
                    visible: root.onboardingMode || root._activeTab === 0
                    spotlight: root.onboardingMode && root.onboardingStepIndex === 0
                    title: root.onboardingMode ? tr("第 1 步 · 选择界面语言", "Step 1 · Choose your language") : strings.section_app
                    description: root.onboardingMode
                                 ? tr("这一步只决定界面看起来像中文还是 English，不影响后面的模型配置。", "This only changes how the app reads visually; it does not affect model setup.")
                                 : tr("先处理界面语言这类最直接的项目。", "Start with the most direct app-level preferences such as UI language.")

                    ColumnLayout {
                        id: appSectionBody
                        width: parent.width
                        spacing: 10

                        Text {
                            visible: root.onboardingMode
                            Layout.fillWidth: true
                            text: tr("选完会立刻生效，你后面随时还能改。", "The change applies immediately and you can switch again any time.")
                            color: textTertiary
                            font.pixelSize: typeMeta
                            wrapMode: Text.WordWrap
                        }

                        Flow {
                            visible: root.onboardingMode
                            width: parent.width
                            spacing: spacingSm

                            Repeater {
                                model: [
                                    {
                                        "value": "auto",
                                        "title": strings.ui_language_auto,
                                        "body": tr("跟着你的系统语言走，最省事。", "Follow your system language for the easiest start."),
                                        "accent": tr("推荐", "Recommended")
                                    },
                                    {
                                        "value": "zh",
                                        "title": strings.ui_language_zh,
                                        "body": tr("界面固定显示中文。", "Keep the interface in Chinese."),
                                        "accent": "ZH"
                                    },
                                    {
                                        "value": "en",
                                        "title": strings.ui_language_en,
                                        "body": tr("Keep the interface in English.", "Keep the interface in English."),
                                        "accent": "EN"
                                    }
                                ]

                                delegate: ChoiceCard {
                                    required property var modelData
                                    readonly property bool selectedCard: root.onboardingUiLanguage === modelData.value

                                    width: Math.max(170, Math.floor((appSectionBody.width - (spacingSm * 2)) / 3))
                                    badgeText: modelData.accent || ""
                                    title: modelData.title || ""
                                    description: modelData.body || ""
                                    trailingText: selectedCard ? tr("当前使用", "Selected") : ""
                                    selected: selectedCard
                                    onClicked: root._applyUiLanguageChoice(modelData.value)
                                }
                            }
                        }

                        SettingsCollapsible {
                            visible: root.onboardingMode
                            Layout.fillWidth: true
                            title: tr("手动选择语言", "Choose language manually")

                            ColumnLayout {
                                width: parent.width
                                spacing: spacingMd

                                SettingsSelect {
                                    label: strings.ui_language
                                    dotpath: ""
                                    initialValue: root.onboardingUiLanguage
                                    options: [
                                        {"label": strings.ui_language_auto, "value": "auto"},
                                        {"label": strings.ui_language_zh, "value": "zh"},
                                        {"label": strings.ui_language_en, "value": "en"}
                                    ]
                                    onValueChanged: function(v) {
                                        if (!_applyUiLanguageChoice(v))
                                            presetValue(root.onboardingUiLanguage)
                                    }
                                }

                                SettingsSelect {
                                    label: strings.ui_theme
                                    dotpath: ""
                                    initialValue: root.currentThemeMode
                                    options: [
                                        {"label": strings.ui_theme_system, "value": "system"},
                                        {"label": strings.ui_theme_light, "value": "light"},
                                        {"label": strings.ui_theme_dark, "value": "dark"}
                                    ]
                                    onValueChanged: function(v) {
                                        if (!_applyThemeModeChoice(v))
                                            presetValue(root.currentThemeMode)
                                    }
                                }
                            }
                        }

                        RowLayout {
                            visible: !root.onboardingMode
                            width: parent.width
                            spacing: spacingMd

                            SettingsSelect {
                                Layout.fillWidth: true
                                label: strings.ui_language
                                dotpath: ""
                                initialValue: root.onboardingUiLanguage
                                options: [
                                    {"label": strings.ui_language_auto, "value": "auto"},
                                    {"label": strings.ui_language_zh, "value": "zh"},
                                    {"label": strings.ui_language_en, "value": "en"}
                                ]
                                onValueChanged: function(v) {
                                    if (!_applyUiLanguageChoice(v))
                                        presetValue(root.onboardingUiLanguage)
                                }
                            }

                            SettingsSelect {
                                Layout.fillWidth: true
                                label: strings.ui_theme
                                dotpath: ""
                                initialValue: root.currentThemeMode
                                options: [
                                    {"label": strings.ui_theme_system, "value": "system"},
                                    {"label": strings.ui_theme_light, "value": "light"},
                                    {"label": strings.ui_theme_dark, "value": "dark"}
                                ]
                                onValueChanged: function(v) {
                                    if (!_applyThemeModeChoice(v))
                                        presetValue(root.currentThemeMode)
                                }
                            }
                        }
                    }
                }

                SettingsSection {
                    id: updatesSection
                    Layout.fillWidth: true
                    visible: !root.onboardingMode && root._activeTab === 2
                    title: strings.section_updates
                    description: tr("这里控制桌面 App 自己的更新检查，不影响聊天功能。", "These options control desktop app updates and do not affect chat behavior.")
                    actionText: strings.settings_save
                    actionHandler: function() {
                        root._saveSection(updatesSectionBody, {"ui.update.autoCheck": root._updateAutoCheckDraft}, function() {
                            root._loadUpdateDraft()
                        })
                    }

                    RowLayout {
                        id: updatesSectionBody
                        width: parent.width
                        Layout.fillWidth: true
                        spacing: 14

                        RowLayout {
                            spacing: 10

                            Text {
                                text: strings.update_auto_check
                                color: textSecondary
                                font.pixelSize: typeLabel
                                font.weight: weightMedium
                            }

                            ToggleSwitch {
                                checked: root._updateAutoCheckDraft
                                onToggled: function(checked) { root._updateAutoCheckDraft = checked }
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                            spacing: 12

                            Text {
                                text: strings.update_current_version + " " + (updateService ? updateService.currentVersion : "")
                                color: textSecondary
                                font.pixelSize: typeMeta
                                verticalAlignment: Text.AlignVCenter
                            }

                            AsyncActionButton {
                                text: root.updateActionText
                                busy: root.updateBusy
                                buttonEnabled: updateBridge !== null
                                minHeight: 30
                                horizontalPadding: 28
                                onClicked: {
                                    root._pendingManualUpdateCheck = true
                                    updateBridge.checkRequested()
                                }
                            }
                        }
                    }
                }

                SettingsSection {
                    id: agentSection
                    Layout.fillWidth: true
                    visible: !root.onboardingMode && root._activeTab === 0
                    title: strings.section_agent_defaults
                    description: tr("先填一个主模型，Bao 就能开始聊天；下面这些只是默认回复习惯。", "Set one primary model first; the rest only shapes Bao's default reply behavior.")
                    actionText: strings.settings_save
                    actionHandler: function() { root._saveSection(agentSectionBody) }
                    helpVisible: true
                    helpHandler: function() {
                        root._openHelp(tr("回复方式与模型说明", "Response Setup Guide"), root._agentHelpSections())
                    }

                    ColumnLayout {
                        id: agentSectionBody
                        width: parent.width
                        spacing: spacingMd

                        SettingsField { label: tr("工作目录", "Workspace Folder"); dotpath: "agents.defaults.workspace"; placeholder: "~/.bao/workspace" }
                        SettingsField { label: tr("默认聊天模型", "Primary Model"); dotpath: "agents.defaults.model"; placeholder: "openai/gpt-4o"; description: tr("Bao 平时聊天最常用的模型", "The model Bao uses for normal chats") }
                        SettingsField { label: tr("后台小任务模型", "Background Model"); dotpath: "agents.defaults.utilityModel"; placeholder: "openrouter/google/gemini-flash-1.5"; description: tr("做标题生成、经验整理这类后台任务时更省钱的模型", "A cheaper model for background tasks such as titles and summaries") }
                        SettingsField { label: tr("经验整理模型", "Learning Model"); dotpath: "agents.defaults.experienceModel"; placeholder: "utility / main / none"; description: tr("utility = 用后台模型 / main = 用主模型 / none = 关闭", "utility = use the background model / main = use the primary model / none = turn it off") }
                        SettingsListField { label: tr("聊天里可切换的模型", "Switchable Models"); dotpath: "agents.defaults.models"; placeholder: "model1, model2"; description: tr("聊天中通过 /model 可以切到这些模型，不填也可以", "Models you can switch to with /model in chat; optional") }

                        SettingsCollapsible {
                            Layout.fillWidth: true
                            title: tr("高级选项", "Advanced")

                            ColumnLayout {
                                width: parent.width
                                spacing: spacingMd

                                SettingsField { label: tr("单次回复上限", "Reply Length Limit"); dotpath: "agents.defaults.maxTokens"; placeholder: "8192"; inputType: "number"; description: tr("一条回复最多能输出多少内容", "How much one reply can generate at most") }
                                SettingsField { label: tr("稳定 / 发散程度", "Stability vs Variety"); dotpath: "agents.defaults.temperature"; placeholder: "0.1"; inputType: "number"; description: tr("越低越稳，越高越发散（0-2）", "Lower is steadier; higher is more varied (0-2)") }
                                SettingsField { label: tr("单轮最多调用工具次数", "Tool Call Limit Per Turn"); dotpath: "agents.defaults.maxToolIterations"; placeholder: "20"; inputType: "number"; description: tr("一轮对话里最多让 Bao 调多少次工具", "The maximum number of tool calls Bao can make in one turn") }
                                SettingsField { label: tr("短期记忆长度", "Recent Memory Size"); dotpath: "agents.defaults.memoryWindow"; placeholder: "50"; inputType: "number"; description: tr("保留最近多少条消息作为上下文", "How many recent messages Bao keeps as context") }
                                SettingsSelect {
                                    label: tr("长对话管理", "Long Chat Handling")
                                    dotpath: "agents.defaults.contextManagement"
                                    description: tr("对话很长时，Bao 怎么压缩和整理上下文", "How Bao trims and manages context in long conversations")
                                    options: [
                                        {"label": tr("关闭", "off"), "value": "off"},
                                        {"label": tr("观察", "observe"), "value": "observe"},
                                        {"label": tr("自动", "auto"), "value": "auto"},
                                        {"label": tr("激进", "aggressive"), "value": "aggressive"}
                                    ]
                                }
                                SettingsSelect {
                                    label: tr("深度思考强度", "Reasoning Depth")
                                    dotpath: "agents.defaults.reasoningEffort"
                                    description: tr("控制模型要不要多想一点；Auto = 交给模型自己判断", "Controls how much extra reasoning the model should use; Auto lets the model decide")
                                    options: [
                                        {"label": tr("自动", "Auto"), "value": null},
                                        {"label": "off", "value": "off"},
                                        {"label": "low", "value": "low"},
                                        {"label": "medium", "value": "medium"},
                                        {"label": "high", "value": "high"}
                                    ]
                                }
                                SettingsField { label: tr("工具结果预览长度", "Tool Preview Length"); dotpath: "agents.defaults.toolOutputPreviewChars"; placeholder: "3000"; inputType: "number"; description: tr("工具结果太长时，消息里先显示多少预览", "How much preview to keep in the message when tool output is long") }
                                SettingsField { label: tr("工具结果外置阈值", "Tool Offload Threshold"); dotpath: "agents.defaults.toolOutputOffloadChars"; placeholder: "8000"; inputType: "number"; description: tr("超过这个长度就自动存成文件，不全塞进对话", "Tool output longer than this is moved to a file instead of staying fully in chat") }
                                SettingsField { label: tr("开始压缩上下文的阈值", "Context Trim Threshold"); dotpath: "agents.defaults.contextCompactBytesEst"; placeholder: "240000"; inputType: "number"; description: tr("对话太长时，达到这个体量就开始压缩", "When the conversation grows past this size, Bao starts compacting it") }
                                SettingsField { label: tr("压缩时保留最近工具块", "Recent Tool Blocks to Keep"); dotpath: "agents.defaults.contextCompactKeepRecentToolBlocks"; placeholder: "4"; inputType: "number"; description: tr("压缩长对话时，保留最近几组工具调用", "How many recent tool call groups to keep when compacting") }
                                SettingsField { label: tr("临时产物保留天数", "Artifact Cleanup Days"); dotpath: "agents.defaults.artifactRetentionDays"; placeholder: "7"; inputType: "number"; description: tr("自动清理临时文件前保留多少天", "How many days temporary output files are kept before cleanup") }
                                SettingsToggle { label: tr("回复里显示进度提示", "Show Progress Updates"); dotpath: "agents.defaults.sendProgress" }
                                SettingsToggle { label: tr("回复里显示工具提示", "Show Tool Hints"); dotpath: "agents.defaults.sendToolHints" }
                            }
                        }
                    }
                }

                SettingsSection {
                    id: providerSection
                    Layout.fillWidth: true
                    visible: root.onboardingMode || root._activeTab === 0
                    spotlight: root.onboardingMode && root.onboardingStepIndex === 1
                    title: root.onboardingMode ? tr("第 2 步 · 选一个 AI 服务", "Step 2 · Pick one AI service") : strings.section_provider
                    description: root.onboardingMode
                                 ? tr("这里先只做一件事：连上一个能聊天的 AI 服务。大多数第三方平台都选 openai；只有直连 Claude 或 Gemini 官方时才改成对应类型。", "Keep this simple: connect one AI service that can chat. Most proxy and aggregator services stay on openai; switch only when you connect to the official Claude or Gemini endpoints.")
                                 : tr("先配一个能用的 Provider 就够了；其他供应商可以后面再加。", "One working provider is enough to get started; you can add others later.")
                    actionText: root.onboardingMode ? tr("保存服务连接", "Save connection") : strings.settings_save
                    actionHandler: function() { root.saveOnboardingProviderStep() }
                    helpVisible: true
                    helpHandler: function() {
                        root._openHelp(tr("AI 服务连接说明", "AI Service Connection Guide"), root._providerHelpSections())
                    }

                    ColumnLayout {
                        id: providerSectionBody
                        width: parent.width
                        spacing: spacingMd

                        Flow {
                            visible: root.onboardingMode
                            width: parent.width
                            spacing: spacingSm

                            Repeater {
                                model: root.onboardingProviderPresets

                                delegate: ChoiceCard {
                                    required property var modelData
                                    objectName: "onboardingProviderPreset_" + (modelData.id || "unknown")

                                    width: Math.max(170, Math.floor((providerSectionBody.width - (spacingSm * 2)) / 3))
                                    badgeText: modelData.accent || ""
                                    title: modelData.title || ""
                                    description: modelData.subtitle || ""
                                    trailingText: modelData.type || "openai"
                                    selected: root._providerPresetSelected(modelData)
                                    onClicked: root._applyProviderPreset(modelData)
                                }
                            }
                        }

                        CalloutPanel {
                            visible: root.onboardingMode
                            Layout.fillWidth: true
                            panelColor: root.providerConfigured ? (isDark ? "#1022C55E" : "#0F22C55E") : (isDark ? "#0CFFFFFF" : "#07000000")
                            panelBorderColor: root.providerConfigured ? (isDark ? "#3622C55E" : "#3022C55E") : borderSubtle

                            ColumnLayout {
                                id: providerIntro
                                width: parent.width
                                spacing: 6

                                Text {
                                    Layout.fillWidth: true
                                    text: root.providerConfigured
                                          ? tr("AI 服务已准备好", "AI service ready")
                                          : tr("只需要先连一个就够", "One service is enough")
                                    color: textPrimary
                                    font.pixelSize: typeLabel
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: root.providerConfigured
                                          ? tr("你已经有可用的 API Key 了。接下来只剩确认默认模型。", "You already have a working API key. The last step is confirming the default model.")
                                          : tr("如果不确定，先点上面的 OpenAI / 官方 或 OpenRouter 预设，再把 API Key 填进去。只有你用代理或公司网关时，才需要展开“自定义接口（可选）”。", "If you are unsure, start with the OpenAI / Official or OpenRouter preset above, then paste in the API key. Only expand Custom Endpoint when you use a proxy or company gateway.")
                                    color: textSecondary
                                    font.pixelSize: typeMeta
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        Repeater {
                            id: providerRepeater
                            model: root.onboardingMode ? [] : root._providerList

                            delegate: ProviderCardShell {
                                id: providerCard
                                property var provData: modelData || ({})

                                Component.onCompleted: {
                                    if (root._pendingExpandProviderName === (provData.name || "")) {
                                        expanded = true
                                        Qt.callLater(function() {
                                            root._scrollToItem(providerCard, 12)
                                            root._pendingExpandProviderName = ""
                                        })
                                    }
                                }

                                title: root.onboardingMode
                                       ? root._providerDisplayName(provData)
                                       : (provData.name || "")
                                typeText: provData.type || ""
                                removable: !(root.onboardingMode && root._providerList.length <= 1)
                                onRemoveClicked: if (provData.name) root._removeProviderDraft(provData.name)

                                SettingsField {
                                    visible: !root.onboardingMode
                                    label: tr("名称", "Name")
                                    placeholder: "openaiCompatible"
                                    dotpath: "_prov_" + index + "_name"
                                    Component.onCompleted: presetText(provData.name || "")
                                }
                                SettingsSelect {
                                    visible: !root.onboardingMode
                                    label: tr("类型", "Type")
                                    dotpath: "_prov_" + index + "_type"
                                    description: tr("大多数平台选 openai；只有 Claude 官方选 anthropic，Gemini 官方选 gemini。", "Choose openai for most services. Use anthropic only for official Claude, and gemini only for official Gemini.")
                                    options: [
                                        {"label": tr("openai - OpenAI / OpenRouter / DeepSeek / Groq", "openai - OpenAI / OpenRouter / DeepSeek / Groq"), "value": "openai"},
                                        {"label": tr("anthropic - Claude 官方", "anthropic - Official Claude"), "value": "anthropic"},
                                        {"label": tr("gemini - Gemini 官方", "gemini - Official Gemini"), "value": "gemini"}
                                    ]
                                    Component.onCompleted: presetValue(provData.type || "openai")
                                }
                                SettingsCollapsible {
                                    visible: root.onboardingMode
                                    Layout.fillWidth: true
                                    title: tr("更改连接方式（可选）", "Change connection mode (optional)")

                                    ColumnLayout {
                                        width: parent.width
                                        spacing: spacingMd

                                        SettingsSelect {
                                            label: tr("连接方式", "Connection mode")
                                            dotpath: "_prov_" + index + "_type"
                                            description: tr("默认不用动。只有你明确知道自己连的是 Claude 官方或 Gemini 官方时才改。", "You usually do not need to change this. Only switch when you know you are connecting to the official Claude or Gemini endpoints.")
                                            options: [
                                                {"label": tr("openai - 大多数服务", "openai - Most services"), "value": "openai"},
                                                {"label": tr("anthropic - Claude 官方", "anthropic - Official Claude"), "value": "anthropic"},
                                                {"label": tr("gemini - Gemini 官方", "gemini - Official Gemini"), "value": "gemini"}
                                            ]
                                            Component.onCompleted: presetValue(provData.type || "openai")
                                        }
                                    }
                                }
                                SettingsField {
                                    label: tr("API 密钥", "API Key")
                                    placeholder: "sk-..."
                                    dotpath: "_prov_" + index + "_apiKey"
                                    isSecret: true
                                    Component.onCompleted: presetText(provData.apiKey || "")
                                }
                                SettingsCollapsible {
                                    visible: root.onboardingMode
                                    Layout.fillWidth: true
                                    title: tr("自定义接口（可选）", "Custom endpoint (optional)")

                                    ColumnLayout {
                                        width: parent.width
                                        spacing: spacingMd

                                        SettingsField {
                                            label: tr("API 地址", "API Base URL")
                                            placeholder: tr("可留空；例如 https://api.openai.com/v1", "Optional; for example https://api.openai.com/v1")
                                            dotpath: "_prov_" + index + "_apiBase"
                                            description: tr("只在你用代理或自建服务时填写；官方默认通常可以留空。", "Only fill this when you use a proxy or self-hosted service. Official defaults can usually stay empty.")
                                            Component.onCompleted: presetText(provData.apiBase || "")
                                        }
                                    }
                                }
                                SettingsField {
                                    visible: !root.onboardingMode
                                    label: tr("API 地址", "API Base URL")
                                    placeholder: tr("可留空；例如 https://api.openai.com/v1", "Optional; for example https://api.openai.com/v1")
                                    dotpath: "_prov_" + index + "_apiBase"
                                    description: tr("只在你用代理或自建服务时填写；官方默认通常可以留空。", "Only fill this when you use a proxy or self-hosted service. Official defaults can usually stay empty.")
                                    Component.onCompleted: presetText(provData.apiBase || "")
                                }
                            }
                        }

                        SelectedProviderSummaryCard {
                            visible: root.onboardingMode && root._providerList.length > 0
                            title: root._providerDisplayName(root.onboardingPrimaryProvider)
                            description: root.providerConfigured
                                         ? tr("这个服务连接已经可用了。你可以直接继续下一步，或者在下面替换 API Key。", "This service connection is ready. You can continue to the next step or replace the API key below.")
                                         : tr("主路径只需要一件事：把这个服务的 API Key 粘进来。", "The main path only needs one thing: paste the API key for this service here.")
                            typeText: onboardingPrimaryProvider.type || "openai"
                            highlighted: root.providerConfigured

                            SettingsField {
                                id: onboardingProviderApiKeyField
                                objectName: "onboardingProviderApiKeyField"
                                label: tr("这个服务的 API Key", "API key for this service")
                                placeholder: "sk-..."
                                dotpath: "_prov_0_apiKey"
                                isSecret: true
                                description: tr("只填这一项就可以先继续。", "This is the only field you need to continue.")
                                Component.onCompleted: {
                                    presetText(root.onboardingPrimaryProvider.apiKey || "")
                                    root._onboardingProviderApiKeyFieldRef = onboardingProviderApiKeyField
                                }
                            }

                            SettingsCollapsible {
                                id: onboardingProviderDetailsCollapsible
                                objectName: "onboardingProviderDetailsCollapsible"
                                Layout.fillWidth: true
                                title: tr("需要的话，再改连接细节", "Change connection details only if needed")

                                ColumnLayout {
                                    width: parent.width
                                    spacing: spacingMd

                                    SettingsSelect {
                                        id: onboardingProviderTypeField
                                        objectName: "onboardingProviderTypeField"
                                        label: tr("连接方式", "Connection mode")
                                        dotpath: "_prov_0_type"
                                        description: tr("默认不用动。只有你确定自己连的是 Claude 官方或 Gemini 官方时才改。", "You usually do not need to change this. Only switch when you know you are connecting to the official Claude or Gemini endpoints.")
                                        options: [
                                            {"label": tr("openai - 大多数服务", "openai - Most services"), "value": "openai"},
                                            {"label": tr("anthropic - Claude 官方", "anthropic - Official Claude"), "value": "anthropic"},
                                            {"label": tr("gemini - Gemini 官方", "gemini - Official Gemini"), "value": "gemini"}
                                        ]
                                        Component.onCompleted: {
                                            presetValue(root.onboardingPrimaryProvider.type || "openai")
                                            root._onboardingProviderTypeFieldRef = onboardingProviderTypeField
                                        }
                                    }

                                    SettingsField {
                                        id: onboardingProviderApiBaseField
                                        objectName: "onboardingProviderApiBaseField"
                                        label: tr("自定义接口地址", "Custom endpoint URL")
                                        placeholder: tr("可留空；例如 https://api.openai.com/v1", "Optional; for example https://api.openai.com/v1")
                                        dotpath: "_prov_0_apiBase"
                                        description: tr("只有你用代理、自建服务或公司网关时才需要填写。", "Only needed for proxies, self-hosted services, or company gateways.")
                                        Component.onCompleted: {
                                            presetText(root.onboardingPrimaryProvider.apiBase || "")
                                            root._onboardingProviderApiBaseFieldRef = onboardingProviderApiBaseField
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            visible: !root.onboardingMode
                            Layout.fillWidth: true
                            height: root.onboardingMode && root._providerList.length === 0 ? 48 : 42
                            radius: radiusMd
                            color: root.onboardingMode && root._providerList.length === 0
                                   ? (addHover.containsMouse ? accentHover : accent)
                                   : (addHover.containsMouse ? (isDark ? "#0AFFFFFF" : "#08000000") : "transparent")
                            border.color: accent
                            border.width: 1
                            opacity: addHover.containsMouse ? 1.0 : 0.7

                            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                            Text {
                                anchors.centerIn: parent
                                text: root.onboardingMode && root._providerList.length === 0
                                      ? tr("+ 先添加第一个 Provider", "+ Add your first provider")
                                      : ("+ " + strings.section_provider_add)
                                color: root.onboardingMode && root._providerList.length === 0 ? "#FFFFFFFF" : accent
                                font.pixelSize: 13
                                font.weight: Font.Medium
                            }

                            MouseArea {
                                id: addHover
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.LeftButton
                                scrollGestureEnabled: false
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root._addNewProvider()
                            }
                        }
                    }
                }

                SettingsSection {
                    id: onboardingModelSection
                    Layout.fillWidth: true
                    visible: root.onboardingMode
                    spotlight: root.onboardingMode && root.onboardingStepIndex === 2
                    title: tr("第 3 步 · 选默认聊天 AI", "Step 3 · Pick your default chat AI")
                    description: root.providerConfigured
                                 ? tr("最后一步只要选一个你想先用来聊天的 AI；保存后如果上面的服务和 API Key 都有效，会自动进入聊天。", "The last step is choosing the AI you want to start chatting with. Once saved, the app automatically enters chat if the service and API key above are valid.")
                                 : tr("你也可以先把默认聊天 AI 选好，但真正生效前，先把上面的服务连接保存一下。", "You can choose the default chat AI now, but it only becomes usable after the service connection above is saved.")
                    actionText: root.providerConfigured
                                ? tr("保存并开始聊天", "Save and start chatting")
                                : tr("先保存上面的服务连接", "Save the connection above first")
                    actionEnabled: root.providerConfigured && root.onboardingModelReady
                    actionHandler: function() { root._saveSection(onboardingModelSectionBody) }

                    ColumnLayout {
                        id: onboardingModelSectionBody
                        width: parent.width
                        spacing: spacingMd

                        Flow {
                            visible: root.onboardingMode
                            width: parent.width
                            spacing: spacingSm

                            Repeater {
                                model: root.onboardingModelPresets

                                delegate: ChoiceCard {
                                    required property var modelData

                                    width: Math.max(170, Math.floor((onboardingModelSectionBody.width - (spacingSm * 2)) / 3))
                                    title: modelData.label || ""
                                    description: modelData.hint || ""
                                    selected: root._modelPresetSelected(modelData)
                                    onClicked: root._applyModelPreset(modelData)
                                }
                            }
                        }

                        CalloutPanel {
                            Layout.fillWidth: true
                            panelColor: root.modelConfigured ? (isDark ? "#1022C55E" : "#0F22C55E") : (isDark ? "#0CFFFFFF" : "#07000000")
                            panelBorderColor: root.modelConfigured ? (isDark ? "#3622C55E" : "#3022C55E") : borderSubtle

                            ColumnLayout {
                                id: modelIntro
                                width: parent.width
                                spacing: 6

                                Text {
                                    Layout.fillWidth: true
                                    text: root.onboardingDraftModel !== ""
                                          ? tr("你当前选的是：", "Your current choice is:")
                                          : tr("先从推荐卡片里选一个最省心的", "Start with one of the recommended cards")
                                    color: textPrimary
                                    font.pixelSize: typeLabel
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: root.onboardingDraftModel !== ""
                                          ? root._displayModelLabel(root.onboardingDraftModel) + " (" + root.onboardingDraftModel + ")"
                                          : tr("推荐卡已经按你上一步选的 AI 服务做了简化。只有你知道准确模型名时，才需要手动填写。", "The recommended cards are already simplified based on the AI service you picked above. Only enter a model manually when you already know the exact model name.")
                                    color: textSecondary
                                    font.pixelSize: typeMeta
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        SettingsCollapsible {
                            id: onboardingModelManualField
                            Layout.fillWidth: true
                            title: tr("我知道准确模型名，手动填写", "I know the exact model name")

                            ColumnLayout {
                                width: parent.width
                                spacing: spacingMd

                                SettingsField {
                                    id: onboardingPrimaryModelField
                                    objectName: "onboardingPrimaryModelField"
                                    label: tr("默认聊天 AI", "Default chat AI")
                                    dotpath: "agents.defaults.model"
                                    placeholder: "openai/gpt-4o"
                                    description: tr("只有你知道准确模型名时才需要手填。否则直接点上面的推荐卡片就够了。", "Only fill this when you already know the exact model name. Otherwise, using one of the recommended cards above is enough.")
                                }
                            }
                        }
                        SettingsCollapsible {
                            Layout.fillWidth: true
                            title: tr("可选：再省一点成本", "Optional: save a bit more on background tasks")

                            ColumnLayout {
                                width: parent.width
                                spacing: spacingMd

                                Text {
                                    Layout.fillWidth: true
                                    text: tr("这一项不是开始聊天所必需的。只有你想把标题生成、总结这类后台动作换成更便宜的模型时，再填这里。", "This is not required to start chatting. Only fill it when you want background actions like titles or summaries to use a cheaper model.")
                                    color: textTertiary
                                    font.pixelSize: typeMeta
                                    wrapMode: Text.WordWrap
                                }

                                SettingsField {
                                    label: tr("更省钱的后台 AI（可选）", "Cheaper background AI (optional)")
                                    dotpath: "agents.defaults.utilityModel"
                                    placeholder: "openrouter/google/gemini-flash-1.5"
                                    description: tr("留空也完全没问题。", "Leaving this empty is perfectly fine.")
                                }
                            }
                        }
                    }
                }

                SettingsSection {
                    id: channelsSection
                    Layout.fillWidth: true
                    visible: !root.onboardingMode && root._activeTab === 1
                    title: strings.section_channels
                    description: tr("只有你真正要接入的平台才需要配置；不使用的渠道可以完全不动。", "Only configure the platforms you actually plan to use; unused channels can stay untouched.")
                    actionText: strings.settings_save
                    actionHandler: function() { root._saveSection(channelsSectionBody) }
                    helpVisible: true
                    helpHandler: function() {
                        root._openHelp(tr("渠道接入说明", "Channel Setup Guide"), root._channelHelpSections())
                    }

                    ColumnLayout {
                        id: channelsSectionBody
                        width: parent.width
                        spacing: 18

                        ChannelRow {
                            width: parent.width
                            channelName: tr("Telegram", "Telegram")
                            enabledPath: "channels.telegram.enabled"
                            fields: [
                                {"label": tr("Bot Token", "Bot Token"), "dotpath": "channels.telegram.token", "placeholder": "123456:ABC-DEF...", "isSecret": true},
                                {"label": tr("代理", "Proxy"), "dotpath": "channels.telegram.proxy", "placeholder": "socks5://127.0.0.1:1080"},
                                {"label": tr("回复引用原消息", "Reply To Message"), "dotpath": "channels.telegram.replyToMessage", "placeholder": "true / false"},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.telegram.allowFrom", "placeholder": "123456789, @name", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("Discord", "Discord")
                            enabledPath: "channels.discord.enabled"
                            fields: [
                                {"label": tr("Bot Token", "Bot Token"), "dotpath": "channels.discord.token", "placeholder": "MTIz...", "isSecret": true},
                                {"label": tr("网关地址", "Gateway URL"), "dotpath": "channels.discord.gatewayUrl", "placeholder": "wss://gateway.discord.gg/?v=10&encoding=json"},
                                {"label": tr("意图位掩码", "Intents"), "dotpath": "channels.discord.intents", "placeholder": "37377", "inputType": "number"},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.discord.allowFrom", "placeholder": "user_id_1, user_id_2", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("WhatsApp", "WhatsApp")
                            enabledPath: "channels.whatsapp.enabled"
                            fields: [
                                {"label": tr("桥接地址", "Bridge URL"), "dotpath": "channels.whatsapp.bridgeUrl", "placeholder": "ws://localhost:3001"},
                                {"label": tr("桥接令牌", "Bridge Token"), "dotpath": "channels.whatsapp.bridgeToken", "placeholder": tr("可选", "optional"), "isSecret": true},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.whatsapp.allowFrom", "placeholder": "+8613800138000", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("飞书", "Feishu")
                            enabledPath: "channels.feishu.enabled"
                            fields: [
                                {"label": tr("应用 ID", "App ID"), "dotpath": "channels.feishu.appId", "placeholder": ""},
                                {"label": tr("应用密钥", "App Secret"), "dotpath": "channels.feishu.appSecret", "placeholder": "", "isSecret": true},
                                {"label": tr("加密 Key", "Encrypt Key"), "dotpath": "channels.feishu.encryptKey", "placeholder": tr("可选", "optional"), "isSecret": true},
                                {"label": tr("验证 Token", "Verification Token"), "dotpath": "channels.feishu.verificationToken", "placeholder": tr("可选", "optional"), "isSecret": true},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.feishu.allowFrom", "placeholder": "open_id_1, open_id_2", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("Slack", "Slack")
                            enabledPath: "channels.slack.enabled"
                            fields: [
                                {"label": tr("Bot Token", "Bot Token"), "dotpath": "channels.slack.botToken", "placeholder": "xoxb-...", "isSecret": true},
                                {"label": tr("App Token", "App Token"), "dotpath": "channels.slack.appToken", "placeholder": "xapp-...", "isSecret": true}
                            ]
                            advancedFields: [
                                {"label": tr("线程回复", "Reply In Thread"), "dotpath": "channels.slack.replyInThread", "placeholder": "true / false"},
                                {"label": tr("反应表情", "React Emoji"), "dotpath": "channels.slack.reactEmoji", "placeholder": "eyes"},
                                {"label": tr("群组策略", "Group Policy"), "dotpath": "channels.slack.groupPolicy", "placeholder": "mention / open / allowlist"},
                                {"label": tr("模式", "Mode"), "dotpath": "channels.slack.mode", "placeholder": "socket"},
                                {"label": tr("Webhook 路径", "Webhook Path"), "dotpath": "channels.slack.webhookPath", "placeholder": "/slack/events"},
                                {"label": tr("用户只读 Token", "User Token Read Only"), "dotpath": "channels.slack.userTokenReadOnly", "placeholder": "true / false"},
                                {"label": tr("群组允许列表", "Group Allow From"), "dotpath": "channels.slack.groupAllowFrom", "placeholder": "C123, C456", "isList": true},
                                {"label": tr("私信开关", "DM Enabled"), "dotpath": "channels.slack.dm.enabled", "placeholder": "true / false"},
                                {"label": tr("私信策略", "DM Policy"), "dotpath": "channels.slack.dm.policy", "placeholder": "open / allowlist"},
                                {"label": tr("私信允许列表", "DM Allow From"), "dotpath": "channels.slack.dm.allowFrom", "placeholder": "U123, U456", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("钉钉", "DingTalk")
                            enabledPath: "channels.dingtalk.enabled"
                            fields: [
                                {"label": tr("Client ID", "Client ID"), "dotpath": "channels.dingtalk.clientId", "placeholder": ""},
                                {"label": tr("Client Secret", "Client Secret"), "dotpath": "channels.dingtalk.clientSecret", "placeholder": "", "isSecret": true},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.dingtalk.allowFrom", "placeholder": "staff_id_1, staff_id_2", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("QQ", "QQ")
                            enabledPath: "channels.qq.enabled"
                            fields: [
                                {"label": tr("应用 ID", "App ID"), "dotpath": "channels.qq.appId", "placeholder": ""},
                                {"label": tr("密钥", "Secret"), "dotpath": "channels.qq.secret", "placeholder": "", "isSecret": true},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.qq.allowFrom", "placeholder": "openid1, openid2", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("邮件", "Email")
                            enabledPath: "channels.email.enabled"
                            fields: [
                                {"label": tr("IMAP 主机", "IMAP Host"), "dotpath": "channels.email.imapHost", "placeholder": "imap.gmail.com"},
                                {"label": tr("IMAP 端口", "IMAP Port"), "dotpath": "channels.email.imapPort", "placeholder": "993", "inputType": "number"},
                                {"label": tr("IMAP 用户名", "IMAP Username"), "dotpath": "channels.email.imapUsername", "placeholder": ""},
                                {"label": tr("IMAP 密码", "IMAP Password"), "dotpath": "channels.email.imapPassword", "placeholder": "", "isSecret": true},
                                {"label": tr("SMTP 主机", "SMTP Host"), "dotpath": "channels.email.smtpHost", "placeholder": "smtp.gmail.com"},
                                {"label": tr("SMTP 端口", "SMTP Port"), "dotpath": "channels.email.smtpPort", "placeholder": "587", "inputType": "number"},
                                {"label": tr("SMTP 用户名", "SMTP Username"), "dotpath": "channels.email.smtpUsername", "placeholder": ""},
                                {"label": tr("SMTP 密码", "SMTP Password"), "dotpath": "channels.email.smtpPassword", "placeholder": "", "isSecret": true},
                                {"label": tr("发件地址", "From Address"), "dotpath": "channels.email.fromAddress", "placeholder": ""},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.email.allowFrom", "placeholder": "alice@example.com, bob@example.com", "isList": true}
                            ]
                            advancedFields: [
                                {"label": tr("IMAP 邮箱", "IMAP Mailbox"), "dotpath": "channels.email.imapMailbox", "placeholder": "INBOX"},
                                {"label": tr("IMAP SSL", "IMAP Use SSL"), "dotpath": "channels.email.imapUseSsl", "placeholder": "true / false"},
                                {"label": tr("SMTP TLS", "SMTP Use TLS"), "dotpath": "channels.email.smtpUseTls", "placeholder": "true / false"},
                                {"label": tr("SMTP SSL", "SMTP Use SSL"), "dotpath": "channels.email.smtpUseSsl", "placeholder": "true / false"},
                                {"label": tr("授权确认", "Consent Granted"), "dotpath": "channels.email.consentGranted", "placeholder": "true / false"},
                                {"label": tr("自动回复", "Auto Reply Enabled"), "dotpath": "channels.email.autoReplyEnabled", "placeholder": "true / false"},
                                {"label": tr("轮询间隔秒", "Poll Interval Seconds"), "dotpath": "channels.email.pollIntervalSeconds", "placeholder": "30", "inputType": "number"},
                                {"label": tr("标记已读", "Mark Seen"), "dotpath": "channels.email.markSeen", "placeholder": "true / false"},
                                {"label": tr("正文最大字符", "Max Body Chars"), "dotpath": "channels.email.maxBodyChars", "placeholder": "12000", "inputType": "number"},
                                {"label": tr("主题前缀", "Subject Prefix"), "dotpath": "channels.email.subjectPrefix", "placeholder": "Re: "}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("iMessage", "iMessage")
                            enabledPath: "channels.imessage.enabled"
                            fields: [
                                {"label": tr("轮询间隔", "Poll Interval"), "dotpath": "channels.imessage.pollInterval", "placeholder": "2.0", "inputType": "number"},
                                {"label": tr("服务", "Service"), "dotpath": "channels.imessage.service", "placeholder": "iMessage"},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.imessage.allowFrom", "placeholder": "+8613800138000", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("Mochat", "Mochat")
                            enabledPath: "channels.mochat.enabled"
                            fields: [
                                {"label": tr("基础地址", "Base URL"), "dotpath": "channels.mochat.baseUrl", "placeholder": "https://mochat.io"},
                                {"label": tr("Claw 令牌", "Claw Token"), "dotpath": "channels.mochat.clawToken", "placeholder": "", "isSecret": true},
                                {"label": tr("Agent 用户 ID", "Agent User ID"), "dotpath": "channels.mochat.agentUserId", "placeholder": ""},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.mochat.allowFrom", "placeholder": "group1, group2", "isList": true}
                            ]
                            advancedFields: [
                                {"label": tr("Socket 地址", "Socket URL"), "dotpath": "channels.mochat.socketUrl", "placeholder": ""},
                                {"label": tr("Socket 路径", "Socket Path"), "dotpath": "channels.mochat.socketPath", "placeholder": "/socket.io"},
                                {"label": tr("禁用 Msgpack", "Disable Msgpack"), "dotpath": "channels.mochat.socketDisableMsgpack", "placeholder": "true / false", "inputType": "bool"},
                                {"label": tr("重连延迟毫秒", "Reconnect Delay Ms"), "dotpath": "channels.mochat.socketReconnectDelayMs", "placeholder": "1000", "inputType": "number"},
                                {"label": tr("最大重连延迟毫秒", "Max Reconnect Delay Ms"), "dotpath": "channels.mochat.socketMaxReconnectDelayMs", "placeholder": "10000", "inputType": "number"},
                                {"label": tr("连接超时毫秒", "Connect Timeout Ms"), "dotpath": "channels.mochat.socketConnectTimeoutMs", "placeholder": "10000", "inputType": "number"},
                                {"label": tr("刷新间隔毫秒", "Refresh Interval Ms"), "dotpath": "channels.mochat.refreshIntervalMs", "placeholder": "30000", "inputType": "number"},
                                {"label": tr("监视超时毫秒", "Watch Timeout Ms"), "dotpath": "channels.mochat.watchTimeoutMs", "placeholder": "25000", "inputType": "number"},
                                {"label": tr("监视上限", "Watch Limit"), "dotpath": "channels.mochat.watchLimit", "placeholder": "100", "inputType": "number"},
                                {"label": tr("重试延迟毫秒", "Retry Delay Ms"), "dotpath": "channels.mochat.retryDelayMs", "placeholder": "500", "inputType": "number"},
                                {"label": tr("最大重试次数", "Max Retry Attempts"), "dotpath": "channels.mochat.maxRetryAttempts", "placeholder": "0", "inputType": "number"},
                                {"label": tr("回复延迟模式", "Reply Delay Mode"), "dotpath": "channels.mochat.replyDelayMode", "placeholder": "off / non-mention"},
                                {"label": tr("回复延迟毫秒", "Reply Delay Ms"), "dotpath": "channels.mochat.replyDelayMs", "placeholder": "120000", "inputType": "number"},
                                {"label": tr("会话列表", "Sessions"), "dotpath": "channels.mochat.sessions", "placeholder": "session1, session2", "isList": true},
                                {"label": tr("面板列表", "Panels"), "dotpath": "channels.mochat.panels", "placeholder": "panel1, panel2", "isList": true}
                            ]
                        }
                    }
                }

                SettingsSection {
                    id: configFileSection
                    Layout.fillWidth: true
                    visible: !root.onboardingMode && root._activeTab === 2
                    title: tr("配置文件", "Configuration")
                    description: tr("Bao 的桌面配置保存在这里。需要手动编辑 JSONC 或排查问题时，可以直接打开目录。", "Bao stores its desktop configuration here. Open the folder when you need to edit the JSONC manually or inspect setup issues.")
                    actionText: tr("打开配置目录", "Open Config Folder")
                    actionEnabled: root.configFilePath !== ""
                    actionHandler: function() { configService.openConfigDirectory() }

                    ColumnLayout {
                        width: parent.width
                        spacing: 8

                        Text {
                            text: tr("当前配置文件", "Current config file")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: radiusMd
                            color: isDark ? "#0DFFFFFF" : "#06000000"
                            border.color: borderSubtle
                            border.width: 1
                            implicitHeight: configPathText.implicitHeight + 24

                            Text {
                                id: configPathText
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: 12
                                text: root.configFilePath
                                color: textPrimary
                                font.pixelSize: typeLabel
                                wrapMode: Text.WrapAnywhere
                            }
                        }
                    }
                }

                SettingsSection {
                    id: gatewaySection
                    Layout.fillWidth: true
                    visible: !root.onboardingMode && root._activeTab === 2
                    title: strings.section_gateway
                    description: tr("通常保持默认即可；只有你明确知道部署方式时再改。", "The defaults are usually fine; change these only when you know your deployment needs them.")
                    actionText: strings.settings_save
                    actionHandler: function() { root._saveSection(gatewaySectionBody) }

                    ColumnLayout {
                        id: gatewaySectionBody
                        width: parent.width
                        spacing: spacingMd

                        SettingsField { label: tr("主机", "Host"); dotpath: "gateway.host"; placeholder: "0.0.0.0" }
                        SettingsField { label: tr("端口", "Port"); dotpath: "gateway.port"; placeholder: "18790"; inputType: "number" }
                        SettingsToggle { label: tr("启用心跳", "Heartbeat Enabled"); dotpath: "gateway.heartbeat.enabled" }
                        SettingsField { label: tr("心跳间隔秒", "Heartbeat Interval Seconds"); dotpath: "gateway.heartbeat.intervalS"; placeholder: "1800"; inputType: "number" }
                    }
                }

                SettingsSection {
                    id: toolsSection
                    Layout.fillWidth: true
                    visible: !root.onboardingMode && root._activeTab === 2
                    title: strings.section_tools
                    description: tr("这些是增强功能，不影响最基本的聊天启动。", "These are optional enhancements and are not required for basic chat setup.")
                    actionText: strings.settings_save
                    actionHandler: function() { root._saveSection(toolsSectionBody) }

                    ColumnLayout {
                        id: toolsSectionBody
                        width: parent.width
                        spacing: spacingMd

                        Text {
                            text: tr("网页搜索", "Web Search")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        SettingsField { label: tr("搜索提供商", "Provider"); dotpath: "tools.web.search.provider"; placeholder: "tavily / brave" }
                        SettingsField { label: tr("Tavily API 密钥", "Tavily API Key"); dotpath: "tools.web.search.tavilyApiKey"; placeholder: "tvly-..."; isSecret: true }
                        SettingsField { label: tr("Brave API 密钥", "Brave API Key"); dotpath: "tools.web.search.braveApiKey"; placeholder: "BSA..."; isSecret: true }

                        Text {
                            text: tr("执行工具", "Exec")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsField { label: tr("超时秒数", "Timeout"); dotpath: "tools.exec.timeout"; placeholder: "60"; inputType: "number" }

                        Text {
                            text: tr("向量嵌入", "Embedding")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsField { label: tr("模型", "Model"); dotpath: "tools.embedding.model"; placeholder: "text-embedding-3-small" }
                        SettingsField { label: tr("API 密钥", "API Key"); dotpath: "tools.embedding.apiKey"; placeholder: "sk-..."; isSecret: true }
                        SettingsField { label: tr("基础地址", "Base URL"); dotpath: "tools.embedding.baseUrl"; placeholder: "https://api.openai.com/v1" }

                        SettingsField { label: tr("搜索最大结果数", "Web Search Max Results"); dotpath: "tools.web.search.maxResults"; placeholder: "5"; inputType: "number" }
                        SettingsField { label: tr("嵌入维度", "Embedding Dim"); dotpath: "tools.embedding.dim"; placeholder: "0"; inputType: "number" }

                        Text {
                            text: tr("图像生成", "Image Generation")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsField { label: tr("API 密钥", "API Key"); dotpath: "tools.imageGeneration.apiKey"; placeholder: "AIza..."; isSecret: true }
                        SettingsField { label: tr("模型", "Model"); dotpath: "tools.imageGeneration.model"; placeholder: "gemini-2.0-flash-exp-image-generation" }
                        SettingsField { label: tr("基础地址", "Base URL"); dotpath: "tools.imageGeneration.baseUrl"; placeholder: "https://generativelanguage.googleapis.com/v1beta" }
                        Text {
                            text: tr("桌面自动化", "Desktop Automation")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsToggle { label: tr("启用桌面操作", "Enable Desktop Control"); dotpath: "tools.desktop.enabled" }
                        SettingsToggle { label: tr("限制到工作区", "Restrict To Workspace"); dotpath: "tools.restrictToWorkspace" }
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                }
                }
            }
        }
    }

    AppToast {
        id: toast
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 24
        anchors.rightMargin: 24
        z: 21
        successBg: isDark ? "#1F7A4D" : "#16A34A"
        errorBg: isDark ? "#B84040" : "#DC2626"
        textColor: "#FFFFFF"
        duration: toastDurationLong
    }

    AppModal {
        id: helpModal
        z: 22
        darkMode: isDark
        title: root._helpTitle
        closeText: tr("我知道了", "Got it")

        Repeater {
            model: root._helpSections

            delegate: Rectangle {
                required property var modelData

                width: parent.width
                radius: radiusMd
                color: isDark ? "#0DFFFFFF" : "#08000000"
                border.color: borderSubtle
                border.width: 1
                implicitHeight: helpBlock.implicitHeight + 24

                Column {
                    id: helpBlock
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    spacing: 8

                    Text {
                        width: parent.width
                        text: modelData.title || ""
                        color: textPrimary
                        font.pixelSize: typeBody
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: modelData.body || ""
                        color: textSecondary
                        font.pixelSize: typeLabel
                        wrapMode: Text.WordWrap
                        lineHeight: 1.25
                    }
                }
            }
        }
    }

    AppModal {
        id: updateConfirmModal
        z: 23
        darkMode: isDark
        title: strings.update_modal_title
        showDefaultCloseAction: false
        maxModalWidth: 460
        maxModalHeight: 520

        Text {
            width: parent.width
            text: strings.update_latest_version + " " + (updateService ? updateService.latestVersion : "")
            color: textSecondary
            font.pixelSize: typeBody
            wrapMode: Text.WordWrap
            visible: updateService !== null && !!updateService.latestVersion
        }

        Text {
            width: parent.width
            text: updateService ? updateService.notesMarkdown : ""
            color: textSecondary
            font.pixelSize: typeMeta
            wrapMode: Text.WordWrap
            visible: updateService !== null && !!updateService.notesMarkdown
        }

        footer: [
            Item {
                Layout.fillWidth: true
            },
            Rectangle {
                implicitWidth: laterLabel.implicitWidth + 28
                implicitHeight: 38
                radius: 19
                color: dialogLater.containsMouse ? bgCardHover : "transparent"
                border.width: 1
                border.color: borderSubtle

                Text {
                    id: laterLabel
                    anchors.centerIn: parent
                    text: strings.update_modal_later
                    color: textSecondary
                    font.pixelSize: typeLabel
                    font.weight: Font.Medium
                }

                MouseArea {
                    id: dialogLater
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: updateConfirmModal.close()
                }
            },
            Rectangle {
                implicitWidth: installLabel.implicitWidth + 28
                implicitHeight: 38
                radius: 19
                color: dialogInstall.containsMouse ? accentHover : accent

                Text {
                    id: installLabel
                    anchors.centerIn: parent
                    text: strings.update_modal_install
                    color: "#FFFFFFFF"
                    font.pixelSize: typeLabel
                    font.weight: Font.DemiBold
                }

                MouseArea {
                    id: dialogInstall
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        updateConfirmModal.close()
                        if (updateBridge)
                            updateBridge.installRequested()
                    }
                }
            }
        ]
    }

    Connections {
        target: configService
        function onConfigLoaded() {
            root._reloadLocalState()
            Qt.callLater(function() { root._restoreScrollPosition() })
        }
        function onSaveError(msg) {
            toast.show(root._translateError(msg), false)
        }
    }
}
