(function () {
  "use strict";
  const { api, kudosCard, show, hide } = window.Kudos;

  const form = document.getElementById("kudos-form");
  const search = document.getElementById("recipient-search");
  const select = document.getElementById("recipient");
  const message = document.getElementById("message");
  const counter = document.getElementById("message-counter");
  const submit = document.getElementById("submit");
  const banner = document.getElementById("form-banner");
  const errors = { recipient_id: document.getElementById("recipient-error"),
                   message: document.getElementById("message-error") };
  const inputs = { recipient_id: select, message: message };

  const feed = document.getElementById("feed");
  const feedEmpty = document.getElementById("feed-empty");
  const feedError = document.getElementById("feed-error");
  const loadMore = document.getElementById("load-more");
  const maxLen = parseInt(counter.dataset.max, 10);
  let page = 0;
  let colleagues = [];

  // --- Recipient picker (US-1)
  function renderOptions(filter) {
    const q = (filter || "").trim().toLowerCase();
    const current = select.value;
    select.replaceChildren();
    const matches = colleagues.filter(u =>
      !q || u.display_name.toLowerCase().includes(q) || u.department.toLowerCase().includes(q));
    const placeholder = new Option(matches.length ? "Select a colleague…" : "No colleagues match", "");
    select.add(placeholder);
    for (const u of matches) {
      select.add(new Option(u.department ? `${u.display_name} — ${u.department}` : u.display_name, String(u.id)));
    }
    if (matches.some(u => String(u.id) === current)) select.value = current;
    else if (matches.length === 1) select.value = String(matches[0].id);
  }

  async function loadColleagues() {
    try {
      colleagues = (await api("/api/users")).users;
      renderOptions("");
    } catch (e) {
      select.replaceChildren(new Option("Couldn't load colleagues", ""));
      show(banner, e.message);
    }
  }
  search.addEventListener("input", () => renderOptions(search.value));

  // --- Character counter (AC-2.2)
  function updateCounter() {
    const left = maxLen - message.value.length;
    counter.textContent = `${left} character${left === 1 ? "" : "s"} left`;
    counter.classList.toggle("warn", left < 50);
  }
  message.addEventListener("input", updateCounter);

  // --- Errors
  function clearErrors() {
    hide(banner);
    for (const key in errors) {
      hide(errors[key]);
      inputs[key].removeAttribute("aria-invalid");
    }
  }
  function showErrors(err) {
    show(banner, err.message);
    for (const [key, msg] of Object.entries(err.fields || {})) {
      if (errors[key]) {
        show(errors[key], msg);
        inputs[key].setAttribute("aria-invalid", "true");
      }
    }
  }

  // --- Submit (US-3)
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearErrors();
    const fields = {};
    if (!select.value) fields.recipient_id = "Please choose a colleague.";
    if (!message.value.trim()) fields.message = "Please write a message.";
    if (Object.keys(fields).length) {
      showErrors({ message: "Please fix the highlighted fields.", fields });
      return;
    }
    submit.disabled = true;
    submit.textContent = "Sending…";
    try {
      const data = await api("/api/kudos", { method: "POST",
        body: { recipient_id: parseInt(select.value, 10), message: message.value } });
      feed.prepend(kudosCard(data.kudos));
      hide(feedEmpty);
      form.reset();
      search.value = "";
      renderOptions("");
      updateCounter();
    } catch (err) {
      showErrors(err);
    } finally {
      submit.disabled = false;
      submit.textContent = "Send kudos";
    }
  });

  // --- Feed (US-4)
  async function loadFeed() {
    loadMore.disabled = true;
    hide(feedError);
    try {
      const data = await api(`/api/kudos?page=${page + 1}`);
      page = data.page;
      const seen = new Set([...feed.children].map(li => li.dataset.id));
      for (const k of data.kudos) if (!seen.has(String(k.id))) feed.append(kudosCard(k));
      feedEmpty.hidden = feed.children.length > 0;
      loadMore.hidden = !data.has_more;
    } catch (e) {
      show(feedError, e.message);
    } finally {
      loadMore.disabled = false;
    }
  }
  loadMore.addEventListener("click", loadFeed);

  updateCounter();
  loadColleagues();
  loadFeed();
})();
