import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// 立即把用户偏好应用到 <html>，避免 FOUC
import '@/core/stores/preferences';

import App from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
