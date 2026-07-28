/* Cupid Agent — frontend logic */

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const state = {
  mode: "agent",
  provider: "mock",
  busy: false,
  tests: [],
  profiles: [],
  user: null,
  genderFilter: "all",
};

const STORAGE_KEY = "cupid.user_id";

const scroll = $("#chatScroll");
const input = $("#input");
const sendBtn = $("#sendBtn");
const statusDot = $("#statusDot");

/* ---------------- boot ---------------- */

async function boot() {
  try {
    const meta = await fetchJSON("/api/meta");
    $("#metaUsers").textContent = meta.user_count;
    $("#metaTools").textContent = meta.tools.length;
    $("#metaGuard").textContent = meta.max_iterations;
    state.provider = meta.default_provider || "mock";
    $("#providerSelect").value = state.provider;
    renderTools(meta.tool_schemas);
    setStatus("online");
  } catch {
    setStatus("error");
  }
  await Promise.all([loadTests(), loadUsers()]);
  await restoreSession();
}

/* ---------------- login ---------------- */

async function restoreSession() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) {
    try {
      const { user } = await fetchJSON("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: saved }),
      });
      applyUser(user);
      return;
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
  }
  openLogin();
}

function openLogin() {
  $("#loginError").textContent = "";
  $("#loginOverlay").classList.add("open");
  renderLoginList();
  $("#loginSearch").focus();
}

function closeLogin() {
  $("#loginOverlay").classList.remove("open");
}

function genderClass(gender) {
  if (gender === "nam") return "nam";
  if (gender === "nữ") return "nu";
  return "khac";
}

function renderLoginList() {
  const query = $("#loginSearch").value.trim().toLowerCase();
  const list = $("#loginList");
  list.innerHTML = "";

  const matches = state.profiles.filter((p) => {
    const byGender =
      state.genderFilter === "all" || p.gender === state.genderFilter;
    const haystack = `${p.user_id} ${p.display_name} ${p.city}`.toLowerCase();
    return byGender && haystack.includes(query);
  });

  if (!matches.length) {
    list.append(el("div", "login-empty", "Không có hồ sơ nào khớp bộ lọc."));
    return;
  }

  matches.forEach((p) => {
    const item = el("button", "login-item");
    item.append(el("div", "uavatar", p.display_name.charAt(0)));

    const info = el("div", "uinfo");
    const name = el("div", "uname");
    name.append(
      document.createTextNode(p.display_name),
      el("span", "uid", p.user_id),
      el("span", `gender-tag ${genderClass(p.gender)}`, p.gender || "?")
    );
    info.append(
      name,
      el("div", "umeta", `${p.age} tuổi · ${p.city} · muốn: ${p.intent || "–"}`),
      el("div", "umeta", `Tìm: ${(p.seeking || []).join(", ") || "–"}`)
    );
    item.append(info);
    item.onclick = () => doLogin(p.user_id);
    list.append(item);
  });
}

