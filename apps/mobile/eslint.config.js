// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*'],
  },
  {
    rules: {
      // workspace:* packages are resolved by pnpm workspace; eslint import resolver isn't configured here.
      'import/no-unresolved': 'off',
    },
  },
]);
