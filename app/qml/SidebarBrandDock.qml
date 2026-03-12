import QtQuick 2.15

Item {
    id: root
    objectName: "sidebarBrandDock"

    property bool active: false
    property bool isDark: false
    property bool hasDiagnostics: false
    property int diagnosticsCount: 0
    property string diagnosticsLabel: ""
    property string diagnosticsHint: ""
    property var bubbleMessages: []

    property color accent: "#FFB33D"
    property color textPrimary: "#FFF6EA"
    property color textSecondary: "#C8B09A"
    property int typeMeta: 12
    property int weightMedium: Font.Medium
    property int weightDemiBold: Font.DemiBold
    property int weightBold: Font.Bold

    property int motionFast: 180
    property int motionUi: 220
    property int motionPanel: 320
    property int easeStandard: Easing.OutCubic
    property int easeEmphasis: Easing.OutBack
    property int easeSoft: Easing.InOutSine
    property real motionHoverScaleSubtle: 1.02
    property real motionPressScaleStrong: 0.94
    property real motionSelectionScaleActive: 1.015

    signal settingsRequested()
    signal diagnosticsRequested()

    implicitWidth: 188
    implicitHeight: 88

    readonly property bool iconHovered: appIconArea.containsMouse
    readonly property bool diagnosticsHovered: diagnosticsArea.containsMouse
    readonly property int visibleDiagnosticsCount: Math.max(0, diagnosticsCount)
    readonly property bool bubbleVisible: iconHovered && currentBubbleText.length > 0
    readonly property real appIconScale: appIconArea.pressed
                                         ? motionPressScaleStrong
                                         : (root.active
                                            ? motionSelectionScaleActive
                                            : (root.iconHovered ? 1.015 : 1.0))
    readonly property url brandImageSource: isDark
                                            ? "../resources/logo-bun-dark.png"
                                            : "../resources/logo-bun-light.png"
    property string currentBubbleText: ""
    readonly property int idleMotionDuration: 860
    readonly property real idleLiftTravel: 3.6
    readonly property real idleScalePeak: 1.055
    readonly property real hoverLiftTravel: 4.6
    readonly property real hoverTiltAngle: -5.5
    readonly property real hoverScalePeak: 1.115

    function pickBubbleText() {
        if (!bubbleMessages || bubbleMessages.length === 0)
            return ""
        var idx = Math.floor(Math.random() * bubbleMessages.length)
        return bubbleMessages[idx] || ""
    }

    onIconHoveredChanged: {
        if (iconHovered)
            currentBubbleText = pickBubbleText()
    }

    Rectangle {
        id: appIconBtn
        objectName: "sidebarAppIconButton"
        readonly property bool active: root.active
        width: 68
        height: 68
        radius: 34
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 2
        antialiasing: true
        color: "transparent"
        border.width: root.active ? 1.5 : 0
        border.color: root.active ? accent : "transparent"
        scale: root.appIconScale

        Behavior on border.color {
            ColorAnimation { duration: motionUi; easing.type: easeStandard }
        }
        Behavior on border.width {
            NumberAnimation { duration: motionFast; easing.type: easeStandard }
        }
        Behavior on color {
            ColorAnimation { duration: motionUi; easing.type: easeStandard }
        }
        Behavior on scale {
            NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
        }

        Item {
            id: brandMarkMotion
            objectName: "sidebarBrandMarkMotion"
            property real restY: (parent.height - height) / 2
            width: 58
            height: 58
            x: (parent.width - width) / 2
            y: restY
            rotation: 0
            scale: 1.0
            transformOrigin: Item.Center

            states: [
                State {
                    name: "hovered"
                    when: root.iconHovered
                    PropertyChanges {
                        brandMarkMotion.y: brandMarkMotion.restY - root.hoverLiftTravel
                        brandMarkMotion.rotation: root.hoverTiltAngle
                        brandMarkMotion.scale: appIconArea.pressed ? 0.965 : root.hoverScalePeak
                    }
                },
                State {
                    name: "active"
                    when: root.active
                    PropertyChanges {
                        brandMarkMotion.y: brandMarkMotion.restY - 1.2
                        brandMarkMotion.rotation: 0
                        brandMarkMotion.scale: 1.04
                    }
                }
            ]

            transitions: [
                Transition {
                    NumberAnimation {
                        properties: "y,rotation,scale"
                        duration: motionPanel
                        easing.type: easeSoft
                    }
                }
            ]

            SequentialAnimation on y {
                running: root.visible && !root.iconHovered && !root.active
                loops: Animation.Infinite
                NumberAnimation {
                    to: brandMarkMotion.restY - root.idleLiftTravel
                    duration: root.idleMotionDuration
                    easing.type: easeSoft
                }
                NumberAnimation {
                    to: brandMarkMotion.restY
                    duration: root.idleMotionDuration - 110
                    easing.type: easeSoft
                }
            }

            SequentialAnimation on scale {
                running: root.visible && !root.iconHovered && !root.active
                loops: Animation.Infinite
                NumberAnimation {
                    to: root.idleScalePeak
                    duration: root.idleMotionDuration
                    easing.type: easeSoft
                }
                NumberAnimation {
                    to: 1.0
                    duration: root.idleMotionDuration - 110
                    easing.type: easeSoft
                }
            }

            Image {
                anchors.fill: parent
                source: root.brandImageSource
                sourceSize: Qt.size(116, 116)
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }
        }

        MouseArea {
            id: appIconArea
            anchors.fill: parent
            anchors.margins: -8
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.settingsRequested()
        }
    }

    Rectangle {
        id: diagnosticsPill
        objectName: "sidebarDiagnosticsPill"
        width: 108
        height: 38
        radius: 19
        anchors.left: appIconBtn.right
        anchors.leftMargin: 16
        anchors.verticalCenter: appIconBtn.verticalCenter
        antialiasing: true
        border.width: 1
        border.color: root.diagnosticsHovered
                      ? (isDark ? "#22FFFFFF" : "#22D3B089")
                      : (isDark ? "#18FFFFFF" : "#18D9C2A9")
        scale: diagnosticsArea.pressed
               ? motionPressScaleStrong
               : (root.diagnosticsHovered ? motionHoverScaleSubtle : 1.0)
        color: isDark ? "#16110E" : "#FCF6F0"

        Behavior on border.color {
            ColorAnimation { duration: motionUi; easing.type: easeStandard }
        }
        Behavior on color {
            ColorAnimation { duration: motionUi; easing.type: easeStandard }
        }
        Behavior on scale {
            NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
        }

        Row {
            anchors.centerIn: parent
            spacing: 7

            Image {
                width: 18
                height: 18
                anchors.verticalCenter: parent.verticalCenter
                source: isDark
                        ? "../resources/icons/sidebar-diagnostics-dark.svg"
                        : "../resources/icons/sidebar-diagnostics-light.svg"
                sourceSize: Qt.size(18, 18)
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
                opacity: root.diagnosticsHovered ? 1.0 : 0.86
            }

            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 0

                Text {
                    text: root.diagnosticsLabel
                    color: textPrimary
                    font.pixelSize: typeMeta + 1
                    font.weight: weightBold
                    renderType: Text.NativeRendering
                }

                Text {
                    text: root.diagnosticsHint
                    color: textSecondary
                    font.pixelSize: typeMeta - 1
                    font.weight: weightMedium
                    renderType: Text.NativeRendering
                }
            }
        }

        Rectangle {
            visible: root.hasDiagnostics && root.visibleDiagnosticsCount > 0
            width: 18
            height: 18
            radius: 9
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.rightMargin: -3
            anchors.topMargin: -3
            color: accent
            scale: root.diagnosticsHovered ? 1.04 : 1.0

            Behavior on scale {
                NumberAnimation { duration: motionFast; easing.type: easeStandard }
            }

            Text {
                anchors.centerIn: parent
                text: root.visibleDiagnosticsCount > 9 ? "9+" : String(root.visibleDiagnosticsCount)
                color: isDark ? "#241106" : "#FFFFFF"
                font.pixelSize: 8
                font.weight: weightBold
                renderType: Text.NativeRendering
            }
        }

        MouseArea {
            id: diagnosticsArea
            anchors.fill: parent
            anchors.margins: -4
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.diagnosticsRequested()
        }
    }

    Item {
        id: bubbleLayer
        property real liftOffset: root.iconHovered ? 0 : 5
        width: speechBubble.width
        height: speechBubble.height
        x: Math.max(2, appIconBtn.x + appIconBtn.width / 2 - width / 2)
        anchors.bottom: appIconBtn.top
        anchors.bottomMargin: 12
        opacity: root.bubbleVisible ? 1.0 : 0.0
        transform: Translate { y: bubbleLayer.liftOffset }
        visible: opacity > 0.01

        Behavior on opacity {
            NumberAnimation { duration: motionUi; easing.type: easeStandard }
        }
        Behavior on liftOffset {
            NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
        }

        Rectangle {
            id: speechBubble
            readonly property real fittedWidth: Math.max(108, Math.min(156, bubbleLabel.implicitWidth + 28))
            width: fittedWidth
            height: bubbleLabel.implicitHeight + 14
            radius: 14
            anchors.horizontalCenter: parent.horizontalCenter
            color: isDark ? "#1B1511" : "#FFFDF9"
            border.width: 1
            border.color: isDark ? "#30241C" : "#E2D6CB"
            antialiasing: true

            Text {
                id: bubbleLabel
                anchors.centerIn: parent
                width: speechBubble.width - 24
                text: root.currentBubbleText
                color: isDark ? "#E8D8C8" : "#6B5B4C"
                font.pixelSize: typeMeta - 1
                font.weight: weightDemiBold
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
                renderType: Text.NativeRendering
            }
        }
    }
}
