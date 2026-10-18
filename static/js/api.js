/* ═══════════════════════════════════════════════════════════════
   API — Shared fetch wrapper and HTML utilities
   ═══════════════════════════════════════════════════════════════ */
import { escHtml } from './helpers.js';

/**
 * Fetch wrapper that parses JSON responses and throws on non-OK status.
 * Auth headers are injected by auth.js (patches window.fetch).
 * @param {string} url
 * @param {RequestInit} [opts]
 * @returns {Promise<any>}
 */
export async function apiFetch(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const error = new Error(typeof body.error==='string'?body.error:body.error?.message||`Falha na operação (HTTP ${res.status}).`);
    error.diagnostic = body.error;
    throw error;
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    return res.json();
  }
  return res;
}

// Re-export escHtml for modules that import both from api.js
export { escHtml };
