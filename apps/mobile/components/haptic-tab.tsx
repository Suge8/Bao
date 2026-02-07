import { BottomTabBarButtonProps } from '@react-navigation/bottom-tabs';
import { PlatformPressable } from '@react-navigation/elements';
import * as Haptics from 'expo-haptics';

const IS_IOS = process.env.EXPO_OS === 'ios';

function triggerTabHaptic() {
  if (!IS_IOS) return;
  // Add a soft haptic feedback when pressing down on the tabs.
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
}

export function HapticTab(props: BottomTabBarButtonProps) {
  return (
    <PlatformPressable
      {...props}
      onPressIn={(ev) => {
        triggerTabHaptic();
        props.onPressIn?.(ev);
      }}
    />
  );
}
