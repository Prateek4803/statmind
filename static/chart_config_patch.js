/**
 * StatMind — Chart.js Global Config Patch
 * Drop this script block into index.html IMMEDIATELY AFTER the Chart.js
 * <script> tag and BEFORE any chart creation code.
 *
 * Fixes:
 *   A-01  Blurry charts on Retina/HiDPI displays (devicePixelRatio)
 *   A-02  Inconsistent font rendering across platforms
 *   A-03  Gridlines too thick (1px → 0.5px)
 *   A-11  Tooltip background invisible on dark theme
 */

(function patchChartDefaults() {
  if (typeof Chart === 'undefined') {
    console.warn('[StatMind] Chart.js not loaded — skipping defaults patch');
    return;
  }

  const DPR = window.devicePixelRatio || 1;

  /* ── Typography ──────────────────────────────────────────────────────── */
  const FONT_STACK = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif';

  Chart.defaults.font.family = FONT_STACK;
  Chart.defaults.font.size   = 11.5;
  Chart.defaults.font.weight = '400';
  Chart.defaults.font.lineHeight = 1.4;

  /* ── HiDPI — the single most impactful fix ───────────────────────────── */
  Chart.defaults.devicePixelRatio = DPR;

  /* ── Colours (dark theme) ────────────────────────────────────────────── */
  Chart.defaults.color       = 'rgba(139, 143, 168, 0.85)';   // --muted
  Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.055)';  // subtle grid

  /* ── Scale defaults ──────────────────────────────────────────────────── */
  const GRID = {
    color:     'rgba(255, 255, 255, 0.055)',
    lineWidth: 0.5,
    drawBorder: false,
  };
  const TICK = {
    color:   'rgba(139, 143, 168, 0.8)',
    font:    { family: FONT_STACK, size: 11 },
    padding: 6,
    maxRotation: 0,
  };
  Chart.defaults.scales = Chart.defaults.scales || {};

  /* linear (most common) */
  Chart.defaults.scales.linear = Chart.defaults.scales.linear || {};
  Object.assign(Chart.defaults.scales.linear, {
    grid: GRID,
    ticks: TICK,
    border: { display: false },
  });

  /* category */
  Chart.defaults.scales.category = Chart.defaults.scales.category || {};
  Object.assign(Chart.defaults.scales.category, {
    grid: GRID,
    ticks: TICK,
    border: { display: false },
  });

  /* ── Tooltip ──────────────────────────────────────────────────────────── */
  Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor:  'rgba(23, 26, 38, 0.97)',   // --bg3
    titleColor:       'rgba(232, 234, 240, 0.95)', // --text
    bodyColor:        'rgba(139, 143, 168, 0.9)',  // --muted
    borderColor:      'rgba(255, 255, 255, 0.12)', // --border2
    borderWidth:      1,
    padding:          10,
    cornerRadius:     8,
    titleFont:        { family: FONT_STACK, size: 12, weight: '600' },
    bodyFont:         { family: FONT_STACK, size: 11.5 },
    titleMarginBottom: 6,
    displayColors:    true,
    boxWidth:         8,
    boxHeight:        8,
    boxPadding:       3,
    usePointStyle:    true,
  });

  /* ── Legend ──────────────────────────────────────────────────────────── */
  Object.assign(Chart.defaults.plugins.legend, {
    display: true,
    labels: {
      color:       'rgba(139, 143, 168, 0.85)',
      font:        { family: FONT_STACK, size: 11.5 },
      boxWidth:    10,
      boxHeight:   10,
      usePointStyle: true,
      pointStyleWidth: 10,
      padding:     16,
    },
  });

  /* ── Element defaults ────────────────────────────────────────────────── */
  /* Lines */
  Object.assign(Chart.defaults.elements.line, {
    borderWidth: 1.5,
    tension:     0,      // crisp straight lines for SPC/time series
    fill:        false,
    spanGaps:    true,
  });

  /* Points */
  Object.assign(Chart.defaults.elements.point, {
    radius:           3,
    hoverRadius:      5,
    borderWidth:      1.5,
    hoverBorderWidth: 2,
    hitRadius:        8,
  });

  /* Bars */
  Object.assign(Chart.defaults.elements.bar, {
    borderWidth:  0,
    borderRadius: 3,
    borderSkipped: 'bottom',
  });

  /* ── Animation — faster feels more responsive ────────────────────────── */
  Chart.defaults.animation = {
    duration: 220,
    easing:   'easeOutQuart',
  };

  /* ── Responsive ───────────────────────────────────────────────────────── */
  Chart.defaults.responsive          = true;
  Chart.defaults.maintainAspectRatio = false;   // let containers control height

  /* ── SPC alarm point style override ─────────────────────────────────── */
  /*
   * Register a custom plugin that draws alarm annotations on SPC charts.
   * Usage: pass chart option  alarmIndices: [{index: N, rule: 'WE1', value: V}]
   * Draws an outer ring in red/amber around the alarmed point.
   */
  Chart.register({
    id: 'statmind-alarms',
    afterDatasetsDraw(chart) {
      const alarms = chart.options.alarmIndices;
      if (!alarms || !alarms.length) return;
      const ctx  = chart.ctx;
      const meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data) return;

      alarms.forEach(alarm => {
        const pt = meta.data[alarm.index];
        if (!pt) return;
        const { x, y } = pt.getProps(['x', 'y'], true);

        /* Outer ring */
        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, Math.PI * 2);
        ctx.strokeStyle = alarm.rule && alarm.rule.startsWith('WE1')
          ? 'rgba(239, 68, 68, 0.9)'   /* WE1 — hard red   */
          : 'rgba(245, 158, 11, 0.85)'; /* other — amber     */
        ctx.lineWidth   = 1.5 * DPR;
        ctx.stroke();
        ctx.restore();
      });
    },
  });

  console.info(`[StatMind] Chart.js patched — DPR ${DPR}x, font: ${FONT_STACK.split(',')[0]}`);
})();


