import { escHtml as esc } from './api.js';
import { activityEditor, collectActivities, changeActivity, proposeUpdates } from './activities.js';

const categories={experience:'Experiências profissionais',education:'Formação acadêmica',project:'Projetos',skill:'Competências',language:'Idiomas',certification:'Certificações',research:'Pesquisa',other:'Outras informações'};
const contactLabels={first_name:'Nome',last_name:'Sobrenome',email:'E-mail',phone_country_code:'Código do país',phone:'Telefone',city:'Cidade',state:'Estado',country:'País',github_url:'GitHub',linkedin_url:'LinkedIn',portfolio_url:'Portfólio'};
const snapshot=e=>JSON.stringify({id:e.id,empresa:e.organization,cargo:e.title,inicio:e.start_date,fim:e.end_date,descricao:e.text,confirmado:e.confirmed,atividades:(e.activities||[]).map(({title,text,start_date,end_date,technologies})=>({title,text,start_date,end_date,technologies})),observacoes_de_datas:e.date_notes},null,2);
const activityList=e=>`<ul>${(e.activities||[]).map(a=>`<li><strong>${esc(a.title)}</strong><br>${esc([a.start_date,a.end_date].filter(Boolean).join(' — '))}</li>`).join('')||'<li>Nenhuma atividade</li>'}</ul>`;

