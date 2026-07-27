import { FlatCompat } from "@eslint/eslintrc";
import { fileURLToPath } from "node:url";
import path from "node:path";

const filePath = fileURLToPath(import.meta.url);
const directoryPath = path.dirname(filePath);
const compat = new FlatCompat({
  baseDirectory: directoryPath,
});

const eslintConfig = [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "out/**",
    ],
  },
  ...compat.extends("next/core-web-vitals"),
];

export default eslintConfig;
