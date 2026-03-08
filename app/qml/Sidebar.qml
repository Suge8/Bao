import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "sidebarRoot"

    property bool showingSettings: false
    property string activeSessionKey: ""
    property bool showChatSelection: true
    signal settingsRequested()
    signal diagnosticsRequested()
    signal newSessionRequested()
    signal sessionSelected(string key)
    signal sessionDeleteRequested(string key)

    color: "transparent"

    Rectangle {
        anchors.fill: parent
        radius: 20
        color: bgSidebar
        antialiasing: true

        Rectangle {
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: parent.radius
            color: parent.color
        }
        Rectangle {
            anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
            width: parent.radius
            color: parent.color
        }
    }

    readonly property bool hasChatService: typeof chatService !== "undefined" && chatService !== null
    readonly property bool hasSessionService: typeof sessionService !== "undefined" && sessionService !== null
    readonly property bool hasDiagnosticsService: typeof diagnosticsService !== "undefined" && diagnosticsService !== null
    property bool gatewayIdle: !hasChatService || chatService.state === "idle" || chatService.state === "stopped"
    property string lastSidebarUnreadFingerprint: ""
    property real headerPulseScale: 0.0
    property real headerBadgeScale: 0.0
    property bool stickyHeaderVisible: false
    property string stickyHeaderChannel: ""
    property bool stickyHeaderExpanded: false
    property int stickyHeaderItemCount: 0
    property int stickyHeaderUnreadCount: 0
    property bool stickyHeaderHasRunning: false
    property real stickyHeaderOffset: 0.0
    property bool uiIsDark: isDark
    property color uiBgCanvas: "transparent"
    property color uiTextPrimary: textPrimary
    property color uiTextSecondary: textSecondary
    property color uiStatusSuccess: statusSuccess
    property color uiStatusError: statusError
    property color uiStatusWarning: statusWarning

    function requestNewSession() {
        root.newSessionRequested()
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
            return isDark ? "../resources/icons/ignite-dark.svg" : "../resources/icons/ignite.svg"
        case "system":
            return filled ? "../resources/icons/sidebar-settings-solid.svg" : "../resources/icons/sidebar-settings.svg"
        case "heartbeat":
            return filled ? "../resources/icons/sidebar-pulse-solid.svg" : "../resources/icons/sidebar-pulse.svg"
        case "cron":
            return filled ? "../resources/icons/sidebar-zap-solid.svg" : "../resources/icons/sidebar-zap.svg"
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

    function channelUsesTint(channel) {
        switch (channel) {
        case "telegram":
        case "discord":
        case "whatsapp":
        case "feishu":
        case "slack":
        case "qq":
        case "dingtalk":
        case "imessage":
            return true
        default:
            return false
        }
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

    function syncUnreadState() {
        if (!hasSessionService) {
            root.lastSidebarUnreadFingerprint = ""
            return
        }
        var nextFingerprint = sessionService.sidebarUnreadFingerprint || ""
        var unreadCount = sessionService.sidebarUnreadCount || 0
        if (root.lastSidebarUnreadFingerprint !== "" && nextFingerprint !== root.lastSidebarUnreadFingerprint && unreadCount > 0)
            sessionsHeaderPulse.restart()
        root.lastSidebarUnreadFingerprint = nextFingerprint
    }

    function listContentYBounds() {
        var minY = sessionList ? sessionList.originY : 0
        var maxY = minY
        if (sessionList)
            maxY = minY + Math.max(0, sessionList.contentHeight - sessionList.height)
        return { minY: minY, maxY: maxY }
    }

    function clampListContentY(y) {
        var bounds = root.listContentYBounds()
        return Math.max(bounds.minY, Math.min(y, bounds.maxY))
    }

    function sidebarRowData(rowIndex) {
        if (!hasSessionService)
            return null
        var model = sessionService.sidebarModel
        if (!model || rowIndex < 0 || rowIndex >= model.rowCount())
            return null
        var idx = model.index(rowIndex, 0)
        return {
            isHeader: model.data(idx, Qt.UserRole + 102) || false,
            channel: model.data(idx, Qt.UserRole + 103) || "other",
            expanded: model.data(idx, Qt.UserRole + 104) || false,
            itemCount: model.data(idx, Qt.UserRole + 115) || 0,
            groupUnreadCount: model.data(idx, Qt.UserRole + 116) || 0,
            groupHasRunning: model.data(idx, Qt.UserRole + 117) || false,
        }
    }

    function resetStickyHeader() {
        root.stickyHeaderVisible = false
        root.stickyHeaderChannel = ""
        root.stickyHeaderExpanded = false
        root.stickyHeaderItemCount = 0
        root.stickyHeaderUnreadCount = 0
        root.stickyHeaderHasRunning = false
        root.stickyHeaderOffset = 0.0
    }

    function refreshStickyHeader() {
        if (!sessionList || !hasSessionService || sessionList.count === 0) {
            root.resetStickyHeader()
            return
        }
        var delegates = root.visibleDelegates()
        var contentY = sessionList.contentY
        var first = null
        for (var i = 0; i < delegates.length; i++) {
            var delegate = delegates[i]
            if (delegate.height <= 0)
                continue
            if (delegate.y + delegate.height <= contentY)
                continue
            first = delegate
            break
        }
        if (!first || !first.anchorChannel) {
            root.resetStickyHeader()
            return
        }

        var stickyNeeded = !first.anchorIsHeader || first.y < contentY + 0.5
        if (!stickyNeeded) {
            root.resetStickyHeader()
            return
        }

        var stickyRow = null
        for (var rowIndex = 0; rowIndex < sessionList.count; rowIndex++) {
            var row = root.sidebarRowData(rowIndex)
            if (!row || !row.isHeader || row.channel !== first.anchorChannel)
                continue
            stickyRow = row
            break
        }
        if (!stickyRow) {
            root.resetStickyHeader()
            return
        }

        var nextHeaderViewportY = Number.POSITIVE_INFINITY
        for (var j = i + 1; j < delegates.length; j++) {
            var nextDelegate = delegates[j]
            if (!nextDelegate.anchorIsHeader)
                continue
            if (nextDelegate.anchorChannel === first.anchorChannel)
                continue
            nextHeaderViewportY = nextDelegate.y - contentY
            break
        }

        var stickyOffset = 0.0
        if (nextHeaderViewportY < sizeSidebarHeader)
            stickyOffset = nextHeaderViewportY - sizeSidebarHeader

        root.stickyHeaderVisible = true
        root.stickyHeaderChannel = stickyRow.channel
        root.stickyHeaderExpanded = stickyRow.expanded
        root.stickyHeaderItemCount = stickyRow.itemCount
        root.stickyHeaderUnreadCount = stickyRow.groupUnreadCount
        root.stickyHeaderHasRunning = stickyRow.groupHasRunning
        root.stickyHeaderOffset = Math.min(0.0, stickyOffset)
    }

    function visibleDelegates() {
        if (!sessionList || !sessionList.contentItem)
            return []
        var delegates = []
        var children = sessionList.contentItem.children
        for (var i = 0; i < children.length; i++) {
            var child = children[i]
            if (child && child.anchorReady === true)
                delegates.push(child)
        }
        delegates.sort(function(a, b) { return a.y - b.y })
        return delegates
    }

    function findVisibleAnchorDelegate(targetY) {
        var delegates = root.visibleDelegates()
        for (var i = 0; i < delegates.length; i++) {
            var delegate = delegates[i]
            if (delegate.height <= 0)
                continue
            if (delegate.y + delegate.height > targetY)
                return delegate
        }
        return null
    }

    function findVisibleDelegateByAnchor(anchor) {
        if (!anchor)
            return null
        var delegates = root.visibleDelegates()
        for (var i = 0; i < delegates.length; i++) {
            var delegate = delegates[i]
            if (anchor.isHeader) {
                if (delegate.anchorIsHeader && delegate.anchorChannel === anchor.channel)
                    return delegate
                continue
            }
            if (!delegate.anchorIsHeader && delegate.anchorKey === anchor.key)
                return delegate
        }
        return null
    }

    function captureScrollAnchor() {
        if (!sessionList || sessionList.count === 0)
            return { contentY: sessionList ? sessionList.contentY : 0, key: "", channel: "", isHeader: false, offset: 0 }
        var targetY = sessionList.contentY
        var anchorDelegate = root.findVisibleAnchorDelegate(targetY)
        if (anchorDelegate) {
            if (!anchorDelegate.anchorIsHeader && anchorDelegate.anchorKey === (root.activeSessionKey || ""))
                return { contentY: targetY, key: "", channel: "", isHeader: false, offset: 0 }
            return {
                contentY: targetY,
                key: anchorDelegate.anchorIsHeader ? "" : (anchorDelegate.anchorKey || ""),
                channel: anchorDelegate.anchorChannel || "",
                isHeader: anchorDelegate.anchorIsHeader === true,
                offset: targetY - anchorDelegate.y,
            }
        }
        return { contentY: targetY, key: "", channel: "", isHeader: false, offset: 0 }
    }

    function restoreScrollAnchor(anchor) {
        if (!sessionList) {
            return
        }
        var targetY = anchor && anchor.contentY !== undefined ? anchor.contentY : sessionList.contentY
        var anchorDelegate = root.findVisibleDelegateByAnchor(anchor)
        if (anchorDelegate)
            targetY = anchorDelegate.y + (anchor.offset || 0)
        sessionList.contentY = root.clampListContentY(targetY)
        root.refreshStickyHeader()
    }

    function toggleGroup(channel) {
        if (!hasSessionService)
            return
        sessionService.toggleSidebarGroup(channel)
    }

    Connections {
        target: hasSessionService ? sessionService : null
        property var pendingAnchor: null

        function onSidebarProjectionWillChange() {
            pendingAnchor = root.captureScrollAnchor()
        }

        function onSidebarProjectionChanged() {
            root.syncUnreadState()
            if (!pendingAnchor) {
                root.refreshStickyHeader()
                return
            }
            var anchor = pendingAnchor
            pendingAnchor = null
            Qt.callLater(function() {
                sessionList.forceLayout()
                root.restoreScrollAnchor(anchor)
            })
        }
    }

    Component.onCompleted: {
        Qt.callLater(function() {
            root.syncUnreadState()
            root.refreshStickyHeader()
        })
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Gateway status capsule ────────────────────────────────────
        Rectangle {
            id: gwCapsule
            objectName: "gatewayCapsule"
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            Layout.topMargin: 16; Layout.bottomMargin: 0
            implicitHeight: sizeCapsuleHeight
            radius: height / 2
                visible: hasChatService

                    property string currentState: hasChatService ? chatService.state : "idle"
                    property bool isRunning: hasChatService && chatService.state === "running"
                    property bool isStarting: hasChatService && chatService.state === "starting"
                    property bool isError: hasChatService && chatService.state === "error"
            property bool isIdleVisual: !isRunning && !isStarting && !isError
            property bool isHovered: gwHover.containsMouse
            property real actionPulse: 0.0
            property real iconLift: 0.0
            property real iconPulse: 0.0
            property real iconTurn: 0.0

            function stateValue(runningValue, errorValue, startingValue, idleValue) {
                switch (currentState) {
                    case "running":
                        return runningValue
                    case "error":
                        return errorValue
                    case "starting":
                        return startingValue
                    default:
                        return idleValue
                }
            }

            property var stateSpec: stateValue(
                                       {
                                           surfaceColor: gatewaySurfaceRunningTop,
                                           statusColor: gatewayTextRunning,
                                           actionColor: statusSuccess,
                                           dotColor: statusSuccess,
                                           primaryLabel: strings.gateway_running,
                                           actionIconSource: "../resources/icons/gateway-running.svg"
                                       },
                                       {
                                           surfaceColor: gatewaySurfaceErrorTop,
                                           statusColor: statusError,
                                           actionColor: statusError,
                                           dotColor: statusError,
                                           primaryLabel: strings.gateway_error,
                                           actionIconSource: "../resources/icons/gateway-error.svg"
                                       },
                                       {
                                           surfaceColor: gatewaySurfaceStartingTop,
                                           statusColor: gatewayTextStarting,
                                           actionColor: statusWarning,
                                           dotColor: statusWarning,
                                           primaryLabel: strings.gateway_starting,
                                           actionIconSource: "../resources/icons/gateway-starting.svg"
                                       },
                                       {
                                           surfaceColor: gatewaySurfaceIdleTop,
                                           statusColor: gatewayTextIdle,
                                           actionColor: accent,
                                           dotColor: accent,
                                           primaryLabel: strings.button_start_gateway,
                                           actionIconSource: "../resources/icons/gateway-idle.svg"
                                       })
            property color surfaceColor: stateSpec.surfaceColor
            property color statusColor: stateSpec.statusColor
            property color actionColor: stateSpec.actionColor
            property color dotColor: stateSpec.dotColor
            property string primaryLabel: stateSpec.primaryLabel
            property string actionIconSource: stateSpec.actionIconSource
                    property string detailText: hasChatService ? (chatService.gatewayDetail || "") : ""
                    property var gatewayChannels: hasChatService ? (chatService.gatewayChannels || []) : []
                    property bool hasErrorDetail: hasChatService ? Boolean(chatService.gatewayDetailIsError) : false
            z: 6

            function resetVisualState() {
                gwCapsule.actionPulse = 0.0
                gwCapsule.iconLift = 0.0
                gwCapsule.iconPulse = 0.0
                gwCapsule.iconTurn = 0.0
                gwDot.opacity = 1.0
                gwDot.scale = 1.0
            }
            function triggerGatewayAction() {
                        if (!hasChatService || gwCapsule.isStarting)
                            return
                if (gwCapsule.isRunning)
                    chatService.stop()
                else
                    chatService.start()
            }
            onCurrentStateChanged: resetVisualState()
            activeFocusOnTab: true
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

            Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
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
                    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                    Rectangle {
                        id: gwActionFace
                        width: parent.width - 2
                        height: width
                        radius: width / 2
                        anchors.centerIn: parent
                        color: gwCapsule.actionColor
                    }

                    SequentialAnimation {
                        running: gwCapsule.isRunning
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.03; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.0; duration: motionBreath; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isStarting
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.10; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isError
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.06; duration: motionStatusPulse; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.0; duration: motionStatusPulse; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isIdleVisual
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: -0.8; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isIdleVisual
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.06; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isIdleVisual
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconTurn"; to: 6; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconTurn"; to: 0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isStarting
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.10; duration: motionAmbient; easing.type: easeSoft }
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
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: -0.6; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: 0.0; duration: motionBreath; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isRunning
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.08; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionBreath; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isError
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.05; duration: motionStatusPulse; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionStatusPulse; easing.type: easeSoft }
                    }

                    Item {
                        width: sizeGatewayActionIcon
                        height: sizeGatewayActionIcon
                        anchors.centerIn: gwActionFace
                        y: gwCapsule.iconLift
                        scale: 1.0 + gwCapsule.iconPulse
                        rotation: gwCapsule.iconTurn

                        Image {
                            anchors.fill: parent
                            source: gwCapsule.actionIconSource
                            sourceSize: Qt.size(sizeGatewayActionIcon, sizeGatewayActionIcon)
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            mipmap: true
                            opacity: gwCapsule.isHovered ? 1.0 : 0.92
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
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
                        spacing: 7

                        Rectangle {
                            id: gwDot
                            width: 6
                            height: 6
                            radius: 3
                            anchors.verticalCenter: parent.verticalCenter
                            color: gwCapsule.dotColor
                            Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

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
                            opacity: 0.72
                        }
                    }

                    Text {
                        text: gwCapsule.primaryLabel
                        color: gwCapsule.statusColor
                        font.pixelSize: typeButton + 1
                        font.weight: weightBold
                        font.letterSpacing: letterTight
                        Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
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

        // ── Session list ──────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.topMargin: 14
            Layout.bottomMargin: 0
            radius: 22
            color: sidebarListPanelBg
            border.width: 1
            border.color: sidebarListPanelBorder

            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: sidebarListPanelOverlay
                opacity: 0.9
            }

            Item {
                id: sessionsHeaderBar
                objectName: "sessionsHeaderBar"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: 14
                anchors.rightMargin: 12
                anchors.topMargin: 8
                height: 30
                scale: 1.0 + headerPulseScale

                Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

                Item {
                    anchors.left: parent.left
                    anchors.right: newSessionButton.left
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    height: parent.height

                    Row {
                        id: sessionsHeaderContent
                        anchors.centerIn: parent
                        spacing: 8

                        Image {
                            objectName: "sidebarSessionsTitleIcon"
                            width: 22
                            height: 22
                            anchors.verticalCenter: parent.verticalCenter
                            y: 1
                            source: themedIconSource("sidebar-sessions-title")
                            sourceSize: Qt.size(22, 22)
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            mipmap: true
                            opacity: 0.98
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: strings.sidebar_sessions
                            color: textPrimary
                            font.pixelSize: typeBody + 2
                            font.weight: weightBold
                            font.letterSpacing: 0.35
                            textFormat: Text.PlainText
                            opacity: 0.96
                        }

                        UnreadBadge {
                            id: unreadBadge
                            badgeObjectName: "sessionsHeaderUnreadBadge"
                            textObjectName: "sessionsHeaderUnreadText"
                            anchors.verticalCenter: parent.verticalCenter
                            active: hasSessionService && (sessionService.sidebarUnreadCount || 0) > 0
                            count: hasSessionService ? (sessionService.sidebarUnreadCount || 0) : 0
                            mode: "count"
                            fillColor: sidebarHeaderBadgeBg
                            textColor: sidebarHeaderBadgeText
                            visualScale: 1.0 + headerBadgeScale
                        }
                    }
                }

                IconCircleButton {
                    id: newSessionButton
                    objectName: "newSessionButton"
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    buttonSize: sizeControlHeight - 6
                    glyphText: "+"
                    glyphSize: 18
                    fillColor: isDark ? "#12FFFFFF" : "#16000000"
                    hoverFillColor: accent
                    outlineColor: newSessionButton.hovered ? accent : "transparent"
                    glyphColor: newSessionButton.hovered ? "#FFFFFFFF" : textPrimary
                    hoverScale: motionHoverScaleMedium
                    onClicked: root.requestNewSession()
                }

                SequentialAnimation {
                    id: sessionsHeaderPulse
                    running: false
                    ParallelAnimation {
                        NumberAnimation { target: root; property: "headerPulseScale"; from: 0.0; to: 0.03; duration: motionFast; easing.type: easeStandard }
                        NumberAnimation { target: root; property: "headerBadgeScale"; from: 0.0; to: 0.12; duration: motionFast; easing.type: easeEmphasis }
                    }
                    PauseAnimation { duration: motionMicro }
                    ParallelAnimation {
                        NumberAnimation { target: root; property: "headerPulseScale"; to: 0.0; duration: motionPanel; easing.type: easeSoft }
                        NumberAnimation { target: root; property: "headerBadgeScale"; to: 0.0; duration: motionPanel; easing.type: easeSoft }
                    }
                }
            }

            ListView {
                id: sessionList
                objectName: "sidebarSessionList"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                anchors.topMargin: sessionsHeaderBar.y + sessionsHeaderBar.height + 6
                anchors.bottomMargin: 0
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                boundsMovement: Flickable.StopAtBounds
                model: hasSessionService ? sessionService.sidebarModel : null
                spacing: 0
                onContentHeightChanged: {
                    contentY = root.clampListContentY(contentY)
                    root.refreshStickyHeader()
                }
                onHeightChanged: {
                    contentY = root.clampListContentY(contentY)
                    root.refreshStickyHeader()
                }
                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                    width: 4
                    background: Item {}
                    contentItem: Rectangle {
                        implicitWidth: 4
                        radius: 2
                        color: sidebarScrollbarThumb
                        opacity: 0.72
                    }
                }
                footer: Item {
                    width: sessionList.width
                    height: 0
                }

                onContentYChanged: root.refreshStickyHeader()

                delegate: Item {
                    property bool anchorReady: true
                    property bool anchorIsHeader: model.isHeader === true
                    property string anchorKey: model.itemKey || ""
                    property string anchorChannel: model.channel || ""
                    readonly property real sessionTopGap: model.isFirstInGroup ? sizeSidebarHeaderToRowGap : 0
                    readonly property real sessionBottomGap: model.isLastInGroup ? sizeSidebarGroupGap : sizeSidebarGroupInnerGap
                    width: sessionList.width
                    height: model.isHeader
                            ? (sizeSidebarHeader + (!model.expanded ? sizeSidebarGroupGap : 0))
                            : (sizeSessionRow + sessionTopGap + sessionBottomGap)

                    // ── Group header row ──────────────────────────────────────
                    SidebarGroupHeader {
                        id: groupHeaderCard
                        visible: model.isHeader
                        anchors { left: parent.left; right: parent.right; top: parent.top }
                        height: sizeSidebarHeader
                        channel: model.channel || "other"
                        expanded: model.expanded ?? false
                        itemCount: model.itemCount || 0
                        unreadCount: model.groupUnreadCount || 0
                        groupHasRunning: model.groupHasRunning ?? false
                        iconSource: root.channelIconSource(model.channel)
                        chevronObjectName: "sidebarGroupChevronIcon_" + (model.channel || "other")
                        unreadBadgeObjectName: "sidebarGroupUnreadBadge_" + (model.channel || "other")
                        unreadTextObjectName: "sidebarGroupUnreadText_" + (model.channel || "other")
                        onClicked: root.toggleGroup(model.channel)
                    }

                    // ── Session item row ──────────────────────────────────────
                    Item {
                        id: sessionRow
                        visible: !model.isHeader
                        anchors { left: parent.left; right: parent.right; top: parent.top }
                        y: sessionTopGap
                        height: sizeSessionRow + sessionBottomGap
                        clip: true

                        SessionItem {
                            id: inner
                            width: parent.width - 16 - ((model.isChildSession ?? false) ? 12 : 0)
                            x: 8 + ((model.isChildSession ?? false) ? 12 : 0)
                            sessionKey:   model.itemKey   ?? ""
                            sessionTitle: model.itemTitle ?? model.itemKey ?? ""
                            sessionRelativeTime: model.itemUpdatedText ?? ""
                            filledIconSource: (model.isChildSession ?? false)
                                              ? "../resources/icons/sidebar-subagent.svg"
                                              : root.channelFilledIconSource(model.visualChannel ?? model.channel)
                            iconTintColor: root.channelAccent(model.visualChannel ?? model.channel)
                            useIconTint: (model.isChildSession ?? false)
                                         ? false
                                         : root.channelUsesTint(model.visualChannel ?? model.channel)
                            isRunning:    model.isRunning ?? false
                            childIndent: (model.isChildSession ?? false) ? 2 : 0
                            isActive:     root.showChatSelection && sessionKey === root.activeSessionKey
                            dimmed:       root.gatewayIdle
                            hasUnread:    model.itemHasUnread ?? false
                            readOnlySession: model.isReadOnly ?? false
                            onSelected:       root.sessionSelected(sessionKey)
                            onDeleteRequested: root.sessionDeleteRequested(sessionKey)
                        }
                    }
                }

                SidebarGroupHeader {
                    id: stickyHeader
                    objectName: "sidebarStickyHeader"
                    parent: sessionList.parent
                    visible: root.stickyHeaderVisible
                    z: 3
                    anchors.left: sessionList.left
                    anchors.right: sessionList.right
                    y: sessionList.y + root.stickyHeaderOffset
                    height: sizeSidebarHeader
                    channel: root.stickyHeaderChannel
                    expanded: root.stickyHeaderExpanded
                    itemCount: root.stickyHeaderItemCount
                    unreadCount: root.stickyHeaderUnreadCount
                    groupHasRunning: root.stickyHeaderHasRunning
                    iconSource: root.channelIconSource(root.stickyHeaderChannel)
                    chevronObjectName: "sidebarStickyGroupChevronIcon_" + (root.stickyHeaderChannel || "other")
                    unreadBadgeObjectName: "sidebarStickyGroupUnreadBadge_" + (root.stickyHeaderChannel || "other")
                    unreadTextObjectName: "sidebarStickyGroupUnreadText_" + (root.stickyHeaderChannel || "other")
                    onClicked: root.toggleGroup(root.stickyHeaderChannel)
                }


                // Loading state
                Item {
                    id: loadingStateWrap
                    objectName: "sidebarLoadingState"
                    anchors.top: parent.top
                    anchors.topMargin: 18
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(sessionList.width - 20, 216)
                    height: loadingStateCard.implicitHeight
                visible: sessionList.count === 0 && hasSessionService && sessionService.sessionsLoading

                    Rectangle {
                        id: loadingStateCard
                        width: parent.width
                        implicitHeight: loadingStateContent.implicitHeight + 24
                        radius: 18
                        color: isDark ? "#18FFFFFF" : "#0B000000"
                        border.width: 1
                        border.color: isDark ? "#32FFFFFF" : "#26000000"

                        Column {
                            id: loadingStateContent
                            anchors.centerIn: parent
                            anchors.verticalCenterOffset: 2
                            width: parent.width - 24
                            spacing: 10

                            Rectangle {
                                width: 46
                                height: 46
                                radius: 23
                                anchors.horizontalCenter: parent.horizontalCenter
                                color: isDark ? "#16FFFFFF" : "#10FFB33D"
                                border.width: 1
                                border.color: isDark ? "#22FFFFFF" : borderSubtle

                                LoadingOrbit {
                                    anchors.centerIn: parent
                                    width: 28
                                    height: 28
                                    running: loadingStateWrap.visible
                                    haloOpacity: 0.16
                                }
                            }

                            Text {
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                text: strings.sidebar_loading_title
                                color: isDark ? "#FFF1E1" : "#4B2D12"
                                font.pixelSize: typeBody + 1
                                font.weight: weightBold
                                wrapMode: Text.WordWrap
                                lineHeight: 1.12
                            }

                            Text {
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                text: strings.sidebar_loading_hint
                                color: isDark ? "#DCC5A8" : "#74512F"
                                font.pixelSize: typeMeta
                                wrapMode: Text.WordWrap
                                lineHeight: 1.18
                            }
                        }
                    }
                }

                // Empty state
                Item {
                    id: emptyStateWrap
                    objectName: "sidebarEmptyStateWrap"
                    anchors.top: parent.top
                    anchors.topMargin: 18
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(sessionList.width - 28, 196)
                    height: emptyStateCard.implicitHeight
                visible: sessionList.count === 0 && !(hasSessionService && sessionService.sessionsLoading)

                    Rectangle {
                        id: emptyStateCard
                        objectName: "sidebarEmptyState"
                        width: parent.width
                        implicitHeight: emptyStateContent.implicitHeight + 24
                        radius: 18
                        color: emptyStateHover.containsMouse ? (isDark ? "#22FFFFFF" : "#14000000") : (isDark ? "#18FFFFFF" : "#0B000000")
                        border.width: 1
                        border.color: emptyStateHover.containsMouse ? sessionRowActiveBorder : (isDark ? "#46FFFFFF" : "#26000000")
                        scale: emptyStateHover.pressed ? 0.988 : (emptyStateHover.containsMouse ? motionHoverScaleMedium : 1.0)

                    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                    Column {
                        id: emptyStateContent
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: 4
                        width: parent.width - 28
                        spacing: 11

                        Item {
                            width: 50
                            height: 50
                            anchors.horizontalCenter: parent.horizontalCenter

                            Rectangle {
                                width: 46
                                height: 46
                                radius: 23
                                anchors.centerIn: parent
                                color: emptyStateHover.containsMouse ? (isDark ? "#18FFFFFF" : "#10000000") : chatEmptyIconBg
                                border.width: 1
                                border.color: emptyStateHover.containsMouse ? sessionRowActiveBorder : (isDark ? "#38FFFFFF" : chatEmptyIconBorder)

                                Image {
                                    objectName: "sidebarEmptyChatIcon"
                        width: 18
                        height: 18
                                    anchors.centerIn: parent
                                    source: themedIconSource("chat")
                        sourceSize: Qt.size(18, 18)
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                    mipmap: true
                                    opacity: 0.96
                                }
                            }

                            Rectangle {
                                width: 16
                                height: 16
                                radius: 8
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.rightMargin: 4
                                anchors.topMargin: 4
                                color: emptyStateHover.containsMouse ? accent : accentGlow

                                PlusGlyph {
                                    glyphSize: 7
                                    barThickness: 1.8
                                    glyphColor: bgSidebar
                                    anchors.centerIn: parent
                                }
                            }
                        }

                        Text {
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            text: strings.sidebar_empty_title
                            color: isDark ? "#FFF1E1" : "#4B2D12"
                            font.pixelSize: typeBody + 1
                            font.weight: weightBold
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            text: strings.sidebar_empty_hint
                            color: isDark ? "#DCC5A8" : "#74512F"
                            font.pixelSize: typeMeta
                            wrapMode: Text.WordWrap
                        }

                        PillActionButton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: strings.sidebar_empty_cta
                            leadingText: "+"
                            minHeight: 28
                            horizontalPadding: 18
                            fillColor: emptyStateHover.containsMouse ? accent : accentGlow
                            hoverFillColor: emptyStateHover.containsMouse ? accent : accentGlow
                            outlineColor: emptyStateHover.containsMouse ? accent : sessionRowActiveBorder
                            hoverOutlineColor: emptyStateHover.containsMouse ? accent : sessionRowActiveBorder
                            textColor: bgSidebar
                        }
                    }

                        MouseArea {
                            id: emptyStateHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.requestNewSession()
                        }
                    }
                }
            }
        }

        // ── App icon (bottom) ────────────────────────────────────────
        Item {
            id: bottomActions
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            Layout.bottomMargin: 6
            property bool diagnosticsHovered: diagnosticsArea.containsMouse

            // Outer glow ring (sibling — never clipped)
            Rectangle {
                id: glowRing
                anchors.centerIn: appIconBtn
                width: appIconBtn.width + spacingMd + 2; height: appIconBtn.height + spacingMd + 2
                radius: width / 2
                color: "transparent"
                border.width: 1.5
                border.color: accent
                opacity: 0
                antialiasing: true
                scale: appIconBtn.scale
                rotation: appIconBtn.rotation

                SequentialAnimation {
                    id: breatheAnim
                    running: !appIconArea.containsMouse
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

            // Second subtle ring (depth layer)
            Rectangle {
                id: glowRingOuter
                anchors.centerIn: appIconBtn
                width: appIconBtn.width + spacingXl; height: appIconBtn.height + spacingXl
                radius: width / 2
                color: "transparent"
                border.width: 1
                border.color: accent
                opacity: appIconArea.containsMouse ? 0.25 : 0
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

            // Icon body
            Rectangle {
                id: appIconBtn
                width: sizeAppIcon; height: sizeAppIcon; radius: sizeAppIcon / 2
                anchors.left: parent.left
                anchors.leftMargin: 18
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 6
                color: "transparent"
                border.width: 1.5
                border.color: appIconArea.containsMouse ? accent : borderSubtle
                antialiasing: true

                scale: appIconArea.pressed ? motionPressScaleStrong
                       : (appIconArea.containsMouse ? motionHoverScaleStrong : 1.0)
                rotation: appIconArea.containsMouse ? -10 : 0

                Behavior on scale {
                    NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
                }
                Behavior on border.color {
                    ColorAnimation { duration: motionUi; easing.type: easeStandard }
                }
                Behavior on rotation {
                    NumberAnimation { duration: motionPanel; easing.type: easeEmphasis }
                }

                // Circular logo (pre-clipped PNG)
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
                    onClicked: {
                        if (!root.showingSettings)
                            root.settingsRequested()
                    }
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

            // ── Speech bubble (hover tooltip) ──────────────────────────
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

                // Bubble text
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
