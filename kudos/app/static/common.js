/* Shared helpers. All user content is rendered with textContent (never innerHTML). */
(function () {
  "use strict";
  const csrf = document.querySelector('meta[name="csrf-token"]').content;

  async function api(path, options = {}) {
    const opts = {
      method: options.method || "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    };
    if (opts.method !== "GET") opts.headers["X-CSRF-Token"] = csrf;
    if (options.body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(options.body);
    }
    let resp;
    try {
      resp = await fetch(path, opts);
    } catch (e) {
      throw { status: 0, code: "network_error", message: "Network error. Check your connection and try again." };
    }
    if (resp.status === 401) {
      window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
      throw { status: 401, code: "unauthenticated", message: "Please sign in." };
    }
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const err = data.error || {};
      throw { status: resp.status, code: err.code || "error", message: err.message || "Something went wrong.", fields: err.fields || {} };
    }
    return data;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function relativeTime(iso) {
    const then = new Date(iso);
    const secs = Math.round((Date.now() - then.getTime()) / 1000);
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    const steps = [[60, "second"], [60, "minute"], [24, "hour"], [7, "day"], [4.35, "week"], [12, "month"], [Infinity, "year"]];
    let value = secs;
    for (const [size, unit] of steps) {
      if (Math.abs(value) < size) return rtf.format(-Math.round(value), unit);
      value /= size;
    }
    return then.toLocaleString();
  }

  function timeEl(iso) {
    const t = el("time", "time", relativeTime(iso));
    t.dateTime = iso;
    t.title = new Date(iso).toLocaleString();
    return t;
  }

  function kudosCard(k) {
    const li = el("li", "kudos");
    li.dataset.id = k.id;
    const head = el("p", "kudos-head");
    head.append(el("strong", null, k.sender.display_name), el("span", "arrow", " → "),
                el("strong", null, k.recipient.display_name));
    li.append(head, el("p", "kudos-message", k.message), timeEl(k.created_at));
    return li;
  }

  function show(node, text) {
    if (text !== undefined) node.textContent = text;
    node.hidden = false;
  }
  function hide(node) { node.hidden = true; }

  window.Kudos = { api, el, kudosCard, timeEl, show, hide };
})();
