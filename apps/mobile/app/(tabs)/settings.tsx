import React from 'react';
import { FlatList, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { type MobileErrorAggregateDimension, type MobileEventCategory } from '@/src/gateway/events';
import { useGateway } from '@/src/gateway/state';
import { useI18n } from '@/src/i18n/i18n';

const ERROR_DIMENSIONS: MobileErrorAggregateDimension[] = ['global', 'provider', 'session'];
const EVENT_CATEGORIES: MobileEventCategory[] = ['message', 'task', 'memory', 'audit', 'other'];

const DIMENSION_KEY_MAP: Record<MobileErrorAggregateDimension, string> = {
  global: 'settings.dimensionGlobal',
  provider: 'settings.dimensionProvider',
  session: 'settings.dimensionSession',
};

const CATEGORY_KEY_MAP: Record<MobileEventCategory, string> = {
  message: 'events.message',
  task: 'events.task',
  memory: 'events.memory',
  audit: 'events.audit',
  other: 'events.other',
};

function withSelectedLabel(selected: boolean, label: string): string {
  return selected ? `[${label}]` : label;
}

function uniqueStrings(values: (string | null | undefined)[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    if (typeof value !== 'string' || seen.has(value)) return;
    seen.add(value);
    result.push(value);
  });
  return result;
}

function parseThreshold(value: string): number | null {
  const parsed = Number.parseInt(value || '0', 10);
  return Number.isFinite(parsed) ? parsed : null;
}

