import QtQuick 2.15

Item {
    id: root

    property string avatarSource: ""
    property string variant: "primary"
    property color ringColor: accent
    property string glyphSource: ""
    property var glyphSources: []
    property string statusKey: "idle"
    property bool active: false
    property string countLabel: ""
    property real baseSize: variant === "mini" ? 36 : (variant === "automation" ? 42 : 52)

    implicitWidth: baseSize
    implicitHeight: baseSize

    readonly property bool isRunning: statusKey === "running"
    readonly property bool isAttention: statusKey === "error" || statusKey === "failed"
    readonly property real haloOpacity: active ? 0.26 : 0.16
    readonly property var resolvedGlyphSources: {
        var values = []
        if (Array.isArray(root.glyphSources)) {
            for (var index = 0; index < root.glyphSources.length; index += 1) {
                var source = String(root.glyphSources[index] || "")
                if (source !== "" && values.indexOf(source) === -1)
                    values.push(source)
            }
        }
        if (values.length === 0 && root.glyphSource !== "")
            values.push(root.glyphSource)
        return values
    }
    readonly property color statusColor: {
        if (isAttention)
            return statusError
        if (isRunning)
            return statusSuccess
        return textTertiary
    }

    Rectangle {
        width: root.baseSize + 12
        height: width
        radius: width / 2
        anchors.centerIn: parent
        color: Qt.rgba(root.ringColor.r, root.ringColor.g, root.ringColor.b, root.haloOpacity)
        scale: root.isRunning ? 1.0 : 0.94
        opacity: root.active ? 1.0 : 0.82

        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeSoft } }
        Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
    }

    Rectangle {
        width: root.baseSize + 4
        height: width
        radius: width / 2
        anchors.centerIn: parent
        color: isDark ? "#170F0B" : "#FFF9F2"
        border.width: root.active ? 2 : 1
        border.color: root.ringColor

        Behavior on border.width { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
        Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    }

    Rectangle {
        width: root.baseSize
        height: width
        radius: width / 2
        anchors.centerIn: parent
        color: isDark ? "#221712" : "#FFF4E8"
        border.width: 1
        border.color: isDark ? "#26FFFFFF" : "#14000000"
        clip: true

        Image {
            anchors.fill: parent
            anchors.margins: root.variant === "mini" ? 4 : 3
            source: root.avatarSource
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: false
        }
    }

    Repeater {
        model: Math.min(2, root.resolvedGlyphSources.length)

        delegate: Rectangle {
            required property int index
            readonly property bool firstBadge: index === 0

            visible: root.resolvedGlyphSources.length > 0
            width: root.variant === "mini" ? 14 : 18
            height: width
            radius: width / 2
            anchors.right: parent.right
            anchors.rightMargin: firstBadge ? 0 : (width - 8)
            anchors.bottom: parent.bottom
            anchors.bottomMargin: firstBadge ? 0 : 2
            z: firstBadge ? 2 : 1
            color: isDark ? "#231712" : "#FFF6EA"
            border.width: 1
            border.color: root.ringColor

            AppIcon {
                anchors.centerIn: parent
                width: parent.width - 6
                height: width
                source: String(root.resolvedGlyphSources[index] || "")
                sourceSize: Qt.size(width, height)
                opacity: 0.96
            }
        }
    }

    Rectangle {
        visible: root.resolvedGlyphSources.length > 2 && root.countLabel === ""
        width: root.variant === "mini" ? 14 : 18
        height: width
        radius: width / 2
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: root.variant === "mini" ? 12 : 14
        anchors.bottomMargin: 4
        color: isDark ? "#24160F" : "#FFF3E2"
        border.width: 1
        border.color: root.ringColor

        Text {
            anchors.centerIn: parent
            text: "+" + String(root.resolvedGlyphSources.length - 2)
            color: textPrimary
            font.pixelSize: typeCaption
            font.weight: weightBold
        }
    }

    Rectangle {
        visible: root.countLabel !== ""
        height: 16
        radius: 8
        anchors.left: parent.left
        anchors.leftMargin: -2
        anchors.bottom: parent.bottom
        color: isDark ? "#24160F" : "#FFF3E2"
        border.width: 1
        border.color: root.ringColor
        width: Math.max(16, countText.implicitWidth + 8)

        Text {
            id: countText
            anchors.centerIn: parent
            text: root.countLabel
            color: textPrimary
            font.pixelSize: typeCaption
            font.weight: weightBold
        }
    }

    Rectangle {
        width: 10
        height: 10
        radius: 5
        anchors.top: parent.top
        anchors.right: parent.right
        color: root.statusColor
        border.width: 1
        border.color: isDark ? "#D7FFF0" : "#FFFFFF"
        visible: root.isRunning || root.isAttention
        opacity: root.isRunning ? 0.8 : 0.92

        SequentialAnimation on scale {
            running: root.isRunning
            loops: Animation.Infinite
            NumberAnimation { from: 0.9; to: 1.18; duration: motionBreath; easing.type: easeSoft }
            NumberAnimation { from: 1.18; to: 0.9; duration: motionBreath; easing.type: easeSoft }
        }

        SequentialAnimation on opacity {
            running: root.isRunning
            loops: Animation.Infinite
            NumberAnimation { from: 0.48; to: 1.0; duration: motionBreath; easing.type: easeSoft }
            NumberAnimation { from: 1.0; to: 0.48; duration: motionBreath; easing.type: easeSoft }
        }
    }
}
