(() => {
  const WINDOW_MS = 10_000;
  document.getElementById('pi-host').textContent = location.host;

  function mkChart(id, color) {
    const ctx = document.getElementById(id).getContext('2d');
    return new Chart(ctx, {
      type: 'line',
      data: { datasets: [{
        data: [], borderColor: color, backgroundColor: color + '33',
        borderWidth: 1.2, pointRadius: 0, tension: 0.15, fill: true,
      }]},
      options: {
        animation: false, responsive: true, maintainAspectRatio: false,
        parsing: false, normalized: true,
        scales: {
          x: { type: 'linear', ticks: { color: '#94a3b8', maxTicksLimit: 6 },
               grid: { color: '#1e2d4a' } },
          y: { min: 0, max: 1, ticks: { color: '#94a3b8' },
               grid: { color: '#1e2d4a' } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  const probChart = mkChart('prob-chart', '#60a5fa');
  const ampChart  = mkChart('amp-chart',  '#22c55e');

  function pushPoint(chart, t, v) {
    const d = chart.data.datasets[0].data;
    d.push({ x: t, y: v });
    const cutoff = t - WINDOW_MS;
    while (d.length && d[0].x < cutoff) d.shift();
    chart.update('none');
  }

  const els = {
    stateValue:  document.getElementById('state-value'),
    bridge:      document.getElementById('bridge-state'),
    callInfo:    document.getElementById('call-info'),
    duration:    document.getElementById('duration'),
    frames:      document.getElementById('frames'),
    latency:     document.getElementById('latency'),
    threshold:   document.getElementById('threshold'),
    log:         document.getElementById('utterance-log'),
    conn:        document.getElementById('conn'),
  };

  let callStartT = 0;
  let frameCount = 0;
  let latSum = 0, latMax = 0;
  let durTimer = null;

  function fmtDur(ms) {
    const s = Math.floor(ms / 1000);
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }

  function setState(state) {
    els.stateValue.textContent = state.toUpperCase();
    els.stateValue.className = 'state-' + state;
  }

  function addUtterance(ms) {
    const now = new Date();
    const stamp = now.toTimeString().slice(0, 8);
    const row = document.createElement('div');
    row.className = 'ent';
    row.innerHTML = `<span class="ts">${stamp}</span>` +
                    `<span>speech</span>` +
                    `<span class="dur">${(ms / 1000).toFixed(2)}s</span>`;
    els.log.insertBefore(row, els.log.firstChild);
    while (els.log.children.length > 50) els.log.lastChild.remove();
  }

  function connect() {
    const url = `ws://${location.host}/stream`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      els.conn.className = 'up';
      els.conn.textContent = 'connected';
    };
    ws.onclose = () => {
      els.conn.className = 'down';
      els.conn.textContent = 'disconnected — retrying';
      setTimeout(connect, 1500);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      let ev; try { ev = JSON.parse(e.data); } catch { return; }
      handle(ev);
    };
  }

  function handle(ev) {
    switch (ev.type) {
      case 'hello':
        els.bridge.textContent = ev.bridge_state || 'idle';
        els.threshold.textContent = (ev.threshold ?? 0.5).toFixed(2);
        break;
      case 'frame':
        frameCount = ev.frame ?? (frameCount + 1);
        els.frames.textContent = frameCount;
        latSum += ev.latency_ms; latMax = Math.max(latMax, ev.latency_ms);
        els.latency.textContent =
          `${(latSum / frameCount).toFixed(1)} ms avg / ${latMax.toFixed(1)} max`;
        pushPoint(probChart, ev.t, ev.prob);
        pushPoint(ampChart,  ev.t, ev.max_abs);
        setState(ev.state);
        break;
      case 'speech_start':
        setState('speaking');
        break;
      case 'speech_end':
        setState('idle');
        if (ev.duration_ms) addUtterance(ev.duration_ms);
        break;
      case 'call_start':
        callStartT = Date.now();
        els.bridge.textContent = 'in_call';
        els.callInfo.textContent =
          `${ev.endpoint || '—'} (${ev.mode || '—'})`;
        frameCount = 0; latSum = 0; latMax = 0;
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
