const API_BASE = location.hostname.endsWith('.vercel.app')
  ? 'https://baltigo-live-cloud-production.up.railway.app/api'
  : '/api';

const state = {
  key: localStorage.getItem('baltigoApiKey') || '',
  dashboard: {}, system: {}, media: [], destinations: [], playlists: [], streams: [],
  streamFilter: 'all', currentView: 'overview',
};

const $ = (q, root = document) => root.querySelector(q);
const $$ = (q, root = document) => [...root.querySelectorAll(q)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtBytes = value => { if (!value) return '0 B'; const units=['B','KB','MB','GB','TB']; let n=value,i=0; while(n>=1024&&i<units.length-1){n/=1024;i++;} return `${n.toFixed(i?1:0)} ${units[i]}`; };
const fmtDuration = value => { if (value == null) return '—'; const s=Math.max(0,Math.round(value)); const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),x=s%60; return h?`${h}h ${m}min`:`${m}:${String(x).padStart(2,'0')}`; };
const fmtDate = value => value ? new Date(value).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'}) : '—';
const uptime = value => { if(!value) return '—'; const s=Math.max(0,Math.floor((Date.now()-new Date(value).getTime())/1000)); const h=Math.floor(s/3600),m=Math.floor((s%3600)/60); return h?`${h}h ${m}min`:`${m}min`; };
const statusLabels = {live:'Ao vivo',starting:'Iniciando',scheduled:'Agendada',recovering:'Reconectando',failed:'Falhou',stopped:'Parada',stopping:'Parando'};
const platformLabels = {tiktok:'TikTok',youtube:'YouTube',twitch:'Twitch',facebook:'Facebook',instagram:'Instagram',kick:'Kick',custom:'RTMP personalizado'};

function toast(message, type='') {
  const el=document.createElement('div'); el.className=`toast ${type}`; el.textContent=message; $('#toasts').append(el); setTimeout(()=>el.remove(),4200);
}
function empty(text){return `<div class="empty">${esc(text)}</div>`;}
function statusBadge(status){return `<span class="status ${esc(status)}">${esc(statusLabels[status]||status)}</span>`;}
function setBusy(button, busy, text='Aguarde...'){ if(!button)return; if(busy){button.dataset.oldText=button.textContent;button.disabled=true;button.textContent=text;} else {button.disabled=false;button.textContent=button.dataset.oldText||button.textContent;} }

async function api(path, options={}) {
  const headers = {...(options.headers||{})};
  if (state.key) headers['X-API-Key']=state.key;
  if (options.body && !(options.body instanceof FormData)) { headers['Content-Type']='application/json'; options.body=JSON.stringify(options.body); }
  let response;
  try { response = await fetch(API_BASE + path, {...options, headers}); }
  catch { throw new Error('Não foi possível conectar ao servidor. Verifique sua internet e tente novamente.'); }
  let data={}; try{data=await response.json();}catch{}
  if(response.status===401){lockApp('Chave de acesso inválida.'); throw new Error('Chave de acesso inválida.');}
  if(!response.ok) throw new Error(data.detail || `Erro ${response.status}`);
  return data;
}

async function publicHealth(){
  try{const r=await fetch(API_BASE+'/health',{cache:'no-store'}); return r.ok?await r.json():null;}catch{return null;}
}

function lockApp(message=''){
  $('#app').classList.add('hidden'); $('#auth-screen').classList.remove('hidden');
  if(message){$('#login-error').textContent=message;$('#login-error').classList.remove('hidden');}
  $('#login-key').value='';
}
function unlockApp(){ $('#auth-screen').classList.add('hidden'); $('#app').classList.remove('hidden'); $('#login-error').classList.add('hidden'); }

async function login(key){
  state.key=key.trim();
  if(!state.key) throw new Error('Informe a chave de acesso.');
  await api('/dashboard');
  localStorage.setItem('baltigoApiKey', state.key);
  unlockApp();
  await refreshAll();
}

function setView(name){
  state.currentView=name;
  $$('.view').forEach(x=>x.classList.toggle('active',x.id===`view-${name}`));
  $$('.nav-item[data-view]').forEach(x=>x.classList.toggle('active',x.dataset.view===name));
  $('#page-title').textContent={overview:'Visão geral',streams:'Transmissões',media:'Mídia',playlists:'Playlists',destinations:'Destinos'}[name]||name;
  window.scrollTo({top:0,behavior:'smooth'});
}

