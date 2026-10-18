import { apiFetch, escHtml as esc } from './api.js';

const defaults = {openai:'gpt-6.1-sol',anthropic:'claude-sonnet-4-20250514',google:'gemini-2.0-flash',deepseek:'deepseek-chat'};

export function aiFields(config, prefix) {
  return `<label>Provedor<select id="${prefix}-provider">${Object.entries({'':'Sem IA',openai:'OpenAI',compatible:'Servidor compatível com OpenAI',anthropic:'Anthropic',google:'Google',deepseek:'DeepSeek'}).map(([k,v])=>`<option value="${k}" ${k===config.provider?'selected':''}>${v}</option>`).join('')}</select></label>
  <label>Modelo<input id="${prefix}-model" value="${esc(config.model||'')}" placeholder="${defaults[config.provider]||'ID do modelo'}" list="${prefix}-models"><datalist id="${prefix}-models"><option value="gpt-6.1-sol"></option></datalist><small>Você pode informar qualquer ID disponibilizado pelo provedor.</small></label>
  <label>Chave de API<input id="${prefix}-api_key" type="password" autocomplete="new-password" placeholder="Vazio mantém a chave deste destino"><small>Guardada no cofre do sistema.</small></label>
  <details id="${prefix}-advanced" class="ai-advanced" ${config.endpoint||config.provider==='compatible'?'open':''}><summary>Opções avançadas de conexão</summary>
    <label>URL-base ou endpoint completo<input id="${prefix}-endpoint" type="url" value="${esc(config.endpoint||'')}" placeholder="https://servidor.example/v1"></label>
    <label>Protocolo<select id="${prefix}-protocol">${Object.entries({auto:'Automático (preserva endpoints antigos)',responses:'Responses (/responses)',chat_completions:'Chat Completions (/chat/completions)'}).map(([k,v])=>`<option value="${k}" ${k===(config.protocol||'auto')?'selected':''}>${v}</option>`).join('')}</select></label>
    <small id="${prefix}-destination-hint">OpenAI oficial: destino preenchido automaticamente com Responses. Uma URL-base recebe apenas o sufixo do protocolo; um endpoint completo é preservado.</small>
  </details>`;
}

export function readAI(prefix) {
  const value = name => document.getElementById(`${prefix}-${name}`).value.trim();
  return {provider:value('provider'),model:value('model'),api_key:value('api_key'),endpoint:value('endpoint'),protocol:value('protocol')};
}

export function bindAI(prefix, onChange=()=>{}) {
  const el = name => document.getElementById(`${prefix}-${name}`);
  el('provider').addEventListener('change',()=>{
    el('api_key').value=''; el('endpoint').value=''; el('model').value=''; el('protocol').value='auto';
    el('model').placeholder=defaults[el('provider').value]||'ID do modelo';
    el('advanced').open=el('provider').value==='compatible';
    onChange('Destino alterado. A credencial será consultada apenas para este provedor e servidor.');
  });
  el('endpoint').addEventListener('input',()=>{
    el('api_key').value='';
    onChange('Destino alterado. Informe uma chave deste servidor ou deixe vazio para consultar o cofre.');
  });
  ['model','protocol','api_key'].forEach(name=>el(name).addEventListener('input',()=>onChange('Configuração alterada; teste novamente para verificar.')));
}

export async function testAI(data) {
  const result = await apiFetch('/api/ai/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if(!result.valid) {
    const error=new Error(result.error?.message||'A IA não concluiu o teste.');
    error.diagnostic=result.error;
    error.context={provider:result.provider,model:result.model,protocol:result.protocol,endpoint:result.endpoint};
    throw error;
  }
  return result;
}

export function credentialStatus(llm) {
  if(llm.credential_source==='environment') return `Credencial disponível pela variável ${llm.environment_variable}, restrita a este destino.`;
  return llm.has_api_key?'Chave disponível no cofre para este destino.':'Nenhuma chave disponível para este destino. Servidores locais podem funcionar sem chave.';
}
