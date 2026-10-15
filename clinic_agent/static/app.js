(() => {
  const state = {
    sessionId: localStorage.getItem("clinic-agent-session-id") || null,
    session: null,
    messages: [],
    sending: false,
  };

  const nodes = {
    emergencyBanner: document.querySelector("#emergencyBanner"),
    sessionForm: document.querySelector("#sessionForm"),
    messageForm: document.querySelector("#messageForm"),
    messageInput: document.querySelector("#messageInput"),
    sendButton: document.querySelector("#sendButton"),
    messages: document.querySelector("#messages"),
    sessionList: document.querySelector("#sessionList"),
    sessionTitle: document.querySelector("#sessionTitle"),
    statusLine: document.querySelector("#statusLine"),
    urgencyCard: document.querySelector("#urgencyCard"),
    departmentList: document.querySelector("#departmentList"),
    healthInfo: document.querySelector("#healthInfo"),
    copySummary: document.querySelector("#copySummary"),
    refreshSessions: document.querySelector("#refreshSessions"),
  };

  const urgencyInfo = {
    emergency: ["疑似急症，请立即就医", "emergency"],
    urgent: ["建议24小时内就医", "urgent"],
    routine: ["建议择期门诊评估", "routine"],
    self_care: ["可先居家观察", "self_care"],
    info_needed: ["待补充信息", "info"],
  };

  const sexLabels = { male: "男", female: "女", other: "其他", unknown: "不提供" };

  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    let payload = null;
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(payload?.error || `请求失败（${response.status}）`);
    return payload;
  }

  async function loadHealth() {
    try {
      const health = await api("/api/health");
      nodes.healthInfo.innerHTML = `
        <span class="status-pill ${esc(health.model_backend)}">${
          health.model_backend === "configured" ? "模型增强" : "规则分诊"
        }</span>
        <span>规则引擎始终先执行；模型回复会经过安全校验，失败时自动回退。</span>`;
    } catch (error) {
      nodes.healthInfo.innerHTML = `<span class="status-pill">离线</span><span>${esc(error.message)}</span>`;
    }
  }

  async function loadSessions() {
    try {
      const data = await api("/api/sessions?limit=50");
      nodes.sessionList.innerHTML = data.sessions.length ? "" : `<p class="muted">暂无历史问诊。</p>`;
      for (const session of data.sessions) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `session-item${session.id === state.sessionId ? " active" : ""}`;
        button.innerHTML = `
          <span class="session-item-title">
            <span>${esc(session.patient_alias || "未命名访客")}</span>
            <span class="dot ${esc(session.urgency || "info_needed")}" aria-hidden="true"></span>
          </span>
          <span class="session-item-meta">${
            session.age_years === null || session.age_years === undefined ? "年龄未填" : `${esc(session.age_years)}岁`
          } · ${esc(sexLabels[session.sex] || "不提供")} · ${formatTime(session.updated_at)}</span>`;
        button.addEventListener("click", () => selectSession(session.id));
        nodes.sessionList.appendChild(button);
      }
    } catch (error) {
      nodes.sessionList.innerHTML = `<p class="muted">${esc(error.message)}</p>`;
    }
  }

  async function createSession(event) {
    event.preventDefault();
    const form = new FormData(nodes.sessionForm);
    const age = form.get("age_years");
    try {
      const payload = await api("/api/sessions", {
        method: "POST",
        body: JSON.stringify({
          patient_alias: form.get("patient_alias") || "未命名访客",
          age_years: age === "" ? null : Number(age),
          sex: form.get("sex") || "unknown",
        }),
      });
      await selectSession(payload.session.id, false);
      localStorage.setItem("clinic-agent-session-id", payload.session.id);
      nodes.messageInput.focus();
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  async function selectSession(sessionId, restore = true) {
    if (!sessionId) return;
    try {
      const data = await api(`/api/sessions/${encodeURIComponent(sessionId)}`);
      state.sessionId = data.session.id;
      state.session = data.session;
      state.messages = data.messages;
      if (restore) localStorage.setItem("clinic-agent-session-id", data.session.id);
      renderConversation();
      renderTriage(data.session, [...data.messages].reverse().find((message) => message.triage)?.triage);
      await loadSessions();
      nodes.messageInput.focus();
    } catch (error) {
      if (error.message.includes("not found")) {
        localStorage.removeItem("clinic-agent-session-id");
        state.sessionId = null;
        renderConversation();
      }
      setStatus(error.message, true);
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    if (state.sending || !state.sessionId) return;
    const content = nodes.messageInput.value.trim();
    if (!content) return;
    state.sending = true;
    nodes.sendButton.disabled = true;
    nodes.sendButton.textContent = "评估中…";
    try {
      const data = await api(`/api/sessions/${encodeURIComponent(state.sessionId)}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      nodes.messageInput.value = "";
      state.session = data.session;
      state.messages.push(data.user_message, data.assistant_message);
      renderConversation();
      renderTriage(data.session, data.triage);
      await loadSessions();
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      state.sending = false;
      nodes.sendButton.disabled = false;
      nodes.sendButton.textContent = "发送";
      nodes.messageInput.focus();
    }
  }

  function renderConversation() {
    if (!state.session) {
      nodes.sessionTitle.textContent = "正在准备问诊";
      nodes.statusLine.textContent = "请先开始一次新问诊。";
      nodes.emergencyBanner.classList.add("hidden");
      return;
    }
    const session = state.session;
    const identity = [
      session.patient_alias || "未命名访客",
      session.age_years === null || session.age_years === undefined ? null : `${session.age_years}岁`,
      sexLabels[session.sex] || "不提供",
    ].filter(Boolean).join(" · ");
    nodes.sessionTitle.textContent = identity;
    setStatus(`开始于 ${formatTime(session.created_at)}`);

    nodes.messages.innerHTML = state.messages.length ? "" : `
      <article class="empty-state"><h3>请描述症状</h3><ul><li>部位、持续时间和严重程度。</li><li>伴随症状与已测体温、血压。</li><li>慢性病、过敏、孕期或正在用药。</li></ul></article>`;

    for (const message of state.messages) {
      const article = document.createElement("article");
      article.className = `message ${message.role}`;
      const body = document.createElement("div");
      body.className = "message-body";
      body.textContent = message.content;
      article.appendChild(body);
      if (message.triage && message.role === "assistant") article.insertAdjacentHTML("beforeend", triageTemplate(message.triage));
      article.insertAdjacentHTML("beforeend", `<span class="message-time">${formatTime(message.created_at)}</span>`);
      nodes.messages.appendChild(article);
    }
    nodes.messages.scrollTop = nodes.messages.scrollHeight;
    nodes.emergencyBanner.classList.toggle("hidden", session.urgency !== "emergency");
  }

  function triageTemplate(triage) {
    const [label] = urgencyInfo[triage.urgency] || ["安全级别待定"];
    const departments = (triage.departments || []).map((item) => `<span class="tag">${esc(item)}</span>`).join("");
    return `
      <div class="triage-mini">
        <strong>${esc(label)}</strong>
        ${triage.follow_ups?.length ? `下一步：${esc(triage.follow_ups.slice(0, 2).join("；"))}` : ""}
        <div class="tag-row">${departments}</div>
      </div>`;
  }

  function renderTriage(session, triage) {
    const urgency = session?.urgency || "info_needed";
    const [label, className] = urgencyInfo[urgency] || urgencyInfo.info_needed;
    const reason = triage?.reasons?.length ? triage.reasons.slice(0, 2).join("；") : "发送症状后显示安全级别。";
    nodes.urgencyCard.className = `urgency-card ${className}`;
    nodes.urgencyCard.innerHTML = `<span class="urgency-title">${esc(label)}</span><span class="muted">${esc(reason)}</span>`;
    nodes.departmentList.innerHTML = (session?.departments || []).map((item) => `<span class="department-pill">${esc(item)}</span>`).join("");
    nodes.emergencyBanner.classList.toggle("hidden", urgency !== "emergency");
  }

  async function copySummary() {
    if (!state.session || state.messages.length === 0) {
      setStatus("当前没有可复制的对话摘要。", true);
      return;
    }
    const summary = [
      `就诊人：${state.session.patient_alias || "未命名访客"}`,
      `年龄：${state.session.age_years ?? "未提供"}；性别：${sexLabels[state.session.sex] || "未提供"}`,
      `当前建议：${(urgencyInfo[state.session.urgency] || ["待补充信息"])[0]}`,
      `建议科室：${state.session.departments?.join("、") || "待定"}`,
      "",
      ...state.messages.map((message) => `${message.role === "user" ? "本人" : "助手"}：${message.content}`),
      "",
      "以上由 clinic-agent 整理，仅供就诊沟通参考，不构成诊断。",
    ].join("\n");
    try {
      await navigator.clipboard.writeText(summary);
      setStatus("就诊摘要已复制。");
    } catch (_) {
      const area = document.createElement("textarea");
      area.value = summary;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      setStatus("就诊摘要已复制。");
    }
  }

  function setStatus(message, isError = false) {
    nodes.statusLine.textContent = message;
    nodes.statusLine.style.color = isError ? "#c62828" : "";
  }

  function formatTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
  }

  nodes.sessionForm.addEventListener("submit", createSession);
  nodes.messageForm.addEventListener("submit", sendMessage);
  nodes.copySummary.addEventListener("click", copySummary);
  nodes.refreshSessions.addEventListener("click", loadSessions);

  (async function initialize() {
    await loadHealth();
    await loadSessions();
    if (state.sessionId) await selectSession(state.sessionId);
    else {
      nodes.sessionForm.requestSubmit();
    }
  })();
})();