async function doLogin(userId) {
  try {
    const { user } = await fetchJSON("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });
    localStorage.setItem(STORAGE_KEY, user.user_id);
    applyUser(user);
    closeLogin();
  } catch (err) {
    $("#loginError").textContent = err.message;
  }
}

function applyUser(user) {
  state.user = user;
  const chip = $("#userChip");
  if (!user) {
    chip.classList.remove("logged-in");
    $("#userChipAvatar").textContent = "?";
    $("#userChipName").textContent = "Khách";
    $("#userChipMeta").textContent = "Bấm để đăng nhập";
    return;
  }
  chip.classList.add("logged-in");
  $("#userChipAvatar").textContent = user.display_name.charAt(0);
  $("#userChipName").textContent = `${user.display_name} · ${user.user_id}`;
  $("#userChipMeta").textContent = `${user.gender} · ${user.age} tuổi · ${user.city}`;
}

function setStatus(kind) {
  statusDot.className = `status-dot ${kind}`;
}

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

/* ---------------- sidebar ---------------- */

async function loadTests() {
  const { test_cases } = await fetchJSON("/api/test-cases");
  state.tests = test_cases;
  const list = $("#testList");
  list.innerHTML = "";

  test_cases.forEach((tc) => {
    const card = el("div", "tcard");
    const top = el("div", "tcard-top");
    top.append(el("span", "tcard-id", `#${tc.id}`), el("span", "tcard-name", tc.name || ""));
    card.append(top, el("div", "tcard-q", tc.question));

    const tags = el("div", "tcard-tags");
    tags.append(el("span", `tag path-${tc.expected_path}`, tc.expected_path));
    if (tc.core_lab_case) tags.append(el("span", "tag core", "core"));
    (tc.expected_tools || []).forEach((t) => tags.append(el("span", "tag", t)));
    card.append(tags);

    card.onclick = () => runTest(tc.id);
    list.append(card);
  });
}

async function loadUsers() {
  const db = await fetchJSON("/api/database");
  state.profiles = db.profiles || [];
  const list = $("#userList");
  list.innerHTML = "";

  state.profiles.forEach((p) => {
    const card = el("div", "ucard");
    card.append(el("div", "uavatar", p.display_name.charAt(0)));

    const info = el("div", "uinfo");
    const name = el("div", "uname");
    name.append(
      document.createTextNode(p.display_name),
      el("span", "uid", p.user_id),
      el("span", `gender-tag ${genderClass(p.gender)}`, p.gender || "?")
    );
    info.append(
      name,
      el("div", "umeta", `${p.age} tuổi · ${p.city}`),
      el("div", "umeta", (p.hobbies || []).join(", "))
    );
    card.append(info);
    card.onclick = () => {
      input.value = `Cho mình xem hồ sơ đầy đủ của user ${p.user_id}.`;
      input.focus();
    };
    list.append(card);
  });
}

function renderTools(schemas) {
  const list = $("#toolList");
  list.innerHTML = "";
  Object.entries(schemas || {}).forEach(([name, spec]) => {
    const card = el("div", "toolcard");
    const params = Object.entries(spec.parameters || {})
      .map(([k, v]) => `${k}: ${v}`)
      .join("\n");
    card.append(el("div", "toolname", `${name}[…]`), el("div", "toolparams", params));
    const write = spec.side_effect === "write";
    card.append(el("span", `side-effect ${write ? "write" : "read"}`, spec.side_effect));
    list.append(card);
  });
}

/* ---------------- rendering answers ---------------- */

function clearWelcome() {
  const w = $("#welcome");
  if (w) w.remove();
}

function addUserMessage(text) {
  clearWelcome();
  const wrap = el("div", "msg user");
  wrap.append(el("div", "bubble-user", text));
  scroll.append(wrap);
  scrollToBottom();
}

function addTyping() {
  const wrap = el("div", "msg");
  const card = el("div", "answer-card");
  const typing = el("div", "typing");
  typing.append(el("i"), el("i"), el("i"));
  card.append(typing);
  wrap.append(card);
  scroll.append(wrap);
  scrollToBottom();
  return wrap;
}

function scrollToBottom() {
  scroll.scrollTop = scroll.scrollHeight;
}

function badge(cls, text) {
  return el("span", `badge ${cls}`, text);
}

function buildAnswerCard(result, opts = {}) {
  const isAgent = result.mode === "react_agent";
  const card = el("div", "answer-card");

  const head = el("div", "answer-head");
  head.append(
    el("span", "answer-icon", isAgent ? "🤖" : "💬"),
    el("span", "answer-title", opts.title || (isAgent ? "ReAct Agent" : "Chatbot Baseline"))
  );
  if (isAgent) {
    head.append(badge("tools", `${result.tool_calls} tool`), badge("steps", `${result.steps} step`));
    if (result.guardrail) head.append(badge("guard", "guardrail"));
  } else {
    head.append(badge("tools", "0 tool"));
  }
  if (opts.passed !== undefined) {
    head.append(opts.passed ? badge("pass", "PASS") : badge("fail", "CHECK"));
  }
  card.append(head, el("div", "answer-body", result.response));

  const events = result.events || [];
  if (isAgent && events.length) {
    card.append(buildTrace(events));
  }
  return card;
}

function buildTrace(events) {
  const wrap = el("div", "trace");
  const toggle = el("button", "trace-toggle");
  toggle.append(el("span", "caret", "▶"), el("span", null, `Trace ReAct (${events.length} sự kiện)`));

  const body = el("div", "trace-body");
  events.forEach((ev) => {
    const bad = ev.kind === "observation" && ev.ok === false;
    const step = el("div", `step ${ev.kind}${bad ? " bad" : ""}`);
    const labels = {
      thought: "🧠 Thought",
      action: "🛠 Action",
      observation: "👁 Observation",
      final: "🏁 Final Answer",
      guardrail: "🛡 Guardrail",
      error: "⚠️ API Error",
    };
    step.append(el("div", "step-label", `Step ${ev.step} · ${labels[ev.kind] || ev.kind}`));

    if (ev.kind === "action") {
      step.append(el("div", "step-code", `${ev.tool}[${(ev.args || []).join(", ")}]`));
    } else if (ev.kind === "observation") {
      step.append(el("div", "step-code", ev.text));
    } else {
      step.append(el("div", "step-text", ev.text));
    }
    body.append(step);
  });

  toggle.onclick = () => {
    toggle.classList.toggle("open");
    body.classList.toggle("open");
  };
  wrap.append(toggle, body);
  return wrap;
}

/* ---------------- actions ---------------- */

function setBusy(busy) {
  state.busy = busy;
  sendBtn.disabled = busy;
  $("#runAllBtn").disabled = busy;
  setStatus(busy ? "busy" : "online");
}

async function send() {
  const message = input.value.trim();
  if (!message || state.busy) return;

  input.value = "";
  input.style.height = "auto";
  addUserMessage(message);
  setBusy(true);
  const placeholder = addTyping();

  try {
    const data = await fetchJSON("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        mode: state.mode,
        provider: state.provider,
        user_id: state.user ? state.user.user_id : null,
      }),
    });

    const wrap = el("div", "msg");
    if (data.mode === "both") {
      const grid = el("div", "compare");
      grid.append(
        buildAnswerCard(data.chatbot, { title: "💬 Chatbot (không tool)" }),
        buildAnswerCard(data.agent, { title: "🤖 ReAct Agent (có tool)" })
      );
      wrap.append(grid);
    } else {
      wrap.append(buildAnswerCard(data));
    }
    placeholder.replaceWith(wrap);
  } catch (err) {
    const wrap = el("div", "msg");
    const card = el("div", "answer-card");
    card.append(
      el("div", "answer-head", ""),
      el("div", "answer-body", `⚠️ Lỗi: ${err.message}`)
    );
    wrap.append(card);
    placeholder.replaceWith(wrap);
  } finally {
    setBusy(false);
    scrollToBottom();
  }
}

