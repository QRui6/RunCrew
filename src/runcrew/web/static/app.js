const $ = (id) => document.getElementById(id);

const labels = {
  review_agent: "训练复盘 Agent",
  coach_orchestrator: "训练运营 Coach",
  execution_agent: "训练执行职责",
  recovery_agent: "恢复评估职责",
  plan_agent: "计划调整职责",
  completed: "正常完成",
  permission_denied: "权限拒绝",
  confirmation_required: "等待确认",
  step_budget_exhausted: "步骤预算耗尽",
  run_timeout: "运行超时",
};

async function api(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Runtime 数据读取失败");
  return payload;
}

function node(tag, className = "", content = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = content;
  return element;
}

function rate(metric) {
  return metric.value == null ? "—" : `${(metric.value * 100).toFixed(metric.value === 0 || metric.value === 1 ? 0 : 1)}%`;
}

function duration(value) {
  if (value == null) return "—";
  if (value < 1000) return `${Number(value.toFixed(1))} ms`;
  return `${Number((value / 1000).toFixed(2))} s`;
}

function shortDate(value) {
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function renderMetrics(snapshot) {
  const overall = snapshot.overall;
  $("run-success").textContent = rate(overall.run_success);
  $("run-success-sample").textContent = `${overall.run_success.numerator} / ${overall.run_success.denominator} RUN`;
  $("guardrail-rejection").textContent = rate(overall.guardrail_rejection);
  $("guardrail-sample").textContent = `${overall.guardrail_rejection.numerator} / ${overall.guardrail_rejection.denominator} CHECK`;
  $("tool-success").textContent = rate(overall.tool_success);
  $("tool-sample").textContent = `${overall.tool_success.numerator} / ${overall.tool_success.denominator} CALL`;
  $("latency-p95").textContent = duration(overall.latency.p95_ms);
  $("latency-sample").textContent = `${overall.latency.sample_count} RUN SAMPLE`;
  $("sample-scope").textContent = `${snapshot.window_days}天 · ${overall.run_count} Run${snapshot.truncated ? " · 已截断" : ""}`;
  $("coverage-note").textContent = snapshot.coverage_note;
  renderWorkflows(snapshot.workflows);
  renderTerminations(snapshot.termination_reasons);
  renderInvocationGroups("tool-list", snapshot.tools);
  renderInvocationGroups("role-list", snapshot.roles);
}

function renderWorkflows(groups) {
  $("workflow-count").textContent = `${groups.length}组`;
  if (!groups.length) return empty($("workflow-list"), "当前窗口还没有正式 Runtime Run。");
  const rows = groups.map((group) => {
    const row = node("div", "workflow-row");
    const identity = document.createElement("div");
    identity.append(node("h3", "", labels[group.key] || group.key), node("p", "", `${group.metrics.run_count} RUN`));
    row.append(
      identity,
      metricCell("成功率", rate(group.metrics.run_success)),
      metricCell("P95", duration(group.metrics.latency.p95_ms)),
      metricCell("重试率", rate(group.metrics.retry)),
    );
    return row;
  });
  $("workflow-list").replaceChildren(...rows);
}

function metricCell(label, value) {
  const wrapper = document.createElement("div");
  wrapper.append(node("span", "", label), node("strong", "", value));
  return wrapper;
}

function renderTerminations(items) {
  if (!items.length) return empty($("termination-list"), "暂无退出原因样本。");
  $("termination-list").replaceChildren(...items.map((item) => {
    const row = node("div", "distribution-row");
    const bar = node("div", "bar");
    const fill = document.createElement("i");
    fill.style.width = `${Math.max(2, item.rate * 100)}%`;
    bar.append(fill);
    row.append(node("span", "", labels[item.key] || item.key), bar, node("strong", "", String(item.count)));
    return row;
  }));
}

function renderInvocationGroups(rootId, items) {
  const root = $(rootId);
  if (!items.length) return empty(root, "暂无调用样本。");
  root.replaceChildren(...items.map((item) => {
    const row = node("div", "compact-row");
    row.append(
      node("b", "", labels[item.key] || item.key),
      metricCell("尝试", String(item.attempt_count)),
      metricCell("成功", rate(item.success)),
      metricCell("重试", rate(item.retry)),
    );
    return row;
  }));
}

function renderGovernance(report) {
  $("governance-suite").textContent = `${report.suite_version} · ${report.suite_hash.slice(0, 12)}`;
  $("governance-score").textContent = `${report.passed_cases}/${report.total_cases}`;
  const metrics = [
    ["执行前阻断", report.metrics.pre_execution_block_rate],
    ["非法输出阻断", report.metrics.invalid_output_block_rate],
    ["观测故障隔离", report.metrics.observability_failure_isolation_rate],
  ];
  $("governance-metrics").replaceChildren(...metrics.map(([label, value]) => metricCell(label, `${Math.round(value * 100)}%`)));
}

function empty(root, message) {
  root.replaceChildren(node("p", "empty", message));
}

function renderRuns(runs) {
  const root = $("run-list");
  if (!runs.length) {
    const row = document.createElement("tr");
    const cell = node("td", "empty", "暂无运行记录。完成一次训练复盘或 Coach 联合评估后会出现在这里。");
    cell.colSpan = 6;
    row.append(cell);
    return root.replaceChildren(row);
  }
  root.replaceChildren(...runs.map((run) => {
    const row = document.createElement("tr");
    row.tabIndex = 0;
    row.setAttribute("aria-label", `查看运行 ${run.run_id}`);
    row.append(
      node("td", "", shortDate(run.recorded_at)),
      node("td", "", labels[run.workflow] || run.workflow),
      statusCell(run.status),
      node("td", "", duration(run.duration_ms)),
      node("td", "", `${run.tool_call_count} / ${run.retry_count}`),
    );
    const idCell = document.createElement("td");
    idCell.append(node("code", "", run.run_id.slice(0, 16)));
    row.append(idCell);
    row.addEventListener("click", () => openTrace(run.run_id));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") openTrace(run.run_id);
    });
    return row;
  }));
}

