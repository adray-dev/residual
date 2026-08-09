/**
 * Lint config, existing for one rule above all others.
 *
 * `react-hooks/exhaustive-deps` catches the bug class that has already cost this project
 * real time: a dependency array missing `selectedFromLink` made the demolition toggle a
 * silent no-op — no error, no network request, nothing in the console, just a control that
 * did nothing. Typechecking cannot see it and the tests did not cover it. A linter can.
 *
 * Kept deliberately small. This is not a style regime — Prettier-style formatting rules are
 * absent on purpose, because the value here is correctness rules that catch what review and
 * types miss, and a wall of formatting noise is how those get ignored.
 */
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "scripts/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // The reason this config exists: errors, not warnings.
      "react-hooks/exhaustive-deps": "error",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/refs": "error",

      // Off, deliberately — both are React Compiler advice about optimization, not
      // correctness, and neither describes a defect in this code.
      //
      // `set-state-in-effect` fires on `setBusy(true)` at the top of a fetch effect. That
      // is the standard way to show a request is in flight, and every alternative
      // (reducers, suspense, a fetch library) is a larger change than the cascading render
      // it avoids. Four call sites, all the same shape, all intentional.
      "react-hooks/set-state-in-effect": "off",
      // `preserve-manual-memoization` reports that the compiler declined to optimize a
      // hand-written useMemo. That is a performance note about a compiler this project
      // does not run, not a bug.
      "react-hooks/preserve-manual-memoization": "off",
      // `_vocab` and friends are deliberate: a prop kept for interface symmetry while its
      // body no longer needs it. Underscore is the signal.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
);
