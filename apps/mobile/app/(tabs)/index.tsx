import React, { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { type MobileEventCategory } from '@/src/gateway/events';
import { useGateway } from '@/src/gateway/state';
import { useI18n } from '@/src/i18n/i18n';

export default function HomeScreen() {
  const { t } = useI18n();
  const gw = useGateway();
  const [url, setUrl] = useState(gw.url);
  const [token, setToken] = useState(gw.token);

  const categoryKeyMap: Record<MobileEventCategory, string> = {
    message: 'events.message',
    task: 'events.task',
    memory: 'events.memory',
    audit: 'events.audit',
    other: 'events.other',
  };

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

      <View style={styles.statusCard}>
        <ThemedText type="subtitle">{t('connect.connected')}</ThemedText>
        <ThemedText>{gw.connected ? t('common.on') : t('common.off')}</ThemedText>
        <ThemedText>
          {t('connect.replayState')}: {gw.replayActive ? t('connect.replayOn') : t('connect.replayOff')}
        </ThemedText>
        <ThemedText>{t('connect.lastEvent')}: {gw.lastEventId ?? '-'}</ThemedText>
        <ThemedText>{t('connect.events')}: {gw.events.length}</ThemedText>
        <ThemedText style={styles.eventsTitle}>{t('connect.eventsByType')}</ThemedText>
        <ThemedText>{t('events.message')}: {gw.eventCounts.message}</ThemedText>
        <ThemedText>{t('events.task')}: {gw.eventCounts.task}</ThemedText>
        <ThemedText>{t('events.memory')}: {gw.eventCounts.memory}</ThemedText>
        <ThemedText>{t('events.audit')}: {gw.eventCounts.audit}</ThemedText>
        <ThemedText>{t('events.other')}: {gw.eventCounts.other}</ThemedText>
        <View style={styles.actionsWrap}>
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
        <ThemedText style={styles.hint}>{t('connect.replayHint')}</ThemedText>
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
  statusCard: {
    marginTop: 6,
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#e2e8f0',
    gap: 4,
  },
  hint: {
    marginTop: 4,
    opacity: 0.75,
  },
  eventsTitle: {
    marginTop: 6,
  },
  actionsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginTop: 6,
  },
});