export function openImportReview(result,{currentEntries,currentContacts,onApply}) {
  const dialog=document.getElementById('assistant-import-review');
  const reconciled=proposeUpdates([...(result.entries||[]),...(result.updates||[]).map(u=>u.incoming)],currentEntries);
  const updates=new Map(reconciled.updates.map(u=>[u.proposed.id,u]));
  let facts=structuredClone([...reconciled.entries,...reconciled.updates.map(u=>u.proposed)]);
  const known=new Set(currentEntries.map(e=>e.import_key||e.id));
  const initial=facts.length;
  facts=facts.filter(e=>updates.has(e.id)||!known.has(e.import_key||e.id));
  let removedDuplicates=(result.duplicate_count||0)+reconciled.duplicates+initial-facts.length;
  const contactValues={...(result.contacts||{})};
  const excludedContacts=new Set(Object.keys(contactValues).filter(k=>currentContacts[k]&&currentContacts[k]!==contactValues[k]));
  const included=new Set(facts.filter(e=>!updates.has(e.id)).map(e=>e.id)), confirmed=new Set();
  const legacy=currentEntries.filter(e=>e.source===result.source&&!e.import_key&&!e.confirmed);
  const el=id=>document.getElementById(id);
  const input=(i,key,label,value,multiline=false)=>`<label ${multiline?'class="import-wide"':''}>${esc(label)}${multiline?`<textarea data-import-index="${i}" data-import-field="${key}">${esc(value||'')}</textarea>`:`<input data-import-index="${i}" data-import-field="${key}" value="${esc(value||'')}">`}</label>`;
  function collect() {
    dialog.querySelectorAll('[data-import-field]').forEach(node=>{
      const fact=facts[Number(node.dataset.importIndex)],key=node.dataset.importField;
      if(fact)fact[key]=key==='technologies'?node.value.split(',').map(v=>v.trim()).filter(Boolean):node.value;
    });
    dialog.querySelectorAll('[data-import-contact]').forEach(node=>contactValues[node.dataset.importContact]=node.value);
    dialog.querySelectorAll('[data-include-contact]').forEach(node=>node.checked?excludedContacts.delete(node.dataset.includeContact):excludedContacts.add(node.dataset.includeContact));
    dialog.querySelectorAll('[data-include-fact]').forEach(node=>node.checked?included.add(node.dataset.includeFact):included.delete(node.dataset.includeFact));
    dialog.querySelectorAll('[data-confirm-fact]').forEach(node=>node.checked?confirmed.add(node.dataset.confirmFact):confirmed.delete(node.dataset.confirmFact));
    collectActivities(dialog,facts);
  }
  function render() {
    el('assistant-import-summary').textContent=`${facts.length} informações para revisão; ${Object.keys(contactValues).length} campos de contato; ${removedDuplicates} duplicatas ignoradas. ${result.ai_used?'IA utilizada.':'Extração estruturada local; nenhum envio à IA.'}`;
    el('assistant-import-review-contacts').innerHTML=Object.keys(contactLabels).filter(key=>key in contactValues).map(key=>{const value=contactValues[key];return `<label><span><input type="checkbox" data-include-contact="${key}" ${excludedContacts.has(key)?'':'checked'}> ${esc(contactLabels[key]||key)}</span><input data-import-contact="${key}" value="${esc(value)}">${currentContacts[key]&&currentContacts[key]!==value?'<small>Já preenchido no perfil. Marque a caixa para substituir explicitamente.</small>':''}</label>`;}).join('');
    el('assistant-import-contact-notes').textContent=(result.contact_notes||[]).join('\n');
    el('assistant-import-review-facts').innerHTML=Object.entries(categories).map(([category,label])=>{
      const group=facts.map((e,i)=>({e,i})).filter(({e})=>e.category===category);
      if(!group.length)return '';
      return `<h3>${label} (${group.length})</h3>`+group.map(({e,i})=>`<details class="assistant-fact" data-review-category="${category}" open>
        <summary>${esc(e.organization||e.title||label)} · Pendente de revisão</summary>
        <label><input type="checkbox" data-include-fact="${e.id}" ${included.has(e.id)?'checked':''}> ${updates.has(e.id)?'Atualizar este vínculo existente (preservar ID)':'Incluir no perfil'}</label>
        ${updates.has(e.id)?`<details open data-update-diff><summary>Comparar atualização proposta · ${esc(e.organization)}</summary><p>Campos e atividades existentes preservados. A confirmação anterior fica no backup; confirme os dados novamente após revisar.</p><p>ID preservado: ${esc(e.id)}</p><div class="assistant-grid"><div><strong>Antes · ${(updates.get(e.id).before.activities||[]).length} atividade(s)</strong>${activityList(updates.get(e.id).before)}</div><div><strong>Proposta · ${(e.activities||[]).length} atividade(s)</strong>${activityList(e)}</div></div><details><summary>Comparar todos os campos</summary><div class="assistant-grid"><pre>${esc(snapshot(updates.get(e.id).before))}</pre><pre>${esc(snapshot(e))}</pre></div></details></details>`:''}
        <div class="assistant-grid"><label>Categoria<select data-import-index="${i}" data-import-field="category">${Object.entries(categories).map(([k,v])=>`<option value="${k}" ${k===e.category?'selected':''}>${v}</option>`).join('')}</select></label>
        ${input(i,'title',category==='language'?'Idioma':'Cargo / curso / projeto / grupo',e.title)}
        ${['experience','education','research'].includes(category)?input(i,'organization',category==='experience'?'Empresa do vínculo':'Instituição',e.organization):''}
        ${['experience','education','project','research'].includes(category)?input(i,'start_date','Início (preserve aproximações)',e.start_date)+input(i,'end_date','Fim / previsão',e.end_date):''}
        ${category==='language'?input(i,'proficiency','Nível informado',e.proficiency)+input(i,'proficiency_basis','Origem da avaliação',e.proficiency_basis):''}
        ${e.technologies?.length?input(i,'technologies','Tecnologias / competências',e.technologies.join(', ')):''}
        ${e.url?input(i,'url','Link',e.url):''}${input(i,'text','Conteúdo profissional',e.text,true)}</div>
        <p class="text-dim">${esc([...(e.date_notes||[]),...(e.uncertainties||[])].join(' · '))}</p>
        ${category==='experience'?activityEditor(e.activities||[],i,e.organization):''}
        <details><summary>Trecho de origem (somente para revisão)</summary><pre>${esc(e.source_excerpt||'')}</pre></details>
        <label><input type="checkbox" data-confirm-fact="${e.id}" ${confirmed.has(e.id)?'checked':''}> Revisei e confirmo esta informação</label>
        <button type="button" class="btn btn-ghost" data-delete-import="${i}">Excluir da importação</button></details>`).join('');
    }).join('');
    el('assistant-import-review-constraints').innerHTML=(result.constraints||[]).map(c=>`<li><strong>${esc(c.scope||'Perfil')}:</strong> ${esc(c.text)}</li>`).join('')||'<li>Nenhuma restrição explícita identificada.</li>';
    el('assistant-import-review-warnings').textContent=(result.warnings||[]).join('\n');
  }
  dialog.onclick=event=>{
    if(event.target.closest('[data-add-activity], [data-remove-activity]')){collect();changeActivity(event.target,facts);render();return;}
    const remove=event.target.closest('[data-delete-import]');
    if(remove){collect();facts.splice(Number(remove.dataset.deleteImport),1);render();}
  };
  el('assistant-import-apply').onclick=()=>apply(false);
  el('assistant-import-confirm-apply').onclick=()=>apply(true);
  el('assistant-import-cancel').onclick=()=>dialog.close();
  el('assistant-import-legacy').innerHTML=legacy.length?`<h3>Rascunhos antigos deste documento</h3><p>Não serão removidos automaticamente. Selecione somente os rascunhos que deseja substituir pela extração nova.</p>${legacy.map(e=>`<label><input type="checkbox" data-replace-legacy="${esc(e.id)}"> Substituir ${esc(e.title||e.organization||categories[e.category]||'rascunho')}</label><details><summary>Texto anterior</summary><pre>${esc(e.text)}</pre></details>`).join('')}`:'';
  function apply(confirmAll) {
    collect();
    const selected=facts.filter(e=>included.has(e.id)).map(e=>({...e,confirmed:confirmAll||confirmed.has(e.id)}));
    const contacts=Object.fromEntries(Object.entries(contactValues).filter(([key])=>!excludedContacts.has(key)));
    onApply({entries:selected.filter(e=>!updates.has(e.id)),updates:selected.filter(e=>updates.has(e.id)),contacts,constraints:result.constraints||[],contact_notes:result.contact_notes||[],location_is_reference:result.location_is_reference,
      duplicate_count:removedDuplicates,replace_ids:[...dialog.querySelectorAll('[data-replace-legacy]:checked')].map(node=>node.dataset.replaceLegacy)});
    dialog.close();
  }
  render();dialog.showModal();
}
