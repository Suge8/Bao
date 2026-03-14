import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    property string channel: "other"
    property bool expanded: false
    property int itemCount: 0
    property int unreadCount: 0
    property bool groupHasRunning: false
    property string iconSource: ""
    property string chevronObjectName: ""
    property string unreadBadgeObjectName: ""
    property string unreadTextObjectName: ""
    readonly property color surfaceColor: headerArea.pressed
                                         ? sidebarGroupExpandedBg
                                         : (headerArea.containsMouse
                                            ? sidebarGroupHoverBg
                                            : (root.expanded ? sidebarGroupExpandedBg : sidebarGroupBg))
    signal clicked()

    radius: 14
    color: root.surfaceColor
    border.width: 0
    scale: headerArea.pressed ? 0.992 : 1.0

    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

    RowLayout {
        anchors { fill: parent; leftMargin: 10; rightMargin: 8 }
        spacing: 7

        Item {
            Layout.preferredWidth: 20
            Layout.preferredHeight: 20

            AppIcon {
                width: 16
                height: 16
                anchors.centerIn: parent
                source: root.iconSource
                sourceSize: Qt.size(16, 16)
                opacity: root.expanded ? 1.0 : 0.92
            }
        }

        Text {
            text: strings["channel_" + (root.channel || "other")] || root.channel || "other"
            color: textPrimary
            font.pixelSize: typeLabel + 1
            font.weight: weightDemiBold
            font.letterSpacing: 0.2
            textFormat: Text.PlainText
            Layout.fillWidth: true
            verticalAlignment: Text.AlignVCenter
            opacity: root.expanded ? 0.99 : 0.94
        }

        RowLayout {
            Layout.alignment: Qt.AlignVCenter
            spacing: 4

            Rectangle {
                id: groupRunningDot
                visible: root.groupHasRunning
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: 8
                Layout.preferredHeight: 8
                radius: 4
                color: statusSuccess
                border.width: 1
                border.color: isDark ? "#CCFFFFFF" : "#F7FFFB"
                opacity: 0.6
                scale: 0.92

                SequentialAnimation on opacity {
                    running: groupRunningDot.visible
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.42; to: 0.98; duration: 900; easing.type: Easing.InOutQuad }
                    NumberAnimation { from: 0.98; to: 0.42; duration: 900; easing.type: Easing.InOutQuad }
                }

                SequentialAnimation on scale {
                    running: groupRunningDot.visible
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.86; to: 1.12; duration: 900; easing.type: Easing.InOutQuad }
                    NumberAnimation { from: 1.12; to: 0.86; duration: 900; easing.type: Easing.InOutQuad }
                }
            }

            UnreadBadge {
                badgeObjectName: root.unreadBadgeObjectName
                textObjectName: root.unreadTextObjectName
                Layout.alignment: Qt.AlignVCenter
                active: root.unreadCount > 0
                count: root.unreadCount
                mode: "count"
                fillColor: sessionUnreadDot
                textColor: "#FFFFFFFF"
                borderColor: isDark ? "#26FFFFFF" : "#22FFFFFF"
                visualScale: 1.0
            }

            Rectangle {
                visible: root.itemCount > 0
                Layout.preferredWidth: countText.implicitWidth + 12
                Layout.preferredHeight: 22
                radius: 11
                color: sidebarGroupCountBg
                border.width: 1
                border.color: sidebarGroupChevronBorder
                opacity: root.unreadCount > 0 ? 0.66 : 0.82

                Text {
                    id: countText
                    anchors.centerIn: parent
                    text: root.itemCount
                    color: sidebarGroupCountText
                    font.pixelSize: typeCaption
                    font.weight: weightDemiBold
                    opacity: root.unreadCount > 0 ? 0.8 : 0.92
                }
            }
        }

        Rectangle {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            radius: 11
            color: sidebarGroupChevronBg
            border.width: 1
            border.color: sidebarGroupChevronBorder

            AppIcon {
                objectName: root.chevronObjectName
                anchors.centerIn: parent
                width: 12
                height: 12
                source: themedIconSource("sidebar-chevron")
                sourceSize: Qt.size(12, 12)
                rotation: root.expanded ? 90 : 0
                opacity: headerArea.containsMouse ? 1.0 : 0.86

                Behavior on rotation { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
                Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
            }
        }
    }

    MouseArea {
        id: headerArea
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        preventStealing: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