async function refreshAll(){
  try{
    const [dashboard,system,media,destinations,playlists,streams]=await Promise.all([
      api('/dashboard'), api('/system'), api('/media'), api('/destinations'), api('/playlists'), api('/streams')
    ]);
    Object.assign(state,{dashboard,system,media,destinations,playlists,streams});
    renderAll();
  }catch(e){if(!String(e.message).includes('Chave'))toast(e.message,'error');}
}
async function refreshLive(){
  if(!state.key||$('#app').classList.contains('hidden'))return;
  try{const [dashboard,system,streams]=await Promise.all([api('/dashboard'),api('/system'),api('/streams')]);Object.assign(state,{dashboard,system,streams});renderStats();renderStreams();renderSystem();renderOnboarding();}
  catch(e){if(!String(e.message).includes('Chave'))console.warn(e);}
}

function renderAll(){renderStats();renderStreams();renderMedia();renderDestinations();renderPlaylists();renderSystem();renderOnboarding();}
function renderStats(){
  const d=state.dashboard;
  const data=[['Ao vivo',d.live||0],['Agendadas',d.scheduled||0],['Vídeos',d.media||0],['Destinos',d.destinations||0]];
  $('#stats').innerHTML=data.map(([label,value])=>`<article class="stat"><span>${esc(label)}</span><strong>${value}</strong></article>`).join('');
}

function filteredStreams(){
  const f=state.streamFilter;
  if(f==='live')return state.streams.filter(x=>['live','starting'].includes(x.status));
  if(f==='scheduled')return state.streams.filter(x=>x.status==='scheduled');
  if(f==='problem')return state.streams.filter(x=>['recovering','failed'].includes(x.status)||x.last_error);
  return state.streams;
}
function streamRow(s){
  const source=s.media_name||s.playlist_name||'Fonte indisponível';
  const canStop=s.desired_state==='running'||['live','starting','recovering'].includes(s.status);
  const timeText=s.status==='live'?`No ar há ${uptime(s.started_at)}`:s.scheduled_at?`Início ${fmtDate(s.scheduled_at)}`:s.stopped_at?`Parada ${fmtDate(s.stopped_at)}`:'Ainda não iniciada';
  return `<article class="stream-row">
    <div class="stream-main"><strong>${esc(s.name)}</strong><small>${esc(source)} → ${esc(s.destination_name||'Destino')}</small>${s.last_error?`<small style="color:#ff8fa1">${esc(String(s.last_error).slice(0,180))}</small>`:''}</div>
    <div>${statusBadge(s.status)}</div>
    <div class="stream-meta">${esc(timeText)}<br>${s.restart_count?`${s.restart_count} reinício(s)`:'Sem reinícios'}</div>
    <div class="stream-actions">${canStop?`<button class="btn small danger" onclick="stopStream('${s.id}',this)">■ Parar</button>`:`<button class="btn small primary" onclick="startStream('${s.id}',this)">▶ Iniciar</button>`}<button class="btn small" onclick="showLogs('${s.id}')">Logs</button><button class="btn small ghost" onclick="deleteStream('${s.id}')">Excluir</button></div>
  </article>`;
}
function renderStreams(){
  const rows=filteredStreams();
  $('#streams-list').innerHTML=rows.length?rows.map(streamRow).join(''):empty('Nenhuma transmissão neste filtro.');
  $('#overview-streams').innerHTML=state.streams.length?`<div class="stack gap12">${state.streams.slice(0,4).map(streamRow).join('')}</div>`:empty('Nenhuma transmissão criada ainda.');
}

function mediaCard(m){
  const info=`${m.width||'?'}×${m.height||'?'} · ${m.fps?Math.round(m.fps):'?'} FPS · ${fmtDuration(m.duration_seconds)}`;
  return `<article class="media-card"><div class="media-preview"><button class="play-circle" onclick="previewMedia('${m.id}')">▶</button><span class="orientation-chip">${m.orientation==='vertical'?'Vertical 9:16':'Horizontal 16:9'}</span>${m.stream_ready?'<span class="ready-chip">Pronto</span>':''}</div><div class="media-body"><strong title="${esc(m.name)}">${esc(m.name)}</strong><div class="meta-line">${esc(info)}<br>${esc((m.video_codec||'?').toUpperCase())} / ${esc((m.audio_codec||'?').toUpperCase())} · ${fmtBytes(m.size_bytes)}</div><div class="card-actions"><button class="btn small" onclick="previewMedia('${m.id}')">Visualizar</button><button class="btn small danger" onclick="deleteMedia('${m.id}')">Excluir</button></div></div></article>`;
}
function renderMedia(){
  $('#media-count').textContent=`${state.media.length} ${state.media.length===1?'vídeo':'vídeos'}`;
  $('#media-list').innerHTML=state.media.length?state.media.map(mediaCard).join(''):empty('Envie seu primeiro vídeo para começar.');
  if(state.system.max_upload_bytes)$('#upload-limit').textContent=`Limite por arquivo: ${fmtBytes(state.system.max_upload_bytes)}`;
}

