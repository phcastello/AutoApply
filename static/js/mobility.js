import { escHtml as esc } from './api.js';

let destinations=[];
const $=id=>document.getElementById(id);
const bool=value=>value===''?null:value==='true';
const split=value=>value.split(',').map(x=>x.trim()).filter(Boolean);
const tierOptions=value=>['','S','A','B','C','D'].map(t=>`<option value="${t}" ${value===t?'selected':''}>${t?'Tier '+t:'Sem prioridade'}</option>`).join('');

function collectDestinations(){
  document.querySelectorAll('[data-destination-country]').forEach(node=>destinations[Number(node.dataset.destinationCountry)].country=node.value.trim());
  document.querySelectorAll('[data-destination-priority]').forEach(node=>destinations[Number(node.dataset.destinationPriority)].priority=node.value||null);
}
function renderDestinations(){
  $('mobility-destinations').innerHTML=destinations.map((d,i)=>`<div class="mobility-destination"><label>País de interesse<input data-destination-country="${i}" value="${esc(d.country)}"></label><label>Prioridade<select data-destination-priority="${i}">${tierOptions(d.priority||'')}</select></label><button type="button" class="btn btn-ghost" data-remove-destination="${i}">Remover país</button></div>`).join('')||'<p>Nenhum país de realocação selecionado. Cadastre seus destinos abaixo.</p>';
}

export function loadMobility(criteria,profile){
  const m=criteria.mobility;
  destinations=structuredClone(m.destinations||[]);renderDestinations();
  for(const key of ['domestic_relocation','international_relocation'])$(`mobility-${key}`).value=m[key]===null?'':String(m[key]);
  for(const key of ['relocation_conditions','available_from','availability_notes','salary_min','salary_currency','salary_period'])$(`mobility-${key}`).value=m[key]??'';
  $('mobility-work_authorization_countries').value=(m.work_authorization_countries||[]).join(', ');
  $('mobility-current-location').textContent=profile.location_is_reference?'A localização do perfil é apenas referência. Confirme sua residência em Meu perfil antes de avaliar trabalho remoto.':`Residência informada em Meu perfil: ${[profile.city,profile.state,profile.country].filter(Boolean).join(', ')||'não informada'}. Destinos e localidades aceitas não alteram sua residência.`;
}

export function readMobility(cities){
  collectDestinations();
  return {direct_locations:[...cities], destinations:structuredClone(destinations),
    domestic_relocation:bool($('mobility-domestic_relocation').value), international_relocation:bool($('mobility-international_relocation').value),
    relocation_conditions:$('mobility-relocation_conditions').value.trim(),
    remote_enabled:$('assistant-work-modes').querySelector('[value=remote]').checked,
    available_from:$('mobility-available_from').value,availability_notes:$('mobility-availability_notes').value.trim(),
    work_authorization_countries:split($('mobility-work_authorization_countries').value),
    salary_min:$('mobility-salary_min').value===''?null:Number($('mobility-salary_min').value),
    salary_currency:$('mobility-salary_currency').value.trim().toUpperCase(), salary_period:$('mobility-salary_period').value||null};
}

export function mobilitySummary(cities){
  const m=readMobility(cities);
  const tiers=['S','A','B','C','D',null].map(t=>{
    const values=m.destinations.filter(d=>d.priority===t).map(d=>d.country);
    return values.length?`${t?'Tier '+t:'Sem prioridade'}: ${values.join(', ')}.`:'';
  }).filter(Boolean).join('\n');
  const willingness=v=>v===true?'disponível para avaliar ofertas':v===false?'não disponível':'a confirmar';
  const modes=[...document.querySelectorAll('#assistant-work-modes input:checked')].map(e=>({remote:'remoto',hybrid:'híbrido','on-site':'presencial'})[e.value]);
  return [`Modalidades: ${modes.join(', ')||'não definidas; confirmar com a empresa'}.`,
    `Localidades diretamente aceitas: ${cities.join('; ')||'nenhuma definida'}.`,
    `Mudança nacional: ${willingness(m.domestic_relocation)}. Mudança internacional: ${willingness(m.international_relocation)}.`,
    tiers, 'Países selecionados aceitam avaliação em qualquer cidade, sem cadastro de municípios.',
    `Remoto: ${m.remote_enabled?'aceito quando permitir contratação e trabalho da residência atual; residência obrigatória em outro destino exige avaliar mudança':'não aceito'}.`,
    `Condições: ${m.relocation_conditions||'a definir; remuneração e custo de vida exigem revisão'}.`,
    `Disponibilidade futura: ${[m.available_from,m.availability_notes].filter(Boolean).join(' — ')||'a combinar'}.`,
    'Prioridades ordenam; não excluem destinos selecionados. Autorização de trabalho não é presumida.'
  ].filter(Boolean).join('\n');
}

export function bindMobility(onChange){
  $('mobility-add-country').onclick=()=>{
    collectDestinations();const name=$('mobility-new-country').value.trim();if(!name)return;
    destinations.push({country:name,priority:$('mobility-new-priority').value||null});
    $('mobility-new-country').value='';renderDestinations();onChange();
  };
  $('mobility-destinations').onclick=event=>{
    const button=event.target.closest('[data-remove-destination]');if(!button)return;
    collectDestinations();destinations.splice(Number(button.dataset.removeDestination),1);renderDestinations();onChange();
  };
  $('assistant-mobility').addEventListener('input',onChange);
  $('assistant-mobility').addEventListener('change',onChange);
}

export const geographyLabels={direct:'Localidade diretamente aceita',remote:'Remoto compatível',relocation:'Oportunidade com realocação',review:'Necessita revisão',outside:'Fora das preferências'};
export function compareGeography(a,b,sort){
  const x=a.match.eligibility,y=b.match.eligibility;
  const score=b.match.score-a.match.score,priority=(y.country_priority||0)-(x.country_priority||0);
  if(sort==='professional')return score||priority;
  const outside=Number(x.category==='outside')-Number(y.category==='outside');
  if(outside)return outside;
  if(sort==='country')return priority||score;
  if(sort==='relocation'){
    const movement=e=>e.relocation_required===false?0:e.relocation_required===true?1:2;
    return movement(x)-movement(y)||score||priority;
  }
  return (b.match.ranking_score??b.match.score)-(a.match.ranking_score??a.match.score)||score||Number(y.relocation_required===false)-Number(x.relocation_required===false);
}
