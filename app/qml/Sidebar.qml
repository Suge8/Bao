import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "sidebarRoot"

    property string selectionTarget: "sessions"
    readonly property bool settingsActive: selectionTarget === "settings"
    signal settingsRequested()
    signal diagnosticsRequested()
    signal newSessionRequested()
    signal sessionSelected(string key)
    signal sessionDeleteRequested(string key)
    signal sectionRequested(string section)

    color: "transparent"

    readonly property bool hasChatService: typeof chatService !== "undefined" && chatService !== null
    readonly property bool hasSessionService: typeof sessionService !== "undefined" && sessionService !== null
    readonly property bool hasDiagnosticsService: typeof diagnosticsService !== "undefined" && diagnosticsService !== null
    readonly property bool uiIsDark: isDark
    readonly property color uiBgCanvas: "transparent"
    readonly property color uiTextPrimary: textPrimary
    readonly property color uiTextSecondary: textSecondary
    readonly property color uiStatusSuccess: statusSuccess
    readonly property color uiStatusError: statusError
    readonly property color uiStatusWarning: statusWarning
    property real navHighlightY: 0.0
    property real navHighlightHeight: 50
    property real navHighlightOpacity: 0.0

    function sectionIconSource(section) {
        switch (section) {
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

    function activeNavTarget() {
        switch (selectionTarget) {
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

    onSelectionTargetChanged: Qt.callLater(function() { root.updateNavHighlight() })
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

            property string currentState: hasChatService ? chatService.state : "idle"
            property bool isRunning: hasChatService && chatService.state === "running"
            property bool isStarting: hasChatService && chatService.state === "starting"
            property bool isError: hasChatService && chatService.state === "error"
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

                        Image {
                            anchors.fill: parent
                            source: gwCapsule.actionIconSource
                            sourceSize: Qt.size(sizeGatewayActionIcon, sizeGatewayActionIcon)
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            mipmap: true
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
            id: navCard
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.topMargin: 18
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

        Item {
            id: bottomActions
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            Layout.bottomMargin: 6
            property bool diagnosticsHovered: diagnosticsArea.containsMouse

            Rectangle {
                id: glowRing
                anchors.centerIn: appIconBtn
                width: appIconBtn.width + spacingMd + 2
                height: appIconBtn.height + spacingMd + 2
                radius: width / 2
                color: "transparent"
                border.width: 1.5
                border.color: accent
                opacity: root.settingsActive ? 0.38 : 0
                antialiasing: true
                scale: appIconBtn.scale
                rotation: appIconBtn.rotation

                SequentialAnimation {
                    id: breatheAnim
                    running: !root.settingsActive && !appIconArea.containsMouse
                    loops: Animation.Infinite
                    NumberAnimation {
                        target: glowRing; property: "opacity"
                        from: 0; to: motionRingIdlePeakOpacity; duration: motionFloat + motionPanel
                        easing.type: easeSoft
                    }
                    NumberAnimation {
                        target: glowRing; property: "opacity"
                        from: motionRingIdlePeakOpacity; to: 0; duration: motionFloat + motionPanel
                        easing.type: easeSoft
                    }
                }

                states: State {
                    name: "hovered"; when: appIconArea.containsMouse
                    PropertyChanges { target: glowRing; opacity: motionRingHoverOpacity }
                }
                transitions: Transition {
                    NumberAnimation {
                        property: "opacity"; duration: motionPanel
                        easing.type: easeStandard
                    }
                }
            }

            Rectangle {
                id: glowRingOuter
                anchors.centerIn: appIconBtn
                width: appIconBtn.width + spacingXl
                height: appIconBtn.height + spacingXl
                radius: width / 2
                color: "transparent"
                border.width: 1
                border.color: accent
                opacity: root.settingsActive ? 0.18 : (appIconArea.containsMouse ? 0.25 : 0)
                antialiasing: true
                scale: appIconBtn.scale
                rotation: appIconBtn.rotation
                Behavior on opacity {
                    NumberAnimation { duration: motionAmbient; easing.type: easeStandard }
                }
            }

            Rectangle {
                id: diagnosticsGlow
                anchors.verticalCenter: diagnosticsPill.verticalCenter
                anchors.horizontalCenter: diagnosticsPill.horizontalCenter
                width: diagnosticsPill.width + 12
                height: diagnosticsPill.height + 12
                radius: height / 2
                color: accent
                opacity: bottomActions.diagnosticsHovered ? 0.12 : 0.0
                scale: bottomActions.diagnosticsHovered ? 1.0 : 0.985
                visible: opacity > 0.01
                Behavior on opacity {
                    NumberAnimation { duration: motionPanel; easing.type: easeStandard }
                }
                Behavior on scale {
                    NumberAnimation { duration: motionPanel; easing.type: easeEmphasis }
                }
            }

            Rectangle {
                id: appIconBtn
                objectName: "sidebarAppIconButton"
                readonly property bool active: root.settingsActive
                width: sizeAppIcon
                height: sizeAppIcon
                radius: sizeAppIcon / 2
                anchors.left: parent.left
                anchors.leftMargin: 18
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 6
                color: active ? (isDark ? "#251910" : "#F8EBDD") : "transparent"
                border.width: 1.5
                border.color: active ? accent : (appIconArea.containsMouse ? accent : borderSubtle)
                antialiasing: true
                scale: appIconArea.pressed ? motionPressScaleStrong
                       : (active ? motionSelectionScaleActive : (appIconArea.containsMouse ? motionHoverScaleStrong : 1.0))
                rotation: active ? 0 : (appIconArea.containsMouse ? -10 : 0)

                Behavior on scale {
                    NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
                }
                Behavior on border.color {
                    ColorAnimation { duration: motionUi; easing.type: easeStandard }
                }
                Behavior on rotation {
                    NumberAnimation { duration: motionPanel; easing.type: easeEmphasis }
                }

                Image {
                    anchors.fill: parent
                    source: "../resources/logo-circle.png"
                    sourceSize: Qt.size(88, 88)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                }

                MouseArea {
                    id: appIconArea
                    anchors.fill: parent
                    anchors.margins: -8
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: {
                        var idx = Math.floor(Math.random() * 5)
                        bubbleText.text = strings["bubble_" + idx] || ""
                    }
                    onClicked: root.settingsRequested()
                }
            }

            Rectangle {
                id: diagnosticsPill
                width: 106
                height: 40
                radius: 20
                anchors.left: appIconBtn.right
                anchors.leftMargin: 26
                anchors.verticalCenter: appIconBtn.verticalCenter
                anchors.verticalCenterOffset: 2
                color: bottomActions.diagnosticsHovered ? (isDark ? "#2A1A12" : "#FFF4E8") : (isDark ? "#211711" : "#FFF9F5")
                border.width: 0
                antialiasing: true
                scale: diagnosticsArea.pressed ? motionPressScaleStrong
                       : (bottomActions.diagnosticsHovered ? motionHoverScaleSubtle : 1.0)

                Behavior on color {
                    ColorAnimation { duration: motionUi; easing.type: easeStandard }
                }
                Behavior on scale {
                    NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
                }

                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: isDark ? "#10FFFFFF" : "#08000000"
                }

                Row {
                    anchors.centerIn: parent
                    spacing: 6

                    Image {
                        width: 18
                        height: 18
                        anchors.verticalCenter: parent.verticalCenter
                        source: isDark
                                ? "../resources/icons/sidebar-diagnostics-dark.svg"
                                : "../resources/icons/sidebar-diagnostics-light.svg"
                        sourceSize: Qt.size(18, 18)
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        mipmap: true
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 0

                        Text {
                            text: strings.sidebar_diagnostics
                            color: textPrimary
                            font.pixelSize: typeMeta + 1
                            font.weight: weightBold
                        }

                        Text {
                            text: strings.sidebar_diagnostics_hint
                            color: textSecondary
                            font.pixelSize: typeMeta - 1
                            font.weight: weightMedium
                        }
                    }
                }

                Rectangle {
                    visible: hasDiagnosticsService && diagnosticsService.eventCount > 0
                    width: 17
                    height: 17
                    radius: 8.5
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.rightMargin: -3
                    anchors.topMargin: -3
                    color: accent
                    border.width: 0

                    Text {
                        anchors.centerIn: parent
                        text: hasDiagnosticsService && diagnosticsService.eventCount > 9 ? "9+" : String(hasDiagnosticsService ? diagnosticsService.eventCount : 0)
                        color: isDark ? "#241106" : "#FFFFFF"
                        font.pixelSize: 8
                        font.weight: weightBold
                    }
                }

                MouseArea {
                    id: diagnosticsArea
                    anchors.fill: parent
                    anchors.margins: -4
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.diagnosticsRequested()
                }
            }

            Rectangle {
                id: speechBubble
                property bool show: appIconArea.containsMouse

                anchors.left: appIconBtn.right
                anchors.leftMargin: 12
                anchors.verticalCenter: appIconBtn.verticalCenter
                width: bubbleText.implicitWidth + 24
                height: bubbleText.implicitHeight + 16
                radius: radiusMd
                color: bgElevated
                border.width: 1
                border.color: borderDefault
                opacity: speechBubble.show ? 1.0 : 0.0
                scale: speechBubble.show ? 1.0 : motionBubbleHiddenScale
                transformOrigin: Item.Left
                visible: speechBubble.show

                Behavior on opacity {
                    NumberAnimation { duration: motionUi; easing.type: easeStandard }
                }
                Behavior on scale {
                    NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
                }

                Text {
                    id: bubbleText
                    anchors.centerIn: parent
                    font.pixelSize: typeMeta
                    font.weight: weightMedium
                    color: textSecondary
                    text: ""
                }
            }
        }
    }
}