function platformName(p){return platformLabels[p]||p||'RTMP';}
function destinationCard(d){
  return `<article class="card"><div class="card-body"><div style="display:flex;justify-content:space-between;gap:12px"><div><span class="kicker">${esc(platformName(d.platform)).toUpperCase()}</span><strong style="margin-top:5px">${esc(d.name)}</strong></div>${d.enabled?'<span class="status live">Ativo</span>':'<span class="status stopped">Desativado</span>'}</div><div class="meta-line">${esc(d.host||d.rtmp_url)}<br>Chave: ${esc(d.stream_key_masked)}</div><div class="card-actions"><button class="btn small" onclick="checkDestination('${d.id}',this)">Testar servidor</button><button class="btn small" onclick="openDestinationDrawer('${d.id}')">Editar</button><button class="btn small danger" onclick="deleteDestination('${d.id}')">Excluir</button></div></div></article>`;
}
function renderDestinations(){ $('#destinations-list').innerHTML=state.destinations.length?state.destinations.map(destinationCard).join(''):empty('Nenhum destino conectado. Cadastre um RTMP para transmitir.'); }

function playlistCard(p){
  const names=p.items.slice(0,3).map(x=>x.media.name).join(' · ')+(p.items.length>3?'…':'');
  return `<article class="card"><div class="card-body"><span class="kicker">${p.orientation==='vertical'?'VERTICAL':'HORIZONTAL'}</span><strong style="margin-top:5px">${esc(p.name)}</strong><div class="meta-line">${p.items.length} vídeo(s) · ${fmtDuration(p.duration_seconds)} por ciclo<br>${esc(names||'Playlist vazia')}</div><div class="card-actions"><button class="btn small danger" onclick="deletePlaylist('${p.id}')">Excluir</button></div></div></article>`;
}
function renderPlaylists(){ $('#playlists-list').innerHTML=state.playlists.length?state.playlists.map(playlistCard).join(''):empty('Nenhuma playlist criada.'); }

function renderSystem(){
  const s=state.system;
  const healthy=!!s.worker_online;
  $('#system-pill').innerHTML=`<span class="status-led ${healthy?'ok':'bad'}"></span><span>${healthy?'Sistema operacional':'Worker offline'}</span>`;
  $('#sidebar-health').innerHTML=`<span class="status-led ${healthy?'ok':'bad'}"></span><div><strong>${healthy?'Tudo operacional':'Worker offline'}</strong><small>API e streaming</small></div>`;
  const pct=s.disk_total_bytes?Math.round((s.disk_used_bytes/s.disk_total_bytes)*100):0;
  $('#system-card').innerHTML=`<div class="system-list"><div class="system-row"><span>Worker</span><strong>${healthy?'Online':'Offline'}</strong></div><div class="system-row"><span>Armazenamento</span><strong>${s.storage_persistent?'Persistente':'Temporário'}</strong></div><div class="system-row"><span>Espaço usado</span><strong>${fmtBytes(s.disk_used_bytes)} / ${fmtBytes(s.disk_total_bytes)} (${pct}%)</strong></div><div class="system-row"><span>Preparação automática</span><strong>${s.normalize_uploads?'Ativa':'Desativada'}</strong></div></div>`;
  $('#system-warning').innerHTML=!s.storage_persistent?`<div class="notice"><span>⚠</span><div><strong>Armazenamento ainda temporário.</strong> Um redeploy pode apagar os vídeos. Estou usando esta instalação como ambiente de teste; para uso contínuo, o volume persistente deve estar ativo.</div></div>`:'';
  renderMedia();
}

