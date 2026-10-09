import { apiFetch, escHtml as esc } from './api.js';

let config, entries = [], jobs = [], busy = false;
let previewUrl;
const $ = id => document.getElementById(id);
const statuses = {saved:'Descoberta', skipped:'Não tenho interesse', selected:'Quero me candidatar', resume_prepared:'Currículo preparado', applied:'Candidatura realizada', response_received:'Resposta recebida', interview:'Entrevista', rejected:'Rejeitada', accepted:'Contratado'};
const categories = {experience:'Experiência profissional', education:'Formação acadêmica', project:'Projeto', skill:'Competência', language:'Idioma', certification:'Certificação', research:'Pesquisa / monitoria / publicação', other:'Outras informações'};
const contacts = [['first_name','Nome'],['last_name','Sobrenome'],['email','E-mail'],['phone_country_code','Código telefônico'],['phone','Telefone'],['city','Cidade'],['state','Estado'],['country','País'],['linkedin_url','LinkedIn'],['github_url','GitHub'],['portfolio_url','Portfólio'],['professional_links','Outros links profissionais','list']];
const preferences = [['job_titles','Cargos desejados','list'],['areas','Áreas de atuação','list'],['keywords_include','Palavras-chave incluídas (qualquer uma)','list'],['keywords_exclude','Palavras-chave excluídas','list'],['experience_levels','Senioridade (intern, junior, senior, pleno…)','list'],['locations','Localizações','list'],['countries','Países desejados','list'],['work_modes','Modalidades (remote, hybrid, on-site)','list'],['weekly_hours','Horas semanais disponíveis','number'],['employment_types','Jornada (Full-time, Part-time)','list'],['salary_min','Salário mínimo (conferência manual)','number'],['contract_types','Contratos (CLT, PJ, estágio…)','list'],['accepted_languages','Idiomas aceitos','list'],['willing_to_relocate','Disponível para realocação','bool'],['needs_sponsorship','Precisa de patrocínio de visto','bool'],['remote_only','Apenas remoto confirmado quando publicado','check'],['resume_language','Títulos de seções do currículo','language'],['greenhouse_boards','Boards Greenhouse','list'],['lever_boards','Boards Lever','list'],['max_results','Limite de vagas por busca (1–100)','number']];
const fields = [['category','Categoria','category'],['organization','Empresa / instituição'],['title','Cargo / curso / projeto'],['start_date','Data de início'],['end_date','Conclusão ou previsão'],['location','Localização'],['experience_type','Modalidade da experiência'],['technologies','Tecnologias confirmadas','list'],['url','Link'],['proficiency','Nível de proficiência'],['text','Responsabilidade, resultado ou informação confirmada','text']];
const split = value => value.split(',').map(x=>x.trim()).filter(Boolean);