async function runTest(id) {
  if (state.busy) return;
  const tc = state.tests.find((t) => t.id === id);
  if (!tc) return;

  addUserMessage(`[Test #${id}] ${tc.question}`);
  setBusy(true);
  const placeholder = addTyping();

  try {
    const data = await fetchJSON("/api/run-test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id,
        provider: state.provider,
        compare: true,
        user_id: state.user ? state.user.user_id : null,
      }),
    });

    const wrap = el("div", "msg");
    const grid = el("div", "compare");
    grid.append(buildAnswerCard(data.chatbot, { title: "💬 Chatbot Baseline" }));
    if (data.agent) {
      grid.append(
        buildAnswerCard(data.agent, {
          title: "🤖 ReAct Agent",
          passed: data.passed,
        })
      );
    }
    wrap.append(grid);
    placeholder.replaceWith(wrap);
  } catch (err) {
    const wrap = el("div", "msg");
    const card = el("div", "answer-card");
    card.append(el("div", "answer-body", `⚠️ Lỗi: ${err.message}`));
    wrap.append(card);
    placeholder.replaceWith(wrap);
  } finally {
    setBusy(false);
    scrollToBottom();
  }
}

async function runCore() {
  const core = state.tests.filter((t) => t.core_lab_case);
  for (const tc of core) {
    await runTest(tc.id);
  }
}

/* ---------------- events ---------------- */

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $(`#panel-${tab.dataset.tab}`).classList.add("active");
  };
});

document.querySelectorAll(".mode").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".mode").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.mode = btn.dataset.mode;
  };
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.onclick = () => {
    input.value = chip.dataset.q;
    send();
  };
});

$("#providerSelect").onchange = (e) => {
  state.provider = e.target.value;
};

$("#refreshDbBtn").onclick = loadUsers;
$("#runAllBtn").onclick = runCore;
sendBtn.onclick = send;

$("#userChip").onclick = openLogin;
$("#loginSearch").oninput = renderLoginList;
$("#guestBtn").onclick = () => {
  localStorage.removeItem(STORAGE_KEY);
  applyUser(null);
  closeLogin();
};

document.querySelectorAll(".gfilter").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".gfilter").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.genderFilter = btn.dataset.gender;
    renderLoginList();
  };
});

$("#loginOverlay").addEventListener("click", (e) => {
  // Chỉ đóng khi đã đăng nhập, tránh kẹt ở trạng thái không rõ user.
  if (e.target === $("#loginOverlay") && state.user) closeLogin();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && state.user) closeLogin();
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
});

boot();