export default function SettingsScreen() {
  const { t, locale, setLocale } = useI18n();
  const gw = useGateway();

  const providerOptions = uniqueStrings(gw.errorAggregates.map((item) => item.provider)).slice(0, 8);
  const sessionOptions = uniqueStrings(gw.errorAggregates.map((item) => item.sessionId)).slice(0, 8);

  return (
    <ThemedView style={styles.container}>
      <ThemedText type="title">{t('settings.title')}</ThemedText>

      <View style={styles.row}>
        <ThemedText type="subtitle">{t('settings.language')}</ThemedText>
        <View style={styles.actions}>
          <ThemedText type="link" onPress={() => setLocale('zh')}>
            zh {locale === 'zh' ? `(${t('common.on')})` : ''}
          </ThemedText>
          <ThemedText type="link" onPress={() => setLocale('en')}>
            en {locale === 'en' ? `(${t('common.on')})` : ''}
          </ThemedText>
        </View>
      </View>

      <View style={styles.row}>
        <ThemedText type="subtitle">Gateway</ThemedText>
        <ThemedText>{gw.connected ? t('common.on') : t('common.off')}</ThemedText>
      </View>

      <View style={styles.row}>
        <ThemedText type="subtitle">{t('settings.actions')}</ThemedText>
        <View style={styles.actions}>
          <ThemedText type="link" onPress={gw.listTasks}>
            {t('sessions.fetchTasks')}
          </ThemedText>
          <ThemedText type="link" onPress={gw.listDimsums}>
            {t('sessions.fetchDimsums')}
          </ThemedText>
          <ThemedText type="link" onPress={gw.listMemories}>
            {t('sessions.fetchMemories')}
          </ThemedText>
        </View>
      </View>

      <View style={styles.actionsWrap}>
        {EVENT_CATEGORIES.map((item) => {
          const label = t(CATEGORY_KEY_MAP[item]);
          const selected = item === gw.selectedCategory;
          return (
            <ThemedText key={item} type="link" onPress={() => gw.setSelectedCategory(item)}>
              {withSelectedLabel(selected, label)}
            </ThemedText>
          );
        })}
      </View>

      <View style={styles.row}>
        <ThemedText type="subtitle">{t('settings.errorSummary')}</ThemedText>

        <View style={styles.actionsWrap}>
          {ERROR_DIMENSIONS.map((dimension) => {
            const selected = dimension === gw.errorDimension;
            const label = t(DIMENSION_KEY_MAP[dimension]);
            return (
              <ThemedText key={dimension} type="link" onPress={() => gw.setErrorDimension(dimension)}>
                {withSelectedLabel(selected, label)}
              </ThemedText>
            );
          })}
        </View>

        <View style={styles.rowInline}>
          <ThemedText>{t('settings.warnThreshold')}</ThemedText>
          <TextInput
            style={styles.numberInput}
            keyboardType="number-pad"
            value={String(gw.errorWarnThreshold)}
            onChangeText={(value) => {
              const warn = parseThreshold(value);
              if (warn == null) return;
              gw.setErrorThresholds({ warn, critical: gw.errorCriticalThreshold });
            }}
          />
          <ThemedText>{t('settings.criticalThreshold')}</ThemedText>
          <TextInput
            style={styles.numberInput}
            keyboardType="number-pad"
            value={String(gw.errorCriticalThreshold)}
            onChangeText={(value) => {
              const critical = parseThreshold(value);
              if (critical == null) return;
              gw.setErrorThresholds({ warn: gw.errorWarnThreshold, critical });
            }}
          />
        </View>

        {gw.errorDimension === 'provider' ? (
          <View style={styles.actionsWrap}>
            <ThemedText type="defaultSemiBold">{t('settings.filterProvider')}</ThemedText>
            {providerOptions.map((provider) => {
              const selected = provider === gw.selectedErrorProvider;
              return (
                <ThemedText key={provider} type="link" onPress={() => gw.setSelectedErrorProvider(provider)}>
                  {withSelectedLabel(selected, provider)}
                </ThemedText>
              );
            })}
            <ThemedText type="link" onPress={() => gw.setSelectedErrorProvider(null)}>
              {t('settings.clearFilter')}
            </ThemedText>
          </View>
        ) : null}

        {gw.errorDimension === 'session' ? (
          <View style={styles.actionsWrap}>
            <ThemedText type="defaultSemiBold">{t('settings.filterSession')}</ThemedText>
            {sessionOptions.map((sessionId) => {
              const selected = sessionId === gw.selectedErrorSessionId;
              return (
                <ThemedText key={sessionId} type="link" onPress={() => gw.setSelectedErrorSessionId(sessionId)}>
                  {withSelectedLabel(selected, sessionId)}
                </ThemedText>
              );
            })}
            <ThemedText type="link" onPress={() => gw.setSelectedErrorSessionId(null)}>
              {t('settings.clearFilter')}
            </ThemedText>
          </View>
        ) : null}

        <FlatList
          data={gw.errorAggregates}
          keyExtractor={(item) => item.key}
          renderItem={({ item }) => {
            return (
              <View style={styles.errorRow}>
                <ThemedText type="defaultSemiBold">{t('settings.errorType')}: {item.eventType}</ThemedText>
                <ThemedText>{t('settings.errorCode')}: {item.code ?? '-'}</ThemedText>
                <ThemedText>{t('settings.errorStage')}: {item.stage ?? '-'}</ThemedText>
                <ThemedText>{t('settings.errorCount')}: {item.count}</ThemedText>
                <ThemedText>{t('settings.errorLatest')}: {item.latestEventId ?? '-'}</ThemedText>
                <ThemedText>{t('settings.filterProvider')}: {item.provider ?? t('settings.none')}</ThemedText>
                <ThemedText>{t('settings.filterSession')}: {item.sessionId ?? t('settings.none')}</ThemedText>
                <ThemedText>{item.message}</ThemedText>
              </View>
            );
          }}
          ListEmptyComponent={<ThemedText>{t('settings.errorEmpty')}</ThemedText>}
        />
      </View>

      <View style={styles.row}>
        <ThemedText type="subtitle">{t('settings.errorAlerts')}</ThemedText>
        <FlatList
          data={gw.errorAlerts}
          keyExtractor={(item) => item.key}
          renderItem={({ item }) => {
            return (
              <View style={styles.alertRow}>
                <ThemedText type="defaultSemiBold">
                  {item.level === 'critical' ? t('settings.alertCritical') : t('settings.alertWarn')} · {item.eventType}
                </ThemedText>
                <ThemedText>{t('settings.errorCode')}: {item.code ?? '-'}</ThemedText>
                <ThemedText>{t('settings.errorCount')}: {item.count}</ThemedText>
                <ThemedText>{t('settings.errorLatest')}: {item.latestEventId ?? '-'}</ThemedText>
                <ThemedText>{t('settings.errorDimension')}: {t(DIMENSION_KEY_MAP[item.dimension])}</ThemedText>
                <ThemedText>{item.dimensionValue ?? t('settings.none')}</ThemedText>
              </View>
            );
          }}
          ListEmptyComponent={<ThemedText>{t('settings.errorEmpty')}</ThemedText>}
        />
      </View>

      <View style={styles.row}>
        <ThemedText type="subtitle">{t('settings.errorEvents')}</ThemedText>
        <FlatList
          data={gw.errorEvents}
          keyExtractor={(item) => item.key}
          renderItem={({ item }) => {
            return (
              <View style={styles.errorRow}>
                <ThemedText type="defaultSemiBold">{item.eventType}</ThemedText>
                <ThemedText>{t('settings.errorCode')}: {item.code ?? '-'}</ThemedText>
                <ThemedText>{t('settings.errorStage')}: {item.stage ?? '-'}</ThemedText>
                <ThemedText>{t('settings.errorLatest')}: {item.eventId ?? '-'}</ThemedText>
                <ThemedText>{t('settings.filterProvider')}: {item.provider ?? t('settings.none')}</ThemedText>
                <ThemedText>{t('settings.filterSession')}: {item.sessionId ?? t('settings.none')}</ThemedText>
                <ThemedText>{item.message}</ThemedText>
              </View>
            );
          }}
          ListEmptyComponent={<ThemedText>{t('settings.errorEmpty')}</ThemedText>}
        />
      </View>

      <View style={styles.actions}>
        <ThemedText type="link" onPress={gw.getSettings}>
          getSettings
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
  row: {
    gap: 6,
  },
  actions: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 8,
  },
  actionsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  rowInline: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  numberInput: {
    minWidth: 54,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#f1f5f9',
  },
  errorRow: {
    marginTop: 8,
    padding: 10,
    borderRadius: 10,
    backgroundColor: '#e2e8f0',
    gap: 2,
  },
  alertRow: {
    marginTop: 8,
    padding: 10,
    borderRadius: 10,
    backgroundColor: '#dbeafe',
    gap: 2,
  },
});
