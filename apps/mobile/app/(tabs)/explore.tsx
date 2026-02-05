import React, { useMemo } from 'react';
import { FlatList, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { useGateway } from '@/src/gateway/state';
import { useI18n } from '@/src/i18n/i18n';

export default function SessionsScreen() {
  const { t } = useI18n();
  const gw = useGateway();

  const sessions = useMemo(() => {
    const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;
    const getType = (e: unknown): string | null => (isObject(e) && typeof e.type === 'string' ? e.type : null);
    const getPayload = (e: unknown): unknown => (isObject(e) ? e.payload : null);

    // sessions.list events payload: { sessions: [...] }
    const last = [...gw.events].reverse().find((e) => getType(e) === 'sessions.list');
    const payload = getPayload(last);
    if (!isObject(payload)) return [];
    const raw = payload.sessions;
    return Array.isArray(raw) ? raw : [];
  }, [gw.events]);

  return (
    <ThemedView style={styles.container}>
      <View style={styles.header}>
        <ThemedText type="title">{t('sessions.title')}</ThemedText>
        <ThemedText type="link" onPress={() => gw.listSessions()}>{t('common.refresh')}</ThemedText>
      </View>

      <FlatList
        data={sessions}
        keyExtractor={(item, idx) => String(item?.sessionId ?? idx)}
        renderItem={({ item }) => {
          return (
            <View style={styles.row}>
              <ThemedText type="defaultSemiBold">{String(item?.sessionId ?? '')}</ThemedText>
              <ThemedText>{String(item?.title ?? '')}</ThemedText>
            </View>
          );
        }}
        ListEmptyComponent={<ThemedText>{t('common.empty')}</ThemedText>}
      />
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
    gap: 12,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  row: {
    paddingVertical: 10,
    gap: 4,
  },
});
