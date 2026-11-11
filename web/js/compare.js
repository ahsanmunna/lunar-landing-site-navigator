/**
 * Side-by-side site comparison manager & table renderer (max 3 entries).
 * Deliberately omits any overall score or "best" ranking label.
 */

import { METRIC_DEFINITIONS } from "./metrics.js";

export const MAX_COMPARE_ENTRIES = 3;

export const COMPARISON_TRADEOFF_NOTE =
  "Which site is better depends on mission needs: power, communications and terrain safety trade off.";

/**
 * Create a unique key for (site + observer height + date range).
 */
export function makeCompareKey({ pointId, observerHeightM, startDate, days }) {
  return `${pointId}|${observerHeightM}|${startDate}|${days}`;
}

/**
 * Pure state manager for up to 3 pinned comparison configurations.
 */
export function createComparisonStore() {
  let entries = [];

  return {
    getEntries() {
      return entries.slice();
    },
    has(key) {
      return entries.some((e) => e.key === key);
    },
    isFull() {
      return entries.length >= MAX_COMPARE_ENTRIES;
    },
    add(entry) {
      if (entries.some((e) => e.key === entry.key)) {
        return { ok: false, reason: "already-added" };
      }
      if (entries.length >= MAX_COMPARE_ENTRIES) {
        return { ok: false, reason: "full" };
      }
      entries.push(entry);
      return { ok: true };
    },
    remove(key) {
      entries = entries.filter((e) => e.key !== key);
    },
    clear() {
      entries = [];
    },
  };
}

/**
 * Compute normalized 0..100% inline bar width for a metric value across compared entries.
 */
function computeBarPct(def, value, allValues) {
  if (def.kind === "fraction") {
    return Math.max(0, Math.min(100, value * 100));
  }
  if (def.kind === "percent") {
    return Math.max(0, Math.min(100, value));
  }
  const maxVal = Math.max(1e-6, ...allValues);
  return Math.max(0, Math.min(100, (value / maxVal) * 100));
}

/**
 * Render the side-by-side comparison table into containerEl.
 */
export function renderComparisonTable(containerEl, entries, { onRemove }) {
  containerEl.textContent = "";

  if (entries.length === 0) {
    const empty = document.createElement("p");
    empty.className = "compare-empty";
    empty.textContent =
      'No configurations pinned yet. Select any site, height, and date window above, then click "Add to comparison" (up to 3).';
    containerEl.appendChild(empty);
    return;
  }

  const wrap = document.createElement("div");
  wrap.className = "table-scroll";

  const table = document.createElement("table");
  table.className = "compare-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");

  const cornerTh = document.createElement("th");
  cornerTh.scope = "col";
  cornerTh.textContent = "Metric";
  headRow.appendChild(cornerTh);

  for (const entry of entries) {
    const th = document.createElement("th");
    th.scope = "col";

    const headerWrap = document.createElement("div");
    headerWrap.className = "cmp-col-head";

    const title = document.createElement("strong");
    title.textContent = `${entry.regionName}`;

    const sub1 = document.createElement("span");
    sub1.className = "cmp-col-meta";
    sub1.textContent = `${entry.point.id} · ${entry.observerHeightM} m obs`;

    const sub2 = document.createElement("span");
    sub2.className = "cmp-col-meta";
    sub2.textContent = `${entry.startDate} (${entry.days} d)`;

    const sub3 = document.createElement("span");
    sub3.className = "cmp-col-meta";
    sub3.textContent = `Elev ${entry.point.ground_height_m.toFixed(0)} m · Slope ${entry.point.slope_deg.toFixed(1)}°`;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-ghost btn-xs";
    removeBtn.textContent = "Remove";
    removeBtn.setAttribute("aria-label", `Remove ${entry.point.id} from comparison`);
    removeBtn.addEventListener("click", () => onRemove(entry.key));

    headerWrap.append(title, sub1, sub2, sub3, removeBtn);
    th.appendChild(headerWrap);
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");

  for (const def of METRIC_DEFINITIONS) {
    const tr = document.createElement("tr");

    const labelTd = document.createElement("th");
    labelTd.scope = "row";
    const labelMain = document.createElement("div");
    labelMain.className = "cmp-metric-name";
    labelMain.textContent = def.label;
    const labelHelp = document.createElement("div");
    labelHelp.className = "cmp-metric-help";
    labelHelp.textContent = def.help;
    labelTd.append(labelMain, labelHelp);
    tr.appendChild(labelTd);

    const rowValues = entries.map((e) => e.summary[def.key]);

    entries.forEach((entry, idx) => {
      const td = document.createElement("td");
      const val = rowValues[idx];
      const barPct = computeBarPct(def, val, rowValues);

      const valDiv = document.createElement("div");
      valDiv.className = "cmp-val";
      valDiv.textContent = def.format(val);

      const barTrack = document.createElement("div");
      barTrack.className = "cmp-bar-track";
      const barFill = document.createElement("div");
      barFill.className = `cmp-bar-fill cmp-bar-${def.accent}`;
      barFill.style.width = `${barPct.toFixed(1)}%`;
      barTrack.appendChild(barFill);

      td.append(valDiv, barTrack);
      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  }

  table.appendChild(tbody);
  wrap.appendChild(table);
  containerEl.appendChild(wrap);
}
