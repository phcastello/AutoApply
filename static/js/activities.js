import { escHtml as esc } from './api.js';

export function activityEditor(activities, index, company) {
  const labels={title:'Título / cliente ou projeto',text:'Descrição profissional autorizada',start_date:'Início (preserve aproximações)',end_date:'Fim',technologies:'Tecnologias (separadas por vírgula)'};
  return `<section class="activity-editor"><h4>Atuações por cliente ou projeto</h4>
    <p>Empresa do vínculo contratual: <strong>${esc(company || 'Informe a empresa acima')}</strong></p>
    ${activities.map((a, ai) => `<fieldset data-activity-card><legend>${esc(a.title || 'Nova atividade')}</legend>
      <div class="assistant-grid">${Object.entries(labels).map(([key,label]) => {
        const attrs=`data-index="${index}" data-activity="${ai}" data-activity-field="${key}"`;
        const value=esc(key==='technologies'?(a[key]||[]).join(', '):a[key]||'');
        return `<label class="${['title','text','technologies'].includes(key)?'activity-wide':''}">${label}${key==='title'?`<input ${attrs} value="${value}">`:`<textarea rows="${key==='text'?4:2}" ${attrs}>${value}</textarea>`}</label>`;
      }).join('')}</div>
      ${a.date_notes?.length?`<p class="text-dim">Observações de datas: ${esc(a.date_notes.join(' · '))}</p>`:''}
      <button type="button" class="btn btn-ghost" data-remove-activity="${index}:${ai}">Excluir atividade</button>
    </fieldset>`).join('')}
    <button type="button" class="btn btn-ghost" data-add-activity="${index}">Adicionar atividade</button></section>`;
}

export function collectActivities(root, entries) {
  root.querySelectorAll('[data-activity-field]').forEach(node => {
    const activity=entries[Number(node.dataset.index)]?.activities?.[Number(node.dataset.activity)];
    if(activity)activity[node.dataset.activityField]=node.dataset.activityField==='technologies'?node.value.split(',').map(v=>v.trim()).filter(Boolean):node.value;
  });
}

export function changeActivity(target, entries) {
  const add=target.closest('[data-add-activity]'), remove=target.closest('[data-remove-activity]');
  if(add){const entry=entries[Number(add.dataset.addActivity)];(entry.activities??=[]).push({title:'Nova atividade',text:'',start_date:'',end_date:'',technologies:[]});return Number(add.dataset.addActivity);}
  if(remove){const [i,a]=remove.dataset.removeActivity.split(':').map(Number);entries[i].activities.splice(a,1);return i;}
  return null;
}

const normalize=value=>(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/\s+/g,' ').trim();
const activityKey=a=>normalize(a.title).split(/\s+para prospeccao\b/)[0];
export function proposeUpdates(incoming, existing) {
  const entries=[], updates=[];let duplicates=0;
  for(const entry of incoming){
    if(existing.some(e=>(e.import_key||e.id)===(entry.import_key||entry.id))){duplicates++;continue;}
    const matches=existing.filter(e=>e.category==='experience'&&entry.category==='experience'&&normalize(e.organization)===normalize(entry.organization)&&e.start_date===entry.start_date&&(normalize(e.title)===normalize(entry.title)||(e.source_document_id&&e.source_document_id===entry.source_document_id)));
    if(matches.length!==1){entries.push(entry);continue;}
    const old=matches[0], known=new Set((old.activities||[]).map(activityKey));
    const additions=(entry.activities||[]).filter(a=>!known.has(activityKey(a)));
    const notes=(old.date_notes||[]).filter(n=>!/^atuacao (com|para) /.test(normalize(n)));
    if(!additions.length&&notes.length===(old.date_notes||[]).length){duplicates++;continue;}
    updates.push({target_id:old.id,before:old,incoming:entry,proposed:{...structuredClone(old),activities:[...structuredClone(old.activities||[]),...structuredClone(additions)],date_notes:notes,import_key:entry.import_key,import_version:3,confirmed:false}});
  }
  return {entries,updates,duplicates};
}
