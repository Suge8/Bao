import QtQuick 2.15

Rectangle {
    id: root

    property string glyphText: ""
    property string iconSource: ""
    property bool buttonEnabled: true
    property bool emphasized: false
    property real buttonSize: 30
    property real glyphSize: typeButton
    property color fillColor: emphasized ? accent : "transparent"
    property color hoverFillColor: emphasized ? accentHover : bgCardHover
    property color outlineColor: emphasized ? accent : borderSubtle
    property color glyphColor: emphasized ? "#FFFFFFFF" : textSecondary
    property color disabledGlyphColor: textTertiary
    property real hoverScale: motionHoverScaleSubtle
    property real pressedScale: 0.96
    readonly property bool hovered: buttonArea.containsMouse
    readonly property bool pressed: buttonArea.pressed
    signal clicked()

    implicitWidth: root.buttonSize
    implicitHeight: root.buttonSize
    radius: root.buttonSize / 2
    color: root.buttonEnabled ? (buttonArea.containsMouse ? root.hoverFillColor : root.fillColor) : "transparent"
    border.width: 1
    border.color: root.outlineColor
    opacity: root.buttonEnabled ? 1.0 : 0.6
    scale: !root.buttonEnabled ? 1.0 : (buttonArea.pressed ? root.pressedScale : (buttonArea.containsMouse ? root.hoverScale : 1.0))

    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeEmphasis } }

    AppIcon {
        visible: root.iconSource !== ""
        anchors.centerIn: parent
        source: root.iconSource
        sourceSize: Qt.size(root.glyphSize, root.glyphSize)
        width: root.glyphSize
        height: root.glyphSize
        opacity: root.buttonEnabled ? 1.0 : 0.5
    }

    Text {
        visible: root.iconSource === "" && root.glyphText !== ""
        anchors.centerIn: parent
        text: root.glyphText
        color: root.buttonEnabled ? root.glyphColor : root.disabledGlyphColor
        font.pixelSize: root.glyphSize
        font.weight: weightDemiBold
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
