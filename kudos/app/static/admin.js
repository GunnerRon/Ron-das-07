(function () {
  "use strict";
  const { api, el, kudosCard, timeEl, show, hide } = window.Kudos;

  const list = document.getElementById("admin-list");
  const empty = document.getElementById("admin-empty");
  const more = document.getElementById("admin-more");
  const banner = document.getElementById("admin-banner");
  const tabs = document.querySelectorAll(".tab");
  let status = "all";
  let page = 0;

  function notify(text, isError) {
    banner.classList.toggle("banner-error", !!isError);
    banner.classList.toggle("banner-ok", !isError);
    show(banner, text);
  }

  function row(k) {
    const li = kudosCard(k);
    li.classList.add("admin-row", "status-" + k.status);
    const meta = el("div", "admin-meta");
    meta.append(el("span", "badge badge-" + k.status, k.status));
    if (k.moderated_by) {
      meta.append(el("span", "muted",
        ` by ${k.moderated_by.display_name}${k.moderation_reason ? ` — “${k.moderation_reason}”` : ""}`));
    }
    li.append(meta);

    if (k.history.length) {
      const details = el("details", "history");
      details.append(el("summary", null, `History (${k.history.length})`));
      const ul = el("ul");
      for (const h of k.history) {
        const item = el("li", null, `${h.action} by ${h.admin.display_name}${h.reason ? `: ${h.reason}` : ""} · `);
        item.append(timeEl(h.created_at));
        ul.append(item);
      }
      details.append(ul);
      li.append(details);
    }

    if (k.status !== "deleted") {
      const actions = el("div", "actions");
      if (k.status === "visible") actions.append(button("Hide", "secondary", () => act(k, "hide", li)));
      else actions.append(button("Unhide", "secondary", () => act(k, "unhide", li)));
      actions.append(button("Delete", "danger", () => act(k, "delete", li)));
      li.append(actions);
    }
    return li;
  }

  function button(label, cls, onClick) {
    const b = el("button", cls, label);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  async function act(k, action, li) {
    let reason = "";
    if (action !== "unhide") {
      const label = action === "delete"
        ? "Reason for permanently deleting this kudos (3-255 characters):"
        : "Reason for hiding this kudos (3-255 characters):";
      reason = window.prompt(label);
      if (reason === null) return;
    }
    li.querySelectorAll("button").forEach(b => { b.disabled = true; });
    try {
      const path = action === "delete" ? `/api/admin/kudos/${k.id}` : `/api/admin/kudos/${k.id}/${action}`;
      const data = await api(path, { method: action === "delete" ? "DELETE" : "POST", body: { reason } });
      const matches = status === "all" || data.kudos.status === status;
      if (matches) li.replaceWith(row(data.kudos)); else li.remove();
      empty.hidden = list.children.length > 0;
      const pastTense = { hide: "hidden", unhide: "restored", delete: "deleted" };
      notify(`Kudos #${k.id} ${pastTense[action]}.`);
    } catch (err) {
      li.querySelectorAll("button").forEach(b => { b.disabled = false; });
      notify(err.message, true);
    }
  }

  async function load(reset) {
    if (reset) { page = 0; list.replaceChildren(); }
    more.disabled = true;
    try {
      const data = await api(`/api/admin/kudos?status=${status}&page=${page + 1}`);
      page = data.page;
      data.kudos.forEach(k => list.append(row(k)));
      empty.hidden = list.children.length > 0;
      more.hidden = !data.has_more;
    } catch (err) {
      notify(err.message, true);
    } finally {
      more.disabled = false;
    }
  }

  tabs.forEach(tab => tab.addEventListener("click", () => {
    tabs.forEach(t => t.setAttribute("aria-selected", String(t === tab)));
    status = tab.dataset.status;
    hide(banner);
    load(true);
  }));
  more.addEventListener("click", () => load(false));
  load(true);
})();
