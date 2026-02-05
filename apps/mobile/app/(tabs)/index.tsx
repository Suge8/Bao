import React, { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { useGateway } from '@/src/gateway/state';
import { useI18n } from '@/src/i18n/i18n';

export default function HomeScreen() {
  const { t } = useI18n();
  const gw = useGateway();
  const [url, setUrl] = useState(gw.url);
  const [token, setToken] = useState(gw.token);

  return (
    <ThemedView style={styles.container}>
      <ThemedText type="title">{t('connect.title')}</ThemedText>

      <View style={styles.field}>
        <ThemedText type="subtitle">{t('connect.url')}</ThemedText>
        <TextInput
          style={styles.input}
          autoCapitalize="none"
          autoCorrect={false}
          value={url}
          onChangeText={setUrl}
          placeholder="ws://127.0.0.1:3901/ws"
        />
      </View>

      <View style={styles.field}>
        <ThemedText type="subtitle">{t('connect.token')}</ThemedText>
        <TextInput
          style={styles.input}
          autoCapitalize="none"
          autoCorrect={false}
          value={token}
          onChangeText={setToken}
          placeholder="..."
        />
      </View>

      <View style={styles.actions}>
        <ThemedText
          type="link"
          onPress={() => {
            gw.connect({ url, token }).catch(() => {});
          }}>
          {t('connect.connect')} ({gw.connected ? t('common.on') : t('common.off')})
        </ThemedText>
        <ThemedText
          type="link"
          onPress={() => {
            gw.disconnect();
          }}>
          {t('common.disconnect')}
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
  field: {
    gap: 6,
  },
  input: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: '#f1f5f9',
  },
  actions: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 8,
  },
});
