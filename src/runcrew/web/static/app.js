const state = {
  labels: {
    training_completion: "训练完成度",
    load_change: "七天负荷变化",
    training_anomaly: "训练异常",
    run_started: "运行开始",
    policy_action: "策略选择动作",
    tool_permission_checked: "工具权限检查",
    tool_call_started: "开始调用 Skill",
    tool_call_retry_scheduled: "安排工具重试",
    tool_call_succeeded: "Skill 返回观察",
    tool_call_failed: "工具调用失败",
    output_validation_started: "开始验证输出",
    output_validated: "输出通过 Schema",
    run_completed: "Agent 运行完成",
    run_failed: "Agent 安全退出",
    run_timed_out: "Agent 运行超时",
    budget_exhausted: "预算已耗尽",
  },
};

const $ = (id) => document.getElementById(id);
const form = $("dashboard-form");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadDashboard(new FormData(form));
});

async function loadDashboard(formData = new FormData(form)) {
  $("loading").hidden = false;
  $("dashboard").hidden = true;
  $("error").hidden = true;
  const params = new URLSearchParams();
  for (const [key, value] of formData.entries()) {
    if (String(value).trim()) params.set(key, String(value).trim());
  }
  try {
    const response = await fetch(`/api/dashboard?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "数据加载失败");
    if (!payload.activity) throw new Error(payload.message || "没有可以演示的活动");
    render(payload);
    $("dashboard").hidden = false;
  } catch (error) {
    $("error").textContent = error.message;
    $("error").hidden = false;
  } finally {
    $("loading").hidden = true;
  }
}

function render(data) {
  renderActivity(data.activity, data.recent_activities);
  renderFindings(data);
  renderAgent(data.agent_run);
  renderEvaluation(data.evaluation);
}

function renderActivity(activity, recent) {
  const date = new Date(activity.started_at);
  $("activity-day").textContent = String(date.getDate()).padStart(2, "0");
  $("activity-month").textContent = date.toLocaleDateString("zh-CN", { year: "numeric", month: "short" }).toUpperCase();
  $("activity-title").textContent = activity.title;
  $("activity-time").textContent = `${date.toLocaleString("zh-CN", { weekday: "long", hour: "2-digit", minute: "2-digit" })} · ${activity.sport_type}`;
  $("activity-provider").textContent = `${activity.provider} / ${activity.detail_available ? "DETAIL" : "SUMMARY"}`;
  $("metric-distance").textContent = activity.distance_km ?? "—";
  $("metric-duration").textContent = activity.duration;
  $("metric-pace").textContent = activity.average_pace ?? "—";
  $("metric-heart-rate").textContent = activity.average_heart_rate ?? "—";
  $("metric-laps").textContent = activity.lap_count;
  const maxDistance = Math.max(...recent.map((item) => item.distance_km || 0), 1);
  $("recent-runs").replaceChildren(...recent.map((item, index) => {
    const bar = document.createElement("span");
    bar.className = `recent-run${index === 0 ? " active" : ""}`;
    const heightLevel = Math.max(1, Math.ceil(((item.distance_km || 0) / maxDistance) * 10));
    bar.classList.add(`height-${heightLevel}`);
    bar.title = `${new Date(item.started_at).toLocaleDateString("zh-CN")} · ${item.distance_km ?? "—"} km`;
    return bar;
  }));
}

function renderFindings(data) {
  const cards = data.findings.map((finding, index) => {
    const card = document.createElement("article");
    card.className = `finding-card level-${finding.level}`;
    card.dataset.number = String(index + 1).padStart(2, "0");
    const top = document.createElement("div");
    top.className = "finding-top";
    top.append(textNode("span", "finding-type", state.labels[finding.type] || finding.type));
    top.append(textNode("span", "level-pill", finding.level));
    const title = textNode("h3", "", finding.message);
    const evidence = document.createElement("div");
    evidence.className = "evidence-list";
    Object.entries(finding.evidence).slice(0, 6).forEach(([key, value]) => {
      evidence.append(textNode("span", "", `${key} · ${formatValue(value)}`));
    });
    card.append(top, title, evidence);
    return card;
  });
  $("findings").replaceChildren(...cards);
  $("confidence").textContent = data.confidence || "unknown";
  $("input-hash").textContent = data.input_hash_short || "—";
  $("missing-fields").textContent = data.missing_fields.length
    ? `MISSING · ${data.missing_fields.join(" / ")}`
    : "MISSING · NONE";
}

function renderAgent(agent) {
  $("agent-status").textContent = agent.status;
  $("agent-steps").textContent = agent.steps_used;
  $("agent-tools").textContent = agent.tool_calls_used;
  $("agent-attempts").textContent = agent.tool_attempts_used;
  $("termination-reason").textContent = agent.termination_reason;
  const items = agent.trace.map((event) => {
    const item = document.createElement("li");
    item.className = "trace-item";
    const heading = document.createElement("div");
    heading.className = "trace-event";
    heading.append(textNode("strong", "", state.labels[event.event] || event.event));
    heading.append(textNode("time", "", `${event.elapsed_ms.toFixed(2)} ms`));
    const summary = [event.state, event.tool_name, summarizeDetails(event.details)].filter(Boolean).join(" · ");
    item.append(heading, textNode("p", "", summary));
    return item;
  });
  $("trace").replaceChildren(...items);
}

function renderEvaluation(evaluation) {
  const same = evaluation.same_suite;
  $("same-suite").classList.toggle("invalid", !same);
  $("same-suite").querySelector("strong").textContent = same ? "SAME HASH ✓" : "REPORT MISSING";
  renderPolicyCard($("baseline-eval"), evaluation.baseline, "DETERMINISTIC BASELINE");
  renderPolicyCard($("deepseek-eval"), evaluation.deepseek, "DEEPSEEK V4 FLASH");
}

function renderPolicyCard(root, policy, label) {
  if (!policy.available) {
    root.replaceChildren(textNode("p", "", `${label} 报告尚未生成。`));
    return;
  }
  const head = document.createElement("div");
  head.className = "eval-card-head";
  const name = document.createElement("div");
  name.append(textNode("small", "", label), textNode("h3", "", policy.policy_name));
  const score = document.createElement("div");
  score.className = "eval-score";
  score.append(textNode("strong", "", `${policy.passed_cases}/${policy.total_cases}`), textNode("span", "", "EXPECTED"));
  head.append(name, score);
  const bars = document.createElement("div");
  bars.className = "eval-bars";
  bars.append(
    evaluationBar("TASK COMPLETION", policy.task_completion_rate),
    evaluationBar("GUARDRAIL", policy.guardrail_pass_rate),
    evaluationBar("FACT INTEGRITY", policy.fact_integrity_rate),
  );
  const foot = document.createElement("div");
  foot.className = "eval-foot";
  foot.append(
    evalMetric("P95 LATENCY", policy.p95_latency_ms == null ? "—" : `${policy.p95_latency_ms.toFixed(1)} ms`),
    evalMetric("TOKENS", policy.total_tokens.toLocaleString("en-US")),
    evalMetric("EST. COST", `$${policy.estimated_cost_usd.toFixed(8)}`),
  );
  root.replaceChildren(head, bars, foot);
}

function evaluationBar(label, value) {
  const wrapper = document.createElement("div");
  const row = document.createElement("div");
  row.className = "eval-bar-label";
  row.append(textNode("span", "", label), textNode("strong", "", value == null ? "—" : `${Math.round(value * 100)}%`));
  const track = document.createElement("div");
  track.className = "eval-bar-track";
  const fill = document.createElement("span");
  const rate = Math.max(0, Math.min(100, Math.round((value || 0) * 10) * 10));
  fill.classList.add(`rate-${rate}`);
  track.append(fill);
  wrapper.append(row, track);
  return wrapper;
}

function evalMetric(label, value) {
  const wrapper = document.createElement("div");
  wrapper.append(textNode("small", "", label), textNode("strong", "", value));
  return wrapper;
}

function textNode(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = content;
  return node;
}

function formatValue(value) {
  if (value === null) return "null";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function summarizeDetails(details) {
  return Object.entries(details || {})
    .filter(([key]) => !key.includes("token") && !key.includes("cost"))
    .slice(0, 4)
    .map(([key, value]) => `${key}=${formatValue(value)}`)
    .join(" · ");
}

loadDashboard();
