import QtQuick 2.15

Item {
    id: root

    property string source: ""
    property color accent: "#F59E0B"
    property bool active: false
    property bool hovered: false
    property bool isDark: true
    property int size: 40
    property int motionFast: 160
    property int easeStandard: Easing.OutCubic

    width: size
    height: size
    scale: active ? 1.0 : (hovered ? 0.98 : 0.94)
    y: hovered ? -1 : 0

    Behavior on scale { NumberAnimation { duration: root.motionFast; easing.type: root.easeStandard } }
    Behavior on y { NumberAnimation { duration: root.motionFast; easing.type: root.easeStandard } }

    Rectangle {
        anchors.fill: parent
        radius: 14
        color: isDark ? "#0E0A08" : "#EADBCB"
        opacity: active ? 0.34 : (hovered ? 0.22 : 0.16)
        y: 3
    }

    Rectangle {
        anchors.fill: parent
        radius: 14
        color: isDark ? "#1C1410" : "#FFF8EF"
        border.width: active ? 2 : 1
        border.color: active ? accent : (isDark ? "#32FFFFFF" : "#18000000")
    }

    Image {
        anchors.centerIn: parent
        width: parent.width - 8
        height: parent.height - 8
        fillMode: Image.PreserveAspectFit
        smooth: false
        mipmap: false
        source: root.source
    }

    Rectangle {
        width: 10
        height: 10
        radius: 5
        visible: active
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: -1
        anchors.bottomMargin: -1
        color: accent
        border.width: 2
        border.color: isDark ? "#120D0A" : "#FFF8EF"
    }
}
