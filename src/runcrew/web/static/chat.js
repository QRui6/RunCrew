const state = { activities: [], conversations: [], selectedActivityId: null, activeConversationId: null, sending: false, training: { goals: [], recent_coach_runs: [], athlete_preferences: [] }, memory: null, trainingWeek: null, planDraft: null, planDraftSubmission: null, selectedGoalId: null, activeCoachRunId: null, coachRunning: false };
const responseModeLabels = { data_analysis: "个人数据分析", mixed_coaching: "数据＋训练思路", general_knowledge: "通用跑步知识", clarification: "需要补充信息", safety_redirect: "安全边界" };
const claimKindLabels = { observed_fact: "数据事实", data_inference: "基于数据的推断", general_knowledge: "通用知识", coaching_suggestion: "可选建议" };
const $ = (selector) => document.querySelector(selector);
const elements = {
  activities: $("#activity-list"), conversations: $("#conversation-list"), messages: $("#messages"),
  input: $("#message-input"), composer: $("#composer"), send: $("#send-button"), title: $("#chat-title"),
  subtitle: $("#chat-subtitle"), badge: $("#context-badge"), selected: $("#selected-activity"), deepseek: $("#use-deepseek"),
  modelToggle: $("#model-toggle"), toast: $("#toast"), turnMeta: $("#turn-meta"), kicker: $("#run-kicker"),
  metricDistance: $("#metric-distance"), metricDuration: $("#metric-duration"), metricPace: $("#metric-pace"), metricHeartRate: $("#metric-heart-rate"), rhythm: $(".run-rhythm"),
  contextToggle: $("#context-toggle"), contextPanel: $("#context-panel"), contextBackdrop: $("#context-backdrop"), contextClose: $("#context-close"),
  crewSummary: $("#crew-summary"), crewExecution: $("#crew-execution"), crewRecovery: $("#crew-recovery"), crewPlan: $("#crew-plan"),
  crewExecutionStatus: $("#crew-execution-status"), crewRecoveryStatus: $("#crew-recovery-status"), crewPlanStatus: $("#crew-plan-status")
};
const trainingElements = {
  toggle: $("#training-toggle"), drawer: $("#training-drawer"), backdrop: $("#training-backdrop"), close: $("#training-close"),
  goal: $("#training-goal"), provider: $("#training-provider"), plan: $("#training-plan"), checkIn: $("#check-in-form"), day: $("#check-in-day"),
  fatigue: $("#check-in-fatigue"), soreness: $("#check-in-soreness"), sleep: $("#check-in-sleep"), readiness: $("#check-in-readiness"), pain: $("#check-in-pain"),
  painArea: $("#check-in-pain-area"), note: $("#check-in-note"), run: $("#coach-run"), result: $("#coach-result"), runs: $("#coach-runs"),
  goalForm: $("#goal-form"), goalName: $("#goal-name"), goalEvent: $("#goal-event"), goalDate: $("#goal-date"), goalTime: $("#goal-time"),
  preferenceForm: $("#preference-form"), preferenceDay: $("#preference-long-run-day"), preferenceValidUntil: $("#preference-valid-until"), preferenceList: $("#preference-list"),
  planForm: $("#plan-draft-form"), planWeekStart: $("#plan-week-start"), planDraft: $("#plan-draft"), weekProgress: $("#week-progress"), today: $("#today-session"), executions: $("#execution-list"), weekSummary: $("#week-summary"), memoryBuild: $("#weekly-memory-build"), memoryList: $("#weekly-memory-list"), memoryContextAudit: $("#memory-context-audit")
};
const memoryElements = {
  toggle: $("#memory-toggle"), drawer: $("#memory-drawer"), backdrop: $("#memory-backdrop"), close: $("#memory-close"), generatedAt: $("#memory-generated-at"),
  candidateCount: $("#memory-count-candidates"), preferenceCount: $("#memory-count-preferences"), weeklyCount: $("#memory-count-weekly"),
  candidates: $("#memory-control-candidates"), preferences: $("#memory-control-preferences"), weekly: $("#memory-control-weekly"), contexts: $("#memory-control-contexts")
};

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

