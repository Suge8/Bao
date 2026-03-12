import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    property string badgeText: ""
    property string title: ""
    property string description: ""
    property string trailingText: ""
    property bool selected: false
    property bool clickable: true
    property real pulsePhase: 0.0
    readonly property color fillColor: _fillColor()
    readonly property color strokeColor: _strokeColor()
    signal clicked()

    function _fillColor() {
        if (selected)
            return isDark ? "#16FFB33D" : "#12FFB33D"
        return isDark ? "#0EFFFFFF" : "#FFFFFFFF"
    }

    function _strokeColor() {
        if (selected)
            return accent
        if (cardArea.containsMouse)
            return borderDefault
        return borderSubtle
    }

    function _accentOverlayOpacity() {
        if (selected)
            return 0.06 + pulsePhase * 0.04
        if (cardArea.containsMouse)
            return 0.03
        return 0.0
    }

    function _selectionRailOpacity() {
        if (selected)
            return 1.0
        if (cardArea.containsMouse)
            return 0.35
        return 0.0
    }

    radius: radiusMd
    color: root.fillColor
    border.color: root.strokeColor
    border.width: selected || cardArea.containsMouse ? 1.2 : 1
    implicitHeight: cardCol.implicitHeight + 26

    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on border.width { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

    SequentialAnimation on pulsePhase {
        running: root.selected
        loops: Animation.Infinite
        NumberAnimation { from: 0.0; to: 1.0; duration: motionAmbient + motionMicro; easing.type: easeSoft }
        NumberAnimation { from: 1.0; to: 0.0; duration: motionAmbient + motionMicro; easing.type: easeSoft }
    }

    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: accent
        opacity: root._accentOverlayOpacity()
        visible: opacity > 0.001
        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
    }

    Rectangle {
        width: 3
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: 10
        radius: width / 2
        color: accent
        opacity: root._selectionRailOpacity()
        visible: opacity > 0.001
        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
    }

    ColumnLayout {
        id: cardCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        anchors.leftMargin: 16
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            visible: badgeText !== "" || trailingText !== ""

            Rectangle {
                visible: badgeText !== ""
                implicitWidth: badgeLabel.implicitWidth + 16
                implicitHeight: 22
                radius: 12
                color: root.selected ? accent : (isDark ? "#12FFFFFF" : "#10F3ECE6")
                border.color: root.selected ? accent : borderSubtle
                border.width: root.selected ? 0 : 1
                Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                Text {
                    id: badgeLabel
                    anchors.centerIn: parent
                    text: root.badgeText
                    color: root.selected ? "#FFFFFFFF" : textSecondary
                    font.pixelSize: typeCaption
                    font.weight: Font.DemiBold
                }
            }

            Item { Layout.fillWidth: true }

            Text {
                visible: trailingText !== ""
                text: root.trailingText
                color: root.selected ? accent : textTertiary
                font.pixelSize: typeCaption
                font.weight: Font.DemiBold
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.title
            color: textPrimary
            font.pixelSize: typeBody
            font.weight: Font.Bold
            wrapMode: Text.WordWrap
        }

        Text {
            visible: description !== ""
            Layout.fillWidth: true
            text: root.description
            color: textSecondary
            font.pixelSize: typeMeta
            wrapMode: Text.WordWrap
            lineHeight: 1.18
        }
    }

    MouseArea {
        id: cardArea
        anchors.fill: parent
        enabled: root.clickable
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        scrollGestureEnabled: false
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }
}