function field(prefix, item, value) {
  const [key,label,type] = item, id = `${prefix}-${key}`;
  let control;
  if(type === 'bool') control = `<select id="${id}"><option value="">Não informado</option><option value="true" ${value===true?'selected':''}>Sim</option><option value="false" ${value===false?'selected':''}>Não</option></select>`;
  else if(type === 'check') control = `<input id="${id}" type="checkbox" ${value?'checked':''}>`;
  else if(type === 'language') control = `<select id="${id}">${Object.entries({auto:'Idioma detectado da vaga', 'pt-BR':'Português', en:'English'}).map(([k,v])=>`<option value="${k}" ${value===k?'selected':''}>${v}</option>`).join('')}</select>`;
  else if(type === 'category') control = `<select id="${id}">${Object.entries(categories).map(([k,v])=>`<option value="${k}" ${value===k?'selected':''}>${v}</option>`).join('')}</select>`;
  else if(type === 'text') control = `<textarea id="${id}">${esc(value||'')}</textarea>`;
  else control = `<input id="${id}" type="${type==='number'?'number':key==='email'?'email':'text'}" value="${esc(type==='list'?(value||[]).join(', '):(value??''))}">`;
  return `<label>${esc(label)}${control}</label>`;
}
function read(prefix, specs) {
  const data = {};
  for(const [key,,type] of specs) {
    const el = $(`${prefix}-${key}`), value = el.value.trim();
    data[key] = type==='list'?split(value):type==='number'?(value===''?null:Number(value)):type==='bool'?(value===''?null:value==='true'):type==='check'?el.checked:value;
  }
  return data;
}
function collectEntries() {
  entries = entries.map((e,i)=>({...e,...read(`fact-${i}`,fields),confirmed:$(`fact-${i}-confirmed`).checked}));
}
function showFacts() {
  $('assistant-facts').innerHTML = entries.map((e,i)=>`<article class="assistant-fact"><strong>Informação ${i+1}</strong><p class="text-dim">Origem: ${esc(e.source||'manual')}</p><div class="assistant-grid">${fields.map(f=>field(`fact-${i}`,f,e[f[0]])).join('')}</div><label><input id="fact-${i}-confirmed" type="checkbox" ${e.confirmed?'checked':''}> Revisei e confirmo esta informação</label> <button class="btn btn-ghost" data-remove-fact="${i}">Excluir</button></article>`).join('') || '<p>Nenhuma informação adicionada.</p>';
}
function message(text, error=false) {
  $('assistant-message').textContent = text;
  $('assistant-message').style.color = error?'var(--danger,#c22)':'';
}
async function action(fn) {
  if(busy) return;
  busy=true;
  document.querySelectorAll('#screen-assistant button').forEach(b=>b.disabled=true);
  try { await fn(); } catch(e) { message(e.message,true); }
  finally { busy=false; document.querySelectorAll('#screen-assistant button').forEach(b=>b.disabled=false); }
}
async function save() {
  collectEntries();
  const provider = $('ai-provider').value;
  const data = {profile:{...read('contact',contacts),career_entries:entries},search_criteria:read('pref',preferences),
    company_blacklist:split($('pref-company_blacklist').value),bot:{min_match_score:Number($('assistant-min-score').value)},
    llm:{provider,model:$('ai-model').value.trim(),endpoint:$('ai-endpoint').value.trim(),api_key:$('ai-api_key').value}};
  await apiFetch('/api/assistant/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  $('ai-api_key').value='';
  message('Perfil e preferências salvos. Apenas informações confirmadas serão usadas.');
}
async function task(url, data={}) {
  const result = await apiFetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  for(;;) {
    await new Promise(resolve=>setTimeout(resolve,2200));
    const state = await apiFetch(`/api/assistant/tasks/${result.task_id}`);
    if(state.state==='failed') throw new Error(state.error);
    if(state.state==='completed') return state.result;
  }
}
function safeUrl(url) { try {const u=new URL(url);return u.protocol==='https:'&&!u.username&&!u.password?u.href:'';} catch {return '';} }
function renderJobs() {
  const query=$('assistant-filter').value.toLowerCase(), min=Number($('assistant-min-score').value), status=$('assistant-status-filter').value;
  const shown=jobs.filter(j=>j.match.score>=min&&(!status||j.status===status)&&`${j.company} ${j.title}`.toLowerCase().includes(query)&&j.availability!=='closed').sort((a,b)=>b.match.score-a.match.score);
  $('assistant-results-summary').textContent=`${shown.length} vagas exibidas de ${jobs.length} registros no histórico. Ordenadas por compatibilidade. Vagas verificadas como encerradas ficam ocultas.`;
  $('assistant-jobs').innerHTML=shown.map(j=>`<article class="assistant-job" data-job-id="${j.id}"><h3>${esc(j.title)}</h3><p><strong>${esc(j.company)}</strong> · ${esc(j.location||'Localização não informada')} · ${esc(j.work_mode||'Modalidade não informada')}</p><p>Compatibilidade: <strong>${j.match.score}/100</strong> · Fonte: ${esc(j.source)} · Publicação: ${esc(j.published_at?.slice(0,10)||'não informada')} · Descoberta: ${esc(j.discovered_at.slice(0,10))}</p><p>${esc(j.description.slice(0,300))}…</p><p>${j.url_status==='verified'?'✓ Link verificado':'⚠ Link não verificado'}: ${esc(j.url_message)}</p><div class="flex gap-sm" style="flex-wrap:wrap"><a class="btn btn-primary" target="_blank" rel="noopener noreferrer" href="${esc(safeUrl(j.apply_url))}">Abrir vaga</a><button class="btn btn-ghost" data-verify="${j.id}">Verificar link</button><button class="btn btn-success" data-generate="${j.id}">Gerar currículo</button><button class="btn btn-ghost" data-regenerate="${j.id}">Gerar nova versão</button><label>Estado da candidatura <select data-job-status="${j.id}">${Object.entries(statuses).map(([k,v])=>`<option value="${k}" ${j.status===k?'selected':''}>${v}</option>`).join('')}</select></label></div><details><summary>Explicação do matching e requisitos</summary><p>${esc(j.match.explanation)}</p><p>${esc(j.match.recommendation)}</p>${['matches','gaps','blockers','unknowns'].map((k,i)=>`<strong>${['Correspondências','Lacunas','Possíveis eliminatórios','Conferência manual'][i]}</strong><ul>${j.match[k].map(x=>`<li>${esc(x)}</li>`).join('')||'<li>Nenhum item identificado</li>'}</ul>`).join('')}<strong>Requisitos obrigatórios identificados</strong><pre>${esc(j.required.join('\n')||'Sem seção explícita identificada; confira a descrição')}</pre><strong>Diferenciais identificados</strong><pre>${esc(j.preferred.join('\n')||'Não identificados')}</pre></details><details><summary>Descrição completa</summary><pre>${esc(j.description)}</pre></details>${j.resumes.length?`<h4>Currículos por versão</h4><p class="text-dim">Textos preservam o idioma das informações confirmadas; a preferência altera os títulos das seções. Revise antes de enviar.</p>`+j.resumes.map(r=>`<p>Versão ${r.id} · ${esc(r.created_at)} <button class="btn btn-ghost" data-download="${r.id}" data-format="pdf">Baixar PDF</button> <button class="btn btn-ghost" data-preview="${r.id}">Visualizar PDF</button> <button class="btn btn-ghost" data-download="${r.id}" data-format="docx">Baixar DOCX</button> <button class="btn btn-ghost" data-download="${r.id}" data-format="provenance">Fontes das afirmações</button></p>`).join(''):''}</article>`).join('')||'<p>Nenhum resultado com estes filtros. Configure os boards, amplie os cargos ou reduza a pontuação mínima. Nenhuma vaga será fabricada.</p>';
}
async function refresh() {jobs=(await apiFetch('/api/assistant/jobs')).jobs;renderJobs();}
async function download(id,format,preview=false) {
  const response=await apiFetch(`/api/assistant/resumes/${id}/${format}${preview?'?preview=1':''}`);
  const url=URL.createObjectURL(await response.blob());
  if(preview) {if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=url;$('assistant-pdf-frame').src=url;$('assistant-preview').showModal();}
  else {const a=document.createElement('a');a.href=url;a.download=`resume-${id}.${format==='provenance'?'json':format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
}
export async function loadAssistant() {
  try {
    if(!config) {
      config=await apiFetch('/api/assistant/config'); entries=config.profile.career_entries;
      $('assistant-contact').innerHTML=contacts.map(f=>field('contact',f,config.profile[f[0]])).join('');
      $('assistant-preferences').innerHTML=preferences.map(f=>field('pref',f,config.search_criteria[f[0]])).join('')+field('pref',['company_blacklist','Empresas bloqueadas','list'],config.company_blacklist);
      $('assistant-ai').innerHTML=`<label>Provedor<select id="ai-provider">${Object.entries({'':'Sem IA',openai:'OpenAI / endpoint compatível',anthropic:'Anthropic',google:'Google',deepseek:'DeepSeek'}).map(([k,v])=>`<option value="${k}" ${k===config.llm.provider?'selected':''}>${v}</option>`).join('')}</select></label><label>Modelo<input id="ai-model" value="${esc(config.llm.model)}"></label><label>Endpoint completo opcional (/v1/chat/completions)<input id="ai-endpoint" value="${esc(config.llm.endpoint||'')}"></label><label>API key (armazenada no cofre do sistema)<input id="ai-api_key" type="password" autocomplete="off"></label>`;
      $('assistant-key-status').textContent=config.llm.has_api_key?'Chave configurada no backend; não enviada à interface.':'Nenhuma chave configurada. Endpoint local pode funcionar sem chave.';
      $('assistant-min-score').value=config.bot.min_match_score;
      $('assistant-status-filter').insertAdjacentHTML('beforeend',Object.entries(statuses).map(([k,v])=>`<option value="${k}">${v}</option>`).join(''));
      showFacts(); initEvents();
    }
    await refresh();
  } catch(e) {message(e.message,true);}
}
function initEvents() {
  $('assistant-add-fact').onclick=()=>{collectEntries();entries.push({id:crypto.randomUUID(),category:'experience',text:'',source:'manual',confirmed:false});showFacts();};
  $('assistant-save').onclick=()=>action(async()=>{await save();await refresh();});
  $('assistant-refresh').onclick=()=>action(refresh);
  $('assistant-search').onclick=()=>action(async()=>{await save();message('Pesquisando APIs públicas e verificando até cinco links…');const r=await task('/api/assistant/search');await refresh();message(`Busca concluída: ${r.received} registros recebidos, ${r.job_ids.length} vagas neste resultado.\n${r.errors.join('\n')}`);});
  $('assistant-ai-test').onclick=()=>action(async()=>{await save();message('Testando provedor sem dados pessoais…');await task('/api/assistant/ai/test');message('Provedor respondeu ao teste.');});
  ['assistant-filter','assistant-min-score','assistant-status-filter'].forEach(id=>$(id).oninput=renderJobs);
  $('assistant-facts').onclick=e=>{const b=e.target.closest('[data-remove-fact]');if(b){collectEntries();entries.splice(Number(b.dataset.removeFact),1);showFacts();}};
  $('assistant-import').onchange=()=>action(async()=>{
    const file=$('assistant-import').files[0];if(!file)return;
    collectEntries();const form=new FormData();form.append('file',file);message('Extraindo texto localmente…');
    const result=await apiFetch('/api/assistant/import',{method:'POST',body:form});
    const paragraphs=result.text.split(/\n\s*\n/).filter(x=>x.trim());
    entries.push(...paragraphs.map(text=>({id:crypto.randomUUID(),category:'other',text,source:result.source,confirmed:false})));
    showFacts();message('Rascunhos importados. Revise o texto, os cargos e as datas, categorize e confirme apenas informações corretas. Salve o perfil.');$('assistant-import').value='';
  });
  $('assistant-kb').onclick=()=>action(async()=>{collectEntries();const r=await apiFetch('/api/assistant/kb-suggestions');const ids=new Set(entries.map(e=>e.id));entries.push(...r.entries.filter(e=>!ids.has(e.id)));showFacts();message('Sugestões da Knowledge Base adicionadas sem confirmação. Confira a origem antes de confirmar.');});
  $('assistant-jobs').onclick=e=>action(async()=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.generate||b.dataset.regenerate){await save();message('Preparando currículo com informações confirmadas…');const r=await task(`/api/assistant/jobs/${b.dataset.generate||b.dataset.regenerate}/resume`,{use_ai:$('assistant-use-ai').checked,force:!!b.dataset.regenerate});await refresh();message(`Currículo ${r.cached?'recuperado do cache':'gerado e validado'}: ${r.validation.pages} página(s), ${r.validation.extracted_characters} caracteres extraídos.`);}
    else if(b.dataset.verify){message('Verificando link e correspondência da vaga…');const r=await task(`/api/assistant/jobs/${b.dataset.verify}/verify`);await refresh();message(r.message);}
    else if(b.dataset.download)await download(b.dataset.download,b.dataset.format);
    else if(b.dataset.preview)await download(b.dataset.preview,'pdf',true);
  });
  $('assistant-jobs').onchange=e=>{const s=e.target.closest('[data-job-status]');if(s)action(async()=>{await apiFetch(`/api/assistant/jobs/${s.dataset.jobStatus}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:s.value})});await refresh();message('Estado registrado no histórico.');});};
  $('assistant-close-preview').onclick=()=>{$('assistant-preview').close();$('assistant-pdf-frame').src='about:blank';if(previewUrl)URL.revokeObjectURL(previewUrl);};
}
