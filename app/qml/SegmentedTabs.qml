import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root

    property var items: []
    property string currentValue: ""
    property color accentColor: typeof accent !== "undefined" ? accent : "#FFA11A"
    property color trackColor: typeof isDark !== "undefined" && isDark ? "#12FFFFFF" : "#08000000"
    property color outlineColor: typeof borderSubtle !== "undefined" ? borderSubtle : "#14000000"
    property color textColor: typeof textSecondary !== "undefined" ? textSecondary : "#6B7280"
    property bool fillSegments: false
    property real preferredTrackWidth: 0
    property int tabHeight: 46
    property int trackPadding: 6
    property int tabSpacing: 6
    property int iconSize: 14
    property int labelPixelSize: typeof typeLabel !== "undefined" ? typeLabel : 14
    property int labelWeight: Font.DemiBold
    property int motionDuration: typeof motionFast !== "undefined" ? motionFast : 180
    property int emphasisEasing: typeof easeEmphasis !== "undefined" ? easeEmphasis : Easing.OutBack
    property int standardEasing: typeof easeStandard !== "undefined" ? easeStandard : Easing.OutCubic
    property int tabItemRevision: 0
    signal selected(string value)

    readonly property int tabCount: items ? items.length : 0
    readonly property real segmentWidth: root.fillSegments && root.tabCount > 0
        ? Math.max(0, (width - root.trackPadding * 2 - root.tabSpacing * (root.tabCount - 1)) / root.tabCount)
        : 0
    readonly property int selectedIndex: {
        for (var index = 0; index < tabCount; index += 1) {
            if (String((items[index] || {}).value || "") === currentValue)
                return index
        }
        return 0
    }

    implicitWidth: preferredTrackWidth > 0 ? preferredTrackWidth : tabRow.implicitWidth + trackPadding * 2
    implicitHeight: tabHeight

    Rectangle {
        id: tabTrack
        anchors.fill: parent
        radius: height / 2
        color: root.trackColor
        border.width: 1
        border.color: root.outlineColor
        readonly property Item selectedTabItem: {
            root.tabItemRevision
            if (root.selectedIndex < 0 || root.selectedIndex >= tabRepeater.count)
                return null
            return tabRepeater.itemAt(root.selectedIndex)
        }

        Rectangle {
            id: tabHighlight
            objectName: "segmentedTabsHighlight"
            y: root.trackPadding
            height: parent.height - root.trackPadding * 2
            radius: height / 2
            color: root.accentColor
            visible: root.tabCount > 0
            x: root.trackPadding + (tabTrack.selectedTabItem ? tabTrack.selectedTabItem.x : 0)
            width: tabTrack.selectedTabItem
                ? tabTrack.selectedTabItem.width
                : root.segmentWidth

            Behavior on x { NumberAnimation { duration: 220; easing.type: root.emphasisEasing } }
            Behavior on width { NumberAnimation { duration: 220; easing.type: root.standardEasing } }
        }

        Row {
            id: tabRow
            x: root.trackPadding
            y: root.trackPadding
            height: parent.height - root.trackPadding * 2
            spacing: root.tabSpacing

            Repeater {
                id: tabRepeater
                model: root.items
                onItemAdded: function() { root.tabItemRevision += 1 }
                onItemRemoved: function() { root.tabItemRevision += 1 }

                delegate: Rectangle {
                    required property int index
                    required property var modelData

                    readonly property real intrinsicWidth: tabContent.implicitWidth + 22
                    implicitWidth: intrinsicWidth
                    width: root.fillSegments ? root.segmentWidth : intrinsicWidth
                    height: tabRow.height
                    radius: 17
                    color: tabMouse.containsMouse && root.selectedIndex !== index
                        ? (typeof isDark !== "undefined" && isDark ? "#10FFFFFF" : "#08000000")
                        : "transparent"

                    Behavior on color { ColorAnimation { duration: root.motionDuration; easing.type: root.standardEasing } }

                    Row {
                        id: tabContent
                        anchors.centerIn: parent
                        spacing: 6

                        AppIcon {
                            visible: String(modelData.icon || "") !== ""
                            width: root.iconSize
                            height: root.iconSize
                            anchors.verticalCenter: parent.verticalCenter
                            source: String(modelData.icon || "")
                            sourceSize: Qt.size(width, height)
                            opacity: root.selectedIndex === index ? 1.0 : 0.72
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: String(modelData.label || "")
                            color: root.selectedIndex === index ? "#FFFFFFFF" : root.textColor
                            font.pixelSize: root.labelPixelSize
                            font.weight: root.labelWeight
                        }
                    }

                    MouseArea {
                        id: tabMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: modelData.enabled !== false
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: root.selected(String(modelData.value || ""))
                    }
                }
            }
        }
    }
}
