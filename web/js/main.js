/**
 * Application entry point and state controller for the Lunar Landing Site Navigator.
 */

import {
  loadDataPack,
  loadRegionImage,
  getRegionCenterPoint,
  getTimeRangeBounds,
  getTimeWindow,
  formatUtc,
} from "./data.js";
import {
  DURATION_OPTIONS,
  METRIC_DEFINITIONS,
  EARTH_VISIBILITY_NOTE,
  evaluateSite,
  getColorMapTimeWindow,
  computeRegionIlluminationLazy,
} from "./metrics.js";
import { createPanoramaRenderer } from "./panorama.js";
import { createSitePicker, createTimelineStrip } from "./charts.js";
import {
  COMPARISON_TRADEOFF_NOTE,
  createComparisonStore,
  makeCompareKey,
  renderComparisonTable,
} from "./compare.js";

function byId(id) {
  return document.getElementById(id);
}

async function init() {
  const els = {
    loadingBanner: byId("loading-banner"),
    loadingText: byId("loading-text"),
    loadingBar: byId("loading-bar"),
    errorBanner: byId("error-banner"),
    errorMessage: byId("error-message"),
    appShell: byId("app-shell"),

    regionSelect: byId("region-select"),
    heightGroup: byId("height-toggle-group"),
    startDateInput: byId("start-date-input"),
    durationSelect: byId("duration-select"),
    dateRangeHint: byId("date-range-hint"),

    siteMapCanvas: byId("site-map-canvas"),
    siteMapTooltip: byId("site-map-tooltip"),
    siteMapStatus: byId("site-map-status"),
    siteMapProgress: byId("site-map-progress"),
    siteMapProgressTrack: byId("site-map-progress-track"),
    siteMapProgressBar: byId("site-map-progress-bar"),
    resetCenterBtn: byId("reset-center-btn"),

    siteIdValue: byId("site-id-value"),
    siteLatLonValue: byId("site-latlon-value"),
    siteHeightValue: byId("site-height-value"),
    siteSlopeValue: byId("site-slope-value"),
    siteHorizonValue: byId("site-horizon-value"),

    panoramaCanvas: byId("panorama-canvas"),
    panoCaption: byId("pano-caption"),
    viewButtons: Array.from(document.querySelectorAll("[data-pano-view]")),

    timeSlider: byId("time-slider"),
    timeDisplay: byId("time-display"),
    playBtn: byId("play-btn"),
    stepPrevBtn: byId("step-prev-btn"),
    stepNextBtn: byId("step-next-btn"),

    nowTime: byId("now-time"),
    nowSunPct: byId("now-sun-pct"),
    nowSunMeta: byId("now-sun-meta"),
    nowEarthPct: byId("now-earth-pct"),
    nowEarthMeta: byId("now-earth-meta"),

    metricsGrid: byId("metrics-grid"),
    earthNote: byId("earth-note"),

    sunStripCanvas: byId("sun-strip-canvas"),
    earthStripCanvas: byId("earth-strip-canvas"),

    addCompareBtn: byId("add-compare-btn"),
    clearCompareBtn: byId("clear-compare-btn"),
    compareTradeoffNote: byId("compare-tradeoff-note"),
    compareContainer: byId("compare-container"),
  };

  els.earthNote.textContent = EARTH_VISIBILITY_NOTE;
  els.compareTradeoffNote.textContent = COMPARISON_TRADEOFF_NOTE;

  // Build metric card skeletons once so updates only swap text values
  const metricValueEls = new Map();
  const metricSubEls = new Map();
  for (const def of METRIC_DEFINITIONS) {
    const card = document.createElement("article");
    card.className = `metric-card metric-${def.accent}`;

    const title = document.createElement("h3");
    title.className = "metric-label";
    title.textContent = def.label;

    const val = document.createElement("div");
    val.className = "metric-value";
    val.textContent = "—";

    const sub = document.createElement("div");
    sub.className = "metric-sub";
    sub.textContent = "";

    const help = document.createElement("p");
    help.className = "metric-help";
    help.textContent = def.help;

    card.append(title, val, sub, help);
    els.metricsGrid.appendChild(card);
    metricValueEls.set(def.key, val);
    metricSubEls.set(def.key, sub);
  }

  let dataPack;
  try {
    dataPack = await loadDataPack("data", (p) => {
      els.loadingText.textContent = p.message;
      els.loadingBar.style.width = `${Math.round(p.fraction * 100)}%`;
    });
  } catch (err) {
    els.loadingBanner.hidden = true;
    els.errorBanner.hidden = false;
    els.errorMessage.textContent = err.message || String(err);
    return;
  }

  const { manifest, ephem, horizons } = dataPack;
  els.loadingBanner.hidden = true;
  els.appShell.hidden = false;

  const state = {
    regionId: manifest.regions[0].id,
    point: getRegionCenterPoint(manifest, manifest.regions[0].id),
    heightIdx: 0,
    startDate: manifest.ephemeris.start_utc.slice(0, 10),
    days: 30,
    tIdx: 0,
    panoViewMode: "full",
    playing: false,
    playTimer: null,
    evaluation: null,
    timeWindow: null,
    regionImage: null,
    illuminationMap: null,
  };

  const illuminationCache = new Map();
  let cancelLazyCompute = null;
  const compareStore = createComparisonStore();

  // Populate region dropdown dynamically from manifest
  for (const reg of manifest.regions) {
    const opt = document.createElement("option");
    opt.value = reg.id;
    opt.textContent = reg.name;
    els.regionSelect.appendChild(opt);
  }
  els.regionSelect.value = state.regionId;

  // Populate observer height radio toggles dynamically from manifest
  manifest.observer_heights_m.forEach((h, idx) => {
    const label = document.createElement("label");
    label.className = "seg-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "observer-height";
    input.value = String(idx);
    input.checked = idx === state.heightIdx;
    const span = document.createElement("span");
    span.textContent = `${h} m`;
    label.append(input, span);
    els.heightGroup.appendChild(label);

    input.addEventListener("change", () => {
      if (input.checked) {
        state.heightIdx = idx;
        recomputeSiteAndGrid();
      }
    });
  });

  // Populate duration dropdown (filtered to available ephemeris span)
  const { maxDaysAvailable } = getTimeRangeBounds(manifest, 1);
  for (const d of DURATION_OPTIONS) {
    const opt = document.createElement("option");
    opt.value = String(d);
    opt.textContent = d === 365 ? "365 days (1 year)" : `${d} days`;
    if (d > maxDaysAvailable) {
      opt.disabled = true;
    }
    els.durationSelect.appendChild(opt);
  }
  if (state.days > maxDaysAvailable) {
    state.days = DURATION_OPTIONS.find((d) => d <= maxDaysAvailable) || 7;
  }
  els.durationSelect.value = String(state.days);

  const panorama = createPanoramaRenderer(els.panoramaCanvas);

  const sitePicker = createSitePicker({
    canvas: els.siteMapCanvas,
    tooltipEl: els.siteMapTooltip,
    onSelectPoint: (pt) => {
      state.point = pt;
      evaluateCurrentSite();
    },
  });

  const sunStrip = createTimelineStrip({
    canvas: els.sunStripCanvas,
    colorVar: "--sun-color",
    fallbackColor: "#fb923c",
    showHalfLine: false,
    onScrub: (idx) => setTimeIndex(idx),
  });

  const earthStrip = createTimelineStrip({
    canvas: els.earthStripCanvas,
    colorVar: "--earth-color",
    fallbackColor: "#38bdf8",
    showHalfLine: true,
    onScrub: (idx) => setTimeIndex(idx),
  });

  function syncDateBounds() {
    const bounds = getTimeRangeBounds(manifest, state.days);
    els.startDateInput.min = bounds.minDateStr;
    els.startDateInput.max = bounds.maxDateStr;

    if (state.startDate < bounds.minDateStr) {
      state.startDate = bounds.minDateStr;
    } else if (state.startDate > bounds.maxDateStr) {
      state.startDate = bounds.maxDateStr;
    }
    els.startDateInput.value = state.startDate;
    els.dateRangeHint.textContent = `Available: ${bounds.minDateStr} to ${bounds.maxDateStr}`;
  }

  function updateTimeUI() {
    if (!state.evaluation || !state.timeWindow) return;
    const { azel, summary } = state.evaluation;
    const { sv, ev } = summary;
    const nSteps = azel.nSteps;
    const idx = Math.max(0, Math.min(nSteps - 1, state.tIdx));
    state.tIdx = idx;

    els.timeSlider.max = String(Math.max(0, nSteps - 1));
    els.timeSlider.value = String(idx);

    const tsMs = state.timeWindow.startMs + idx * state.timeWindow.stepS * 1000.0;
    const utcStr = formatUtc(tsMs);
    els.timeDisplay.textContent = utcStr;
    els.nowTime.textContent = utcStr;

    const sunPct = sv[idx] * 100.0;
    const earthPct = ev[idx] * 100.0;
    els.nowSunPct.textContent = `${sunPct.toFixed(1)}%`;
    els.nowSunMeta.textContent = `Az ${azel.sunAz[idx].toFixed(1)}° · El ${azel.sunEl[idx].toFixed(2)}° · r ${azel.sunR[idx].toFixed(2)}°`;
    els.nowEarthPct.textContent = `${earthPct.toFixed(1)}%`;
    els.nowEarthMeta.textContent = `Az ${azel.earthAz[idx].toFixed(1)}° · El ${azel.earthEl[idx].toFixed(2)}° · r ${azel.earthR[idx].toFixed(2)}°`;

    panorama.render({
      hor: state.evaluation.hor,
      azel,
      sv,
      ev,
      tIdx: idx,
      viewMode: state.panoViewMode,
      azStepDeg: manifest.azStepDeg,
    });

    sunStrip.update({
      values: sv,
      startMs: state.timeWindow.startMs,
      stepS: state.timeWindow.stepS,
      tIdx: idx,
    });

    earthStrip.update({
      values: ev,
      startMs: state.timeWindow.startMs,
      stepS: state.timeWindow.stepS,
      tIdx: idx,
    });
  }

  function setTimeIndex(idx) {
    if (!state.evaluation) return;
    const maxIdx = state.evaluation.azel.nSteps - 1;
    state.tIdx = Math.max(0, Math.min(maxIdx, idx));
    updateTimeUI();
  }

  function updateSiteReadout() {
    const pt = state.point;
    const summary = state.evaluation?.summary;
    const isCenter = pt.id.endsWith("-c");
    els.siteIdValue.textContent = isCenter ? `${pt.id} (region centre)` : pt.id;
    els.siteLatLonValue.textContent = `${pt.lat.toFixed(4)}°, ${pt.lon.toFixed(4)}°`;
    els.siteHeightValue.textContent = `${pt.ground_height_m.toFixed(1)} m`;
    els.siteSlopeValue.textContent = `${pt.slope_deg.toFixed(1)}°`;
    els.siteHorizonValue.textContent = summary
      ? `${summary.horizon_min.toFixed(1)}° to ${summary.horizon_max.toFixed(1)}°`
      : "—";
  }

  function updateMetricCards() {
    const summary = state.evaluation?.summary;
    if (!summary) return;
    for (const def of METRIC_DEFINITIONS) {
      const val = summary[def.key];
      metricValueEls.get(def.key).textContent = def.format(val);
      metricSubEls.get(def.key).textContent = def.subFormat(val);
    }
  }

  function refreshCompareControls() {
    if (!state.point || !state.timeWindow) return;
    const observerHeightM = manifest.observer_heights_m[state.heightIdx];
    const key = makeCompareKey({
      pointId: state.point.id,
      observerHeightM,
      startDate: state.timeWindow.startDateStr,
      days: state.days,
    });
    const entries = compareStore.getEntries();
    if (compareStore.has(key)) {
      els.addCompareBtn.disabled = true;
      els.addCompareBtn.textContent = "Already in comparison";
    } else if (compareStore.isFull()) {
      els.addCompareBtn.disabled = true;
      els.addCompareBtn.textContent = "Comparison full (max 3)";
    } else {
      els.addCompareBtn.disabled = false;
      els.addCompareBtn.textContent = "Add to comparison";
    }
    els.clearCompareBtn.disabled = entries.length === 0;
  }

  function renderComparison() {
    renderComparisonTable(els.compareContainer, compareStore.getEntries(), {
      onRemove: (key) => {
        compareStore.remove(key);
        renderComparison();
        refreshCompareControls();
      },
    });
    refreshCompareControls();
  }

  function evaluateCurrentSite() {
    const observerHeightM = manifest.observer_heights_m[state.heightIdx];
    state.timeWindow = getTimeWindow(manifest, state.startDate, state.days);
    state.evaluation = evaluateSite({
      point: state.point,
      heightIdx: state.heightIdx,
      observerHeightM,
      timeWindow: state.timeWindow,
      manifest,
      ephem,
      horizons,
    });

    if (state.tIdx >= state.evaluation.azel.nSteps) {
      state.tIdx = 0;
    }

    updateSiteReadout();
    updateMetricCards();
    updateTimeUI();
    refreshCompareControls();

    const region = manifest.regionsById.get(state.regionId);
    const regionPoints = manifest.pointsByRegion.get(state.regionId) || [];
    sitePicker.update({
      region,
      image: state.regionImage,
      points: regionPoints,
      selectedPoint: state.point,
      illuminationMap: state.illuminationMap,
      gridSpacingM: manifest.grid_spacing_m,
    });
  }

  function cancelPendingColorMap() {
    if (cancelLazyCompute) {
      cancelLazyCompute();
      cancelLazyCompute = null;
    }
  }

  function startLazyRegionIllumination() {
    cancelPendingColorMap();
    const region = manifest.regionsById.get(state.regionId);
    const regionPoints = manifest.pointsByRegion.get(state.regionId) || [];
    const observerHeightM = manifest.observer_heights_m[state.heightIdx];
    state.timeWindow = getTimeWindow(manifest, state.startDate, state.days);
    const mapTimeWindow = getColorMapTimeWindow(manifest, state.startDate, state.days);
    const mapDays = Math.min(state.days, 90);
    state.illuminationMap = null;

    els.siteMapProgress.hidden = false;
    els.siteMapProgressBar.style.width = "0%";
    els.siteMapProgressTrack.setAttribute("aria-valuenow", "0");
    els.siteMapStatus.textContent = `Computing colour map: 0/${regionPoints.length} sites (0%)…`;

    cancelLazyCompute = computeRegionIlluminationLazy({
      regionId: state.regionId,
      regionPoints,
      heightIdx: state.heightIdx,
      observerHeightM,
      timeWindow: mapTimeWindow,
      manifest,
      ephem,
      horizons,
      cache: illuminationCache,
      onBatch: (partialMap, doneCount, totalCount) => {
        state.illuminationMap = partialMap;
        const pct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 100;
        els.siteMapProgressBar.style.width = `${pct}%`;
        els.siteMapProgressTrack.setAttribute("aria-valuenow", String(pct));
        els.siteMapStatus.textContent = `Computing colour map: ${doneCount}/${totalCount} sites (${pct}%)…`;
        sitePicker.update({
          region,
          image: state.regionImage,
          points: regionPoints,
          selectedPoint: state.point,
          illuminationMap: partialMap,
          gridSpacingM: manifest.grid_spacing_m,
        });
      },
      onDone: (fullMap) => {
        cancelLazyCompute = null;
        state.illuminationMap = fullMap;
        els.siteMapProgressBar.style.width = "100%";
        els.siteMapProgressTrack.setAttribute("aria-valuenow", "100");
        els.siteMapProgress.hidden = true;
        els.siteMapStatus.textContent =
          `${regionPoints.length} sites · ${manifest.grid_spacing_m} m grid · ${region.radius_km} km radius (map: ${mapDays}d @ ${mapTimeWindow.stepS}s)`;
        sitePicker.update({
          region,
          image: state.regionImage,
          points: regionPoints,
          selectedPoint: state.point,
          illuminationMap: fullMap,
          gridSpacingM: manifest.grid_spacing_m,
        });
      },
    });
  }

  function recomputeSiteAndGrid() {
    cancelPendingColorMap();
    state.illuminationMap = null;
    syncDateBounds();
    evaluateCurrentSite();
    startLazyRegionIllumination();
  }

  async function selectRegion(regionId) {
    cancelPendingColorMap();
    state.regionId = regionId;
    state.point = getRegionCenterPoint(manifest, regionId);
    state.regionImage = null;

    const region = manifest.regionsById.get(regionId);
    recomputeSiteAndGrid();

    try {
      const img = await loadRegionImage(region.image, "data");
      if (state.regionId === regionId) {
        state.regionImage = img;
        sitePicker.update({ image: img });
      }
    } catch (err) {
      els.siteMapStatus.textContent = err.message;
    }
  }

  // Control event listeners
  els.regionSelect.addEventListener("change", () => {
    selectRegion(els.regionSelect.value);
  });

  els.startDateInput.addEventListener("change", () => {
    if (els.startDateInput.value) {
      state.startDate = els.startDateInput.value;
      recomputeSiteAndGrid();
    }
  });

  els.durationSelect.addEventListener("change", () => {
    state.days = Number(els.durationSelect.value);
    recomputeSiteAndGrid();
  });

  els.resetCenterBtn.addEventListener("click", () => {
    state.point = getRegionCenterPoint(manifest, state.regionId);
    evaluateCurrentSite();
  });

  const FULL_PANO_CAPTION =
    "Azimuth 0 deg = away from the pole (outward), clockwise. Discs drawn at true vertical size; use Zoom for true shape.";
  const ZOOM_PANO_CAPTION =
    "Azimuth 0 deg = away from the pole (outward), clockwise. Equal 1:1 angular scale (±10°).";

  els.viewButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.panoViewMode = btn.dataset.panoView;
      els.viewButtons.forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      if (els.panoCaption) {
        els.panoCaption.textContent =
          state.panoViewMode === "full" ? FULL_PANO_CAPTION : ZOOM_PANO_CAPTION;
      }
      updateTimeUI();
    });
  });

  els.timeSlider.addEventListener("input", () => {
    stopPlayback();
    setTimeIndex(Number(els.timeSlider.value));
  });

  function stopPlayback() {
    state.playing = false;
    if (state.playTimer !== null) {
      clearInterval(state.playTimer);
      state.playTimer = null;
    }
    els.playBtn.textContent = "Play";
    els.playBtn.setAttribute("aria-pressed", "false");
  }

  els.playBtn.addEventListener("click", () => {
    if (state.playing) {
      stopPlayback();
      return;
    }
    state.playing = true;
    els.playBtn.textContent = "Pause";
    els.playBtn.setAttribute("aria-pressed", "true");
    state.playTimer = setInterval(() => {
      if (!state.evaluation) return;
      const nSteps = state.evaluation.azel.nSteps;
      // Advance proportionally so 365d plays at reasonable speed while 7-30d moves 1-2 steps
      const stepDelta = Math.max(1, Math.round(nSteps / 360));
      setTimeIndex((state.tIdx + stepDelta) % nSteps);
    }, 60);
  });

  els.stepPrevBtn.addEventListener("click", () => {
    stopPlayback();
    setTimeIndex(state.tIdx - 1);
  });

  els.stepNextBtn.addEventListener("click", () => {
    stopPlayback();
    setTimeIndex(state.tIdx + 1);
  });

  els.addCompareBtn.addEventListener("click", () => {
    if (!state.evaluation || !state.timeWindow) return;
    const observerHeightM = manifest.observer_heights_m[state.heightIdx];
    const region = manifest.regionsById.get(state.regionId);
    const key = makeCompareKey({
      pointId: state.point.id,
      observerHeightM,
      startDate: state.timeWindow.startDateStr,
      days: state.days,
    });
    compareStore.add({
      key,
      point: state.point,
      regionName: region.name,
      observerHeightM,
      startDate: state.timeWindow.startDateStr,
      days: state.days,
      summary: state.evaluation.summary,
    });
    renderComparison();
  });

  els.clearCompareBtn.addEventListener("click", () => {
    compareStore.clear();
    renderComparison();
  });

  // Re-render canvases cleanly on resize and OS theme switches
  const resizeObserver = new ResizeObserver(() => {
    if (state.evaluation) {
      updateTimeUI();
      sitePicker.render();
    }
  });
  resizeObserver.observe(els.panoramaCanvas);
  resizeObserver.observe(els.siteMapCanvas);

  const themeQuery = window.matchMedia("(prefers-color-scheme: light)");
  if (themeQuery.addEventListener) {
    themeQuery.addEventListener("change", () => {
      if (state.evaluation) {
        updateTimeUI();
        sitePicker.render();
      }
    });
  }

  // Initial load
  renderComparison();
  await selectRegion(state.regionId);
}

init();
