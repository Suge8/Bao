import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';

import { useColorScheme } from '@/hooks/use-color-scheme';
import { I18nProvider } from '@/src/i18n/i18n';
import { GatewayProvider } from '@/src/gateway/state';

export const unstable_settings = {
  anchor: '(tabs)',
};

const MODAL_OPTIONS = { presentation: 'modal' as const, title: 'Modal' };

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? DarkTheme : DefaultTheme;

  return (
    <I18nProvider>
      <GatewayProvider>
        <ThemeProvider value={theme}>
          <Stack>
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            <Stack.Screen name="modal" options={MODAL_OPTIONS} />
          </Stack>
          <StatusBar style="auto" />
        </ThemeProvider>
      </GatewayProvider>
    </I18nProvider>
  );
}
