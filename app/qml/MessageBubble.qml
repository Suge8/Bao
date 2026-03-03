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
    readonly property int entranceOpacityDuration: entranceStyle === "greeting" ? 240 : (isSystem ? 260 : (isUser ? 160 : 200))
    readonly property int entranceScaleDuration: entranceStyle === "greeting" ? 260 : (isSystem ? 320 : (isUser ? 200 : 220))
    readonly property real entranceStartScale: entranceStyle === "greeting" ? 0.965 : (isSystem ? 0.94 : (isUser ? 0.976 : 0.972))
    readonly property real entranceStartY: isSystem ? 18 : 0

    height: isSystem ? systemBubble.height + 14 : bubble.height + 10
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
        anchors.margins: -12
        radius: systemBubble.radius + 12
        color: root.status === "error" ? "#2EF87171" : (isDark ? "#2C9AA8FF" : "#247C6CF0")
        opacity: 0.0
    }

    Rectangle {
        id: systemAuraNear
        visible: isSystem
        anchors.fill: systemBubble
        anchors.margins: -6
        radius: systemBubble.radius + 6
        color: root.status === "error" ? "#44F87171" : (isDark ? "#249AA8FF" : "#1E7C6CF0")
        opacity: 0.0
    }

    Rectangle {
        id: systemBubble
        visible: isSystem
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 7
        width: Math.max(60, Math.min(root.width * 0.9, systemText.implicitWidth + 34))
        height: systemText.contentHeight + 14
        radius: 11
        color: root.status === "error" ? (isDark ? "#20F87171" : "#14F87171") : (isDark ? "#14FFFFFF" : "#12000000")
        border.width: 1
        border.color: root.status === "error" ? (isDark ? "#58F87171" : "#42F87171") : borderSubtle
        opacity: shouldAnimateEntrance && !_entranceStarted ? 0.0 : 1.0
        scale: shouldAnimateEntrance && !_entranceStarted ? entranceStartScale : 1.0
        transformOrigin: Item.Center
        transform: Translate { id: systemShift; y: 0 }

        Behavior on color { ColorAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on border.color { ColorAnimation { duration: 180; easing.type: Easing.OutCubic } }

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: root.status === "error" ? "#08F87171" : (isDark ? "#0D7C6CF0" : "#097C6CF0")
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
            font.pixelSize: 12
            font.weight: Font.Medium
            font.letterSpacing: 0.2
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
        onStopped: root.consumeEntrance()
        NumberAnimation { target: systemBubble; property: "opacity"; from: 0.0; to: 1.0; duration: entranceOpacityDuration; easing.type: Easing.OutCubic }
        NumberAnimation { target: systemBubble; property: "scale"; from: entranceStartScale; to: 1.0; duration: entranceScaleDuration; easing.type: Easing.OutCubic }
        NumberAnimation { target: systemShift; property: "y"; from: entranceStartY; to: 0; duration: entranceScaleDuration; easing.type: Easing.OutCubic }
        SequentialAnimation {
            NumberAnimation { target: systemAuraNear; property: "opacity"; from: 0.0; to: 0.24; duration: 170; easing.type: Easing.OutCubic }
            NumberAnimation { target: systemAuraNear; property: "opacity"; to: 0.0; duration: 520; easing.type: Easing.OutCubic }
        }
        SequentialAnimation {
            NumberAnimation { target: systemAuraFar; property: "opacity"; from: 0.0; to: 0.14; duration: 220; easing.type: Easing.OutCubic }
            NumberAnimation { target: systemAuraFar; property: "opacity"; to: 0.0; duration: 700; easing.type: Easing.OutCubic }
        }
    }

    TextEdit { id: clipHelper; visible: false }

    Text {
        id: contentMetrics
        text: root.content
        font.pixelSize: 15
        textFormat: root.isMarkdown ? Text.MarkdownText : Text.PlainText
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
        radius: 18
        opacity: shouldAnimateEntrance && !_entranceStarted ? 0.0 : 1.0
        scale: shouldAnimateEntrance && !_entranceStarted ? entranceStartScale : 1.0
        transformOrigin: Item.Center
        transform: Translate { id: enterTranslate; y: 0 }

        color: isUser ? (hoverHandler.hovered ? accentHover : accent) : (hoverHandler.hovered ? bgCardHover : bgCard)
        border.color: isUser ? "transparent" : borderSubtle
        border.width: isUser ? 0 : 1
        Behavior on color { ColorAnimation { duration: 150 } }

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

        Rectangle { id: copyFlash; anchors.fill: parent; radius: parent.radius; z: 1; color: root.isUser ? "#40FFFFFF" : accentGlow; opacity: 0.0 }
        SequentialAnimation {
            id: copyFlashAnim
            NumberAnimation { target: copyFlash; property: "opacity"; from: 0.0; to: 0.32; duration: 90; easing.type: Easing.OutCubic }
            NumberAnimation { target: copyFlash; property: "opacity"; to: 0.0; duration: 180; easing.type: Easing.OutCubic }
        }

        ParallelAnimation {
            id: entranceAnim
            onStopped: root.consumeEntrance()
            NumberAnimation { target: bubble; property: "opacity"; from: 0.0; to: 1.0; duration: entranceOpacityDuration; easing.type: Easing.OutCubic }
            NumberAnimation { target: bubble; property: "scale"; from: entranceStartScale; to: 1.0; duration: entranceScaleDuration; easing.type: Easing.OutCubic }
            NumberAnimation { target: enterTranslate; property: "y"; from: 10; to: 0; duration: entranceScaleDuration; easing.type: Easing.OutCubic }
        }

        Text {
            id: contentText
            anchors { top: parent.top; topMargin: 14; left: parent.left; leftMargin: 16; right: parent.right; rightMargin: 16 }
            text: root.content
            visible: root.content !== ""
            color: root.isUser ? "#FFFFFF" : textPrimary
            font.pixelSize: 15
            wrapMode: Text.Wrap
            textFormat: root.isMarkdown ? Text.MarkdownText : Text.PlainText
            lineHeight: 1.4
        }

        Rectangle { anchors.fill: parent; radius: parent.radius; color: "#15F87171"; visible: root.status === "error" }
    }
}
