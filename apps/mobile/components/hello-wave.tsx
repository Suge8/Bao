import Animated from 'react-native-reanimated';

const WAVE_STYLE = {
  fontSize: 28,
  lineHeight: 32,
  marginTop: -6,
  animationName: {
    '50%': { transform: [{ rotate: '25deg' }] },
  },
  animationIterationCount: 4,
  animationDuration: '300ms',
} as const;

export function HelloWave() {
  return (
    <Animated.Text style={WAVE_STYLE}>
      👋
    </Animated.Text>
  );
}
