import { Href, Link } from 'expo-router';
import { openBrowserAsync, WebBrowserPresentationStyle } from 'expo-web-browser';
import { type ComponentProps } from 'react';

type Props = Omit<ComponentProps<typeof Link>, 'href'> & { href: Href & string };

const IS_WEB = process.env.EXPO_OS === 'web';
const BROWSER_OPTIONS = {
  presentationStyle: WebBrowserPresentationStyle.AUTOMATIC,
} as const;

async function handleNativeExternalLink(event: Parameters<NonNullable<ComponentProps<typeof Link>['onPress']>>[0], href: string) {
  if (IS_WEB) return;
  // Prevent the default behavior of linking to the default browser on native.
  event.preventDefault();
  // Open the link in an in-app browser.
  await openBrowserAsync(href, BROWSER_OPTIONS);
}

export function ExternalLink({ href, ...rest }: Props) {
  return (
    <Link
      target="_blank"
      {...rest}
      href={href}
      onPress={(event) => handleNativeExternalLink(event, href)}
    />
  );
}
