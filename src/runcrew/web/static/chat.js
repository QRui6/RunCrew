const state = { activities: [], conversations: [], selectedActivityId: null, activeConversationId: null, sending: false };
const $ = (selector) => document.querySelector(selector);
const elements = {
  activities: $("#activity-list"), conversations: $("#conversation-list"), messages: $("#messages"),
  input: $("#message-input"), composer: $("#composer"), send: $("#send-button"), title: $("#chat-title"),
  badge: $("#context-badge"), selected: $("#selected-activity"), deepseek: $("#use-deepseek"),
  modelToggle: $("#model-toggle"), toast: $("#toast"), turnMeta: $("#turn-meta")
};

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

function dateLabel(value) { return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(new Date(value)); }
function fullDate(value) { return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }

function renderActivities() {
  elements.activities.replaceChildren();
  $("#activity-count").textContent = `${state.activities.length} 条`;
  if (!state.activities.length) return elements.activities.append(empty("还没有跑步数据，请先在终端同步 COROS 或 fixture。"));
  state.activities.forEach((activity) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `activity-item${activity.id === state.selectedActivityId ? " active" : ""}`;
    const head = document.createElement("div"); head.className = "activity-head";
    const title = document.createElement("strong"); title.textContent = activity.title;
    const time = document.createElement("time"); time.textContent = dateLabel(activity.started_at);
    head.append(title, time);
    const stats = document.createElement("div"); stats.className = "activity-stats";
    [activity.distance_km == null ? "— km" : `${activity.distance_km} km`, activity.average_pace || "— /km", activity.provider.toUpperCase()].forEach((value) => { const span = document.createElement("span"); span.textContent = value; stats.append(span); });
    button.append(head, stats);
    button.addEventListener("click", () => selectActivity(activity.id));
    elements.activities.append(button);
  });
}

function renderConversations() {
  elements.conversations.replaceChildren();
  if (!state.conversations.length) return elements.conversations.append(empty("发送第一条消息后，对话会保存在本机。"));
  state.conversations.forEach((conversation) => {
    const button = document.createElement("button"); button.type = "button";
    button.className = `conversation-item${conversation.id === state.activeConversationId ? " active" : ""}`;
    const title = document.createElement("strong"); title.textContent = conversation.title;
    const time = document.createElement("small"); time.textContent = `${dateLabel(conversation.updated_at)} · ${conversation.message_count || 0} 条消息`;
    button.append(title, time); button.addEventListener("click", () => loadConversation(conversation.id));
    elements.conversations.append(button);
  });
}

function empty(text) { const p = document.createElement("p"); p.className = "empty-list"; p.textContent = text; return p; }

function selectActivity(id) {
  state.selectedActivityId = id; state.activeConversationId = null;
  const activity = state.activities.find((item) => item.id === id);
  elements.title.textContent = activity ? `聊聊 · ${activity.title}` : "选一场跑步，开始聊";
  elements.badge.textContent = activity ? `${dateLabel(activity.started_at)} · ${activity.provider.toUpperCase()}` : "等待选择数据";
  renderActivities(); renderConversations(); renderSelectedActivity(activity); resetMessages(); elements.input.focus();
}

function renderSelectedActivity(activity) {
  elements.selected.replaceChildren();
  if (!activity) { elements.selected.className = "selected-activity empty"; elements.selected.textContent = "尚未选择活动"; return; }
  elements.selected.className = "selected-activity";
  const time = document.createElement("time"); time.textContent = fullDate(activity.started_at);
  const h3 = document.createElement("h3"); h3.textContent = activity.title;
  const dl = document.createElement("dl");
  [["距离", activity.distance_km == null ? "—" : `${activity.distance_km} km`], ["时长", activity.duration], ["平均配速", activity.average_pace || "—"], ["平均心率", activity.average_heart_rate == null ? "—" : `${activity.average_heart_rate} bpm`]].forEach(([key, value]) => {
    const div = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = key; dd.textContent = value; div.append(dt, dd); dl.append(div);
  });
  elements.selected.append(time, h3, dl);
}

function resetMessages() {
  elements.messages.replaceChildren();
  const welcome = document.createElement("div"); welcome.className = "welcome";
  const orbit = document.createElement("span"); orbit.className = "welcome-orbit"; orbit.append("RUN", document.createElement("br"), "DATA");
  const p = document.createElement("p"); p.textContent = "从这场跑步开始问。Agent 会先调用 Training Review Skill 建立证据快照，后续追问复用同一份快照与最近对话。";
  const suggestions = document.createElement("div"); suggestions.className = "suggestions";
  ["这次跑步完成得怎么样？", "最近七天的训练负荷有什么变化？", "这个判断用了哪些证据？"].forEach((text) => { const b = document.createElement("button"); b.type = "button"; b.textContent = text; b.addEventListener("click", () => { elements.input.value = text; elements.input.focus(); }); suggestions.append(b); });
  welcome.append(orbit, p, suggestions); elements.messages.append(welcome);
}

