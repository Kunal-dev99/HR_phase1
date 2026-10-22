/* Sales Nav List Exporter — content script
 *
 * Runs inside your own logged-in Sales Navigator session.
 * It only reads the people ALREADY rendered in the search-results list
 * (the same data LinkedIn is showing you on screen) and never opens
 * individual profiles. That "list mode" is the low-detection path.
 *
 * State lives on window.__SN_EXPORTER__ so it survives Sales Navigator's
 * in-app (SPA) page turns. The popup talks to this script via messages.
 */
(function () {
  const SN = (window.__SN_EXPORTER__ = window.__SN_EXPORTER__ || {});
  // Reset state when the script version changes (keeps things clean after an update).
  if (SN.v !== 2) {
    SN.v = 2;
    SN.running = false;
    SN.stopRequested = false;
    SN.pages = 0;
    SN.map = new Map(); // key -> row; we keep the FULLEST copy we ever see
    SN.status = "idle";
    SN.lastError = "";
    SN.consultant = "";
    SN.resolvePublic = false;
  }

  // ---- helpers -------------------------------------------------------------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
  const clean = (el) => (el ? el.textContent.replace(/\s+/g, " ").trim() : "");

  // ---- enrichment derived locally from what the row already shows ----------
  // These run on data already on screen — no extra requests, no profile visits.

  // City / Country parsed from the Location line.
  // "Swindon, England, United Kingdom" -> {city:"Swindon", country:"United Kingdom"}
  // Region words (England/Scotland/Wales/NI) normalise to United Kingdom and are
  // never treated as a city. A bare country -> country only, city blank.
  // Never guess a city from a country.
  const REGIONS = new Set(["england", "scotland", "wales", "northern ireland"]);
  const CMAP = {
    uk: "United Kingdom", "u.k.": "United Kingdom", "united kingdom": "United Kingdom",
    england: "United Kingdom", scotland: "United Kingdom", wales: "United Kingdom",
    "northern ireland": "United Kingdom",
    usa: "United States", us: "United States", "u.s.": "United States",
    "u.s.a.": "United States", "united states of america": "United States",
    "united states": "United States",
    uae: "United Arab Emirates", "u.a.e.": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates"
  };
  const KNOWN_COUNTRIES = new Set([
    "united kingdom", "united states", "ireland", "canada", "australia",
    "new zealand", "singapore", "japan", "south korea", "saudi arabia",
    "united arab emirates", "qatar", "kuwait", "bahrain", "oman", "germany",
    "france", "spain", "italy", "netherlands", "belgium", "switzerland",
    "austria", "sweden", "norway", "denmark", "finland", "poland", "portugal",
    "ireland", "luxembourg", "india", "pakistan", "bangladesh", "philippines",
    "uk", "usa", "us", "uae"
  ]);
  const normCountry = (s) => CMAP[s.toLowerCase()] || s;
  const tidyCity = (c) =>
    c.replace(/^greater\s+/i, "").replace(/\s+area$/i, "").trim();

  function parseLoc(location) {
    if (!location) return { city: "", country: "" };
    const s = location.split("(")[0].trim(); // drop "(works for ...)" trailers
    const parts = s.split(",").map((x) => x.trim()).filter(Boolean);
    if (parts.length >= 2) {
      let country = normCountry(parts[parts.length - 1]);
      let city = REGIONS.has(parts[0].toLowerCase()) ? "" : tidyCity(parts[0]);
      return { city, country };
    }
    if (parts.length === 1) {
      const p = parts[0];
      if (KNOWN_COUNTRIES.has(p.toLowerCase())) return { city: "", country: normCountry(p) };
      if (/area$/i.test(p)) return { city: tidyCity(p), country: "" }; // "Greater Reading Area"
      return { city: "", country: "" }; // ambiguous single token — don't guess
    }
    return { city: "", country: "" };
  }

  // Job Classification (corporate view), priority order:
  // Architect -> Influencer ; C-suite -> Signatory ; Consultant/Analyst -> Can help
  // identify stakeholders ; Director/Head/VP/Manager/Lead/Owner -> Decision Maker ;
  // working-level -> Can help identify stakeholders ; else -> Can help identify stakeholders.
  // Job Classification — Anil's rule. Six checks IN ORDER; first match wins.
  // Whole-word matching so "cto" in "director" / "manager" in "programmer" don't fire.
  //   1. architect                          -> Influencer (always wins)
  //   2. director/VP/GM/C-suite             -> Signatory  (signs, doesn't decide)
  //   3. head of / head / manager / owner /
  //      product lead / delivery lead       -> Decision Maker (owns the decision)
  //   4. analyst                            -> Can help identify stakeholders (always)
  //   5. functional / techno-functional /
  //      sme / expert / principal / lead    -> Influencer (senior IC, shapes it)
  //   6. everything else                    -> Can help identify stakeholders
  function classifyJob(title) {
    const s = (title || "").toLowerCase();
    if (!s.trim()) return "Can help identify stakeholders";
    if (s.includes("architect")) return "Influencer";
    if (/\b(director|vice president|vp|general manager|managing director|chief|cfo|cio|cto|ceo|coo|chro|cdo|cmo)\b/.test(s))
      return "Signatory";
    if (/\bhead\b/.test(s) || s.includes("head of") || /\bmanager\b/.test(s) ||
        /\bowner\b/.test(s) || s.includes("product lead") || s.includes("delivery lead"))
      return "Decision Maker";
    if (/\banalyst\b/.test(s)) return "Can help identify stakeholders";
    if (/\bfunctional\b/.test(s) || s.includes("techno-functional") || s.includes("techno functional") ||
        /\bsme\b/.test(s) || /\bexpert\b/.test(s) || /\bprincipal\b/.test(s) || /\b(lead|leader)\b/.test(s))
      return "Influencer";
    return "Can help identify stakeholders";
  }

  // Department / function from the title (blank if not clear — never guessed).
  function deptFromTitle(title) {
    const s = (title || "").toLowerCase();
    if (/(financ|epm|payable|receivable|treasury|controller|general ledger)/.test(s) && !/procure/.test(s)) return "Finance";
    if (/(procure|sourcing|purchasing)/.test(s)) return "Procurement";
    if (/(hcm|human capital|human resource|payroll|talent|workforce|\bhr\b)/.test(s)) return "HR";
    if (/(supply chain|\bscm\b|logistics|warehouse|inventory)/.test(s)) return "Supply Chain";
    if (/(\berp\b|ebs|e-business|integration|technical|systems|application|\bcloud\b|database|\bit\b|software|developer|architect|digital|infrastructure)/.test(s)) return "IT";
    if (/(project|\bppm\b|programme|program)/.test(s)) return "Projects";
    return "";
  }

  // Seniority band from the title (informational; classification is separate).
  function seniorityFromTitle(title) {
    const s = (title || "").toLowerCase();
    if (/\b(chief|cfo|cio|cto|ceo|coo|chro|cdo|cmo)\b/.test(s)) return "C-Suite";
    if (/\b(director|vice president|vp|general manager|managing director)\b/.test(s)) return "Director/VP";
    if (/\bhead\b/.test(s) || s.includes("head of")) return "Head";
    if (/\bmanager\b/.test(s)) return "Manager";
    if (/\bprincipal\b/.test(s)) return "Principal";
    if (/\b(lead|leader)\b/.test(s)) return "Lead";
    if (/(senior|\bsnr\b|\bsr\b)/.test(s)) return "Senior";
    if (/(analyst|consultant|engineer|developer|specialist|coordinator|officer|sme|functional|executive)/.test(s)) return "Mid";
    return "";
  }

  // Sales Navigator tags every piece of PII with data-anonymize="...".
  // These attributes are far more stable than its scrambled class names.
  function findRows() {
    const names = Array.from(
      document.querySelectorAll('[data-anonymize="person-name"]')
    );
    const rows = [];
    const used = new Set();
    for (const n of names) {
      const li = n.closest("li");
      if (li && !used.has(li)) {
        used.add(li);
        rows.push(li);
      }
    }
    return rows;
  }

  // Turn a raw Sales Nav href into a portable one by dropping the per-session
  // search token: /sales/lead/<ID>,NAME_SEARCH,<track>  ->  /sales/lead/<ID>
  function cleanSalesUrl(href) {
    if (!href) return "";
    if (href.startsWith("/")) href = "https://www.linkedin.com" + href;
    href = href.split("?")[0].split("#")[0];
    const m = href.match(/\/sales\/(lead|people)\/([^,\/?#]+)/);
    return m ? `https://www.linkedin.com/sales/${m[1]}/${m[2]}` : href;
  }

  function salesNavUrl(li) {
    const a = li.querySelector(
      'a[href*="/sales/lead/"], a[href*="/sales/people/"]'
    );
    return a ? cleanSalesUrl(a.getAttribute("href") || "") : "";
  }

  // A public /in/ link is rarely in the row in list mode, but grab it if present.
  function publicUrlInRow(li) {
    const a = li.querySelector('a[href*="/in/"]');
    if (!a) return "";
    let h = a.getAttribute("href") || "";
    if (h.startsWith("/")) h = "https://www.linkedin.com" + h;
    return h.split("?")[0].split("#")[0];
  }

  // OPTIONAL / experimental: do Anil's "three dots -> View profile" automatically
  // to read the public /in/ URL (no session token). One menu open per lead, so
  // it's slower and higher-detection — only runs when the toggle is on.
  async function resolvePublicUrl(li) {
    const trig = li.querySelector(
      'button.artdeco-dropdown__trigger, button[aria-label*="Open" i], button[aria-label*="action" i], button[aria-label*="overflow" i], button[aria-label*="More" i]'
    );
    if (!trig) return "";
    try {
      trig.click();
      await sleep(rand(300, 600));
      const a =
        document.querySelector('.artdeco-dropdown__content--is-open a[href*="/in/"]') ||
        document.querySelector('div[role="menu"] a[href*="/in/"]') ||
        li.querySelector('a[href*="/in/"]');
      let url = "";
      if (a) {
        let h = a.getAttribute("href") || "";
        if (h.startsWith("/")) h = "https://www.linkedin.com" + h;
        url = h.split("?")[0].split("#")[0];
      }
      trig.click(); // close
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
      );
      await sleep(rand(150, 300));
      return url;
    } catch (e) {
      return "";
    }
  }

  async function resolvePublicForVisible() {
    for (const li of findRows()) {
      if (SN.stopRequested) return;
      const key = salesNavUrl(li);
      if (!key) continue;
      const entry = SN.map.get(key);
      if (!entry || (entry.url && /\/in\//.test(entry.url))) continue;
      const pub = await resolvePublicUrl(li);
      if (pub) entry.url = pub;
      await sleep(rand(120, 280));
    }
  }

  // harvest + (optional) public-URL resolution in one pass
  async function sweep() {
    harvest();
    if (SN.resolvePublic) await resolvePublicForVisible();
  }

  // Connection degree relative to the logged-in (crawling) account.
  // Targets the degree BADGE specifically, so a title like "1st Line Support
  // Analyst" or "3rd party logistics" can't masquerade as a connection degree.
  // Captures 1st / 2nd / 3rd (3rd+ is normalised to 3rd). Blank if none shown.
  function degree(li) {
    const norm = (d) => (d ? d.replace("+", "") : "");
    // 1) A dedicated badge whose ENTIRE trimmed text is the degree.
    const exact = Array.from(li.querySelectorAll("span, div"))
      .map((e) => (e.textContent || "").trim())
      .find((t) => /^(1st|2nd|3rd)(\+)?$/.test(t));
    if (exact) return norm(exact.match(/^(1st|2nd|3rd)(\+)?$/)[0]);
    // 2) Explicit "Nth degree" / "Nth degree connection" phrasing.
    const m1 = li.textContent.match(/\b(1st|2nd|3rd)\+?\s+degree\b/i);
    if (m1) return norm(m1[1]);
    // 3) Badge sitting just after a separator dot/bar: "· 2nd", "• 3rd+", "| 1st".
    const m2 = li.textContent.match(/[·•|]\s*(1st|2nd|3rd)\+?\b/);
    if (m2) return norm(m2[1]);
    return "";
  }

  // Best-effort: pull the "About:" preview text Sales Nav shows under a result.
  // Reads the row's combined text and slices the About blurb out of it, stopping
  // before the mutual-connections / shared-groups / "Show more" trailers.
  function aboutSnippet(li) {
    const t = li.textContent.replace(/\s+/g, " ").trim();
    const m = t.match(
      /About[:\s]+(.+?)(?:\s*Show more|\s*Show less|\s*\d+\s*mutual|\s*Shared group|\s*Follows your|\s*\d+\s*recent post|$)/i
    );
    let a = m ? m[1].trim() : "";
    if (a.length > 500) a = a.slice(0, 500).trim() + "\u2026";
    return a;
  }

  function extract(li) {
    const name = clean(li.querySelector('[data-anonymize="person-name"]'));
    const parts = name.split(" ");
    const firstName = parts.shift() || "";
    const lastName = parts.join(" ");
    const headline = clean(li.querySelector('[data-anonymize="headline"]'));
    const title = clean(li.querySelector('[data-anonymize="title"]')) || headline;
    const location = clean(li.querySelector('[data-anonymize="location"]'));
    const { city, country } = parseLoc(location);
    return {
      firstName,
      lastName,
      name,
      headline,
      title,
      company: clean(li.querySelector('[data-anonymize="company-name"]')),
      location,
      city,
      country,
      seniority: seniorityFromTitle(title),
      jobClass: classifyJob(title),
      department: deptFromTitle(title),
      degree: degree(li),
      about: aboutSnippet(li),
      salesUrl: salesNavUrl(li),
      url: publicUrlInRow(li) || salesNavUrl(li)
    };
  }

  // How "complete" a row is — used so a later, fully-loaded read of a person
  // replaces an earlier half-loaded one instead of being thrown away.
  function score(r) {
    return [
      r.name,
      r.headline,
      r.title,
      r.company,
      r.location,
      r.about,
      r.url
    ].filter(Boolean).length;
  }

  function harvest() {
    for (const li of findRows()) {
      const r = extract(li);
      if (!r.name) continue; // skip skeleton / not-yet-loaded rows (the "blank" ones)
      r.consultant = SN.consultant || "";
      const key = r.salesUrl || r.url || r.name + "|" + r.company;
      const prev = SN.map.get(key);
      if (!prev || score(r) >= score(prev)) SN.map.set(key, r);
    }
  }

  // Wait until the list is actually populated (not skeleton placeholders)
  // before we start reading — otherwise we capture empty rows.
  async function waitForResults(timeout = 15000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      if (SN.stopRequested) return false;
      const populated = Array.from(
        document.querySelectorAll('[data-anonymize="person-name"]')
      ).some((n) => n.textContent.trim().length > 0);
      if (populated) {
        await sleep(rand(500, 900)); // small settle so neighbouring fields fill in
        return true;
      }
      await sleep(300);
    }
    return false;
  }

  // The results list scrolls inside its own container, NOT the window.
  function getScroller() {
    const anchor = document.querySelector('[data-anonymize="person-name"]');
    let el = anchor ? anchor.parentElement : null;
    while (el && el !== document.body) {
      const oy = getComputedStyle(el).overflowY;
      if (
        (oy === "auto" || oy === "scroll" || oy === "overlay") &&
        el.scrollHeight > el.clientHeight + 40
      ) {
        return el;
      }
      el = el.parentElement;
    }
    const se = document.scrollingElement || document.documentElement;
    if (se && se.scrollHeight > se.clientHeight + 40) return se;
    return null; // signals: scroll the window
  }

  // Scroll gently from top to bottom in small steps (like a human / LinkedHelper),
  // pausing for lazy rows to render, and harvesting at every step so nothing is
  // missed even when Sales Nav recycles off-screen rows.
  async function scrollAndHarvest() {
    await waitForResults();
    const sc = getScroller();
    const win = sc === null;

    const top = () => (win ? window.scrollY : sc.scrollTop);
    const full = () =>
      win
        ? (document.scrollingElement || document.documentElement).scrollHeight
        : sc.scrollHeight;
    const view = () => (win ? window.innerHeight : sc.clientHeight);
    const go = (y) => (win ? window.scrollTo(0, y) : (sc.scrollTop = y));

    go(0);
    await sleep(rand(350, 600));
    await sweep();

    let lastSize = SN.map.size;
    let stable = 0;
    for (let i = 0; i < 160 && !SN.stopRequested; i++) {
      const before = top();
      // small, natural step — a little over half a viewport, with jitter
      const step = Math.max(260, view() * 0.55) + rand(-40, 60);
      go(top() + step);
      await sleep(rand(550, 1000)); // human-paced; lets lazy rows load
      await sweep();

      const atBottom = top() + view() >= full() - 8;
      const moved = top() > before + 2;

      if (SN.map.size === lastSize) stable++;
      else {
        stable = 0;
        lastSize = SN.map.size;
      }

      if (atBottom && stable >= 3) break; // at the end and nothing new appearing
      if (!moved && stable >= 4) break; // can't scroll any further
    }

    // settle at the bottom and sweep once more for the final lazy batch
    await sleep(rand(500, 900));
    await sweep();
    go(0);
    await sleep(rand(250, 450));
  }

  function nextButton() {
    return document.querySelector(
      'button.artdeco-pagination__button--next, button[aria-label="Next"]'
    );
  }

  async function run(opts) {
    if (SN.running) return;
    SN.running = true;
    SN.stopRequested = false;
    SN.status = "running";
    SN.lastError = "";
    SN.consultant = (opts.consultant || "").trim();
    SN.resolvePublic = !!opts.resolvePublic;

    const maxPages = opts.maxPages && opts.maxPages > 0 ? opts.maxPages : Infinity; // no limit
    const minDelay = opts.minDelay ?? 4000;
    const maxDelay = opts.maxDelay ?? 8000;

    try {
      const ready = await waitForResults();
      if (!ready) {
        SN.lastError =
          "No results loaded. Open a Sales Navigator people search and let it finish loading.";
        SN.status = "error";
        SN.running = false;
        return;
      }

      while (!SN.stopRequested && SN.pages < maxPages) {
        await scrollAndHarvest();
        SN.pages++;

        const next = nextButton();
        const done =
          !next ||
          next.disabled ||
          next.getAttribute("aria-disabled") === "true";
        if (done) break;

        await sleep(rand(minDelay, maxDelay)); // human-paced pause between pages
        if (SN.stopRequested) break;
        next.click();
        await waitForResults(); // wait for the NEW page to actually populate
      }
      SN.status = SN.stopRequested ? "stopped" : "done";
    } catch (e) {
      SN.lastError = String(e && e.message ? e.message : e);
      SN.status = "error";
    } finally {
      SN.running = false;
    }
  }

  function toCSV() {
    // First 15 columns = the Oracle project's Tab 1 header, in order.
    // Sector and Oracle Product are intentionally BLANK — they require web
    // research, which the Oracle project does (the extractor never guesses them).
    // The trailing helper columns (Full Name, Headline, About, Sales Nav URL)
    // are kept so the project can verify Oracle and so the cookie URL stays as a
    // stable merge key after the public-URL resolver pass.
    const headers = [
      "First Name",
      "Last Name",
      "LinkedIn URL",
      "Company",
      "Seniority",
      "Job Title",
      "Job Classification",
      "Location",
      "City",
      "Country",
      "Department",
      "Sector",
      "Source: Consultant Name",
      "Oracle Product",
      "Degree of Connection",
      "Full Name",
      "Headline",
      "About",
      "Sales Nav URL"
    ];
    const esc = (v) =>
      '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
    const lines = [headers.map(esc).join(",")];
    for (const r of SN.map.values()) {
      lines.push(
        [
          r.firstName,
          r.lastName,
          r.url, // LinkedIn URL: public if visible, else cookie Sales Nav URL
          r.company,
          r.seniority,
          r.title,
          r.jobClass,
          r.location,
          r.city,
          r.country,
          r.department,
          "", // Sector — filled by the Oracle project (web-verified)
          r.consultant,
          "", // Oracle Product — filled by the Oracle project (verified)
          r.degree,
          r.name, // Full Name (helper, used by Tab 2)
          r.headline,
          r.about,
          r.salesUrl || "" // stable merge key for the resolver pass
        ]
          .map(esc)
          .join(",")
      );
    }
    return lines.join("\r\n");
  }

  function download() {
    const csv = "\uFEFF" + toCSV(); // BOM so Excel reads UTF-8 correctly
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    a.href = url;
    a.download = `sales-nav-connections-${stamp}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    return SN.map.size;
  }

  // ---- message bridge to the popup ----------------------------------------
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    switch (msg && msg.action) {
      case "start":
        run(msg);
        sendResponse({ ok: true });
        break;
      case "stop":
        SN.stopRequested = true;
        sendResponse({ ok: true });
        break;
      case "status":
        sendResponse({
          running: SN.running,
          pages: SN.pages,
          count: SN.map.size,
          status: SN.status,
          lastError: SN.lastError
        });
        break;
      case "download":
        sendResponse({ ok: true, count: download() });
        break;
      case "reset":
        SN.map = new Map();
        SN.pages = 0;
        SN.status = "idle";
        SN.lastError = "";
        sendResponse({ ok: true });
        break;
      default:
        sendResponse({ ok: false });
    }
    return true; // keep the channel open for async responses
  });
})();