function renderOnboarding(){
  const doneDest=state.destinations.length>0, doneMedia=state.media.length>0, doneStream=state.streams.length>0;
  const all=doneDest&&doneMedia&&doneStream;
  const el=$('#onboarding'); el.classList.toggle('hidden',all);
  if(all)return;
  el.innerHTML=`<div class="onboarding-head"><div><span class="kicker">PRIMEIROS PASSOS</span><h2>Configure sua primeira transmissão</h2><p>Três passos. Depois disso, o servidor continua sozinho.</p></div><span class="status ${doneDest&&doneMedia?'starting':'stopped'}">${[doneDest,doneMedia,doneStream].filter(Boolean).length}/3</span></div><div class="steps">
    <div class="step ${doneDest?'done':''}"><div class="step-top"><span class="step-num">${doneDest?'✓':'1'}</span></div><strong>Conecte um destino</strong><span>Adicione Server URL e Stream Key da plataforma.</span><button class="btn small" onclick="openDestinationDrawer()">${doneDest?'Ver destinos':'Conectar destino'}</button></div>
    <div class="step ${doneMedia?'done':''}"><div class="step-top"><span class="step-num">${doneMedia?'✓':'2'}</span></div><strong>Envie um vídeo</strong><span>Convertemos automaticamente para um formato confiável.</span><button class="btn small" onclick="setView('media')">${doneMedia?'Ver mídia':'Enviar vídeo'}</button></div>
    <div class="step ${doneStream?'done':''}"><div class="step-top"><span class="step-num">${doneStream?'✓':'3'}</span></div><strong>Crie a transmissão</strong><span>Escolha destino, vídeo e se deseja loop infinito.</span><button class="btn small" onclick="openStreamWizard()" ${(!doneDest||!doneMedia)?'disabled':''}>Criar transmissão</button></div>
  </div>`;
}

function openDrawer(content){$('#drawer-content').innerHTML=content;$('#drawer-backdrop').classList.remove('hidden');}
function closeDrawer(){$('#drawer-backdrop').classList.add('hidden');}
function openModal(content){$('#modal').innerHTML=content;$('#modal-backdrop').classList.remove('hidden');}
function closeModal(){const video=$('#modal video');if(video&&video.src?.startsWith('blob:'))URL.revokeObjectURL(video.src);$('#modal-backdrop').classList.add('hidden');$('#modal').innerHTML='';}
function drawerHead(title,copy){return `<div class="drawer-head"><div><span class="kicker">BALTIGO LIVE</span><h2>${esc(title)}</h2><p>${esc(copy)}</p></div><button class="icon-btn" onclick="closeDrawer()">×</button></div>`;}

const platformHelp={
  tiktok:'Cole o Server URL e a Stream Key exibidos pelo modo de software/encoder do TikTok.',
  youtube:'No YouTube Studio, abra a transmissão e copie URL do servidor e chave de transmissão.',
  twitch:'No Painel do Criador, copie a chave principal e use o servidor RTMP da sua região.',
  facebook:'Use as configurações de software de streaming do Facebook Live.',
  custom:'Use qualquer endpoint RTMP ou RTMPS. Se você recebeu uma URL completa, deixe a chave vazia.'
};
function openDestinationDrawer(id=null){
  const item=id?state.destinations.find(x=>x.id===id):null;
  const platform=item?.platform||'tiktok';
  openDrawer(`<div class="drawer-inner">${drawerHead(item?'Editar destino':'Novo destino','Conecte a plataforma sem compartilhar sua senha. A chave é criptografada no servidor.')}
    <form id="destination-form" class="form-grid">
      <div><span class="kicker">PLATAFORMA</span><div class="platform-grid" id="platform-grid">${['tiktok','youtube','twitch','custom'].map(p=>`<button type="button" class="platform-option ${platform===p?'active':''}" data-platform="${p}"><strong>${platformName(p)}</strong><span>${p==='custom'?'Qualquer servidor':'RTMP / RTMPS'}</span></button>`).join('')}</div></div>
      <input type="hidden" name="platform" value="${esc(platform)}" />
      <div id="platform-helper" class="helper">${esc(platformHelp[platform]||platformHelp.custom)}</div>
      <label class="field"><span>Nome do destino</span><input name="name" required minlength="2" value="${esc(item?.name||'')}" placeholder="Ex.: TikTok principal" /></label>
      <label class="field"><span>Server URL</span><input name="rtmp_url" required value="${esc(item?.rtmp_url||'')}" placeholder="rtmps://servidor/app" autocomplete="off" /><small>Pode ser RTMP ou RTMPS. Também aceitamos uma URL completa.</small></label>
      <label class="field"><span>Stream Key ${item?'(deixe em branco para manter a atual)':''}</span><input name="stream_key" type="password" ${item?'':'required'} autocomplete="new-password" placeholder="••••••••••••" /><small>A chave não será exibida novamente depois de salvar.</small></label>
      <div id="destination-error" class="form-error hidden"></div>
      <div class="drawer-actions"><button class="btn" type="button" onclick="closeDrawer()">Cancelar</button><button class="btn primary" type="submit">${item?'Salvar alterações':'Salvar destino'}</button></div>
    </form></div>`);
  $$('#platform-grid .platform-option').forEach(btn=>btn.onclick=()=>{$$('#platform-grid .platform-option').forEach(x=>x.classList.remove('active'));btn.classList.add('active');$('#destination-form [name=platform]').value=btn.dataset.platform;$('#platform-helper').textContent=platformHelp[btn.dataset.platform]||platformHelp.custom;});
  $('#destination-form').onsubmit=async e=>{e.preventDefault();const btn=e.submitter;setBusy(btn,true,'Salvando...');const f=new FormData(e.target);const body={name:f.get('name'),platform:f.get('platform'),rtmp_url:f.get('rtmp_url')};const key=f.get('stream_key');if(key)body.stream_key=key;try{if(item)await api(`/destinations/${item.id}`,{method:'PATCH',body});else await api('/destinations',{method:'POST',body:{...body,stream_key:key||''}});closeDrawer();toast(item?'Destino atualizado.':'Destino conectado.','success');await refreshAll();}catch(err){$('#destination-error').textContent=err.message;$('#destination-error').classList.remove('hidden');setBusy(btn,false);}};
}

