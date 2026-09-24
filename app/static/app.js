const state = {
  media: [],
  enabledProviders: new Set(),
  currentMediaId: null,
  providerLabels: { zimuku: "字幕库", subhd: "SubHD", assrt: "assrt", opensubtitles: "OpenSubtitles 网页", opensubtitles_api: "OpenSubtitles API" },
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  const node = document.createElement("span");
  node.textContent = value ?? "";
  return node.innerHTML;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || `请求失败 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
  const titles = { media: "媒体", search: "字幕", settings: "设置" };
  $("#page-title").textContent = titles[name] || "SubHub";
}

async function loadConfig() {
  try {
    const data = await api("/web-api/config");
    $("#brand-version").textContent = `v${data.version}`;
  } catch (_) { /* 保持默认 */ }
}

async function loadProviderSettings() {
  try {
    const data = await api("/web-api/settings/providers");
    state.enabledProviders = new Set(Object.entries(data.providers).filter(([, enabled]) => enabled).map(([name]) => name));
    renderProviders();
  } catch (_) { /* 使用默认 */ }
}

function renderProviders() {
  const hints = { zimuku: "免配置,自动过验证码", subhd: "免配置", assrt: "需 Token", opensubtitles: "需 FlareSolverr", opensubtitles_api: "需官方凭据" };
  $("#provider-list").innerHTML = Object.keys(state.providerLabels).map((name) => `
    <label class="provider-row">
      <span><strong>${state.providerLabels[name]}</strong><small>${hints[name] || ""}</small></span>
      <input type="checkbox" data-provider="${name}" ${state.enabledProviders.has(name) ? "checked" : ""}>
    </label>`).join("");
  document.querySelectorAll("[data-provider]").forEach((input) => input.addEventListener("change", () => changeProvider(input)));
}

async function changeProvider(input) {
  const was = state.enabledProviders.has(input.dataset.provider);
  if (input.checked) state.enabledProviders.add(input.dataset.provider); else state.enabledProviders.delete(input.dataset.provider);
  try {
    const data = await api("/web-api/settings/providers", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ providers: { [input.dataset.provider]: input.checked } }),
    });
    state.enabledProviders = new Set(Object.entries(data.providers).filter(([, enabled]) => enabled).map(([name]) => name));
  } catch (error) {
    input.checked = was;
    if (was) state.enabledProviders.add(input.dataset.provider); else state.enabledProviders.delete(input.dataset.provider);
    alert(error.message);
  }
  renderProviders();
}

async function loadMedia() {
  $("#media-list").innerHTML = '<p class="empty">正在扫描媒体库…</p>';
  try {
    state.media = await api("/web-api/media");
    renderMedia();
  } catch (error) {
    $("#media-list").innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
  }
}

function renderMedia() {
  const filter = $("#media-filter").value.trim().toLowerCase();
  const items = state.media.filter((item) => `${item.title} ${item.path}`.toLowerCase().includes(filter));
  $("#media-list").innerHTML = items.length ? items.map((item) => `
    <article class="media-card">
      <div class="poster">
        ${item.is_strm ? '<span class="badge">STRM</span>' : ""}
        ${item.poster_url ? `<img src="${item.poster_url.replace(/^\/api\//, "/web-api/")}" alt="" loading="lazy">` : '<span class="fallback">🎬</span>'}
      </div>
      <div class="media-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
      <button class="btn search-media" data-id="${item.id}" data-title="${escapeHtml(item.title)}">搜索字幕</button>
    </article>`).join("") : '<p class="empty">没有找到媒体文件</p>';
  document.querySelectorAll(".poster img").forEach((img) => img.addEventListener("error", () => img.remove()));
  document.querySelectorAll(".search-media").forEach((button) => button.addEventListener("click", () => {
    state.currentMediaId = button.dataset.id || null;
    $("#keyword").value = button.dataset.title;
    showView("search");
    search(button.dataset.title);
  }));
}

async function search(keyword) {
  if (!state.enabledProviders.size) {
    $("#results").innerHTML = '<p class="empty error">请先在设置中开启至少一个字幕源</p>';
    return;
  }
  $("#results").innerHTML = '<p class="empty">正在搜索字幕…</p>';
  $("#search-meta").textContent = "";
  const params = new URLSearchParams({ keyword });
  state.enabledProviders.forEach((provider) => params.append("source", provider));
  try {
    const data = await api(`/web-api/search?${params}`);
    const errors = Object.entries(data.errors).map(([name, message]) => `<span class="error">${escapeHtml(state.providerLabels[name] || name)}：${escapeHtml(message)}</span>`).join("");
    $("#search-meta").innerHTML = errors;
    renderResults(data.results);
  } catch (error) {
    $("#results").innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
  }
}

function renderResults(results) {
  $("#results").innerHTML = results.length ? results.map((item, index) => `
    <article class="result">
      <div class="result-main">
        <span class="source">${escapeHtml(state.providerLabels[item.provider] || item.provider)}</span>
        <div>
          <div class="result-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
          ${item.movie_title && item.movie_title !== item.title ? `<div class="result-sub" title="${escapeHtml(item.movie_title)}">${escapeHtml(item.movie_title)}</div>` : ""}
        </div>
      </div>
      <button class="btn primary download" data-index="${index}">下载</button>
    </article>`).join("") : '<p class="empty">没有搜到字幕,请尝试精简片名。</p>';
  document.querySelectorAll(".download").forEach((button) => button.addEventListener("click", () => download(results[Number(button.dataset.index)], button)));
}

async function download(item, button) {
  button.disabled = true;
  button.textContent = "下载中…";
  try {
    const data = await api("/web-api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: item.provider,
        subtitle_id: item.id,
        detail_url: item.detail_url,
        title: item.title,
        media_id: state.currentMediaId,
      }),
    });
    button.textContent = "已保存";
    button.title = data.path;
    if (data.note) $("#search-meta").innerHTML = `<span class="error">${escapeHtml(data.note)}</span>`;
  } catch (error) {
    button.textContent = "重试";
    $("#search-meta").innerHTML = `<span class="error">${escapeHtml(error.message)}</span>`;
  } finally {
    button.disabled = false;
  }
}

async function loadAssrt() {
  try {
    const data = await api("/web-api/settings/assrt");
    $("#assrt-token").placeholder = data.token_set ? "已保存,留空保持不变" : "填写 assrt Token";
  } catch (_) { /* 忽略 */ }
}

async function saveAssrt() {
  const button = $("#save-assrt");
  button.disabled = true;
  $("#assrt-message").textContent = "";
  try {
    const data = await api("/web-api/settings/assrt", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: $("#assrt-token").value.trim() || null }),
    });
    $("#assrt-token").value = "";
    $("#assrt-token").placeholder = "已保存,留空保持不变";
    $("#assrt-message").textContent = data.configured ? "已保存并开启 assrt" : "已清除 assrt 配置";
    await loadProviderSettings();
  } catch (error) {
    $("#assrt-message").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function loadOpenSubtitlesWeb() {
  try {
    const data = await api("/web-api/settings/opensubtitles");
    if (data.url) $("#flaresolverr-url").value = data.url;
    $("#flaresolverr-message").textContent = data.url ? "已配置 FlareSolverr" : "";
  } catch (_) { /* 忽略 */ }
}

async function saveOpenSubtitlesWeb() {
  const button = $("#save-flaresolverr");
  button.disabled = true;
  $("#flaresolverr-message").textContent = "";
  try {
    const data = await api("/web-api/settings/opensubtitles", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: $("#flaresolverr-url").value.trim() }),
    });
    $("#flaresolverr-message").textContent = data.url ? "已保存并开启 OpenSubtitles 网页版" : "已清除 FlareSolverr 配置";
    await loadProviderSettings();
  } catch (error) {
    $("#flaresolverr-message").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function loadOpenSubtitlesApi() {
  try {
    const data = await api("/web-api/settings/opensubtitles-api");
    $("#os-api-key").placeholder = data.api_key_set ? "已保存,留空保持不变" : "API Key";
    $("#os-username").placeholder = data.username_set ? "已保存,留空保持不变" : "用户名";
    $("#os-password").placeholder = data.password_set ? "已保存,留空保持不变" : "密码";
    $("#os-message").textContent = data.configured ? "已配置" : "";
  } catch (_) { /* 忽略 */ }
}

async function saveOpenSubtitlesApi() {
  const button = $("#save-os");
  button.disabled = true;
  $("#os-message").textContent = "";
  try {
    await api("/web-api/settings/opensubtitles-api", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: $("#os-api-key").value.trim() || null,
        username: $("#os-username").value.trim() || null,
        password: $("#os-password").value || null,
      }),
    });
    $("#os-api-key").value = "";
    $("#os-username").value = "";
    $("#os-password").value = "";
    $("#os-message").textContent = "已保存并开启 OpenSubtitles API";
    await loadProviderSettings();
  } catch (error) {
    $("#os-message").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function loadPatterns() {
  try {
    const data = await api("/web-api/settings/title-patterns");
    renderPatterns(data.patterns);
  } catch (error) {
    $("#pattern-list").innerHTML = `<p class="message error">${escapeHtml(error.message)}</p>`;
  }
}

function renderPatterns(patterns) {
  $("#pattern-list").innerHTML = patterns.map((pattern, index) => `
    <div class="pattern-row">
      <span>${index + 1}</span>
      <input class="pattern-input" value="${escapeHtml(pattern)}" aria-label="正则 ${index + 1}">
      <button class="btn remove-pattern" data-index="${index}" type="button">删除</button>
    </div>`).join("");
  document.querySelectorAll(".remove-pattern").forEach((button) => button.addEventListener("click", () => {
    const patterns = currentPatterns();
    patterns.splice(Number(button.dataset.index), 1);
    renderPatterns(patterns.length ? patterns : [""]);
  }));
}

function currentPatterns() {
  return [...document.querySelectorAll(".pattern-input")].map((input) => input.value.trim()).filter(Boolean);
}

async function savePatterns() {
  $("#pattern-test-result").textContent = "";
  try {
    const data = await api("/web-api/settings/title-patterns", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patterns: currentPatterns() }),
    });
    renderPatterns(data.patterns);
    $("#pattern-test-result").textContent = "已保存";
    await loadMedia();
  } catch (error) {
    $("#pattern-test-result").textContent = error.message;
  }
}

async function testPatterns() {
  try {
    const data = await api("/web-api/settings/title-patterns/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: $("#pattern-test-filename").value, patterns: currentPatterns() }),
    });
    $("#pattern-test-result").textContent = `识别结果：${data.title}`;
  } catch (error) {
    $("#pattern-test-result").textContent = `测试失败：${error.message}`;
  }
}

document.querySelectorAll(".nav-item").forEach((item) => item.addEventListener("click", () => showView(item.dataset.view)));
$("#refresh").addEventListener("click", loadMedia);
$("#media-filter").addEventListener("input", renderMedia);
$("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.currentMediaId = null;
  search($("#keyword").value.trim());
});
$("#save-assrt").addEventListener("click", saveAssrt);
$("#save-flaresolverr").addEventListener("click", saveOpenSubtitlesWeb);
$("#save-os").addEventListener("click", saveOpenSubtitlesApi);
$("#save-patterns").addEventListener("click", savePatterns);
$("#test-patterns").addEventListener("click", testPatterns);

Promise.all([loadConfig(), loadProviderSettings(), loadAssrt(), loadOpenSubtitlesWeb(), loadOpenSubtitlesApi(), loadPatterns(), loadMedia()]);
