/* ═══════════════════════════════════════════════════════════════
   AI PROVIDER STATUS
   ═══════════════════════════════════════════════════════════════ */
import { state } from './state.js';

export function updateAIIndicators() {
  const cls = state.aiAvailable ? 'dot dot-green' : 'dot dot-yellow';
  const txt = state.aiAvailable ? 'IA configurada' : 'IA não configurada';
  document.querySelectorAll('#nav-ai-indicator, #profile-ai-indicator').forEach(el => {
    const dot = el.querySelector('.dot');
    const span = el.querySelector('span:last-child');
    if (dot) dot.className = cls;
    if (span) span.textContent = txt;
  });
}
