import QtQuick 2.15
import QtQuick.Controls 2.15

Flickable {
    id: root

    property alias text: logText.text
    property color textColor: "#2C241F"
    property int fontPixelSize: 12
    property string fontFamily: Qt.platform.os === "osx" ? "Menlo" : "Monospace"
    property int followTailThreshold: 4
    property bool autoFollowActive: true
    property bool scrollToEndQueued: false
    readonly property bool hasText: text.length > 0

    clip: true
    boundsBehavior: Flickable.StopAtBounds
    contentWidth: width
    contentHeight: Math.max(height, logText.contentHeight)

    ScrollBar.vertical: ScrollBar {
        policy: ScrollBar.AsNeeded
    }

    function maxContentY() {
        return Math.max(0, contentHeight - height)
    }

    function isNearEnd() {
        return maxContentY() - contentY <= followTailThreshold
    }

    function refreshAutoFollowFromViewport() {
        autoFollowActive = !hasText || isNearEnd()
    }

    function applyScrollToEnd() {
        contentY = maxContentY()
    }

    function requestScrollToEnd() {
        if (scrollToEndQueued || !autoFollowActive || !hasText)
            return
        scrollToEndQueued = true
        Qt.callLater(function() {
            if (root.visible && root.autoFollowActive)
                root.applyScrollToEnd()
            root.scrollToEndQueued = false
        })
    }

    function followTail() {
        autoFollowActive = true
        requestScrollToEnd()
    }

    onContentYChanged: refreshAutoFollowFromViewport()
    onContentHeightChanged: requestScrollToEnd()
    onHeightChanged: requestScrollToEnd()
    onVisibleChanged: {
        if (visible)
            requestScrollToEnd()
    }

    TextEdit {
        id: logText
        property bool baoClickAwayEditor: true
        readOnly: true
        width: root.width
        color: root.textColor
        wrapMode: TextEdit.NoWrap
        selectByMouse: true
        textFormat: TextEdit.PlainText
        font.pixelSize: root.fontPixelSize
        font.family: root.fontFamily
        padding: 0
        onTextChanged: root.requestScrollToEnd()
    }
}
