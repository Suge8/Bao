import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
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

export default function HomeScreen() {
  const { t } = useI18n();
  const gw = useGateway();
  const [url, setUrl] = useState(gw.url);
  const [token, setToken] = useState(gw.token);

  const handleConnect = () => {
    gw.connect({ url, token }).catch(() => {});
  };

  const handleDisconnect = () => {
    gw.disconnect();
  };

  return (
    <ThemedView style={styles.container}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <Animated.View entering={FadeInDown.springify().damping(16)} style={styles.hero}>
          <ThemedText type="title">{t('connect.title')}</ThemedText>
          <ThemedText style={styles.hint}>{t('connect.replayHint')}</ThemedText>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(50).springify().damping(16)} style={styles.card}>
          <View style={styles.field}>
            <ThemedText type="subtitle">{t('connect.url')}</ThemedText>
            <TextInput
              style={styles.input}
              autoCapitalize="none"
              autoCorrect={false}
              value={url}
              onChangeText={setUrl}
              placeholder={t('connect.urlPlaceholder')}
              keyboardType="url"
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
              placeholder={t('connect.tokenPlaceholder')}
              secureTextEntry
            />
          </View>

          <View style={styles.actions}>
            <Pressable
              style={({ pressed }) => [styles.primaryButton, pressed ? styles.buttonPressed : null]}
              onPress={handleConnect}>
              <ThemedText style={styles.primaryButtonText}>
                {t('connect.connect')} · {gw.connected ? t('common.on') : t('common.off')}
              </ThemedText>
            </Pressable>
            <Pressable
              style={({ pressed }) => [styles.ghostButton, pressed ? styles.buttonPressed : null]}
              onPress={handleDisconnect}>
              <ThemedText>{t('common.disconnect')}</ThemedText>
            </Pressable>
          </View>
          {gw.connectionError ? <ThemedText style={styles.errorText}>{gw.connectionError}</ThemedText> : null}
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(100).springify().damping(16)} style={styles.statusCard}>
          <ThemedText type="subtitle">{t('connect.connected')}</ThemedText>
          <ThemedText>{gw.connected ? t('common.on') : t('common.off')}</ThemedText>
          <ThemedText>
            {t('connect.replayState')}: {gw.replayActive ? t('connect.replayOn') : t('connect.replayOff')}
          </ThemedText>
          <ThemedText>{t('connect.lastEvent')}: {gw.lastEventId ?? '-'}</ThemedText>
          <ThemedText>{t('connect.events')}: {gw.events.length}</ThemedText>
          <ThemedText style={styles.eventsTitle}>{t('connect.eventsByType')}</ThemedText>
          {EVENT_CATEGORIES.map((item) => (
            <ThemedText key={item}>
              {t(CATEGORY_KEY_MAP[item])}: {gw.eventCounts[item]}
            </ThemedText>
          ))}
          <View style={styles.actionsWrap}>
            {EVENT_CATEGORIES.map((item) => {
              const label = t(CATEGORY_KEY_MAP[item]);
              const selected = item === gw.selectedCategory;
              return (
                <Pressable
                  key={item}
                  style={({ pressed }) => [styles.categoryChip, selected ? styles.categoryChipActive : null, pressed ? styles.buttonPressed : null]}
                  onPress={() => gw.setSelectedCategory(item)}>
                  <ThemedText style={selected ? styles.categoryTextActive : undefined}>{label}</ThemedText>
                </Pressable>
              );
            })}
          </View>
        </Animated.View>
      </ScrollView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 16,
    gap: 12,
    paddingBottom: 36,
  },
  hero: {
    borderRadius: 18,
    padding: 16,
    backgroundColor: '#dbeafe',
  },
  field: {
    gap: 6,
  },
  input: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: '#eff6ff',
  },
  card: {
    borderRadius: 18,
    padding: 14,
    backgroundColor: '#bfdbfe',
    gap: 12,
  },
  actions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 4,
  },
  primaryButton: {
    flex: 1,
    minHeight: 42,
    borderRadius: 12,
    backgroundColor: '#0f172a',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 10,
  },
  ghostButton: {
    minHeight: 42,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#0f172a',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 12,
  },
  primaryButtonText: {
    color: '#f8fafc',
    fontWeight: '700',
  },
  buttonPressed: {
    opacity: 0.85,
    transform: [{ scale: 0.985 }],
  },
  statusCard: {
    padding: 14,
    borderRadius: 18,
    backgroundColor: '#dbeafe',
    gap: 4,
  },
  hint: {
    opacity: 0.75,
  },
  errorText: {
    color: '#7f1d1d',
  },
  eventsTitle: {
    marginTop: 6,
  },
  actionsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 6,
  },
  categoryChip: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#bfdbfe',
  },
  categoryChipActive: {
    backgroundColor: '#0f172a',
  },
  categoryTextActive: {
    color: '#f8fafc',
  },
});
