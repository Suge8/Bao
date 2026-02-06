import React, { useMemo } from 'react';
import { FlatList, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { type MobileEventCategory } from '@/src/gateway/events';
import { useGateway } from '@/src/gateway/state';
import { useI18n } from '@/src/i18n/i18n';

export default function SessionsScreen() {
  const { t } = useI18n();
  const gw = useGateway();

  const categoryKeyMap: Record<MobileEventCategory, string> = {
    message: 'events.message',
    task: 'events.task',
    memory: 'events.memory',
    audit: 'events.audit',
    other: 'events.other',
  };

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

      <View style={styles.actions}>
        <ThemedText type="link" onPress={() => gw.listTasks()}>
          {t('sessions.fetchTasks')}
        </ThemedText>
        <ThemedText type="link" onPress={() => gw.listDimsums()}>
          {t('sessions.fetchDimsums')}
        </ThemedText>
        <ThemedText type="link" onPress={() => gw.listMemories()}>
          {t('sessions.fetchMemories')}
        </ThemedText>
      </View>

      <View style={styles.actions}>
        {(['message', 'task', 'memory', 'audit', 'other'] as MobileEventCategory[]).map((item) => {
          const label = t(categoryKeyMap[item]);
          const selected = item === gw.selectedCategory;
          return (
            <ThemedText key={item} type="link" onPress={() => gw.setSelectedCategory(item)}>
              {selected ? `[${label}]` : label}
            </ThemedText>
          );
        })}
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
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 14,
    marginBottom: 4,
  },
});
