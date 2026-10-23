import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'playwright-report', 'test-results'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // Data loading here is a plain `useEffect` + fetch per page, on purpose:
      // the product has no client-side cache requirement, so a query library
      // would add a dependency without removing real work. The React
      // Compiler-era rule flags exactly that pattern, so it is turned off
      // explicitly instead of weakening the whole lint run. Genuine hook bugs
      // are still caught by rules-of-hooks and exhaustive-deps below.
      'react-hooks/set-state-in-effect': 'off',

      // HMR-only DX hint with no bearing on production correctness; leaving it
      // on would force splitting every context module into two files.
      'react-refresh/only-export-components': 'off',

      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
)