async function checkDestination(id,button){setBusy(button,true,'Testando...');try{const r=await api(`/destinations/${id}/check`,{method:'POST'});toast(`Servidor alcançável em ${r.latency_ms} ms. A chave será validada ao iniciar.`,'success');}catch(e){toast(e.message,'error');}finally{setBusy(button,false);}}

function openPlaylistDrawer(){
  if(!state.media.length){toast('Envie pelo menos um vídeo antes de criar uma playlist.','error');setView('media');return;}
  let selected=[];
  const render=()=>{
    openDrawer(`<div class="drawer-inner">${drawerHead('Nova playlist','Adicione os vídeos na ordem em que devem tocar. Todos precisam ter a mesma orientação.')}
      <form id="playlist-form" class="form-grid"><label class="field"><span>Nome da playlist</span><input name="name" minlength="2" required placeholder="Ex.: Programação principal" /></label>
      <div><span class="kicker">VÍDEOS DISPONÍVEIS</span><div class="select-list" style="margin-top:8px">${state.media.map(m=>`<button type="button" class="select-card" data-add-media="${m.id}" ${selected.includes(m.id)?'disabled':''}><div><strong>${esc(m.name)}</strong><small>${m.orientation==='vertical'?'Vertical':'Horizontal'} · ${fmtDuration(m.duration_seconds)}</small></div><span>＋</span></button>`).join('')}</div></div>
      <div><span class="kicker">ORDEM DA PLAYLIST</span><div id="selected-order" class="order-list" style="margin-top:8px">${selected.length?selected.map((id,i)=>{const m=state.media.find(x=>x.id===id);return `<div class="order-row"><span class="order-index">${i+1}</span><div><strong>${esc(m.name)}</strong><small class="muted">${m.orientation==='vertical'?'Vertical':'Horizontal'}</small></div><div class="order-actions"><button type="button" onclick="movePlaylistItem(${i},-1)">↑</button><button type="button" onclick="movePlaylistItem(${i},1)">↓</button><button type="button" onclick="removePlaylistItem(${i})">×</button></div></div>`;}).join(''):empty('Adicione pelo menos um vídeo.')}</div></div>
      <div id="playlist-error" class="form-error hidden"></div><div class="drawer-actions"><button class="btn" type="button" onclick="closeDrawer()">Cancelar</button><button class="btn primary" type="submit">Criar playlist</button></div></form></div>`);
    $$('[data-add-media]').forEach(b=>b.onclick=()=>{const m=state.media.find(x=>x.id===b.dataset.addMedia);const first=selected.length?state.media.find(x=>x.id===selected[0]):null;if(first&&m.orientation!==first.orientation){toast('Use apenas vídeos da mesma orientação na playlist.','error');return;}selected.push(m.id);render();});
    $('#playlist-form').onsubmit=async e=>{e.preventDefault();if(!selected.length){toast('Adicione ao menos um vídeo.','error');return;}const btn=e.submitter;setBusy(btn,true,'Criando...');const name=new FormData(e.target).get('name');try{await api('/playlists',{method:'POST',body:{name,media_ids:selected}});closeDrawer();toast('Playlist criada.','success');await refreshAll();}catch(err){$('#playlist-error').textContent=err.message;$('#playlist-error').classList.remove('hidden');setBusy(btn,false);}};
  };
  window.movePlaylistItem=(index,dir)=>{const next=index+dir;if(next<0||next>=selected.length)return;[selected[index],selected[next]]=[selected[next],selected[index]];render();};
  window.removePlaylistItem=index=>{selected.splice(index,1);render();};
  render();
}

