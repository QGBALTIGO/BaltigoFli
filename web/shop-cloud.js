const API_BASE = location.hostname.endsWith('.vercel.app')
  ? 'https://baltigo-live-cloud-production.up.railway.app/api'
  : '/api';

const state = {
  key: localStorage.getItem('baltigoApiKey') || '',
  nodes: [],
  selectedNodeId: null,
  commands: [],
};

const $ = q => document.querySelector(q);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function toast(message, type='') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), 4000);
}

async function api(path, options={}) {
  const headers = {...(options.headers || {})};
  if (state.key) headers['X-API-Key'] = state.key;
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  let response;
  try {
    response = await fetch(API_BASE + path, {...options, headers, cache:'no-store'});
  } catch {
    throw new Error('Não foi possível conectar ao Baltigo.');
  }
  let body = {};
  try { body = await response.json(); } catch {}
  if (response.status === 401) {
    lock('Código de acesso inválido.');
    throw new Error('Código de acesso inválido.');
  }
  if (!response.ok) throw new Error(body.detail || `Erro ${response.status}`);
  return body;
}

function lock(message='') {
  $('#shop-app').classList.add('hidden');
  $('#shop-auth').classList.remove('hidden');
  if (message) {
    $('#shop-login-error').textContent = message;
    $('#shop-login-error').classList.remove('hidden');
  }
}

function unlock() {
  $('#shop-auth').classList.add('hidden');
  $('#shop-app').classList.remove('hidden');
  $('#shop-login-error').classList.add('hidden');
}

function selectedNode() {
  return state.nodes.find(n => n.id === state.selectedNodeId) || state.nodes[0] || null;
}

async function refresh() {
  if (!state.key) return lock();
  try {
    state.nodes = await api('/shop/nodes');
    if (!state.selectedNodeId && state.nodes.length) state.selectedNodeId = state.nodes[0].id;
    if (state.selectedNodeId && !state.nodes.some(n => n.id === state.selectedNodeId)) {
      state.selectedNodeId = state.nodes[0]?.id || null;
    }
    const node = selectedNode();
    if (node) {
      state.commands = await api(`/shop/nodes/${node.id}/commands?limit=20`);
    } else {
      state.commands = [];
    }
    render();
  } catch (error) {
    if (!String(error.message).includes('acesso')) toast(error.message, 'error');
  }
}

function render() {
  const node = selectedNode();
  $('#empty-node').classList.toggle('hidden', !!node);
  $('#node-area').classList.toggle('hidden', !node);
  if (!node) return;

  $('#node-name').textContent = node.name;
  const online = $('#node-online');
  online.textContent = node.online ? '● Online' : '● Offline';
  online.className = `pill ${node.online ? 'online' : 'offline'}`;

  $('#status-windows').textContent = node.online ? 'Conectado' : 'Offline';
  $('#status-host').textContent = node.hostname || (node.online ? 'Agente conectado' : 'Aguardando agente');
  $('#status-obs').textContent = node.obs_connected ? 'Conectado' : 'Desconectado';
  $('#status-scene').textContent = node.current_scene ? `Cena: ${node.current_scene}` : 'Sem cena detectada';
  $('#status-camera').textContent = node.virtual_camera_active ? 'Ativa' : 'Parada';

  $('#open-manager').disabled = !node.online;
  $('#start-camera').disabled = !node.online || !node.obs_connected || node.virtual_camera_active;
  $('#stop-camera').disabled = !node.online || !node.obs_connected || !node.virtual_camera_active;

  const scenes = Array.isArray(node.capabilities?.scenes) ? node.capabilities.scenes : [];
  $('#scene-control').classList.toggle('hidden', !scenes.length);
  if (scenes.length) {
    $('#scene-select').innerHTML = scenes.map(name => `<option value="${esc(name)}" ${name===node.current_scene?'selected':''}>${esc(name)}</option>`).join('');
  }

  $('#command-list').innerHTML = state.commands.length
    ? state.commands.map(command => `<div class="command"><div><strong>${esc(command.action)}</strong><br><span>${new Date(command.created_at).toLocaleString('pt-BR')}</span></div><span>${esc(command.status)}</span></div>`).join('')
    : '<div class="command"><span>Nenhum comando enviado ainda.</span></div>';
}

function showToken(token, nodeName) {
  $('#modal').innerHTML = `
    <h2>Token de pareamento criado</h2>
    <p>Copie este token agora. O Baltigo guarda apenas o hash e não conseguirá mostrar o token novamente.</p>
    <div class="token-box" id="pairing-token">${esc(token)}</div>
    <p><strong>${esc(nodeName)}</strong>: coloque o token em <code>BALTIGO_NODE_TOKEN</code> no arquivo <code>shop-agent-windows/.env</code> da máquina Windows.</p>
    <div class="modal-actions"><button class="btn" id="copy-token">Copiar token</button><button class="btn primary" id="close-modal">Concluído</button></div>`;
  $('#modal-backdrop').classList.remove('hidden');
  $('#copy-token').onclick = async () => {
    try { await navigator.clipboard.writeText(token); toast('Token copiado.'); }
    catch { toast('Não foi possível copiar automaticamente.', 'error'); }
  };
  $('#close-modal').onclick = () => $('#modal-backdrop').classList.add('hidden');
}

async function createNode() {
  const button = $('#create-node');
  button.disabled = true;
  button.textContent = 'Criando...';
  try {
    const result = await api('/shop/nodes', {method:'POST', body:{name:'Shop Cloud 01'}});
    state.selectedNodeId = result.node.id;
    showToken(result.pairing_token, result.node.name);
    await refresh();
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'Criar pareamento';
  }
}

async function queue(action, payload={}) {
  const node = selectedNode();
  if (!node) return toast('Nenhuma máquina pareada.', 'error');
  try {
    await api(`/shop/nodes/${node.id}/commands`, {method:'POST', body:{action, payload}});
    toast('Comando enviado para a máquina.');
    setTimeout(refresh, 1200);
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function rotateToken() {
  const node = selectedNode();
  if (!node) return;
  if (!confirm('Gerar um novo token? O agente atual ficará desconectado até receber o novo token.')) return;
  try {
    const result = await api(`/shop/nodes/${node.id}/rotate-token`, {method:'POST'});
    showToken(result.pairing_token, result.node.name);
  } catch (error) {
    toast(error.message, 'error');
  }
}

$('#shop-login').onsubmit = async event => {
  event.preventDefault();
  state.key = $('#shop-key').value.trim();
  try {
    await api('/shop/nodes');
    localStorage.setItem('baltigoApiKey', state.key);
    unlock();
    await refresh();
  } catch (error) {
    $('#shop-login-error').textContent = error.message;
    $('#shop-login-error').classList.remove('hidden');
  }
};

$('#refresh').onclick = refresh;
$('#create-node').onclick = createNode;
$('#open-manager').onclick = () => queue('live_manager_open');
$('#start-camera').onclick = () => queue('virtual_camera_start');
$('#stop-camera').onclick = () => queue('virtual_camera_stop');
$('#set-scene').onclick = () => queue('scene_set', {name:$('#scene-select').value});
$('#rotate-token').onclick = rotateToken;
$('#modal-backdrop').onclick = event => { if (event.target === event.currentTarget) event.currentTarget.classList.add('hidden'); };

if (state.key) {
  unlock();
  refresh();
} else {
  lock();
}

setInterval(() => {
  if (state.key && !$('#shop-app').classList.contains('hidden')) refresh();
}, 5000);
