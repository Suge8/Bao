import { Link } from 'expo-router';
import { StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';

const HOME_ROUTE = '/' as const;
const MODAL_TITLE = 'This is a modal';
const HOME_LINK_TEXT = 'Go to home screen';

export default function ModalScreen() {
  return (
    <ThemedView style={styles.container}>
      <ThemedText type="title">{MODAL_TITLE}</ThemedText>
      <Link href={HOME_ROUTE} dismissTo style={styles.link}>
        <ThemedText type="link">{HOME_LINK_TEXT}</ThemedText>
      </Link>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  link: {
    marginTop: 15,
    paddingVertical: 15,
  },
});
