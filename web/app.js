const API_BASE = location.hostname.endsWith('.vercel.app')
  ? 'https://baltigo-live-cloud-production.up.railway.app/api'
  : '/api';

const state = {
  key: localStorage.getItem('baltigoApiKey') || '',
  media: [], destinations: [], streams: [], system: {},
  mediaId: localStorage.getItem('baltigoMediaId') || '',
  destinationId: localStorage.getItem('baltigoDestinationId') || '',
};

const $ = (q, root=document) => root.querySelector(q);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtDuration = value => { if(value == null) return '—'; const s=Math.round(value),m=Math.floor(s/60),x=s%60; return `${m}:${String(x).padStart(2,'0')}`; };
const fmtDate = value => value ? new Date(value).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'}) : '—';
const statusLabel = {live:'Ao vivo',starting:'Iniciando',recovering:'Reconectando',scheduled:'Agendada',stopped:'Parada',stopping:'Parando',failed:'Falhou'};

function toast(message, type=''){
  const el=document.createElement('div'); el.className=`toast ${type}`; el.textContent=message; $('#toasts').append(el); setTimeout(()=>el.remove(),4200);
}
function showAuth(message=''){
  $('#app').classList.add('hidden'); $('#auth').classList.remove('hidden');
  $('#login-error').classList.toggle('hidden',!message); $('#login-error').textContent=message;
}
function showApp(){ $('#auth').classList.add('hidden'); $('#app').classList.remove('hidden'); }

async function api(path, options={}){
  const headers={...(options.headers||{})};
  if(state.key) headers['X-API-Key']=state.key;
  if(options.body && !(options.body instanceof FormData)){ headers['Content-Type']='application/json'; options.body=JSON.stringify(options.body); }
  let res;
  try{res=await fetch(API_BASE+path,{...options,headers});}catch{throw new Error('Não foi possível conectar ao servidor.');}
  let data={}; try{data=await res.json();}catch{}
  if(res.status===401){ localStorage.removeItem('baltigoApiKey'); state.key=''; showAuth('Código de acesso inválido.'); throw new Error('Código de acesso inválido.'); }
  if(!res.ok) throw new Error(data.detail||`Erro ${res.status}`);
  return data;
}

function selectedMedia(){return state.media.find(x=>x.id===state.mediaId)||null;}
function selectedDestination(){return state.destinations.find(x=>x.id===state.destinationId)||null;}
function activeStream(){return state.streams.find(x=>x.desired_state==='running'||['live','starting','recovering'].includes(x.status))||null;}

function chooseDefaults(){
  if(!state.media.some(x=>x.id===state.mediaId)) state.mediaId=state.media[0]?.id||'';
  if(!state.destinations.some(x=>x.id===state.destinationId)) state.destinationId=state.destinations.find(x=>x.platform==='tiktok')?.id||state.destinations[0]?.id||'';
  localStorage.setItem('baltigoMediaId',state.mediaId);
  localStorage.setItem('baltigoDestinationId',state.destinationId);
}

async function refreshAll(){
  const [media,destinations,streams,system]=await Promise.all([api('/media'),api('/destinations'),api('/streams'),api('/system')]);
  Object.assign(state,{media,destinations,streams,system}); chooseDefaults(); render();
}
async function refreshLive(){
  if(!state.key)return;
  try{const [streams,system]=await Promise.all([api('/streams'),api('/system')]);Object.assign(state,{streams,system});renderStatus();renderAdvancedStreams();}catch(e){console.warn(e);}
}

function render(){ renderStatus(); renderSteps(); renderAdvanced(); }
function renderStatus(){
  const healthy=!!state.system.worker_online;
  $('#cloud-status').className=`cloud-status ${healthy?'ok':'bad'}`;
  $('#cloud-status').textContent=healthy?'Servidor online':'Servidor com problema';
  const live=activeStream(); const box=$('#live-banner');
  if(!live){box.classList.add('hidden');box.innerHTML='';return;}
  box.classList.remove('hidden');
  const source=live.media_name||live.playlist_name||'Vídeo';
  box.innerHTML=`<div class="live-info"><span class="live-dot"></span><div><strong>${live.status==='live'?'Sua LIVE está no ar':esc(statusLabel[live.status]||live.status)}</strong><small>${esc(source)} → ${esc(live.destination_name||'TikTok')}</small></div></div><button class="btn danger" onclick="stopLive('${live.id}',this)">■ Parar LIVE</button>`;
}

