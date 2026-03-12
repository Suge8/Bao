import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    property string text: ""
    property string leadingText: ""
    property string iconSource: ""
    property real iconSize: 15
    property bool buttonEnabled: true
    property color fillColor: accent
    property color hoverFillColor: accentHover
    property color disabledFillColor: isDark ? "#24FFFFFF" : "#14000000"
    property color outlineColor: accent
    property color hoverOutlineColor: accent
    property color textColor: "#FFFFFFFF"
    property color disabledTextColor: textSecondary
    property bool outlined: false
    property bool showOutlineWhenDisabled: false
    property real horizontalPadding: 20
    property real minHeight: 30
    property real hoverScale: motionHoverScaleSubtle
    property real pressedScale: 0.988
    signal clicked()

    implicitWidth: contentRow.implicitWidth + root.horizontalPadding
    implicitHeight: root.minHeight
    radius: implicitHeight / 2
    color: !root.buttonEnabled ? root.disabledFillColor : (buttonArea.containsMouse ? root.hoverFillColor : root.fillColor)
    border.width: root.outlined || (!root.buttonEnabled && root.showOutlineWhenDisabled) ? 1 : 0
    border.color: !root.buttonEnabled ? root.outlineColor : (buttonArea.containsMouse ? root.hoverOutlineColor : root.outlineColor)
    opacity: root.buttonEnabled ? 1.0 : 0.6
    scale: !root.buttonEnabled ? 1.0 : (buttonArea.pressed ? root.pressedScale : (buttonArea.containsMouse ? root.hoverScale : 1.0))

    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on border.width { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

    RowLayout {
        id: contentRow
        anchors.centerIn: parent
        spacing: (root.leadingText !== "" || root.iconSource !== "") ? 7 : 0

        Image {
            visible: root.iconSource !== ""
            source: root.iconSource
            width: root.iconSize
            height: root.iconSize
            sourceSize: Qt.size(root.iconSize, root.iconSize)
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            opacity: root.buttonEnabled ? 1.0 : 0.6
        }

        Text {
            visible: root.leadingText !== ""
            text: root.leadingText
            color: root.buttonEnabled ? root.textColor : root.disabledTextColor
            font.pixelSize: typeMeta
            font.weight: weightBold
        }

        Text {
            text: root.text
            color: root.buttonEnabled ? root.textColor : root.disabledTextColor
            font.pixelSize: typeLabel
            font.weight: weightDemiBold
        }
    }

    MouseArea {
        id: buttonArea
        anchors.fill: parent
        enabled: root.buttonEnabled
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        scrollGestureEnabled: false
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }
}