function openStreamWizard(){
  if(!state.destinations.length){toast('Conecte um destino antes de criar uma transmissão.','error');openDestinationDrawer();return;}
  if(!state.media.length&&!state.playlists.length){toast('Envie um vídeo antes de criar uma transmissão.','error');setView('media');return;}
  const w={step:1,destination_id:state.destinations[0].id,source_type:state.playlists.length?'playlist':'media',source_id:state.playlists[0]?.id||state.media[0]?.id||'',name:'',loop:true,mode:'now',scheduled_at:''};
  const render=()=>{
    const steps=`<div class="wizard-progress"><span class="${w.step>=1?'active':''}"></span><span class="${w.step>=2?'active':''}"></span><span class="${w.step>=3?'active':''}"></span></div>`;
    let body='';
    if(w.step===1)body=`<span class="kicker">1 · DESTINO</span><h3>Onde essa transmissão vai aparecer?</h3><div class="select-list">${state.destinations.filter(x=>x.enabled).map(d=>`<button class="select-card ${w.destination_id===d.id?'active':''}" data-w-dest="${d.id}"><div><strong>${esc(d.name)}</strong><small>${esc(platformName(d.platform))} · ${esc(d.host||'RTMP')}</small></div><span>${w.destination_id===d.id?'✓':'›'}</span></button>`).join('')}</div>`;
    if(w.step===2){const sources=[...state.playlists.map(p=>({id:p.id,type:'playlist',name:p.name,meta:`Playlist · ${p.items.length} vídeos · ${p.orientation==='vertical'?'Vertical':'Horizontal'}`})),...state.media.map(m=>({id:m.id,type:'media',name:m.name,meta:`Vídeo · ${m.orientation==='vertical'?'Vertical':'Horizontal'} · ${fmtDuration(m.duration_seconds)}`}))];body=`<span class="kicker">2 · CONTEÚDO</span><h3>O que o servidor vai reproduzir?</h3><div class="select-list">${sources.map(s=>`<button class="select-card ${w.source_type===s.type&&w.source_id===s.id?'active':''}" data-w-source="${s.type}:${s.id}"><div><strong>${esc(s.name)}</strong><small>${esc(s.meta)}</small></div><span>${w.source_type===s.type&&w.source_id===s.id?'✓':'›'}</span></button>`).join('')}</div>`;}
    if(w.step===3)body=`<span class="kicker">3 · INÍCIO</span><h3>Últimos ajustes</h3><div class="form-grid"><label class="field"><span>Nome da transmissão</span><input id="w-name" value="${esc(w.name)}" placeholder="Ex.: AniNexus 24/7" /></label><label class="field"><span>Reprodução</span><select id="w-loop"><option value="true" ${w.loop?'selected':''}>Loop contínuo</option><option value="false" ${!w.loop?'selected':''}>Tocar uma vez e parar</option></select></label><label class="field"><span>Quando iniciar?</span><select id="w-mode"><option value="now" ${w.mode==='now'?'selected':''}>Agora</option><option value="schedule" ${w.mode==='schedule'?'selected':''}>Agendar</option><option value="later" ${w.mode==='later'?'selected':''}>Criar sem iniciar</option></select></label><label id="w-date-field" class="field ${w.mode==='schedule'?'':'hidden'}"><span>Data e hora</span><input id="w-date" type="datetime-local" value="${esc(w.scheduled_at)}" /></label><div class="helper">O worker cuida da transmissão na nuvem. Depois de iniciar, você pode fechar o navegador.</div></div>`;
    openDrawer(`<div class="drawer-inner">${drawerHead('Nova transmissão','Um fluxo curto para evitar configurações erradas.')}${steps}<div class="form-grid">${body}<div id="wizard-error" class="form-error hidden"></div></div><div class="drawer-actions">${w.step>1?'<button class="btn" id="w-back">Voltar</button>':'<button class="btn" onclick="closeDrawer()">Cancelar</button>'}<button class="btn primary" id="w-next">${w.step===3?(w.mode==='now'?'Criar e iniciar':'Criar transmissão'):'Continuar'}</button></div></div>`);
    $$('[data-w-dest]').forEach(b=>b.onclick=()=>{w.destination_id=b.dataset.wDest;render();});
    $$('[data-w-source]').forEach(b=>b.onclick=()=>{const [type,id]=b.dataset.wSource.split(':');w.source_type=type;w.source_id=id;render();});
    if($('#w-back'))$('#w-back').onclick=()=>{w.step--;render();};
    if(w.step===3){$('#w-name').oninput=e=>w.name=e.target.value;$('#w-loop').onchange=e=>w.loop=e.target.value==='true';$('#w-mode').onchange=e=>{w.mode=e.target.value;$('#w-date-field').classList.toggle('hidden',w.mode!=='schedule');$('#w-next').textContent=w.mode==='now'?'Criar e iniciar':'Criar transmissão';};$('#w-date').onchange=e=>w.scheduled_at=e.target.value;}
    $('#w-next').onclick=async e=>{if(w.step<3){w.step++;render();return;}w.name=$('#w-name').value.trim();w.loop=$('#w-loop').value==='true';w.mode=$('#w-mode').value;w.scheduled_at=$('#w-date').value;if(!w.name){$('#wizard-error').textContent='Dê um nome para a transmissão.';$('#wizard-error').classList.remove('hidden');return;}if(w.mode==='schedule'&&!w.scheduled_at){$('#wizard-error').textContent='Escolha a data e hora do agendamento.';$('#wizard-error').classList.remove('hidden');return;}setBusy(e.currentTarget,true,'Criando...');const payload={name:w.name,destination_id:w.destination_id,loop:w.loop,media_id:w.source_type==='media'?w.source_id:null,playlist_id:w.source_type==='playlist'?w.source_id:null,start_now:w.mode==='now',scheduled_at:w.mode==='schedule'?new Date(w.scheduled_at).toISOString():null};try{await api('/streams',{method:'POST',body:payload});closeDrawer();toast(w.mode==='now'?'Transmissão criada. O worker está iniciando.':'Transmissão criada.','success');setView('streams');await refreshAll();}catch(err){$('#wizard-error').textContent=err.message;$('#wizard-error').classList.remove('hidden');setBusy(e.currentTarget,false);}};
  };
  render();
}

