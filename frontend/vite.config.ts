import { defineConfig } from 'vite';
export default defineConfig({base:process.env.VITE_BASE_PATH || '/',server:{proxy:{'/api':'http://127.0.0.1:8186','/docs':'http://127.0.0.1:8186','/openapi.json':'http://127.0.0.1:8186'}}});
