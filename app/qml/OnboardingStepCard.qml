import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    property int stepNumber: 0
    property string overlineText: ""
    property string title: ""
    property string description: ""
    property string ctaText: ""
    property bool done: false
    property bool current: false
    property bool clickable: true
    readonly property color surfaceColor: _surfaceColor()
    readonly property color outlineColor: _outlineColor()
    readonly property string statusText: _statusText()
    readonly property color statusTextColor: _statusTextColor()
    readonly property color badgeColor: _badgeColor()
    readonly property color badgeOutlineColor: _badgeOutlineColor()
    readonly property color badgeTextColor: _badgeTextColor()
    readonly property color ctaFillColor: _ctaFillColor()
    readonly property color ctaTextColor: _ctaTextColor()
    signal clicked()

    function _surfaceColor() {
        if (current)
            return isDark ? "#16110D" : "#FFF9F3"
        if (done)
            return isDark ? "#14110F" : "#FFFDFC"
        return isDark ? "#0F0C0A" : "#FFFFFFFF"
    }

    function _outlineColor() {
        if (current)
            return accent
        if (done)
            return isDark ? "#26FFB33D" : "#20A8641F"
        return borderSubtle
    }

    function _statusText() {
        if (done)
            return tr("已完成", "Done")
        if (current)
            return tr("当前步骤", "Current step")
        return tr("待执行", "Up next")
    }

    function _statusTextColor() {
        if (current)
            return accent
        if (done)
            return textPrimary
        return textTertiary
    }

    function _badgeColor() {
        if (done)
            return accent
        if (current)
            return isDark ? "#20FFB33D" : "#18FFB33D"
        return isDark ? "#14FFFFFF" : "#10F3ECE6"
    }

    function _badgeOutlineColor() {
        if (done || current)
            return accent
        return borderSubtle
    }

    function _badgeTextColor() {
        if (done)
            return "#FFFFFFFF"
        if (current)
            return accent
        return textSecondary
    }

    function _ctaFillColor() {
        if (current)
            return accent
        if (done)
            return isDark ? "#14FFFFFF" : "#10F3ECE6"
        return "transparent"
    }

    function _ctaTextColor() {
        if (current)
            return "#FFFFFFFF"
        if (done)
            return textPrimary
        return textSecondary
    }

    function _selectionRailOpacity() {
        if (current)
            return 1.0
        if (done)
            return 0.45
        if (stepArea.containsMouse)
            return 0.28
        return 0.0
    }

    radius: radiusLg
    color: root.surfaceColor
    border.color: root.outlineColor
    border.width: root.current ? 1.3 : 1
    implicitHeight: stepCardCol.implicitHeight + 28

    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
    Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

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
        id: stepCardCol
        anchors.fill: parent
        anchors.margins: 16
        anchors.leftMargin: 18
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Rectangle {
                Layout.alignment: Qt.AlignTop
                width: 30
                height: 30
                radius: 15
                color: root.badgeColor
                border.color: root.badgeOutlineColor
                border.width: root.current || !root.done ? 1.1 : 0

                Text {
                    anchors.centerIn: parent
                    text: root.done ? "OK" : String(root.stepNumber + 1)
                    color: root.badgeTextColor
                    font.pixelSize: typeLabel
                    font.weight: Font.DemiBold
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    Layout.fillWidth: true
                    text: root.overlineText !== "" ? root.overlineText : root.statusText
                    color: root.statusTextColor
                    font.pixelSize: typeCaption
                    font.weight: Font.DemiBold
                    font.letterSpacing: letterWide
                    wrapMode: Text.WordWrap
                }

                Text {
                    Layout.fillWidth: true
                    text: root.title
                    color: textPrimary
                    font.pixelSize: typeBody
                    font.weight: Font.Bold
                    wrapMode: Text.WordWrap
                }
            }

            Rectangle {
                implicitWidth: stepActionLabel.implicitWidth + 18
                implicitHeight: 28
                radius: 14
                color: root.ctaFillColor
                border.color: root.current ? accent : borderSubtle
                border.width: root.current ? 0 : 1

                Text {
                    id: stepActionLabel
                    anchors.centerIn: parent
                    text: root.ctaText
                    color: root.ctaTextColor
                    font.pixelSize: typeCaption
                    font.weight: Font.DemiBold
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.description
            color: textSecondary
            font.pixelSize: typeMeta
            wrapMode: Text.WordWrap
            lineHeight: 1.18
        }
    }

    MouseArea {
        id: stepArea
        anchors.fill: parent
        enabled: root.clickable
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        scrollGestureEnabled: false
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }
}