function renderSteps(){
  const media=selectedMedia(),dest=selectedDestination(),live=activeStream();
  $('#video-step').classList.toggle('complete',!!media);
  $('#video-step .step-number').textContent=media?'✓':'1';
  $('#selected-video').className=`selection ${media?'':'empty-selection'}`;
  $('#selected-video').innerHTML=media?`<strong>${esc(media.name)}</strong><small>${media.orientation==='vertical'?'Vertical 9:16':'Horizontal 16:9'} · ${fmtDuration(media.duration_seconds)} · pronto para LIVE</small>`:'Nenhum vídeo escolhido';
  $('.upload-button').childNodes[0].textContent=media?'Trocar vídeo':'Enviar vídeo';

  $('#tiktok-step').classList.toggle('complete',!!dest);
  $('#tiktok-step .step-number').textContent=dest?'✓':'2';
  $('#selected-destination').className=`selection ${dest?'':'empty-selection'}`;
  $('#selected-destination').innerHTML=dest?`<strong>${esc(dest.name)}</strong><small>${esc(dest.host||'TikTok')} · conectado</small>`:'TikTok ainda não conectado';
  $('#connect-tiktok').textContent=dest?'Atualizar conexão':'Conectar TikTok';

  const ready=!!media&&!!dest&&!live&&!!state.system.worker_online;
  $('#start-step').classList.toggle('complete',!!media&&!!dest);
  $('#start-step .step-number').textContent=media&&dest?'✓':'3';
  $('#start-live').disabled=!ready;
  $('#start-live').textContent=live?'LIVE já iniciada':'▶ Iniciar LIVE agora';
  $('#ready-text').textContent=live?'Sua transmissão já está sendo executada.':!state.system.worker_online?'O servidor de streaming está indisponível no momento.':media&&dest?'Tudo pronto. Clique abaixo para entrar ao vivo.':!media&&!dest?'Envie um vídeo e conecte o TikTok.':!media?'Falta apenas escolher o vídeo.':'Falta apenas conectar o TikTok.';
}

function renderAdvanced(){renderAdvancedMedia();renderAdvancedDestinations();renderAdvancedStreams();}
function renderAdvancedMedia(){
  $('#media-list').innerHTML=state.media.length?state.media.map(m=>`<div class="list-row"><div class="list-main"><strong>${esc(m.name)}</strong><small>${m.orientation==='vertical'?'Vertical':'Horizontal'} · ${fmtDuration(m.duration_seconds)}</small></div><div class="list-actions">${m.id===state.mediaId?'<span class="selected-tag">Em uso</span>':`<button class="btn small" onclick="useMedia('${m.id}')">Usar</button>`}<button class="btn small danger" onclick="removeMedia('${m.id}')">Excluir</button></div></div>`).join(''):'<div class="empty">Nenhum vídeo enviado.</div>';
}
function renderAdvancedDestinations(){
  $('#destination-list').innerHTML=state.destinations.length?state.destinations.map(d=>`<div class="list-row"><div class="list-main"><strong>${esc(d.name)}</strong><small>${esc(d.host||d.rtmp_url)}</small></div><div class="list-actions">${d.id===state.destinationId?'<span class="selected-tag">Em uso</span>':`<button class="btn small" onclick="useDestination('${d.id}')">Usar</button>`}<button class="btn small" onclick="testDestination('${d.id}',this)">Testar</button><button class="btn small" onclick="openTikTok('${d.id}')">Editar</button></div></div>`).join(''):'<div class="empty">Nenhuma conexão salva.</div>';
}
function renderAdvancedStreams(){
  $('#stream-list').innerHTML=state.streams.length?state.streams.map(s=>`<div class="list-row"><div class="list-main"><strong>${esc(s.name)}</strong><small>${esc(s.media_name||s.playlist_name||'Vídeo')} · ${fmtDate(s.created_at)}</small></div><div class="list-actions"><span class="status ${esc(s.status)}">${esc(statusLabel[s.status]||s.status)}</span>${s.desired_state==='running'?`<button class="btn small danger" onclick="stopLive('${s.id}',this)">Parar</button>`:`<button class="btn small" onclick="startExisting('${s.id}',this)">Iniciar</button>`}<button class="btn small" onclick="showLogs('${s.id}')">Logs</button></div></div>`).join(''):'<div class="empty">Nenhuma transmissão criada.</div>';
}

