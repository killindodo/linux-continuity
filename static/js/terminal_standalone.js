// Standalone Remote Terminal Controller
// Developed by killindodo

document.addEventListener('DOMContentLoaded', () => {
  const connStatus = document.getElementById('connStatus');
  const toastEl = document.getElementById('toast');
  let toastTimer = null;

  function showToast(msg) {
    if (toastTimer) clearTimeout(toastTimer);
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    toastTimer = setTimeout(() => {
      toastEl.classList.remove('show');
    }, 2500);
  }

  function setStatus(connected, text) {
    if (!connStatus) return;
    connStatus.textContent = text;
    if (connected) {
      connStatus.classList.add('connected');
      connStatus.classList.remove('disconnected');
    } else {
      connStatus.classList.remove('connected');
      connStatus.classList.add('disconnected');
    }
  }

  // Token & PIN Authentication
  const urlParams = new URLSearchParams(window.location.search);
  let authToken = urlParams.get('token') || localStorage.getItem('continuity_token') || '';
  if (urlParams.get('token')) {
    localStorage.setItem('continuity_token', urlParams.get('token'));
  }

  const pinModal = document.getElementById('pinModal');
  const pinInput = document.getElementById('pinInput');
  const btnUnlock = document.getElementById('btnUnlock');
  const pinError = document.getElementById('pinError');

  function showPinModal() {
    if (pinModal) {
      pinModal.style.display = 'flex';
      setTimeout(() => pinInput && pinInput.focus(), 200);
    }
  }

  function hidePinModal() {
    if (pinModal) pinModal.style.display = 'none';
  }

  if (btnUnlock) {
    btnUnlock.addEventListener('click', async () => {
      const val = pinInput ? pinInput.value.trim() : '';
      if (!val) return;
      try {
        const res = await fetch('/api/auth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: val })
        });
        const data = await res.json();
        if (res.ok && data.token) {
          authToken = data.token;
          localStorage.setItem('continuity_token', authToken);
          hidePinModal();
          init();
          showToast('✓ Terminal Unlocked');
        } else {
          if (pinError) pinError.style.display = 'block';
          if (pinInput) pinInput.value = '';
        }
      } catch (e) {
        if (pinError) pinError.style.display = 'block';
      }
    });
  }

  if (pinInput) {
    pinInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') btnUnlock && btnUnlock.click();
    });
  }

  // Terminal Setup
  const termContainer = document.getElementById('termStandalone');
  const term = new Terminal({
    cursorBlink: true,
    fontFamily: '"Cascadia Code", "Fira Code", monospace',
    fontSize: 13,
    lineHeight: 1.2,
    theme: {
      background: '#0c0e14',
      foreground: '#e4e7ee',
      cursor: '#00d2ff',
      selectionBackground: '#264f78',
      black: '#1a1d26',
      red: '#ff5555',
      green: '#50fa7b',
      yellow: '#f1fa8c',
      blue: '#bd93f9',
      magenta: '#ff79c6',
      cyan: '#8be9fd',
      white: '#f8f8f2'
    }
  });

  const fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(termContainer);
  fitAddon.fit();

  let termWs = null;
  let currentSession = 'main';
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  let pingIntervalTimer = null;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

  function connectTerminal(sessionName) {
    if (sessionName) currentSession = sessionName;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (termWs) {
      try { termWs.close(); } catch (e) {}
      termWs = null;
    }

    term.write(`\r\n\x1b[36m[*] Connecting to remote shell: [${currentSession}]...\x1b[0m\r\n`);
    const termUrl = `${protocol}//${window.location.host}/ws/terminal?token=${encodeURIComponent(authToken)}&session=${encodeURIComponent(currentSession)}`;
    termWs = new WebSocket(termUrl);
    termWs.binaryType = 'arraybuffer';

    termWs.onopen = () => {
      reconnectAttempts = 0;
      setStatus(true, 'Connected');
      fitAddon.fit();
      termWs.send(JSON.stringify({
        type: 'resize',
        cols: term.cols,
        rows: term.rows
      }));
      startPingHeartbeat();
    };

    termWs.onmessage = (evt) => {
      if (typeof evt.data === 'string') {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'output') {
            term.write(msg.data);
          } else if (msg.type === 'pong') {
            const rtt = Date.now() - (msg.t || Date.now());
            setStatus(true, `Connected (${rtt}ms)`);
          }
        } catch (e) {
          term.write(evt.data);
        }
      } else {
        const u8 = new Uint8Array(evt.data);
        term.write(u8);
      }
    };

    termWs.onclose = () => {
      stopPingHeartbeat();
      setStatus(false, 'Disconnected');
      scheduleReconnect();
    };

    termWs.onerror = () => {
      setStatus(false, 'Conn Error');
    };
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectAttempts++;
    const delay = Math.min(8000, 1500 * Math.pow(1.3, reconnectAttempts - 1));
    const sec = Math.round(delay / 1000);
    setStatus(false, `Reconnecting in ${sec}s...`);
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connectTerminal(currentSession);
    }, delay);
  }

  function startPingHeartbeat() {
    stopPingHeartbeat();
    pingIntervalTimer = setInterval(() => {
      if (termWs && termWs.readyState === WebSocket.OPEN) {
        termWs.send(JSON.stringify({ type: 'ping', t: Date.now() }));
      }
    }, 10000);
  }

  function stopPingHeartbeat() {
    if (pingIntervalTimer) {
      clearInterval(pingIntervalTimer);
      pingIntervalTimer = null;
    }
  }

  term.onData((data) => {
    if (termWs && termWs.readyState === WebSocket.OPEN) {
      termWs.send(JSON.stringify({ type: 'input', data: data }));
    }
  });

  // Mobile Keyboard Keys
  document.querySelectorAll('.kbtn[data-key]').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-key');
      if (termWs && termWs.readyState === WebSocket.OPEN) {
        termWs.send(JSON.stringify({ type: 'input', data: key }));
      }
      term.focus();
    });
  });

  document.getElementById('btnReconnectTerm').addEventListener('click', () => {
    connectTerminal(currentSession);
  });

  document.getElementById('btnClearTerm').addEventListener('click', () => {
    term.clear();
  });

  // Fullscreen Button
  const btnFullscreen = document.getElementById('btnFullscreen');
  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
        btnFullscreen.textContent = '✕ Exit';
      } else {
        document.exitFullscreen().catch(() => {});
        btnFullscreen.textContent = '⛶ Fullscreen';
      }
      setTimeout(() => fitAddon.fit(), 300);
    });
  }

  // Session Selector
  const termSessionSelect = document.getElementById('termSessionSelect');
  const btnNewSession = document.getElementById('btnNewSession');
  const btnLaunchPcTerm = document.getElementById('btnLaunchPcTerm');

  async function loadSessions() {
    try {
      const res = await fetch(`/api/terminals?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();
      if (data.status === 'ok' && data.tmux_sessions) {
        termSessionSelect.innerHTML = '';
        data.tmux_sessions.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.name;
          opt.textContent = `${s.name} (${s.windows} win)`;
          if (s.name === currentSession) opt.selected = true;
          termSessionSelect.appendChild(opt);
        });
      }
    } catch (e) {}
  }

  termSessionSelect.addEventListener('change', () => {
    const selected = termSessionSelect.value;
    if (selected && selected !== currentSession) {
      currentSession = selected;
      connectTerminal(currentSession);
      showToast(`Switched to session: ${currentSession}`);
    }
  });

  btnNewSession.addEventListener('click', async () => {
    const name = prompt('Enter a name for the new terminal session:');
    if (!name || !name.trim()) return;
    const cleanName = name.trim().replace(/[^a-zA-Z0-9_-]/g, '');
    if (!cleanName) return;

    try {
      const res = await fetch(`/api/terminals?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'create', name: cleanName })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        currentSession = cleanName;
        await loadSessions();
        connectTerminal(cleanName);
        showToast(`✓ Created session: ${cleanName}`);
      }
    } catch (e) {
      showToast('Failed to create session');
    }
  });

  btnLaunchPcTerm.addEventListener('click', async () => {
    try {
      const res = await fetch(`/api/terminals?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'launch_pc', name: currentSession })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        showToast(`⚡ Terminal opened on PC desktop`);
      }
    } catch (e) {}
  });

  // Mobile Screen Wake Auto-reconnect
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      if (!termWs || termWs.readyState === WebSocket.CLOSED || termWs.readyState === WebSocket.CLOSING) {
        connectTerminal(currentSession);
      }
    }
  });

  window.addEventListener('resize', () => {
    fitAddon.fit();
    if (termWs && termWs.readyState === WebSocket.OPEN) {
      termWs.send(JSON.stringify({
        type: 'resize',
        cols: term.cols,
        rows: term.rows
      }));
    }
  });

  function init() {
    loadSessions();
    connectTerminal(currentSession);
  }

  fetch('/api/info')
    .then(r => r.json())
    .then(data => {
      if (data.require_pin && !authToken) {
        showPinModal();
      } else {
        init();
      }
    })
    .catch(() => init());
});
