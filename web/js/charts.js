/**
 * Canvas 2D charts:
 * 1. Site picker map (hillshade PNG + Viridis-coloured grid points + click/keyboard selection)
 * 2. Sun and Earth visible-fraction timeline strips tied interactively to the time slider
 */

import { formatUtc } from "./data.js";
import { VIRIDIS_LUT, viridisIndex } from "./metrics.js";
import { getCanvasPalette } from "./panorama.js";

/**
 * Interactive Site Picker canvas displaying regions/<id>.png with manifest extent
 * and grid points coloured by illumination_avg_fraction.
 */
export function createSitePicker({ canvas, tooltipEl, onSelectPoint }) {
  let state = {
    region: null,
    image: null,
    points: [],
    selectedPoint: null,
    illuminationMap: null,
    gridSpacingM: 500,
    hoverPoint: null,
  };

  // Pre-allocated colour buckets for fast chunked rendering of large regions (<= 256 fill paths)
  const bucketsX = Array.from({ length: 256 }, () => []);
  const bucketsY = Array.from({ length: 256 }, () => []);
  const activeBuckets = [];
  const strokedX = [];
  const strokedY = [];

  function getGeometry() {
    const rect = canvas.getBoundingClientRect();
    const size = Math.max(220, Math.round(rect.width || canvas.clientWidth || 320));
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    return { size, dpr };
  }

  function pointToCanvas(pt, region, size) {
    const ext = region.extent;
    const x = ((pt.x_m - ext.x_min) / (ext.x_max - ext.x_min)) * size;
    const y = ((ext.y_max - pt.y_m) / (ext.y_max - ext.y_min)) * size;
    return { x, y };
  }

  function findNearestPoint(clientX, clientY) {
    if (!state.region || state.points.length === 0) return null;
    const rect = canvas.getBoundingClientRect();
    const px = clientX - rect.left;
    const py = clientY - rect.top;
    const ext = state.region.extent;
    const targetX = ext.x_min + (px / rect.width) * (ext.x_max - ext.x_min);
    const targetY = ext.y_max - (py / rect.height) * (ext.y_max - ext.y_min);

    let best = null;
    let bestD2 = Infinity;
    for (const pt of state.points) {
      const dx = pt.x_m - targetX;
      const dy = pt.y_m - targetY;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD2) {
        bestD2 = d2;
        best = pt;
      }
    }
    return best;
  }

  function render() {
    if (!state.region) return;
    const { size, dpr } = getGeometry();
    const pxSize = Math.round(size * dpr);
    if (canvas.width !== pxSize || canvas.height !== pxSize) {
      canvas.width = pxSize;
      canvas.height = pxSize;
    }

    const ctx = canvas.getContext("2d");
    const pal = getCanvasPalette();
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);

    // 1. Background hillshade PNG matching extent
    if (state.image) {
      ctx.drawImage(state.image, 0, 0, size, size);
    } else {
      ctx.fillStyle = "#1e293b";
      ctx.fillRect(0, 0, size, size);
    }

    // 2. Subtle region boundary circle
    const ext = state.region.extent;
    const spanX = ext.x_max - ext.x_min;
    const centerPx = pointToCanvas(
      { x_m: state.region.center_x_m, y_m: state.region.center_y_m },
      state.region,
      size,
    );
    const radiusPx = ((state.region.radius_km * 1000.0) / spanX) * size;

    ctx.save();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.arc(centerPx.x, centerPx.y, radiusPx, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    // 3. Grid points coloured by illumination_avg_fraction
    const spacingPx = (state.gridSpacingM / spanX) * size;
    const dotRadius = Math.max(2.3, Math.min(7.0, spacingPx * 0.33));
    const xMin = ext.x_min;
    const yMax = ext.y_max;
    const scaleX = size / spanX;
    const scaleY = size / (yMax - ext.y_min);
    const twoPi = Math.PI * 2;
    const illumMap = state.illuminationMap;

    ctx.strokeStyle = "rgba(15, 23, 42, 0.72)";
    ctx.lineWidth = 1;

    // Batch all uncomputed points in a single path for fast chunked renders
    let hasUncomputed = false;
    ctx.beginPath();
    for (let i = 0; i < state.points.length; i++) {
      const pt = state.points[i];
      if (illumMap && illumMap.has(pt.id)) continue;
      const x = (pt.x_m - xMin) * scaleX;
      const y = (yMax - pt.y_m) * scaleY;
      ctx.moveTo(x + dotRadius, y);
      ctx.arc(x, y, dotRadius, 0, twoPi);
      hasUncomputed = true;
    }
    if (hasUncomputed) {
      ctx.fillStyle = "rgba(148, 163, 184, 0.55)";
      ctx.fill();
      ctx.stroke();
    }

    // Draw computed Viridis dots batched by LUT colour index + one combined stroke
    if (illumMap && illumMap.size > 0) {
      for (let b = 0; b < activeBuckets.length; b++) {
        const idx = activeBuckets[b];
        bucketsX[idx].length = 0;
        bucketsY[idx].length = 0;
      }
      activeBuckets.length = 0;
      strokedX.length = 0;
      strokedY.length = 0;

      for (let i = 0; i < state.points.length; i++) {
        const pt = state.points[i];
        const val = illumMap.get(pt.id);
        if (val === undefined) continue;
        const x = (pt.x_m - xMin) * scaleX;
        const y = (yMax - pt.y_m) * scaleY;
        const cIdx = viridisIndex(val);
        if (bucketsX[cIdx].length === 0) {
          activeBuckets.push(cIdx);
        }
        bucketsX[cIdx].push(x);
        bucketsY[cIdx].push(y);
        strokedX.push(x);
        strokedY.push(y);
      }

      for (let b = 0; b < activeBuckets.length; b++) {
        const cIdx = activeBuckets[b];
        const bx = bucketsX[cIdx];
        const by = bucketsY[cIdx];
        ctx.beginPath();
        for (let j = 0; j < bx.length; j++) {
          const x = bx[j];
          const y = by[j];
          ctx.moveTo(x + dotRadius, y);
          ctx.arc(x, y, dotRadius, 0, twoPi);
        }
        ctx.fillStyle = VIRIDIS_LUT[cIdx];
        ctx.fill();
      }

      if (strokedX.length > 0) {
        ctx.beginPath();
        for (let j = 0; j < strokedX.length; j++) {
          const x = strokedX[j];
          const y = strokedY[j];
          ctx.moveTo(x + dotRadius, y);
          ctx.arc(x, y, dotRadius, 0, twoPi);
        }
        ctx.stroke();
      }
    }

    // 4. Hovered point ring
    if (state.hoverPoint && state.hoverPoint.id !== state.selectedPoint?.id) {
      const { x, y } = pointToCanvas(state.hoverPoint, state.region, size);
      ctx.beginPath();
      ctx.arc(x, y, dotRadius + 3.5, 0, Math.PI * 2);
      ctx.strokeStyle = "#f8fafc";
      ctx.lineWidth = 1.6;
      ctx.stroke();
    }

    // 5. Selected point crosshair + double ring
    if (state.selectedPoint) {
      const { x, y } = pointToCanvas(state.selectedPoint, state.region, size);
      const ringR = dotRadius + 4.5;

      ctx.save();
      ctx.strokeStyle = "#0f172a";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.arc(x, y, ringR, 0, Math.PI * 2);
      ctx.stroke();

      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, ringR, 0, Math.PI * 2);
      ctx.stroke();

      // Short crosshair ticks
      ctx.beginPath();
      ctx.moveTo(x - ringR - 5, y);
      ctx.lineTo(x - ringR + 1, y);
      ctx.moveTo(x + ringR - 1, y);
      ctx.lineTo(x + ringR + 5, y);
      ctx.moveTo(x, y - ringR - 5);
      ctx.lineTo(x, y - ringR + 1);
      ctx.moveTo(x, y + ringR - 1);
      ctx.lineTo(x, y + ringR + 5);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.restore();
    }

    // 6. Scale bar + orientation badge (+y = near side / 0 lon up)
    const scaleKm = state.region.radius_km >= 4 ? 2 : 1;
    const barPx = ((scaleKm * 1000.0) / spanX) * size;
    const bx = 12;
    const by = size - 14;
    ctx.fillStyle = "rgba(15, 23, 42, 0.72)";
    ctx.fillRect(bx - 5, by - 18, barPx + 10, 24);
    ctx.strokeStyle = "#f8fafc";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(bx, by);
    ctx.lineTo(bx + barPx, by);
    ctx.stroke();
    ctx.fillStyle = "#f8fafc";
    ctx.font = "600 10px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    ctx.fillText(`${scaleKm} km`, bx, by - 3);

    // Subtle border
    ctx.strokeStyle = pal.grid;
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, size - 1, size - 1);

    ctx.restore();
  }

  function updateTooltip(pt, clientX, clientY) {
    if (!tooltipEl) return;
    if (!pt) {
      tooltipEl.hidden = true;
      return;
    }
    const illum = state.illuminationMap?.get(pt.id);
    const illumText = illum !== undefined ? `${(illum * 100).toFixed(1)}%` : "computing…";
    tooltipEl.textContent = `${pt.id} • Illum: ${illumText} • Elev: ${pt.ground_height_m.toFixed(0)} m • Slope: ${pt.slope_deg.toFixed(1)}°`;
    tooltipEl.hidden = false;

    const parentRect = canvas.parentElement.getBoundingClientRect();
    const x = Math.min(parentRect.width - 180, Math.max(8, clientX - parentRect.left + 10));
    const y = Math.max(8, clientY - parentRect.top - 28);
    tooltipEl.style.left = `${x}px`;
    tooltipEl.style.top = `${y}px`;
  }

  canvas.addEventListener("click", (e) => {
    const pt = findNearestPoint(e.clientX, e.clientY);
    if (pt && onSelectPoint) {
      onSelectPoint(pt);
    }
  });

  canvas.addEventListener("pointermove", (e) => {
    const pt = findNearestPoint(e.clientX, e.clientY);
    if (pt?.id !== state.hoverPoint?.id) {
      state.hoverPoint = pt;
      render();
    }
    updateTooltip(pt, e.clientX, e.clientY);
  });

  canvas.addEventListener("pointerleave", () => {
    state.hoverPoint = null;
    updateTooltip(null);
    render();
  });

  // Keyboard navigation across grid points (arrow keys move spatially; Home jumps to center)
  canvas.addEventListener("keydown", (e) => {
    if (!state.selectedPoint || state.points.length === 0) return;
    const dirs = {
      ArrowRight: [1, 0],
      ArrowLeft: [-1, 0],
      ArrowUp: [0, 1],
      ArrowDown: [0, -1],
    };
    if (e.key === "Home") {
      e.preventDefault();
      const centerPt = state.points.find((p) => p.id.endsWith("-c")) || state.points[0];
      if (centerPt && onSelectPoint) onSelectPoint(centerPt);
      return;
    }
    const vec = dirs[e.key];
    if (!vec) return;
    e.preventDefault();

    const cur = state.selectedPoint;
    let best = null;
    let bestScore = Infinity;
    for (const pt of state.points) {
      if (pt.id === cur.id) continue;
      const dx = pt.x_m - cur.x_m;
      const dy = pt.y_m - cur.y_m;
      const proj = dx * vec[0] + dy * vec[1];
      if (proj <= 50) continue; // must lie forward in pressed direction
      const perp = Math.abs(dx * -vec[1] + dy * vec[0]);
      if (perp > proj * 1.15) continue;
      const score = proj + perp * 2.5;
      if (score < bestScore) {
        bestScore = score;
        best = pt;
      }
    }
    if (best && onSelectPoint) {
      onSelectPoint(best);
    }
  });

  return {
    update(nextState) {
      state = { ...state, ...nextState };
      render();
    },
    render,
  };
}