function openModal(html){$('#modal').innerHTML=html;$('#modal-backdrop').classList.remove('hidden');}
function closeModal(){$('#modal-backdrop').classList.add('hidden');$('#modal').innerHTML='';}

function openTikTok(id=''){
  const d=state.destinations.find(x=>x.id===id)||selectedDestination();
  openModal(`<div class="modal-head"><div><h2>${d?'Atualizar TikTok':'Conectar TikTok'}</h2><p>Use as credenciais de transmissão fornecidas pelo TikTok. Não é sua senha da conta.</p></div><button class="close" onclick="closeModal()">×</button></div><form id="tiktok-form" class="form"><label><span>Server URL</span><input name="rtmp_url" value="${esc(d?.rtmp_url||'')}" placeholder="rtmp://... ou rtmps://..." required /></label><label><span>Stream Key</span><input name="stream_key" type="password" placeholder="${d?'Deixe vazio para manter a atual':'Cole a Stream Key'}" ${d?'':'required'} autocomplete="off" /></label><div class="helper"><strong>Onde encontro isso?</strong>No TikTok, abra a preparação de uma LIVE e procure a opção de transmitir com software/encoder. Se sua conta ainda não mostrar essa opção, ela ainda não liberou Stream Key.</div><div class="modal-actions"><button type="button" class="btn" onclick="closeModal()">Cancelar</button><button class="btn primary" type="submit">Salvar conexão</button></div></form>`);
  $('#tiktok-form').onsubmit=async e=>{
    e.preventDefault(); const btn=e.submitter; btn.disabled=true; btn.textContent='Salvando...'; const fd=new FormData(e.target);
    try{
      const body={name:d?.name||'Meu TikTok',platform:'tiktok',rtmp_url:String(fd.get('rtmp_url')).trim()}; const key=String(fd.get('stream_key')||'').trim(); if(key)body.stream_key=key;
      const saved=d?await api(`/destinations/${d.id}`,{method:'PATCH',body}):await api('/destinations',{method:'POST',body:{...body,stream_key:key}});
      state.destinationId=saved.id;localStorage.setItem('baltigoDestinationId',saved.id);closeModal();toast('TikTok conectado.');await refreshAll();
    }catch(err){toast(err.message,'error');btn.disabled=false;btn.textContent='Salvar conexão';}
  };
}

function showKeyHelp(){
  openModal(`<div class="modal-head"><div><h2>Onde encontrar a Stream Key?</h2><p>Ela é criada pelo TikTok para permitir transmissão por software.</p></div><button class="close" onclick="closeModal()">×</button></div><div class="helper"><strong>Procure no TikTok:</strong>1. Abra a tela para criar uma LIVE.<br>2. Procure “software de transmissão”, “streaming software”, “encoder” ou “PC/Mac”.<br>3. O TikTok mostrará <b>Server URL</b> e <b>Stream Key</b>.<br><br>Se essa opção não aparecer, sua conta ainda não recebeu esse tipo de acesso. Nesse caso, não existe uma chave escondida no painel para copiar.</div><div class="modal-actions"><button class="btn primary" onclick="closeModal()">Entendi</button></div>`);
}

function uploadVideo(file){
  if(!file)return; const progress=$('#upload-progress'); progress.classList.remove('hidden'); $('#upload-text').textContent='Enviando vídeo...'; $('#upload-percent').textContent='0%'; $('#upload-bar').style.width='0%';
  const xhr=new XMLHttpRequest(); xhr.open('POST',API_BASE+'/media'); xhr.setRequestHeader('X-API-Key',state.key);
  xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.round(e.loaded/e.total*100);$('#upload-percent').textContent=`${pct}%`;$('#upload-bar').style.width=`${pct}%`;if(pct===100)$('#upload-text').textContent='Preparando vídeo para LIVE...';}};
  xhr.onload=async()=>{
    try{const data=JSON.parse(xhr.responseText||'{}'); if(xhr.status===401){showAuth('Código de acesso inválido.');return;} if(xhr.status<200||xhr.status>=300)throw new Error(data.detail||`Erro ${xhr.status}`); state.mediaId=data.id;localStorage.setItem('baltigoMediaId',data.id);toast('Vídeo pronto para usar.');await refreshAll();}
    catch(err){toast(err.message,'error');}
    finally{progress.classList.add('hidden');$('#video-upload').value='';}
  };
  xhr.onerror=()=>{progress.classList.add('hidden');toast('Falha durante o upload.','error');};
  const fd=new FormData();fd.append('file',file);xhr.send(fd);
}

