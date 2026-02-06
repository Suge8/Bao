import React, { useMemo, useState } from 'react';
import { FlatList, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { useGateway } from '@/src/gateway/state';
import { classifyEventCategory, getEventType, type MobileEventCategory } from '@/src/gateway/events';
import { useI18n } from '@/src/i18n/i18n';

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null;
}

export default function ChatScreen() {
  const { t } = useI18n();
  const gw = useGateway();
  const [sessionId, setSessionId] = useState('s1');
  const [text, setText] = useState('');
  const category = gw.selectedCategory;

  const categoryKeyMap: Record<MobileEventCategory, string> = {
    message: 'events.message',
    task: 'events.task',
    memory: 'events.memory',
    audit: 'events.audit',
    other: 'events.other',
  };

  const messageEvents = useMemo(() => {
    return [...gw.events]
      .reverse()
      .filter((e) => classifyEventCategory(getEventType(e)) === category)
      .slice(0, 100);
  }, [gw.events, category]);

  return (
    <ThemedView style={styles.container}>
      <ThemedText type="title">{t('chat.title')}</ThemedText>

      <View style={styles.field}>
        <ThemedText type="subtitle">{t('chat.sessionId')}</ThemedText>
        <TextInput
          style={styles.input}
          autoCapitalize="none"
          autoCorrect={false}
          value={sessionId}
          onChangeText={setSessionId}
          placeholder={t('chat.sessionIdPlaceholder')}
        />
      </View>

      <View style={styles.field}>
        <ThemedText type="subtitle">{t('chat.message')}</ThemedText>
        <TextInput
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder={t('chat.messagePlaceholder')}
        />
      </View>

      <View style={styles.actions}>
        <ThemedText
          type="link"
          onPress={() => {
            if (!text.trim()) return;
            gw.sendMessage({ sessionId, text });
            setText('');
          }}>
          {t('chat.send')}
        </ThemedText>
      </View>

      <View style={styles.actions}>
        {(['message', 'task', 'memory', 'audit', 'other'] as MobileEventCategory[]).map((item) => {
          const label = t(categoryKeyMap[item]);
          const selected = item === category;
          return (
            <ThemedText key={item} type="link" onPress={() => gw.setSelectedCategory(item)}>
              {selected ? `[${label}]` : label}
            </ThemedText>
          );
        })}
      </View>

      <FlatList
        data={messageEvents}
        keyExtractor={(item, idx) => String((isObject(item) ? item.eventId : undefined) ?? idx)}
        renderItem={({ item }) => {
          const payload = isObject(item) ? item.payload : null;
          const msg = isObject(payload) && typeof payload.text === 'string' ? payload.text : '';
          const sid = isObject(payload) && typeof payload.sessionId === 'string' ? payload.sessionId : '';
          return (
            <View style={styles.row}>
              <ThemedText type="defaultSemiBold">{sid}</ThemedText>
              <ThemedText>{msg}</ThemedText>
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
    marginTop: 4,
  },
  row: {
    paddingVertical: 10,
    gap: 4,
  },
});