/**
 * Utility: create a crisp Chart.js chart on a canvas element.
 * Handles HiDPI sizing and returns the Chart instance.
 *
 * Usage:
 *   const chart = createStatMindChart('myCanvasId', config);
 */
function createStatMindChart(canvasId, config) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) { console.warn('[StatMind] Canvas not found:', canvasId); return null; }

  /* Destroy any existing chart on this canvas */
  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  /* Ensure display dimensions are applied before reading getBoundingClientRect */
  canvas.style.display = canvas.style.display || 'block';

  return new Chart(canvas, config);
}


/**
 * StatMind colour palette for charts.
 * Use these instead of raw hex to keep charts consistent.
 */
const SM_COLORS = {
  /* Primary analysis line */
  data:           'rgba(99, 102, 241, 0.9)',   /* accent indigo */
  dataFill:       'rgba(99, 102, 241, 0.08)',

  /* Spec limits */
  usl:            'rgba(239, 68, 68, 0.75)',
  lsl:            'rgba(239, 68, 68, 0.75)',
  target:         'rgba(16, 185, 129, 0.65)',

  /* Control limits */
  ucl:            'rgba(245, 158, 11, 0.7)',
  lcl:            'rgba(245, 158, 11, 0.7)',
  cl:             'rgba(139, 143, 168, 0.5)',  /* centreline */

  /* Normal distribution curve */
  curveWithin:    'rgba(99, 102, 241, 0.85)',
  curveOverall:   'rgba(245, 158, 11, 0.75)',

  /* Histogram bars */
  histCapable:    'rgba(16, 185, 129, 0.55)',
  histMarginal:   'rgba(245, 158, 11, 0.55)',
  histNotCapable: 'rgba(239, 68, 68, 0.55)',

  /* Alarm points */
  alarmHard:      'rgba(239, 68, 68, 0.9)',
  alarmSoft:      'rgba(245, 158, 11, 0.85)',

  /* GRR */
  repeatability:  'rgba(99, 102, 241, 0.8)',
  reproducibility:'rgba(16, 185, 129, 0.7)',
  partTopart:     'rgba(245, 158, 11, 0.7)',
};