function statusCell(status) {
  const cell = document.createElement("td");
  cell.append(node("span", `status ${status}`, status));
  return cell;
}

async function openTrace(runId) {
  const drawer = $("trace-drawer");
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  $("trace-title").textContent = "正在读取…";
  $("trace-summary").replaceChildren();
  $("trace-list").replaceChildren();
  try {
    const capture = await api(`/api/runtime/runs/${encodeURIComponent(runId)}`);
    $("trace-title").textContent = labels[capture.run.workflow] || capture.run.workflow;
    renderTraceSummary(capture.run);
    renderTrace(capture.spans);
  } catch (error) {
    $("trace-title").textContent = "时间线读取失败";
    $("trace-list").replaceChildren(node("li", "", error.message));
  }
}

function renderTraceSummary(run) {
  const values = [
    ["RUN ID", run.run_id],
    ["终态", run.status],
    ["退出原因", labels[run.termination_reason] || run.termination_reason],
    ["耗时", duration(run.duration_ms)],
    ["工作流版本", run.workflow_version],
    ["TRACE HASH", run.trace_hash.slice(0, 16)],
  ];
  $("trace-summary").replaceChildren(...values.map(([label, value]) => {
    const wrapper = document.createElement("div");
    wrapper.append(node("span", "", label), node("strong", "", value));
    return wrapper;
  }));
}

function renderTrace(spans) {
  $("trace-list").replaceChildren(...spans.map((span) => {
    const item = document.createElement("li");
    const identity = [span.kind, span.node, span.tool_name, span.attempt ? `TRY ${span.attempt}` : null]
      .filter(Boolean).join(" · ");
    item.append(
      node("h3", "", span.name),
      node("p", "", `${identity || "RUN"} · ${span.status}`),
      node("time", "", `+${duration(span.start_offset_ms)}`),
    );
    return item;
  }));
}

function closeTrace() {
  const drawer = $("trace-drawer");
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
}

document.querySelectorAll("[data-close-drawer]").forEach((element) => element.addEventListener("click", closeTrace));
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeTrace(); });

async function load() {
  $("loading").hidden = false;
  $("workspace").hidden = true;
  $("error").hidden = true;
  const windowDays = $("window-days").value;
  try {
    const [metrics, listing, governance] = await Promise.all([
      api(`/api/runtime/metrics?window_days=${encodeURIComponent(windowDays)}`),
      api("/api/runtime/runs?limit=50"),
      api("/api/runtime/governance-evaluation"),
    ]);
    renderMetrics(metrics);
    renderRuns(listing.runs);
    renderGovernance(governance);
    $("workspace").hidden = false;
  } catch (error) {
    $("error").textContent = error.message;
    $("error").hidden = false;
  } finally {
    $("loading").hidden = true;
  }
}

$("metric-filter").addEventListener("submit", (event) => { event.preventDefault(); load(); });
load();
