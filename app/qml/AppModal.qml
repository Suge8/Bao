import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: root

    property string title: ""
    property string closeText: "Close"
    property real maxModalWidth: 720
    property real maxModalHeight: 620
    property bool darkMode: true
    property bool showDefaultCloseAction: true
    property bool bodyScrollable: true
    property int motionFast: 160
    property int motionUi: 220
    property int easeStandard: Easing.OutCubic
    property int easeEmphasis: Easing.OutQuint
    property real radiusLg: 24
    property color bgElevated: darkMode ? "#171210" : "#FFFBF6"
    property color borderDefault: darkMode ? "#2D221C" : "#E8D7C5"
    property color textPrimary: darkMode ? "#FFF8F2" : "#22160E"
    property color textSecondary: darkMode ? "#C7B7A8" : "#69574A"
    property color bgCardHover: darkMode ? "#221815" : "#F4E7D8"
    property color borderSubtle: darkMode ? "#3B2D24" : "#E5D2BD"
    property int typeTitle: 20
    property int typeLabel: 14
    default property alias body: modalBody.data
    property alias footer: customFooterRow.data

    parent: Overlay.overlay
    anchors.centerIn: Overlay.overlay
    width: Math.min((parent ? parent.width : 760) - 48, maxModalWidth)
    height: Math.min((parent ? parent.height : 680) - 48, maxModalHeight)
    padding: 0
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle {
        color: root.darkMode ? "#B3000000" : "#70000000"
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motionUi; easing.type: easeStandard }
            NumberAnimation { property: "scale"; from: 0.96; to: 1.0; duration: motionUi; easing.type: easeEmphasis }
        }
    }

    exit: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motionFast; easing.type: easeStandard }
            NumberAnimation { property: "scale"; from: 1.0; to: 0.98; duration: motionFast; easing.type: easeStandard }
        }
    }

    background: Rectangle {
        radius: radiusLg
        color: bgElevated
        border.width: 1
        border.color: borderDefault
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Text {
                Layout.fillWidth: true
                text: root.title
                color: textPrimary
                font.pixelSize: typeTitle
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }

            IconCircleButton {
                buttonSize: 30
                glyphText: "✕"
                glyphSize: typeLabel
                fillColor: "transparent"
                hoverFillColor: bgCardHover
                outlineColor: borderSubtle
                glyphColor: textSecondary
                onClicked: root.close()
            }
        }

        ScrollView {
            id: modalScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical.policy: root.bodyScrollable ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff

            Column {
                id: modalBody
                width: modalScroll.availableWidth
                spacing: 14
            }
        }

        RowLayout {
            id: footerArea
            visible: root.showDefaultCloseAction || customFooterRow.children.length > 0
            Layout.fillWidth: true
            spacing: 10

            RowLayout {
                id: customFooterRow
                Layout.fillWidth: true
                spacing: 10
            }

            Item {
                Layout.fillWidth: true
                visible: root.showDefaultCloseAction
            }

            PillActionButton {
                visible: root.showDefaultCloseAction
                Layout.alignment: Qt.AlignRight
                text: root.closeText
                minHeight: 34
                horizontalPadding: 24
                onClicked: root.close()
            }
        }
    }
}
