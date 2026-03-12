import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property bool active: false
    property string sectionTitle: ""
    property string sectionCaption: ""
    property string sectionKicker: ""
    property string accentHex: "#D89A3C"
    property real revealOpacity: 1.0
    property real revealScale: 1.0
    property real revealShift: 0.0

    function playReveal() {
        revealOpacity = motionPageRevealStartOpacity
        revealScale = motionPageRevealStartScale
        revealShift = motionPageShiftSubtle
        revealAnimation.restart()
    }

    onActiveChanged: {
        if (active)
            playReveal()
    }

    Item {
        anchors.fill: parent
        opacity: root.revealOpacity
        scale: root.revealScale
        transform: Translate { x: root.revealShift }

        Rectangle {
            anchors.fill: parent
            anchors.margins: 16
            radius: 30
            color: bgCard
            border.width: 1
            border.color: isDark ? "#20FFFFFF" : "#146E4B2A"

            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: isDark ? "#08FFFFFF" : "#0DFFF7EF"
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 28
                spacing: 22

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6

                Text {
                    text: root.sectionKicker
                    color: textSecondary
                    font.pixelSize: typeMeta
                    font.weight: weightBold
                    font.letterSpacing: letterWide
                }

                Text {
                    text: root.sectionTitle
                    color: textPrimary
                    font.pixelSize: typeTitle
                    font.weight: weightBold
                    font.letterSpacing: letterTight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.sectionCaption
                    color: textSecondary
                    font.pixelSize: typeBody
                    wrapMode: Text.WordWrap
                    lineHeight: 1.2
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 18

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 24
                    color: isDark ? "#15100D" : "#FAF4EE"
                    border.width: 1
                    border.color: isDark ? "#18FFFFFF" : "#12000000"

                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 22
                        spacing: 14

                        Rectangle {
                            width: 42
                            height: 4
                            radius: 2
                            color: root.accentHex
                            opacity: 0.9
                        }

                        Repeater {
                            model: 3

                            delegate: Rectangle {
                                width: parent.width
                                height: 72
                                radius: 18
                                color: isDark ? "#1B1512" : "#FFFDFB"
                                border.width: 1
                                border.color: isDark ? "#14FFFFFF" : "#10000000"

                                Column {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.margins: 16
                                    spacing: 8

                                    Rectangle {
                                        width: (index === 0 ? 132 : (index === 1 ? 110 : 154))
                                        height: 10
                                        radius: 5
                                        color: isDark ? "#2B211B" : "#E9DCCF"
                                    }

                                    Rectangle {
                                        width: (index === 2 ? 184 : 156)
                                        height: 8
                                        radius: 4
                                        color: isDark ? "#211915" : "#F0E6DC"
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 240
                    Layout.fillHeight: true
                    radius: 24
                    color: isDark ? "#16110E" : "#FBF7F2"
                    border.width: 1
                    border.color: isDark ? "#18FFFFFF" : "#12000000"

                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 20
                        spacing: 12

                        Rectangle {
                            width: 92
                            height: 10
                            radius: 5
                            color: root.accentHex
                            opacity: 0.5
                        }

                        Repeater {
                            model: 4

                            delegate: Rectangle {
                                width: parent.width
                                height: 46
                                radius: 14
                                color: index === 0
                                       ? (isDark ? "#201712" : "#F5E8DB")
                                       : (isDark ? "#1A1411" : "#FFFDFC")
                                border.width: 1
                                border.color: isDark ? "#12FFFFFF" : "#0E000000"
                            }
                        }
                    }
                }
            }
            }
        }
    }

    SequentialAnimation {
        id: revealAnimation

        ParallelAnimation {
            NumberAnimation { target: root; property: "revealOpacity"; to: 1.0; duration: motionUi; easing.type: easeStandard }
            NumberAnimation { target: root; property: "revealScale"; to: 1.0; duration: motionPanel; easing.type: easeEmphasis }
            NumberAnimation { target: root; property: "revealShift"; to: 0.0; duration: motionPanel; easing.type: easeEmphasis }
        }
    }
}
