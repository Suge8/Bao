import React from 'react';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { useGateway } from '@/src/gateway/state';
import { useI18n } from '@/src/i18n/i18n';

export default function SettingsScreen() {
  const { t, locale, setLocale } = useI18n();
  const gw = useGateway();

  return (
    <ThemedView style={styles.container}>
      <ThemedText type="title">{t('settings.title')}</ThemedText>

      <View style={styles.row}>
        <ThemedText type="subtitle">{t('settings.language')}</ThemedText>
        <View style={styles.actions}>
          <ThemedText type="link" onPress={() => setLocale('zh')}>
            zh {locale === 'zh' ? `(${t('common.on')})` : ''}
          </ThemedText>
          <ThemedText type="link" onPress={() => setLocale('en')}>
            en {locale === 'en' ? `(${t('common.on')})` : ''}
          </ThemedText>
        </View>
      </View>

      <View style={styles.row}>
        <ThemedText type="subtitle">Gateway</ThemedText>
        <ThemedText>{gw.connected ? t('common.on') : t('common.off')}</ThemedText>
      </View>

      <View style={styles.actions}>
        <ThemedText type="link" onPress={() => gw.getSettings()}>
          getSettings
        </ThemedText>
      </View>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
    gap: 12,
  },
  row: {
    gap: 6,
  },
  actions: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 8,
  },
});
