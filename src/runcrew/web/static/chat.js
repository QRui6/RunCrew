const state = { activities: [], conversations: [], selectedActivityId: null, activeConversationId: null, sending: false, training: { goals: [], recent_coach_runs: [] }, selectedGoalId: null, activeCoachRunId: null, coachRunning: false };
const responseModeLabels = { data_analysis: "个人数据分析", mixed_coaching: "数据＋训练思路", general_knowledge: "通用跑步知识", clarification: "需要补充信息", safety_redirect: "安全边界" };
const claimKindLabels = { observed_fact: "数据事实", data_inference: "基于数据的推断", general_knowledge: "通用知识", coaching_suggestion: "可选建议" };
const $ = (selector) => document.querySelector(selector);
const elements = {
  activities: $("#activity-list"), conversations: $("#conversation-list"), messages: $("#messages"),
  input: $("#message-input"), composer: $("#composer"), send: $("#send-button"), title: $("#chat-title"),
  badge: $("#context-badge"), selected: $("#selected-activity"), deepseek: $("#use-deepseek"),
  modelToggle: $("#model-toggle"), toast: $("#toast"), turnMeta: $("#turn-meta")
};
const trainingElements = {
  toggle: $("#training-toggle"), drawer: $("#training-drawer"), backdrop: $("#training-backdrop"), close: $("#training-close"),
  goal: $("#training-goal"), provider: $("#training-provider"), plan: $("#training-plan"), checkIn: $("#check-in-form"), day: $("#check-in-day"),
  fatigue: $("#check-in-fatigue"), soreness: $("#check-in-soreness"), sleep: $("#check-in-sleep"), pain: $("#check-in-pain"),
  painArea: $("#check-in-pain-area"), note: $("#check-in-note"), run: $("#coach-run"), result: $("#coach-result"), runs: $("#coach-runs")
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
function statusLabel(value) { return ({ completed: "已完成", awaiting_user_confirmation: "等待确认", blocked: "安全阻断", failed: "运行失败", approved: "已批准", rejected: "已拒绝", stale: "已过期" })[value] || value; }
function recommendationLabel(value) { return ({ proceed: "可以按计划", reduce: "建议减量", rest: "建议休息", seek_professional_help: "建议专业评估", insufficient_data: "数据不足" })[value] || value || "—"; }

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
    const claimKinds = [...new Set((message.grounded_claims || []).map((claim) => claimKindLabels[claim.kind] || claim.kind))];
    [...(message.response_mode ? [responseModeLabels[message.response_mode] || message.response_mode] : []), ...claimKinds, ...(message.evidence_refs || []).map((item) => `依据 · ${item}`), ...(message.confidence ? [`置信度 · ${message.confidence}`] : []), ...(message.missing_data || []).slice(0, 2).map((item) => `缺失 · ${item}`)].forEach((value) => { const span = document.createElement("span"); span.textContent = value; meta.append(span); });
    if (meta.childNodes.length) bubble.append(meta);
    if ((message.follow_up_suggestions || []).length) {
      const followups = document.createElement("div"); followups.className = "message-followups";
      message.follow_up_suggestions.forEach((value) => { const button = document.createElement("button"); button.type = "button"; button.textContent = value; button.addEventListener("click", () => { elements.input.value = value; elements.input.focus(); }); followups.append(button); });
      bubble.append(followups);
    }
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

function toggleTraining(open) {
  trainingElements.drawer.hidden = !open; trainingElements.backdrop.hidden = !open;
  if (open) refreshTraining().catch((error) => showToast(error.message));
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
  renderPlan(selectedGoalView()); renderCoachRuns();
}

function renderPlan(view) {
  trainingElements.plan.replaceChildren();
  if (!view || !view.active_plan) { trainingElements.plan.className = "plan-card empty"; trainingElements.plan.textContent = "所选目标没有激活计划，请先在终端建立课表。"; return; }
  const plan = view.active_plan; trainingElements.plan.className = "plan-card";
  const title = document.createElement("h4"); title.textContent = `${plan.week_start} 当周 · revision ${plan.revision}`;
  const detail = document.createElement("p"); detail.textContent = `${plan.sessions.length} 节计划课 · ${view.latest_check_in ? `最近反馈 ${view.latest_check_in.day}` : "尚无身体反馈"}`;
  const chips = document.createElement("div"); chips.className = "session-chips";
  plan.sessions.forEach((session) => { const chip = document.createElement("span"); chip.textContent = `${session.scheduled_for.slice(5)} · ${session.session_type}`; chips.append(chip); });
  trainingElements.plan.append(title, detail, chips);
}

function renderCoachRuns() {
  trainingElements.runs.replaceChildren();
  if (!state.training.recent_coach_runs.length) return trainingElements.runs.append(empty("尚无 Coach 运行记录。"));
  state.training.recent_coach_runs.forEach((run) => {
    const button = document.createElement("button"); button.type = "button"; button.className = "coach-run-item";
    const text = document.createElement("span"); const title = document.createElement("strong"); title.textContent = recommendationLabel(run.recommendation); const time = document.createElement("small"); time.textContent = `${fullDate(run.created_at)} · ${run.run_id.slice(0, 8)}`; text.append(title, time);
    const status = document.createElement("em"); status.textContent = statusLabel(run.status); button.append(text, status);
    button.addEventListener("click", () => loadCoachRun(run.run_id)); trainingElements.runs.append(button);
  });
}

function renderCoachResult(view) {
  state.activeCoachRunId = view.audit.run_id; const result = view.audit.result; trainingElements.result.replaceChildren(); trainingElements.result.className = "coach-result";
  const status = document.createElement("span"); status.className = "coach-status"; status.textContent = statusLabel(view.audit.status);
  const title = document.createElement("h4"); title.textContent = result.recovery ? recommendationLabel(result.recovery.recommendation) : "Coach 未形成恢复结论";
  const summary = document.createElement("p"); summary.textContent = result.recovery ? result.recovery.summary : (result.error ? result.error.message : "运行未产生业务结果。");
  const flow = document.createElement("div"); flow.className = "coach-flow";
  [["Execution Agent", result.execution ? result.execution.summary : "未完成"], ["Recovery Agent", result.recovery ? result.recovery.risk_level : "未完成"], ["Plan Agent", result.planning ? result.planning.status : "未调用"]].forEach(([name, value]) => { const row = document.createElement("div"); const key = document.createElement("strong"); key.textContent = name; const output = document.createElement("span"); output.textContent = value; row.append(key, output); flow.append(row); });
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

async function refreshTraining() { state.training = await api("/api/training/bootstrap"); renderTraining(); }
async function loadCoachRun(runId) { try { renderCoachResult(await api(`/api/training/coach-runs/${encodeURIComponent(runId)}`)); } catch (error) { showToast(error.message); } }

async function saveCheckIn(event) {
  event.preventDefault(); const view = selectedGoalView(); if (!view) return showToast("请先选择训练目标。");
  const symptoms = [...document.querySelectorAll('input[name="acute-symptom"]:checked')].map((item) => item.value);
  const payload = { day: trainingElements.day.value, fatigue: Number(trainingElements.fatigue.value), soreness: Number(trainingElements.soreness.value), sleep_quality: Number(trainingElements.sleep.value), pain_severity: Number(trainingElements.pain.value), pain_area: trainingElements.painArea.value.trim() || null, acute_symptoms: symptoms, note: trainingElements.note.value.trim() || null };
  const button = trainingElements.checkIn.querySelector("button"); button.disabled = true;
  try { await api(`/api/training/goals/${encodeURIComponent(view.goal.id)}/check-ins`, { method: "POST", body: JSON.stringify(payload) }); showToast("身体反馈已保存到本机。"); await refreshTraining(); }
  catch (error) { showToast(error.message); } finally { button.disabled = false; }
}

async function runCoach() {
  const view = selectedGoalView(); if (!view || !view.active_plan) return showToast("所选目标没有激活计划。");
  trainingElements.run.disabled = true; state.coachRunning = true; trainingElements.result.className = "coach-result empty"; trainingElements.result.textContent = "三个职责节点正在按权限运行…";
  try { const result = await api("/api/training/coach-runs", { method: "POST", body: JSON.stringify({ goal_id: view.goal.id, plan_id: view.active_plan.id, as_of: new Date().toISOString(), provider: trainingElements.provider.value || null }) }); renderCoachResult(result); await refreshTraining(); showToast("Coach 运行完成，计划草案仍未自动生效。"); }
  catch (error) { showToast(error.message); trainingElements.result.textContent = "运行失败，请检查数据和计划状态。"; }
  finally { state.coachRunning = false; trainingElements.run.disabled = false; }
}

async function decideCoach(decision) {
  if (!state.activeCoachRunId) return; const verb = decision === "approve" ? "应用" : "拒绝";
  if (!window.confirm(`确认${verb}这次 Coach 建议？批准前服务端会重跑并校验是否过期。`)) return;
  try { const result = await api(`/api/training/coach-runs/${encodeURIComponent(state.activeCoachRunId)}/decision`, { method: "POST", body: JSON.stringify({ decision }) }); renderCoachResult({ audit: result.audit, plan_sessions: result.plan.sessions }); await refreshTraining(); showToast(result.outcome === "stale" ? "建议已过期，计划没有被修改。" : `建议已${verb}。`); }
  catch (error) { showToast(error.message); }
}

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
trainingElements.day.value = localDateValue();
trainingElements.toggle.addEventListener("click", () => toggleTraining(true));
trainingElements.close.addEventListener("click", () => toggleTraining(false));
trainingElements.backdrop.addEventListener("click", () => toggleTraining(false));
trainingElements.goal.addEventListener("change", () => { state.selectedGoalId = trainingElements.goal.value || null; renderPlan(selectedGoalView()); });
trainingElements.checkIn.addEventListener("submit", saveCheckIn);
trainingElements.run.addEventListener("click", runCoach);