async function previewMedia(id){
  const m=state.media.find(x=>x.id===id); openModal(`<div class="drawer-head"><div><span class="kicker">PRÉ-VISUALIZAÇÃO</span><h2 style="margin:3px 0">${esc(m?.name||'Vídeo')}</h2></div><button class="icon-btn" onclick="closeModal()">×</button></div><div class="helper">Carregando vídeo...</div>`);
  try{const r=await fetch(`${API_BASE}/media/${id}/file`,{headers:{'X-API-Key':state.key}});if(!r.ok)throw new Error('Não foi possível carregar o vídeo.');const blob=await r.blob();const url=URL.createObjectURL(blob);$('#modal').innerHTML=`<div class="drawer-head"><div><span class="kicker">PRÉ-VISUALIZAÇÃO</span><h2 style="margin:3px 0">${esc(m?.name||'Vídeo')}</h2></div><button class="icon-btn" onclick="closeModal()">×</button></div><video src="${url}" controls autoplay muted playsinline></video>`;}catch(e){$('#modal').innerHTML=`<div class="drawer-head"><h2>Não foi possível abrir o vídeo</h2><button class="icon-btn" onclick="closeModal()">×</button></div><div class="form-error">${esc(e.message)}</div>`;}
}

async function showLogs(id){const s=state.streams.find(x=>x.id===id);openModal(`<div class="drawer-head"><div><span class="kicker">LOGS DO WORKER</span><h2 style="margin:3px 0">${esc(s?.name||'Transmissão')}</h2></div><button class="icon-btn" onclick="closeModal()">×</button></div><div class="helper">Carregando...</div>`);try{const data=await api(`/streams/${id}/logs?lines=250`);$('#modal').innerHTML=`<div class="drawer-head"><div><span class="kicker">LOGS DO WORKER</span><h2 style="margin:3px 0">${esc(s?.name||'Transmissão')}</h2><p>O endereço RTMP e a chave ficam ocultos.</p></div><button class="icon-btn" onclick="closeModal()">×</button></div><code class="log">${esc(data.lines.join('\n')||'Nenhum log ainda.')}</code>`;}catch(e){toast(e.message,'error');closeModal();}}

async function startStream(id,button){setBusy(button,true,'Iniciando...');try{await api(`/streams/${id}/start`,{method:'POST'});toast('O worker recebeu o comando de iniciar.','success');await refreshLive();}catch(e){toast(e.message,'error');}finally{setBusy(button,false);}}
async function stopStream(id,button){if(!confirm('Parar esta transmissão agora?'))return;setBusy(button,true,'Parando...');try{await api(`/streams/${id}/stop`,{method:'POST'});toast('Parada solicitada.','success');await refreshLive();}catch(e){toast(e.message,'error');}finally{setBusy(button,false);}}
async function deleteStream(id){if(!confirm('Excluir esta transmissão?'))return;try{await api(`/streams/${id}`,{method:'DELETE'});toast('Transmissão excluída.','success');await refreshAll();}catch(e){toast(e.message,'error');}}
async function deleteMedia(id){if(!confirm('Excluir este vídeo?'))return;try{await api(`/media/${id}`,{method:'DELETE'});toast('Vídeo excluído.','success');await refreshAll();}catch(e){toast(e.message,'error');}}
async function deleteDestination(id){if(!confirm('Excluir este destino?'))return;try{await api(`/destinations/${id}`,{method:'DELETE'});toast('Destino excluído.','success');await refreshAll();}catch(e){toast(e.message,'error');}}
async function deletePlaylist(id){if(!confirm('Excluir esta playlist?'))return;try{await api(`/playlists/${id}`,{method:'DELETE'});toast('Playlist excluída.','success');await refreshAll();}catch(e){toast(e.message,'error');}}

