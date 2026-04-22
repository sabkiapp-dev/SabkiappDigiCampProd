(() => {
  const WINDOW_MS = 10_000;
  document.getElementById('pi-host').textContent = location.host;

  // ── Speaking intervals (for background shading on charts) ──
  // Each entry: {start: t_ms, end: t_ms|null}. end=null means still speaking.
  const speakingIntervals = [];

  // ── Plugin: shade SPEAKING regions behind the chart lines ──
  const speakingBandPlugin = {
    id: 'speakingBand',
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      if (!speakingIntervals.length) return;
      ctx.save();
      ctx.fillStyle = 'rgba(34, 197, 94, 0.18)';  // green @ 18%
      const xScale = scales.x;
      for (const iv of speakingIntervals) {
        const x0 = xScale.getPixelForValue(iv.start);
        const x1 = xScale.getPixelForValue(iv.end ?? (xScale.max));
        const left  = Math.max(x0, chartArea.left);
        const right = Math.min(x1, chartArea.right);
        if (right > left) {
          ctx.fillRect(left, chartArea.top,
                       right - left, chartArea.bottom - chartArea.top);
        }
      }
      ctx.restore();
    },
  };

  // ── Plugin: draw threshold line on prob chart ──
  const thresholdLinePlugin = {
    id: 'thresholdLine',
    afterDatasetsDraw(chart, _, opts) {
      const value = opts.value;
      if (value == null) return;
      const { ctx, chartArea, scales } = chart;
      const y = scales.y.getPixelForValue(value);
      ctx.save();
      ctx.strokeStyle = '#f59e0b';  // amber
      ctx.setLineDash([6, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(chartArea.left, y);
      ctx.lineTo(chartArea.right, y);
      ctx.stroke();
      ctx.restore();
    },
  };

  // Draw a faint vertical line every 10 frames on the x-axis.
  // Points carry .frame; we ride on Chart.js's own draw pass so the grid
  // stays in sync with the zoom/pan state.
  const frameGridPlugin = {
    id: 'frameGrid',
    afterDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      const d = chart.data.datasets[0].data;
      if (!d.length) return;
      ctx.save();
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.10)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (const p of d) {
        if (!p.frame || p.frame % 10 !== 0) continue;
        const x = scales.x.getPixelForValue(p.x);
        if (x < chartArea.left || x > chartArea.right) continue;
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
      }
      ctx.stroke();
      ctx.restore();
    },
  };

  Chart.register(speakingBandPlugin, thresholdLinePlugin, frameGridPlugin);

  // Segment coloring driven by the per-point .above flag (set when we push data).
  // Used on BOTH charts so it's immediately visible when VAD crosses the threshold.
  const ABOVE = '#22c55e';
  const BELOW = '#ef4444';
  const aboveFill = 'rgba(34,197,94,0.35)';
  const belowFill = 'rgba(239,68,68,0.20)';
  const thresholdSegment = {
    borderColor: (c) => (c.p1.raw && c.p1.raw.above) ? ABOVE : BELOW,
    backgroundColor: (c) => (c.p1.raw && c.p1.raw.above) ? aboveFill : belowFill,
  };

  // For the binary is-speech chart: a segment is green if EITHER endpoint is
  // at y=1 (so rising/falling edges are green, only flat y=0 runs stay red).
  const binarySegment = {
    borderColor: (c) => {
      const up = (c.p0?.parsed.y ?? 0) >= 0.5 || (c.p1?.parsed.y ?? 0) >= 0.5;
      return up ? ABOVE : BELOW;
    },
    backgroundColor: (c) => {
      const up = (c.p0?.parsed.y ?? 0) >= 0.5 || (c.p1?.parsed.y ?? 0) >= 0.5;
      return up ? aboveFill : belowFill;
    },
  };

  function mkChart(id, opts) {
    const ctx = document.getElementById(id).getContext('2d');
    const yMax = opts?.yMax ?? 1;
    const stepped = !!opts?.stepped;
    const segment = opts?.segment || thresholdSegment;
    return new Chart(ctx, {
      type: 'line',
      data: { datasets: [{
        data: [],
        borderColor: BELOW,
        borderWidth: 1.6,
        pointRadius: 0,
        tension: stepped ? 0 : 0.15,
        stepped: stepped,
        fill: true,
        segment: segment,
      }]},
      options: {
        animation: false, responsive: true, maintainAspectRatio: false,
        parsing: false, normalized: true,
        scales: {
          x: { type: 'linear',
               ticks: { color: '#94a3b8', maxTicksLimit: 6,
                        callback: () => '' },
               grid: { color: '#1e2d4a' } },
          y: { min: 0, max: yMax, ticks: { color: '#94a3b8' },
               grid: { color: '#1e2d4a' } },
        },
        plugins: {
          legend: { display: false },
          ...(opts?.plugins || {}),
        },
      },
    });
  }

  const probChart = mkChart('prob-chart', { plugins: { thresholdLine: { value: 0.5 } } });
  // Amp chart y-max compressed 5x — typical speech max_abs stays under 0.20 so
  // full-scale [0,1] wastes most of the panel. Values above 0.25 get clipped,
  // which is fine for calibration (clipping itself is a useful visual cue).
  const ampChart  = mkChart('amp-chart',  { yMax: 0.25, plugins: { thresholdLine: { value: 0.0 } } });
  // Binary VAD decision: 1 = speech (green fill), 0 = silence (red fill).
  // stepped: true so values jump cleanly without interpolation between 0↔1.
  // binarySegment so transition edges (vertical jumps to y=1) stay green.
  const speechChart = mkChart('speech-chart', { yMax: 1, stepped: true, segment: binarySegment });

  function pushPoint(chart, t, v, above, frame) {
    const d = chart.data.datasets[0].data;
    d.push({ x: t, y: v, above: !!above, frame: frame || 0 });
    const cutoff = t - WINDOW_MS;
    while (d.length && d[0].x < cutoff) d.shift();
    chart.update('none');
  }

  // Trim speakingIntervals to the visible window — keep a small slop
  function trimIntervals(now) {
    const cutoff = now - WINDOW_MS - 1000;
    while (speakingIntervals.length &&
           (speakingIntervals[0].end ?? now) < cutoff) {
      speakingIntervals.shift();
    }
  }

  const els = {
    stateValue:  document.getElementById('state-value'),
    stateCard:   document.getElementById('state-card'),
    bridge:      document.getElementById('bridge-state'),
    callInfo:    document.getElementById('call-info'),
    duration:    document.getElementById('duration'),
    frames:      document.getElementById('frames'),
    latency:     document.getElementById('latency'),
    threshold:   document.getElementById('threshold'),
    log:         document.getElementById('utterance-log'),
    conn:        document.getElementById('conn'),
    lastSpeech:  document.getElementById('last-speech'),
    speakingTimer: document.getElementById('speaking-timer'),
    // sliders + their live labels
    sThreshold:  document.getElementById('s-threshold'),
    sAmp:        document.getElementById('s-amp'),
    sAmpHold:    document.getElementById('s-amphold'),
    sOnset:      document.getElementById('s-onset'),
    sOffset:     document.getElementById('s-offset'),
    sMinUtt:     document.getElementById('s-minutt'),
    sPreRoll:    document.getElementById('s-preroll'),
    lThreshold:  document.getElementById('l-threshold'),
    lAmp:        document.getElementById('l-amp'),
    lAmpHold:    document.getElementById('l-amphold'),
    lOnset:      document.getElementById('l-onset'),
    lOffset:     document.getElementById('l-offset'),
    lMinUtt:     document.getElementById('l-minutt'),
    lPreRoll:    document.getElementById('l-preroll'),
    srcAsterisk: document.getElementById('src-asterisk'),
    srcMic:      document.getElementById('src-mic'),
    srcStatus:   document.getElementById('src-status'),
    outTts:      document.getElementById('out-tts'),
    outEcho:     document.getElementById('out-echo'),
    outRaw:      document.getElementById('out-raw'),
    outStatus:   document.getElementById('out-status'),
  };

  let callStartT = 0;
  let frameCount = 0;
  let latSum = 0, latMax = 0;
  let durTimer = null;
  let threshold = 0.5;
  let ampThreshold = 0.0;       // amplitude floor — frame only counts as speech if max_abs >= this
  let speakingStartT = 0;       // wall-clock ms when we entered SPEAKING
  let speakingAboveFrames = 0;  // frames with prob >= threshold AND amp >= ampThreshold
  let wsRef = null;             // set in connect()
  let isSpeechState = 0;        // sticky is-speech flag for the binary chart:
                                //   0 → 1 requires BOTH prob AND amp above threshold
                                //   1 → 0 requires prob BELOW threshold

  function fmtDur(ms) {
    const s = Math.floor(ms / 1000);
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }

  function setState(state) {
    els.stateValue.textContent = state.toUpperCase();
    els.stateValue.className = 'state-' + state;
    els.stateCard.className = 'card state-card-' + state;
  }

  // Each row has two pending slots — filtered + raw. When a labeled
  // transcript arrives we fill the matching slot. YAMNet categories land in
  // a separate .cat span under the transcript.
  function addUtterance(ms) {
    const now = new Date();
    const stamp = now.toTimeString().slice(0, 8);
    const durStr = `${(ms / 1000).toFixed(2)}s`;
    if (els.lastSpeech) {
      els.lastSpeech.innerHTML =
        `<span class="k">Last speech:</span> <span class="v">${durStr} at ${stamp}</span>`;
    }
    const row = document.createElement('div');
    row.className = 'ent';
    row.dataset.pendingFiltered = '1';
    row.dataset.pendingRaw      = '1';
    row.innerHTML =
      `<span class="ts">${stamp}</span>` +
      `<span class="dur">${durStr}</span>` +
      `<div class="text-wrap">` +
        `<div class="slot slot-filtered">` +
          `<span class="role role-filtered">filtered</span>` +
          `<span class="text pending">… transcribing …</span>` +
        `</div>` +
        `<div class="cat cat-filtered"></div>` +
        `<div class="slot slot-raw">` +
          `<span class="role role-raw">raw</span>` +
          `<span class="text pending">… transcribing …</span>` +
        `</div>` +
        `<div class="cat cat-raw"></div>` +
      `</div>`;
    els.log.insertBefore(row, els.log.firstChild);
    while (els.log.children.length > 50) els.log.lastChild.remove();
  }

  function fillCategory(classes, label) {
    const slot = (label === 'filtered') ? 'filtered' : 'raw';
    // Pick row that still has the matching slot pending OR most recent row.
    const pendingKey = slot === 'filtered' ? 'pendingFiltered' : 'pendingRaw';
    let targetRow = null;
    for (const row of els.log.children) {
      if (row.dataset[pendingKey] === '1') {
        targetRow = row;
        break;
      }
    }
    if (!targetRow) targetRow = els.log.children[0];
    if (!targetRow) return;
    const catEl = targetRow.querySelector(`.cat-${slot}`);
    if (!catEl) return;
    const html = (classes || []).slice(0, 3).map(c => {
      const score = typeof c.score === 'number' ? ` ${(c.score * 100).toFixed(0)}%` : '';
      return `<span class="tag">${escapeHtml(c.name)}${score}</span>`;
    }).join('');
    catEl.innerHTML = html;
  }

  function fillTranscript(text, label) {
    // Default pre-existing server code path: empty label OR 'main' maps to raw slot.
    const slot = (label === 'filtered') ? 'filtered' : 'raw';
    const pendingKey = slot === 'filtered' ? 'pendingFiltered' : 'pendingRaw';
    for (const row of els.log.children) {
      if (row.dataset[pendingKey] !== '1') continue;
      const textEl = row.querySelector(`.slot-${slot} .text`);
      if (!textEl) return;
      const words = (text || '').split(/\s+/).filter(Boolean);
      const wordsHtml = words.length
        ? words.map(w => `<span class="word">${escapeHtml(w)}</span>`).join('')
        : `<span style="color:var(--dim);font-style:italic;">(empty)</span>`;
      textEl.innerHTML = wordsHtml;
      textEl.classList.remove('pending');
      delete row.dataset[pendingKey];
      return;
    }
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function connect() {
    const url = `ws://${location.host}/stream`;
    const ws = new WebSocket(url);
    wsRef = ws;
    ws.onopen  = () => { els.conn.className = 'up';   els.conn.textContent = 'connected'; };
    ws.onclose = () => { els.conn.className = 'down'; els.conn.textContent = 'disconnected — retrying'; wsRef = null; setTimeout(connect, 1500); };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch {} };
  }

  function sendParam(name, value) {
    if (!wsRef || wsRef.readyState !== 1) return;
    wsRef.send(JSON.stringify({ type: 'set_param', name, value }));
  }

  // Live-sync slider labels + push to bridge on input.
  // Defensive: if the DOM is missing elements (stale cached HTML), skip —
  // otherwise the whole IIFE throws and connect() never runs.
  function bindSlider(slider, label, name, parse) {
    if (!slider || !label) { console.warn('slider/label missing:', name); return; }
    slider.addEventListener('input', () => {
      label.textContent = slider.value;
      sendParam(name, parse(slider.value));
    });
  }
  bindSlider(els.sThreshold, els.lThreshold, 'threshold',            parseFloat);
  // Amp slider also updates the local state immediately so the chart's
  // coloring + threshold line don't wait for the server echo to update.
  if (els.sAmp && els.lAmp) {
    els.sAmp.addEventListener('input', () => {
      ampThreshold = parseFloat(els.sAmp.value);
      els.lAmp.textContent = ampThreshold.toFixed(3);
      ampChart.options.plugins.thresholdLine.value = ampThreshold;
      sendParam('amplitude_threshold', ampThreshold);
    });
  }
  bindSlider(els.sAmpHold,   els.lAmpHold,   'amplitude_hold_frames', parseInt);
  bindSlider(els.sOnset,     els.lOnset,     'onset_frames',         parseInt);
  bindSlider(els.sOffset,    els.lOffset,    'offset_frames',        parseInt);
  bindSlider(els.sMinUtt,    els.lMinUtt,    'min_utterance_frames', parseInt);
  bindSlider(els.sPreRoll,   els.lPreRoll,   'pre_roll_frames',       parseInt);

  function setSourceUI(src) {
    if (els.srcAsterisk) els.srcAsterisk.classList.toggle('src-active', src === 'asterisk');
    if (els.srcMic)      els.srcMic.classList.toggle('src-active',      src === 'mic');
    if (els.srcStatus)   els.srcStatus.textContent = src === 'mic'
      ? 'mic — speak into the USB mic to test VAD'
      : 'phone audio (needs active call)';
  }
  function sendSource(src) {
    if (!wsRef || wsRef.readyState !== 1) return;
    wsRef.send(JSON.stringify({ type: 'set_source', source: src }));
  }
  if (els.srcAsterisk) els.srcAsterisk.addEventListener('click', () => sendSource('asterisk'));
  if (els.srcMic)      els.srcMic.addEventListener('click',      () => sendSource('mic'));

  function setOutputUI(out) {
    if (els.outTts)  els.outTts.classList.toggle('src-active',  out === 'tts');
    if (els.outEcho) els.outEcho.classList.toggle('src-active', out === 'echo');
    if (els.outRaw)  els.outRaw.classList.toggle('src-active',  out === 'raw');
    if (els.outStatus) {
      els.outStatus.textContent = (
        out === 'echo' ? 'echo — VAD-filtered speech replayed to caller' :
        out === 'raw'  ? 'raw — every SPEAKING-state frame, unfiltered' :
                         'tts — normal AI pipeline'
      );
    }
  }
  function sendOutput(out) {
    if (!wsRef || wsRef.readyState !== 1) return;
    wsRef.send(JSON.stringify({ type: 'set_output', output: out }));
  }
  if (els.outTts)  els.outTts.addEventListener('click',  () => sendOutput('tts'));
  if (els.outEcho) els.outEcho.addEventListener('click', () => sendOutput('echo'));
  if (els.outRaw)  els.outRaw.addEventListener('click',  () => sendOutput('raw'));

  // Live "speaking for X.XXs / Y frames above threshold" tick
  setInterval(() => {
    if (!els.speakingTimer) return;
    if (!speakingStartT) { els.speakingTimer.innerHTML = '&nbsp;'; return; }
    const ms = Date.now() - speakingStartT;
    els.speakingTimer.textContent =
      `▶ speaking ${(ms / 1000).toFixed(2)}s · ${speakingAboveFrames} frames ≥ threshold`;
  }, 100);

  function handle(ev) {
    switch (ev.type) {
      case 'hello':
      case 'params':
        els.bridge.textContent = ev.bridge_state || els.bridge.textContent;
        if (ev.source !== undefined) setSourceUI(ev.source);
        if (ev.output !== undefined) setOutputUI(ev.output);
        if (ev.threshold !== undefined) {
          threshold = ev.threshold;
          els.threshold.textContent = threshold.toFixed(2);
          probChart.options.plugins.thresholdLine.value = threshold;
          els.sThreshold.value = threshold; els.lThreshold.textContent = threshold.toFixed(2);
        }
        if (ev.amplitude_threshold !== undefined) {
          ampThreshold = Number(ev.amplitude_threshold);
          ampChart.options.plugins.thresholdLine.value = ampThreshold;
          if (els.sAmp) els.sAmp.value = ampThreshold;
          if (els.lAmp) els.lAmp.textContent = ampThreshold.toFixed(3);
        }
        if (ev.onset_frames !== undefined) {
          els.sOnset.value = ev.onset_frames;  els.lOnset.textContent  = ev.onset_frames;
        }
        if (ev.offset_frames !== undefined) {
          els.sOffset.value = ev.offset_frames; els.lOffset.textContent = ev.offset_frames;
        }
        if (ev.min_utterance_frames !== undefined) {
          els.sMinUtt.value = ev.min_utterance_frames; els.lMinUtt.textContent = ev.min_utterance_frames;
        }
        if (ev.pre_roll_frames !== undefined && els.sPreRoll) {
          els.sPreRoll.value = ev.pre_roll_frames;
          els.lPreRoll.textContent = ev.pre_roll_frames;
        }
        if (ev.amplitude_hold_frames !== undefined && els.sAmpHold) {
          els.sAmpHold.value = ev.amplitude_hold_frames;
          els.lAmpHold.textContent = ev.amplitude_hold_frames;
        }
        break;
      case 'source':
        setSourceUI(ev.source);
        speakingIntervals.length = 0;
        break;
      case 'output':
        setOutputUI(ev.output);
        break;
      case 'transcript':
        fillTranscript(ev.text || '', ev.label || 'main');
        break;
      case 'category':
        fillCategory(ev.classes || [], ev.label || 'main');
        break;
      case 'frame':
        frameCount = ev.frame ?? (frameCount + 1);
        els.frames.textContent = frameCount;
        latSum += ev.latency_ms; latMax = Math.max(latMax, ev.latency_ms);
        els.latency.textContent =
          `${(latSum / frameCount).toFixed(1)} ms avg / ${latMax.toFixed(1)} max`;
        // Color each chart independently by its own threshold.
        const aboveProb = ev.prob    >= threshold;
        const aboveAmp  = ev.max_abs >= ampThreshold;
        // Is-speech viz state machine:
        //   0 → 1: need BOTH prob AND amp above threshold
        //   staying at 1: prob must stay above threshold (amp ignored)
        //   1 → 0: prob drops below threshold
        if (isSpeechState === 0) {
          if (aboveProb && aboveAmp) isSpeechState = 1;
        } else {
          if (!aboveProb) isSpeechState = 0;
        }
        const isSpeech = isSpeechState === 1;
        if (isSpeech && speakingStartT) speakingAboveFrames++;
        pushPoint(probChart,   ev.t, ev.prob,    aboveProb, ev.frame);
        pushPoint(ampChart,    ev.t, ev.max_abs, aboveAmp,  ev.frame);
        pushPoint(speechChart, ev.t, isSpeech ? 1 : 0, isSpeech, ev.frame);
        setState(ev.state);
        trimIntervals(ev.t);
        // Extend the open speaking interval (if any) to the latest frame time
        if (speakingIntervals.length) {
          const cur = speakingIntervals[speakingIntervals.length - 1];
          if (cur.end === null) cur.end = ev.t;
        }
        break;
      case 'speech_start':
        setState('speaking');
        speakingStartT = Date.now();
        speakingAboveFrames = 0;
        speakingIntervals.push({ start: ev.t ?? Date.now(), end: null });
        break;
      case 'speech_end':
        setState('idle');
        speakingStartT = 0;
        if (speakingIntervals.length) {
          const cur = speakingIntervals[speakingIntervals.length - 1];
          cur.end = ev.t ?? Date.now();
        }
        if (ev.duration_ms) addUtterance(ev.duration_ms);
        break;
      case 'call_start':
        callStartT = Date.now();
        els.bridge.textContent = 'in_call';
        els.callInfo.textContent = `${ev.endpoint || '—'} (${ev.mode || '—'})`;
        frameCount = 0; latSum = 0; latMax = 0;
        speakingIntervals.length = 0;
        if (durTimer) clearInterval(durTimer);
        durTimer = setInterval(() => {
          els.duration.textContent = fmtDur(Date.now() - callStartT);
        }, 500);
        break;
      case 'call_end':
        els.bridge.textContent = 'idle';
        if (durTimer) { clearInterval(durTimer); durTimer = null; }
        break;
    }
  }

  connect();
})();
