// 仅模拟界面交互，不发送或保存用户数据。
const screens = document.querySelectorAll('.screen');
let current = 'home';
let previous = 'home';
let count = 4;
let toastTimer;

function showScreen(id) {
  if (id === 'profile') previous = current;
  current = id;
  screens.forEach(screen => screen.classList.toggle('active', screen.id === id));
  window.scrollTo(0, 0);
}

function toast(message) {
  const element = document.querySelector('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove('show'), 2500);
}

document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => showScreen(button.dataset.go)));
document.querySelector('#profile-back').addEventListener('click', () => showScreen(previous));
document.querySelectorAll('.style-option').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.style-option').forEach(option => option.classList.remove('selected'));
  button.classList.add('selected');
}));
document.querySelector('#reference').addEventListener('change', event => {
  const number = event.target.files.length;
  document.querySelector('#upload-title').textContent = number ? `已选择 ${number} 张参考图` : '上传参考图片';
});
document.querySelector('#minus').addEventListener('click', () => { count = Math.max(1, count - 1); document.querySelector('#count').textContent = count; });
document.querySelector('#plus').addEventListener('click', () => { count = Math.min(9, count + 1); document.querySelector('#count').textContent = count; });
document.querySelector('#generate').addEventListener('click', () => {
  const grid = document.querySelector('#result-grid');
  grid.replaceChildren();
  for (let i = 0; i < count; i++) {
    const tile = document.createElement('div');
    tile.className = 'result-tile';
    const label = document.createElement('span');
    label.textContent = `MOMENT / ${String(i + 1).padStart(2, '0')}`;
    const button = document.createElement('button');
    button.textContent = '↻ 重新生成';
    button.addEventListener('click', () => toast('这是界面预览，暂未接入图片生成'));
    tile.append(label, button);
    grid.append(tile);
  }
  showScreen('result');
  toast('示例画面：实际生成将在后续接入');
});
document.querySelector('#chat-form').addEventListener('submit', event => {
  event.preventDefault();
  const input = document.querySelector('#chat-input');
  const value = input.value.trim();
  if (!value) return;
  const row = document.createElement('div');
  row.className = 'message-row mine';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = value;
  row.append(bubble);
  document.querySelector('#messages').append(row);
  input.value = '';
  toast('这是界面预览，诺诺暂未接入');
});
document.querySelectorAll('.profile-list div').forEach(item => item.addEventListener('click', () => toast('此功能将在后续开发')));

// 预览总览可直接打开指定页面，完整流程仍可从首页进入。
const initialScreen = location.hash.slice(1);
if (initialScreen && document.getElementById(initialScreen)?.classList.contains('screen')) showScreen(initialScreen);
