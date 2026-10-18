import { apiFetch, escHtml as esc } from './api.js';
import { aiFields, readAI, bindAI, testAI, credentialStatus } from './ai-config.js';
import { state } from './state.js';
import { updateAIIndicators } from './ai-status.js';
import { openImportReview } from './import-review.js';
import { activityEditor, collectActivities, changeActivity } from './activities.js';
import { loadMobility, readMobility, mobilitySummary, bindMobility, geographyLabels, compareGeography } from './mobility.js';

let config, entries = [], jobs = [], busy = false;
let previewUrl;
let activePage='profile', cities=[], sourceNames={}, dirty=new Set();
let generationConstraints=[], contactNotes=[];
const $ = id => document.getElementById(id);
const statuses = {saved:'Descoberta', skipped:'Não tenho interesse', selected:'Quero me candidatar', resume_prepared:'Currículo preparado', applied:'Candidatura realizada', response_received:'Resposta recebida', interview:'Entrevista', rejected:'Rejeitada', accepted:'Contratado'};
const categories = {experience:'Experiência profissional', education:'Formação acadêmica', project:'Projeto', skill:'Competência', language:'Idioma', certification:'Certificação', research:'Pesquisa / monitoria / publicação', other:'Outras informações'};
const contacts = [['first_name','Nome'],['last_name','Sobrenome'],['email','E-mail'],['phone_country_code','Código telefônico'],['phone','Telefone'],['city','Cidade'],['state','Estado'],['country','País'],['linkedin_url','LinkedIn'],['github_url','GitHub'],['portfolio_url','Portfólio'],['professional_links','Outros links profissionais','list']];
const preferences = [['job_titles','Cargos desejados','list'],['areas','Áreas de atuação','list'],['keywords_include','Palavras-chave incluídas (qualquer uma)','list'],['keywords_exclude','Palavras-chave excluídas','list'],['experience_levels','Senioridade (intern, junior, senior, pleno…)','list'],['locations','Localizações','list'],['countries','Países desejados','list'],['work_modes','Modalidades (remote, hybrid, on-site)','list'],['weekly_hours','Horas semanais disponíveis','number'],['employment_types','Jornada (Full-time, Part-time)','list'],['salary_min','Salário mínimo (conferência manual)','number'],['contract_types','Contratos (CLT, PJ, estágio…)','list'],['accepted_languages','Idiomas aceitos','list'],['willing_to_relocate','Disponível para realocação','bool'],['needs_sponsorship','Precisa de patrocínio de visto','bool'],['remote_only','Apenas remoto confirmado quando publicado','check'],['resume_language','Títulos de seções do currículo','language'],['greenhouse_boards','Boards Greenhouse','list'],['lever_boards','Boards Lever','list'],['max_results','Limite de vagas por busca (1–100)','number']];
const fields = [['category','Categoria','category'],['organization','Empresa / instituição'],['title','Cargo / curso / projeto'],['start_date','Data de início'],['end_date','Conclusão ou previsão'],['location','Localização'],['experience_type','Modalidade da experiência'],['technologies','Tecnologias confirmadas','list'],['url','Link'],['proficiency','Nível de proficiência'],['text','Responsabilidade, resultado ou informação confirmada','text']];
const split = value => value.split(',').map(x=>x.trim()).filter(Boolean);
const pageInfo = {profile:['Meu perfil','Cadastre ou importe sua trajetória e confirme o que poderá entrar nos currículos.'], preferences:['Preferências de vagas','Defina onde e como aceita trabalhar. Campos opcionais vazios não restringem a busca.'], jobs:['Vagas e candidaturas','Busque oportunidades nas empresas escolhidas e prepare seu currículo antes de abrir a vaga.'], settings:['Configurações','Configure e teste a IA opcionalmente. O teste funciona mesmo com o perfil vazio.']};
const markDirty = page => {dirty.add(page);$('assistant-save-status').textContent='Alterações pendentes. Elas são mantidas ao navegar entre as quatro áreas.';};
const basicPrefs = preferences.filter(f=>['job_titles','keywords_include','keywords_exclude','experience_levels','max_results'].includes(f[0]));
const extraPrefs = preferences.filter(f=>!['job_titles','keywords_include','keywords_exclude','experience_levels','max_results','locations','work_modes','remote_only','countries','willing_to_relocate','salary_min','greenhouse_boards','lever_boards'].includes(f[0]));
const boardPrefs = preferences.filter(f=>['greenhouse_boards','lever_boards'].includes(f[0]));
function factFields(e) {
  const common=fields.filter(f=>['category','text'].includes(f[0]));
  const keys={experience:['organization','title','start_date','end_date','location','experience_type','technologies'],education:['organization','title','start_date','end_date','location'],project:['title','technologies','url','start_date','end_date'],research:['organization','title','start_date','end_date','url'],skill:['title','technologies','proficiency'],language:['title','proficiency'],certification:['organization','title','end_date','url'],other:['title','url']}[e.category]||['title'];
  return [common[0],...keys.map(k=>fields.find(f=>f[0]===k)).map(f=>{
    let label=f[1],type=f[2];
    if(f[0]==='organization')label=e.category==='experience'?'Empresa do vínculo contratual':'Instituição';
    if(f[0]==='title')label=({experience:'Cargo',education:'Curso / formação',project:'Nome do projeto',language:'Idioma',skill:'Competência'})[e.category]||'Título';
    if(['start_date','end_date'].includes(f[0]))type=/^\d{4}-\d{2}$/.test(e[f[0]]||'')||!e[f[0]]?'month':undefined;
    return [f[0],label,type];
  }),common[1]];
}

