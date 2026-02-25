import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    property string currentView: "chat"
    signal viewRequested(string view)
    signal newSessionRequested()
    signal sessionSelected(string key)
    signal sessionDeleteRequested(string key)

    color: "transparent"

    Rectangle {
        anchors.fill: parent
        radius: 20
        color: bgSidebar
        antialiasing: true

        // Square the top and right edges; keep only the bottom-left corner rounded.
        Rectangle {
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: parent.radius
            color: parent.color
        }
        Rectangle {
            anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
            width: parent.radius
            color: parent.color
        }
    }

    // No divider lines; use spacing/layering instead.

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Top nav buttons
        Item {
            Layout.fillWidth: true
            height: 108

            ColumnLayout {
                anchors { top: parent.top; left: parent.left; right: parent.right; topMargin: 16 }
                spacing: 4

                Repeater {
                    model: [
                        { icon: "💬", view: "chat"     },
                        { icon: "⚙️",  view: "settings" }
                    ]
                    delegate: NavButton {
                        Layout.fillWidth: true
                        Layout.leftMargin: 10
                        Layout.rightMargin: 10
                        icon: modelData.icon
                        label: modelData.view === "chat" ? strings.nav_chat : strings.nav_settings
                        active: root.currentView === modelData.view
                        onClicked: {
                            root.currentView = modelData.view
                            root.viewRequested(modelData.view)
                        }
                    }
                }
            }
        }

        // Session list header
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.rightMargin: 12
            Layout.topMargin: 14
            Layout.bottomMargin: 6
            spacing: 0

            Text {
                text: strings.sidebar_sessions
                color: textTertiary
                font.pixelSize: 11
                font.weight: Font.DemiBold
                font.letterSpacing: 0.8
                textFormat: Text.PlainText
                Layout.fillWidth: true
            }

            // New session button
            Rectangle {
                width: 28; height: 28; radius: radiusSm
                color: newSessionHover.containsMouse
                       ? (isDark ? "#10FFFFFF" : "#08000000")
                       : "transparent"
                Behavior on color { ColorAnimation { duration: 120 } }

                Text {
                    anchors.centerIn: parent
                    text: "+"
                    color: textSecondary
                    font.pixelSize: 18
                    font.weight: Font.Medium
                }

                MouseArea {
                    id: newSessionHover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.newSessionRequested()
                }
            }
        }

        // Session list
        ListView {
            id: sessionList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: sessionService ? sessionService.sessionsModel : null
            spacing: 2

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: SessionItem {
                width: sessionList.width - 20
                x: 10
                sessionKey: model.key ?? ""
                sessionTitle: model.title ?? model.key ?? ""
                isActive: model.isActive ?? false
                onSelected: root.sessionSelected(sessionKey)
                onDeleteRequested: root.sessionDeleteRequested(sessionKey)
            }

            // Empty state
            Text {
                anchors.centerIn: parent
                visible: sessionList.count === 0
                text: strings.sidebar_no_sessions
                color: textTertiary
                font.pixelSize: 13
            }
        }
    }
}
