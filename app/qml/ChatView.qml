import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Dialogs
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    color: "transparent"

    property var chatService: null
    property var sessionService: null
    property var configService: null
    readonly property int composerMinHeight: 44
    readonly property int composerMaxHeight: 140
    readonly property int composerScrollInset: 12
    readonly property int composerBottomSafeGap: 4
    readonly property real composerFieldRadius: composerMinHeight / 2
    readonly property int chatTopSafeInset: windowContentInsetTop
    readonly property int chatTopContentGap: spacingMd
    readonly property int chatSideInset: windowContentInsetSide + spacingSm
    readonly property int chatIdleBottomGap: windowContentInsetBottom
    readonly property int composerBottomMargin: Math.max(spacingXs, windowContentInsetBottom - spacingSm)
    readonly property int composerDockGap: windowContentInsetBottom
    readonly property int composerEdgeInset: spacingSm
    readonly property bool hasDraftAttachments: chatService ? chatService.draftAttachmentCount > 0 : false
    readonly property bool hasSessionService: sessionService !== null
    readonly property bool activeSessionReadOnly: hasSessionService ? sessionService.activeSessionReadOnly : false
    readonly property string gatewayStateValue: {
        if (!chatService)
            return "idle"
        if (typeof chatService.gatewayState === "string" && chatService.gatewayState !== "")
            return chatService.gatewayState
        if (typeof chatService.state === "string" && chatService.state !== "")
            return chatService.state
        return "idle"
    }
    signal messageCopied()

    // Message list and composer share one inset source so content never gets
    // visually clipped by the window edge or by the floating composer itself.
    ListView {
        id: messageList
        objectName: "chatMessageList"
        anchors.fill: parent
        anchors.leftMargin: root.chatSideInset
        anchors.rightMargin: root.chatSideInset
        anchors.bottomMargin: composerBar.presentedListBottomInset
        clip: true
        spacing: spacingLg
        topMargin: root.chatTopSafeInset + root.chatTopContentGap
        bottomMargin: 0
        focus: root.visible
        activeFocusOnTab: true
        boundsBehavior: Flickable.StopAtBounds
        cacheBuffer: 20000
        reuseItems: false
        highlightFollowsCurrentItem: false
        highlightRangeMode: ListView.NoHighlightRange
        verticalLayoutDirection: ListView.TopToBottom

        model: chatService ? chatService.messages : null

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Component.onCompleted: scheduleSessionViewportReady()

        // ── Bottom-pinned follow state ──────────────────────────────
        property bool historyLoading: chatService ? chatService.historyLoading : false
        readonly property string activeSessionKey: sessionService ? sessionService.activeKey : ""
        property string renderedSessionKey: activeSessionKey
        readonly property string viewPhase: {
            if (!chatService) return "idle"
            var phase = chatService.viewPhase
            if (phase !== undefined && phase !== null && phase !== "") return phase
            if (root.gatewayStateValue === "error") return "error"
            if (chatService.historyLoading || root.gatewayStateValue === "starting") return "loading"
            if (chatService.activeSessionReady) return "ready"
            return "idle"
        }
        readonly property bool sessionReady: chatService ? chatService.activeSessionReady : false
        readonly property bool sessionHasMessages: chatService ? chatService.activeSessionHasMessages : false
        readonly property real keyboardLineStep: Math.max(48, Math.round(height * 0.08))
        readonly property real keyboardPageStep: Math.max(keyboardLineStep, Math.round(height * 0.9))
        readonly property real nearEndThresholdPx: Math.max(24, keyboardLineStep)
        readonly property real animateReconcileThresholdPx: Math.max(height * 0.75, 240)
        property real pendingRestoreContentY: -1
        property bool pendingRestorePinned: false
        property bool bottomPinned: true
        property int suppressViewportTracking: 0
        property var pendingPinnedReconcile: null
        property bool programmaticFollowActive: false

        function positionAfterLayout() {
            if (count <= 0) return
            forceLayout()
            positionViewAtEnd()
        }

        function maxContentY() {
            return Math.max(originY, originY + contentHeight - height)
        }

        function minContentY() {
            return originY
        }

        function clampContentY(value) {
            return Math.max(minContentY(), Math.min(maxContentY(), value))
        }

        function isNearEnd() {
            return maxContentY() - contentY <= nearEndThresholdPx
        }

        function withSuppressedViewportTracking(fn) {
            suppressViewportTracking += 1
            try {
                fn()
            } finally {
                suppressViewportTracking = Math.max(0, suppressViewportTracking - 1)
            }
        }

        function refreshPinnedFromViewport() {
            if (suppressViewportTracking > 0) return
            if (count <= 0) {
                bottomPinned = true
                return
            }
            bottomPinned = isNearEnd()
        }

        onBottomPinnedChanged: {
            // Detaching from bottom means user owns scrolling now.
            if (!bottomPinned)
                cancelProgrammaticFollow()
        }

        function finishProgrammaticFollow() {
            if (!programmaticFollowActive) return
            programmaticFollowActive = false
            suppressViewportTracking = Math.max(0, suppressViewportTracking - 1)
            if (bottomPinned && !historyLoading && count > 0 && !isNearEnd())
                queuePinnedReconcile(shouldAnimatePinnedReconcile())
        }

        function cancelProgrammaticFollow() {
            if (!programmaticFollowActive && !bottomPinnedFollower.running)
                return
            bottomPinnedFollower.stop()
            if (!programmaticFollowActive) return
            programmaticFollowActive = false
            suppressViewportTracking = Math.max(0, suppressViewportTracking - 1)
        }

        function applyPinnedReconcileOnce(animated) {
            if (!bottomPinned || historyLoading || count <= 0)
                return
            forceLayout()
            setProgrammaticContentY(maxContentY(), animated)
        }

        function setProgrammaticContentY(targetY, animated) {
            if (count <= 0) return
            var nextY = clampContentY(targetY)
            if (Math.abs(nextY - contentY) <= 1) {
                cancelProgrammaticFollow()
                withSuppressedViewportTracking(function() {
                    contentY = nextY
                })
                return
            }

            if (!animated) {
                cancelProgrammaticFollow()
                withSuppressedViewportTracking(function() {
                    contentY = nextY
                })
                return
            }

            if (!programmaticFollowActive) {
                suppressViewportTracking += 1
                programmaticFollowActive = true
            } else if (bottomPinnedFollower.running) {
                bottomPinnedFollower.stop()
            }

            bottomPinnedFollower.from = contentY
            bottomPinnedFollower.to = nextY
            bottomPinnedFollower.start()
        }

        function reconcilePinnedBottom(animated) {
            var useAnimation = animated !== false
            applyPinnedReconcileOnce(useAnimation)
            Qt.callLater(function() {
                if (!messageList.bottomPinned || messageList.historyLoading || messageList.count <= 0)
                    return
                messageList.applyPinnedReconcileOnce(useAnimation)
            })
        }

        function queuePinnedReconcile(animated) {
            if (pendingPinnedReconcile !== null) {
                pendingPinnedReconcile = {
                    animated: Boolean(pendingPinnedReconcile.animated) && animated !== false
                }
                return
            }
            pendingPinnedReconcile = { animated: animated !== false }
            scheduleQueuedReconcile()
        }

        function scheduleQueuedReconcile() {
            Qt.callLater(function() {
                var request = messageList.pendingPinnedReconcile
                if (request === null)
                    return
                var useAnimation = request.animated !== false
                messageList.pendingPinnedReconcile = null
                messageList.reconcilePinnedBottom(useAnimation)
            })
        }

        function shouldAnimatePinnedReconcile() {
            return Math.abs(maxContentY() - contentY) <= animateReconcileThresholdPx
        }

        function forceFollowToEnd(animated) {
            bottomPinned = true
            if (animated === false) {
                pendingPinnedReconcile = null
                reconcilePinnedBottom(false)
                return
            }
            queuePinnedReconcile(animated)
        }

        function messageMetaAt(row) {
            if (row < 0 || !model) return null
            var idx = model.index(row, 0)
            return {
                role: model.data(idx, Qt.UserRole + 2) || "",
                status: model.data(idx, Qt.UserRole + 5) || "",
                entranceStyle: model.data(idx, Qt.UserRole + 7) || ""
            }
        }

        function pinOnAppend(row) {
            var message = messageMetaAt(row)
            if (!message) return false
            return message.role === "user"
                || message.role === "assistant"
                || message.role === "system"
                || message.status === "typing"
        }

        function shouldForceInstantAppend(row) {
            var message = messageMetaAt(row)
            if (!message) return false
            return message.entranceStyle === "greeting"
                || message.role === "user"
                || message.status === "typing"
        }

        function shouldReconcileOnStatusUpdate(row, status) {
            if (status !== "done" && status !== "error") return false
            var message = messageMetaAt(row)
            if (!message) return false
            return message.role === "assistant" || message.role === "system"
        }

        function scrollBy(delta) {
            if (count <= 0) return
            cancelProgrammaticFollow()
            var nextY = contentY + delta
            if (nextY <= minContentY()) {
                positionViewAtBeginning()
                refreshPinnedFromViewport()
                return
            }
            if (nextY >= maxContentY()) {
                positionAfterLayout()
                refreshPinnedFromViewport()
                return
            }
            contentY = clampContentY(nextY)
            refreshPinnedFromViewport()
        }

        function handleNavigationKey(event) {
            if (!event || messageInput.activeFocus || count <= 0) return false
            cancelProgrammaticFollow()

            switch (event.key) {
            case Qt.Key_Up:
                scrollBy(-keyboardLineStep)
                return true
            case Qt.Key_Down:
                scrollBy(keyboardLineStep)
                return true
            case Qt.Key_PageUp:
                scrollBy(-keyboardPageStep)
                return true
            case Qt.Key_PageDown:
                scrollBy(keyboardPageStep)
                return true
            case Qt.Key_Home:
                positionViewAtBeginning()
                refreshPinnedFromViewport()
                return true
            case Qt.Key_End:
                positionAfterLayout()
                refreshPinnedFromViewport()
                return true
            default:
                return false
            }
        }

        function captureViewportBeforeReset() {
            pendingRestorePinned = bottomPinned
            pendingRestoreContentY = contentY
        }

        function clearPendingViewportRestore() {
            pendingRestoreContentY = -1
            pendingRestorePinned = false
        }

        function scheduleSessionViewportReady() {
            Qt.callLater(function() {
                if (messageList.historyLoading || messageList.count <= 0)
                    return
                messageList.bottomPinned = true
                messageList.queuePinnedReconcile(false)
            })
        }

        function restoreViewportAfterReset() {
            if (pendingRestoreContentY < 0 && !pendingRestorePinned) return

            Qt.callLater(function() {
                if (messageList.count <= 0) {
                    messageList.clearPendingViewportRestore()
                    messageList.bottomPinned = true
                    return
                }

                if (messageList.pendingRestorePinned) {
                    messageList.bottomPinned = true
                    messageList.reconcilePinnedBottom(false)
                } else {
                    messageList.setProgrammaticContentY(messageList.pendingRestoreContentY, false)
                    messageList.refreshPinnedFromViewport()
                }
                messageList.clearPendingViewportRestore()
            })
        }

        Connections {
            target: chatService
            ignoreUnknownSignals: true

            function onHistoryLoadingChanged(loading) {
                if (loading) {
                    messageList.cancelFlick()
                    messageList.cancelProgrammaticFollow()
                }
            }

            function onMessageAppended(_row) {
                if (messageList.pinOnAppend(_row))
                    messageList.bottomPinned = true
                if (messageList.shouldForceInstantAppend(_row)) {
                    messageList.forceFollowToEnd(false)
                    return
                }
                messageList.queuePinnedReconcile(messageList.shouldAnimatePinnedReconcile())
            }

            function onStatusUpdated(_row, _status) {
                if (messageList.shouldReconcileOnStatusUpdate(_row, _status))
                    messageList.queuePinnedReconcile(messageList.shouldAnimatePinnedReconcile())
            }

            function onContentUpdated(_row, _content) {
                if (messageList.bottomPinned)
                    messageList.forceFollowToEnd(false)
            }
        }

        Connections {
            target: messageList.model
            ignoreUnknownSignals: true

            function onModelAboutToBeReset() {
                if (messageList.activeSessionKey === messageList.renderedSessionKey) {
                    messageList.captureViewportBeforeReset()
                } else {
                    messageList.clearPendingViewportRestore()
                }
            }

            function onModelReset() {
                var switchedSession = messageList.activeSessionKey !== messageList.renderedSessionKey
                messageList.renderedSessionKey = messageList.activeSessionKey
                if (switchedSession) {
                    return
                }
                messageList.restoreViewportAfterReset()
            }
        }

        Connections {
            target: chatService
            ignoreUnknownSignals: true

            function onSessionViewportReady(key) {
                Qt.callLater(function() {
                    messageList.renderedSessionKey = key || messageList.activeSessionKey
                    messageList.forceActiveFocus()
                    messageList.scheduleSessionViewportReady()
                })
            }
        }

        SmoothedAnimation {
            id: bottomPinnedFollower
            target: messageList
            property: "contentY"
            velocity: Math.max(12000, messageList.height * 28)

            onRunningChanged: {
                if (!running)
                    messageList.finishProgrammaticFollow()
            }
        }

        function onViewportGeometryChanged() {
            if (!bottomPinned)
                return
            queuePinnedReconcile(shouldAnimatePinnedReconcile())
        }

        onMovementStarted: cancelProgrammaticFollow()
        onMovementEnded: refreshPinnedFromViewport()
        onFlickEnded: refreshPinnedFromViewport()
        onHeightChanged: onViewportGeometryChanged()
        onContentHeightChanged: onViewportGeometryChanged()

        Keys.onPressed: function(event) {
            if (messageList.handleNavigationKey(event))
                event.accepted = true
        }

        delegate: MessageBubble {
            width: messageList.width
            role: model.role ?? "assistant"
            content: model.content ?? ""
            format: model.format ?? "plain"
            status: model.status ?? "done"
            attachments: model.attachments ?? []
            references: model.references ?? ({})
            messageId: model.id ?? -1
            messageRow: index
            entranceStyle: model.entranceStyle ?? "none"
            entrancePending: model.entrancePending ?? false
            showDateDivider: (model.dividerText ?? "") !== ""
            dateDividerText: model.dividerText ?? ""
            toastFunc: function() { root.messageCopied() }
        }

        // ── Empty state — multi-state onboarding cards ──────────
        Item {
            id: historyLoadingState
            anchors.centerIn: parent
            width: Math.min(320, messageList.width - 80)
            height: loadingCol.implicitHeight
            visible: messageList.count === 0 && messageList.viewPhase === "loading"

            Column {
                id: loadingCol
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 12

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 68
                    height: 68
                    radius: 34
                    color: isDark ? "#16FFFFFF" : "#10FFB33D"
                    border.color: isDark ? "#22FFFFFF" : borderSubtle

                    LoadingOrbit {
                        anchors.centerIn: parent
                        width: 38
                        height: 38
                        running: historyLoadingState.visible
                        haloOpacity: 0.16
                    }
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.gatewayStateValue === "starting"
                          ? strings.empty_starting_hint
                          : strings.chat_loading_history
                    color: textTertiary
                    font.pixelSize: typeMeta
                    font.weight: weightDemiBold
                    font.letterSpacing: letterWide
                }
            }
        }

        Item {
            anchors.centerIn: parent
            width: Math.min(360, messageList.width - 80)
            height: emptyCol.implicitHeight
            visible: messageList.count === 0
                     && messageList.viewPhase !== "loading"

            Column {
                id: emptyCol
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width
                spacing: 16

                // ── State 1: Needs setup (no config) ──
                Column {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: configService && configService.needsSetup
                    spacing: 14
                    width: parent.width

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 72; height: 72; radius: 36
                        color: chatEmptyIconBg
                        border.width: isDark ? 0 : 1
                        border.color: chatEmptyIconBorder
                        Image {
                            objectName: "chatEmptySetupIcon"
                            anchors.centerIn: parent
                            source: themedIconSource("settings")
                            sourceSize: Qt.size(34, 34)
                            width: 34; height: 34
                            opacity: isDark ? 0.72 : 0.96
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_setup_title
                        color: textPrimary
                        font.pixelSize: typeTitle
                        font.weight: weightDemiBold
                        font.letterSpacing: 0.3
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_setup_hint
                        color: textTertiary
                        font.pixelSize: typeButton
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width
                        wrapMode: Text.WordWrap
                    }
                }

                // ── State 2: Gateway error ──
                Column {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: messageList.viewPhase === "error"
                             && !(configService && configService.needsSetup)
                    spacing: 14
                    width: parent.width

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 72; height: 72; radius: 36
                        color: chatErrorBadgeBg
                        Text {
                            anchors.centerIn: parent
                            text: "!"
                            color: statusError
                            font.pixelSize: 28
                            font.weight: Font.Bold
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_error_hint
                        color: textPrimary
                        font.pixelSize: typeTitle
                        font.weight: weightDemiBold
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: chatService ? (chatService.lastError || "") : ""
                        color: textTertiary
                        font.pixelSize: typeLabel
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width
                        wrapMode: Text.WordWrap
                        visible: text !== ""
                    }
                    PillActionButton {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 120
                        minHeight: 38
                        text: strings.empty_error_btn
                        onClicked: if (chatService) chatService.start()
                    }
                }

                // ── State 3: Ready (session visible, no messages yet) ──
                Column {
                    id: readyEmptyState
                    objectName: "chatEmptyReadyState"
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: messageList.viewPhase === "ready"
                             && !messageList.sessionHasMessages
                    spacing: 14

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 72; height: 72; radius: 36
                        color: chatEmptyIconBg
                        border.width: isDark ? 0 : 1
                        border.color: chatEmptyIconBorder
                        Image {
                            objectName: "chatEmptyReadyIcon"
                            anchors.centerIn: parent
                            source: themedIconSource("chat")
                            sourceSize: Qt.size(34, 34)
                            width: 34; height: 34
                            opacity: isDark ? 0.68 : 0.94
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_chat_title
                        color: textPrimary
                        font.pixelSize: typeTitle
                        font.weight: weightDemiBold
                        font.letterSpacing: 0.3
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: root.gatewayStateValue === "running"
                              ? strings.empty_chat_hint
                              : strings.empty_chat_idle_hint
                        color: textTertiary
                        font.pixelSize: typeButton
                    }
                }

                // ── State 4: Idle/Stopped (gateway not started) ──
                Column {
                    id: idleEmptyState
                    objectName: "chatEmptyIdleState"
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: messageList.viewPhase === "idle"
                             && !(configService && configService.needsSetup)
                    spacing: 14

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 72; height: 72; radius: 36
                        color: chatEmptyIconBg
                        border.width: isDark ? 0 : 1
                        border.color: chatEmptyIconBorder
                        Image {
                            objectName: "chatEmptyIdleIcon"
                            anchors.centerIn: parent
                            source: themedIconSource("zap")
                            sourceSize: Qt.size(34, 34)
                            width: 34; height: 34
                            opacity: isDark ? 0.7 : 0.96
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_idle_title
                        color: textPrimary
                        font.pixelSize: typeTitle
                        font.weight: weightDemiBold
                        font.letterSpacing: 0.3
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_idle_hint
                        color: textTertiary
                        font.pixelSize: typeButton
                    }
                }
            }
        }
    }

    // ── Input bar ────────────────────────────────────────────────────
    Item {
        id: composerBar
        objectName: "composerBar"
        readonly property bool active: root.gatewayStateValue === "running" && !root.activeSessionReadOnly
        readonly property real visibleHeight: composerContent.implicitHeight + 20
        readonly property int revealDuration: motionPanel + 40
        // targetListBottomInset is the layout fact; presentedListBottomInset is the animated projection.
        readonly property real targetListBottomInset: active
                                                   ? visibleHeight + root.composerBottomMargin + root.composerDockGap
                                                   : root.chatIdleBottomGap
        property real presentedListBottomInset: targetListBottomInset

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: root.chatSideInset + root.composerEdgeInset
        anchors.rightMargin: root.chatSideInset + root.composerEdgeInset
        anchors.bottomMargin: root.composerBottomMargin
        height: visibleHeight
        enabled: active
        opacity: active ? 1.0 : 0.0
        scale: active ? 1.0 : 0.992
        transform: Translate {
            y: composerBar.active ? 0 : 22
            Behavior on y { NumberAnimation { duration: composerBar.revealDuration; easing.type: easeEmphasis } }
        }

        Behavior on presentedListBottomInset { NumberAnimation { duration: composerBar.revealDuration; easing.type: easeEmphasis } }
        Behavior on opacity { NumberAnimation { duration: motionUi + 40; easing.type: easeStandard } }
        Behavior on scale { NumberAnimation { duration: composerBar.revealDuration; easing.type: easeEmphasis } }

        Column {
            id: composerContent
            anchors {
                left: parent.left; right: parent.right
                verticalCenter: parent.verticalCenter
                leftMargin: 18; rightMargin: 18
            }
            spacing: root.hasDraftAttachments ? 10 : 0

            Rectangle {
                id: attachmentStrip
                objectName: "attachmentStrip"
                width: parent.width
                height: root.hasDraftAttachments ? 72 : 0
                radius: 22
                color: isDark ? "#E623170F" : "#F7FFFFFF"
                border.width: 1
                border.color: root.hasDraftAttachments ? borderDefault : borderSubtle
                opacity: root.hasDraftAttachments ? 1.0 : 0.0
                clip: true
                visible: opacity > 0
                Behavior on height { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
                Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: "transparent"
                    border.width: 1
                    border.color: isDark ? "#15FFFFFF" : "#22FFFFFF"
                    opacity: root.hasDraftAttachments ? 1.0 : 0.0
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    height: 28
                    radius: parent.radius
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: isDark ? "#20FFFFFF" : "#D9FFFFFF" }
                        GradientStop { position: 1.0; color: "#00FFFFFF" }
                    }
                    opacity: 0.55
                }

                ListView {
                    id: attachmentList
                    objectName: "attachmentList"
                    anchors.fill: parent
                    anchors.margins: 8
                    orientation: ListView.Horizontal
                    spacing: 8
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: chatService ? chatService.draftAttachments : null
                    add: Transition {
                        ParallelAnimation {
                            NumberAnimation {
                                property: "opacity"
                                from: 0.0
                                to: 1.0
                                duration: motionUi
                                easing.type: easeStandard
                            }
                            NumberAnimation {
                                property: "scale"
                                from: 0.94
                                to: 1.0
                                duration: motionUi + 20
                                easing.type: easeEmphasis
                            }
                            NumberAnimation {
                                property: "x"
                                from: ViewTransition.item.x + 8
                                to: ViewTransition.item.x
                                duration: motionUi
                                easing.type: easeEmphasis
                            }
                        }
                    }
                    addDisplaced: Transition {
                        NumberAnimation {
                            properties: "x"
                            duration: motionUi
                            easing.type: easeEmphasis
                        }
                    }
                    removeDisplaced: Transition {
                        NumberAnimation {
                            properties: "x"
                            duration: motionUi
                            easing.type: easeEmphasis
                        }
                    }

                    delegate: AttachmentChip {
                        required property int index
                        required property string fileName
                        required property string fileSizeLabel
                        required property string previewUrl
                        required property bool isImage
                        required property string extensionLabel

                        fileName: model.fileName ?? ""
                        fileSizeLabel: model.fileSizeLabel ?? ""
                        previewUrl: model.previewUrl ?? ""
                        isImage: Boolean(model.isImage)
                        extensionLabel: model.extensionLabel ?? "FILE"
                        removable: true
                        removeAction: function() {
                            if (chatService)
                                chatService.removeDraftAttachment(index)
                        }
                    }
                }
            }

            RowLayout {
                id: inputRow
                width: parent.width
                spacing: 0

                Rectangle {
                    id: composerField
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    readonly property bool focused: messageInput.activeFocus
                    readonly property bool hovered: messageInput.hovered || attachHover.containsMouse
                    readonly property color fillColor: focused ? bgInputFocus : (hovered ? bgInputHover : bgInput)
                    readonly property color strokeColor: focused ? borderFocus : (hovered ? borderDefault : borderSubtle)
                    readonly property real strokeWidth: focused ? 1.35 : 1.0
                    readonly property real fieldScale: focused ? 1.006 : (hovered ? 1.003 : 1.0)
                    Layout.preferredHeight: Math.min(
                                              Math.max(
                                                  messageInput.contentHeight
                                                  + messageInput.topPadding
                                                  + messageInput.bottomPadding
                                                  + root.composerScrollInset,
                                                  root.composerMinHeight
                                              ),
                                              root.composerMaxHeight
                                          )
                    radius: root.composerFieldRadius
                    color: fillColor
                    border.color: strokeColor
                    border.width: strokeWidth
                    clip: true
                    scale: fieldScale
                    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on border.width { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                    Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

                    Rectangle {
                        id: attachButton
                        width: 32
                        height: 32
                        radius: 16
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        color: attachHover.containsMouse ? (isDark ? "#38F38F1A" : "#1AE68A18") : "transparent"
                        scale: attachHover.containsMouse ? motionHoverScaleSubtle : 1.0
                        Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                        Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                        Rectangle {
                            anchors.fill: parent
                            radius: parent.radius
                            color: "transparent"
                            border.width: 1
                            border.color: root.hasDraftAttachments ? accent : "transparent"
                            opacity: root.hasDraftAttachments ? 0.42 : 0.0
                            scale: root.hasDraftAttachments ? 1.0 : 0.92
                            Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                            Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
                        }

                        Rectangle {
                            width: 6
                            height: 6
                            radius: 3
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.rightMargin: 3
                            anchors.topMargin: 3
                            color: accent
                            opacity: root.hasDraftAttachments ? 0.95 : 0.0
                            scale: root.hasDraftAttachments ? 1.0 : 0.6
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                            Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
                        }

                        Image {
                            anchors.centerIn: parent
                            source: "../resources/icons/paperclip.svg"
                            width: 19
                            height: 19
                            sourceSize: Qt.size(19, 19)
                            opacity: attachHover.containsMouse ? 1.0 : 0.78
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                        }

                        MouseArea {
                            id: attachHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: attachmentDialog.open()
                        }
                    }

                    Rectangle {
                        id: innerSendButton
                        width: sizeButton
                        height: sizeButton
                        radius: width / 2
                        anchors.right: parent.right
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        property bool canSend: (messageInput.text.trim().length > 0 || root.hasDraftAttachments)
                                              && chatService
                                              && root.gatewayStateValue === "running"
                        color: sendHover.containsMouse && canSend
                               ? accentHover
                               : (canSend ? accent : chatComposerSendDisabled)
                        border.width: canSend ? 0 : 1
                        border.color: canSend ? "transparent" : borderSubtle
                        scale: sendHover.pressed && canSend
                               ? motionPressScaleStrong
                               : (sendHover.containsMouse && canSend ? motionHoverScaleSubtle : 1.0)
                        antialiasing: true
                        Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                        Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                        Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                        Rectangle {
                            anchors.fill: parent
                            radius: parent.radius
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: chatComposerSendHighlight }
                                GradientStop { position: 1.0; color: "#00FFFFFF" }
                            }
                            opacity: parent.canSend ? (sendHover.containsMouse ? 0.82 : 0.66) : 0.0
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                        }

                        Image {
                            anchors.centerIn: parent
                            source: "../resources/icons/send.svg"
                            width: 20
                            height: 20
                            sourceSize: Qt.size(20, 20)
                            opacity: parent.canSend ? 1.0 : 0.3
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                        }

                        MouseArea {
                            id: sendHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: parent.canSend ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: if (parent.canSend) sendMessage()
                        }
                    }

                    ScrollView {
                        id: inputScroll
                        anchors.left: attachButton.right
                        anchors.right: innerSendButton.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: 4
                        anchors.rightMargin: 8
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded

                        TextArea {
                            id: messageInput
                            objectName: "chatMessageInput"
                            property bool baoClickAwayEditor: true
                            hoverEnabled: true
                            placeholderText: strings.chat_placeholder
                            placeholderTextColor: textPlaceholder
                            color: textPrimary
                            background: null
                            wrapMode: TextArea.Wrap
                            leftPadding: sizeFieldPaddingX - 2
                            rightPadding: sizeFieldPaddingX
                            topPadding: 15
                            bottomPadding: 5
                            font.pixelSize: typeBody
                            selectionColor: textSelectionBg
                            selectedTextColor: textSelectionFg

                            onCursorPositionChanged: {
                                if (!activeFocus || cursorPosition !== length) return
                                var flick = inputScroll.contentItem
                                if (!flick) return
                                if (flick.contentHeight > flick.height)
                                    flick.contentY = flick.contentHeight - flick.height + root.composerBottomSafeGap
                            }

                            Keys.onReturnPressed: function(event) {
                                if (event.modifiers & Qt.ShiftModifier) {
                                    event.accepted = false
                                } else {
                                    event.accepted = true
                                    sendMessage()
                                }
                            }

                            Keys.onPressed: function(event) {
                                if (!event.matches(StandardKey.Paste))
                                    return
                                if (!chatService)
                                    return
                                if (chatService.pasteClipboardAttachment())
                                    event.accepted = true
                            }
                        }
                    }
                }
            }
        }

        FileDialog {
            id: attachmentDialog
            title: strings.chat_attach_title
            fileMode: FileDialog.OpenFiles
            onAccepted: if (chatService) chatService.addDraftAttachments(selectedFiles)
        }
    }

    function sendMessage() {
        var text = messageInput.text.trim()
        if ((!text && !root.hasDraftAttachments) || !chatService) return
        chatService.sendMessage(text)
        messageInput.text = ""
    }
}
