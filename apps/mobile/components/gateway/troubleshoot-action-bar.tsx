import React, { useMemo } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { useGateway } from '@/src/gateway/state';
import { useI18n } from '@/src/i18n/i18n';

type TroubleshootActionBarProps = {
  title?: string;
};

export function TroubleshootActionBar({ title }: TroubleshootActionBarProps) {
  const { t } = useI18n();
  const gw = useGateway();

  const actions = useMemo(
    () => [
      {
        key: 'all',
        label: t('actions.fetchAll'),
        onPress: () => gw.runTroubleshootActions(),
      },
      {
        key: 'sessions',
        label: t('actions.fetchSessions'),
        onPress: () => gw.listSessions(),
      },
      {
        key: 'tasks',
        label: t('actions.fetchTasks'),
        onPress: () => gw.listTasks(),
      },
      {
        key: 'dimsums',
        label: t('actions.fetchDimsums'),
        onPress: () => gw.listDimsums(),
      },
      {
        key: 'memories',
        label: t('actions.fetchMemories'),
        onPress: () => gw.listMemories(),
      },
      {
        key: 'settings',
        label: t('actions.fetchSettings'),
        onPress: () => gw.getSettings(),
      },
    ],
    [gw, t],
  );

  return (
    <View style={styles.container}>
      <ThemedText type="subtitle">{title ?? t('actions.title')}</ThemedText>
      <View style={styles.grid}>
        {actions.map((action) => (
          <Pressable
            key={action.key}
            style={({ pressed }) => [styles.button, pressed ? styles.buttonPressed : null]}
            onPress={action.onPress}>
            <ThemedText style={styles.buttonText}>{action.label}</ThemedText>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 8,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  button: {
    minHeight: 36,
    paddingHorizontal: 12,
    borderRadius: 999,
    backgroundColor: '#0f172a',
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonPressed: {
    opacity: 0.85,
    transform: [{ scale: 0.98 }],
  },
  buttonText: {
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '600',
    color: '#f8fafc',
  },
});
