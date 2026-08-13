// ESLint 9 flat config. The old `--ext`-style invocation had no config file
// at all, so `npm run lint` failed immediately and nothing was linted.
import tsParser from '@typescript-eslint/parser';
import tsPlugin from '@typescript-eslint/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      'react-hooks': reactHooks,
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // tsc (noUnusedLocals) already covers unused vars; the base rule
      // false-positives on type-only imports.
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      // All console output goes through utils/logger.ts (which carries the
      // per-line disables); stray console.log elsewhere fails the build.
      'no-console': 'error',
    },
  },
];
