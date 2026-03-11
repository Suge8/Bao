import QtQuick 2.15

Item {
    id: root

    property string role: "assistant"
    property string content: ""
    property string format: "plain"
    property string status: "done"
    property int messageId: -1
    property int messageRow: -1
    property string entranceStyle: "none"
    property bool entrancePending: false
    property bool showDateDivider: false
    property string dateDividerText: ""
    property var toastFunc: null

    property bool isGreeting: entranceStyle === "greeting"
    property bool isUser: role === "user"
    property bool isSystem: role === "system" || isGreeting
    property bool isSystemError: role === "system" && status === "error"
    property bool isPending: status === "pending"
    property bool isMarkdown: format === "markdown"
    property bool isTypingBubble: status === "typing" && content === ""
    property bool isAssistantEntrance: !isSystem && entranceStyle === "assistantReceived"
    property bool isUserEntrance: !isSystem && entranceStyle === "userSent"
    property bool _entranceStarted: false
    readonly property bool shouldAnimateEntrance: entranceStyle !== "none" && entrancePending
    readonly property bool showGreetingDecoration: isGreeting && !isSystemError
    readonly property real greetingAuraFarPeak: motionAuraFarPeak * 0.45
    readonly property real greetingAuraNearPeak: motionAuraNearPeak * 0.5
    readonly property real feedbackProgressStart: -0.3
    readonly property real feedbackProgressEnd: 1.3
    readonly property real feedbackBandOuterOffset: 0.24
    readonly property real feedbackBandInnerOffset: 0.08
    readonly property int systemContentPaddingX: isGreeting ? 11 : 12
    readonly property int systemContentPaddingY: isGreeting ? 7 : 8
    readonly property int systemIconSlotWidth: isGreeting ? systemIconSize : 12
    readonly property int systemIconSize: isGreeting ? 22 : 10
    readonly property int systemIconGap: isGreeting ? 5 : 8
    readonly property int systemTextStartX: systemContentPaddingX + systemIconSlotWidth + systemIconGap
    readonly property bool useGreetingGradient: showGreetingDecoration && chatGreetingBubbleBgStart !== chatGreetingBubbleBgEnd
    readonly property string entranceMotionProfile: {
        if (isGreeting) return "greeting"
        if (isSystem) return "system"
        if (isUserEntrance) return "userSent"
        if (isAssistantEntrance) return "assistantReceived"
        if (isUser) return "user"
        return "assistant"
    }
    readonly property string contentMorphProfile: isTypingBubble ? "typing" : "content"
    readonly property string pendingSurfaceProfile: isPending ? "pending" : "settled"
    function alphaColor(color, alpha) {
        return Qt.rgba(color.r, color.g, color.b, Math.max(0.0, Math.min(1.0, alpha)))
    }
    function clamp01(value) {
        return Math.max(0.0, Math.min(1.0, value))
    }
    function resetFeedbackSheen(sheen) {
        sheen.opacity = 0.0
        sheen.progress = feedbackProgressStart
    }
    function resetFeedbackRipple(ripple) {
        ripple.opacity = 0.0
        ripple.scale = 0.92
    }
    // Keep motion decisions in one place so ChatView stays geometry-only.
    function entranceProfileData(profile) {
        switch (profile) {
        case "greeting":
            return {
                opacityDuration: motionUi + 40,
                moveDuration: motionUi + 44,
                settleDuration: motionPanel + 42,
                glowFadeDuration: motionAmbient,
                startScale: 0.962,
                peakScale: 1.016,
                startX: 0,
                settleX: 0,
                startY: 16,
                settleY: -1.4,
                glowPeak: motionAuraNearPeak * 0.44,
                glowStartScale: 0.95,
                glowPeakScale: 1.058
            }
        case "system":
            return {
                opacityDuration: motionUi + 24,
                moveDuration: motionUi + 20,
                settleDuration: motionPanel + 16,
                glowFadeDuration: motionPanel + 60,
                startScale: 0.932,
                peakScale: 1.014,
                startX: 0,
                settleX: 0,
                startY: -26,
                settleY: 1.2,
                glowPeak: motionAuraNearPeak * 0.43,
                glowStartScale: 0.95,
                glowPeakScale: 1.046
            }
        case "userSent":
            return {
                opacityDuration: motionFast + 40,
                moveDuration: motionFast + 50,
                settleDuration: motionUi + 44,
                glowFadeDuration: motionPanel + 20,
                startScale: 0.981,
                peakScale: 1.02,
                startX: motionEnterOffsetY * 2.65,
                settleX: -1.05,
                startY: motionEnterOffsetY * 0.58,
                settleY: -0.58,
                glowPeak: motionAuraNearPeak * 0.68,
                glowStartScale: 0.938,
                glowPeakScale: 1.045
            }
        case "assistantReceived":
            return {
                opacityDuration: motionUi + 22,
                moveDuration: motionUi + 18,
                settleDuration: motionUi + 52,
                glowFadeDuration: motionPanel + 20,
                startScale: 0.972,
                peakScale: 1.015,
                startX: -motionEnterOffsetY * 2.25,
                settleX: 0.82,
                startY: motionEnterOffsetY * 0.84,
                settleY: -0.78,
                glowPeak: motionAuraNearPeak * 0.55,
                glowStartScale: 0.95,
                glowPeakScale: 1.044
            }
        case "user":
            return {
                opacityDuration: motionFast + 28,
                moveDuration: motionFast + 32,
                settleDuration: motionUi + 36,
                glowFadeDuration: motionPanel + 20,
                startScale: 0.975,
                peakScale: 1.017,
                startX: motionEnterOffsetY * 1.95,
                settleX: -0.82,
                startY: motionEnterOffsetY * 0.4,
                settleY: -0.46,
                glowPeak: motionAuraNearPeak * 0.53,
                glowStartScale: 0.938,
                glowPeakScale: 1.044
            }
        default:
            return {
                opacityDuration: motionUi + 6,
                moveDuration: motionUi + 14,
                settleDuration: motionUi + 42,
                glowFadeDuration: motionPanel + 20,
                startScale: 0.971,
                peakScale: 1.014,
                startX: -motionEnterOffsetY * 1.65,
                settleX: 0.62,
                startY: motionEnterOffsetY * 0.68,
                settleY: -0.56,
                glowPeak: motionAuraNearPeak * 0.44,
                glowStartScale: 0.95,
                glowPeakScale: 1.043
            }
        }
    }
    function contentMorphProfileData(profile) {
        switch (profile) {
        case "typing":
            return {
                showsTypingIndicator: true,
                showsContentBody: false,
                contentOffsetY: 5,
                contentScale: 0.992,
                typingOffsetY: 0,
                typingScale: 1.0,
                contentDuration: motionUi + 20,
                typingDuration: motionUi
            }
        default:
            return {
                showsTypingIndicator: false,
                showsContentBody: root.content !== "",
                contentOffsetY: 0,
                contentScale: 1.0,
                typingOffsetY: -4,
                typingScale: 0.92,
                contentDuration: motionUi + 20,
                typingDuration: motionUi
            }
        }
    }
    function pendingSurfaceProfileData(profile) {
        switch (profile) {
        case "pending":
            return {
                opacity: root.isUser ? 1.0 : 0.84,
                scale: 1.016,
                color: root.isUser ? "#12FFFFFF" : root.alphaColor(accent, 0.08),
                duration: motionUi + 60
            }
        default:
            return {
                opacity: 0.0,
                scale: 1.0,
                color: root.isUser ? "#12FFFFFF" : root.alphaColor(accent, 0.08),
                duration: motionUi + 60
            }
        }
    }
    readonly property var entranceMotion: entranceProfileData(entranceMotionProfile)
    readonly property var contentMorphMotion: contentMorphProfileData(contentMorphProfile)
    readonly property var pendingSurfaceMotion: pendingSurfaceProfileData(pendingSurfaceProfile)
    readonly property color systemIconColor: {
        if (isSystemError) return statusError
        if (isGreeting) return chatGreetingAccent
        return systemAccentColor
    }
    readonly property int entranceOpacityDuration: entranceMotion.opacityDuration
    readonly property int entranceMoveDuration: entranceMotion.moveDuration
    readonly property int entranceSettleDuration: entranceMotion.settleDuration
    readonly property int entranceGlowFadeDuration: entranceMotion.glowFadeDuration
    readonly property real entranceStartScale: entranceMotion.startScale
    readonly property real entrancePeakScale: entranceMotion.peakScale
    readonly property real entranceStartX: entranceMotion.startX
    readonly property real entranceSettleX: entranceMotion.settleX
    readonly property real entranceStartY: entranceMotion.startY
    readonly property real entranceSettleY: entranceMotion.settleY
    readonly property color systemAuraFarColor: {
        if (isSystemError) return chatSystemAuraErrorFar
        if (isGreeting) return chatGreetingAuraFar
        return chatSystemAuraFar
    }
    readonly property color systemAuraNearColor: {
        if (isSystemError) return chatSystemAuraErrorNear
        if (isGreeting) return chatGreetingAuraNear
        return chatSystemAuraNear
    }
    readonly property color systemBubbleFillColor: {
        if (isSystemError) return chatSystemBubbleErrorBg
        if (isGreeting) return chatGreetingBubbleBgStart
        return chatSystemBubbleBg
    }
    readonly property color systemBubbleBorderColor: {
        if (isSystemError) return chatSystemBubbleErrorBorder
        if (isGreeting) return chatGreetingBubbleBorder
        return chatSystemBubbleBorder
    }
    readonly property color systemOverlayColor: {
        if (isSystemError) return chatSystemBubbleErrorOverlay
        if (isGreeting) return chatGreetingBubbleOverlay
        return chatSystemBubbleOverlay
    }
    readonly property color systemAccentColor: {
        if (isSystemError) return statusError
        if (isGreeting) return chatGreetingAccent
        return accent
    }
    readonly property color systemTextColor: {
        if (isSystemError) return statusError
        if (isGreeting) return chatGreetingText
        return chatSystemText
    }
    readonly property int bubblePaddingX: 16
    readonly property int bubblePaddingTop: 12
    readonly property int bubblePaddingBottom: 16
    readonly property int dividerBlockHeight: showDateDivider && dateDividerText !== "" ? 28 : 0
    readonly property color dividerLineColor: alphaColor(textSecondary, isSystem ? 0.18 : 0.14)
    readonly property real bubbleEntranceGlowPeak: entranceMotion.glowPeak
    readonly property color bubbleEntranceGlowColor: isUserEntrance
                                                    ? root.alphaColor(accent, 0.34)
                                                    : root.alphaColor(accentGlow, 0.52)
    readonly property real bubbleEntranceGlowStartScale: entranceMotion.glowStartScale
    readonly property real bubbleEntranceGlowPeakScale: entranceMotion.glowPeakScale
    readonly property bool showsTypingIndicator: contentMorphMotion.showsTypingIndicator
    readonly property bool showsContentBody: contentMorphMotion.showsContentBody
    readonly property real contentMorphOffsetY: contentMorphMotion.contentOffsetY
    readonly property real contentMorphScale: contentMorphMotion.contentScale
    readonly property real typingMorphOffsetY: contentMorphMotion.typingOffsetY
    readonly property real typingMorphScale: contentMorphMotion.typingScale
    readonly property int contentMorphDuration: contentMorphMotion.contentDuration
    readonly property int typingMorphDuration: contentMorphMotion.typingDuration
    readonly property bool canCopyFeedback: root.content !== ""
    readonly property color copyFeedbackOverlayColor: {
        if (isSystemError) return chatSystemBubbleErrorOverlay
        if (isGreeting) return chatGreetingBubbleHighlight
        if (isSystem) return chatSystemBubbleOverlay
        if (isUser) return chatBubbleCopyFlashUser
        return accentGlow
    }
    readonly property color copyFeedbackSheenColor: {
        if (isSystemError) return "#12FFFFFF"
        if (isGreeting) return chatGreetingBubbleHighlight
        if (isSystem) return "#18FFFFFF"
        if (isUser) return "#24FFFFFF"
        return "#1CFFFFFF"
    }
    readonly property real copyFeedbackOverlayPeak: {
        if (isGreeting) return motionCopyFlashPeak * 0.82
        if (isSystem) return motionCopyFlashPeak * 0.64
        if (isUser) return motionCopyFlashPeak * 0.9
        return motionCopyFlashPeak * 0.72
    }
    readonly property real copyFeedbackSheenPeak: {
        if (isGreeting) return motionGreetingSweepPeak * 0.82
        if (isSystem) return motionGreetingSweepPeak * 0.94
        if (isUser) return motionGreetingSweepPeak * 0.68
        return motionGreetingSweepPeak * 0.54
    }

    height: dividerBlockHeight + (isSystem ? systemBubble.height + 7 : bubble.height + 5)
    width: parent ? parent.width : 600

    function playEntrance() {
        if (_entranceStarted || !shouldAnimateEntrance) return
        entranceStartTimer.restart()
    }

    function consumeEntrance() {
        var view = ListView.view
        if (!view || !view.model) return
        if (messageId >= 0 && view.model.consumeEntranceById) {
            view.model.consumeEntranceById(messageId)
            return
        }
        if (messageRow >= 0 && view.model.consumeEntrance) {
            view.model.consumeEntrance(messageRow)
        }
    }

    function copyToClipboard(text) {
        if (!text) return
        clipHelper.text = text
        clipHelper.selectAll()
        clipHelper.copy()
        clipHelper.deselect()
        if (root.toastFunc) root.toastFunc()
    }

    function resetCopyFeedback() {
        copyFlash.opacity = 0.0
        resetFeedbackRipple(copyRipple)
        resetFeedbackSheen(copySheen)
        systemCopyFlash.opacity = 0.0
        resetFeedbackRipple(systemCopyRipple)
        resetFeedbackSheen(systemCopySheen)
    }

    function playCopyFeedback() {
        if (!canCopyFeedback) return
        resetCopyFeedback()
        copyFeedbackAnim.restart()
    }

    function copyCurrentMessage() {
        if (!canCopyFeedback) return
        copyToClipboard(root.content)
        playCopyFeedback()
    }

    Component.onCompleted: playEntrance()
    onShouldAnimateEntranceChanged: {
        if (shouldAnimateEntrance) playEntrance()
    }

    Timer {
        id: entranceStartTimer
        interval: 0
        repeat: false
        onTriggered: {
            if (root._entranceStarted || !root.shouldAnimateEntrance) return
            root._entranceStarted = true
            // Mark consumed at animation start so rebuilt delegates do not replay the same entrance.
            root.consumeEntrance()
            if (root.isSystem) {
                systemAuraNear.opacity = 0.0
                systemAuraFar.opacity = 0.0
                resetFeedbackSheen(greetingSweep)
                systemShift.y = root.entranceStartY
                systemBubble.scale = root.entranceStartScale
                systemEntranceAnim.restart()
            } else {
                enterTranslate.x = root.entranceStartX
                enterTranslate.y = root.entranceStartY
                bubble.scale = root.entranceStartScale
                bubbleEntranceGlow.scale = root.bubbleEntranceGlowStartScale
                entranceAnim.restart()
            }
        }
    }

    Item {
        id: dateDivider
        objectName: "dateDivider"
        visible: root.showDateDivider && root.dateDividerText !== ""
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: root.dividerBlockHeight
        opacity: visible ? 1.0 : 0.0

        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

        Rectangle {
            anchors.left: parent.left
            anchors.leftMargin: root.isSystem ? 24 : 34
            anchors.right: dividerLabel.left
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            height: 1
            radius: 1
            color: root.dividerLineColor
            opacity: 0.9
        }

        Text {
            id: dividerLabel
            objectName: "dateDividerText"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            text: root.dateDividerText
            color: textSecondary
            font.pixelSize: typeMeta
            font.weight: weightMedium
            font.letterSpacing: 0.3
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            opacity: 0.84
        }

        Rectangle {
            anchors.left: dividerLabel.right
            anchors.leftMargin: 12
            anchors.right: parent.right
            anchors.rightMargin: root.isSystem ? 24 : 34
            anchors.verticalCenter: parent.verticalCenter
            height: 1
            radius: 1
            color: root.dividerLineColor
            opacity: 0.9
        }
    }

    Rectangle {
        id: systemAuraFar
        visible: isSystemError
        anchors.fill: systemBubble
        anchors.leftMargin: -12
        anchors.rightMargin: -12
        anchors.topMargin: -12
        anchors.bottomMargin: -12
        radius: systemBubble.radius + (isGreeting ? 10 : 12)
        color: systemAuraFarColor
        opacity: 0.0
    }

    Rectangle {
        id: systemAuraNear
        objectName: "systemAuraNear"
        visible: isSystem
        anchors.fill: systemBubble
        radius: systemBubble.radius
        color: systemAuraNearColor
        opacity: 0.0
    }

    Rectangle {
        id: systemBubble
        objectName: "systemBubble"
        visible: isSystem
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: root.dividerBlockHeight + (isGreeting ? 8 : 7)
        width: isGreeting
               ? Math.max(228, Math.min(root.width * 0.64, systemText.implicitWidth + root.systemTextStartX + root.systemContentPaddingX + 2))
               : Math.max(98, Math.min(root.width * 0.9, systemText.implicitWidth + root.systemTextStartX + root.systemContentPaddingX))
        height: Math.max(systemText.contentHeight, root.systemIconSize) + (root.systemContentPaddingY * 2)
        radius: isGreeting ? height / 2 : sizeSystemBubbleRadius
        color: systemBubbleFillColor
        border.width: 1
        border.color: systemBubbleBorderColor
        clip: true
        opacity: shouldAnimateEntrance && !_entranceStarted ? 0.0 : 1.0
        scale: shouldAnimateEntrance && !_entranceStarted ? entranceStartScale : 1.0
        transformOrigin: Item.Center
        transform: Translate { id: systemShift; y: 0 }

        Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
        Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: systemOverlayColor
        }

        Rectangle {
            objectName: "greetingGradient"
            anchors.fill: parent
            radius: parent.radius
            visible: root.useGreetingGradient
            gradient: Gradient {
                GradientStop { position: 0.0; color: chatGreetingBubbleBgStart }
                GradientStop { position: 1.0; color: chatGreetingBubbleBgEnd }
            }
            opacity: 0.92
        }

        Rectangle {
            id: systemCopyFlash
            objectName: "systemCopyFlash"
            anchors.fill: parent
            radius: parent.radius
            color: copyFeedbackOverlayColor
            opacity: 0.0
        }

        Rectangle {
            id: systemCopyRipple
            objectName: "systemCopyRipple"
            anchors.fill: parent
            anchors.margins: 2
            radius: Math.max(1, parent.radius - 2)
            color: "transparent"
            border.width: 1
            border.color: root.alphaColor(copyFeedbackSheenColor, 0.52)
            opacity: 0.0
            scale: 0.92
            transformOrigin: Item.Center
        }

        Item {
            id: systemIconSlot
            width: root.systemIconSlotWidth
            height: root.systemIconSize
            anchors.left: parent.left
            anchors.leftMargin: root.systemContentPaddingX
            anchors.verticalCenter: parent.verticalCenter
            Item {
                anchors.centerIn: parent
                width: root.systemIconSize
                height: root.systemIconSize

                Image {
                    id: greetingIcon
                    objectName: "greetingIcon"
                    visible: isGreeting
                    anchors.centerIn: parent
                    width: root.systemIconSize
                    height: root.systemIconSize
                    source: chatGreetingIconSource
                    sourceSize: Qt.size(root.systemIconSize, root.systemIconSize)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    opacity: 1.0
                }

                Rectangle {
                    visible: !isGreeting
                    anchors.top: parent.top
                    anchors.left: parent.left
                    width: parent.width
                    height: 2
                    radius: 1
                    color: root.systemIconColor
                }

                Rectangle {
                    visible: !isGreeting
                    anchors.top: parent.top
                    anchors.topMargin: 4
                    anchors.left: parent.left
                    width: Math.max(4, parent.width - 3)
                    height: 2
                    radius: 1
                    color: root.systemIconColor
                    opacity: 0.9
                }

                Rectangle {
                    visible: !isGreeting
                    anchors.top: parent.top
                    anchors.topMargin: 8
                    anchors.left: parent.left
                    width: Math.max(6, parent.width - 1)
                    height: 2
                    radius: 1
                    color: root.systemIconColor
                    opacity: 0.78
                }
            }
        }

        Rectangle {
            id: greetingSweep
            objectName: "greetingSweep"
            visible: root.useGreetingGradient
            property real progress: -0.3
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            gradient: Gradient {
                GradientStop { position: 0.0; color: root.alphaColor(chatGreetingSweep, 0.0) }
                GradientStop { position: root.clamp01(greetingSweep.progress - root.feedbackBandOuterOffset); color: root.alphaColor(chatGreetingSweep, 0.0) }
                GradientStop { position: root.clamp01(greetingSweep.progress - root.feedbackBandInnerOffset); color: root.alphaColor(chatGreetingSweep, 0.08) }
                GradientStop { position: root.clamp01(greetingSweep.progress); color: root.alphaColor(chatGreetingSweep, 0.28) }
                GradientStop { position: root.clamp01(greetingSweep.progress + root.feedbackBandInnerOffset); color: root.alphaColor(chatGreetingSweep, 0.1) }
                GradientStop { position: root.clamp01(greetingSweep.progress + root.feedbackBandOuterOffset); color: root.alphaColor(chatGreetingSweep, 0.0) }
                GradientStop { position: 1.0; color: root.alphaColor(chatGreetingSweep, 0.0) }
            }
            opacity: 0.0
        }

        Rectangle {
            id: systemCopySheen
            objectName: "systemCopySheen"
            visible: root.canCopyFeedback
            property real progress: -0.3
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            gradient: Gradient {
                GradientStop { position: 0.0; color: root.alphaColor(copyFeedbackSheenColor, 0.0) }
                GradientStop { position: root.clamp01(systemCopySheen.progress - root.feedbackBandOuterOffset); color: root.alphaColor(copyFeedbackSheenColor, 0.0) }
                GradientStop { position: root.clamp01(systemCopySheen.progress - root.feedbackBandInnerOffset); color: root.alphaColor(copyFeedbackSheenColor, 0.1) }
                GradientStop { position: root.clamp01(systemCopySheen.progress); color: root.alphaColor(copyFeedbackSheenColor, 0.32) }
                GradientStop { position: root.clamp01(systemCopySheen.progress + root.feedbackBandInnerOffset); color: root.alphaColor(copyFeedbackSheenColor, 0.12) }
                GradientStop { position: root.clamp01(systemCopySheen.progress + root.feedbackBandOuterOffset); color: root.alphaColor(copyFeedbackSheenColor, 0.0) }
                GradientStop { position: 1.0; color: root.alphaColor(copyFeedbackSheenColor, 0.0) }
            }
            opacity: 0.0
        }

        Text {
            id: systemText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: root.systemTextStartX
            anchors.rightMargin: root.systemContentPaddingX
            anchors.verticalCenter: parent.verticalCenter
            text: root.content
            color: systemTextColor
            font.pixelSize: isGreeting ? Math.max(typeMeta + 2, typeBody - 1) : typeMeta
            font.weight: isGreeting ? Font.DemiBold : weightMedium
            font.letterSpacing: isGreeting ? 0.1 : letterTight
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignLeft
            verticalAlignment: Text.AlignVCenter
            lineHeight: isGreeting ? 1.2 : 1.35
            textFormat: Text.PlainText
        }

        MouseArea {
            id: systemClickArea
            anchors.fill: parent
            z: 10
            hoverEnabled: true
            preventStealing: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.copyCurrentMessage()
        }
    }

    ParallelAnimation {
        id: systemEntranceAnim
        NumberAnimation { target: systemBubble; property: "opacity"; from: 0.0; to: 1.0; duration: entranceOpacityDuration; easing.type: easeStandard }
        SequentialAnimation {
            NumberAnimation { target: systemBubble; property: "scale"; from: entranceStartScale; to: entrancePeakScale; duration: entranceMoveDuration; easing.type: easeEmphasis }
            NumberAnimation { target: systemBubble; property: "scale"; to: 1.0; duration: entranceSettleDuration; easing.type: easeSoft }
        }
        SequentialAnimation {
            NumberAnimation { target: systemShift; property: "y"; from: entranceStartY; to: entranceSettleY; duration: entranceMoveDuration; easing.type: easeEmphasis }
            NumberAnimation { target: systemShift; property: "y"; to: 0; duration: entranceSettleDuration; easing.type: easeSoft }
        }
        SequentialAnimation {
            NumberAnimation {
                target: systemAuraNear
                property: "opacity"
                from: 0.0
                to: isGreeting ? greetingAuraNearPeak * 0.72 : (isSystemError ? motionAuraNearPeak * 0.78 : motionAuraNearPeak * 0.46)
                duration: motionUi
                easing.type: easeStandard
            }
            NumberAnimation { target: systemAuraNear; property: "opacity"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
        }
        SequentialAnimation {
            NumberAnimation {
                target: systemAuraFar
                property: "opacity"
                from: 0.0
                to: isGreeting ? greetingAuraFarPeak * 0.92 : motionAuraFarPeak * 0.8
                duration: motionUi
                easing.type: easeStandard
            }
            NumberAnimation { target: systemAuraFar; property: "opacity"; to: 0.0; duration: motionAmbient + 120; easing.type: easeSoft }
        }
        SequentialAnimation {
            NumberAnimation { target: greetingSweep; property: "opacity"; from: 0.0; to: motionGreetingSweepPeak * 0.78; duration: motionUi; easing.type: easeStandard }
            PauseAnimation { duration: motionFast }
            NumberAnimation { target: greetingSweep; property: "opacity"; to: 0.0; duration: motionPanel; easing.type: easeSoft }
        }
        NumberAnimation {
            target: greetingSweep
            property: "progress"
            from: root.feedbackProgressStart
            to: root.feedbackProgressEnd
            duration: motionAmbient + 200
            easing.type: easeSoft
        }
    }

    ParallelAnimation {
        id: copyFeedbackAnim

        SequentialAnimation {
            NumberAnimation { target: copyFlash; property: "opacity"; from: 0.0; to: copyFeedbackOverlayPeak; duration: motionMicro; easing.type: easeStandard }
            NumberAnimation { target: copyFlash; property: "opacity"; to: 0.0; duration: motionUi; easing.type: easeSoft }
        }
        SequentialAnimation {
            NumberAnimation { target: copyRipple; property: "opacity"; from: 0.0; to: 0.24; duration: motionFast; easing.type: easeStandard }
            NumberAnimation { target: copyRipple; property: "opacity"; to: 0.0; duration: motionPanel; easing.type: easeSoft }
        }
        NumberAnimation {
            target: copyRipple
            property: "scale"
            from: 0.92
            to: 1.02
            duration: motionPanel
            easing.type: easeEmphasis
        }
        SequentialAnimation {
            NumberAnimation { target: systemCopyFlash; property: "opacity"; from: 0.0; to: copyFeedbackOverlayPeak; duration: motionMicro; easing.type: easeStandard }
            NumberAnimation { target: systemCopyFlash; property: "opacity"; to: 0.0; duration: motionUi; easing.type: easeSoft }
        }
        SequentialAnimation {
            NumberAnimation { target: systemCopyRipple; property: "opacity"; from: 0.0; to: 0.24; duration: motionFast; easing.type: easeStandard }
            NumberAnimation { target: systemCopyRipple; property: "opacity"; to: 0.0; duration: motionPanel; easing.type: easeSoft }
        }
        NumberAnimation {
            target: systemCopyRipple
            property: "scale"
            from: 0.92
            to: 1.02
            duration: motionPanel
            easing.type: easeEmphasis
        }

        SequentialAnimation {
            NumberAnimation { target: copySheen; property: "opacity"; from: 0.0; to: copyFeedbackSheenPeak; duration: motionFast; easing.type: easeStandard }
            PauseAnimation { duration: motionMicro }
            NumberAnimation { target: copySheen; property: "opacity"; to: 0.0; duration: motionPanel; easing.type: easeSoft }
        }
        NumberAnimation {
            target: copySheen
            property: "progress"
            from: root.feedbackProgressStart
            to: root.feedbackProgressEnd
            duration: motionAmbient + 100
            easing.type: easeSoft
        }
        SequentialAnimation {
            NumberAnimation { target: systemCopySheen; property: "opacity"; from: 0.0; to: copyFeedbackSheenPeak; duration: motionFast; easing.type: easeStandard }
            PauseAnimation { duration: motionMicro }
            NumberAnimation { target: systemCopySheen; property: "opacity"; to: 0.0; duration: motionPanel; easing.type: easeSoft }
        }
        NumberAnimation {
            target: systemCopySheen
            property: "progress"
            from: root.feedbackProgressStart
            to: root.feedbackProgressEnd
            duration: motionAmbient + 100
            easing.type: easeSoft
        }
    }

    TextEdit { id: clipHelper; visible: false }

    Text {
        id: contentMetrics
        text: root.content
        font.pixelSize: typeBody
        textFormat: Text.PlainText
        visible: false
    }

    Rectangle {
        id: bubbleEntranceGlow
        objectName: "bubbleEntranceGlow"
        visible: !isSystem
        anchors.fill: bubble
        anchors.margins: -6
        radius: bubble.radius + 6
        color: bubbleEntranceGlowColor
        opacity: 0.0
        scale: 0.96
        z: -1
    }

    Rectangle {
        id: bubble
        objectName: "bubbleBody"
        visible: !isSystem
        anchors {
            right: isUser ? parent.right : undefined
            left: isUser ? undefined : parent.left
            rightMargin: isUser ? 20 : 0
            leftMargin: isUser ? 0 : 20
            top: parent.top
            topMargin: root.dividerBlockHeight + 5
        }
        property bool isTyping: root.isTypingBubble
        width: isTyping ? 72 : Math.min(contentMetrics.implicitWidth + (bubblePaddingX * 2), root.width * 0.75)
        height: isTyping ? 42 : contentText.contentHeight + bubblePaddingTop + bubblePaddingBottom
        radius: sizeBubbleRadius
        clip: true
        opacity: shouldAnimateEntrance && !_entranceStarted ? 0.0 : 1.0
        scale: shouldAnimateEntrance && !_entranceStarted ? entranceStartScale : 1.0
        transformOrigin: Item.Center
        transform: Translate {
            id: enterTranslate
            objectName: "bubbleEntranceShift"
            x: 0
            y: 0
        }

        color: isUser ? (clickArea.containsMouse ? accentHover : accent) : (clickArea.containsMouse ? bgCardHover : bgCard)
        border.color: isUser ? "transparent" : borderSubtle
        border.width: isUser ? 0 : 1
        Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

        MouseArea {
            id: clickArea
            anchors.fill: parent
            z: 10
            hoverEnabled: true
            preventStealing: true
            cursorShape: Qt.PointingHandCursor
            onClicked: function(mouse) {
                if (bubble.isTyping || root.content === "") return
                if (root.isMarkdown) {
                    var localPt = clickArea.mapToItem(contentText, mouse.x, mouse.y)
                    var link = contentText.linkAt(localPt.x, localPt.y)
                    if (link) {
                        Qt.openUrlExternally(link)
                        return
                    }
                }
                root.copyCurrentMessage()
            }
        }

        Rectangle { id: copyFlash; objectName: "copyFlash"; anchors.fill: parent; radius: parent.radius; z: 1; color: copyFeedbackOverlayColor; opacity: 0.0 }
        Rectangle {
            id: copyRipple
            objectName: "copyRipple"
            anchors.fill: parent
            anchors.margins: 2
            radius: Math.max(1, parent.radius - 2)
            color: "transparent"
            border.width: 1
            border.color: root.alphaColor(copyFeedbackSheenColor, 0.52)
            opacity: 0.0
            scale: 0.92
            transformOrigin: Item.Center
        }
        Rectangle {
            id: copySheen
            objectName: "copySheen"
            visible: root.canCopyFeedback
            property real progress: -0.3
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            gradient: Gradient {
                GradientStop { position: 0.0; color: root.alphaColor(copyFeedbackSheenColor, 0.0) }
                GradientStop { position: root.clamp01(copySheen.progress - root.feedbackBandOuterOffset); color: root.alphaColor(copyFeedbackSheenColor, 0.0) }
                GradientStop { position: root.clamp01(copySheen.progress - root.feedbackBandInnerOffset); color: root.alphaColor(copyFeedbackSheenColor, 0.1) }
                GradientStop { position: root.clamp01(copySheen.progress); color: root.alphaColor(copyFeedbackSheenColor, 0.32) }
                GradientStop { position: root.clamp01(copySheen.progress + root.feedbackBandInnerOffset); color: root.alphaColor(copyFeedbackSheenColor, 0.12) }
                GradientStop { position: root.clamp01(copySheen.progress + root.feedbackBandOuterOffset); color: root.alphaColor(copyFeedbackSheenColor, 0.0) }
                GradientStop { position: 1.0; color: root.alphaColor(copyFeedbackSheenColor, 0.0) }
            }
            opacity: 0.0
        }

        ParallelAnimation {
            id: entranceAnim
            NumberAnimation { target: bubble; property: "opacity"; from: 0.0; to: 1.0; duration: entranceOpacityDuration; easing.type: easeStandard }
            SequentialAnimation {
                NumberAnimation { target: bubble; property: "scale"; from: entranceStartScale; to: entrancePeakScale; duration: entranceMoveDuration; easing.type: easeEmphasis }
                NumberAnimation { target: bubble; property: "scale"; to: 1.0; duration: entranceSettleDuration; easing.type: easeSoft }
            }
            SequentialAnimation {
                NumberAnimation { target: enterTranslate; property: "x"; from: entranceStartX; to: entranceSettleX; duration: entranceMoveDuration; easing.type: easeEmphasis }
                NumberAnimation { target: enterTranslate; property: "x"; to: 0; duration: entranceSettleDuration; easing.type: easeSoft }
            }
            SequentialAnimation {
                NumberAnimation { target: enterTranslate; property: "y"; from: entranceStartY; to: entranceSettleY; duration: entranceMoveDuration; easing.type: easeEmphasis }
                NumberAnimation { target: enterTranslate; property: "y"; to: 0; duration: entranceSettleDuration; easing.type: easeSoft }
            }
            SequentialAnimation {
                NumberAnimation {
                    target: bubbleEntranceGlow
                    property: "opacity"
                    from: 0.0
                    to: bubbleEntranceGlowPeak
                    duration: motionUi
                    easing.type: easeStandard
                }
                NumberAnimation {
                    target: bubbleEntranceGlow
                    property: "opacity"
                    to: 0.0
                    duration: entranceGlowFadeDuration
                    easing.type: easeSoft
                }
            }
            SequentialAnimation {
                NumberAnimation {
                    target: bubbleEntranceGlow
                    property: "scale"
                    from: bubbleEntranceGlowStartScale
                    to: bubbleEntranceGlowPeakScale
                    duration: entranceMoveDuration
                    easing.type: easeEmphasis
                }
                NumberAnimation {
                    target: bubbleEntranceGlow
                    property: "scale"
                    to: 1.0
                    duration: entranceSettleDuration
                    easing.type: easeSoft
                }
            }
        }

        Text {
            id: contentText
            objectName: "contentText"
            anchors {
                top: parent.top
                bottom: parent.bottom
                left: parent.left
                right: parent.right
                topMargin: bubblePaddingTop
                bottomMargin: bubblePaddingBottom
                leftMargin: bubblePaddingX
                rightMargin: bubblePaddingX
            }
            text: root.content
            visible: root.showsContentBody || opacity > 0.01
            color: root.isUser ? "#FFFFFF" : textPrimary
            font.pixelSize: typeBody
            wrapMode: Text.Wrap
            textFormat: root.isMarkdown ? Text.MarkdownText : Text.PlainText
            lineHeight: lineHeightBody
            verticalAlignment: Text.AlignVCenter
            opacity: root.showsContentBody ? 1.0 : 0.0
            y: root.contentMorphOffsetY
            scale: root.contentMorphScale
            transformOrigin: Item.Center
            Behavior on opacity { NumberAnimation { duration: root.contentMorphDuration; easing.type: easeStandard } }
            Behavior on y { NumberAnimation { duration: root.contentMorphDuration; easing.type: easeSoft } }
            Behavior on scale { NumberAnimation { duration: root.contentMorphDuration; easing.type: easeSoft } }
        }

        Item {
            id: typingIndicator
            objectName: "typingIndicator"
            anchors.centerIn: parent
            visible: root.showsTypingIndicator || opacity > 0.01
            width: 32
            height: 10
            opacity: root.showsTypingIndicator ? 1.0 : 0.0
            y: root.typingMorphOffsetY
            scale: root.typingMorphScale
            transformOrigin: Item.Center
            Behavior on opacity { NumberAnimation { duration: root.typingMorphDuration; easing.type: easeStandard } }
            Behavior on y { NumberAnimation { duration: root.typingMorphDuration; easing.type: easeSoft } }
            Behavior on scale { NumberAnimation { duration: root.typingMorphDuration; easing.type: easeSoft } }

            Row {
                anchors.centerIn: parent
                spacing: 5

                Repeater {
                    model: 3

                    Rectangle {
                        width: 6
                        height: 6
                        radius: 3
                        color: root.isUser ? "#FFFFFF" : textSecondary
                        opacity: motionTypingPulseMinOpacity

                        SequentialAnimation on opacity {
                            running: root.showsTypingIndicator
                            loops: Animation.Infinite
                            PauseAnimation { duration: index * 120 }
                            NumberAnimation { to: 1.0; duration: motionUi; easing.type: easeStandard }
                            NumberAnimation { to: motionTypingPulseMinOpacity; duration: motionUi; easing.type: easeStandard }
                            PauseAnimation { duration: motionUi }
                        }
                    }
                }
            }
        }

        Rectangle {
            id: pendingOverlay
            objectName: "pendingOverlay"
            anchors.fill: parent
            radius: parent.radius
            color: root.pendingSurfaceMotion.color
            visible: root.isPending || opacity > 0.01
            opacity: root.pendingSurfaceMotion.opacity
            scale: root.pendingSurfaceMotion.scale
            transformOrigin: Item.Center
            Behavior on opacity { NumberAnimation { duration: root.pendingSurfaceMotion.duration; easing.type: easeSoft } }
            Behavior on scale { NumberAnimation { duration: root.pendingSurfaceMotion.duration; easing.type: easeSoft } }
        }
        Rectangle { anchors.fill: parent; radius: parent.radius; color: chatBubbleErrorTint; visible: root.status === "error" }
    }
}
