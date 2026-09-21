(function () {
  const frame = document.getElementById("frame");
  const canvas = document.getElementById("lofi-canvas");
  const strip = document.getElementById("lofi-strip");
  if (!frame || !canvas || !strip) return;
  if (frame.dataset.lofi !== "1") return;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  // Retro Winamp-ish spectrum colors
  const LED = {
    green: "#39ff14",
    yellow: "#ffe600",
    orange: "#ff8c00",
    red: "#ff1a1a",
    dim: "rgba(40, 55, 40, 0.55)",
    grid: "rgba(80, 100, 60, 0.25)",
  };

  const STYLES = [
    "classicBars",
    "peakCaps",
    "ledMatrix",
    "scope",
    "vuMirror",
    "fireBars",
    "segmentLeds",
  ];
  const CYCLE_MS = 90000;
  let styleIndex = 0;
  let bands = new Array(10).fill(0);
  let smoothed = new Array(10).fill(0);
  let peaks = new Array(10).fill(0);
  let peakHold = new Array(10).fill(0);
  let es = null;
  let raf = 0;
  let t0 = performance.now();

  function resize() {
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const w = strip.clientWidth;
    const h = strip.clientHeight;
    if (w < 1 || h < 1) return;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function heatColor(v) {
    // Low→green, mid→yellow, hot→orange, peak→red
    if (v < 0.35) return LED.green;
    if (v < 0.55) return LED.yellow;
    if (v < 0.78) return LED.orange;
    return LED.red;
  }

  function heatGradient(x, y0, y1, v) {
    const g = ctx.createLinearGradient(x, y0, x, y1);
    g.addColorStop(0, heatColor(Math.max(v, 0.85)));
    g.addColorStop(0.35, LED.orange);
    g.addColorStop(0.65, LED.yellow);
    g.addColorStop(1, LED.green);
    return g;
  }

  function drawBackdrop(w, h) {
    ctx.fillStyle = "#0a1008";
    ctx.fillRect(0, 0, w, h);
    // subtle scanlines
    ctx.fillStyle = "rgba(0, 0, 0, 0.25)";
    for (let y = 0; y < h; y += 3) {
      ctx.fillRect(0, y, w, 1);
    }
  }

  function drawClassicBars(w, h) {
    const n = bands.length;
    const gap = 2;
    const barW = Math.max(3, (w - gap * (n + 1)) / n);
    for (let i = 0; i < n; i++) {
      const v = smoothed[i];
      const barH = Math.max(2, v * (h - 4));
      const x = gap + i * (barW + gap);
      const y = h - barH;
      ctx.fillStyle = heatGradient(x, y, h, v);
      ctx.fillRect(x, y, barW, barH);
      // pixelated horizontal segments
      ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
      for (let yy = y; yy < h; yy += 4) {
        ctx.fillRect(x, yy, barW, 1);
      }
    }
  }

  function drawPeakCaps(w, h) {
    const n = bands.length;
    const gap = 2;
    const barW = Math.max(3, (w - gap * (n + 1)) / n);
    for (let i = 0; i < n; i++) {
      const v = smoothed[i];
      const barH = Math.max(2, v * (h - 6));
      const x = gap + i * (barW + gap);
      const y = h - barH;
      ctx.fillStyle = heatGradient(x, y, h, v);
      ctx.fillRect(x, y, barW, barH);
      if (v >= peaks[i]) {
        peaks[i] = v;
        peakHold[i] = 18;
      } else if (peakHold[i] > 0) {
        peakHold[i] -= 1;
      } else {
        peaks[i] = Math.max(0, peaks[i] - 0.012);
      }
      const py = h - Math.max(2, peaks[i] * (h - 6)) - 2;
      ctx.fillStyle = LED.yellow;
      ctx.fillRect(x, py, barW, 2);
    }
  }

  function drawLedMatrix(w, h) {
    const n = bands.length;
    const cols = n;
    const rows = Math.max(6, Math.floor(h / 5));
    const cellW = w / cols;
    const cellH = h / rows;
    for (let i = 0; i < cols; i++) {
      const lit = Math.round(smoothed[i] * rows);
      for (let r = 0; r < rows; r++) {
        const on = r < lit;
        const level = (r + 1) / rows;
        const x = i * cellW + 1;
        const y = h - (r + 1) * cellH + 1;
        ctx.fillStyle = on ? heatColor(level) : LED.dim;
        ctx.fillRect(x, y, Math.max(1, cellW - 2), Math.max(1, cellH - 2));
      }
    }
  }

  function drawScope(w, h) {
    const n = bands.length;
    const mid = h * 0.55;
    ctx.strokeStyle = LED.grid;
    ctx.beginPath();
    ctx.moveTo(0, mid);
    ctx.lineTo(w, mid);
    ctx.stroke();
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * w;
      const y = mid - (smoothed[i] - 0.35) * (h * 0.9);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = LED.green;
    ctx.lineWidth = 2;
    ctx.shadowColor = LED.green;
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0;
    // orange ghost trail
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * w;
      const y = mid - (smoothed[i] - 0.35) * (h * 0.7) + 3;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = "rgba(255, 140, 0, 0.45)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  function drawVuMirror(w, h) {
    const n = bands.length;
    const mid = h / 2;
    const gap = 2;
    const barW = Math.max(3, (w - gap * (n + 1)) / n);
    ctx.fillStyle = LED.grid;
    ctx.fillRect(0, mid - 0.5, w, 1);
    for (let i = 0; i < n; i++) {
      const v = smoothed[i];
      const half = Math.max(1, v * (mid - 3));
      const x = gap + i * (barW + gap);
      ctx.fillStyle = heatGradient(x, mid - half, mid, v);
      ctx.fillRect(x, mid - half, barW, half);
      ctx.fillStyle = heatGradient(x, mid, mid + half, v);
      ctx.fillRect(x, mid, barW, half);
    }
  }

  function drawFireBars(w, h) {
    const n = bands.length;
    const gap = 1;
    const barW = Math.max(4, (w - gap * (n + 1)) / n);
    const flicker = (performance.now() - t0) * 0.01;
    for (let i = 0; i < n; i++) {
      const wobble = 0.04 * Math.sin(flicker + i * 1.7);
      const v = Math.max(0, Math.min(1, smoothed[i] + wobble));
      const barH = Math.max(2, v * (h - 2));
      const x = gap + i * (barW + gap);
      const y = h - barH;
      const g = ctx.createLinearGradient(x, y, x, h);
      g.addColorStop(0, LED.red);
      g.addColorStop(0.25, LED.orange);
      g.addColorStop(0.55, LED.yellow);
      g.addColorStop(1, LED.green);
      ctx.fillStyle = g;
      ctx.fillRect(x, y, barW, barH);
    }
  }

  function drawSegmentLeds(w, h) {
    // Horizontal stereo-style LED meters (ClassicLED vibe)
    const rows = 2;
    const segs = 24;
    const rowH = (h - 6) / rows;
    const averages = [
      smoothed.slice(0, Math.ceil(smoothed.length / 2)).reduce(function (a, b) {
        return a + b;
      }, 0) /
        Math.max(1, Math.ceil(smoothed.length / 2)),
      smoothed.slice(Math.floor(smoothed.length / 2)).reduce(function (a, b) {
        return a + b;
      }, 0) /
        Math.max(1, Math.floor(smoothed.length / 2)),
    ];
    for (let row = 0; row < rows; row++) {
      const lit = Math.round(averages[row] * segs);
      const y = 3 + row * (rowH + 2);
      for (let s = 0; s < segs; s++) {
        const x = 4 + s * ((w - 8) / segs);
        const level = (s + 1) / segs;
        ctx.fillStyle = s < lit ? heatColor(level) : LED.dim;
        ctx.fillRect(x, y, Math.max(2, (w - 8) / segs - 2), rowH - 2);
      }
    }
  }

  function paint() {
    const w = strip.clientWidth;
    const h = strip.clientHeight;
    if (w < 1 || h < 1) {
      raf = requestAnimationFrame(paint);
      return;
    }
    for (let i = 0; i < bands.length; i++) {
      smoothed[i] += (bands[i] - smoothed[i]) * 0.32;
    }
    while (peaks.length < bands.length) peaks.push(0);
    while (peakHold.length < bands.length) peakHold.push(0);
    peaks.length = bands.length;
    peakHold.length = bands.length;

    drawBackdrop(w, h);
    const style = STYLES[styleIndex % STYLES.length];
    if (style === "peakCaps") drawPeakCaps(w, h);
    else if (style === "ledMatrix") drawLedMatrix(w, h);
    else if (style === "scope") drawScope(w, h);
    else if (style === "vuMirror") drawVuMirror(w, h);
    else if (style === "fireBars") drawFireBars(w, h);
    else if (style === "segmentLeds") drawSegmentLeds(w, h);
    else drawClassicBars(w, h);
    raf = requestAnimationFrame(paint);
  }

  function onFrame(raw) {
    try {
      const data = JSON.parse(raw);
      if (!data || !Array.isArray(data.bands)) return;
      bands = data.bands.map(function (v) {
        const n = Number(v);
        if (!isFinite(n)) return 0;
        return Math.max(0, Math.min(1, n));
      });
      if (bands.length < 1) bands = new Array(10).fill(0);
      while (smoothed.length < bands.length) smoothed.push(0);
      smoothed.length = bands.length;
    } catch (_) {
      /* ignore bad frames */
    }
  }

  function connect() {
    if (es) {
      try {
        es.close();
      } catch (_) {}
    }
    es = new EventSource("/api/visstream");
    es.onmessage = function (ev) {
      onFrame(ev.data);
    };
    es.onerror = function () {
      /* keep strip blank; EventSource retries */
    };
  }

  resize();
  window.addEventListener("resize", resize);
  connect();
  raf = requestAnimationFrame(paint);
  setInterval(function () {
    styleIndex = (styleIndex + 1) % STYLES.length;
  }, CYCLE_MS);
})();
