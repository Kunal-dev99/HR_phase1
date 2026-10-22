const $ = (id) => document.getElementById(id);

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function onSalesNav(tab) {
  return tab && /https:\/\/www\.linkedin\.com\/sales\//.test(tab.url || "");
}

// Make sure content.js is live in the tab (handles the case where the page
// was already open before the extension was installed/refreshed).
async function ensureInjected(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { action: "status" });
  } catch (e) {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"]
    });
  }
}

async function send(action, extra = {}) {
  const tab = await activeTab();
  if (!onSalesNav(tab)) {
    throw new Error("Open a Sales Navigator search page first.");
  }
  await ensureInjected(tab.id);
  return await chrome.tabs.sendMessage(tab.id, { action, ...extra });
}

function setStatus(text, kind) {
  $("statusText").textContent = text;
  const dot = $("dot");
  dot.className = "dot" + (kind ? " " + kind : "");
}

function render(s) {
  if (!s) return;
  $("count").textContent = s.count ?? 0;
  $("pages").textContent = s.pages ?? 0;

  const startBtn = $("start");
  const stopBtn = $("stop");
  startBtn.disabled = !!s.running;
  stopBtn.disabled = !s.running;

  if (s.running) {
    setStatus(`Scanning… page ${s.pages} · ${s.count} profiles`, "run");
  } else if (s.status === "done") {
    setStatus(`Done. ${s.count} profiles ready to download.`, "done");
  } else if (s.status === "stopped") {
    setStatus(`Stopped. ${s.count} collected — download anytime.`, "done");
  } else if (s.status === "error") {
    setStatus(s.lastError || "Something went wrong.", "err");
  } else {
    setStatus("Idle — open a search and press Start.", "");
  }
}

async function poll() {
  try {
    const tab = await activeTab();
    if (!onSalesNav(tab)) {
      setStatus("Not on Sales Navigator. Open a people search.", "err");
      $("start").disabled = true;
      return;
    }
    $("start").disabled = false;
    const s = await chrome.tabs.sendMessage(tab.id, { action: "status" });
    render(s);
  } catch (e) {
    // content script not injected yet — that's fine, it injects on Start
  }
}

$("start").addEventListener("click", async () => {
  try {
    let maxPages = parseInt($("maxPages").value, 10);
    if (isNaN(maxPages) || maxPages < 0) maxPages = 0; // 0 = all pages, no limit
    const minDelay = (parseFloat($("minDelay").value) || 4) * 1000;
    let maxDelay = (parseFloat($("maxDelay").value) || 8) * 1000;
    if (maxDelay < minDelay) maxDelay = minDelay + 1000;
    const consultant = $("consultant").value.trim();
    const resolvePublic = $("resolvePublic").checked;
    await send("start", { maxPages, minDelay, maxDelay, consultant, resolvePublic });
    setStatus("Starting…", "run");
  } catch (e) {
    setStatus(e.message, "err");
  }
});

$("stop").addEventListener("click", async () => {
  try {
    await send("stop");
  } catch (e) {
    setStatus(e.message, "err");
  }
});

$("download").addEventListener("click", async () => {
  try {
    const r = await send("download");
    if (r && r.count === 0) setStatus("Nothing collected yet.", "err");
  } catch (e) {
    setStatus(e.message, "err");
  }
});

$("reset").addEventListener("click", async () => {
  try {
    await send("reset");
    poll();
  } catch (e) {
    setStatus(e.message, "err");
  }
});

poll();
setInterval(poll, 1000);