function renderMessages(messages) {
  elements.messages.replaceChildren();
  if (!messages.length) return resetMessages();
  messages.forEach((message) => appendMessage(message));
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function appendMessage(message) {
  const row = document.createElement("article"); row.className = `message ${message.role}`;
  const avatar = document.createElement("span"); avatar.className = "avatar"; avatar.textContent = message.role === "assistant" ? "RC" : "YOU";
  const bubble = document.createElement("div"); bubble.className = "bubble";
  const content = document.createElement("p"); content.textContent = message.content; bubble.append(content);
  if (message.role === "assistant") {
    const meta = document.createElement("div"); meta.className = "answer-meta";
    [...(message.evidence_refs || []).map((item) => `依据 · ${item}`), ...(message.confidence ? [`置信度 · ${message.confidence}`] : []), ...(message.missing_data || []).slice(0, 2).map((item) => `缺失 · ${item}`)].forEach((value) => { const span = document.createElement("span"); span.textContent = value; meta.append(span); });
    if (meta.childNodes.length) bubble.append(meta);
  }
  row.append(avatar, bubble); elements.messages.append(row);
}

async function loadConversation(id) {
  try {
    const conversation = await api(`/api/chat/conversations/${encodeURIComponent(id)}`);
    state.activeConversationId = id; state.selectedActivityId = conversation.target_activity_id;
    elements.title.textContent = conversation.title; elements.badge.textContent = conversation.review_input_hash ? `证据快照 · ${conversation.review_input_hash.slice(0, 8)}` : "等待首次 Agent 运行";
    renderActivities(); renderConversations(); renderSelectedActivity(state.activities.find((item) => item.id === state.selectedActivityId)); renderMessages(conversation.messages);
  } catch (error) { showToast(error.message); }
}

async function ensureConversation(question) {
  if (state.activeConversationId) return state.activeConversationId;
  if (!state.selectedActivityId) throw new Error("请先从左侧选择一场跑步。");
  const conversation = await api("/api/chat/conversations", { method: "POST", body: JSON.stringify({ activity_id: state.selectedActivityId, title: question.slice(0, 28), lookback_days: 28 }) });
  state.activeConversationId = conversation.id; state.conversations.unshift(conversation); renderConversations(); return conversation.id;
}

async function sendMessage(event) {
  event.preventDefault(); if (state.sending) return;
  const content = elements.input.value.trim(); if (!content) return;
  try {
    state.sending = true; elements.send.disabled = true;
    const conversationId = await ensureConversation(content);
    const before = await api(`/api/chat/conversations/${encodeURIComponent(conversationId)}`);
    elements.input.value = "";
    renderMessages([...before.messages, { role: "user", content }]);
    appendTyping();
    const result = await api(`/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`, { method: "POST", body: JSON.stringify({ content, use_deepseek: elements.deepseek.checked }) });
    renderMessages(result.conversation.messages); elements.title.textContent = result.conversation.title;
    elements.badge.textContent = `证据快照 · ${(result.conversation.review_input_hash || "").slice(0, 8)}`;
    updateTurnMeta(result); await refreshBootstrap(false);
  } catch (error) { showToast(error.message); if (state.activeConversationId) await loadConversation(state.activeConversationId); }
  finally { state.sending = false; elements.send.disabled = false; elements.input.focus(); }
}

function appendTyping() { const row = document.createElement("article"); row.className = "message assistant typing"; const avatar = document.createElement("span"); avatar.className = "avatar"; avatar.textContent = "RC"; const bubble = document.createElement("div"); bubble.className = "bubble"; for (let i = 0; i < 3; i += 1) bubble.append(document.createElement("i")); row.append(avatar, bubble); elements.messages.append(row); elements.messages.scrollTop = elements.messages.scrollHeight; }
function updateTurnMeta(result) { elements.turnMeta.hidden = false; $("#meta-model").textContent = result.usage.model; $("#meta-context").textContent = `${result.context_message_count} 条${result.context_truncated ? " · 已裁剪" : ""}`; $("#meta-tokens").textContent = result.usage.total_tokens || "离线"; $("#meta-cost").textContent = result.usage.estimated_cost_usd ? `$${result.usage.estimated_cost_usd.toFixed(8)}` : "$0"; }
function showToast(message) { elements.toast.textContent = message; elements.toast.hidden = false; window.setTimeout(() => { elements.toast.hidden = true; }, 3800); }

async function refreshBootstrap(initial = true) {
  const payload = await api("/api/chat/bootstrap"); state.activities = payload.activities; state.conversations = payload.conversations;
  elements.deepseek.disabled = !payload.deepseek_available; elements.modelToggle.classList.toggle("disabled", !payload.deepseek_available);
  if (!payload.deepseek_available) elements.modelToggle.title = "请先在本机配置 DEEPSEEK_API_KEY";
  if (initial && state.activities.length) state.selectedActivityId = state.activities[0].id;
  renderActivities(); renderConversations(); renderSelectedActivity(state.activities.find((item) => item.id === state.selectedActivityId));
  if (initial) resetMessages();
}

$("#new-chat").addEventListener("click", () => { state.activeConversationId = null; renderConversations(); resetMessages(); elements.title.textContent = "新的跑步对话"; elements.badge.textContent = "等待首次 Agent 运行"; elements.input.focus(); });
elements.composer.addEventListener("submit", sendMessage);
elements.input.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); elements.composer.requestSubmit(); } });
elements.input.addEventListener("input", () => { elements.input.style.height = "auto"; elements.input.style.height = `${Math.min(elements.input.scrollHeight, 170)}px`; });

refreshBootstrap().catch((error) => showToast(error.message));
