import React, { useMemo } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { useGateway } from '@/src/gateway/state';
import { useI18n } from '@/src/i18n/i18n';

type TroubleshootActionBarProps = {
  title?: string;
};

type ActionDescriptor = {
  key: string;
  labelKey: string;
  run: () => void;
};

export function TroubleshootActionBar({ title }: TroubleshootActionBarProps) {
  const { t } = useI18n();
  const gw = useGateway();

  const actions = useMemo(
    (): ActionDescriptor[] => [
      {
        key: 'all',
        labelKey: 'actions.fetchAll',
        run: gw.runTroubleshootActions,
      },
      {
        key: 'sessions',
        labelKey: 'actions.fetchSessions',
        run: gw.listSessions,
      },
      {
        key: 'tasks',
        labelKey: 'actions.fetchTasks',
        run: gw.listTasks,
      },
      {
        key: 'dimsums',
        labelKey: 'actions.fetchDimsums',
        run: gw.listDimsums,
      },
      {
        key: 'memories',
        labelKey: 'actions.fetchMemories',
        run: gw.listMemories,
      },
      {
        key: 'settings',
        labelKey: 'actions.fetchSettings',
        run: gw.getSettings,
      },
    ],
    [gw],
  );

  return (
    <View style={styles.container}>
      <ThemedText type="subtitle">{title ?? t('actions.title')}</ThemedText>
      <View style={styles.grid}>
        {actions.map((action) => (
            <Pressable
              key={action.key}
              style={({ pressed }) => [styles.button, pressed ? styles.buttonPressed : null]}
              onPress={action.run}>
              <ThemedText style={styles.buttonText}>{t(action.labelKey)}</ThemedText>
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
