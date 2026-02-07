import React, { useMemo, useState } from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { useGateway } from '@/src/gateway/state';
import { classifyEventCategory, getEventType, type MobileEventCategory } from '@/src/gateway/events';
import { useI18n } from '@/src/i18n/i18n';

const EVENT_CATEGORIES: MobileEventCategory[] = ['message', 'task', 'memory', 'audit', 'other'];
const EVENT_LIMIT = 100;

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

function getMessageRowData(item: unknown) {
  const payload = isObject(item) ? item.payload : null;
  if (!isObject(payload)) {
    return { msg: '', sid: '', role: '' };
  }
  const msg = typeof payload.text === 'string' ? payload.text : '';
  const sid = typeof payload.sessionId === 'string' ? payload.sessionId : '';
  const role = typeof payload.role === 'string' ? payload.role : '';
  return { msg, sid, role };
}

export default function ChatScreen() {
  const { t } = useI18n();
  const gw = useGateway();
  const [sessionId, setSessionId] = useState('default-chat');
  const [text, setText] = useState('');
  const category = gw.selectedCategory;

  const messageEvents = useMemo(() => {
    return [...gw.events]
      .reverse()
      .filter((e) => classifyEventCategory(getEventType(e)) === category)
      .slice(0, EVENT_LIMIT);
  }, [gw.events, category]);

  const handleSend = () => {
    if (!text.trim()) return;
    gw.sendMessage({ sessionId, text });
    setText('');
  };

  return (
    <ThemedView style={styles.container}>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 84 : 0}>
        <Animated.View entering={FadeInDown.springify().damping(16)} style={styles.hero}>
          <ThemedText type="title">{t('chat.title')}</ThemedText>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(50).springify().damping(16)} style={styles.composer}>
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
              style={[styles.input, styles.messageInput]}
              value={text}
              onChangeText={setText}
              placeholder={t('chat.messagePlaceholder')}
              multiline
            />
          </View>

          <Pressable
            style={({ pressed }) => [styles.sendButton, pressed ? styles.buttonPressed : null]}
            onPress={handleSend}>
            <ThemedText style={styles.sendText}>{t('chat.send')}</ThemedText>
          </Pressable>
        </Animated.View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.actions}>
          {EVENT_CATEGORIES.map((item) => {
            const label = t(CATEGORY_KEY_MAP[item]);
            const selected = item === category;
            return (
              <Pressable
                key={item}
                style={({ pressed }) => [styles.chip, selected ? styles.chipActive : null, pressed ? styles.buttonPressed : null]}
                onPress={() => gw.setSelectedCategory(item)}>
                <ThemedText style={selected ? styles.chipTextActive : undefined}>{label}</ThemedText>
              </Pressable>
            );
          })}
        </ScrollView>

        <FlatList
          data={messageEvents}
          keyExtractor={(item, idx) => String((isObject(item) ? item.eventId : undefined) ?? idx)}
          renderItem={({ item }) => {
            const { msg, sid, role } = getMessageRowData(item);
            const isAssistant = role === 'assistant';
            return (
              <View style={[styles.row, isAssistant ? styles.rowAssistant : styles.rowUser]}>
                <ThemedText type="defaultSemiBold">{sid || '-'}</ThemedText>
                <ThemedText>{msg || t('common.empty')}</ThemedText>
              </View>
            );
          }}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={<ThemedText>{t('common.empty')}</ThemedText>}
          keyboardShouldPersistTaps="handled"
        />
      </KeyboardAvoidingView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 16,
  },
  hero: {
    marginTop: 10,
    borderRadius: 18,
    padding: 14,
    backgroundColor: '#fde68a',
  },
  composer: {
    marginTop: 10,
    borderRadius: 18,
    padding: 12,
    backgroundColor: '#fef3c7',
    gap: 10,
  },
  field: {
    gap: 6,
  },
  input: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: '#fffbeb',
  },
  messageInput: {
    minHeight: 60,
    textAlignVertical: 'top',
  },
  actions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
    marginBottom: 8,
    paddingRight: 16,
  },
  chip: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#fef3c7',
  },
  chipActive: {
    backgroundColor: '#92400e',
  },
  chipTextActive: {
    color: '#fffbeb',
  },
  sendButton: {
    minHeight: 40,
    borderRadius: 12,
    backgroundColor: '#92400e',
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendText: {
    color: '#fffbeb',
    fontWeight: '700',
  },
  buttonPressed: {
    opacity: 0.86,
    transform: [{ scale: 0.985 }],
  },
  listContent: {
    gap: 8,
    paddingBottom: 24,
  },
  row: {
    borderRadius: 14,
    padding: 12,
    gap: 4,
  },
  rowUser: {
    backgroundColor: '#fef3c7',
  },
  rowAssistant: {
    backgroundColor: '#fde68a',
  },
});