/**
 * Interactive Timeline Strip for Sun or Earth visible fraction over the selected period.
 */
export function createTimelineStrip({ canvas, colorVar, fallbackColor, showHalfLine = false, onScrub }) {
  let state = {
    values: null,
    startMs: 0,
    stepS: 900,
    tIdx: 0,
  };
  let dragging = false;

  function clientXToIdx(clientX) {
    if (!state.values || state.values.length === 0) return 0;
    const rect = canvas.getBoundingClientRect();
    const padLeft = 36;
    const padRight = 10;
    const plotW = Math.max(40, rect.width - padLeft - padRight);
    const frac = Math.max(0, Math.min(1, (clientX - rect.left - padLeft) / plotW));
    return Math.round(frac * (state.values.length - 1));
  }

  function render() {
    if (!state.values || state.values.length === 0) return;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(260, Math.round(rect.width || canvas.clientWidth || 680));
    const height = Math.max(76, Math.round(rect.height || canvas.clientHeight || 86));
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }

    const ctx = canvas.getContext("2d");
    const pal = getCanvasPalette();
    const styles = typeof window !== "undefined" ? getComputedStyle(document.documentElement) : null;
    const seriesColor = (styles && styles.getPropertyValue(colorVar).trim()) || fallbackColor;

    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const pad = { top: 8, right: 10, bottom: 22, left: 36 };
    const plotW = Math.max(40, width - pad.left - pad.right);
    const plotH = Math.max(30, height - pad.top - pad.bottom);
    const n = state.values.length;

    // Background box
    ctx.fillStyle = pal.skyBottom;
    ctx.fillRect(pad.left, pad.top, plotW, plotH);

    // 50% and 100% guides
    ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.fillStyle = pal.axisText;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";

    for (const frac of [0, 0.5, 1]) {
      const y = Math.round(pad.top + (1 - frac) * plotH) + 0.5;
      ctx.beginPath();
      ctx.strokeStyle = frac === 0.5 && showHalfLine ? pal.zeroLine : pal.grid;
      if (frac === 0.5 && showHalfLine) ctx.setLineDash([3, 3]);
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + plotW, y);
      ctx.stroke();
      ctx.setLineDash([]);
      if (frac === 0 || frac === 1 || (frac === 0.5 && showHalfLine)) {
        ctx.fillText(`${Math.round(frac * 100)}%`, pad.left - 5, y);
      }
    }

    // Min-max envelope + mean fill per pixel column so short eclipses never disappear
    const cols = Math.max(1, Math.floor(plotW));
    const vals = state.values;
    ctx.fillStyle = seriesColor;

    for (let px = 0; px < cols; px++) {
      const iStart = Math.floor((px / cols) * n);
      const iEnd = Math.max(iStart + 1, Math.floor(((px + 1) / cols) * n));
      let minV = 1.0;
      let maxV = 0.0;
      let sumV = 0.0;
      for (let i = iStart; i < iEnd && i < n; i++) {
        const v = vals[i];
        if (v < minV) minV = v;
        if (v > maxV) maxV = v;
        sumV += v;
      }
      const x = pad.left + px;
      if (maxV > 0) {
        const meanV = sumV / (iEnd - iStart);
        // Solid fill up to minV (or meanV), translucent spike up to maxV
        ctx.globalAlpha = 0.35;
        const yMax = pad.top + (1 - maxV) * plotH;
        ctx.fillRect(x, yMax, 1, pad.top + plotH - yMax);

        ctx.globalAlpha = 0.85;
        const yMean = pad.top + (1 - (minV === maxV ? maxV : meanV)) * plotH;
        ctx.fillRect(x, yMean, 1, Math.max(1, pad.top + plotH - yMean));
      }
    }
    ctx.globalAlpha = 1.0;

    // Date ticks along bottom axis
    const tickCount = width < 440 ? 3 : 5;
    ctx.fillStyle = pal.axisText;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let t = 0; t <= tickCount; t++) {
      const frac = t / tickCount;
      const idx = Math.min(n - 1, Math.round(frac * (n - 1)));
      const x = pad.left + frac * plotW;
      const ms = state.startMs + idx * state.stepS * 1000.0;
      const label = formatUtc(ms, { compact: true }).slice(5, 10); // MM-DD
      if (t === 0) ctx.textAlign = "left";
      else if (t === tickCount) ctx.textAlign = "right";
      else ctx.textAlign = "center";
      ctx.fillText(label, x, pad.top + plotH + 5);
    }

    // Current slider cursor line
    const cursorFrac = n > 1 ? state.tIdx / (n - 1) : 0;
    const cx = pad.left + cursorFrac * plotW;
    const curVal = vals[Math.min(n - 1, Math.max(0, state.tIdx))];
    const cy = pad.top + (1 - curVal) * plotH;

    ctx.strokeStyle = pal.cursor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(cx, pad.top);
    ctx.lineTo(cx, pad.top + plotH);
    ctx.stroke();

    ctx.fillStyle = seriesColor;
    ctx.strokeStyle = pal.isLight ? "#0f172a" : "#ffffff";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Border
    ctx.strokeStyle = pal.grid;
    ctx.lineWidth = 1;
    ctx.strokeRect(pad.left + 0.5, pad.top + 0.5, plotW - 1, plotH - 1);

    ctx.restore();
  }

  canvas.addEventListener("pointerdown", (e) => {
    dragging = true;
    canvas.setPointerCapture(e.pointerId);
    if (onScrub) onScrub(clientXToIdx(e.clientX));
  });

  canvas.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    if (onScrub) onScrub(clientXToIdx(e.clientX));
  });

  canvas.addEventListener("pointerup", (e) => {
    dragging = false;
    if (canvas.hasPointerCapture(e.pointerId)) {
      canvas.releasePointerCapture(e.pointerId);
    }
  });

  return {
    update(nextState) {
      state = { ...state, ...nextState };
      render();
    },
    render,
  };
}
