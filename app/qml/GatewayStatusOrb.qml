import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root

    property var channels: []
    property string detailText: ""
    property bool detailIsError: false
    property bool parentHovered: false
    property bool parentFocused: false
    property bool isDark: true
    property color bgCanvas: "transparent"
    property color textSecondary: "#FFFFFF"
    property color textPrimary: "#FFFFFF"
    property color statusSuccess: "#22C55E"
    property color statusError: "#EF4444"
    property color statusWarning: "#F59E0B"
    property int typeCaption: 12
    property int weightBold: Font.Bold
    property int weightMedium: Font.Medium
    property int motionFast: 160
    property int motionUi: 200
    property var channelIconSource: null
    property var channelFilledIconSource: null
    property var channelAccent: null

    readonly property int channelCount: channels && channels.length !== undefined ? channels.length : 0
    readonly property bool hasChannels: channelCount > 0
    readonly property bool hasDetail: detailText !== "" || hasChannels
    readonly property bool hasErrorState: detailIsError || _hasState("error")
    readonly property bool hasStartingState: _hasState("starting")
    readonly property bool hasRunningState: _hasState("running")
    readonly property var orbChannels: _orbChannels()
    readonly property int overflowCount: hasChannels ? Math.max(0, channelCount - 2) : 0
    readonly property bool showBubble: hasDetail && (parentHovered || orbHover.containsMouse || bubbleHover.containsMouse)
    readonly property real orbMinWidth: 30
    readonly property real orbPaddingX: hasChannels ? 4 : 0
    readonly property color orbSurface: hasErrorState
                                        ? (isDark ? "#5B2A29" : "#FFF4F1")
                                        : (hasStartingState
                                           ? (isDark ? "#614126" : "#FFF6EA")
                                           : (isDark ? "#4B3126" : "#FFFDFC"))
    readonly property color bubbleSurface: hasErrorState
                                           ? (isDark ? "#FF472122" : "#FFFFF8F6")
                                           : (isDark ? "#FF2A241F" : "#FFFFFCF9")
    readonly property color bubbleBorder: hasErrorState
                                          ? (isDark ? "#55F07A7A" : "#18DC2626")
                                          : (isDark ? "#22FFFFFF" : "#10000000")
    readonly property string bubbleHeading: detailText !== "" ? detailText : _defaultSummary()
    readonly property color bubbleHeadingColor: hasErrorState ? statusError : textPrimary
    readonly property real bubbleHeadingSize: hasErrorState ? typeCaption + 1 : typeCaption
    readonly property int bubbleHeadingWeight: hasErrorState ? weightBold : weightMedium
    readonly property real bubbleHeadingOpacity: hasErrorState ? 1.0 : 0.94
    readonly property real bubbleBodyWidth: hasChannels ? 168 : headingMeasure.implicitWidth
    readonly property color chipSurface: isDark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(1, 1, 1, 0.92)
    readonly property color rowIconSurface: isDark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(1, 1, 1, 0.90)

    visible: hasDetail
    anchors.fill: parent
    z: 10

    function _hasState(state) {
        for (var i = 0; i < channelCount; i++) {
            var item = channels[i]
            if (item && item.state === state)
                return true
        }
        return false
    }

    function _orbChannels() {
        var items = []
        for (var i = 0; i < Math.min(2, channelCount); i++)
            items.push(channels[i])
        return items
    }

    function _iconSource(channel) {
        return channelFilledIconSource ? channelFilledIconSource(channel) : ""
    }

    function _iconAccent(channel, state) {
        if (state === "error")
            return statusError
        if (state === "running")
            return statusSuccess
        if (state === "starting")
            return statusWarning
        return channelAccent ? channelAccent(channel) : textSecondary
    }

    function _channelLabel(channel) {
        var key = "channel_" + channel
        return (typeof strings !== "undefined" && strings[key]) ? strings[key] : channel
    }

    function _channelStateText(state) {
        if (state === "running")
            return typeof strings !== "undefined" ? strings.gateway_running : "Running"
        if (state === "starting")
            return typeof strings !== "undefined" ? strings.gateway_starting : "Starting"
        if (state === "error")
            return typeof strings !== "undefined" ? strings.gateway_error : "Error"
        return typeof strings !== "undefined" ? strings.button_start_gateway : "Ready"
    }

    function _defaultSummary() {
        if (hasErrorState)
            return typeof strings !== "undefined" ? strings.gateway_channels_error : "Error"
        if (hasRunningState)
            return typeof strings !== "undefined" ? strings.gateway_channels_running : "Running"
        if (hasStartingState)
            return typeof strings !== "undefined" ? strings.gateway_starting : "Starting"
        return typeof strings !== "undefined" ? strings.gateway_channels_idle : "Start"
    }

    Rectangle {
        id: orb
        objectName: "gatewayDetailOrb"
        width: Math.max(root.orbMinWidth, orbContent.implicitWidth + root.orbPaddingX * 2)
        height: 28
        radius: height / 2
        anchors.right: parent.right
        anchors.rightMargin: -18
        anchors.top: parent.top
        anchors.topMargin: -8
        color: root.orbSurface
        border.width: 0
        opacity: root.hasDetail ? 1.0 : 0.0
        scale: orbHover.containsMouse ? 1.06 : 1.0

        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: motionFast; easing.type: Easing.OutCubic } }

        Row {
            id: orbContent
            anchors.centerIn: parent
            spacing: 1

            Repeater {
                model: root.orbChannels.length > 0 ? root.orbChannels : [null]

                Rectangle {
                    width: modelData && root.orbChannels.length > 1 ? 15 : 18
                    height: width
                    radius: width / 2
                    color: modelData ? root.chipSurface : "transparent"

                    AppIcon {
                        visible: modelData !== null
                        anchors.centerIn: parent
                        width: parent.width - 1
                        height: width
                        source: modelData ? root._iconSource(modelData.channel) : ""
                        sourceSize: Qt.size(width, height)
                        opacity: 0.96
                    }

                    Rectangle {
                        visible: modelData !== null
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        width: 8
                        height: width
                        radius: width / 2
                        color: modelData ? root._iconAccent(modelData.channel, modelData.state) : "transparent"
                        border.width: 1
                        border.color: orb.color
                    }
                }
            }
        }

        Text {
            anchors.centerIn: parent
            visible: root.orbChannels.length === 0
            text: root.hasErrorState ? "!" : "✓"
            color: root.hasErrorState ? statusError : statusSuccess
            font.pixelSize: 16
            font.weight: weightBold
        }

        Rectangle {
            id: orbOverflowBadge
            objectName: "gatewayDetailOrbOverflow"
            visible: root.overflowCount > 0
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: -4
            anchors.bottomMargin: -2
            width: 15
            height: width
            radius: width / 2
            color: isDark ? "#FF201A17" : "#FFF3E7DB"
            border.width: 0

            Text {
                anchors.centerIn: parent
                text: "+" + root.overflowCount
                color: root.textPrimary
                font.pixelSize: 9
                font.weight: weightBold
            }
        }

        MouseArea {
            id: orbHover
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: function(mouse) { mouse.accepted = true }
        }
    }

    Rectangle {
        id: gatewayDetailBubble
        objectName: "gatewayDetailBubble"
        z: 20
        property real maxContentHeight: 116
        width: Math.max(156, Math.min(280, root.bubbleBodyWidth + 24))
        x: orb.x + orb.width - 2
        y: Math.max(2, orb.y + 2)
        visible: root.showBubble
        color: root.bubbleSurface
        radius: 14
        border.width: 1
        border.color: root.bubbleBorder
        opacity: visible ? 1.0 : 0.0
        implicitHeight: Math.min(maxContentHeight, bubbleContent.implicitHeight) + 16
        clip: true
        transformOrigin: Item.Left
        scale: visible ? 1.0 : 0.92

        Behavior on scale { NumberAnimation { duration: motionFast; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: Easing.OutCubic } }

        Canvas {
            visible: false
            anchors.bottom: parent.top
            width: 12
            height: 8
            x: Math.max(0, Math.min(parent.width - width, orb.x + orb.width / 2 - gatewayDetailBubble.x - width / 2))
            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.beginPath()
                ctx.moveTo(width / 2, 0)
                ctx.lineTo(0, height)
                ctx.lineTo(width, height)
                ctx.closePath()
                ctx.fillStyle = gatewayDetailBubble.color
                ctx.fill()
            }
        }

        Flickable {
            id: gatewayDetailViewport
            objectName: "gatewayDetailViewport"
            anchors.fill: parent
            anchors.margins: 7
            clip: true
            contentWidth: width
            contentHeight: bubbleContent.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height

            Column {
                id: bubbleContent
                width: gatewayDetailViewport.width
                spacing: 6

                Text {
                    id: gatewayDetailText
                    objectName: "gatewayDetailText"
                    width: parent.width
                    text: root.bubbleHeading
                    color: root.bubbleHeadingColor
                    font.pixelSize: root.bubbleHeadingSize
                    font.weight: root.bubbleHeadingWeight
                    opacity: root.bubbleHeadingOpacity
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }

                Text {
                    id: headingMeasure
                    visible: false
                    text: root.bubbleHeading
                    font.pixelSize: root.bubbleHeadingSize
                    font.weight: root.bubbleHeadingWeight
                }

                Column {
                    width: parent.width
                    spacing: 5
                    visible: root.hasChannels

                    Repeater {
                        model: root.channels

                        Row {
                            width: bubbleContent.width
                            spacing: 7

                            Rectangle {
                                width: 22
                                height: width
                                radius: width / 2
                                color: root.rowIconSurface

                                AppIcon {
                                    anchors.centerIn: parent
                                    width: 16
                                    height: width
                                    source: modelData ? root._iconSource(modelData.channel) : ""
                                    sourceSize: Qt.size(width, height)
                                }

                                Rectangle {
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    width: 8
                                    height: width
                                    radius: width / 2
                                    color: modelData ? root._iconAccent(modelData.channel, modelData.state) : "transparent"
                                    border.width: 1
                                    border.color: gatewayDetailBubble.color
                                }
                            }

                            Column {
                                width: parent.width - 26
                                spacing: 2

                                Row {
                                    width: parent.width
                                    spacing: 6

                                    Text {
                                        text: root._channelLabel(modelData.channel)
                                        color: textPrimary
                                        font.pixelSize: typeCaption
                                        font.weight: weightMedium
                                    }

                                    Text {
                                        text: root._channelStateText(modelData.state)
                                        color: root._iconAccent(modelData.channel, modelData.state)
                                        font.pixelSize: typeCaption - 1
                                        font.weight: weightMedium
                                        opacity: 0.86
                                    }
                                }

                                Text {
                                    visible: Boolean(modelData.detail)
                                    width: parent.width
                                    text: modelData.detail || ""
                                    color: isDark ? textSecondary : "#7A5F52"
                                    font.pixelSize: typeCaption - 1
                                    font.weight: weightMedium
                                    wrapMode: Text.WordWrap
                                    textFormat: Text.PlainText
                                    opacity: 0.9
                                }
                            }
                        }
                    }
                }
            }
        }

        MouseArea {
            id: bubbleHover
            anchors.fill: parent
            anchors.leftMargin: -10
            anchors.topMargin: -8
            hoverEnabled: true
            acceptedButtons: Qt.NoButton
        }
    }
}
