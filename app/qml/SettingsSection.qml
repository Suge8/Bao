import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    property string title: ""
    default property alias content: contentArea.data

    Layout.fillWidth: true
    implicitHeight: titleText.implicitHeight + contentArea.implicitHeight + 52
    radius: radiusLg
    color: bgCard

    border.color: borderSubtle
    border.width: 1

    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

    ColumnLayout {
        anchors { fill: parent; margins: 24 }
        spacing: 20

        Text {
            id: titleText
            text: root.title
            color: textPrimary
            font.pixelSize: 15
            font.weight: Font.DemiBold
            font.letterSpacing: 0.3
        }

        Item {
            id: contentArea
            Layout.fillWidth: true
            implicitHeight: childrenRect.height
        }
    }
}