function uploadFile(file){
  if(!file)return; if(state.system.max_upload_bytes&&file.size>state.system.max_upload_bytes){toast(`Arquivo maior que o limite de ${fmtBytes(state.system.max_upload_bytes)}.`,'error');return;}
  const box=$('#upload-progress');box.classList.remove('hidden');$('#upload-name').textContent=file.name;$('#upload-percent').textContent='0%';$('#upload-bar').style.width='0%';$('#upload-status').textContent='Transferindo arquivo';
  const fd=new FormData();fd.append('file',file);const xhr=new XMLHttpRequest();xhr.open('POST',API_BASE+'/media');xhr.setRequestHeader('X-API-Key',state.key);xhr.upload.onprogress=e=>{if(!e.lengthComputable)return;const pct=Math.round((e.loaded/e.total)*100);$('#upload-percent').textContent=`${pct}%`;$('#upload-bar').style.width=`${pct}%`;if(pct>=100)$('#upload-status').textContent='Upload concluído. Preparando H.264/AAC — isso pode levar alguns minutos...';};xhr.onload=async()=>{if(xhr.status>=200&&xhr.status<300){toast('Vídeo preparado e pronto para streaming.','success');box.classList.add('hidden');await refreshAll();}else{let msg='Falha ao enviar o vídeo.';try{msg=JSON.parse(xhr.responseText).detail||msg;}catch{}toast(msg,'error');box.classList.add('hidden');}};xhr.onerror=()=>{toast('A conexão caiu durante o upload.','error');box.classList.add('hidden');};xhr.send(fd);
}

function bindEvents(){
  $('#login-form').onsubmit=async e=>{e.preventDefault();const btn=e.submitter;setBusy(btn,true,'Entrando...');$('#login-error').classList.add('hidden');try{await login($('#login-key').value);}catch(err){$('#login-error').textContent=err.message;$('#login-error').classList.remove('hidden');}finally{setBusy(btn,false);}};
  $('#logout-btn').onclick=()=>{localStorage.removeItem('baltigoApiKey');state.key='';lockApp();};
  $$('.nav-item[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
  $$('[data-go]').forEach(b=>b.onclick=()=>setView(b.dataset.go));
  $$('[data-open="destination"]').forEach(b=>b.onclick=()=>openDestinationDrawer());
  $$('[data-open="playlist"]').forEach(b=>b.onclick=()=>openPlaylistDrawer());
  $$('[data-open="stream"],#top-new-stream').forEach(b=>b.onclick=()=>openStreamWizard());
  $$('.filter').forEach(b=>b.onclick=()=>{$$('.filter').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.streamFilter=b.dataset.streamFilter;renderStreams();});
  $('#media-upload').onchange=e=>{uploadFile(e.target.files[0]);e.target.value='';};
  $('#drawer-backdrop').onclick=e=>{if(e.target===e.currentTarget)closeDrawer();};
  $('#modal-backdrop').onclick=e=>{if(e.target===e.currentTarget)closeModal();};
  window.addEventListener('keydown',e=>{if(e.key==='Escape'){closeDrawer();closeModal();}});
}

Object.assign(window,{setView,openDestinationDrawer,openPlaylistDrawer,openStreamWizard,closeDrawer,closeModal,checkDestination,previewMedia,showLogs,startStream,stopStream,deleteStream,deleteMedia,deleteDestination,deletePlaylist});

async function boot(){
  bindEvents();
  const health=await publicHealth();
  if(!state.key){lockApp();return;}
  try{await api('/dashboard');unlockApp();await refreshAll();}
  catch{lockApp(health?'Sua chave expirou ou está incorreta.':'O servidor está indisponível no momento.');}
}

boot();
setInterval(refreshLive,5000);
setInterval(()=>{if(state.key&&!$('#app').classList.contains('hidden'))refreshAll();},60000);
setInterval(()=>{if(state.currentView==='streams')renderStreams();},30000);