async function startLive(){
  const media=selectedMedia(),dest=selectedDestination(); if(!media||!dest)return;
  if(!confirm(`Iniciar agora a LIVE com “${media.name}”?`))return;
  const btn=$('#start-live');btn.disabled=true;btn.textContent='Iniciando...';
  try{await api('/streams',{method:'POST',body:{name:`Live - ${media.name}`,destination_id:dest.id,media_id:media.id,playlist_id:null,loop:true,start_now:true,scheduled_at:null}});toast('LIVE iniciando.');await refreshAll();}
  catch(err){toast(err.message,'error');renderSteps();}
}
async function stopLive(id,btn){if(!confirm('Parar esta LIVE agora?'))return;btn.disabled=true;try{await api(`/streams/${id}/stop`,{method:'POST'});toast('LIVE sendo encerrada.');await refreshAll();}catch(err){toast(err.message,'error');btn.disabled=false;}}
async function startExisting(id,btn){btn.disabled=true;try{await api(`/streams/${id}/start`,{method:'POST'});toast('Transmissão iniciando.');await refreshAll();}catch(err){toast(err.message,'error');btn.disabled=false;}}
async function testDestination(id,btn){btn.disabled=true;const old=btn.textContent;btn.textContent='Testando...';try{const r=await api(`/destinations/${id}/check`,{method:'POST'});toast(`Servidor respondeu em ${r.latency_ms} ms.`);}catch(err){toast(err.message,'error');}finally{btn.disabled=false;btn.textContent=old;}}
async function showLogs(id){try{const r=await api(`/streams/${id}/logs?lines=180`);openModal(`<div class="modal-head"><div><h2>Logs da transmissão</h2><p>Use apenas quando algo não estiver funcionando.</p></div><button class="close" onclick="closeModal()">×</button></div><div class="log">${esc((r.lines||[]).join('\n')||'Nenhum log disponível.')}</div>`);}catch(err){toast(err.message,'error');}}

function useMedia(id){state.mediaId=id;localStorage.setItem('baltigoMediaId',id);render();toast('Vídeo selecionado.');}
function useDestination(id){state.destinationId=id;localStorage.setItem('baltigoDestinationId',id);render();toast('Conexão selecionada.');}
async function removeMedia(id){if(!confirm('Excluir este vídeo?'))return;try{await api(`/media/${id}`,{method:'DELETE'});if(state.mediaId===id){state.mediaId='';localStorage.removeItem('baltigoMediaId');}await refreshAll();toast('Vídeo excluído.');}catch(err){toast(err.message,'error');}}

$('#login-form').onsubmit=async e=>{e.preventDefault();const key=$('#login-key').value.trim();try{state.key=key;await api('/dashboard');localStorage.setItem('baltigoApiKey',key);showApp();await refreshAll();}catch(err){showAuth(err.message);}};
$('#logout').onclick=()=>{localStorage.removeItem('baltigoApiKey');state.key='';showAuth();};
$('#video-upload').onchange=e=>uploadVideo(e.target.files[0]);
$('#connect-tiktok').onclick=()=>openTikTok();
$('#where-key').onclick=showKeyHelp;
$('#start-live').onclick=startLive;
$('#modal-backdrop').onclick=e=>{if(e.target===e.currentTarget)closeModal();};
Object.assign(window,{closeModal,openTikTok,useMedia,useDestination,removeMedia,testDestination,showLogs,stopLive,startExisting});

(async function init(){
  if(!state.key){showAuth();return;}
  try{showApp();await refreshAll();}catch(e){if(state.key)showAuth('Não foi possível entrar. Confira seu código de acesso.');}
})();
setInterval(refreshLive,5000);
