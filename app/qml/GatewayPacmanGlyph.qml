import QtQuick 2.15

Item {
    id: root

    property real mouth: 0.2
    property real phase: 0.0
    property color fillColor: "#F7FFF9"
    property color eyeColor: "#10A356"

    readonly property real stageExtraWidth: 4
    readonly property real glyphSize: 23
    readonly property real glyphLeftMargin: 4
    readonly property real glyphRadius: 10.2
    readonly property real eyeOffsetX: 1.8
    readonly property real eyeOffsetY: -3.6
    readonly property real eyeRadius: 1.35
    readonly property real dotSize: 3.5
    readonly property real dotStartX: 19.6
    readonly property real dotTravel: 8.8
    readonly property real dotHideX: 20.8

    Item {
        id: stage
        width: parent.width + root.stageExtraWidth
        height: parent.height
        anchors.centerIn: parent

        Canvas {
            id: pacmanGlyph
            width: root.glyphSize
            height: root.glyphSize
            anchors.left: parent.left
            anchors.leftMargin: root.glyphLeftMargin
            anchors.verticalCenter: parent.verticalCenter
            antialiasing: true

            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()

                var centerX = width / 2
                var centerY = height / 2
                var startAngle = root.mouth * Math.PI
                var endAngle = (2 - root.mouth) * Math.PI

                ctx.beginPath()
                ctx.moveTo(centerX, centerY)
                ctx.arc(centerX, centerY, root.glyphRadius, startAngle, endAngle, false)
                ctx.closePath()
                ctx.fillStyle = root.fillColor
                ctx.fill()

                ctx.beginPath()
                ctx.arc(
                    centerX + root.eyeOffsetX,
                    centerY + root.eyeOffsetY,
                    root.eyeRadius,
                    0,
                    Math.PI * 2,
                    false
                )
                ctx.fillStyle = root.eyeColor
                ctx.fill()
            }
        }

        Repeater {
            model: 1

            Rectangle {
                required property int index
                width: root.dotSize
                height: root.dotSize
                radius: width / 2
                color: root.fillColor
                anchors.verticalCenter: pacmanGlyph.verticalCenter
                property real offset: (1.0 - root.phase)
                x: root.dotStartX + offset * root.dotTravel
                opacity: x <= root.dotHideX ? 0.0 : 0.98
            }
        }
    }

    onMouthChanged: pacmanGlyph.requestPaint()
    Component.onCompleted: pacmanGlyph.requestPaint()
}
