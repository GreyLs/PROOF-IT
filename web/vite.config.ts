import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import {localeQualityGate} from './locale-quality.mjs';
export default defineConfig({
  plugins: [localeQualityGate(),react({jsxImportSource:'proofit-i18n'})],
  resolve: {alias:{'proofit-i18n':new URL('./src/i18n-runtime',import.meta.url).pathname.replace(/^\/(?:([A-Za-z]):)/,'$1:')}},
  server: { proxy: { "/api": "http://127.0.0.1:8080" } },
  build: { sourcemap: false },
});