function field(prefix, item, value) {
  const [key,label,type] = item, id = `${prefix}-${key}`;
  let control;
  if(type === 'bool') control = `<select id="${id}"><option value="">Não informado</option><option value="true" ${value===true?'selected':''}>Sim</option><option value="false" ${value===false?'selected':''}>Não</option></select>`;
  else if(type === 'check') control = `<input id="${id}" type="checkbox" ${value?'checked':''}>`;
  else if(type === 'language') control = `<select id="${id}">${Object.entries({auto:'Idioma detectado da vaga', 'pt-BR':'Português', en:'English'}).map(([k,v])=>`<option value="${k}" ${value===k?'selected':''}>${v}</option>`).join('')}</select>`;
  else if(type === 'category') control = `<select id="${id}">${Object.entries(categories).map(([k,v])=>`<option value="${k}" ${value===k?'selected':''}>${v}</option>`).join('')}</select>`;
  else if(type === 'text') control = `<textarea id="${id}">${esc(value||'')}</textarea>`;
  else if(type === 'list') control = `<input id="${id}" type="hidden" value="${esc((value||[]).join(', '))}"><span class="assistant-chips" id="${id}-chips">${(value||[]).map(x=>`<span class="assistant-chip">${esc(x)}<button type="button" data-chip-remove="${id}" data-value="${esc(x)}" aria-label="Remover ${esc(x)}">×</button></span>`).join('')}</span><span class="assistant-toolbar"><input id="${id}-new" placeholder="Digite um item e pressione Enter" data-chip-input="${id}"><button type="button" class="btn btn-ghost" data-chip-add="${id}">Adicionar</button></span>`;
  else control = `<input id="${id}" type="${type==='number'?'number':type==='month'?'month':key==='email'?'email':'text'}" value="${esc(type==='list'?(value||[]).join(', '):(value??''))}">`;
  return `<label>${esc(label)}${control}</label>`;
}
function read(prefix, specs) {
  const data = {};
  for(const [key,,type] of specs) {
    const el = $(`${prefix}-${key}`); if(!el)continue; const value = el.value.trim();
    data[key] = type==='list'?split(value):type==='number'?(value===''?null:Number(value)):type==='bool'?(value===''?null:value==='true'):type==='check'?el.checked:value;
  }
  return data;
}
function collectEntries() {
  collectActivities($('assistant-facts'),entries);
  entries = entries.map((e,i)=>({...e,...read(`fact-${i}`,factFields(e)),confirmed:$(`fact-${i}-confirmed`).checked}));
}
function showFacts() {
  $('assistant-facts').innerHTML = entries.map((e,i)=>`<details class="assistant-fact" ${e.confirmed||e.import_key?'':'open'}><summary>${esc(categories[e.category]||'Informação')} · ${e.organization?esc(e.organization)+' | ':''}${esc(e.title||e.organization||`Informação ${i+1}`)} · ${e.confirmed?'Confirmada':'Precisa de revisão'}${e.activities?.length?' | '+esc(e.activities.map(a=>a.title).join(', ')):''}</summary><p class="text-dim">Origem: ${esc(e.source||'manual')}</p><div class="assistant-grid">${factFields(e).map(f=>field(`fact-${i}`,f,e[f[0]])).join('')}</div>${(e.date_notes||[]).length?'<p class="text-dim">'+esc(e.date_notes.join(' · '))+'</p>':''}${e.category==='experience'?activityEditor(e.activities||[],i,e.organization):''}${e.proficiency_basis?'<p>Proficiência: '+esc(e.proficiency_basis)+'</p>':''}<label><input id="fact-${i}-confirmed" type="checkbox" ${e.confirmed?'checked':''}> Revisei e confirmo esta informação</label> <button class="btn btn-ghost" data-remove-fact="${i}">Excluir rascunho</button></details>`).join('') || '<p>Nenhuma informação adicionada.</p>';
}
function showImportMetadata() {
  $('assistant-contact-notes').textContent=contactNotes.join('\n');
  $('assistant-profile-constraints').innerHTML=generationConstraints.map((rule,i)=>`<label>${esc(rule.scope||'Perfil')}<textarea data-profile-rule="${i}">${esc(rule.text)}</textarea></label>`).join('')||'<p>Nenhuma restrição importada.</p>';
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
  const data={};
  if(dirty.has('profile')){
    document.querySelectorAll('[data-profile-rule]').forEach(el=>generationConstraints[Number(el.dataset.profileRule)].text=el.value);
    data.profile={...read('contact',contacts),career_entries:entries,generation_constraints:generationConstraints,contact_notes:contactNotes,location_is_reference:$('contact-location-reference').checked};
  }
  if(dirty.has('preferences')){
    data.search_criteria={...read('pref',[...basicPrefs,...extraPrefs]),mobility:readMobility(cities),work_modes:[...document.querySelectorAll('#assistant-work-modes input:checked')].map(e=>e.value),remote_only:false};
    data.company_blacklist=split($('pref-company_blacklist').value);
  }
  if(dirty.has('jobs')){
    data.search_criteria={...(data.search_criteria||{}),...read('pref',boardPrefs),source_names:sourceNames};
    data.bot={min_match_score:Number($('assistant-min-score').value)};
  }
  if(dirty.has('settings'))data.llm=readAI('ai');
  if(!Object.keys(data).length)return;
  await apiFetch('/api/assistant/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  $('ai-api_key').value='';
  config=await apiFetch('/api/assistant/config');dirty.clear();
  state.aiAvailable=!!config.llm.available;updateAIIndicators();
  $('assistant-welcome').classList.toggle('hidden',!!config.profile.first_name||!!entries.length);
  $('assistant-key-status').textContent=credentialStatus(config.llm);
  $('assistant-save-status').textContent='Alterações salvas neste computador.';
  message('Perfil e preferências salvos. Apenas informações confirmadas serão usadas.');
}
async function task(url, data={}) {
  const result = await apiFetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const deadline=Date.now()+180000;
  while(Date.now()<deadline) {
    await new Promise(resolve=>setTimeout(resolve,2200));
    const state = await apiFetch(`/api/assistant/tasks/${result.task_id}`);
    if(state.state==='failed') throw new Error(state.error);
    if(state.state==='completed') return state.result;
  }
  throw new Error('A operação está demorando. Atualize o histórico antes de tentar novamente.');
}
function showCities() {
  $('assistant-cities').innerHTML=cities.map((c,i)=>`<span class="assistant-chip">${esc(c)}<button type="button" data-remove-city="${i}" aria-label="Remover ${esc(c)}">×</button></span>`).join('');
  $('assistant-location-summary').textContent=mobilitySummary(cities);
}
function showSources() {
  $('assistant-sources').innerHTML=boardPrefs.flatMap(([key])=>split($(`pref-${key}`).value).map(board=>`<p>${esc(sourceNames[`${key}:${board}`]||board)} · ${key.startsWith('greenhouse')?'Greenhouse':'Lever'}</p>`)).join('')||'<p>Nenhuma empresa configurada. Adicione uma página de carreiras para buscar.</p>';
}
function safeUrl(url) { try {const u=new URL(url);return u.protocol==='https:'&&!u.username&&!u.password?u.href:'';} catch {return '';} }
function renderJobs() {
  const query=$('assistant-filter').value.toLowerCase(), min=Number($('assistant-min-score').value), status=$('assistant-status-filter').value;
  const geography=$('assistant-geography-filter').value,sort=$('assistant-sort').value;
  const shown=jobs.filter(j=>j.match.score>=min&&(!status||j.status===status)&&(!geography||j.match.eligibility.category===geography)&&`${j.company} ${j.title}`.toLowerCase().includes(query)&&j.availability!=='closed').sort((a,b)=>compareGeography(a,b,sort));
  $('assistant-results-summary').textContent=`${shown.length} vagas exibidas de ${jobs.length} registros no histórico. Ordenadas por compatibilidade. Vagas verificadas como encerradas ficam ocultas.`;
  $('assistant-jobs').innerHTML=shown.map((j,i)=>`<article class="assistant-job" data-job-id="${j.id}" data-geography="${j.match.eligibility.category}"><p><strong class="geographic-badge geographic-${j.match.eligibility.category}">${esc(geographyLabels[j.match.eligibility.category])}</strong> ${j.match.eligibility.country_tier?`Tier ${esc(j.match.eligibility.country_tier)}`:""}</p><h3>${esc(j.title)}</h3><p>${esc((j.match.eligibility?.reasons||[]).join(" "))}</p><p><strong>${esc(j.company)}</strong> · ${esc(j.location||'Localização não informada')} · ${esc(j.work_mode||'Modalidade não informada')}</p><p>Compatibilidade profissional: <strong>${j.match.score}/100</strong> · Fonte: ${esc(j.source)} · Publicação: ${esc(j.published_at?.slice(0,10)||'não informada')} · Descoberta: ${esc(j.discovered_at.slice(0,10))}</p><p>${esc(j.description.slice(0,300))}…</p><p>${j.url_status==='verified'?'✓ Link verificado':'⚠ Link não verificado'}: ${esc(j.url_message)}</p><div class="flex gap-sm" style="flex-wrap:wrap"><a class="btn btn-primary" target="_blank" rel="noopener noreferrer" href="${esc(safeUrl(j.apply_url))}">Abrir vaga</a><button class="btn btn-ghost" data-verify="${j.id}">Verificar link</button><button class="btn btn-success" data-generate="${j.id}">Gerar currículo</button><button class="btn btn-ghost" data-regenerate="${j.id}">Gerar nova versão</button><label>Estado da candidatura <select data-job-status="${j.id}">${Object.entries(statuses).map(([k,v])=>`<option value="${k}" ${j.status===k?'selected':''}>${v}</option>`).join('')}</select></label></div><details><summary>Mobilidade, visto e remuneração</summary><p>${esc(j.match.eligibility.immigration.message)}</p><p>${esc(j.match.eligibility.financial.message)}</p><ul>${j.match.eligibility.pending.map(p=>`<li>${esc(p.message)}</li>`).join('')}</ul></details><details><summary>Explicação do compatibilidade e requisitos</summary><p>${esc(j.match.explanation)}</p><p>${esc(j.match.recommendation)}</p>${['matches','gaps','blockers','unknowns'].map((k,i)=>`<strong>${['Correspondências','Lacunas','Possíveis eliminatórios','Conferência manual'][i]}</strong><ul>${j.match[k].map(x=>`<li>${esc(x.replace(/^Evid[^ ]* [^:]+: /,"Perfil confirmado: "))}</li>`).join('')||'<li>Nenhum item identificado</li>'}</ul>`).join('')}<strong>Requisitos obrigatórios identificados</strong><pre>${esc(j.required.join('\n')||'Sem seção explícita identificada; confira a descrição')}</pre><strong>Diferenciais identificados</strong><pre>${esc(j.preferred.join('\n')||'Não identificados')}</pre></details><details><summary>Descrição completa</summary><pre>${esc(j.description)}</pre></details>${j.resumes.length?`<h4>Currículos por versão</h4><p class="text-dim">Textos preservam o idioma das informações confirmadas; a preferência altera os títulos das seções. Revise antes de enviar.</p>`+j.resumes.map(r=>`<p>Versão ${r.id} · ${esc(r.created_at)} <button class="btn btn-ghost" data-download="${r.id}" data-format="pdf">Baixar PDF</button> <button class="btn btn-ghost" data-preview="${r.id}">Visualizar PDF</button> <button class="btn btn-ghost" data-download="${r.id}" data-format="docx">Baixar DOCX</button> <button class="btn btn-ghost" data-download="${r.id}" data-format="provenance">Fontes das afirmações</button></p>`).join(''):''}</article>`).join('')||'<p>Nenhum resultado com estes filtros. Adicione empresas nas fontes, amplie os cargos ou reduza a pontuação mínima. Nenhuma vaga será fabricada.</p>';
}
async function refresh() {jobs=(await apiFetch('/api/assistant/jobs')).jobs;renderJobs();}
async function download(id,format,preview=false) {
  const response=await apiFetch(`/api/assistant/resumes/${id}/${format}${preview?'?preview=1':''}`);
  const url=URL.createObjectURL(await response.blob());
  if(preview) {if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=url;$('assistant-pdf-frame').src=url;$('assistant-preview').showModal();}
  else {const a=document.createElement('a');a.href=url;a.download=`resume-${id}.${format==='provenance'?'json':format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
}
export async function loadAssistant(page='profile') {
  if(activePage!==page)message('');
  activePage=page;
  document.querySelectorAll('[data-assistant-page]').forEach(el=>el.hidden=el.dataset.assistantPage!==page);
  [$('assistant-title').textContent,$('assistant-intro').textContent]=pageInfo[page]||pageInfo.profile;
  try {
    if(!config) {
      config=await apiFetch('/api/assistant/config'); entries=config.profile.career_entries;
      generationConstraints=config.profile.generation_constraints||[];contactNotes=config.profile.contact_notes||[];
      $('contact-location-reference').checked=!!config.profile.location_is_reference;
      showImportMetadata();
      $('assistant-contact').innerHTML=contacts.map(f=>field('contact',f,config.profile[f[0]])).join('');
      $('assistant-preferences').innerHTML=basicPrefs.map(f=>field('pref',f,config.search_criteria[f[0]])).join('')+field('pref',['company_blacklist','Empresas bloqueadas','list'],config.company_blacklist);
      $('assistant-extra-preferences').innerHTML=extraPrefs.map(f=>field('pref',f,config.search_criteria[f[0]])).join('');
      $('assistant-boards').innerHTML=boardPrefs.map(f=>field('pref',f,config.search_criteria[f[0]])).join('');
      cities=[...config.search_criteria.mobility.direct_locations];
      loadMobility(config.search_criteria,config.profile);
      sourceNames={...(config.search_criteria.source_names||{})};
      document.querySelectorAll('#assistant-work-modes input').forEach(el=>el.checked=config.search_criteria.remote_only?el.value==='remote':(!config.search_criteria.work_modes.length||config.search_criteria.work_modes.includes(el.value))&&(el.value!=='remote'||config.search_criteria.mobility.remote_enabled));
      $('assistant-ai').innerHTML=aiFields(config.llm,'ai');
      $('assistant-key-status').textContent=credentialStatus(config.llm);
      bindAI('ai',text=>{$('assistant-key-status').textContent=text;$('assistant-test-status').textContent='Configuração alterada. Teste novamente.';markDirty('settings');});
      $('assistant-min-score').value=config.bot.min_match_score;
      $('assistant-new-category').innerHTML=Object.entries(categories).map(([k,v])=>`<option value="${k}">${v}</option>`).join('');
      $('assistant-status-filter').insertAdjacentHTML('beforeend',Object.entries(statuses).map(([k,v])=>`<option value="${k}">${v}</option>`).join(''));
      $('assistant-welcome').classList.toggle('hidden',!!config.profile.first_name||!!entries.length);
      showFacts(); showCities();showSources(); initEvents();
    }
    await refresh();
  } catch(e) {message(e.message,true);}
}
function initEvents() {
  bindMobility(()=>{markDirty('preferences');showCities();});
  $('screen-assistant').addEventListener('input',e=>{
    if(e.target.id==='assistant-filter'||e.target.id==='assistant-status-filter')return;
    const page=e.target.closest('[data-assistant-page]')?.dataset.assistantPage;
    if(page)markDirty(page);
    if(e.target.closest('#assistant-facts')&&e.target.matches('[data-activity-field]'))$(`fact-${e.target.dataset.index}-confirmed`).checked=false;
  });
  $('screen-assistant').addEventListener('change',e=>{
    if(e.target.closest('#assistant-work-modes'))showCities();
    if(e.target.id.endsWith('-category')&&e.target.id.startsWith('fact-')){collectEntries();showFacts();markDirty('profile');}
  });
  const chipAction=(id,remove)=>{
    const input=$(id),list=split(input.value),value=remove??$(`${id}-new`).value.trim();
    if(!value)return;
    const updated=remove?list.filter(x=>x!==value):[...new Set([...list,value])];
    input.value=updated.join(', ');$(`${id}-new`).value='';
    $(`${id}-chips`).innerHTML=updated.map(x=>`<span class="assistant-chip">${esc(x)}<button type="button" data-chip-remove="${id}" data-value="${esc(x)}" aria-label="Remover ${esc(x)}">×</button></span>`).join('');
    markDirty(input.closest('[data-assistant-page]')?.dataset.assistantPage||activePage);
    if(boardPrefs.some(f=>id===`pref-${f[0]}`))showSources();
  };
  $('screen-assistant').addEventListener('click',e=>{
    const add=e.target.closest('[data-chip-add]'),remove=e.target.closest('[data-chip-remove]'),legacy=e.target.closest('[data-legacy]');
    if(add)chipAction(add.dataset.chipAdd);
    if(remove)chipAction(remove.dataset.chipRemove,remove.dataset.value);
    if(legacy)window.switchScreen(legacy.dataset.legacy);
  });
  $('screen-assistant').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.dataset.chipInput){e.preventDefault();chipAction(e.target.dataset.chipInput);}});
  $('assistant-add-fact').onclick=()=>{collectEntries();entries.push({id:crypto.randomUUID(),category:$('assistant-new-category').value,text:'',source:'manual',confirmed:false});showFacts();markDirty('profile');};
  $('assistant-confirm-all').onclick=()=>{collectEntries();entries.forEach(e=>e.confirmed=true);showFacts();markDirty('profile');message('Informações marcadas como confirmadas. Salve para concluir.');};
  $('assistant-add-city').onclick=()=>{
    const name=$('city-name').value.trim(),state=$('city-state').value.trim(),country=$('city-country').value.trim();
    if(!name){message('Informe a cidade de comparecimento.',true);return;}
    const city=[name,state,country].filter(Boolean).join(', ');if(!cities.includes(city))cities.push(city);
    $('city-name').value='';$('city-state').value='';showCities();markDirty('preferences');
  };
  $('assistant-cities').onclick=e=>{const b=e.target.closest('[data-remove-city]');if(b){cities.splice(Number(b.dataset.removeCity),1);showCities();markDirty('preferences');}};
  $('assistant-add-source').onclick=()=>{
    try {
      const url=new URL($('source-url').value),parts=url.pathname.split('/').filter(Boolean);
      if(url.protocol!=='https:'||url.username||url.password||url.port)throw new Error();
      let source,board;
      if(['boards.greenhouse.io','job-boards.greenhouse.io'].includes(url.hostname)){source='greenhouse_boards';board=parts[0];}
      if(url.hostname==='jobs.lever.co'){source='lever_boards';board=parts[0];}
      if(!source||!board||!/^[-\w]{1,80}$/.test(board))throw new Error();
      sourceNames[`${source}:${board}`]=$('source-name').value.trim()||board;$('source-name').value='';
      const el=$(`pref-${source}-new`);el.value=board;chipAction(`pref-${source}`);$('source-url').value='';
      message('Página adicionada às fontes. Salve ou pesquise para consultar as vagas.');
    } catch {message('Use uma página HTTPS de empresa em jobs.lever.co, boards.greenhouse.io ou job-boards.greenhouse.io.',true);}
  };
  $('assistant-save').onclick=()=>action(async()=>{await save();await refresh();});
  $('assistant-refresh').onclick=()=>action(refresh);
  $('assistant-search').onclick=()=>action(async()=>{await save();message('Pesquisando APIs públicas e verificando até cinco links…');const r=await task('/api/assistant/search');await refresh();message(`Busca concluída: ${r.received} registros recebidos, ${r.job_ids.length} vagas neste resultado.\n${r.errors.join('\n')}`);});
  $('assistant-ai-test').onclick=()=>action(async()=>{
    const draft=readAI('ai');
    $('assistant-test-status').textContent='Testando geração sem dados pessoais (até 60 segundos)…';
    try {const r=await testAI(draft);if(JSON.stringify(draft)!==JSON.stringify(readAI('ai')))throw new Error('O teste terminou para a configuração anterior. Teste novamente após concluir a edição.');$('assistant-test-status').textContent=`${r.message} Modelo: ${r.model}.`;
      $('assistant-test-details').hidden=false;$('assistant-test-metadata').textContent=`Provedor: ${r.provider}; protocolo: ${r.protocol}; destino: ${r.endpoint}`;
    } catch(e){$('assistant-test-status').textContent=e.message;
      if(e.diagnostic){$('assistant-test-details').hidden=false;$('assistant-test-metadata').textContent=Object.entries({...e.context,...e.diagnostic}).filter(([,v])=>v!==null&&v!==undefined&&v!=='').map(([k,v])=>`${k}: ${v}`).join(' · ');}
      throw e;
    }
  });
  $('assistant-remove-key').onclick=()=>action(async()=>{
    if(dirty.has('settings'))throw new Error('Salve primeiro o destino selecionado para remover sua chave armazenada.');
    const r=await apiFetch('/api/ai/credential',{method:'DELETE'});$('ai-api_key').value='';config.llm=r.llm;
    state.aiAvailable=!!r.llm?.available;updateAIIndicators();
    $('assistant-key-status').textContent=credentialStatus(r.llm);$('assistant-test-status').textContent='Chave removida do cofre. Variáveis de ambiente são gerenciadas fora do aplicativo.';
  });
  ['assistant-filter','assistant-min-score','assistant-status-filter','assistant-geography-filter','assistant-sort'].forEach(id=>$(id).oninput=renderJobs);
  $('assistant-facts').onclick=e=>{if(e.target.closest('[data-add-activity], [data-remove-activity]')){collectEntries();const index=changeActivity(e.target,entries);entries[index].confirmed=false;showFacts();$('assistant-facts').children[index].open=true;markDirty('profile');return;}const b=e.target.closest('[data-remove-fact]');if(b){collectEntries();entries.splice(Number(b.dataset.removeFact),1);showFacts();markDirty('profile');}};
  $('assistant-import').onchange=()=>action(async()=>{
    const file=$('assistant-import').files[0];if(!file)return;
    collectEntries();const mode=$('assistant-import-mode').value;
    if(mode==='ai'&&!$('assistant-import-ai').checked){$('assistant-import').value='';throw new Error('Autorize o uso da IA ou selecione extração local.');}
    const form=new FormData();form.append('file',file);form.append('mode',mode);form.append('consent_ai',$('assistant-import-ai').checked?'true':'false');
    message(mode==='basic'?'Extraindo texto básico; nenhum campo será preenchido automaticamente…':'Extraindo campos para revisão…');
    try {
      const result=await apiFetch('/api/assistant/import',{method:'POST',body:form});
      if(result.mode==='basic'){
        $('assistant-import-suggestions').innerHTML=`<p>Importação básica de texto: sem extração estruturada. Nada foi aplicado ao perfil.</p><details open><summary>Texto extraído para consulta manual</summary><pre style="white-space:pre-wrap;max-height:300px;overflow:auto">${esc(result.text)}</pre></details>`;
        message('Texto básico extraído. Para preencher campos, escolha extração estruturada local ou importação inteligente com IA.');return;
      }
      $('assistant-import-suggestions').textContent='';
      openImportReview(result,{currentEntries:entries,currentContacts:read('contact',contacts),onApply:review=>{
        const updated=new Map((review.updates||[]).map(e=>[e.id,e]));entries=entries.map(e=>updated.get(e.id)||e);
        const replaced=new Set(review.replace_ids||[]);entries=entries.filter(e=>!replaced.has(e.id));
        const keys=new Set(entries.map(e=>e.import_key||e.id));
        entries.push(...review.entries.filter(e=>!keys.has(e.import_key||e.id)));
        for(const [key,value]of Object.entries(review.contacts)){const input=$(`contact-${key}`);if(input)input.value=value;}
        if(review.contacts.city)$('contact-location-reference').checked=!!review.location_is_reference;
        const ruleIds=new Set(generationConstraints.map(c=>c.id));generationConstraints.push(...review.constraints.filter(c=>!ruleIds.has(c.id)));
        contactNotes=[...new Set([...contactNotes,...review.contact_notes])];
        showFacts();showImportMetadata();markDirty('profile');
        message(`Importação revisada aplicada aos campos. ${review.duplicate_count} duplicatas ignoradas. Salve o perfil para persistir. Itens não confirmados permanecem rascunhos.`);
      }});
      message('Revise os contatos e as categorias na janela de importação. Nada foi aplicado ainda.');
    } finally {$('assistant-import').value='';}
  });
  $('assistant-import-mode').onchange=()=>{
    const mode=$('assistant-import-mode').value;
    $('assistant-import-consent').hidden=mode!=='ai';
    $('assistant-import-mode-help').textContent=mode==='basic'?'Apenas mostra o texto bruto para consulta manual. Não extrai campos nem adiciona informações ao perfil.':mode==='ai'?'Usa a estrutura do documento primeiro. Quando necessário, envia texto ao provedor autorizado e valida os campos e trechos de origem. Falhas são exibidas sem fallback silencioso.':'Extrai campos a partir de títulos e rótulos reconhecidos, sem enviar dados à IA. Revise o resultado antes de aplicar.';
  };
  $('assistant-kb').onclick=()=>action(async()=>{collectEntries();const r=await apiFetch('/api/assistant/kb-suggestions');const ids=new Set(entries.map(e=>e.id));entries.push(...r.entries.filter(e=>!ids.has(e.id)));showFacts();markDirty('profile');message('Sugestões do perfil antigo adicionadas para revisão. Confira a origem antes de confirmar.');});
  $('assistant-jobs').onclick=e=>action(async()=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.generate||b.dataset.regenerate){await save();message('Preparando currículo com informações confirmadas…');const r=await task(`/api/assistant/jobs/${b.dataset.generate||b.dataset.regenerate}/resume`,{use_ai:$('assistant-use-ai').checked,force:!!b.dataset.regenerate});await refresh();message(`Currículo ${r.cached?'recuperado do cache':'gerado e validado'}: ${r.validation.pages} página(s), ${r.validation.extracted_characters} caracteres extraídos.`);}
    else if(b.dataset.verify){message('Verificando link e correspondência da vaga…');const r=await task(`/api/assistant/jobs/${b.dataset.verify}/verify`);await refresh();message(r.message);}
    else if(b.dataset.download)await download(b.dataset.download,b.dataset.format);
    else if(b.dataset.preview)await download(b.dataset.preview,'pdf',true);
  });
  $('assistant-jobs').onchange=e=>{const s=e.target.closest('[data-job-status]');if(s)action(async()=>{await apiFetch(`/api/assistant/jobs/${s.dataset.jobStatus}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:s.value})});await refresh();message('Estado registrado no histórico.');});};
  $('assistant-close-preview').onclick=()=>{$('assistant-preview').close();$('assistant-pdf-frame').src='about:blank';if(previewUrl)URL.revokeObjectURL(previewUrl);};
  window.addEventListener('beforeunload',e=>{if(dirty.size){e.preventDefault();e.returnValue='';}});
  window.addEventListener('autoapply-config-saved',()=>{if(!dirty.size){config=null;loadAssistant(activePage);}});
}
