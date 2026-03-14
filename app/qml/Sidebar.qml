import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "sidebarRoot"

    property var chatService: null
    property var profileService: null
    property var sessionService: null
    property var supervisorService: null
    property var diagnosticsService: null
    property string selectionTarget: "sessions"
    readonly property bool settingsActive: selectionTarget === "settings"
    signal settingsRequested()
    signal diagnosticsRequested()
    signal newSessionRequested()
    signal sessionSelected(string key)
    signal sessionDeleteRequested(string key)
    signal sectionRequested(string section)

    color: "transparent"

    readonly property bool hasChatService: chatService !== null
    readonly property bool hasProfileService: profileService !== null && typeof profileService.activeProfileId !== "undefined"
    readonly property bool hasSessionService: sessionService !== null
    readonly property bool hasSupervisorService: supervisorService !== null
    readonly property bool hasDiagnosticsService: diagnosticsService !== null
    readonly property bool hasDiagnosticsCount: hasDiagnosticsService && typeof diagnosticsService.eventCount !== "undefined"
    readonly property var supervisorOverview: hasSupervisorService ? (supervisorService.overview || {}) : ({})
    readonly property string currentState: resolvedGatewayState()
    readonly property bool isRunning: currentState === "running"
    readonly property bool isStarting: currentState === "starting"
    readonly property bool isError: currentState === "error"
    readonly property bool isChinese: typeof effectiveLang === "string" ? effectiveLang === "zh" : uiLanguage === "zh"
    readonly property bool uiIsDark: isDark
    readonly property color uiBgCanvas: "transparent"
    readonly property color uiTextPrimary: textPrimary
    readonly property color uiTextSecondary: textSecondary
    readonly property color uiStatusSuccess: statusSuccess
    readonly property color uiStatusError: statusError
    readonly property color uiStatusWarning: statusWarning
    property string editingProfileId: ""
    property string editingProfileName: ""
    property var pendingDeleteProfile: ({
        "id": "",
        "displayName": "",
        "avatarKey": "mochi"
    })
    property var profilePopupHandle: null
    property real navHighlightY: 0.0
    property real navHighlightHeight: 50
    property real navHighlightOpacity: 0.0

    function sectionIconSource(section) {
        switch (section) {
        case "control_tower":
            return "../resources/icons/sidebar-control-tower-solid.svg"
        case "memory":
            return "../resources/icons/sidebar-memory.svg"
        case "skills":
            return "../resources/icons/sidebar-skills.svg"
        case "tools":
            return "../resources/icons/sidebar-tools.svg"
        case "cron":
            return "../resources/icons/sidebar-cron.svg"
        default:
            return themedIconSource("sidebar-sessions-title")
        }
    }

    function channelVisualSource(channel, filled) {
        switch (channel) {
        case "telegram":
            return "../resources/icons/channel-telegram.svg"
        case "discord":
            return "../resources/icons/channel-discord.svg"
        case "whatsapp":
            return "../resources/icons/channel-whatsapp.svg"
        case "feishu":
            return "../resources/icons/channel-feishu.svg"
        case "slack":
            return "../resources/icons/channel-slack.svg"
        case "qq":
            return "../resources/icons/channel-qq.svg"
        case "dingtalk":
            return "../resources/icons/channel-dingtalk.svg"
        case "imessage":
            return "../resources/icons/channel-imessage.svg"
        case "desktop":
            if (filled)
                return isDark
                       ? "../resources/icons/sidebar-monitor-solid-dark.svg"
                       : "../resources/icons/sidebar-monitor-solid.svg"
            return isDark ? "../resources/icons/sidebar-monitor-dark.svg" : "../resources/icons/sidebar-monitor.svg"
        case "subagent":
            return filled ? "../resources/icons/sidebar-subagent-solid.svg" : "../resources/icons/sidebar-subagent.svg"
        case "system":
            return filled ? "../resources/icons/sidebar-system-solid.svg" : "../resources/icons/sidebar-system.svg"
        case "heartbeat":
            return filled ? "../resources/icons/sidebar-heartbeat-solid.svg" : "../resources/icons/sidebar-heartbeat.svg"
        case "cron":
            return filled ? "../resources/icons/sidebar-cron-solid.svg" : "../resources/icons/sidebar-cron.svg"
        case "email":
            return filled ? "../resources/icons/sidebar-mail-solid.svg" : "../resources/icons/sidebar-mail.svg"
        default:
            return filled ? "../resources/icons/sidebar-chat-solid.svg" : "../resources/icons/sidebar-chat.svg"
        }
    }

    function channelIconSource(channel) {
        return channelVisualSource(channel, false)
    }

    function channelFilledIconSource(channel) {
        return channelVisualSource(channel, true)
    }

    function resolvedGatewayState() {
        if (!hasChatService)
            return "idle"
        if (typeof chatService.gatewayState === "string" && chatService.gatewayState !== "")
            return chatService.gatewayState
        if (typeof chatService.state === "string" && chatService.state !== "")
            return chatService.state
        return "idle"
    }

    function channelAccent(channel) {
        switch (channel) {
        case "telegram":
            return isDark ? Qt.rgba(0.33, 0.73, 1.0, 1.0) : Qt.rgba(0.00, 0.60, 0.96, 1.0)
        case "discord":
            return isDark ? Qt.rgba(0.56, 0.60, 1.0, 1.0) : Qt.rgba(0.39, 0.44, 1.0, 1.0)
        case "whatsapp":
            return isDark ? Qt.rgba(0.31, 0.90, 0.53, 1.0) : Qt.rgba(0.00, 0.78, 0.34, 1.0)
        case "feishu":
            return isDark ? Qt.rgba(0.54, 0.71, 1.0, 1.0) : Qt.rgba(0.17, 0.52, 0.98, 1.0)
        case "slack":
            return isDark ? Qt.rgba(0.99, 0.58, 0.76, 1.0) : Qt.rgba(0.83, 0.12, 0.44, 1.0)
        case "qq":
            return isDark ? Qt.rgba(0.61, 0.67, 1.0, 1.0) : Qt.rgba(0.24, 0.40, 0.98, 1.0)
        case "dingtalk":
            return isDark ? Qt.rgba(0.38, 0.74, 1.0, 1.0) : Qt.rgba(0.00, 0.62, 0.97, 1.0)
        case "imessage":
            return isDark ? Qt.rgba(0.54, 0.70, 1.0, 1.0) : Qt.rgba(0.12, 0.62, 1.0, 1.0)
        case "desktop":
            return isDark ? Qt.rgba(1.0, 0.78, 0.29, 1.0) : Qt.rgba(0.97, 0.63, 0.05, 1.0)
        case "subagent":
            return isDark ? Qt.rgba(1.0, 0.72, 0.24, 1.0) : Qt.rgba(0.96, 0.57, 0.00, 1.0)
        case "system":
            return isDark ? Qt.rgba(0.53, 0.82, 1.0, 1.0) : Qt.rgba(0.18, 0.67, 0.98, 1.0)
        case "heartbeat":
            return isDark ? Qt.rgba(0.20, 0.90, 0.56, 1.0) : Qt.rgba(0.00, 0.82, 0.40, 1.0)
        case "cron":
            return isDark ? Qt.rgba(1.0, 0.66, 0.18, 1.0) : Qt.rgba(0.99, 0.58, 0.00, 1.0)
        case "email":
            return isDark ? Qt.rgba(0.46, 0.69, 1.0, 1.0) : Qt.rgba(0.16, 0.56, 0.95, 1.0)
        default:
            return isDark ? Qt.rgba(0.79, 0.55, 1.0, 1.0) : Qt.rgba(0.52, 0.27, 0.84, 1.0)
        }
    }

    function profileAvatarSource(key) {
        var avatarKey = String(key || "mochi")
        return "../resources/profile-avatars/" + avatarKey + ".svg"
    }

    function beginRenameProfile(profileId, displayName) {
        var nextId = String(profileId || "").trim()
        if (!nextId.length)
            return
        if (editingProfileId === nextId) {
            cancelRenameProfile()
            return
        }
        editingProfileId = nextId
        editingProfileName = String(displayName || "").trim()
    }

    function cancelRenameProfile() {
        editingProfileId = ""
        editingProfileName = ""
    }

    function submitRenameProfile() {
        var profileId = String(editingProfileId || "").trim()
        var displayName = String(editingProfileName || "").trim()
        if (!profileId.length || !displayName.length || !hasProfileService)
            return
        profileService.renameProfile(profileId, displayName)
        cancelRenameProfile()
    }

    function closeProfilePopup() {
        if (profilePopupHandle !== null)
            profilePopupHandle.close()
    }

    function toggleProfilePopup() {
        if (profilePopupHandle === null)
            return
        if (profilePopupHandle.opened)
            profilePopupHandle.close()
        else
            profilePopupHandle.open()
    }

    function focusProfileRenameEditor(editor) {
        if (!editor)
            return
        editor.forceActiveFocus()
        editor.selectAll()
    }

    function clearPendingDeleteProfile() {
        pendingDeleteProfile = {
            "id": "",
            "displayName": "",
            "avatarKey": "mochi"
        }
    }

    function requestDeleteProfile(profileId, displayName, avatarKey) {
        var nextId = String(profileId || "").trim()
        if (!nextId.length)
            return
        cancelRenameProfile()
        pendingDeleteProfile = {
            "id": nextId,
            "displayName": String(displayName || nextId),
            "avatarKey": String(avatarKey || "mochi")
        }
        closeProfilePopup()
        deleteProfileModal.open()
    }

    function confirmDeleteProfile() {
        var profileId = String((pendingDeleteProfile || {}).id || "").trim()
        if (!profileId.length || !hasProfileService)
            return
        profileService.deleteProfile(profileId)
        deleteProfileModal.close()
    }

    function containsItemPoint(item, x, y) {
        if (!item || !item.visible)
            return false
        var point = item.mapFromItem(root, x, y)
        return item.contains(point)
    }

    function activeNavTarget() {
        switch (selectionTarget) {
        case "control_tower":
            return null
        case "memory":
            return memoryNavItem
        case "skills":
            return skillsNavItem
        case "tools":
            return toolsNavItem
        case "cron":
            return cronNavItem
        case "settings":
            return null
        default:
            return sessionsNavItem
        }
    }

    function updateNavHighlight() {
        var target = activeNavTarget()
        if (!target) {
            navHighlightOpacity = 0.0
            return
        }
        navHighlightY = navContent.y + target.y
        navHighlightHeight = target.height
        navHighlightOpacity = 1.0
    }

    onSelectionTargetChanged: Qt.callLater(function() {
        root.updateNavHighlight()
        root.cancelRenameProfile()
        root.closeProfilePopup()
        deleteProfileModal.close()
    })
    Component.onCompleted: Qt.callLater(function() { root.updateNavHighlight() })

    Rectangle {
        anchors.fill: parent
        radius: 24
        color: bgSidebar
        antialiasing: true

        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: parent.radius
            color: parent.color
        }

        Rectangle {
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            width: parent.radius
            color: parent.color
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: gwCapsule
            objectName: "gatewayCapsule"
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            Layout.topMargin: 16
            Layout.bottomMargin: 0
            implicitHeight: sizeCapsuleHeight
            radius: height / 2
            visible: hasChatService

            property string currentState: root.currentState
            property bool isRunning: root.isRunning
            property bool isStarting: root.isStarting
            property bool isError: root.isError
            property bool isIdleVisual: !isRunning && !isStarting && !isError
            property string previousState: currentState
            property bool isHovered: gwHover.containsMouse
            property real actionPulse: 0.0
            property real iconLift: 0.0
            property real iconPulse: 0.0
            property real iconTurn: 0.0
            property real pacmanMouth: 0.2
            property real pacmanPhase: 0.0
            readonly property int stateTransitionDuration: motionPanel + 40
            readonly property real pacmanMouthRest: 0.2
            readonly property real pacmanMouthWide: 0.34
            readonly property real pacmanMouthClosed: 0.06
            property string displayedPrimaryLabel: primaryLabel
            property string outgoingPrimaryLabel: ""
            property real primaryLabelTransition: 1.0
            readonly property var gatewayStateSpecs: ({
                "running": {
                    surfaceColor: gatewaySurfaceRunningTop,
                    statusColor: gatewayTextRunning,
                    actionColor: statusSuccess,
                    dotColor: statusSuccess,
                    primaryLabel: strings.gateway_running,
                    actionIconSource: ""
                },
                "error": {
                    surfaceColor: gatewaySurfaceErrorTop,
                    statusColor: statusError,
                    actionColor: statusError,
                    dotColor: statusError,
                    primaryLabel: strings.gateway_error,
                    actionIconSource: "../resources/icons/gateway-error.svg"
                },
                "starting": {
                    surfaceColor: gatewaySurfaceStartingTop,
                    statusColor: gatewayTextStarting,
                    actionColor: statusWarning,
                    dotColor: statusWarning,
                    primaryLabel: strings.gateway_starting,
                    actionIconSource: "../resources/icons/gateway-starting.svg"
                },
                "idle": {
                    surfaceColor: gatewaySurfaceIdleTop,
                    statusColor: gatewayTextIdle,
                    actionColor: accent,
                    dotColor: accent,
                    primaryLabel: strings.button_start_gateway,
                    actionIconSource: "../resources/icons/gateway-idle.svg"
                }
            })
            readonly property var stateSpec: gatewayStateSpecs[currentState] || gatewayStateSpecs.idle
            property color surfaceColor: stateSpec.surfaceColor
            property color statusColor: stateSpec.statusColor
            property color actionColor: stateSpec.actionColor
            property color dotColor: stateSpec.dotColor
            property string primaryLabel: stateSpec.primaryLabel
            property string actionIconSource: stateSpec.actionIconSource
            readonly property bool useRunningPacman: currentState === "running"
            property string detailText: hasChatService ? (chatService.gatewayDetail || "") : ""
            property var gatewayChannels: hasChatService ? (chatService.gatewayChannels || []) : []
            property bool hasErrorDetail: hasChatService ? Boolean(chatService.gatewayDetailIsError) : false
            z: 6

            function resetVisualState() {
                applyVisualSeed(0.0, 0.0, 0.0, 0.0)
                gwCapsule.pacmanMouth = pacmanMouthRest
                gwCapsule.pacmanPhase = 0.0
            }
            function applyVisualSeed(actionPulseValue, iconLiftValue, iconPulseValue, iconTurnValue) {
                gwCapsule.actionPulse = actionPulseValue
                gwCapsule.iconLift = iconLiftValue
                gwCapsule.iconPulse = iconPulseValue
                gwCapsule.iconTurn = iconTurnValue
                gwDot.opacity = 1.0
                gwDot.scale = 1.0
            }
            function transitionPrimaryLabel(nextLabel) {
                if (displayedPrimaryLabel === nextLabel)
                    return
                outgoingPrimaryLabel = displayedPrimaryLabel
                displayedPrimaryLabel = nextLabel
                primaryLabelTransition = 0.0
                primaryLabelTransitionAnim.restart()
            }
            function handoffVisualState() {
                if (gwCapsule.previousState === gwCapsule.currentState)
                    return

                if (gwCapsule.previousState === "starting" && gwCapsule.currentState === "running") {
                    applyVisualSeed(Math.max(gwCapsule.actionPulse, 0.03), -0.18, Math.max(gwCapsule.iconPulse, 0.05), 2.2)
                    gwCapsule.pacmanMouth = 0.26
                    gwCapsule.previousState = gwCapsule.currentState
                    return
                }

                if (gwCapsule.previousState === "starting") {
                    applyVisualSeed(Math.max(gwCapsule.actionPulse, 0.02), 0.0, Math.max(gwCapsule.iconPulse, 0.03), 0.0)
                    gwCapsule.previousState = gwCapsule.currentState
                    return
                }

                if (gwCapsule.currentState === "starting") {
                    applyVisualSeed(Math.max(gwCapsule.actionPulse, 0.04), 0.0, Math.max(gwCapsule.iconPulse, 0.04), gwCapsule.iconTurn)
                    gwCapsule.previousState = gwCapsule.currentState
                    return
                }

                resetVisualState()
                gwCapsule.previousState = gwCapsule.currentState
            }
            function triggerGatewayAction() {
                if (!hasChatService || gwCapsule.isStarting)
                    return
                if (gwCapsule.isRunning)
                    chatService.stop()
                else
                    chatService.start()
            }

            onCurrentStateChanged: handoffVisualState()
            onPrimaryLabelChanged: transitionPrimaryLabel(primaryLabel)
            activeFocusOnTab: true
            Component.onCompleted: displayedPrimaryLabel = primaryLabel
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    gwCapsule.triggerGatewayAction()
                    event.accepted = true
                }
            }
            color: gwCapsule.surfaceColor
            border.width: activeFocus ? 1.5 : 0
            border.color: activeFocus ? borderFocus : "transparent"
            scale: gwHover.pressed ? 0.985 : (gwCapsule.isHovered ? motionHoverScaleSubtle : 1.0)

            Behavior on actionPulse { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeSoft } }
            Behavior on iconLift { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeSoft } }
            Behavior on iconPulse { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeSoft } }
            Behavior on iconTurn { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeSoft } }
            Behavior on color { ColorAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeStandard } }
            Behavior on border.color { ColorAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeStandard } }
            Behavior on scale { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeEmphasis } }

            NumberAnimation {
                id: primaryLabelTransitionAnim
                target: gwCapsule
                property: "primaryLabelTransition"
                from: 0.0
                to: 1.0
                duration: gwCapsule.stateTransitionDuration
                easing.type: easeSoft
            }

            Item {
                anchors.fill: parent

                Rectangle {
                    id: gwAction
                    anchors.right: parent.right
                    anchors.rightMargin: 22
                    anchors.verticalCenter: parent.verticalCenter
                    width: sizeGatewayAction
                    height: sizeGatewayAction
                    radius: width / 2
                    antialiasing: true
                    color: Qt.darker(gwCapsule.actionColor, isDark ? 1.22 : 1.14)
                    border.width: 0
                    scale: (gwHover.pressed ? 0.97 : (gwCapsule.isHovered ? motionHoverScaleSubtle : 1.0)) + gwCapsule.actionPulse * 0.025
                    Behavior on color { ColorAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeStandard } }
                    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                    Rectangle {
                        id: gwActionFace
                        width: parent.width - 2
                        height: width
                        radius: width / 2
                        anchors.centerIn: parent
                        color: gwCapsule.actionColor
                        Behavior on color { ColorAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeStandard } }
                    }

                    Rectangle {
                        id: gwActionRing
                        width: gwActionFace.width
                        height: width
                        radius: width / 2
                        anchors.centerIn: gwActionFace
                        color: "transparent"
                        border.width: 1.4
                        border.color: gwCapsule.isError ? "#66FFF7F6" : (gwCapsule.isRunning ? "#7AF7FFF9" : "#72FFFFFF")
                        opacity: gwCapsule.isIdleVisual ? 0.08 : (0.18 + gwCapsule.actionPulse * 2.2)
                        scale: 1.0 + gwCapsule.actionPulse * (gwCapsule.isStarting ? 1.25 : 0.9)
                        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeSoft } }
                        Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeSoft } }
                        Behavior on border.color { ColorAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeStandard } }
                    }

                    SequentialAnimation {
                        running: gwCapsule.isRunning
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.075; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.0; duration: motionBreath; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isStarting
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.14; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isError
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.09; duration: motionStatusPulse; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.0; duration: motionStatusPulse; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isIdleVisual
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: -0.55; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isIdleVisual
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.045; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isIdleVisual
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconTurn"; to: 3; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconTurn"; to: 0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isStarting
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.13; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    NumberAnimation {
                        target: gwCapsule
                        property: "iconTurn"
                        from: 0
                        to: 360
                        duration: motionFloat
                        loops: Animation.Infinite
                        easing.type: easeLinear
                        running: gwCapsule.isStarting
                    }
                    SequentialAnimation {
                        running: gwCapsule.isRunning
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: -0.45; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: 0.45; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: 0.0; duration: motionBreath; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isRunning
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.085; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.02; duration: motionBreath; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isRunning
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "pacmanMouth"; to: gwCapsule.pacmanMouthWide; duration: 220; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "pacmanMouth"; to: gwCapsule.pacmanMouthClosed; duration: 140; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "pacmanMouth"; to: gwCapsule.pacmanMouthRest; duration: 120; easing.type: easeSoft }
                    }
                    NumberAnimation {
                        target: gwCapsule
                        property: "pacmanPhase"
                        from: 0.0
                        to: 1.0
                        duration: 480
                        loops: Animation.Infinite
                        easing.type: easeLinear
                        running: gwCapsule.isRunning
                    }
                    SequentialAnimation {
                        running: gwCapsule.isError
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.07; duration: motionStatusPulse; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionStatusPulse; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isError
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconTurn"; to: 4; duration: motionStatusPulse; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconTurn"; to: -4; duration: motionStatusPulse; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconTurn"; to: 0; duration: motionStatusPulse; easing.type: easeSoft }
                    }

                    NumberAnimation {
                        target: gwCapsule
                        property: "iconTurn"
                        to: 0
                        duration: motionUi
                        easing.type: easeSoft
                        running: gwCapsule.isRunning && Math.abs(gwCapsule.iconTurn) > 0.01
                    }

                    Item {
                        objectName: "gatewayActionIconWrap"
                        width: sizeGatewayActionIcon
                        height: sizeGatewayActionIcon
                        anchors.centerIn: gwActionFace
                        transformOrigin: Item.Center
                        y: gwCapsule.iconLift
                        scale: 1.0 + gwCapsule.iconPulse
                        rotation: gwCapsule.iconTurn

                        Behavior on y { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeSoft } }
                        Behavior on scale { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeSoft } }
                        Behavior on rotation { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeSoft } }

                        AppIcon {
                            anchors.fill: parent
                            source: gwCapsule.actionIconSource
                            sourceSize: Qt.size(sizeGatewayActionIcon, sizeGatewayActionIcon)
                            opacity: gwCapsule.isHovered ? 1.0 : 0.98
                            visible: !gwCapsule.useRunningPacman && gwCapsule.actionIconSource != ""
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                        }

                        Item {
                            anchors.fill: parent
                            visible: gwCapsule.useRunningPacman

                            GatewayPacmanGlyph {
                                anchors.fill: parent
                                mouth: gwCapsule.pacmanMouth
                                phase: gwCapsule.pacmanPhase
                            }
                        }
                    }
                }

                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: 22
                    anchors.right: gwAction.left
                    anchors.rightMargin: 22
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1

                    Row {
                        id: gatewaySecondaryRow
                        objectName: "gatewaySecondaryRow"
                        spacing: 7
                        opacity: 0.58 + gwCapsule.primaryLabelTransition * 0.14
                        y: 2 * (1.0 - gwCapsule.primaryLabelTransition)

                        Behavior on opacity { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeSoft } }
                        Behavior on y { NumberAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeSoft } }

                        Rectangle {
                            id: gwDot
                            width: 6
                            height: 6
                            radius: 3
                            anchors.verticalCenter: parent.verticalCenter
                            color: gwCapsule.dotColor
                            Behavior on color { ColorAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeStandard } }
                            Behavior on opacity { NumberAnimation { duration: motionUi + 20; easing.type: easeSoft } }
                            Behavior on scale { NumberAnimation { duration: motionUi + 20; easing.type: easeSoft } }

                            SequentialAnimation on scale {
                                running: gwCapsule.isRunning
                                loops: Animation.Infinite
                                NumberAnimation { to: motionDotPulseScaleMax; duration: motionBreath - motionFast; easing.type: easeSoft }
                                NumberAnimation { to: 1.0; duration: motionBreath - motionFast; easing.type: easeSoft }
                            }
                            SequentialAnimation {
                                running: gwCapsule.isStarting
                                loops: Animation.Infinite
                                NumberAnimation { target: gwDot; property: "opacity"; from: 1.0; to: 0.42; duration: motionAmbient; easing.type: easeSoft }
                                NumberAnimation { target: gwDot; property: "opacity"; from: 0.42; to: 1.0; duration: motionAmbient; easing.type: easeSoft }
                            }
                            SequentialAnimation {
                                running: gwCapsule.isError
                                loops: Animation.Infinite
                                NumberAnimation { target: gwDot; property: "opacity"; from: 1.0; to: motionDotPulseMinOpacity; duration: motionStatusPulse; easing.type: easeSoft }
                                NumberAnimation { target: gwDot; property: "opacity"; from: motionDotPulseMinOpacity; to: 1.0; duration: motionStatusPulse; easing.type: easeSoft }
                            }
                        }

                        Text {
                            text: strings.chat_gateway
                            color: gwCapsule.statusColor
                            font.pixelSize: typeCaption
                            font.weight: weightDemiBold
                            font.letterSpacing: letterWide
                            opacity: 1.0
                            Behavior on color { ColorAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeStandard } }
                        }
                    }

                    Item {
                        objectName: "gatewayPrimaryLabelWrap"
                        width: parent.width
                        implicitHeight: Math.max(gatewayPrimaryLabelIncoming.implicitHeight, gatewayPrimaryLabelOutgoing.implicitHeight)
                        height: implicitHeight

                        Text {
                            id: gatewayPrimaryLabelOutgoing
                            objectName: "gatewayPrimaryLabelOutgoing"
                            width: parent.width
                            visible: gwCapsule.outgoingPrimaryLabel !== "" && opacity > 0.01
                            text: gwCapsule.outgoingPrimaryLabel
                            color: gwCapsule.statusColor
                            font.pixelSize: typeButton + 1
                            font.weight: weightBold
                            font.letterSpacing: letterTight
                            opacity: 1.0 - gwCapsule.primaryLabelTransition
                            y: -4 * gwCapsule.primaryLabelTransition
                            Behavior on color { ColorAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeStandard } }
                        }

                        Text {
                            id: gatewayPrimaryLabelIncoming
                            objectName: "gatewayPrimaryLabelIncoming"
                            width: parent.width
                            text: gwCapsule.displayedPrimaryLabel
                            color: gwCapsule.statusColor
                            font.pixelSize: typeButton + 1
                            font.weight: weightBold
                            font.letterSpacing: letterTight
                            opacity: gwCapsule.primaryLabelTransition
                            y: 4 * (1.0 - gwCapsule.primaryLabelTransition)
                            Behavior on color { ColorAnimation { duration: gwCapsule.stateTransitionDuration; easing.type: easeStandard } }
                        }
                    }
                }

                GatewayStatusOrb {
                    id: gatewayStatusOrb
                    objectName: "gatewayStatusOrb"
                    channels: gwCapsule.gatewayChannels
                    detailText: gwCapsule.detailText
                    detailIsError: gwCapsule.hasErrorDetail
                    parentHovered: gwHover.containsMouse
                    parentFocused: gwCapsule.activeFocus
                    isDark: root.uiIsDark
                    bgCanvas: root.uiBgCanvas
                    textSecondary: root.uiTextSecondary
                    textPrimary: root.uiTextPrimary
                    statusSuccess: root.uiStatusSuccess
                    statusError: root.uiStatusError
                    statusWarning: root.uiStatusWarning
                    typeCaption: typeCaption
                    weightBold: weightBold
                    weightMedium: weightMedium
                    motionFast: motionFast
                    motionUi: motionUi
                    channelIconSource: root.channelIconSource
                    channelFilledIconSource: root.channelFilledIconSource
                    channelAccent: root.channelAccent
                }

            }

            MouseArea {
                id: gwHover
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: gwCapsule.isStarting ? Qt.ArrowCursor : Qt.PointingHandCursor
                onClicked: {
                    gwCapsule.forceActiveFocus()
                    gwCapsule.triggerGatewayAction()
                }
            }
        }

        Rectangle {
            id: profileBar
            objectName: "profileBar"
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            Layout.topMargin: 12
            visible: hasProfileService
            implicitHeight: 72
            radius: 22
            color: isDark ? "#16100D" : "#FCF6EF"
            border.width: 1
            border.color: profilePopup.opened
                          ? (isDark ? "#5A3A20" : "#E7B05D")
                          : (isDark ? "#2D221C" : "#E7D6C2")
            scale: profileBarMouse.containsPress ? 0.992 : 1.0

            Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
            Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

            Item {
                z: 1
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 16
                anchors.topMargin: 12
                anchors.bottomMargin: 12

                ProfileAvatar {
                    id: activeProfileAvatar
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    size: 46
                    source: root.profileAvatarSource(
                                hasProfileService ? (profileService.activeProfile || {}).avatarKey : "mochi")
                    active: true
                    hovered: profileBarMouse.containsMouse
                    accent: accent
                    isDark: isDark
                    motionFast: motionFast
                    easeStandard: easeStandard
                }

                Column {
                    anchors.left: activeProfileAvatar.right
                    anchors.leftMargin: 14
                    anchors.right: profileChevronFrame.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        width: parent.width
                        elide: Text.ElideRight
                        text: strings.profile_switch
                        color: textSecondary
                        font.pixelSize: typeMeta
                        font.weight: weightBold
                        font.letterSpacing: letterWide
                    }

                    Text {
                        id: profileBarLabel
                        width: parent.width
                        elide: Text.ElideRight
                        text: hasProfileService
                              ? String((profileService.activeProfile || {}).displayName || strings.profile_switch)
                              : strings.profile_switch
                        color: textPrimary
                        font.pixelSize: typeBody
                        font.weight: weightDemiBold
                    }

                }

                Rectangle {
                    id: profileChevronFrame
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: 34
                    height: 34
                    radius: 12
                    color: profileBarMouse.containsMouse
                           ? (isDark ? "#251B16" : "#F4E6D6")
                           : (isDark ? "#1B1411" : "#F7EDE3")
                    border.width: 1
                    border.color: isDark ? "#30241D" : "#E5D2BD"

                    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                    AppIcon {
                        id: profileChevron
                        anchors.centerIn: parent
                        width: 16
                        height: 16
                        source: themedIconSource("sidebar-chevron")
                        sourceSize: Qt.size(16, 16)
                        rotation: profilePopup.opened ? -90 : 90
                        opacity: 0.72

                        Behavior on rotation { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                    }
                }
            }

            Rectangle {
                z: 0
                anchors.fill: parent
                anchors.margins: 1
                radius: parent.radius - 1
                color: isDark ? "#08FFFFFF" : "#12FFFFFF"
                opacity: profileBarMouse.containsMouse ? 1.0 : 0.72

                Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
            }

            MouseArea {
                id: profileBarMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.toggleProfilePopup()
            }
        }

        Rectangle {
            id: controlTowerCard
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            Layout.topMargin: 12
            implicitHeight: 112
            radius: 24
            color: root.selectionTarget === "control_tower"
                   ? (isDark ? "#24160F" : "#FFF0DE")
                   : (controlTowerMouse.containsMouse ? (isDark ? "#1C130F" : "#FFF7EF") : (isDark ? "#15100D" : "#FFFBF7"))
            border.width: 1
            border.color: root.selectionTarget === "control_tower"
                          ? (isDark ? "#6A4322" : "#E2AA55")
                          : (isDark ? "#2A1F18" : "#E7D7C6")
            scale: controlTowerMouse.pressed ? 0.992 : (controlTowerMouse.containsMouse ? motionHoverScaleSubtle : 1.0)

            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
            Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
            Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeEmphasis } }

            Rectangle {
                anchors.fill: parent
                anchors.margins: 1
                radius: parent.radius - 1
                color: isDark ? "#0AFFFFFF" : "#10FFFFFF"
            }

            Item {
                anchors.fill: parent
                anchors.margins: 12

                Item {
                    id: controlTowerHeader
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    height: controlTowerIcon.height

                    AppIcon {
                        id: controlTowerIcon
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        width: 52
                        height: 52
                        source: root.sectionIconSource("control_tower")
                        sourceSize: Qt.size(width, height)
                        opacity: 1.0
                    }

                    Text {
                        id: controlTowerTitle
                        anchors.left: controlTowerIcon.right
                        anchors.leftMargin: 14
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: strings.sidebar_control_tower
                        color: textPrimary
                        font.pixelSize: typeBody + 4
                        font.weight: weightBold
                        elide: Text.ElideRight
                    }
                }

                RowLayout {
                    id: controlTowerStatsRow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    spacing: 8

                    Repeater {
                        model: [
                            {
                                "label": isChinese ? "工作中" : "Working",
                                "value": Number(supervisorOverview.workingCount || 0)
                            },
                            {
                                "label": isChinese ? "自动化" : "Automation",
                                "value": Number(supervisorOverview.automationCount || 0)
                            },
                            {
                                "label": isChinese ? "待处理" : "Pending",
                                "value": Number(supervisorOverview.attentionCount || 0)
                            }
                        ]

                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 34
                            radius: 14
                            color: isDark ? "#190F0A" : "#FFF6ED"
                            border.width: 1
                            border.color: isDark ? "#22FFFFFF" : "#14000000"

                            Column {
                                anchors.centerIn: parent
                                spacing: 0

                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: String(modelData.value)
                                    color: textPrimary
                                    font.pixelSize: typeLabel
                                    font.weight: weightBold
                                }

                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: String(modelData.label)
                                    color: textSecondary
                                    font.pixelSize: typeCaption
                                    font.weight: weightMedium
                                }
                            }
                        }
                    }
                }
            }

            MouseArea {
                id: controlTowerMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.sectionRequested("control_tower")
            }
        }

        Rectangle {
            id: navCard
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.topMargin: 16
            implicitHeight: navContent.implicitHeight + 20
            radius: 22
            color: isDark ? "#15100D" : "#FAF4EE"
            border.width: 1
            border.color: isDark ? "#20FFFFFF" : "#14000000"

            Rectangle {
                id: navHighlight
                objectName: "sidebarNavHighlight"
                z: 1
                x: 8
                y: root.navHighlightY
                width: navContent.width + 4
                height: root.navHighlightHeight
                radius: 16
                color: isDark ? "#2A1C14" : "#F3E7D8"
                border.width: 1
                border.color: isDark ? "#3A2A20" : "#E9D6C0"
                opacity: root.navHighlightOpacity

                Behavior on y { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
                Behavior on height { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
                Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                Rectangle {
                    width: 3
                    height: 26
                    radius: 1.5
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    color: accent
                }

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: parent.radius - 1
                    color: isDark ? "#08FFFFFF" : "#10FFFFFF"
                    opacity: 0.8
                }
            }

            ColumnLayout {
                id: navContent
                z: 2
                anchors.fill: parent
                anchors.margins: 10
                spacing: 4

                Text {
                    Layout.leftMargin: 8
                    Layout.topMargin: 6
                    text: strings.sidebar_library_title
                    color: textSecondary
                    font.pixelSize: typeMeta
                    font.weight: weightBold
                    font.letterSpacing: letterWide
                }

                SidebarNavItem {
                    id: sessionsNavItem
                    Layout.fillWidth: true
                    label: strings.sidebar_sessions
                    iconSource: root.sectionIconSource("sessions")
                    active: root.selectionTarget === "sessions"
                    badgeCount: hasSessionService ? (sessionService.sidebarUnreadCount || 0) : 0
                    useAccentBadge: true
                    useExternalHighlight: true
                    onClicked: root.sectionRequested("sessions")
                }

                SidebarNavItem {
                    id: memoryNavItem
                    Layout.fillWidth: true
                    label: strings.sidebar_memory
                    iconSource: root.sectionIconSource("memory")
                    active: root.selectionTarget === "memory"
                    useExternalHighlight: true
                    onClicked: root.sectionRequested("memory")
                }

                SidebarNavItem {
                    id: skillsNavItem
                    Layout.fillWidth: true
                    label: strings.sidebar_skills
                    iconSource: root.sectionIconSource("skills")
                    active: root.selectionTarget === "skills"
                    useExternalHighlight: true
                    onClicked: root.sectionRequested("skills")
                }

                SidebarNavItem {
                    id: toolsNavItem
                    Layout.fillWidth: true
                    label: strings.sidebar_tools_nav
                    iconSource: root.sectionIconSource("tools")
                    active: root.selectionTarget === "tools"
                    useExternalHighlight: true
                    onClicked: root.sectionRequested("tools")
                }

                SidebarNavItem {
                    id: cronNavItem
                    Layout.fillWidth: true
                    label: strings.sidebar_cron
                    iconSource: root.sectionIconSource("cron")
                    active: root.selectionTarget === "cron"
                    useExternalHighlight: true
                    onClicked: root.sectionRequested("cron")
                }
            }
        }

        Item { Layout.fillHeight: true }

        SidebarBrandDock {
            id: brandDock
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
            Layout.bottomMargin: 6
            active: root.settingsActive
            isDark: isDark
            hasDiagnostics: root.hasDiagnosticsCount
            diagnosticsCount: root.hasDiagnosticsCount ? diagnosticsService.eventCount : 0
            diagnosticsLabel: strings.sidebar_diagnostics
            diagnosticsHint: strings.sidebar_diagnostics_hint
            bubbleMessages: [
                strings.bubble_0,
                strings.bubble_1,
                strings.bubble_2,
                strings.bubble_3,
                strings.bubble_4
            ]
            accent: accent
            typeMeta: typeMeta
            weightMedium: weightMedium
            weightDemiBold: weightDemiBold
            weightBold: weightBold
            motionFast: motionFast
            motionUi: motionUi
            motionPanel: motionPanel
            easeStandard: easeStandard
            easeEmphasis: easeEmphasis
            easeSoft: easeSoft
            motionPressScaleStrong: 0.94
            motionSelectionScaleActive: motionSelectionScaleActive
            onSettingsRequested: root.settingsRequested()
            onDiagnosticsRequested: root.diagnosticsRequested()
        }
    }

    Popup {
        id: profilePopup
        objectName: "profilePopup"
        parent: root
        x: profileBar.x
        y: profileBar.y + profileBar.height + 8
        width: Math.max(profileBar.width + 8, 256)
        padding: 0
        modal: false
        focus: true
        transformOrigin: Item.Top
        closePolicy: Popup.CloseOnEscape
        onClosed: root.cancelRenameProfile()
        Component.onCompleted: root.profilePopupHandle = profilePopup
        Component.onDestruction: if (root.profilePopupHandle === profilePopup) root.profilePopupHandle = null

        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motionFast; easing.type: easeStandard }
                NumberAnimation { property: "scale"; from: 0.985; to: 1.0; duration: motionFast; easing.type: easeEmphasis }
            }
        }

        exit: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motionMicro; easing.type: easeStandard }
                NumberAnimation { property: "scale"; from: 1.0; to: 0.988; duration: motionMicro; easing.type: easeStandard }
            }
        }

        background: Item {
            Rectangle {
                anchors.fill: parent
                anchors.topMargin: 6
                radius: 22
                color: isDark ? "#24000000" : "#18000000"
                opacity: 0.9
            }

            Rectangle {
                anchors.fill: parent
                radius: 22
                color: isDark ? "#171210" : "#FFFBF6"
                border.width: 1
                border.color: isDark ? "#2D221C" : "#E8D7C5"
            }
        }

        contentItem: Column {
            width: profilePopup.width
            spacing: 10
            topPadding: 10
            bottomPadding: 12

            ScrollView {
                id: profileListScroll
                width: parent.width - 20
                anchors.horizontalCenter: parent.horizontalCenter
                height: Math.min(profileListColumn.implicitHeight, 212)
                clip: true
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                Column {
                    id: profileListColumn
                    width: profileListScroll.availableWidth
                    spacing: 8

                    Repeater {
                        model: hasProfileService ? (profileService.profiles || []) : []

                        delegate: Item {
                            id: profileRow
                            required property var modelData
                            readonly property bool isActive: Boolean(profileRow.modelData.isActive)
                            readonly property bool isEditing: root.editingProfileId === String(profileRow.modelData.id || "")
                            readonly property bool hovered: rowMouse.containsMouse || renameAction.hovered || deleteAction.hovered
                            width: profileListColumn.width
                            height: profileCard.height + (profileRow.isEditing ? renameBubble.height + 8 : 0)

                            Behavior on height { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

                            onIsEditingChanged: {
                                if (!profileRow.isEditing)
                                    return
                                Qt.callLater(function() {
                                    root.focusProfileRenameEditor(renameFieldLoader.item)
                                })
                            }

                            Rectangle {
                                id: profileCard
                                width: parent.width
                                height: 58
                                radius: 19
                                color: profileRow.isActive
                                       ? (isDark ? "#241712" : "#F7E9D7")
                                       : (profileRow.hovered ? (isDark ? "#1E1511" : "#FBF0E4") : "transparent")
                                border.width: profileRow.isActive || profileRow.isEditing || profileRow.hovered ? 1 : 0
                                border.color: profileRow.isEditing
                                              ? accent
                                              : profileRow.isActive
                                              ? (isDark ? "#6A4322" : "#E3AA54")
                                              : (isDark ? "#2C211B" : "#E9D8C5")
                                scale: rowMouse.pressed ? 0.992 : 1.0

                                Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                                Rectangle {
                                    anchors.fill: parent
                                    anchors.margins: 1
                                    radius: parent.radius - 1
                                    color: isDark ? "#04FFFFFF" : "#0AFFFFFF"
                                    opacity: profileRow.isActive ? 1.0 : 0.0

                                    Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                                }

                                ProfileAvatar {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 14
                                    anchors.verticalCenter: parent.verticalCenter
                                    size: 40
                                    source: root.profileAvatarSource(profileRow.modelData.avatarKey)
                                    active: profileRow.isActive
                                    hovered: profileRow.hovered
                                    accent: accent
                                    isDark: isDark
                                    motionFast: motionFast
                                    easeStandard: easeStandard
                                }

                                Text {
                                    id: profileNameLabel
                                    anchors.left: parent.left
                                    anchors.leftMargin: 66
                                    anchors.right: profileActions.left
                                    anchors.rightMargin: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    elide: Text.ElideRight
                                    text: String(profileRow.modelData.displayName || "")
                                    color: textPrimary
                                    font.pixelSize: typeBody + 1
                                    font.weight: profileRow.isActive ? weightBold : weightDemiBold
                                }

                                Row {
                                    id: profileActions
                                    anchors.right: parent.right
                                    anchors.rightMargin: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 7

                                    IconCircleButton {
                                        id: renameAction
                                        buttonSize: 30
                                        iconSource: themedIconSource("profile-edit")
                                        glyphSize: 18
                                        fillColor: profileRow.isEditing
                                                   ? (isDark ? "#24150C" : "#F6E1C9")
                                                   : (isDark ? "#16100D" : "#FFF7EF")
                                        hoverFillColor: profileRow.isEditing
                                                        ? (isDark ? "#2E1B10" : "#F0D3AC")
                                                        : bgCardHover
                                        outlineColor: profileRow.isEditing
                                                      ? accent
                                                      : (isDark ? "#352821" : "#E1CCB9")
                                        glyphColor: profileRow.isEditing ? accent : textSecondary
                                        hoverScale: 1.06
                                        onClicked: root.beginRenameProfile(
                                                       String(profileRow.modelData.id || ""),
                                                       String(profileRow.modelData.displayName || "")
                                                   )
                                    }

                                    IconCircleButton {
                                        id: deleteAction
                                        visible: Boolean(profileRow.modelData.canDelete)
                                        buttonSize: 30
                                        iconSource: themedIconSource("profile-trash")
                                        glyphSize: 18
                                        fillColor: isDark ? "#16100D" : "#FFF7EF"
                                        hoverFillColor: isDark ? "#301715" : "#FBE8E2"
                                        outlineColor: deleteAction.hovered
                                                      ? (isDark ? "#8D3C33" : "#D79082")
                                                      : (isDark ? "#3F241F" : "#E7C9C1")
                                        glyphColor: deleteAction.hovered ? statusError : textSecondary
                                        hoverScale: 1.06
                                        onClicked: root.requestDeleteProfile(
                                                       String(profileRow.modelData.id || ""),
                                                       String(profileRow.modelData.displayName || ""),
                                                       String(profileRow.modelData.avatarKey || "mochi")
                                                   )
                                    }
                                }

                                MouseArea {
                                    id: rowMouse
                                    anchors.fill: parent
                                    anchors.rightMargin: profileActions.width + 18
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    enabled: !profileRow.isEditing
                                    onClicked: {
                                        profileService.activateProfile(String(profileRow.modelData.id || ""))
                                        root.closeProfilePopup()
                                    }
                                }
                            }

                            Rectangle {
                                id: renameBubble
                                anchors.top: profileCard.bottom
                                anchors.topMargin: 8
                                anchors.left: profileCard.left
                                anchors.leftMargin: 62
                                anchors.right: profileCard.right
                                anchors.rightMargin: 10
                                height: 52
                                radius: 17
                                visible: opacity > 0.01
                                opacity: profileRow.isEditing ? 1.0 : 0.0
                                scale: profileRow.isEditing ? 1.0 : 0.985
                                color: isDark ? "#181210" : "#FFF8F1"
                                border.width: 1
                                border.color: profileRow.isEditing ? accent : (isDark ? "#31241E" : "#E4D2C0")

                                Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                                Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
                                Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                Rectangle {
                                    anchors.fill: parent
                                    anchors.margins: 1
                                    radius: parent.radius - 1
                                    color: isDark ? "#08FFFFFF" : "#12FFFFFF"
                                }

                                Loader {
                                    id: renameFieldLoader
                                    anchors.left: parent.left
                                    anchors.leftMargin: 8
                                    anchors.right: renameBubbleActions.left
                                    anchors.rightMargin: 8
                                    anchors.verticalCenter: parent.verticalCenter
                                    active: profileRow.isEditing
                                    sourceComponent: renameFieldComponent
                                }

                                Row {
                                    id: renameBubbleActions
                                    anchors.right: parent.right
                                    anchors.rightMargin: 8
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 6

                                    IconCircleButton {
                                        buttonSize: 28
                                        glyphText: "\u2713"
                                        glyphSize: 13
                                        fillColor: accent
                                        hoverFillColor: accentHover
                                        outlineColor: accent
                                        glyphColor: isDark ? bgSidebar : "#FFFFFF"
                                        hoverScale: 1.06
                                        onClicked: root.submitRenameProfile()
                                    }

                                    IconCircleButton {
                                        buttonSize: 28
                                        glyphText: "\u00D7"
                                        glyphSize: 13
                                        fillColor: isDark ? "#16100D" : "#FFF7EF"
                                        hoverFillColor: bgCardHover
                                        outlineColor: isDark ? "#352821" : "#E1CCB9"
                                        glyphColor: textSecondary
                                        hoverScale: 1.06
                                        onClicked: root.cancelRenameProfile()
                                    }
                                }

                                Component {
                                    id: renameFieldComponent

                                    SettingsField {
                                        label: ""
                                        showLabel: false
                                        showDescription: false
                                        placeholder: String(strings.profile_display_name_placeholder || "")
                                        fieldHeight: 38
                                        fieldFontPixelSize: typeBody
                                        text: root.editingProfileName
                                        onTextEdited: function(text) {
                                            root.editingProfileName = text
                                        }
                                        onAccepted: root.submitRenameProfile()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                width: parent.width - 24
                anchors.horizontalCenter: parent.horizontalCenter
                height: 10

                Row {
                    anchors.fill: parent
                    spacing: 6

                    Repeater {
                        model: Math.max(1, Math.floor(parent.width / 12))

                        Rectangle {
                            width: 7
                            height: 1
                            radius: 0.5
                            anchors.verticalCenter: parent.verticalCenter
                            color: isDark ? "#3A2A20" : "#DCC8B4"
                            opacity: 0.8
                        }
                    }
                }
            }

            Item {
                width: parent.width - 24
                anchors.horizontalCenter: parent.horizontalCenter
                height: 38

                SettingsField {
                    id: newProfileField
                    anchors.left: parent.left
                    anchors.right: createButton.left
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    label: ""
                    showLabel: false
                    showDescription: false
                    fieldHeight: 38
                    fieldFontPixelSize: typeLabel
                    placeholder: strings.profile_create_placeholder
                    onAccepted: createProfileAction.trigger()
                }

                IconCircleButton {
                    id: createButton
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    buttonSize: 38
                    glyphText: "+"
                    glyphSize: 20
                    fillColor: accent
                    hoverFillColor: accentHover
                    outlineColor: accent
                    glyphColor: isDark ? bgSidebar : "#FFFFFF"
                    hoverScale: 1.05
                    pressedScale: 0.92
                    onClicked: createProfileAction.trigger()
                }
            }

            Rectangle {
                width: parent.width - 24
                anchors.horizontalCenter: parent.horizontalCenter
                radius: 14
                color: isDark ? "#2A1715" : "#FCE7E2"
                border.width: 1
                border.color: isDark ? "#5E2B26" : "#E2A69A"
                visible: hasProfileService && String(profileService.lastError || "").length > 0
                implicitHeight: errorText.implicitHeight + 18

                Text {
                    id: errorText
                    anchors.fill: parent
                    anchors.margins: 9
                    text: hasProfileService ? String(profileService.lastError || "") : ""
                    color: isDark ? "#FFD6CF" : "#A23A2B"
                    font.pixelSize: typeCaption
                    font.weight: weightMedium
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    TapHandler {
        enabled: profilePopup.opened

        onTapped: function(eventPoint) {
            if (root.containsItemPoint(profileBar, eventPoint.position.x, eventPoint.position.y))
                return
            if (root.containsItemPoint(profilePopup.contentItem, eventPoint.position.x, eventPoint.position.y))
                return
            if (root.containsItemPoint(profilePopup.background, eventPoint.position.x, eventPoint.position.y))
                return
            root.closeProfilePopup()
        }
    }

    Action {
        id: createProfileAction

        function trigger() {
            var name = String(newProfileField.text || "").trim()
            if (!name.length)
                return
            profileService.createProfile(name)
            newProfileField.text = ""
            root.closeProfilePopup()
        }
    }

    AppModal {
        id: deleteProfileModal
        title: strings.profile_delete_title
        closeText: strings.profile_delete_cancel
        darkMode: isDark
        maxModalWidth: 468
        maxModalHeight: 396
        bodyScrollable: false
        showDefaultCloseAction: true
        property real heroRevealScale: 0.92
        property real heroRevealY: 12
        property real bodyRevealOpacity: 0.0
        property real bodyRevealY: 16
        property real actionRevealOpacity: 0.0
        property real actionRevealScale: 0.92
        property real warningPulse: 0.0
        property real auraOpacity: 0.0
        Behavior on heroRevealScale { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }
        Behavior on heroRevealY { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }
        Behavior on bodyRevealOpacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
        Behavior on bodyRevealY { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }
        Behavior on actionRevealOpacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
        Behavior on actionRevealScale { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }
        Behavior on auraOpacity { NumberAnimation { duration: motionUi; easing.type: easeSoft } }
        onOpened: {
            heroRevealScale = 0.92
            heroRevealY = 12
            bodyRevealOpacity = 0.0
            bodyRevealY = 16
            actionRevealOpacity = 0.0
            actionRevealScale = 0.92
            warningPulse = 0.0
            auraOpacity = 0.0
            Qt.callLater(function() {
                deleteProfileModal.heroRevealScale = 1.0
                deleteProfileModal.heroRevealY = 0
                deleteProfileModal.bodyRevealOpacity = 1.0
                deleteProfileModal.bodyRevealY = 0
                deleteProfileModal.actionRevealOpacity = 1.0
                deleteProfileModal.actionRevealScale = 1.0
                deleteProfileModal.auraOpacity = isDark ? 0.08 : 0.06
            })
            deleteModalWarningPulse.restart()
        }
        onClosed: {
            deleteModalWarningPulse.stop()
            root.clearPendingDeleteProfile()
        }

        Rectangle {
            id: deleteProfileDangerCard
            width: parent ? parent.width : 360
            radius: 20
            color: isDark ? "#18110F" : "#FFF8F3"
            border.width: 1
            border.color: isDark ? "#4A2621" : "#EDC1B6"
            implicitHeight: deleteModalCard.implicitHeight + 28
            opacity: 0.94 + deleteProfileModal.bodyRevealOpacity * 0.06
            y: deleteProfileModal.bodyRevealY

            Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on y { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }

            Rectangle {
                anchors.fill: parent
                anchors.margins: 1
                radius: parent.radius - 1
                color: isDark ? "#0AFFFFFF" : "#12FFFFFF"
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 72
                radius: parent.radius
                color: statusError
                opacity: deleteProfileModal.auraOpacity

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: parent.radius
                    color: deleteProfileDangerCard.color
                }

                Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
            }

            Column {
                id: deleteModalCard
                anchors.fill: parent
                anchors.margins: 14
                spacing: 14

                Row {
                    id: deleteProfileHero
                    width: parent.width
                    spacing: 12
                    opacity: 0.78 + deleteProfileModal.bodyRevealOpacity * 0.22
                    y: deleteProfileModal.heroRevealY

                    Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
                    Behavior on y { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }

                    Item {
                        width: 58
                        height: 58
                        scale: deleteProfileModal.heroRevealScale + deleteProfileModal.warningPulse * 0.02

                        Behavior on scale { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }

                        Rectangle {
                            anchors.centerIn: parent
                            width: 54
                            height: 54
                            radius: 18
                            color: isDark ? "#261714" : "#FDECE6"
                            border.width: 1
                            border.color: isDark ? "#5F312B" : "#E7ACA0"
                        }

                        ProfileAvatar {
                            anchors.centerIn: parent
                            size: 46
                            source: root.profileAvatarSource((root.pendingDeleteProfile || {}).avatarKey)
                            active: true
                            hovered: false
                            accent: accent
                            isDark: isDark
                            motionFast: motionFast
                            easeStandard: easeStandard
                        }

                        Rectangle {
                            id: deleteProfileWarningBadge
                            width: 22
                            height: 22
                            radius: 11
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            color: statusError
                            border.width: 2
                            border.color: isDark ? "#18110F" : "#FFF8F3"
                            scale: 1.0 + deleteProfileModal.warningPulse * 0.08

                            Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeSoft } }

                            AppIcon {
                                anchors.centerIn: parent
                                width: 12
                                height: 12
                                source: "../resources/icons/vendor/iconoir/message-alert.svg"
                                sourceSize: Qt.size(12, 12)
                            }
                        }
                    }

                    Column {
                        width: parent.width - 70
                        spacing: 6

                        Text {
                            width: parent.width
                            text: String((root.pendingDeleteProfile || {}).displayName || "")
                            color: textPrimary
                            font.pixelSize: typeBody + 2
                            font.weight: weightBold
                            elide: Text.ElideRight
                        }

                        Flow {
                            width: parent.width
                            spacing: 8

                            Rectangle {
                                width: irreversibleLabel.implicitWidth + 16
                                height: 22
                                radius: 11
                                color: isDark ? "#331714" : "#FFECE7"
                                border.width: 1
                                border.color: isDark ? "#72332B" : "#E4AEA2"

                                Text {
                                    id: irreversibleLabel
                                    anchors.centerIn: parent
                                    text: strings.profile_delete_irreversible
                                    color: statusError
                                    font.pixelSize: typeCaption
                                    font.weight: weightBold
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    id: deleteHintCard
                    width: parent.width
                    radius: 16
                    color: isDark ? "#221613" : "#FFF2ED"
                    border.width: 1
                    border.color: isDark ? "#3C221D" : "#E9D2C8"
                    implicitHeight: deleteHintColumn.implicitHeight + 24

                    Column {
                        id: deleteHintColumn
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8

                        Text {
                            text: strings.profile_delete_irreversible
                            color: statusError
                            font.pixelSize: typeCaption
                            font.weight: weightBold
                            font.letterSpacing: letterWide
                        }

                        Text {
                            id: deleteHintText
                            width: parent.width
                            text: String(strings.profile_delete_hint || "").replace(
                                      "%1",
                                      String((root.pendingDeleteProfile || {}).displayName || "")
                                  )
                            color: textSecondary
                            font.pixelSize: typeBody
                            font.weight: weightMedium
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }

        footer: PillActionButton {
            text: strings.profile_delete_confirm
            iconSource: "../resources/icons/vendor/iconoir/message-alert.svg"
            iconSize: 13
            fillColor: statusError
            hoverFillColor: Qt.darker(statusError, 1.08)
            outlineColor: "transparent"
            hoverOutlineColor: "transparent"
            textColor: "#FFFFFF"
            opacity: deleteProfileModal.actionRevealOpacity
            scale: deleteProfileModal.actionRevealScale

            Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on scale { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }
            onClicked: root.confirmDeleteProfile()
        }

        SequentialAnimation {
            id: deleteModalWarningPulse
            loops: Animation.Infinite
            running: false

            NumberAnimation {
                target: deleteProfileModal
                property: "warningPulse"
                to: 1.0
                duration: motionBreath
                easing.type: easeSoft
            }
            NumberAnimation {
                target: deleteProfileModal
                property: "warningPulse"
                to: 0.0
                duration: motionBreath
                easing.type: easeSoft
            }
        }
    }
}
