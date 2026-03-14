import QtQuick 2.15

Item {
    id: root

    property string fileName: ""
    property string fileSizeLabel: ""
    property string previewUrl: ""
    property bool isImage: false
    property string extensionLabel: "FILE"
    property bool removable: false
    property bool openOnClick: false
    property var removeAction: null

    width: isImage ? 72 : 164
    height: 56

    Rectangle {
        anchors.fill: parent
        radius: 18
        color: isImage ? (isDark ? "#241A12" : "#FFF9F4") : (isDark ? "#1D150F" : "#FFFCF9")
        border.width: 1
        border.color: chipHover.containsMouse ? accent : borderSubtle
        scale: chipHover.containsMouse ? 1.018 : 1.0
        Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
        Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            border.width: 1
            border.color: isDark ? "#18FFFFFF" : "#36FFFFFF"
            opacity: 0.9
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: isImage ? 26 : 20
            radius: parent.radius
            gradient: Gradient {
                GradientStop { position: 0.0; color: isImage ? "#30FFFFFF" : (isDark ? "#16FFFFFF" : "#26FFFFFF") }
                GradientStop { position: 1.0; color: "#00FFFFFF" }
            }
        }

        Item {
            anchors.fill: parent
            anchors.margins: 4
            visible: isImage

            Rectangle {
                anchors.fill: parent
                radius: 14
                color: bgInput
                clip: true

                Image {
                    anchors.fill: parent
                    source: previewUrl
                    fillMode: Image.PreserveAspectCrop
                    sourceSize: Qt.size(width * 2, height * 2)
                    asynchronous: true
                    smooth: true
                    mipmap: true
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 22
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#00000000" }
                        GradientStop { position: 1.0; color: "#99000000" }
                    }
                }

                Rectangle {
                    width: 26
                    height: 16
                    radius: 8
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 7
                    anchors.bottomMargin: 7
                    color: "#B8130F0B"
                    border.width: 1
                    border.color: "#33FFFFFF"

                    Text {
                        anchors.centerIn: parent
                        text: extensionLabel
                        color: "#FFF9F3"
                        font.pixelSize: typeCaption - 2
                        font.weight: weightDemiBold
                    }
                }
            }
        }

        Row {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: removable ? 34 : 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            visible: !isImage

            Rectangle {
                width: 34
                height: 34
                radius: 11
                anchors.verticalCenter: parent.verticalCenter
                color: isDark ? "#2EF38F1A" : "#1CE68A18"
                border.width: 1
                border.color: isDark ? "#2CFFC36B" : "#2AF0AF47"

                Text {
                    anchors.centerIn: parent
                    text: extensionLabel
                    color: accent
                    font.pixelSize: typeCaption - 1
                    font.weight: weightDemiBold
                }
            }

            Column {
                width: parent.width - 44
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1

                Text {
                    width: parent.width
                    text: fileName
                    color: textPrimary
                    font.pixelSize: typeMeta + 1
                    font.weight: weightDemiBold
                    elide: Text.ElideMiddle
                }

                Text {
                    width: parent.width
                    text: fileSizeLabel
                    color: textTertiary
                    font.pixelSize: typeCaption
                    elide: Text.ElideRight
                }
            }
        }

        Rectangle {
            visible: removable
            width: 22
            height: 22
            radius: 11
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.rightMargin: 6
            anchors.topMargin: 6
            color: removeArea.containsMouse ? accent : (isDark ? "#F21B120D" : "#F8FFFFFF")
            border.width: 1
            border.color: removeArea.containsMouse ? accent : borderSubtle
            scale: removeArea.containsMouse ? 1.04 : 1.0
            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
            Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
            Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

            Image {
                anchors.centerIn: parent
                source: "../resources/icons/sidebar-close.svg"
                width: 10
                height: 10
                sourceSize: Qt.size(10, 10)
                opacity: 0.9
            }

            MouseArea {
                id: removeArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: if (root.removeAction) root.removeAction()
            }
        }

        MouseArea {
            id: chipHover
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: root.openOnClick ? Qt.LeftButton : Qt.NoButton
            cursorShape: root.openOnClick ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: {
                if (!root.openOnClick || !root.previewUrl)
                    return
                Qt.openUrlExternally(root.previewUrl)
            }
        }
    }
}
