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
    property bool entranceConsumed: true
    property var toastFunc: null

    property bool isUser: role === "user"
    property bool isSystem: role === "system"
    property bool isMarkdown: format === "markdown"
    property bool _entranceStarted: false
    property bool _entranceQueued: false
    readonly property bool shouldAnimateEntrance: entranceStyle !== "none" && entrancePending && !entranceConsumed
    readonly property int entranceOpacityDuration: entranceStyle === "greeting" ? motionUi : (isSystem ? motionPanel : (isUser ? motionFast : motionUi))
    readonly property int entranceScaleDuration: entranceStyle === "greeting" ? (motionPanel + 20) : (isSystem ? (motionPanel + 40) : (isUser ? motionUi : (motionUi + 20)))
    readonly property real entranceStartScale: entranceStyle === "greeting" ? 0.955 : (isSystem ? 0.9 : (isUser ? 0.968 : 0.964))
    readonly property real entranceStartY: isSystem ? -18 : 0

    height: isSystem ? systemBubble.height + 7 : bubble.height + 5
    width: parent ? parent.width : 600

    function playEntrance() {
        if (_entranceStarted || _entranceQueued || !shouldAnimateEntrance) return
        _entranceQueued = true
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

    Component.onCompleted: playEntrance()
    onShouldAnimateEntranceChanged: {
        if (shouldAnimateEntrance) playEntrance()
    }

    Timer {
        id: entranceStartTimer
        interval: 0
        repeat: false
        onTriggered: {
            root._entranceQueued = false
            if (root._entranceStarted || !root.shouldAnimateEntrance) return
            root._entranceStarted = true
            // Mark consumed at animation start to avoid replay flicker after delegate recycling.
            root.consumeEntrance()
            if (root.isSystem) {
                systemAuraNear.opacity = 0.0
                systemAuraFar.opacity = 0.0
                systemShift.y = root.entranceStartY
                systemEntranceAnim.restart()
            } else {
                entranceAnim.restart()
            }
        }
    }

    Rectangle {
        id: systemAuraFar
        visible: isSystem
        anchors.fill: systemBubble
        anchors.leftMargin: -12
        anchors.rightMargin: -12
        anchors.topMargin: -12
        anchors.bottomMargin: 0
        radius: systemBubble.radius + 12
        color: root.status === "error" ? chatSystemAuraErrorFar : chatSystemAuraFar
        opacity: 0.0
    }

    Rectangle {
        id: systemAuraNear
        visible: isSystem
        anchors.fill: systemBubble
        anchors.leftMargin: -6
        anchors.rightMargin: -6
        anchors.topMargin: -6
        anchors.bottomMargin: 0
        radius: systemBubble.radius + 6
        color: root.status === "error" ? chatSystemAuraErrorNear : chatSystemAuraNear
        opacity: 0.0
    }

    Rectangle {
        id: systemBubble
        visible: isSystem
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 7
        width: Math.max(60, Math.min(root.width * 0.9, systemText.implicitWidth + 34))
        height: systemText.contentHeight + spacingMd + 2
        radius: sizeSystemBubbleRadius
        color: root.status === "error" ? chatSystemBubbleErrorBg : chatSystemBubbleBg
        border.width: 1
        border.color: root.status === "error" ? chatSystemBubbleErrorBorder : borderSubtle
        opacity: shouldAnimateEntrance && !_entranceStarted ? 0.0 : 1.0
        scale: shouldAnimateEntrance && !_entranceStarted ? entranceStartScale : 1.0
        transformOrigin: Item.Center
        transform: Translate { id: systemShift; y: 0 }

        Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
        Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: root.status === "error" ? chatSystemBubbleErrorOverlay : chatSystemBubbleOverlay
        }

        Rectangle {
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            width: 3
            height: Math.max(16, parent.height - 12)
            radius: 2
            color: root.status === "error" ? statusError : accent
            opacity: 0.82
        }

        Text {
            id: systemText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 17
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            text: root.content
            color: root.status === "error" ? statusError : textSecondary
            font.pixelSize: typeMeta
            font.weight: weightMedium
            font.letterSpacing: letterTight
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            lineHeight: 1.35
            textFormat: Text.PlainText
        }

        HoverHandler { cursorShape: Qt.PointingHandCursor }
        MouseArea {
            anchors.fill: parent
            z: 10
            preventStealing: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.copyToClipboard(root.content)
        }
    }

    ParallelAnimation {
        id: systemEntranceAnim
        NumberAnimation { target: systemBubble; property: "opacity"; from: 0.0; to: 1.0; duration: entranceOpacityDuration; easing.type: easeStandard }
        NumberAnimation { target: systemBubble; property: "scale"; from: entranceStartScale; to: 1.0; duration: entranceScaleDuration; easing.type: easeEmphasis }
        NumberAnimation { target: systemShift; property: "y"; from: entranceStartY; to: 0; duration: entranceScaleDuration; easing.type: easeEmphasis }
        SequentialAnimation {
            NumberAnimation { target: systemAuraNear; property: "opacity"; from: 0.0; to: motionAuraNearPeak; duration: motionFast; easing.type: easeStandard }
            NumberAnimation { target: systemAuraNear; property: "opacity"; to: 0.0; duration: motionAmbient; easing.type: easeStandard }
        }
        SequentialAnimation {
            NumberAnimation { target: systemAuraFar; property: "opacity"; from: 0.0; to: motionAuraFarPeak; duration: motionUi; easing.type: easeStandard }
            NumberAnimation { target: systemAuraFar; property: "opacity"; to: 0.0; duration: motionAmbient + 120; easing.type: easeStandard }
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
        id: bubble
        visible: !isSystem
        anchors {
            right: isUser ? parent.right : undefined
            left: isUser ? undefined : parent.left
            rightMargin: isUser ? 20 : 0
            leftMargin: isUser ? 0 : 20
            top: parent.top
            topMargin: 5
        }
        property bool isTyping: root.status === "typing" && root.content === ""
        width: isTyping ? 72 : Math.min(contentMetrics.implicitWidth + 32, root.width * 0.75)
        height: isTyping ? 42 : contentText.contentHeight + 28
        radius: sizeBubbleRadius
        opacity: shouldAnimateEntrance && !_entranceStarted ? 0.0 : 1.0
        scale: shouldAnimateEntrance && !_entranceStarted ? entranceStartScale : 1.0
        transformOrigin: Item.Center
        transform: Translate { id: enterTranslate; y: 0 }

        color: isUser ? (hoverHandler.hovered ? accentHover : accent) : (hoverHandler.hovered ? bgCardHover : bgCard)
        border.color: isUser ? "transparent" : borderSubtle
        border.width: isUser ? 0 : 1
        Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

        HoverHandler { id: hoverHandler; cursorShape: Qt.PointingHandCursor }
        MouseArea {
            id: clickArea
            anchors.fill: parent
            z: 10
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
                root.copyToClipboard(root.content)
                copyFlash.opacity = 0.0
                copyFlashAnim.restart()
            }
        }

        Rectangle { id: copyFlash; anchors.fill: parent; radius: parent.radius; z: 1; color: root.isUser ? chatBubbleCopyFlashUser : accentGlow; opacity: 0.0 }
        SequentialAnimation {
            id: copyFlashAnim
            NumberAnimation { target: copyFlash; property: "opacity"; from: 0.0; to: motionCopyFlashPeak; duration: motionMicro; easing.type: easeStandard }
            NumberAnimation { target: copyFlash; property: "opacity"; to: 0.0; duration: motionUi; easing.type: easeStandard }
        }

        ParallelAnimation {
            id: entranceAnim
            NumberAnimation { target: bubble; property: "opacity"; from: 0.0; to: 1.0; duration: entranceOpacityDuration; easing.type: easeStandard }
            NumberAnimation { target: bubble; property: "scale"; from: entranceStartScale; to: 1.0; duration: entranceScaleDuration; easing.type: easeEmphasis }
            NumberAnimation { target: enterTranslate; property: "y"; from: -motionEnterOffsetY; to: 0; duration: entranceScaleDuration; easing.type: easeEmphasis }
        }

        Text {
            id: contentText
            anchors { top: parent.top; topMargin: 14; left: parent.left; leftMargin: 16; right: parent.right; rightMargin: 16 }
            text: root.content
            visible: root.content !== ""
            color: root.isUser ? "#FFFFFF" : textPrimary
            font.pixelSize: typeBody
            wrapMode: Text.Wrap
            textFormat: root.isMarkdown ? Text.MarkdownText : Text.PlainText
            lineHeight: lineHeightBody
        }

        Item {
            id: typingIndicator
            anchors.centerIn: parent
            visible: bubble.isTyping
            width: 32
            height: 10

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
                            running: typingIndicator.visible
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

        Rectangle { anchors.fill: parent; radius: parent.radius; color: chatBubbleErrorTint; visible: root.status === "error" }
    }
}
