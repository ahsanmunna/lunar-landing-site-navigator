/**
 * Canvas 2D Horizon Panorama Renderer.
 * Renders azimuth 0-360 deg (0 = outward-radial north, clockwise) vs elevation,
 * terrain silhouette, faint dotted Sun/Earth tracks, and Sun/Earth discs at true
 * angular elevation size visibly clipped by the terrain horizon.
 * Supports "full" (0-360 deg) and 1:1 equal-angle "zoom-sun" / "zoom-earth" modes.
 */

import { interpHorizon } from "./visibility.js";

/**
 * Read theme-aware canvas colours from CSS custom properties (dark by default,
 * switching cleanly via prefers-color-scheme: light).
 */
export function getCanvasPalette() {
  if (typeof window === "undefined" || !window.getComputedStyle) {
    return {
      skyTop: "#091022",
      skyBottom: "#111c33",
      grid: "rgba(148, 163, 184, 0.18)",
      zeroLine: "rgba(148, 163, 184, 0.42)",
      axisText: "#94a3b8",
      terrainFill: "#475569",
      terrainFillBottom: "#334155",
      terrainStroke: "#94a3b8",
      sun: "#fb923c",
      sunGlow: "rgba(251, 146, 60, 0.28)",
      sunTrack: "rgba(251, 146, 60, 0.65)",
      sunTrackHidden: "rgba(251, 146, 60, 0.20)",
      earth: "#38bdf8",
      earthGlow: "rgba(56, 189, 248, 0.25)",
      earthTrack: "rgba(56, 189, 248, 0.65)",
      earthTrackHidden: "rgba(56, 189, 248, 0.20)",
      cursor: "rgba(248, 250, 252, 0.55)",
      isLight: false,
    };
  }
  const styles = getComputedStyle(document.documentElement);
  const v = (name, fallback) => styles.getPropertyValue(name).trim() || fallback;
  return {
    skyTop: v("--pano-sky-top", "#091022"),
    skyBottom: v("--pano-sky-bottom", "#111c33"),
    grid: v("--pano-grid", "rgba(148, 163, 184, 0.18)"),
    zeroLine: v("--pano-zero", "rgba(148, 163, 184, 0.42)"),
    axisText: v("--text-muted", "#94a3b8"),
    terrainFill: v("--terrain-fill", "#4b5563"),
    terrainFillBottom: v("--terrain-bottom", "#334155"),
    terrainStroke: v("--terrain-stroke", "#94a3b8"),
    sun: v("--sun-color", "#fb923c"),
    sunGlow: v("--sun-glow", "rgba(251, 146, 60, 0.28)"),
    sunTrack: v("--sun-track", "rgba(251, 146, 60, 0.65)"),
    sunTrackHidden: v("--sun-track-hidden", "rgba(251, 146, 60, 0.20)"),
    earth: v("--earth-color", "#38bdf8"),
    earthGlow: v("--earth-glow", "rgba(56, 189, 248, 0.25)"),
    earthTrack: v("--earth-track", "rgba(56, 189, 248, 0.65)"),
    earthTrackHidden: v("--earth-track-hidden", "rgba(56, 189, 248, 0.20)"),
    cursor: v("--pano-cursor", "rgba(248, 250, 252, 0.55)"),
    isLight: window.matchMedia("(prefers-color-scheme: light)").matches,
  };
}

/**
 * Compute nice vertical axis bounds for the full 360-deg panorama.
 */
function computeElevationBounds(hor, azel) {
  let minVal = -2.0;
  let maxVal = 5.0;
  for (let i = 0; i < hor.length; i++) {
    if (hor[i] < minVal) minVal = hor[i];
    if (hor[i] > maxVal) maxVal = hor[i];
  }
  const n = azel.nSteps;
  for (let i = 0; i < n; i++) {
    const sLow = azel.sunEl[i] - azel.sunR[i];
    const sHigh = azel.sunEl[i] + azel.sunR[i];
    const eLow = azel.earthEl[i] - azel.earthR[i];
    const eHigh = azel.earthEl[i] + azel.earthR[i];
    if (sLow < minVal) minVal = sLow;
    if (eLow < minVal) minVal = eLow;
    if (sHigh > maxVal) maxVal = sHigh;
    if (eHigh > maxVal) maxVal = eHigh;
  }
  return {
    elMin: Math.floor(minVal - 1.0),
    elMax: Math.ceil(maxVal + 1.5),
  };
}

