import { Tabs } from 'expo-router';
import React from 'react';

import { HapticTab } from '@/components/haptic-tab';
import { IconSymbol } from '@/components/ui/icon-symbol';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { useI18n } from '@/src/i18n/i18n';

const TAB_BAR_HEIGHT = 64;
const TAB_ICON_SIZE = 28;

const TAB_SCREENS = [
  { name: 'index', titleKey: 'nav.connect', icon: 'house.fill' },
  { name: 'explore', titleKey: 'nav.sessions', icon: 'list.bullet' },
  { name: 'chat', titleKey: 'nav.chat', icon: 'message.fill' },
  { name: 'settings', titleKey: 'nav.settings', icon: 'gearshape.fill' },
] as const;

function getTabBarBackground(colorScheme: 'light' | 'dark' | null | undefined): string {
  return colorScheme === 'dark' ? '#111827' : '#e2e8f0';
}

export default function TabLayout() {
  const colorScheme = useColorScheme();
  const { t } = useI18n();
  const colors = Colors[colorScheme ?? 'light'];

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.tint,
        tabBarInactiveTintColor: colors.tabIconDefault,
        tabBarStyle: {
          height: TAB_BAR_HEIGHT,
          borderTopWidth: 0,
          backgroundColor: getTabBarBackground(colorScheme),
        },
        tabBarItemStyle: {
          paddingTop: 6,
        },
        headerShown: false,
        tabBarButton: HapticTab,
      }}>
      {TAB_SCREENS.map((screen) => (
        <Tabs.Screen
          key={screen.name}
          name={screen.name}
          options={{
            title: t(screen.titleKey),
            tabBarIcon: ({ color }) => <IconSymbol size={TAB_ICON_SIZE} name={screen.icon} color={color} />,
          }}
        />
      ))}
    </Tabs>
  );
}