function dateLabel(value) { return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(new Date(value)); }
function fullDate(value) { return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
function localDateValue() { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`; }
function dateInputValue(date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; }
function nextMondayValue() { const date = new Date(); const days = ((8 - date.getDay()) % 7) || 7; date.setDate(date.getDate() + days); return dateInputValue(date); }
function futureDateValue(days = 84) { const date = new Date(); date.setDate(date.getDate() + days); return dateInputValue(date); }
function previousMondayValue() { const date = new Date(); const sinceMonday = (date.getDay() + 6) % 7; date.setDate(date.getDate() - sinceMonday - 7); return dateInputValue(date); }
function sessionTypeLabel(value) { return ({ easy: "轻松跑", long_run: "长距离", tempo: "节奏跑", interval: "间歇跑", recovery: "恢复跑", rest: "休息", test: "测试跑" })[value] || value; }
function durationLabel(seconds) { if (!seconds) return "未设时长"; const minutes = Math.round(seconds / 60); return `${minutes} 分钟`; }
function statusLabel(value) { return ({ completed: "已完成", awaiting_user_confirmation: "等待确认", blocked: "安全阻断", failed: "运行失败", approved: "已批准", rejected: "已拒绝", stale: "已过期" })[value] || value; }
function recommendationLabel(value) { return ({ proceed: "可以按计划", reduce: "建议减量", rest: "建议休息", seek_professional_help: "建议专业评估", insufficient_data: "数据不足" })[value] || value || "—"; }
function activitySubtitle(activity) {
  if (!activity) return "从一份真实训练记录开始对话";
  return activity.detail_available ? "活动详情已就绪，可以围绕本次训练连续追问" : "已载入活动摘要；缺少的细节会在回答中明确说明";
}

function renderRunHeader(activity) {
  if (!activity) {
    elements.title.textContent = "选择一次跑步";
    elements.subtitle.textContent = activitySubtitle(null);
    elements.kicker.textContent = "RUN — · 等待选择记录";
    elements.metricDistance.textContent = "—";
    elements.metricDuration.textContent = "—";
    elements.metricPace.textContent = "—";
    elements.metricHeartRate.textContent = "—";
    elements.rhythm.classList.remove("active");
    return;
  }
  const index = state.activities.findIndex((item) => item.id === activity.id);
  const issue = String(Math.max(1, state.activities.length - Math.max(index, 0))).padStart(3, "0");
  const date = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(activity.started_at)).replaceAll("/", ".");
  elements.title.textContent = activity.title;
  elements.subtitle.textContent = activitySubtitle(activity);
  elements.kicker.textContent = `RUN ${issue} · ${date} · ${activity.provider.toUpperCase()}`;
  elements.metricDistance.textContent = activity.distance_km == null ? "—" : `${activity.distance_km} km`;
  elements.metricDuration.textContent = activity.duration || "—";
  elements.metricPace.textContent = activity.average_pace || "—";
  elements.metricHeartRate.textContent = activity.average_heart_rate == null ? "—" : `${activity.average_heart_rate} bpm`;
  elements.rhythm.classList.add("active");
}

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

function setCrewOverview(mode, result = null) {
  [elements.crewExecution, elements.crewRecovery, elements.crewPlan].forEach((node) => { node.classList.remove("running", "complete", "skipped"); });
  const states = {
    waiting: ["待运行", "待运行", "按需调用", "等待运行"],
    ready: ["数据就绪", "等待反馈", "按需调用", "上下文就绪"],
    running: ["运行中", "等待上游", "等待路由", "正在运行"],
    failed: ["运行中断", "未完成", "未调用", "运行失败"]
  };
  const values = states[mode] || states.waiting;
  [elements.crewExecutionStatus, elements.crewRecoveryStatus, elements.crewPlanStatus, elements.crewSummary].forEach((node, index) => { node.textContent = values[index]; });
  if (mode === "ready") elements.crewExecution.classList.add("complete");
  if (mode === "running") elements.crewExecution.classList.add("running");
  if (mode === "failed") elements.crewExecution.classList.add("skipped");
  if (!result) return;
  elements.crewSummary.textContent = "运行完成";
  if (result.execution) { elements.crewExecution.classList.add("complete"); elements.crewExecutionStatus.textContent = "已完成"; }
  if (result.recovery) { elements.crewRecovery.classList.add("complete"); elements.crewRecoveryStatus.textContent = "已完成"; }
  if (result.planning) { elements.crewPlan.classList.add("complete"); elements.crewPlanStatus.textContent = "已生成草案"; }
  else { elements.crewPlan.classList.add("skipped"); elements.crewPlanStatus.textContent = "无需调用"; }
}

function selectActivity(id) {
  state.selectedActivityId = id; state.activeConversationId = null;
  const activity = state.activities.find((item) => item.id === id);
  renderRunHeader(activity);
  elements.badge.textContent = activity ? "数据已连接" : "尚未建立上下文";
  renderActivities(); renderConversations(); renderSelectedActivity(activity); setCrewOverview(activity ? "ready" : "waiting"); resetMessages(); elements.input.focus();
}

function renderSelectedActivity(activity) {
  elements.selected.replaceChildren();
  if (!activity) { elements.selected.className = "selected-activity empty"; elements.selected.textContent = "请选择一条跑步记录以建立证据上下文"; return; }
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
  const label = document.createElement("span"); label.className = "welcome-label"; label.textContent = "从这里开始";
  const activity = state.activities.find((item) => item.id === state.selectedActivityId);
  const title = document.createElement("h2"); title.textContent = activity ? "想从这次训练里确认什么？" : "想从哪次训练开始？";
  const p = document.createElement("p"); p.className = "welcome-copy"; p.textContent = activity ? "RunCrew 会先核对记录和训练证据，再给出解释。你可以继续追问判断过程，而不必重新描述背景。" : "选择左侧的一次跑步。RunCrew 会先核对真实记录，再与你讨论表现、负荷和下一步安排。";
  const suggestions = document.createElement("div"); suggestions.className = "suggestions";
  [["训练复盘", "这次跑得怎么样？"], ["数据依据", "哪些指标值得关注？"], ["近期负荷", "最近七天有什么变化？"], ["后续安排", "下一次应该怎么练？"]].forEach(([category, text], index) => {
    const button = document.createElement("button"); button.type = "button"; const tag = document.createElement("span"); tag.textContent = String(index + 1).padStart(2, "0"); const copy = document.createElement("b"); copy.textContent = text; const arrow = document.createElement("i"); arrow.textContent = `${category} →`; button.append(tag, copy, arrow); button.addEventListener("click", () => { elements.input.value = text; elements.input.focus(); }); suggestions.append(button);
  });
  const note = document.createElement("p"); note.className = "grounding-note"; const check = document.createElement("span"); check.textContent = "证据原则"; note.append(check, "个人事实、分析推断和训练建议会分层表达");
  welcome.append(label, title, p, suggestions, note); elements.messages.append(welcome);
}

function renderMessages(messages, candidates = []) {
  elements.messages.replaceChildren();
  if (!messages.length) return resetMessages();
  messages.forEach((message) => appendMessage(message, candidates.filter((candidate) => candidate.source_message_id === message.id)));
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function appendMessage(message, candidates = []) {
  const row = document.createElement("article"); row.className = `message ${message.role}`;
  const avatar = document.createElement("span"); avatar.className = "avatar"; avatar.textContent = message.role === "assistant" ? "RunCrew" : "你问";
  const bubble = document.createElement("div"); bubble.className = "bubble";
  const content = document.createElement("p"); content.textContent = message.content; bubble.append(content);
  if (message.role === "assistant") {
    const meta = document.createElement("div"); meta.className = "answer-meta";
    const claimKinds = [...new Set((message.grounded_claims || []).map((claim) => claimKindLabels[claim.kind] || claim.kind))];
    [...(message.response_mode ? [responseModeLabels[message.response_mode] || message.response_mode] : []), ...claimKinds, ...(message.evidence_refs || []).map((item) => `依据 · ${item}`), ...(message.confidence ? [`置信度 · ${message.confidence}`] : []), ...(message.missing_data || []).slice(0, 2).map((item) => `缺失 · ${item}`)].forEach((value) => { const span = document.createElement("span"); span.textContent = value; meta.append(span); });
    if (meta.childNodes.length) bubble.append(meta);
    if ((message.follow_up_suggestions || []).length) {
      const followups = document.createElement("div"); followups.className = "message-followups";
      message.follow_up_suggestions.forEach((value) => { const button = document.createElement("button"); button.type = "button"; button.textContent = value; button.addEventListener("click", () => { elements.input.value = value; elements.input.focus(); }); followups.append(button); });
      bubble.append(followups);
    }
  }
  candidates.forEach((candidate) => bubble.append(renderMemoryCandidate(candidate)));
  row.append(avatar, bubble); elements.messages.append(row);
}

function renderMemoryCandidate(candidate) {
  const card = document.createElement("section"); card.className = `memory-candidate ${candidate.status}`;
  const label = document.createElement("span"); label.textContent = candidate.status === "pending" ? "待你确认的训练偏好" : "训练偏好候选";
  const title = document.createElement("strong"); title.textContent = `长跑优先安排在${weekdayLabel(candidate.proposed_value)}`;
  const meta = document.createElement("small");
  const status = ({ pending: "尚未写入长期记忆", confirmed: "已确认并写入", rejected: "已忽略", superseded: "已被新候选替代", expired: "已过期" })[candidate.status] || candidate.status;
  meta.textContent = `${status} · ${candidate.confidence === "high" ? "明确偏好表达" : "需确认的偏好表达"}`;
  card.append(label, title, meta);
  if (candidate.status === "pending") {
    const actions = document.createElement("div"); actions.className = "memory-candidate-actions";
    const reject = document.createElement("button"); reject.type = "button"; reject.className = "reject"; reject.textContent = "忽略"; reject.addEventListener("click", () => decideMemoryCandidate(candidate, "reject"));
    const confirm = document.createElement("button"); confirm.type = "button"; confirm.className = "confirm"; confirm.textContent = "确认记住"; confirm.addEventListener("click", () => decideMemoryCandidate(candidate, "confirm"));
    actions.append(reject, confirm); card.append(actions);
  }
  return card;
}

async function decideMemoryCandidate(candidate, decision) {
  if (decision === "confirm" && !window.confirm(`确认把“长跑优先安排在${weekdayLabel(candidate.proposed_value)}”保存为长期偏好？`)) return;
  try {
    await api(`/api/chat/memory-candidates/${encodeURIComponent(candidate.id)}/decision`, { method: "POST", body: JSON.stringify({ decision, expected_candidate_hash: candidate.candidate_hash }) });
    await loadConversation(candidate.conversation_id);
    await refreshTraining();
    showToast(decision === "confirm" ? "偏好已确认并写入长期记忆。" : "候选已忽略，不会写入长期记忆。");
  } catch (error) { showToast(error.message); if (state.activeConversationId) await loadConversation(state.activeConversationId); }
}

async function loadConversation(id) {
  try {
    const conversation = await api(`/api/chat/conversations/${encodeURIComponent(id)}`);
    state.activeConversationId = id; state.selectedActivityId = conversation.target_activity_id;
    const activity = state.activities.find((item) => item.id === state.selectedActivityId);
    renderRunHeader(activity); elements.badge.textContent = conversation.review_input_hash ? "证据已建立" : "等待首次分析";
    renderActivities(); renderConversations(); renderSelectedActivity(activity); renderMessages(conversation.messages, conversation.memory_candidates || []);
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
    renderMessages([...before.messages, { role: "user", content }], before.memory_candidates || []);
    appendTyping();
    const result = await api(`/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`, { method: "POST", body: JSON.stringify({ content, use_deepseek: elements.deepseek.checked }) });
    renderMessages(result.conversation.messages, result.conversation.memory_candidates || []);
    elements.badge.textContent = "证据已建立";
    updateTurnMeta(result); await refreshBootstrap(false);
  } catch (error) { showToast(error.message); if (state.activeConversationId) await loadConversation(state.activeConversationId); }
  finally { state.sending = false; elements.send.disabled = false; elements.input.focus(); }
}

function appendTyping() { const row = document.createElement("article"); row.className = "message assistant typing"; const avatar = document.createElement("span"); avatar.className = "avatar"; avatar.textContent = "RunCrew"; const bubble = document.createElement("div"); bubble.className = "bubble"; for (let i = 0; i < 3; i += 1) bubble.append(document.createElement("i")); row.append(avatar, bubble); elements.messages.append(row); elements.messages.scrollTop = elements.messages.scrollHeight; }
function updateTurnMeta(result) { elements.turnMeta.hidden = false; $("#meta-model").textContent = result.usage.model; $("#meta-context").textContent = `${result.context_message_count} 条${result.context_truncated ? " · 已裁剪" : ""}`; $("#meta-tokens").textContent = result.usage.total_tokens || "离线"; $("#meta-cost").textContent = result.usage.estimated_cost_usd ? `$${result.usage.estimated_cost_usd.toFixed(8)}` : "$0"; }
function showToast(message) { elements.toast.textContent = message; elements.toast.hidden = false; window.setTimeout(() => { elements.toast.hidden = true; }, 3800); }

function toggleContext(open) {
  elements.contextPanel.hidden = !open; elements.contextBackdrop.hidden = !open;
  elements.contextToggle.setAttribute("aria-expanded", String(open));
  if (open && !trainingElements.drawer.hidden) toggleTraining(false);
  if (open && !memoryElements.drawer.hidden) toggleMemory(false);
}

function toggleTraining(open) {
  trainingElements.drawer.hidden = !open; trainingElements.backdrop.hidden = !open;
  trainingElements.toggle.setAttribute("aria-expanded", String(open));
  if (open && !elements.contextPanel.hidden) toggleContext(false);
  if (open && !memoryElements.drawer.hidden) toggleMemory(false);
  if (open) refreshTraining().catch((error) => showToast(error.message));
}

function toggleMemory(open) {
  memoryElements.drawer.hidden = !open; memoryElements.backdrop.hidden = !open;
  memoryElements.toggle.setAttribute("aria-expanded", String(open));
  if (open && !elements.contextPanel.hidden) toggleContext(false);
  if (open && !trainingElements.drawer.hidden) toggleTraining(false);
  if (open) refreshMemory().catch((error) => showToast(error.message));
}

const memoryStatusLabels = { pending: "等待确认", confirmed: "已确认", rejected: "已忽略", superseded: "已被替代", expired: "已过期", active: "当前有效", archived: "已停用", invalidated: "已失效" };
const memoryReasonLabels = {
  selected_role_relevant: "职责相关，已选中", excluded_role_not_allowed: "该职责不允许读取", excluded_wrong_goal: "不属于当前目标", excluded_future: "生成时间晚于本轮", excluded_expired: "已过期", excluded_superseded: "已被新版替代", excluded_archived: "已停用", excluded_invalidated: "已失效", excluded_outside_target_window: "不在目标周之前", excluded_item_budget: "超过条数预算", excluded_character_budget: "超过字符预算"
};
const memoryRoleLabels = { execution: "训练执行", recovery: "恢复评估", plan: "计划调整" };

function memoryRecord({ status, kicker, title, body, meta = [], actions = [] }) {
  const article = document.createElement("article");
  article.className = `memory-record${status === "pending" || status === "active" ? "" : " resolved inactive"}`;
  const copy = document.createElement("div"); copy.className = "memory-record-copy";
  const label = document.createElement("span"); label.className = "memory-record-kicker"; const dot = document.createElement("i"); label.append(dot, kicker);
  const heading = document.createElement("h4"); heading.textContent = title; copy.append(label, heading);
  if (body) { const description = document.createElement("p"); description.textContent = body; copy.append(description); }
  if (meta.length) { const details = document.createElement("div"); details.className = "memory-record-meta"; meta.forEach((value) => { const span = document.createElement("span"); span.textContent = value; details.append(span); }); copy.append(details); }
  article.append(copy);
  if (actions.length) { const controls = document.createElement("div"); controls.className = "memory-record-actions"; actions.forEach(({ label: actionLabel, primary = false, run }) => { const button = document.createElement("button"); button.type = "button"; button.textContent = actionLabel; button.classList.toggle("primary", primary); button.addEventListener("click", async () => { button.disabled = true; try { await run(); } finally { button.disabled = false; } }); controls.append(button); }); article.append(controls); }
  return article;
}

function renderMemoryControl() {
  const overview = state.memory;
  if (!overview) return;
  memoryElements.generatedAt.textContent = `更新于 ${fullDate(overview.generated_at)}`;
  memoryElements.candidateCount.textContent = overview.counts.pending_candidates;
  memoryElements.preferenceCount.textContent = overview.counts.active_preferences;
  memoryElements.weeklyCount.textContent = overview.counts.active_weekly_memories;
  renderMemoryControlCandidates(overview.candidates || []);
  renderMemoryControlPreferences(overview.preferences || []);
  renderMemoryControlWeekly(overview.weekly_memories || []);
  renderMemoryControlContexts(overview.goal_contexts || []);
}

function renderMemoryControlCandidates(items) {
  memoryElements.candidates.replaceChildren();
  if (!items.length) return memoryElements.candidates.append(empty("尚未从对话中提取训练偏好候选。"));
  items.forEach((item) => {
    const candidate = item.candidate;
    const actions = candidate.status === "pending" ? [
      { label: "忽略", run: () => decideMemoryControlCandidate(candidate, "reject") },
      { label: "确认记住", primary: true, run: () => decideMemoryControlCandidate(candidate, "confirm") }
    ] : [];
    memoryElements.candidates.append(memoryRecord({
      status: candidate.status,
      kicker: memoryStatusLabels[candidate.status] || candidate.status,
      title: `长跑优先安排在${weekdayLabel(candidate.proposed_value)}`,
      body: item.source_excerpt ? `原话：“${item.source_excerpt}”` : "原始消息当前不可用；该候选不会被静默确认。",
      meta: [item.conversation_title, `置信度 ${candidate.confidence}`, `有效至 ${fullDate(candidate.expires_at)}`],
      actions
    }));
  });
}

function renderMemoryControlPreferences(items) {
  memoryElements.preferences.replaceChildren();
  if (!items.length) return memoryElements.preferences.append(empty("尚无经过确认的长期训练偏好。"));
  items.forEach((item) => {
    const preference = item.preference;
    const status = item.effective_now ? "active" : preference.status;
    const actions = item.effective_now ? [{ label: "停用", run: () => archiveMemoryControlPreference(preference) }] : [];
    memoryElements.preferences.append(memoryRecord({
      status,
      kicker: item.effective_now ? "当前会进入计划职责" : (memoryStatusLabels[preference.status] || preference.status),
      title: `长跑优先安排在${weekdayLabel(preference.value)}`,
      body: "该偏好只向计划调整职责开放，不会改变训练执行事实或恢复判断。",
      meta: [`来源 ${preference.source_ref}`, `生效 ${fullDate(preference.valid_from)}`, preference.valid_until ? `截至 ${fullDate(preference.valid_until)}` : "无固定截止日"],
      actions
    }));
  });
}

function renderMemoryControlWeekly(items) {
  memoryElements.weekly.replaceChildren();
  if (!items.length) return memoryElements.weekly.append(empty("尚无已结算的周训练记忆。"));
  items.forEach((item) => {
    const memory = item.memory;
    const actions = memory.status === "active" ? [{ label: "标记失效", run: () => invalidateMemoryControlWeekly(item) }] : [];
    memoryElements.weekly.append(memoryRecord({
      status: memory.status,
      kicker: memoryStatusLabels[memory.status] || memory.status,
      title: `${item.goal_name} · ${memory.week_start} 当周 · 第 ${memory.version} 版`,
      body: memory.summary,
      meta: [`确认完成 ${memory.confirmed_completed_sessions}/${memory.planned_sessions}`, `来源 ${memory.source_refs.length} 条`, `证据 ${memory.input_hash.slice(0, 10)}`],
      actions
    }));
  });
}

function renderMemoryControlContexts(goals) {
  memoryElements.contexts.replaceChildren();
  if (!goals.length) return memoryElements.contexts.append(empty("创建激活目标后，这里会展示三个职责的记忆可见性。"));
  goals.forEach((goal) => {
    const section = document.createElement("section"); section.className = "memory-goal-audit";
    const header = document.createElement("header"); const title = document.createElement("strong"); title.textContent = goal.goal_name; const week = document.createElement("small"); week.textContent = `计划目标周 ${goal.target_week_start}`; header.append(title, week); section.append(header);
    goal.contexts.forEach((context) => {
      const details = document.createElement("details"); details.className = "memory-role-row";
      const summary = document.createElement("summary"); const role = document.createElement("strong"); role.textContent = memoryRoleLabels[context.role] || context.role;
      const scope = document.createElement("span"); scope.textContent = `${context.budget.used_items}/${context.budget.max_items} 条 · ${context.budget.used_chars}/${context.budget.max_chars} 字符`;
      const result = document.createElement("em"); result.textContent = context.budget.used_items ? "已注入" : "未注入"; summary.append(role, scope, result); details.append(summary);
      const decisions = document.createElement("div"); decisions.className = "memory-role-decisions";
      if (!context.decisions.length) { const row = document.createElement("p"); row.append(document.createTextNode("无候选记忆")); decisions.append(row); }
      context.decisions.forEach((decision) => { const row = document.createElement("p"); const memory = document.createElement("span"); memory.textContent = `${decision.memory_type === "athlete_preference" ? "长期偏好" : "周训练记忆"} · ${decision.memory_id.slice(0, 8)}`; const reason = document.createElement("span"); reason.textContent = memoryReasonLabels[decision.reason] || decision.reason; row.append(memory, reason); decisions.append(row); });
      details.append(decisions); section.append(details);
    });
    memoryElements.contexts.append(section);
  });
}

async function refreshMemory() {
  state.memory = await api("/api/memory/overview");
  renderMemoryControl();
}

async function decideMemoryControlCandidate(candidate, decision) {
  if (decision === "confirm" && !window.confirm(`确认把“长跑优先安排在${weekdayLabel(candidate.proposed_value)}”保存为长期偏好？`)) return;
  try {
    await api(`/api/memory/candidates/${encodeURIComponent(candidate.id)}/decision`, { method: "POST", body: JSON.stringify({ decision, expected_candidate_hash: candidate.candidate_hash }) });
    await Promise.all([refreshMemory(), refreshTraining()]);
    if (state.activeConversationId === candidate.conversation_id) await loadConversation(candidate.conversation_id);
    showToast(decision === "confirm" ? "偏好已确认；后续计划职责可以读取。" : "候选已忽略，不会写入正式记忆。");
  } catch (error) { showToast(error.message); await refreshMemory(); }
}

async function archiveMemoryControlPreference(preference) {
  if (!window.confirm(`确认停用“长跑优先安排在${weekdayLabel(preference.value)}”？停用后后续计划不会再读取。`)) return;
  try {
    await api(`/api/memory/preferences/${encodeURIComponent(preference.id)}/archive`, { method: "POST", body: JSON.stringify({ confirmed: true }) });
    await Promise.all([refreshMemory(), refreshTraining()]); showToast("长期偏好已停用，后续上下文将自动排除。");
  } catch (error) { showToast(error.message); await refreshMemory(); }
}

async function invalidateMemoryControlWeekly(item) {
  if (!window.confirm(`确认将“${item.goal_name} · ${item.memory.week_start} 当周”标记为失效？原记录仍保留用于审计。`)) return;
  try {
    await api(`/api/memory/weekly-memories/${encodeURIComponent(item.memory.id)}/invalidate`, { method: "POST", body: JSON.stringify({ confirmed: true }) });
    await Promise.all([refreshMemory(), refreshTraining()]); showToast("周训练记忆已失效，原记录仍保留用于审计。");
  } catch (error) { showToast(error.message); await refreshMemory(); }
}

function selectedGoalView() { return state.training.goals.find((item) => item.goal.id === state.selectedGoalId); }

function renderTraining() {
  trainingElements.goal.replaceChildren();
  if (!state.training.goals.length) { const option = document.createElement("option"); option.textContent = "尚无激活目标"; option.value = ""; trainingElements.goal.append(option); state.selectedGoalId = null; }
  else {
    state.training.goals.forEach((view) => { const option = document.createElement("option"); option.value = view.goal.id; option.textContent = `${view.goal.name} · ${view.goal.event_type}`; trainingElements.goal.append(option); });
    if (!state.selectedGoalId || !selectedGoalView()) state.selectedGoalId = state.training.goals[0].goal.id;
    trainingElements.goal.value = state.selectedGoalId;
  }
  const selectedProvider = trainingElements.provider.value;
  trainingElements.provider.replaceChildren(); const all = document.createElement("option"); all.value = ""; all.textContent = "全部来源（确认无重复时使用）"; trainingElements.provider.append(all);
  (state.training.providers || []).forEach((provider) => { const option = document.createElement("option"); option.value = provider; option.textContent = provider.toUpperCase(); trainingElements.provider.append(option); });
  trainingElements.provider.value = (state.training.providers || []).includes(selectedProvider) ? selectedProvider : ((state.training.providers || []).length === 1 ? state.training.providers[0] : "");
  renderPlan(selectedGoalView()); renderPreferences(); renderCoachRuns();
}

function weekdayLabel(value) { return ({ mon: "星期一", tue: "星期二", wed: "星期三", thu: "星期四", fri: "星期五", sat: "星期六", sun: "星期日" })[value] || value; }

function renderPreferences() {
  trainingElements.preferenceList.replaceChildren();
  const preferences = state.training.athlete_preferences || [];
  if (!preferences.length) return trainingElements.preferenceList.append(empty("尚未保存长期训练偏好。"));
  preferences.slice(0, 5).forEach((preference) => {
    const row = document.createElement("div"); row.className = "preference-row";
    const copy = document.createElement("div"); const title = document.createElement("strong"); title.textContent = `长跑优先安排在${weekdayLabel(preference.value)}`;
    const meta = document.createElement("small"); const expiry = preference.valid_until ? ` · 有效至 ${dateLabel(preference.valid_until)}` : ""; meta.textContent = `${preference.status === "active" ? "当前生效" : preference.status === "superseded" ? "已被替代" : preference.status === "expired" ? "已过期" : "已停用"}${expiry}`; copy.append(title, meta); row.append(copy);
    if (preference.status === "active") { const archive = document.createElement("button"); archive.type = "button"; archive.textContent = "停用"; archive.addEventListener("click", () => archivePreference(preference.id)); row.append(archive); }
    trainingElements.preferenceList.append(row);
  });
}

async function savePreference(event) {
  event.preventDefault();
  if (!window.confirm(`确认把“长跑优先安排在${weekdayLabel(trainingElements.preferenceDay.value)}”保存为长期偏好？`)) return;
  const button = trainingElements.preferenceForm.querySelector("button"); button.disabled = true;
  const validUntil = trainingElements.preferenceValidUntil.value ? new Date(`${trainingElements.preferenceValidUntil.value}T23:59:59`).toISOString() : null;
  try {
    await api("/api/training/preferences", { method: "POST", body: JSON.stringify({ key: "preferred_long_run_weekday", value: trainingElements.preferenceDay.value, confirmed: true, valid_until: validUntil }) });
    state.planDraft = null; state.planDraftSubmission = null; renderPlanDraft(); await refreshTraining(); showToast("长期训练偏好已确认并保存到本机。");
  } catch (error) { showToast(error.message); } finally { button.disabled = false; }
}

async function archivePreference(preferenceId) {
  if (!window.confirm("确认停用这条长期训练偏好？已有计划不会被自动修改。")) return;
  try {
    await api(`/api/training/preferences/${encodeURIComponent(preferenceId)}/archive`, { method: "POST", body: JSON.stringify({ confirmed: true }) });
    state.planDraft = null; state.planDraftSubmission = null; renderPlanDraft(); await refreshTraining(); showToast("长期训练偏好已停用。");
  } catch (error) { showToast(error.message); }
}

function renderPlan(view) {
  trainingElements.plan.replaceChildren();
  trainingElements.planForm.hidden = !view;
  if (!view || !view.active_plan) { trainingElements.plan.className = "plan-card empty"; trainingElements.plan.textContent = view ? "当前没有激活计划。选择下一周并生成草案，确认后才会写入。" : "请先选择或新建一个训练目标。"; return; }
  const plan = view.active_plan; trainingElements.plan.className = "plan-card";
  const title = document.createElement("h4"); title.textContent = `${plan.week_start} 当周 · 第 ${plan.revision} 版`;
  const detail = document.createElement("p"); detail.textContent = `${plan.sessions.length} 节计划课 · ${view.latest_check_in ? `最近反馈 ${view.latest_check_in.day}` : "尚无身体反馈"}`;
  const chips = document.createElement("div"); chips.className = "session-chips";
  plan.sessions.forEach((session) => { const chip = document.createElement("span"); chip.textContent = `${session.scheduled_for.slice(5)} · ${sessionTypeLabel(session.session_type)}`; chips.append(chip); });
  trainingElements.plan.append(title, detail, chips);
}

async function createGoal(event) {
  event.preventDefault();
  const weekdays = [...document.querySelectorAll('input[name="training-weekday"]:checked')].map((item) => item.value);
  if (!weekdays.length) return showToast("请至少选择一个可训练日期。");
  const button = trainingElements.goalForm.querySelector("button"); button.disabled = true;
  const minutes = Number(trainingElements.goalTime.value || 0);
  try {
    const goal = await api("/api/training/goals", { method: "POST", body: JSON.stringify({ name: trainingElements.goalName.value.trim(), event_type: trainingElements.goalEvent.value, target_date: trainingElements.goalDate.value, target_time_seconds: minutes ? Math.round(minutes * 60) : null, available_weekdays: weekdays }) });
    state.selectedGoalId = goal.id; trainingElements.goalForm.reset(); trainingElements.goalDate.value = futureDateValue();
    await refreshTraining(); showToast("训练目标已保存在本机，可以生成周计划了。");
  } catch (error) { showToast(error.message); } finally { button.disabled = false; }
}

async function draftPlan(event) {
  event.preventDefault(); const view = selectedGoalView(); if (!view) return showToast("请先选择训练目标。");
  const button = trainingElements.planForm.querySelector("button"); button.disabled = true;
  const submission = { week_start: trainingElements.planWeekStart.value, as_of: new Date().toISOString(), lookback_days: 28, provider: trainingElements.provider.value || null };
  try {
    const result = await api(`/api/training/goals/${encodeURIComponent(view.goal.id)}/plan-drafts`, { method: "POST", body: JSON.stringify(submission) });
    state.planDraft = result; state.planDraftSubmission = submission; renderPlanDraft();
  } catch (error) { showToast(error.message); } finally { button.disabled = false; }
}

function renderPlanDraft() {
  trainingElements.planDraft.replaceChildren();
  const result = state.planDraft;
  if (!result) { trainingElements.planDraft.hidden = true; return; }
  trainingElements.planDraft.hidden = false; trainingElements.planDraft.className = `plan-draft${result.status === "ready" ? "" : " blocked"}`;
  const label = document.createElement("span"); label.textContent = result.status === "ready" ? "待确认草案" : "暂不能生成";
  const title = document.createElement("h4"); title.textContent = result.summary;
  trainingElements.planDraft.append(label, title);
  if (result.weekly_plan_draft) {
    const rationale = document.createElement("p"); rationale.textContent = result.weekly_plan_draft.rationale; trainingElements.planDraft.append(rationale);
    const list = document.createElement("div"); list.className = "draft-sessions";
    result.weekly_plan_draft.sessions.forEach((session) => { const row = document.createElement("div"); const name = document.createElement("strong"); name.textContent = `${session.scheduled_for.slice(5)} · ${sessionTypeLabel(session.session_type)}`; const volume = document.createElement("small"); volume.textContent = durationLabel(session.duration_seconds); row.append(name, volume); list.append(row); });
    const approve = document.createElement("button"); approve.type = "button"; approve.className = "primary-action"; approve.textContent = "确认并激活这份周计划"; approve.addEventListener("click", activatePlan); trainingElements.planDraft.append(list, approve);
  }
  (result.warnings || []).forEach((warning) => { const note = document.createElement("small"); note.textContent = warning; trainingElements.planDraft.append(note); });
}

async function activatePlan() {
  const view = selectedGoalView(); if (!view || !state.planDraft || !state.planDraftSubmission) return;
  if (!window.confirm("确认激活这份计划？系统会先重放草案并校验数据是否变化。")) return;
  try {
    await api(`/api/training/goals/${encodeURIComponent(view.goal.id)}/plans/activate`, { method: "POST", body: JSON.stringify({ ...state.planDraftSubmission, expected_input_hash: state.planDraft.input_hash }) });
    state.planDraft = null; state.planDraftSubmission = null; renderPlanDraft(); await refreshTraining(); showToast("周计划已激活，后续修改仍需你的确认。");
  } catch (error) { showToast(error.message); }
}

function renderTrainingWeek() {
  const view = state.trainingWeek;
  [trainingElements.weekProgress, trainingElements.today, trainingElements.executions, trainingElements.weekSummary].forEach((node) => node.replaceChildren());
  renderWeeklyMemories(view ? view.recent_memories : []);
  renderMemoryContexts(view ? view.memory_contexts : []);
  if (!view || !view.plan || !view.execution || !view.progress) {
    trainingElements.weekProgress.className = "week-progress empty"; trainingElements.weekProgress.textContent = "当前目标还没有可执行的激活计划。";
    trainingElements.today.className = "today-session empty"; trainingElements.today.textContent = "激活计划后，这里会显示今日或下一节训练。";
    trainingElements.weekSummary.className = "week-summary empty"; trainingElements.weekSummary.textContent = "尚无可总结的训练周。"; return;
  }
  const progress = view.progress; trainingElements.weekProgress.className = "week-progress";
  [["已确认", `${progress.confirmed_sessions}/${progress.due_sessions}`], ["待核对", String(progress.pending_confirmation_sessions)], ["待执行", String(progress.upcoming_sessions)], ["反馈", `${progress.check_in_days} 天`]].forEach(([name, value]) => { const item = document.createElement("div"); const small = document.createElement("small"); small.textContent = name; const strong = document.createElement("strong"); strong.textContent = value; item.append(small, strong); trainingElements.weekProgress.append(item); });
  const focusId = view.today_session_ids.find((id) => view.plan.sessions.find((item) => item.id === id && item.session_type !== "rest")) || view.next_session_id;
  const focus = view.plan.sessions.find((item) => item.id === focusId);
  trainingElements.today.className = focus ? "today-session" : "today-session empty";
  if (focus) { const label = document.createElement("span"); label.textContent = view.today_session_ids.includes(focus.id) ? "今日训练" : "下一节训练"; const title = document.createElement("h4"); title.textContent = sessionTypeLabel(focus.session_type); const detail = document.createElement("p"); detail.textContent = `${focus.scheduled_for} · ${durationLabel(focus.duration_seconds)} · ${focus.purpose}`; trainingElements.today.append(label, title, detail); }
  else trainingElements.today.textContent = "本周已没有待执行训练。";
  view.execution.sessions.filter((item) => item.outcome !== "rest" && item.outcome !== "upcoming").forEach((comparison) => renderExecutionRow(comparison, view.plan));
  trainingElements.weekSummary.className = "week-summary"; const headline = document.createElement("strong"); headline.textContent = progress.headline; const copy = document.createElement("p"); const rate = progress.completion_rate == null ? "尚未形成" : `${Math.round(progress.completion_rate * 100)}%`; copy.textContent = `计划总时长 ${durationLabel(progress.planned_duration_seconds)}；到期训练确认率 ${rate}；跳过 ${progress.skipped_sessions} 节。`; trainingElements.weekSummary.append(headline, copy);
}

function renderWeeklyMemories(memories = []) {
  trainingElements.memoryList.replaceChildren();
  if (!memories.length) return trainingElements.memoryList.append(empty("尚无已结算的周训练记忆。"));
  memories.forEach((memory) => {
    const card = document.createElement("article"); card.className = "weekly-memory-card";
    const header = document.createElement("header"); const title = document.createElement("strong"); title.textContent = `${memory.week_start} 当周 · 第 ${memory.version} 版`; const status = document.createElement("small"); status.textContent = memory.status === "active" ? "当前有效" : memory.status; header.append(title, status);
    const summary = document.createElement("p"); const rate = memory.completion_rate == null ? "无计划训练" : `${Math.round(memory.completion_rate * 100)}%`; summary.textContent = `${memory.summary} 确认完成率 ${rate}，实际 ${durationLabel(memory.actual_duration_seconds)}。`;
    card.append(header, summary); trainingElements.memoryList.append(card);
  });
}

function renderMemoryContexts(contexts = []) {
  trainingElements.memoryContextAudit.replaceChildren();
  if (!contexts.length) return trainingElements.memoryContextAudit.append(empty("尚无职责上下文审计。"));
  const labels = { execution: "执行核对", recovery: "恢复评估", plan: "计划调整" };
  contexts.forEach((context) => {
    const row = document.createElement("div"); row.className = "memory-context-row";
    const role = document.createElement("strong"); role.textContent = labels[context.role] || context.role;
    const usage = document.createElement("span"); const excluded = context.decisions.filter((item) => !item.selected).length; usage.textContent = `选中 ${context.budget.used_items}/${context.budget.max_items} 条 · ${context.budget.used_chars}/${context.budget.max_chars} 字符 · 排除 ${excluded} 条`;
    row.append(role, usage); trainingElements.memoryContextAudit.append(row);
  });
}

async function buildPreviousWeeklyMemory() {
  const view = selectedGoalView(); if (!view) return showToast("请先选择训练目标。");
  if (!window.confirm("确认根据正式计划、执行确认和身体反馈结算上一训练周？")) return;
  trainingElements.memoryBuild.disabled = true;
  try {
    const result = await api(`/api/training/goals/${encodeURIComponent(view.goal.id)}/weekly-memories`, { method: "POST", body: JSON.stringify({ week_start: previousMondayValue(), as_of: new Date().toISOString() }) });
    showToast(result.outcome === "unchanged" ? "周训练记忆没有变化。" : result.outcome === "superseded" ? "周训练记忆已生成新版本。" : "周训练记忆已生成。"); await refreshTraining();
  } catch (error) { showToast(error.message); }
  finally { trainingElements.memoryBuild.disabled = false; }
}

function renderExecutionRow(comparison, plan) {
  const session = plan.sessions.find((item) => item.id === comparison.session_id); if (!session) return;
  const row = document.createElement("article"); row.className = "execution-row";
  const copy = document.createElement("div"); const title = document.createElement("strong"); title.textContent = `${session.scheduled_for.slice(5)} · ${sessionTypeLabel(session.session_type)}`; const status = document.createElement("small"); status.textContent = comparison.match_state === "confirmed" ? "活动已确认" : comparison.match_state === "suggested" ? "发现高匹配候选" : comparison.match_state === "ambiguous" ? "存在多个候选" : comparison.outcome === "skipped" ? "已标记跳过" : "没有找到匹配活动"; copy.append(title, status); row.append(copy);
  const actions = document.createElement("div"); actions.className = "execution-actions";
  if (comparison.match_state === "confirmed") { const review = document.createElement("button"); review.type = "button"; review.textContent = "去复盘"; review.addEventListener("click", () => openActivityReview(comparison.suggested_activity_id)); const clear = document.createElement("button"); clear.type = "button"; clear.textContent = "解除"; clear.addEventListener("click", () => decideExecution(comparison, "clear_execution")); actions.append(review, clear); }
  else if (comparison.outcome === "skipped") { const clear = document.createElement("button"); clear.type = "button"; clear.textContent = "解除跳过"; clear.addEventListener("click", () => decideExecution(comparison, "clear_execution")); actions.append(clear); }
  else if (comparison.candidates.length) { comparison.candidates.slice(0, 2).forEach((candidate, index) => { const confirm = document.createElement("button"); confirm.type = "button"; confirm.textContent = `${index ? "候选" : "确认匹配"} ${dateLabel(candidate.started_at)}`; confirm.addEventListener("click", () => decideExecution(comparison, "confirm_match", candidate.activity_id)); actions.append(confirm); }); }
  if (comparison.match_state !== "confirmed" && comparison.outcome !== "skipped") { const skip = document.createElement("button"); skip.type = "button"; skip.className = "muted"; skip.textContent = "标记跳过"; skip.addEventListener("click", () => decideExecution(comparison, "mark_skipped")); actions.append(skip); }
  row.append(actions); trainingElements.executions.append(row);
}

async function decideExecution(comparison, decision, activityId = null) {
  const view = state.trainingWeek; if (!view || !view.plan) return;
  if (decision === "mark_skipped" && !window.confirm("确认将这节训练标记为跳过？之后仍可解除。")) return;
  try {
    const result = await api(`/api/training/plans/${encodeURIComponent(view.plan.id)}/execution-decisions`, { method: "POST", body: JSON.stringify({ base_revision: view.plan.revision, session_id: comparison.session_id, decision, as_of: new Date().toISOString(), activity_id: activityId, comment: null }) });
    if (result.confirmation.status === "stale") showToast("计划版本已经变化，请重新核对。"); else showToast(decision === "confirm_match" ? "活动已与计划课确认关联。" : decision === "mark_skipped" ? "训练已标记为跳过。" : "执行状态已解除。");
    await refreshTraining();
  } catch (error) { showToast(error.message); }
}

function openActivityReview(activityId) {
  if (!activityId || !state.activities.some((item) => item.id === activityId)) return showToast("该活动不在当前跑步列表中。");
  selectActivity(activityId); toggleTraining(false); elements.input.value = "复盘这次训练，并告诉我下一次训练需要注意什么。"; elements.input.focus();
}

function renderCoachRuns() {
  trainingElements.runs.replaceChildren();
  if (!state.training.recent_coach_runs.length) return trainingElements.runs.append(empty("尚无联合评估记录。"));
  state.training.recent_coach_runs.forEach((run) => {
    const button = document.createElement("button"); button.type = "button"; button.className = "coach-run-item";
    const text = document.createElement("span"); const title = document.createElement("strong"); title.textContent = recommendationLabel(run.recommendation); const time = document.createElement("small"); time.textContent = `${fullDate(run.created_at)} · ${run.run_id.slice(0, 8)}`; text.append(title, time);
    const status = document.createElement("em"); status.textContent = statusLabel(run.status); button.append(text, status);
    button.addEventListener("click", () => loadCoachRun(run.run_id)); trainingElements.runs.append(button);
  });
}

function renderCoachResult(view) {
  state.activeCoachRunId = view.audit.run_id; const result = view.audit.result; trainingElements.result.replaceChildren(); trainingElements.result.className = "coach-result";
  if (view.audit.status === "failed") setCrewOverview("failed");
  else setCrewOverview("complete", result);
  const status = document.createElement("span"); status.className = "coach-status"; status.textContent = statusLabel(view.audit.status);
  const title = document.createElement("h4"); title.textContent = result.recovery ? recommendationLabel(result.recovery.recommendation) : "本次评估未形成恢复结论";
  const summary = document.createElement("p"); summary.textContent = result.recovery ? result.recovery.summary : (result.error ? result.error.message : "运行未产生业务结果。");
  const flow = document.createElement("div"); flow.className = "coach-flow";
  [["训练执行", result.execution ? result.execution.summary : "未完成"], ["恢复评估", result.recovery ? result.recovery.risk_level : "未完成"], ["计划调整", result.planning ? result.planning.status : "未调用"]].forEach(([name, value]) => { const row = document.createElement("div"); const key = document.createElement("strong"); key.textContent = name; const output = document.createElement("span"); output.textContent = value; row.append(key, output); flow.append(row); });
  trainingElements.result.append(status, title, summary, flow);
  const draft = result.planning && result.planning.change_proposal_draft;
  if (draft) {
    const proposal = document.createElement("div"); proposal.className = "coach-proposal"; const strong = document.createElement("strong"); strong.textContent = "待审核计划调整"; const small = document.createElement("small"); small.textContent = `${draft.reason}（绑定 revision ${draft.base_revision}，${draft.changes.length} 项修改）`; proposal.append(strong, small); trainingElements.result.append(proposal);
  }
  if (view.audit.status === "awaiting_user_confirmation") {
    const actions = document.createElement("div"); actions.className = "coach-actions";
    const reject = document.createElement("button"); reject.type = "button"; reject.className = "reject"; reject.textContent = "拒绝建议"; reject.addEventListener("click", () => decideCoach("reject"));
    const approve = document.createElement("button"); approve.type = "button"; approve.className = "approve"; approve.textContent = "确认并应用"; approve.addEventListener("click", () => decideCoach("approve"));
    actions.append(reject, approve); trainingElements.result.append(actions);
  }
}

async function refreshWeek() {
  const view = selectedGoalView();
  if (!view) { state.trainingWeek = null; renderTrainingWeek(); return; }
  const query = new URLSearchParams({ as_of: new Date().toISOString() });
  if (trainingElements.provider.value) query.set("provider", trainingElements.provider.value);
  state.trainingWeek = await api(`/api/training/goals/${encodeURIComponent(view.goal.id)}/week?${query.toString()}`); renderTrainingWeek();
}
async function refreshTraining() { state.training = await api("/api/training/bootstrap"); renderTraining(); await refreshWeek(); }
async function loadCoachRun(runId) { try { renderCoachResult(await api(`/api/training/coach-runs/${encodeURIComponent(runId)}`)); } catch (error) { showToast(error.message); } }

async function saveCheckIn(event) {
  event.preventDefault(); const view = selectedGoalView(); if (!view) return showToast("请先选择训练目标。");
  const symptoms = [...document.querySelectorAll('input[name="acute-symptom"]:checked')].map((item) => item.value);
  const payload = { day: trainingElements.day.value, fatigue: Number(trainingElements.fatigue.value), soreness: Number(trainingElements.soreness.value), sleep_quality: Number(trainingElements.sleep.value), readiness: trainingElements.readiness.value ? Number(trainingElements.readiness.value) : null, pain_severity: Number(trainingElements.pain.value), pain_area: trainingElements.painArea.value.trim() || null, acute_symptoms: symptoms, note: trainingElements.note.value.trim() || null };
  const button = trainingElements.checkIn.querySelector("button"); button.disabled = true;
  try { await api(`/api/training/goals/${encodeURIComponent(view.goal.id)}/check-ins`, { method: "POST", body: JSON.stringify(payload) }); showToast("身体反馈已保存到本机。"); await refreshTraining(); }
  catch (error) { showToast(error.message); } finally { button.disabled = false; }
}

async function runCoach() {
  const view = selectedGoalView(); const plan = state.trainingWeek && state.trainingWeek.plan; if (!view || !plan) return showToast("所选目标没有激活计划。");
  trainingElements.run.disabled = true; state.coachRunning = true; setCrewOverview("running"); trainingElements.result.className = "coach-result empty"; trainingElements.result.textContent = "三个职责节点正在按权限运行…";
  try { const result = await api("/api/training/coach-runs", { method: "POST", body: JSON.stringify({ goal_id: view.goal.id, plan_id: plan.id, as_of: new Date().toISOString(), provider: trainingElements.provider.value || null }) }); renderCoachResult(result); await refreshTraining(); showToast("联合评估已完成，计划草案不会自动生效。"); }
  catch (error) { showToast(error.message); setCrewOverview("failed"); trainingElements.result.textContent = "运行失败，请检查数据和计划状态。"; }
  finally { state.coachRunning = false; trainingElements.run.disabled = false; }
}

async function decideCoach(decision) {
  if (!state.activeCoachRunId) return; const verb = decision === "approve" ? "应用" : "拒绝";
  if (!window.confirm(`确认${verb}这次训练建议？批准前系统会重新运行并校验是否过期。`)) return;
  try { const result = await api(`/api/training/coach-runs/${encodeURIComponent(state.activeCoachRunId)}/decision`, { method: "POST", body: JSON.stringify({ decision }) }); renderCoachResult({ audit: result.audit, plan_sessions: result.plan.sessions }); await refreshTraining(); showToast(result.outcome === "stale" ? "建议已过期，计划没有被修改。" : `建议已${verb}。`); }
  catch (error) { showToast(error.message); }
}

async function refreshBootstrap(initial = true) {
  const payload = await api("/api/chat/bootstrap"); state.activities = payload.activities; state.conversations = payload.conversations;
  elements.deepseek.disabled = !payload.deepseek_available; elements.modelToggle.classList.toggle("disabled", !payload.deepseek_available);
  if (!payload.deepseek_available) elements.modelToggle.title = "请先在本机配置 DEEPSEEK_API_KEY";
  if (initial && state.activities.length) state.selectedActivityId = state.activities[0].id;
  const selectedActivity = state.activities.find((item) => item.id === state.selectedActivityId);
  renderActivities(); renderConversations(); renderSelectedActivity(selectedActivity);
  if (initial) { renderRunHeader(selectedActivity); elements.badge.textContent = selectedActivity ? "数据已连接" : "尚未建立上下文"; }
  setCrewOverview(state.selectedActivityId ? "ready" : "waiting");
  if (initial) resetMessages();
}

$("#new-chat").addEventListener("click", () => { state.activeConversationId = null; const activity = state.activities.find((item) => item.id === state.selectedActivityId); renderConversations(); resetMessages(); renderRunHeader(activity); elements.badge.textContent = activity ? "数据已连接" : "尚未建立上下文"; elements.input.focus(); });
elements.composer.addEventListener("submit", sendMessage);
elements.input.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); elements.composer.requestSubmit(); } });
elements.input.addEventListener("input", () => { elements.input.style.height = "auto"; elements.input.style.height = `${Math.min(elements.input.scrollHeight, 170)}px`; });

refreshBootstrap().catch((error) => showToast(error.message));
trainingElements.day.value = localDateValue();
trainingElements.planWeekStart.value = nextMondayValue();
trainingElements.goalDate.value = futureDateValue();
trainingElements.toggle.addEventListener("click", () => toggleTraining(true));
trainingElements.close.addEventListener("click", () => toggleTraining(false));
trainingElements.backdrop.addEventListener("click", () => toggleTraining(false));
trainingElements.goal.addEventListener("change", () => { state.selectedGoalId = trainingElements.goal.value || null; state.planDraft = null; renderPlan(selectedGoalView()); renderPlanDraft(); refreshWeek().catch((error) => showToast(error.message)); });
trainingElements.provider.addEventListener("change", () => refreshWeek().catch((error) => showToast(error.message)));
trainingElements.goalForm.addEventListener("submit", createGoal);
trainingElements.preferenceForm.addEventListener("submit", savePreference);
trainingElements.planForm.addEventListener("submit", draftPlan);
trainingElements.checkIn.addEventListener("submit", saveCheckIn);
trainingElements.run.addEventListener("click", runCoach);
trainingElements.memoryBuild.addEventListener("click", buildPreviousWeeklyMemory);
memoryElements.toggle.addEventListener("click", () => toggleMemory(true));
memoryElements.close.addEventListener("click", () => toggleMemory(false));
memoryElements.backdrop.addEventListener("click", () => toggleMemory(false));
elements.contextToggle.addEventListener("click", () => toggleContext(true));
elements.contextClose.addEventListener("click", () => toggleContext(false));
elements.contextBackdrop.addEventListener("click", () => toggleContext(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !trainingElements.drawer.hidden) toggleTraining(false);
  else if (event.key === "Escape" && !memoryElements.drawer.hidden) toggleMemory(false);
  else if (event.key === "Escape" && !elements.contextPanel.hidden) toggleContext(false);
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") { event.preventDefault(); $("#new-chat").click(); }
});
