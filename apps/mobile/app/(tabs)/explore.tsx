import React, { useMemo } from 'react';
import { FlatList, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { type MobileEventCategory } from '@/src/gateway/events';
import { useGateway } from '@/src/gateway/state';
import { useI18n } from '@/src/i18n/i18n';

const EVENT_CATEGORIES: MobileEventCategory[] = ['message', 'task', 'memory', 'audit', 'other'];

const CATEGORY_KEY_MAP: Record<MobileEventCategory, string> = {
  message: 'events.message',
  task: 'events.task',
  memory: 'events.memory',
  audit: 'events.audit',
  other: 'events.other',
};

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null;
}

function getType(e: unknown): string | null {
  return isObject(e) && typeof e.type === 'string' ? e.type : null;
}

function getPayload(e: unknown): unknown {
  return isObject(e) ? e.payload : null;
}

export default function SessionsScreen() {
  const { t } = useI18n();
  const gw = useGateway();

  const sessions = useMemo(() => {
    // sessions.list events payload: { sessions: [...] }
    const last = [...gw.events].reverse().find((e) => getType(e) === 'sessions.list');
    const payload = getPayload(last);
    if (!isObject(payload)) return [];
    const raw = payload.sessions;
    return Array.isArray(raw) ? raw : [];
  }, [gw.events]);

  const quickActions: { label: string; onPress: () => void; dark?: boolean }[] = [
    { label: t('sessions.fetchTasks'), onPress: gw.listTasks },
    { label: t('sessions.fetchDimsums'), onPress: gw.listDimsums },
    { label: t('sessions.fetchMemories'), onPress: gw.listMemories },
    { label: 'Fetch All', onPress: gw.runTroubleshootActions, dark: true },
  ];

  return (
    <ThemedView style={styles.container}>
      <Animated.View entering={FadeInDown.springify().damping(16)} style={styles.headerCard}>
        <View style={styles.header}>
          <ThemedText type="title">{t('sessions.title')}</ThemedText>
          <Pressable
            style={({ pressed }) => [styles.pill, pressed ? styles.pressed : null]}
            onPress={gw.listSessions}>
            <ThemedText>{t('common.refresh')}</ThemedText>
          </Pressable>
        </View>
        <View style={styles.actions}>
          {quickActions.map((action) => (
            <Pressable
              key={action.label}
              style={({ pressed }) => [action.dark ? styles.pillDark : styles.pill, pressed ? styles.pressed : null]}
              onPress={action.onPress}>
              <ThemedText style={action.dark ? styles.pillDarkText : undefined}>{action.label}</ThemedText>
            </Pressable>
          ))}
        </View>
      </Animated.View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.actions}>
        {EVENT_CATEGORIES.map((item) => {
          const label = t(CATEGORY_KEY_MAP[item]);
          const selected = item === gw.selectedCategory;
          return (
            <Pressable
              key={item}
              style={({ pressed }) => [styles.filterChip, selected ? styles.filterChipActive : null, pressed ? styles.pressed : null]}
              onPress={() => gw.setSelectedCategory(item)}>
              <ThemedText style={selected ? styles.filterTextActive : undefined}>{label}</ThemedText>
            </Pressable>
          );
        })}
      </ScrollView>

      <FlatList
        data={sessions}
        keyExtractor={(item, idx) => String(item?.sessionId ?? idx)}
        renderItem={({ item }) => {
          return (
            <View style={styles.rowCard}>
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
    paddingHorizontal: 16,
    paddingTop: 10,
    gap: 10,
  },
  headerCard: {
    borderRadius: 18,
    padding: 12,
    backgroundColor: '#d9f99d',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  rowCard: {
    marginTop: 8,
    borderRadius: 14,
    padding: 12,
    backgroundColor: '#ecfccb',
    gap: 4,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  pill: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#ecfccb',
  },
  pillDark: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#365314',
  },
  pillDarkText: {
    color: '#f7fee7',
  },
  filterChip: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#ecfccb',
  },
  filterChipActive: {
    backgroundColor: '#365314',
  },
  filterTextActive: {
    color: '#f7fee7',
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.985 }],
  },
});
