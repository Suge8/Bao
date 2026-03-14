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
    property real motionPressScaleStrong: 0.94
    property real motionSelectionScaleActive: 1.015

    signal settingsRequested()
    signal diagnosticsRequested()

    implicitWidth: 188
    implicitHeight: 72

    readonly property bool iconHovered: appIconArea.containsMouse
    readonly property bool diagnosticsHovered: diagnosticsArea.containsMouse
    readonly property int visibleDiagnosticsCount: Math.max(0, diagnosticsCount)
    readonly property bool bubbleVisible: iconHovered && currentBubbleText.length > 0
    readonly property color primaryInk: isDark ? "#F7EFE7" : "#261A12"
    readonly property color secondaryInk: isDark ? "#C5AF9E" : "#6B5649"
    readonly property url brandImageSource: "../resources/logo-circle.png"
    property string currentBubbleText: ""
    readonly property real appIconRestScale: root.iconHovered ? 1.015 : 1.0
    readonly property real appIconInteractiveScale: root.active
                                                    ? motionSelectionScaleActive
                                                    : root.appIconRestScale
    readonly property real appIconScale: appIconArea.pressed
                                         ? motionPressScaleStrong
                                         : root.appIconInteractiveScale
    readonly property int idleMotionDuration: 860
    readonly property real idleLiftTravel: 3.6
    readonly property real idleScalePeak: 1.055
    readonly property real hoverLiftTravel: 5.2
    readonly property real hoverTiltAngle: -6.5
    readonly property real hoverScalePeak: 1.14
    readonly property real brandAuraRestOpacity: root.iconHovered ? 0.26 : 0.10
    readonly property real brandAuraOpacity: root.active ? 0.34 : root.brandAuraRestOpacity
    readonly property real brandAuraRestScale: root.active ? 1.02 : 0.94
    readonly property real brandAuraScale: root.iconHovered ? 1.08 : root.brandAuraRestScale
    readonly property real brandPlateOpacity: root.iconHovered ? 0.92 : 0.76
    readonly property real brandPlateScale: root.iconHovered ? 1.02 : 0.98
    readonly property real diagnosticsHoverScale: root.diagnosticsHovered ? 1.03 : 1.0
    readonly property color diagnosticsBorderColor: root.diagnosticsHovered
                                                    ? (isDark ? "#C29C6A" : "#D8A66A")
                                                    : (isDark ? "#2AFFFFFF" : "#DCC4A7")
    readonly property color diagnosticsFillColor: root.diagnosticsHovered
                                                  ? (isDark ? "#221712" : "#F6EBDD")
                                                  : (isDark ? "#16110E" : "#FCF6F0")
    readonly property color diagnosticsOverlayColor: root.diagnosticsHovered
                                                     ? (isDark ? "#12FFFFFF" : "#16FFFFFF")
                                                     : (isDark ? "#07FFFFFF" : "#0CFFFFFF")
    readonly property real diagnosticsIconScale: root.diagnosticsHovered ? 1.06 : 1.0
    readonly property real diagnosticsIconOpacity: root.diagnosticsHovered ? 1.0 : 0.88
    readonly property real diagnosticsLabelOpacity: root.diagnosticsHovered ? 1.0 : 0.94
    readonly property color diagnosticsHintColor: root.diagnosticsHovered
                                                  ? root.primaryInk
                                                  : root.secondaryInk
    readonly property int diagnosticsHintWeight: root.diagnosticsHovered
                                                 ? weightDemiBold
                                                 : weightMedium
    readonly property real diagnosticsBadgeScale: root.diagnosticsHovered ? 1.04 : 1.0
    readonly property string diagnosticsCountLabel: root.visibleDiagnosticsCount > 9
                                                    ? "9+"
                                                    : String(root.visibleDiagnosticsCount)

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

        Rectangle {
            id: brandAura
            anchors.centerIn: parent
            width: 78
            height: 78
            radius: width / 2
            color: isDark ? "#26F4BF6A" : "#2FE4A45D"
            opacity: root.brandAuraOpacity
            scale: root.brandAuraScale

            Behavior on opacity {
                NumberAnimation { duration: motionUi; easing.type: easeSoft }
            }
            Behavior on scale {
                NumberAnimation { duration: motionPanel; easing.type: easeEmphasis }
            }
        }

        Rectangle {
            anchors.centerIn: parent
            width: 66
            height: 66
            radius: width / 2
            color: isDark ? "#12000000" : "#120A0603"
            opacity: root.brandPlateOpacity
            scale: root.brandPlateScale

            Behavior on opacity {
                NumberAnimation { duration: motionFast; easing.type: easeStandard }
            }
            Behavior on scale {
                NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
            }
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
                        brandMarkMotion.x: (appIconBtn.width - brandMarkMotion.width) / 2 - 0.6
                        brandMarkMotion.scale: appIconArea.pressed ? 0.965 : root.hoverScalePeak
                    }
                },
                State {
                    name: "active"
                    when: root.active
                    PropertyChanges {
                        brandMarkMotion.y: brandMarkMotion.restY - 1.2
                        brandMarkMotion.rotation: 0
                        brandMarkMotion.x: (appIconBtn.width - brandMarkMotion.width) / 2
                        brandMarkMotion.scale: 1.04
                    }
                }
            ]

            transitions: [
                Transition {
                    NumberAnimation {
                        properties: "x,y,rotation,scale"
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

            AppIcon {
                id: brandMarkIcon
                objectName: "sidebarBrandMarkIcon"
                anchors.fill: parent
                source: root.brandImageSource
                sourceSize: Qt.size(116, 116)
            }

            Rectangle {
                width: 22
                height: 9
                radius: 4.5
                anchors.top: parent.top
                anchors.topMargin: 8
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.horizontalCenterOffset: -8
                rotation: -18
                color: "#24FFFFFF"
                opacity: root.iconHovered ? 0.42 : 0.20

                Behavior on opacity {
                    NumberAnimation { duration: motionFast; easing.type: easeStandard }
                }
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
        width: 104
        height: 42
        radius: 21
        anchors.left: appIconBtn.right
        anchors.leftMargin: 16
        anchors.verticalCenter: appIconBtn.verticalCenter
        antialiasing: true
        border.width: 1
        border.color: root.diagnosticsBorderColor
        scale: diagnosticsArea.pressed ? motionPressScaleStrong : root.diagnosticsHoverScale
        color: root.diagnosticsFillColor

        Behavior on border.color {
            ColorAnimation { duration: motionUi; easing.type: easeStandard }
        }
        Behavior on color {
            ColorAnimation { duration: motionUi; easing.type: easeStandard }
        }
        Behavior on scale {
            NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: parent.radius - 1
            color: root.diagnosticsOverlayColor
        }

        Row {
            id: diagnosticsContentRow
            objectName: "sidebarDiagnosticsContentRow"
            anchors.fill: parent
            anchors.leftMargin: 11
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            spacing: 14

            Item {
                id: diagnosticsIconChip
                objectName: "sidebarDiagnosticsIconChip"
                width: 20
                height: 20
                anchors.verticalCenter: parent.verticalCenter
                scale: root.diagnosticsIconScale

                Behavior on scale {
                    NumberAnimation { duration: motionFast; easing.type: easeStandard }
                }

                AppIcon {
                    width: 20
                    height: 20
                    anchors.centerIn: parent
                    source: isDark
                            ? "../resources/icons/sidebar-diagnostics-dark.svg"
                            : "../resources/icons/sidebar-diagnostics-light.svg"
                    sourceSize: Qt.size(20, 20)
                    opacity: root.diagnosticsIconOpacity
                }
            }

            Column {
                id: diagnosticsLabelStack
                objectName: "sidebarDiagnosticsLabelStack"
                anchors.verticalCenter: parent.verticalCenter
                spacing: 0
                width: parent.width - diagnosticsIconChip.width - parent.spacing

                Text {
                    text: root.diagnosticsLabel
                    color: root.primaryInk
                    font.pixelSize: typeMeta + 1
                    font.weight: weightBold
                    renderType: Text.NativeRendering
                    opacity: root.diagnosticsLabelOpacity
                }

                Text {
                    text: root.diagnosticsHint
                    color: root.diagnosticsHintColor
                    font.pixelSize: typeMeta - 1
                    font.weight: root.diagnosticsHintWeight
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
            scale: root.diagnosticsBadgeScale

            Behavior on scale {
                NumberAnimation { duration: motionFast; easing.type: easeStandard }
            }

            Text {
                anchors.centerIn: parent
                text: root.diagnosticsCountLabel
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
