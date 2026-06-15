import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { vSegPill } from './directives/segPill';
import './styles.css';

createApp(App).use(createPinia()).directive('seg-pill', vSegPill).mount('#app');
