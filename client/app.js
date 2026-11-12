// 所有请求经过同源 HTTPS，模型密钥只保留在服务器。
const $ = s => document.querySelector(s);
let access = localStorage.getItem('yingni_token') || '';
let firstUse = false, count = 4, refs = [], memoryEnabled = false;
let selectedStyle = '动漫日常';
let toastTimer;

function toast(message) {
  const box = $('#toast'); box.textContent = message; box.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => box.classList.remove('show'), 3500);
}
function busy(text) { $('#busy').hidden = !text; $('#busy-text').textContent = text || ''; }
function screen(name) {
  document.querySelectorAll('.screen').forEach(x => x.classList.toggle('active', x.id === name));
  window.scrollTo(0, 0);
  if (name === 'chat') loadMessages();
  if (name === 'works') loadWorks();
  if (name === 'profile') $('#memory-status').textContent = memoryEnabled ? '已开启' : '未开启';
}
async function api(path, method = 'GET', body) {
  const options = { method, headers: { 'Authorization': `Bearer ${access}` } };
  if (body !== undefined) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
  const response = await fetch(path, options);
  if (response.status === 401 && path !== 'login') { access = ''; localStorage.removeItem('yingni_token'); screen('auth'); }
  let result; try { result = await response.json(); } catch { throw new Error('服务暂时不可用，请稍后重试'); }
  if (!response.ok) throw new Error(result.error || '操作失败，请稍后重试');
  return result;
}
async function start() {
  try {
    const info = await api('setup-status'); firstUse = !info.setup;
    $('#auth-title').innerHTML = firstUse ? '你好，<br><em>创建你的账号。</em>' : '你好，<br><em>欢迎回到映你。</em>';
    $('#auth-subtitle').textContent = firstUse ? '首次使用，请设置手机号和密码。手机号仅作登录标识，暂不验证。' : '登录，继续你的故事。';
    $('#auth-submit').textContent = firstUse ? '创建账号 ↗' : '登录 ↗';
    $('#consent-wrap').hidden = !firstUse;
    if (access && !firstUse) { const x = await api('messages'); memoryEnabled = x.memory_enabled; screen('home'); }
  } catch (e) { toast(e.message || '网络连接失败'); }
}
$('#auth-form').addEventListener('submit', async event => {
  event.preventDefault(); busy('正在连接…');
  try {
    const body = {phone: $('#phone').value.trim(), password: $('#password').value};
    if (firstUse) { body.setup_token = window.YINGNI_SETUP_TOKEN || ''; body.memory_enabled = $('#consent').checked; }
    const result = await api(firstUse ? 'setup' : 'login', 'POST', body);
    access = result.token; localStorage.setItem('yingni_token', access);
    memoryEnabled = firstUse ? $('#consent').checked : result.memory_enabled;
    $('#password').value = ''; firstUse = false; screen('home');
  } catch(e) { toast(e.message || '网络连接失败'); } finally { busy(); }
});
document.querySelectorAll('[data-go]').forEach(x => x.addEventListener('click', () => screen(x.dataset.go)));
function addMessage(role, content) {
  const row = document.createElement('div'); row.className = 'message-row' + (role === 'user' ? ' mine' : '');
  if (role !== 'user') { const avatar = document.createElement('span'); avatar.className = 'avatar'; avatar.textContent = '◡'; row.append(avatar); }
  const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = content; row.append(bubble); $('#messages').append(row);
}
async function loadMessages() {
  try { const data = await api('messages'); memoryEnabled = data.memory_enabled; $('.chat-heading strong').textContent = data.name; $('#messages').replaceChildren();
    if (!data.messages.length) addMessage('assistant', '嗨，我是诺诺。今天的你，过得怎么样？');
    data.messages.forEach(m => addMessage(m.role, m.content)); window.scrollTo(0, document.body.scrollHeight);
  } catch(e) { toast(e.message); }
}
$('#chat-form').addEventListener('submit', async event => {
  event.preventDefault(); const input = $('#chat-input'), text = input.value.trim(); if (!text) return;
  input.value = ''; addMessage('user', text); $('#send').disabled = true; window.scrollTo(0, document.body.scrollHeight);
  try { const result = await api('chat', 'POST', {message:text}); $('.chat-heading strong').textContent = result.name; addMessage('assistant', result.reply); window.scrollTo(0, document.body.scrollHeight); }
  catch(e) { toast(e.message || '发送失败'); input.value = text; } finally { $('#send').disabled = false; }
});
// 参考图也可直接作为风格来源。
const referenceStyle = document.createElement('button');
referenceStyle.className = 'style-option';
referenceStyle.dataset.style = '参考图片的画风';
referenceStyle.innerHTML = '<span class="style-art anime"><i>✧</i></span><strong>参考图画风</strong><small>REFERENCE</small>';
$('.style-grid').append(referenceStyle);
document.querySelectorAll('.style-option').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.style-option').forEach(x => x.classList.remove('selected')); button.classList.add('selected'); selectedStyle = button.dataset.style;
}));
$('#minus').onclick = () => { count = Math.max(1, count - 1); $('#count').textContent = count; };
$('#plus').onclick = () => { count = Math.min(6, count + 1); $('#count').textContent = count; };
function readFile(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); }); }
$('#reference').addEventListener('change', async event => {
  const files = [...event.target.files];
  if (files.length > 4 || files.some(x => x.size > 6_000_000 || !['image/jpeg','image/png','image/webp'].includes(x.type))) { toast('请选择最多 4 张、每张不超过 6 MB 的 JPG、PNG 或 WebP'); event.target.value = ''; return; }
  try { refs = await Promise.all(files.map(readFile)); $('#upload-title').textContent = refs.length ? `已选择 ${refs.length} 张参考图` : '上传参考图片'; } catch { toast('图片读取失败'); }
});
$('#save-template').onclick = async () => {
  if (!refs.length) return toast('请先选择参考图片');
  const name = prompt('给模板起个名字'); if (!name) return;
  try { await api('templates', 'POST', {name, refs}); toast('模板已保存，仅自己可用'); } catch(e) { toast(e.message); }
};
$('#template-list').onclick = async () => {
  try { const result = await api('templates'); if (!result.templates.length) return toast('还没有保存模板');
    const choice = prompt('输入模板序号：\n' + result.templates.map((t, i) => `${i + 1}. ${t.name}`).join('\n'));
    const template = result.templates[Number(choice) - 1]; if (template) { refs = template.refs; $('#upload-title').textContent = `已使用模板：${template.name}`; }
  } catch(e) { toast(e.message); }
};
$('#generate').onclick = async () => {
  const story = $('#story').value.trim(); if (!story) return toast('先写下你的想法吧');
  busy('诺诺正在整理故事并绘制图片，可能需要几分钟，请保持页面开启…');
  try { const result = await api('generate', 'POST', {story, style:selectedStyle, count, refs}); screen('works');
    if (result.pictures.some(x => x.error)) toast('部分图片未生成成功，可以单独重试'); else toast('你的故事生成好了');
  } catch(e) { toast(e.message || '生成失败，请稍后重试'); } finally { busy(); }
};
async function loadWorks() {
  const list = $('#works-list'); list.replaceChildren();
  try { const result = await api('works'); if (!result.works.length) { const p = document.createElement('p'); p.className = 'muted'; p.textContent = '还没有作品，去创造第一个故事吧。'; list.append(p); }
    for (const work of result.works) {
      const card = document.createElement('div'); card.className = 'work';
      const title = document.createElement('h3'); title.textContent = work.story; card.append(title);
      const meta = document.createElement('p'); meta.textContent = work.style; card.append(meta);
      const grid = document.createElement('div'); grid.className = 'work-grid'; card.append(grid); list.append(card);
      for (const picture of work.pictures) {
        const tile = document.createElement('div'); tile.className = 'work-picture'; grid.append(tile);
        if (picture.error) { const failed = document.createElement('div'); failed.className = 'failed'; failed.textContent = '图片生成失败'; tile.append(failed); }
        else { const image = document.createElement('img'); image.alt = '生成的图片'; tile.append(image);
          fetch(`picture/${picture.id}`, {headers:{Authorization:`Bearer ${access}`}}).then(r => { if (!r.ok) throw Error(); return r.blob(); }).then(blob => { image.src = URL.createObjectURL(blob); tile.dataset.mime = blob.type; image.onclick = () => { $('#image-full').src = image.src; $('#image-viewer').hidden = false; }; }).catch(() => { image.alt = '图片加载失败'; }); }
        const button = document.createElement('button'); button.textContent = '↻ 重新生成'; button.onclick = async () => {
          if (!confirm('重新生成会产生一次图片调用费用，继续吗？')) return;
          busy('正在重新生成这张图片…'); try { await api(`regenerate/${picture.id}`, 'POST', {}); await loadWorks(); } catch(e) { toast(e.message); } finally { busy(); }
        }; tile.append(button);
        if (!picture.error && window.Yingni) {
          const save = document.createElement('button'); save.textContent = '↓ 保存到手机';
          save.onclick = () => { if (tile.dataset.mime) window.Yingni.savePicture(picture.id, access, tile.dataset.mime); else toast('图片还在加载，请稍候'); }; tile.append(save);
        }
      }
    }
  } catch(e) { toast(e.message); }
}
$('#memory-toggle').onclick = async () => {
  const next = !memoryEnabled;
  if (!confirm(next ? '允许诺诺从聊天中形成记忆，并在图片生成时使用相关记忆？' : '关闭后诺诺将不再使用或更新长期记忆，原有记忆会保留。继续吗？')) return;
  try { await api('memory-setting', 'POST', {enabled:next}); memoryEnabled = next; $('#memory-status').textContent = next ? '已开启' : '未开启'; } catch(e) { toast(e.message); }
};
$('#forget').onclick = async () => {
  if (!confirm('将永久清除全部聊天记录和诺诺记忆，作品与模板不会删除。确定继续吗？')) return;
  try { await api('forget-all', 'POST', {}); toast('聊天和诺诺记忆已清除'); } catch(e) { toast(e.message); }
};
$('#logout').onclick = async () => {
  try { await api('logout', 'POST', {}); } catch(e) { return toast(e.message || '退出失败，请稍后重试'); }
  access = ''; localStorage.removeItem('yingni_token'); screen('auth');
};
$('#image-close').onclick = () => { $('#image-viewer').hidden = true; };
start();