/**
 * Wrap azimuth delta to [-180, +180) degrees.
 */
function wrapDeltaAz(az, centerAz) {
  let d = ((az - centerAz + 540.0) % 360.0) - 180.0;
  return d;
}

const CARDINAL_LABELS = new Map([
  [0, "0° N"],
  [45, "45°"],
  [90, "90° E"],
  [135, "135°"],
  [180, "180° S"],
  [225, "225°"],
  [270, "270° W"],
  [315, "315°"],
  [360, "360° N"],
]);

/**
 * Build a stateful Canvas 2D Panorama renderer with offscreen caching for fast slider scrubbing.
 */
export function createPanoramaRenderer(canvas) {
  const offscreen = typeof document !== "undefined" ? document.createElement("canvas") : null;
  let cachedKey = null;
  let cachedBounds = null;

  function render({ hor, azel, sv, ev, tIdx, viewMode = "full", azStepDeg = 1.0 }) {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(300, Math.round(rect.width || canvas.clientWidth || 760));
    const height = Math.max(240, Math.round(rect.height || canvas.clientHeight || 340));
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }

    const ctx = canvas.getContext("2d");
    const pal = getCanvasPalette();

    const margin = {
      top: 16,
      right: 16,
      bottom: 34,
      left: width < 440 ? 40 : 48,
    };
    const plotW = Math.max(100, width - margin.left - margin.right);
    const plotH = Math.max(100, height - margin.top - margin.bottom);

    const isZoomed = viewMode === "zoom-sun" || viewMode === "zoom-earth";
    let azCenter = 180.0;
    let azSpan = 360.0;
    let elMin;
    let elMax;

    if (isZoomed) {
      azCenter = viewMode === "zoom-sun" ? azel.sunAz[tIdx] : azel.earthAz[tIdx];
      const bodyEl = viewMode === "zoom-sun" ? azel.sunEl[tIdx] : azel.earthEl[tIdx];
      const hzAtCenter = interpHorizon(hor, azCenter, azStepDeg);
      azSpan = 20.0; // +/- 10 deg horizontal window with 1:1 angular scale
      const pxPerDeg = plotW / azSpan;
      const elSpan = plotH / pxPerDeg;
      const elMid = (bodyEl + hzAtCenter) * 0.5;
      elMin = elMid - elSpan * 0.5;
      elMax = elMid + elSpan * 0.5;
    } else {
      const boundsKey = `${hor[0]}|${hor[90]}|${azel.nSteps}|${azel.sunEl[0]}|${azel.earthEl[0]}`;
      if (!cachedBounds || cachedBounds.key !== boundsKey) {
        const b = computeElevationBounds(hor, azel);
        cachedBounds = { key: boundsKey, ...b };
      }
      elMin = cachedBounds.elMin;
      elMax = cachedBounds.elMax;
    }

    const pxPerDegX = plotW / azSpan;
    const pxPerDegY = plotH / (elMax - elMin);

    const azToX = (az) => {
      if (!isZoomed) {
        return margin.left + (az / 360.0) * plotW;
      }
      return margin.left + ((wrapDeltaAz(az, azCenter) + azSpan * 0.5) / azSpan) * plotW;
    };
    const elToY = (el) => margin.top + ((elMax - el) / (elMax - elMin)) * plotH;

    // Static background layer caching (only used in full mode where axes/tracks don't shift with tIdx)
    const staticKey = !isZoomed
      ? `${width}x${height}x${dpr}|${pal.isLight}|${elMin}|${elMax}|${hor[0]}|${hor[90]}|${hor[180]}|${azel.nSteps}|${azel.sunAz[0]}|${azel.earthAz[0]}`
      : null;

    let targetCtx = ctx;
    let drawStatic = true;

    if (!isZoomed && offscreen) {
      if (offscreen.width !== canvas.width || offscreen.height !== canvas.height) {
        offscreen.width = canvas.width;
        offscreen.height = canvas.height;
      }
      if (cachedKey === staticKey) {
        drawStatic = false;
      } else {
        targetCtx = offscreen.getContext("2d");
      }
    }

    if (drawStatic) {
      targetCtx.save();
      targetCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      targetCtx.clearRect(0, 0, width, height);

      // Sky gradient inside plot box
      const skyGrad = targetCtx.createLinearGradient(0, margin.top, 0, margin.top + plotH);
      skyGrad.addColorStop(0, pal.skyTop);
      skyGrad.addColorStop(1, pal.skyBottom);
      targetCtx.fillStyle = skyGrad;
      targetCtx.fillRect(margin.left, margin.top, plotW, plotH);

      // Grid lines
      targetCtx.lineWidth = 1;
      targetCtx.font = "11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
      targetCtx.fillStyle = pal.axisText;

      // Elevation grid lines
      const elStep = elMax - elMin > 25 ? 5 : elMax - elMin > 10 ? 2 : 1;
      const firstEl = Math.ceil(elMin / elStep) * elStep;
      targetCtx.textAlign = "right";
      targetCtx.textBaseline = "middle";
      for (let el = firstEl; el <= elMax; el += elStep) {
        const y = Math.round(elToY(el)) + 0.5;
        if (y < margin.top || y > margin.top + plotH) continue;
        targetCtx.beginPath();
        if (Math.abs(el) < 1e-9) {
          targetCtx.strokeStyle = pal.zeroLine;
          targetCtx.setLineDash([4, 4]);
        } else {
          targetCtx.strokeStyle = pal.grid;
          targetCtx.setLineDash([]);
        }
        targetCtx.moveTo(margin.left, y);
        targetCtx.lineTo(margin.left + plotW, y);
        targetCtx.stroke();
        targetCtx.setLineDash([]);
        targetCtx.fillText(`${el}°`, margin.left - 6, y);
      }

      // Azimuth grid lines
      targetCtx.textAlign = "center";
      targetCtx.textBaseline = "top";
      if (!isZoomed) {
        const azStepTick = width < 520 ? 90 : 45;
        for (let az = 0; az <= 360; az += azStepTick) {
          const x = Math.round(azToX(az)) + 0.5;
          targetCtx.strokeStyle = pal.grid;
          targetCtx.beginPath();
          targetCtx.moveTo(x, margin.top);
          targetCtx.lineTo(x, margin.top + plotH);
          targetCtx.stroke();
          const lbl = CARDINAL_LABELS.get(az) || `${az}°`;
          targetCtx.fillText(lbl, x, margin.top + plotH + 7);
        }
      } else {
        const startRel = -Math.floor(azSpan * 0.5);
        const endRel = Math.ceil(azSpan * 0.5);
        const tickStep = 5;
        const firstTick = Math.ceil((azCenter + startRel) / tickStep) * tickStep;
        for (let az = firstTick; az <= azCenter + endRel; az += tickStep) {
          const azNorm = ((az % 360) + 360) % 360;
          const x = azToX(azNorm);
          if (x < margin.left || x > margin.left + plotW) continue;
          targetCtx.strokeStyle = pal.grid;
          targetCtx.beginPath();
          targetCtx.moveTo(x, margin.top);
          targetCtx.lineTo(x, margin.top + plotH);
          targetCtx.stroke();
          targetCtx.fillText(`${azNorm.toFixed(0)}°`, x, margin.top + plotH + 7);
        }
      }

      // Build sky clip and terrain silhouette path
      targetCtx.save();
      targetCtx.beginPath();
      targetCtx.rect(margin.left, margin.top, plotW, plotH);
      targetCtx.clip();

      const drawTrackDots = (azArr, elArr, color, radiusPx) => {
        targetCtx.fillStyle = color;
        const stride = Math.max(1, Math.ceil(azArr.length / 1400));
        for (let i = 0; i < azArr.length; i += stride) {
          const x = azToX(azArr[i]);
          const y = elToY(elArr[i]);
          if (x < margin.left - 4 || x > margin.left + plotW + 4) continue;
          if (y < margin.top - 4 || y > margin.top + plotH + 4) continue;
          targetCtx.beginPath();
          targetCtx.arc(x, y, radiusPx, 0, Math.PI * 2);
          targetCtx.fill();
        }
      };

      // Faint dotted tracks in sky
      drawTrackDots(azel.sunAz, azel.sunEl, pal.sunTrack, 1.35);
      drawTrackDots(azel.earthAz, azel.earthEl, pal.earthTrack, 1.35);

      // Terrain silhouette polygon
      const nSamples = isZoomed ? Math.max(120, Math.round(plotW / 2)) : hor.length;
      const terrainGrad = targetCtx.createLinearGradient(0, margin.top, 0, margin.top + plotH);
      terrainGrad.addColorStop(0, pal.terrainFill);
      terrainGrad.addColorStop(1, pal.terrainFillBottom);

      targetCtx.beginPath();
      targetCtx.moveTo(margin.left, margin.top + plotH + 2);
      for (let s = 0; s <= nSamples; s++) {
        let az;
        let x;
        if (!isZoomed) {
          az = (s / nSamples) * 360.0;
          x = margin.left + (s / nSamples) * plotW;
        } else {
          const rel = -azSpan * 0.5 + (s / nSamples) * azSpan;
          az = ((azCenter + rel) % 360 + 360) % 360;
          x = margin.left + (s / nSamples) * plotW;
        }
        const hz = interpHorizon(hor, az, azStepDeg);
        const y = elToY(hz);
        targetCtx.lineTo(x, y);
      }
      targetCtx.lineTo(margin.left + plotW, margin.top + plotH + 2);
      targetCtx.closePath();

      targetCtx.fillStyle = terrainGrad;
      targetCtx.fill();

      // Ridgeline top stroke
      targetCtx.beginPath();
      for (let s = 0; s <= nSamples; s++) {
        const az = !isZoomed
          ? (s / nSamples) * 360.0
          : ((azCenter - azSpan * 0.5 + (s / nSamples) * azSpan) % 360 + 360) % 360;
        const x = margin.left + (s / nSamples) * plotW;
        const y = elToY(interpHorizon(hor, az, azStepDeg));
        if (s === 0) targetCtx.moveTo(x, y);
        else targetCtx.lineTo(x, y);
      }
      targetCtx.strokeStyle = pal.terrainStroke;
      targetCtx.lineWidth = 1.6;
      targetCtx.stroke();

      // Faint behind-terrain guide dots so shadowed craters like Haworth still show track path
      drawTrackDots(azel.sunAz, azel.sunEl, pal.sunTrackHidden, 1.0);
      drawTrackDots(azel.earthAz, azel.earthEl, pal.earthTrackHidden, 1.0);

      targetCtx.restore(); // end plot clip

      // Plot border
      targetCtx.strokeStyle = pal.grid;
      targetCtx.lineWidth = 1;
      targetCtx.strokeRect(margin.left + 0.5, margin.top + 0.5, plotW - 1, plotH - 1);

      targetCtx.restore();

      if (!isZoomed && offscreen) {
        cachedKey = staticKey;
      }
    }

    // Blit cached static background onto main canvas when in full mode
    if (!isZoomed && offscreen) {
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(offscreen, 0, 0);
      ctx.restore();
    }

    // Draw dynamic Sun and Earth discs at selected time tIdx, clipped above the terrain horizon
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Clip to plot box first for ghost outlines, then clip to sky above horizon for solid discs
    ctx.beginPath();
    ctx.rect(margin.left, margin.top, plotW, plotH);
    ctx.clip();

    const sunAz = azel.sunAz[tIdx];
    const sunEl = azel.sunEl[tIdx];
    const sunRDeg = azel.sunR[tIdx];
    const earthAz = azel.earthAz[tIdx];
    const earthEl = azel.earthEl[tIdx];
    const earthRDeg = azel.earthR[tIdx];

    // Use true elevation radius vertically; in 1:1 zoomed mode rx === ry === rDeg * pxPerDeg,
    // and in full 360 mode draw circular discs at true vertical angular radius rDeg * pxPerDegY
    // so vertical horizon clipping matches visible_fraction() visually.
    const sunRadiusPx = Math.max(1.8, sunRDeg * pxPerDegY);
    const earthRadiusPx = Math.max(3.5, earthRDeg * pxPerDegY);

    const drawGhostOutline = (az, el, rPx, color) => {
      const offsets = !isZoomed ? [0, -360, 360] : [0];
      ctx.save();
      ctx.strokeStyle = color;
      ctx.globalAlpha = 0.32;
      ctx.lineWidth = 1.25;
      ctx.setLineDash([3, 3]);
      for (const off of offsets) {
        const cx = azToX(az + off);
        if (cx + rPx < margin.left || cx - rPx > margin.left + plotW) continue;
        const cy = elToY(el);
        ctx.beginPath();
        ctx.arc(cx, cy, rPx, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.restore();
    };

    if (sv[tIdx] < 1.0) drawGhostOutline(sunAz, sunEl, sunRadiusPx, pal.sun);
    if (ev[tIdx] < 1.0) drawGhostOutline(earthAz, earthEl, earthRadiusPx, pal.earth);

    // Sky clip polygon (area strictly above terrain horizon line)
    ctx.save();
    ctx.beginPath();
    const nClip = isZoomed ? Math.max(120, Math.round(plotW / 2)) : hor.length;
    ctx.moveTo(margin.left, margin.top);
    ctx.lineTo(margin.left + plotW, margin.top);
    for (let s = nClip; s >= 0; s--) {
      const az = !isZoomed
        ? (s / nClip) * 360.0
        : ((azCenter - azSpan * 0.5 + (s / nClip) * azSpan) % 360 + 360) % 360;
      const x = margin.left + (s / nClip) * plotW;
      const y = elToY(interpHorizon(hor, az, azStepDeg));
      ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.clip();

    const drawSolidDisc = (az, el, rPx, color, glowColor, label) => {
      const offsets = !isZoomed ? [0, -360, 360] : [0];
      for (const off of offsets) {
        const cx = azToX(az + off);
        if (cx + rPx + 12 < margin.left || cx - rPx - 12 > margin.left + plotW) continue;
        const cy = elToY(el);

        // Soft halo
        const glow = ctx.createRadialGradient(cx, cy, rPx * 0.5, cx, cy, rPx * 2.2);
        glow.addColorStop(0, glowColor);
        glow.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(cx, cy, rPx * 2.2, 0, Math.PI * 2);
        ctx.fill();

        // Crisp solid disc at true vertical angular radius
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(cx, cy, rPx, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = pal.isLight ? "rgba(15, 23, 42, 0.45)" : "rgba(255, 255, 255, 0.6)";
        ctx.lineWidth = 0.9;
        ctx.stroke();

        // Subtle label if main occurrence inside plot
        if (off === 0 && cx >= margin.left && cx <= margin.left + plotW) {
          ctx.font = "600 11px system-ui, -apple-system, sans-serif";
          ctx.fillStyle = color;
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(label, cx, Math.max(margin.top + 13, cy - rPx - 4));
        }
      }
    };

    // Draw Earth first then Sun (Sun is bright orange, Earth is blue)
    drawSolidDisc(earthAz, earthEl, earthRadiusPx, pal.earth, pal.earthGlow, "Earth");
    drawSolidDisc(sunAz, sunEl, sunRadiusPx, pal.sun, pal.sunGlow, "Sun");

    ctx.restore(); // end sky clip

    // Zoomed view scale annotation badge
    if (isZoomed) {
      ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
      ctx.fillStyle = pal.axisText;
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("1:1 true angular scale (±10°)", margin.left + 8, margin.top + 8);
    }

    ctx.restore();
  }

  return { render };
}
