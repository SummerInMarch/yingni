// 所有请求经过同源 HTTPS，模型密钥只保留在服务器。
const $ = s => document.querySelector(s);
let access = localStorage.getItem('yingni_token') || '';
let firstUse = false, count = 4, refs = [], memoryEnabled = false;
let selectedStyle = '动漫日常';
let userAvatar = '', nonoAvatar = '', avatarChanged = 0;
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
    if (access && !firstUse) { const [x, appearance] = await Promise.all([api('messages'), api('appearance')]); memoryEnabled = x.memory_enabled; applyAppearance(appearance); screen('home'); }
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
    $('#password').value = ''; firstUse = false; applyAppearance(await api('appearance')); screen('home');
  } catch(e) { toast(e.message || '网络连接失败'); } finally { busy(); }
});
document.querySelectorAll('[data-go]').forEach(x => x.addEventListener('click', () => screen(x.dataset.go)));
function addMessage(role, content) {
  const row = document.createElement('div'); row.className = 'message-row' + (role === 'user' ? ' mine' : '');
  const avatar = document.createElement('span'); avatar.className = 'avatar ' + (role === 'user' ? 'avatar-user' : 'avatar-nono');
  const source = role === 'user' ? userAvatar : nonoAvatar;
  if (source) { const image = document.createElement('img'); image.src = source; image.alt = role === 'user' ? '我的头像' : '诺诺的头像'; avatar.append(image); }
  else avatar.textContent = role === 'user' ? '我' : '◡';
  if (role !== 'user') row.append(avatar);
  const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = content; row.append(bubble); $('#messages').append(row);
  if (role === 'user') row.append(avatar);
}
async function loadMessages() {
  try { const [data, appearance] = await Promise.all([api('messages'), api('appearance')]); applyAppearance(appearance); memoryEnabled = data.memory_enabled; $('.chat-heading strong').textContent = data.name; $('#messages').replaceChildren();
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
const themes = [{id:'sage', name:'清新绿'}, {id:'peach', name:'暖杏色'}, {id:'blue', name:'宁静蓝'}];
let currentTheme = 'sage';
function setAvatar(element, source, fallback) {
  element.replaceChildren();
  if (source) { const img = document.createElement('img'); img.src = source; img.alt = ''; element.append(img); }
  else element.textContent = fallback;
}
function blendWithWhite(color, amount) {
  const parts = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16));
  return '#' + parts.map(n => Math.round(n + (255 - n) * amount).toString(16).padStart(2, '0')).join('');
}
function applyAppearance(settings) {
  userAvatar = settings.user_avatar; nonoAvatar = settings.nono_avatar;
  avatarChanged = settings.avatar_changed; currentTheme = settings.theme;
  const phone = $('.phone');
  phone.classList.remove('theme-sage', 'theme-peach', 'theme-blue', 'theme-custom');
  phone.classList.add(`theme-${currentTheme}`);
  ['--page','--accent','--accent-text','--highlight','--tint','--secondary'].forEach(key => phone.style.removeProperty(key));
  if (currentTheme === 'custom') {
    const color = settings.custom_color;
    phone.style.setProperty('--page', blendWithWhite(color, 0.96));
    phone.style.setProperty('--accent', color);
    const rgb = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16));
    phone.style.setProperty('--accent-text', (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000 > 160 ? '#26322e' : '#ffffff');
    phone.style.setProperty('--highlight', color);
    phone.style.setProperty('--tint', blendWithWhite(color, 0.80));
    phone.style.setProperty('--secondary', blendWithWhite(color, 0.88));
  }
  const chat = $('#chat');
  chat.style.backgroundImage = settings.chat_background ? `linear-gradient(#ffffff88,#ffffff88),url("${settings.chat_background}")` : '';
  document.querySelectorAll('.avatar-user').forEach(x => setAvatar(x, userAvatar, '我'));
  document.querySelectorAll('.avatar-nono, .mini-face').forEach(x => setAvatar(x, nonoAvatar, '◡'));
  themeControl.lastChild.textContent = themes.find(t => t.id === currentTheme)?.name || '自定义';
}
// 头像通过账号保存，重新登录后仍可使用。
const avatarControl = document.createElement('button');
avatarControl.type = 'button'; avatarControl.textContent = '☻　设置我的头像';
const avatarInput = document.createElement('input');
avatarInput.type = 'file'; avatarInput.accept = 'image/jpeg,image/png,image/webp'; avatarInput.hidden = true;
$('.profile-list').prepend(avatarControl); $('.profile-body').append(avatarInput);
avatarControl.onclick = () => avatarInput.click();
avatarInput.onchange = async () => {
  const file = avatarInput.files[0]; if (!file) return;
  if (file.size > 2_000_000 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { toast('请选择不超过 2 MB 的 JPG、PNG 或 WebP 图片'); avatarInput.value = ''; return; }
  try { const result = await api('appearance', 'POST', {user_avatar: await readFile(file)}); applyAppearance(result); toast('头像已保存'); }
  catch (e) { toast(e.message || '头像保存失败'); } finally { avatarInput.value = ''; }
};
const nonoInfo = document.createElement('div'); nonoInfo.className = 'appearance-note'; nonoInfo.textContent = '✳ 诺诺会自己决定头像，最多每 7 天更换一次';
avatarControl.after(nonoInfo);
const themeControl = document.createElement('button'); themeControl.type = 'button';
themeControl.append(document.createTextNode('◈　App 主题'), document.createElement('span'));
$('.profile-list').insertBefore(themeControl, $('#memory-toggle'));
themeControl.onclick = async () => {
  const index = themes.findIndex(x => x.id === currentTheme), next = themes[(index + 1) % themes.length];
  try { applyAppearance(await api('appearance', 'POST', {theme: next.id})); toast(`已切换到${next.name}`); } catch(e) { toast(e.message); }
};
const colorControl = document.createElement('button'); colorControl.type = 'button'; colorControl.textContent = '◉　自定义主题颜色';
const colorInput = document.createElement('input'); colorInput.type = 'color'; colorInput.value = '#779676'; colorInput.className = 'color-input'; colorInput.setAttribute('aria-label', '选择主题颜色');
$('.profile-list').insertBefore(colorControl, $('#memory-toggle')); $('.profile-body').append(colorInput);
colorControl.onclick = () => colorInput.click();
colorInput.onchange = async () => {
  try { applyAppearance(await api('appearance', 'POST', {theme: 'custom', custom_color: colorInput.value})); toast('自定义主题已保存'); } catch(e) { toast(e.message); }
};
const backgroundControl = document.createElement('button'); backgroundControl.type = 'button'; backgroundControl.textContent = '▧　设置聊天背景';
const backgroundInput = document.createElement('input'); backgroundInput.type = 'file'; backgroundInput.accept = 'image/jpeg,image/png,image/webp'; backgroundInput.hidden = true;
$('.profile-list').insertBefore(backgroundControl, $('#memory-toggle')); $('.profile-body').append(backgroundInput);
backgroundControl.onclick = () => backgroundInput.click();
backgroundInput.onchange = async () => {
  const file = backgroundInput.files[0]; if (!file) return;
  if (file.size > 4_000_000 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { toast('请选择不超过 4 MB 的 JPG、PNG 或 WebP 图片'); backgroundInput.value = ''; return; }
  try { applyAppearance(await api('appearance', 'POST', {chat_background: await readFile(file)})); toast('聊天背景已保存'); }
  catch(e) { toast(e.message || '背景保存失败'); } finally { backgroundInput.value = ''; }
};
const clearBackground = document.createElement('button'); clearBackground.type = 'button'; clearBackground.textContent = '↺　恢复默认聊天背景';
$('.profile-list').insertBefore(clearBackground, $('#memory-toggle'));
clearBackground.onclick = async () => { try { applyAppearance(await api('appearance', 'POST', {chat_background: ''})); toast('已恢复默认背景'); } catch(e) { toast(e.message); } };
// 仅在头像变化时重新下载外观，不轮询完整图片。
setInterval(async () => {
  if (!access || !$('#chat').classList.contains('active')) return;
  try { const version = await api('avatar-version'); if (version.avatar_changed !== avatarChanged) applyAppearance(await api('appearance')); } catch { /* 下次继续检查。 */ }
}, 20000);
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
