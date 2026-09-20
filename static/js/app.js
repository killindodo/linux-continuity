// Linux Continuity - Mobile Web Client Controller
// Developed by killindodo

document.addEventListener('DOMContentLoaded', () => {
  // Connection Status Element
  const connStatus = document.getElementById('connStatus');

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

  // Toast Helper
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
          // Reset all auth-rejection flags before reconnecting
          authRejected = false;
          reconnectAttempts = 0;
          if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
          initAppConnections();
          showToast('✓ Device Unlocked');
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

  // Tab Switching: Terminal, Files, Clipboard, Camera/Mic (AV), System Controls
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-tab');
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const pane = document.getElementById(`tab-${target}`);
      if (pane) {
        pane.classList.add('active');

        // Stop loops that shouldn't run in background
        if (target === 'terminal') {
          if (typeof stopMediaLoop === 'function') stopMediaLoop();
          if (typeof stopVitalsLoop === 'function') stopVitalsLoop();
          if (typeof loadDesktopWindows === 'function') loadDesktopWindows();
          if (typeof startDesktopTermLoop === 'function') startDesktopTermLoop();
          if (window.fitAddon && embeddedTermContainer && embeddedTermContainer.style.display !== 'none') {
            setTimeout(() => {
              window.fitAddon.fit();
              if (termWs && termWs.readyState === WebSocket.OPEN && term) {
                termWs.send(JSON.stringify({
                  type: 'resize',
                  cols: term.cols,
                  rows: term.rows
                }));
              }
            }, 150);
          }
        } else if (target === 'trackpad') {
          if (typeof stopDesktopTermLoop === 'function') stopDesktopTermLoop();
          if (typeof stopMediaLoop === 'function') stopMediaLoop();
          if (typeof stopVitalsLoop === 'function') stopVitalsLoop();
        } else if (target === 'files') {
          if (typeof stopDesktopTermLoop === 'function') stopDesktopTermLoop();
          if (typeof stopMediaLoop === 'function') stopMediaLoop();
          if (typeof stopVitalsLoop === 'function') stopVitalsLoop();
          if (typeof loadDirectory === 'function') loadDirectory(currentBrowsePath);
        } else if (target === 'av') {
          if (typeof stopDesktopTermLoop === 'function') stopDesktopTermLoop();
          if (typeof stopMediaLoop === 'function') stopMediaLoop();
          if (typeof stopVitalsLoop === 'function') stopVitalsLoop();
        } else if (target === 'system') {
          if (typeof stopDesktopTermLoop === 'function') stopDesktopTermLoop();
          if (typeof loadMediaStatus === 'function') loadMediaStatus();
          if (typeof startMediaLoop === 'function') startMediaLoop();
          if (typeof loadSystemStats === 'function') loadSystemStats();
          if (typeof startVitalsLoop === 'function') startVitalsLoop();
          if (typeof loadTunnelStatus === 'function') loadTunnelStatus();
        } else {
          if (typeof stopDesktopTermLoop === 'function') stopDesktopTermLoop();
          if (typeof stopMediaLoop === 'function') stopMediaLoop();
          if (typeof stopVitalsLoop === 'function') stopVitalsLoop();
        }
      }
    });
  });

  // ----------------------------------------------------
  // 1. Live PC Desktop Terminal Controller (Option A)
  // ----------------------------------------------------
  const btnTermModeDesktop = document.getElementById('btnTermModeDesktop');
  const btnTermModeEmbedded = document.getElementById('btnTermModeEmbedded');
  const desktopTermContainer = document.getElementById('desktopTermContainer');
  const embeddedTermContainer = document.getElementById('embeddedTermContainer');

  const desktopWinSelect = document.getElementById('desktopWinSelect');
  const btnRefreshDesktopWins = document.getElementById('btnRefreshDesktopWins');
  const btnFocusDesktopWin = document.getElementById('btnFocusDesktopWin');
  const btnDesktopSnapshot = document.getElementById('btnDesktopSnapshot');
  const desktopTermImg = document.getElementById('desktopTermImg');
  const desktopTermStatus = document.getElementById('desktopTermStatus');

  const desktopTermInput = document.getElementById('desktopTermInput');
  const btnSendDesktopRun = document.getElementById('btnSendDesktopRun');
  const btnSendDesktopType = document.getElementById('btnSendDesktopType');

  let activeDesktopWid = '';
  let desktopTermTimer = null;
  let isFetchingDesktopFrame = false;

  async function loadDesktopWindows() {
    if (!desktopWinSelect) return;
    try {
      const res = await fetch(`/api/desktop/terminals?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();
      if (data.status === 'ok') {
        const wins = data.windows || [];
        desktopWinSelect.innerHTML = '';
        if (wins.length === 0) {
          desktopWinSelect.innerHTML = '<option value="">No terminal window found</option>';
          activeDesktopWid = '';
          if (desktopTermStatus) desktopTermStatus.textContent = 'No terminal open on PC';
          return;
        }

        wins.forEach((w, idx) => {
          const opt = document.createElement('option');
          opt.value = w.id;
          opt.textContent = w.title;
          if (idx === 0 && !activeDesktopWid) {
            opt.selected = true;
            activeDesktopWid = w.id;
          } else if (w.id === activeDesktopWid) {
            opt.selected = true;
          }
          desktopWinSelect.appendChild(opt);
        });

        if (!activeDesktopWid && wins.length > 0) {
          activeDesktopWid = wins[0].id;
        }

        fetchDesktopTermFrame();
      }
    } catch (e) {}
  }

  function fetchDesktopTermFrame() {
    if (isFetchingDesktopFrame || !desktopTermImg) return;
    isFetchingDesktopFrame = true;
    const wid = desktopWinSelect ? desktopWinSelect.value || activeDesktopWid : activeDesktopWid;
    const ts = Date.now();
    const img = new Image();
    img.src = `/api/desktop/terminal/frame?token=${encodeURIComponent(authToken)}&id=${encodeURIComponent(wid)}&t=${ts}&w=960&q=65`;

    img.onload = () => {
      desktopTermImg.src = img.src;
      isFetchingDesktopFrame = false;
      if (desktopTermStatus) {
        desktopTermStatus.textContent = `Live Terminal • ${new Date().toLocaleTimeString()}`;
      }
    };

    img.onerror = () => {
      isFetchingDesktopFrame = false;
      if (desktopTermStatus) desktopTermStatus.textContent = 'Waiting for terminal window...';
    };
  }

  function startDesktopTermLoop() {
    stopDesktopTermLoop();
    desktopTermTimer = setInterval(fetchDesktopTermFrame, 1500);
  }

  function stopDesktopTermLoop() {
    if (desktopTermTimer) {
      clearInterval(desktopTermTimer);
      desktopTermTimer = null;
    }
  }

  if (desktopWinSelect) {
    desktopWinSelect.addEventListener('change', () => {
      activeDesktopWid = desktopWinSelect.value;
      fetchDesktopTermFrame();
    });
  }

  if (btnRefreshDesktopWins) {
    btnRefreshDesktopWins.addEventListener('click', () => {
      loadDesktopWindows();
      showToast('Scanning desktop windows...');
    });
  }

  if (btnFocusDesktopWin) {
    btnFocusDesktopWin.addEventListener('click', async () => {
      const wid = desktopWinSelect ? desktopWinSelect.value : activeDesktopWid;
      try {
        await fetch(`/api/desktop/terminal/input?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: wid, focus_only: true })
        });
        showToast('Focused terminal on PC desktop');
        setTimeout(fetchDesktopTermFrame, 200);
      } catch (e) {
        showToast('Focus failed');
      }
    });
  }

  if (btnDesktopSnapshot) {
    btnDesktopSnapshot.addEventListener('click', () => {
      fetchDesktopTermFrame();
    });
  }

  // Submode Switcher: Desktop vs Embedded
  if (btnTermModeDesktop && btnTermModeEmbedded) {
    btnTermModeDesktop.addEventListener('click', () => {
      btnTermModeDesktop.classList.add('active');
      btnTermModeEmbedded.classList.remove('active');
      if (desktopTermContainer) desktopTermContainer.style.display = 'flex';
      if (embeddedTermContainer) embeddedTermContainer.style.display = 'none';
      loadDesktopWindows();
      startDesktopTermLoop();
    });

    btnTermModeEmbedded.addEventListener('click', () => {
      btnTermModeEmbedded.classList.add('active');
      btnTermModeDesktop.classList.remove('active');
      if (desktopTermContainer) desktopTermContainer.style.display = 'none';
      if (embeddedTermContainer) embeddedTermContainer.style.display = 'flex';
      stopDesktopTermLoop();
      if (fitAddon) {
        setTimeout(() => fitAddon.fit(), 100);
      }
    });
  }

  // Send Command to Desktop Terminal
  async function sendDesktopCommand(pressEnter = true) {
    if (!desktopTermInput) return;
    const text = desktopTermInput.value;
    if (!text && pressEnter) {
      sendDesktopKey('Return');
      return;
    }
    if (!text) return;

    const wid = desktopWinSelect ? desktopWinSelect.value : activeDesktopWid;
    try {
      await fetch(`/api/desktop/terminal/input?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: wid, text: text, press_enter: pressEnter })
      });
      desktopTermInput.value = '';
      showToast(pressEnter ? '✓ Command sent to PC terminal' : 'Typed in PC terminal');
      setTimeout(fetchDesktopTermFrame, 150);
      setTimeout(fetchDesktopTermFrame, 600);
    } catch (e) {
      showToast('Failed to send command');
    }
  }

  async function sendDesktopKey(key) {
    const wid = desktopWinSelect ? desktopWinSelect.value : activeDesktopWid;
    try {
      await fetch(`/api/desktop/terminal/input?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: wid, key: key })
      });
      setTimeout(fetchDesktopTermFrame, 150);
    } catch (e) {}
  }

  if (btnSendDesktopRun) {
    btnSendDesktopRun.addEventListener('click', () => sendDesktopCommand(true));
  }
  if (btnSendDesktopType) {
    btnSendDesktopType.addEventListener('click', () => sendDesktopCommand(false));
  }

  if (desktopTermInput) {
    desktopTermInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        sendDesktopCommand(true);
      }
    });
  }

  // Desktop Terminal Key Toolbar Buttons
  document.querySelectorAll('.kbtn.dkey[data-dkey]').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-dkey');
      sendDesktopKey(key);
    });
  });

  // Desktop Terminal Quick Macro Chips
  document.querySelectorAll('.btn-chip.dmacro[data-macro]').forEach(chip => {
    chip.addEventListener('click', async () => {
      const macro = chip.getAttribute('data-macro');
      const wid = desktopWinSelect ? desktopWinSelect.value : activeDesktopWid;
      try {
        await fetch(`/api/desktop/terminal/input?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: wid, text: macro, press_enter: true })
        });
        showToast(`⚡ ${macro}`);
        setTimeout(fetchDesktopTermFrame, 150);
        setTimeout(fetchDesktopTermFrame, 600);
      } catch (e) {}
    });
  });

  // ----------------------------------------------------
  // 1b. Embedded Terminal Setup (xterm.js + Shared Tmux Sessions)
  // ----------------------------------------------------
  const termContainer = document.getElementById('terminal');
  let term = null;
  let fitAddon = null;

  try {
    term = new Terminal({
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
    fitAddon = new FitAddon.FitAddon();
    window.fitAddon = fitAddon;
    term.loadAddon(fitAddon);
    if (termContainer) {
      term.open(termContainer);
      fitAddon.fit();
    }
  } catch (e) {
    console.error('[Continuity] xterm init error:', e);
    // Terminal init failed but we MUST continue so PIN modal works
  }

  let termWs = null;
  let currentSession = 'main';
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  let pingIntervalTimer = null;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

  // Flag to stop reconnect loop if auth was rejected
  let authRejected = false;

  function connectTerminal(sessionName) {
    if (authRejected) return; // Don't reconnect after auth failure
    if (sessionName) currentSession = sessionName;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (termWs) {
      try { termWs.close(); } catch (e) {}
      termWs = null;
    }

    if (term) term.write(`\r\n\x1b[36m[*] Attaching to Terminal session: [${currentSession}]...\x1b[0m\r\n`);
    const termUrl = `${protocol}//${window.location.host}/ws/terminal?token=${encodeURIComponent(authToken)}&session=${encodeURIComponent(currentSession)}`;
    termWs = new WebSocket(termUrl);
    termWs.binaryType = 'arraybuffer';

    termWs.onopen = () => {
      reconnectAttempts = 0;
      authRejected = false;
      setStatus(true, 'Connected');
      if (fitAddon) fitAddon.fit();
      termWs.send(JSON.stringify({
        type: 'resize',
        cols: term ? term.cols : 80,
        rows: term ? term.rows : 24
      }));
      startPingHeartbeat();
    };

    termWs.onmessage = (evt) => {
      if (typeof evt.data === 'string') {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'output') {
            if (term) term.write(msg.data);
          } else if (msg.type === 'pong') {
            const rtt = Date.now() - (msg.t || Date.now());
            setStatus(true, `Connected (${rtt}ms)`);
          } else if (msg.type === 'phone_control') {
            handleRemotePhoneControl(msg.action, msg.param);
          }
        } catch (e) {
          if (term) term.write(evt.data);
        }
      } else {
        // Check for unauthorized message in binary data
        const u8 = new Uint8Array(evt.data);
        const text = new TextDecoder().decode(u8);
        if (text.includes('Unauthorized')) {
          authRejected = true;
          setStatus(false, 'PIN Required');
          localStorage.removeItem('continuity_token');
          authToken = '';
          showPinModal();
          return;
        }
        if (term) term.write(u8);
      }
    };

    termWs.onclose = (evt) => {
      stopPingHeartbeat();
      if (authRejected) {
        setStatus(false, 'PIN Required');
        return;
      }
      setStatus(false, 'Disconnected');
      scheduleReconnect();
    };

    termWs.onerror = () => {
      if (!authRejected) setStatus(false, 'Conn Error');
    };
  }

  function scheduleReconnect() {
    if (authRejected) return;
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

  // Mobile Screen Wake Auto-reconnect
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      const pane = document.getElementById('tab-terminal');
      if (pane && pane.classList.contains('active')) {
        if (!termWs || termWs.readyState === WebSocket.CLOSED || termWs.readyState === WebSocket.CLOSING) {
          connectTerminal(currentSession);
        }
      }
    }
  });

  if (term) {
    term.onData((data) => {
      if (termWs && termWs.readyState === WebSocket.OPEN) {
        termWs.send(JSON.stringify({ type: 'input', data: data }));
      }
    });
  }

  // Mobile Keyboard Helper Keys
  document.querySelectorAll('.kbtn[data-key]').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-key');
      if (termWs && termWs.readyState === WebSocket.OPEN) {
        termWs.send(JSON.stringify({ type: 'input', data: key }));
      }
      if (term) term.focus();
    });
  });

  const btnReconnectTerm = document.getElementById('btnReconnectTerm');
  if (btnReconnectTerm) {
    btnReconnectTerm.addEventListener('click', () => {
      connectTerminal(currentSession);
    });
  }

  const btnClearTerm = document.getElementById('btnClearTerm');
  if (btnClearTerm) {
    btnClearTerm.addEventListener('click', () => {
      if (term) term.clear();
    });
  }

  const btnMainTermFullscreen = document.getElementById('btnMainTermFullscreen');
  if (btnMainTermFullscreen) {
    btnMainTermFullscreen.addEventListener('click', () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
        btnMainTermFullscreen.textContent = '✕';
      } else {
        document.exitFullscreen().catch(() => {});
        btnMainTermFullscreen.textContent = '⛶';
      }
      if (fitAddon) setTimeout(() => fitAddon.fit(), 300);
    });
  }

  // Session Management Controls
  const termSessionSelect = document.getElementById('termSessionSelect');
  const btnNewSession = document.getElementById('btnNewSession');
  const btnLaunchPcTerm = document.getElementById('btnLaunchPcTerm');
  const btnToggleProcs = document.getElementById('btnToggleProcs');
  const procsDrawer = document.getElementById('ptsDrawer');
  const procsContent = document.getElementById('ptsList');
  const btnRefreshProcs = document.getElementById('btnRefreshProcs');
  const btnCloseProcs = document.getElementById('btnClosePts');

  async function loadSessions() {
    try {
      const res = await fetch(`/api/terminals?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();
      if (data.status === 'ok' && termSessionSelect) {
        const sessions = data.sessions || [];
        termSessionSelect.innerHTML = '';
        sessions.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.name;
          opt.textContent = `${s.name} (${s.windows} win${s.attached ? ' • attached' : ''})`;
          if (s.name === currentSession) opt.selected = true;
          termSessionSelect.appendChild(opt);
        });
      }
    } catch (e) {}
  }

  if (termSessionSelect) {
    termSessionSelect.addEventListener('change', () => {
      const selected = termSessionSelect.value;
      if (selected && selected !== currentSession) {
        currentSession = selected;
        connectTerminal(currentSession);
        showToast(`Switched to session: ${currentSession}`);
      }
    });
  }

  if (btnNewSession) {
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
  }

  if (btnLaunchPcTerm) {
    btnLaunchPcTerm.addEventListener('click', async () => {
      try {
        const res = await fetch(`/api/terminals?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'launch_pc', name: currentSession })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          showToast(`⚡ Terminal launched on PC desktop (Session: ${currentSession})`);
        } else {
          showToast('Could not launch terminal emulator on PC');
        }
      } catch (e) {
        showToast('Request failed');
      }
    });
  }

  // Running Desktop Terminals (PTS) Inspector
  if (btnToggleProcs && procsDrawer) {
    btnToggleProcs.addEventListener('click', () => {
      if (procsDrawer.style.display === 'none') {
        procsDrawer.style.display = 'block';
        loadRunningProcesses();
      } else {
        procsDrawer.style.display = 'none';
      }
    });
  }

  if (btnCloseProcs && procsDrawer) {
    btnCloseProcs.addEventListener('click', () => {
      procsDrawer.style.display = 'none';
    });
  }

  if (btnRefreshProcs) {
    btnRefreshProcs.addEventListener('click', () => {
      loadRunningProcesses();
    });
  }

  async function loadRunningProcesses() {
    procsContent.innerHTML = '<div class="procs-loading">Inspecting running processes...</div>';
    try {
      const res = await fetch(`/api/terminals?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();
      if (data.status === 'ok') {
        const procs = data.pts_processes || [];
        if (procs.length === 0) {
          procsContent.innerHTML = '<div class="procs-loading">No active processes running on pts terminals.</div>';
          return;
        }

        let html = '<table class="procs-table"><thead><tr><th>TTY</th><th>PID</th><th>User</th><th>Command</th></tr></thead><tbody>';
        procs.forEach(p => {
          html += `<tr>
            <td class="tty">${escapeHtml(p.tty)}</td>
            <td>${escapeHtml(p.pid)}</td>
            <td>${escapeHtml(p.user)}</td>
            <td class="cmd">${escapeHtml(p.cmd)}</td>
          </tr>`;
        });
        html += '</tbody></table>';
        procsContent.innerHTML = html;
      }
    } catch (e) {
      procsContent.innerHTML = '<div class="procs-loading">Error loading active processes</div>';
    }
  }

  window.addEventListener('resize', () => {
    if (fitAddon) {
      fitAddon.fit();
      if (termWs && termWs.readyState === WebSocket.OPEN && term) {
        termWs.send(JSON.stringify({
          type: 'resize',
          cols: term.cols,
          rows: term.rows
        }));
      }
    }
  });

  // (Screen Mirror module removed per user request)

  // ----------------------------------------------------
  // 3. Universal Shared Clipboard
  // ----------------------------------------------------
  const pcClipBox = document.getElementById('pcClipboardText');
  const phoneClipInput = document.getElementById('phoneClipboardInput');
  const btnSendToPc = document.getElementById('btnSendToPc');
  const btnCopyFromPc = document.getElementById('btnCopyFromPc');
  let clipWs = null;
  let currentPcText = '';

  function connectClipboard() {
    if (clipWs && (clipWs.readyState === WebSocket.OPEN || clipWs.readyState === WebSocket.CONNECTING)) return;
    const clipUrl = `${protocol}//${window.location.host}/ws/clipboard?token=${encodeURIComponent(authToken)}`;
    clipWs = new WebSocket(clipUrl);

    clipWs.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'clipboard') {
          currentPcText = data.text || '';
          if (pcClipBox) {
            if (currentPcText.trim()) {
              pcClipBox.textContent = currentPcText;
              pcClipBox.classList.remove('placeholder');
            } else {
              pcClipBox.textContent = '(PC Clipboard is currently empty)';
              pcClipBox.classList.add('placeholder');
            }
          }
        } else if (data.type === 'phone_control') {
          handleRemotePhoneControl(data.action, data.param);
        }
      } catch (e) {}
    };

    clipWs.onclose = () => {
      setTimeout(connectClipboard, 3000);
    };
  }

  if (btnCopyFromPc) {
    btnCopyFromPc.addEventListener('click', async () => {
      if (!currentPcText) {
        showToast('Clipboard is empty');
        return;
      }
      try {
        await navigator.clipboard.writeText(currentPcText);
        showToast('✓ Copied to Phone Clipboard!');
      } catch (e) {
        const ta = document.createElement('textarea');
        ta.value = currentPcText;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('✓ Copied to Phone Clipboard!');
      }
    });
  }

  if (btnSendToPc) {
    btnSendToPc.addEventListener('click', () => {
      if (!phoneClipInput) return;
      const text = phoneClipInput.value;
      if (!text) {
        showToast('Please type or paste text first');
        return;
      }
      if (clipWs && clipWs.readyState === WebSocket.OPEN) {
        clipWs.send(JSON.stringify({
          type: 'set_clipboard',
          text: text
        }));
        showToast('⚡ Sent to Linux PC Clipboard!');
        phoneClipInput.value = '';
      } else {
        showToast('Clipboard service not connected');
      }
    });
  }

  // ----------------------------------------------------
  // 3.5 Remote Phone Control & Telemetry Bridge
  // ----------------------------------------------------
  let alarmAudioCtx = null;
  let alarmOsc = null;
  let phoneCamStream = null;
  let phoneCamInterval = null;

  function playAlarmSound() {
    stopAlarmSound();
    try {
      alarmAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
      alarmOsc = alarmAudioCtx.createOscillator();
      const gain = alarmAudioCtx.createGain();
      alarmOsc.type = 'sawtooth';
      alarmOsc.frequency.setValueAtTime(880, alarmAudioCtx.currentTime);
      gain.gain.setValueAtTime(0.8, alarmAudioCtx.currentTime);
      alarmOsc.connect(gain);
      gain.connect(alarmAudioCtx.destination);
      alarmOsc.start();
    } catch (e) {}
  }

  function stopAlarmSound() {
    if (alarmOsc) {
      try { alarmOsc.stop(); } catch (e) {}
      alarmOsc = null;
    }
    if (alarmAudioCtx) {
      try { alarmAudioCtx.close(); } catch (e) {}
      alarmAudioCtx = null;
    }
  }

  function startPhoneCameraStream(facing) {
    stopPhoneCameraStream();
    const mode = facing === 'front' ? 'user' : 'environment';
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    navigator.mediaDevices.getUserMedia({ video: { facingMode: mode } })
      .then(stream => {
        phoneCamStream = stream;
        const video = document.createElement('video');
        video.srcObject = stream;
        video.play();
        const canvas = document.createElement('canvas');
        canvas.width = 480;
        canvas.height = 360;
        const ctx = canvas.getContext('2d');

        phoneCamInterval = setInterval(() => {
          if (!video.videoWidth) return;
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          canvas.toBlob(blob => {
            if (!blob) return;
            fetch('/api/phone/camera/frame', {
              method: 'POST',
              body: blob
            }).catch(() => {});
          }, 'image/jpeg', 0.6);
        }, 600);
      })
      .catch(err => {
        console.error('Camera stream error:', err);
      });
  }

  function stopPhoneCameraStream() {
    if (phoneCamInterval) {
      clearInterval(phoneCamInterval);
      phoneCamInterval = null;
    }
    if (phoneCamStream) {
      phoneCamStream.getTracks().forEach(t => t.stop());
      phoneCamStream = null;
    }
  }

  function handleRemotePhoneControl(action, param) {
    if (action === 'ring') {
      if (window.AndroidBridge && window.AndroidBridge.ringPhone) {
        window.AndroidBridge.ringPhone(true);
      }
      playAlarmSound();
      showToast('🚨 "Find My Phone" Ringing!');
    } else if (action === 'stop_ring') {
      if (window.AndroidBridge && window.AndroidBridge.ringPhone) {
        window.AndroidBridge.ringPhone(false);
      }
      stopAlarmSound();
      showToast('Alarm stopped');
    } else if (action === 'vibrate') {
      if (window.AndroidBridge && window.AndroidBridge.vibratePhone) {
        window.AndroidBridge.vibratePhone(500);
      } else if (navigator.vibrate) {
        navigator.vibrate([300, 150, 400, 150, 600]);
      }
      showToast('📳 Vibration triggered from PC');
    } else if (action === 'toast') {
      if (window.AndroidBridge && window.AndroidBridge.showToast) {
        window.AndroidBridge.showToast(param || 'Message from PC');
      }
      showToast('💬 PC: ' + (param || 'Ping'));
    } else if (action === 'url') {
      if (window.AndroidBridge && window.AndroidBridge.openUrl) {
        window.AndroidBridge.openUrl(param);
      } else if (param) {
        window.open(param, '_blank');
      }
      showToast('🌐 Opening URL from PC: ' + param);
    } else if (action === 'volume_up') {
      if (window.AndroidBridge && window.AndroidBridge.setVolume) {
        window.AndroidBridge.setVolume(1);
      }
      showToast('🔊 Volume Up (from PC)');
    } else if (action === 'volume_down') {
      if (window.AndroidBridge && window.AndroidBridge.setVolume) {
        window.AndroidBridge.setVolume(-1);
      }
      showToast('🔉 Volume Down (from PC)');
    } else if (action === 'media_play_pause') {
      if (window.AndroidBridge && window.AndroidBridge.playMediaKey) {
        window.AndroidBridge.playMediaKey('play_pause');
      }
      showToast('⏯️ Play/Pause (from PC)');
    } else if (action === 'media_next') {
      if (window.AndroidBridge && window.AndroidBridge.playMediaKey) {
        window.AndroidBridge.playMediaKey('next');
      }
      showToast('⏭️ Next Track (from PC)');
    } else if (action === 'media_prev') {
      if (window.AndroidBridge && window.AndroidBridge.playMediaKey) {
        window.AndroidBridge.playMediaKey('prev');
      }
      showToast('⏮️ Previous Track (from PC)');
    } else if (action === 'camera_start') {
      startPhoneCameraStream(param);
      showToast('📷 Camera Viewfinder active on PC');
    } else if (action === 'camera_stop') {
      stopPhoneCameraStream();
      showToast('📷 Camera Viewfinder stopped');
    }
  }

  // Battery Telemetry Reporting
  function reportBatteryTelemetry() {
    let batteryLevel = null;
    let isCharging = false;
    let deviceModel = (window.AndroidBridge && typeof window.AndroidBridge.getDeviceModel === 'function')
      ? window.AndroidBridge.getDeviceModel()
      : navigator.userAgent;

    if (window.AndroidBridge && typeof window.AndroidBridge.getBatteryLevel === 'function') {
      try {
        const lvl = window.AndroidBridge.getBatteryLevel();
        if (typeof lvl === 'number' && lvl >= 0 && lvl <= 100) {
          batteryLevel = lvl;
        }
      } catch (e) {}
    }

    if (window.AndroidBridge && typeof window.AndroidBridge.isCharging === 'function') {
      try {
        isCharging = !!window.AndroidBridge.isCharging();
      } catch (e) {}
    }

    if (batteryLevel !== null) {
      fetch('/api/phone/telemetry', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          battery: batteryLevel,
          charging: isCharging,
          device: deviceModel
        })
      }).catch(() => {});
      return;
    }

    if (navigator.getBattery) {
      navigator.getBattery().then(b => {
        fetch('/api/phone/telemetry', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            battery: Math.round(b.level * 100),
            charging: b.charging,
            device: deviceModel
          })
        }).catch(() => {});
      }).catch(() => {
        fetch('/api/phone/telemetry', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            battery: null,
            charging: false,
            device: deviceModel
          })
        }).catch(() => {});
      });
    } else {
      fetch('/api/phone/telemetry', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          battery: null,
          charging: false,
          device: deviceModel
        })
      }).catch(() => {});
    }
  }
  setInterval(reportBatteryTelemetry, 15000);
  setTimeout(reportBatteryTelemetry, 1500);

  // Fallback Phone Control Poller (for transient reconnects)
  async function pollPendingPhoneCommands() {
    if (document.hidden) return;
    try {
      const res = await fetch(`/api/phone/control?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();
      if (data.status === 'ok' && Array.isArray(data.commands)) {
        data.commands.forEach(cmd => {
          handleRemotePhoneControl(cmd.action, cmd.param);
        });
      }
    } catch (e) {}
  }
  setInterval(pollPendingPhoneCommands, 4000);

  // ----------------------------------------------------
  // 4. File Hub & Interactive PC Directory Browser
  // ----------------------------------------------------
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const uploadProgContainer = document.getElementById('uploadProgress');
  const progressBar = document.getElementById('progressBarFill');
  const uploadStatusText = document.getElementById('uploadStatusText');
  const currentTargetPathDisplay = document.getElementById('currentTargetPathDisplay');
  const targetDirBadge = document.getElementById('targetDirBadge');
  const uploadDestHint = document.getElementById('uploadDestHint');
  const btnSetAsDefaultDir = document.getElementById('btnSetAsDefaultDir');
  const btnBookmarkCurrentDir = document.getElementById('btnBookmarkCurrentDir');
  const quickShortcutsBar = document.getElementById('quickShortcutsBar');
  const dirBreadcrumbs = document.getElementById('dirBreadcrumbs');
  const browserFoldersGrid = document.getElementById('browserFoldersGrid');
  const pcFilesList = document.getElementById('pcFilesList');
  const btnBrowseUp = document.getElementById('btnBrowseUp');
  const btnCreateNewFolder = document.getElementById('btnCreateNewFolder');
  const btnRefreshBrowser = document.getElementById('btnRefreshBrowser');

  let currentBrowsePath = '';
  let defaultSaveDir = '';
  let parentBrowsePath = null;

  async function loadDirectory(targetPath) {
    const url = `/api/files/browse?token=${encodeURIComponent(authToken)}` + 
                (targetPath ? `&path=${encodeURIComponent(targetPath)}` : '');
    try {
      const res = await fetch(url);
      const data = await res.json();
      if (data.status === 'ok') {
        currentBrowsePath = data.current_path;
        defaultSaveDir = data.default_save_dir;
        parentBrowsePath = data.parent_path;

        if (currentTargetPathDisplay) currentTargetPathDisplay.textContent = currentBrowsePath;
        if (uploadDestHint) uploadDestHint.textContent = `Saving to: ${currentBrowsePath.split('/').pop() || currentBrowsePath}`;

        // Badge & Make Default Button
        if (data.is_default) {
          if (targetDirBadge) {
            targetDirBadge.textContent = '⭐ Default Save Location';
            targetDirBadge.className = 'status-pill status-active';
          }
          if (btnSetAsDefaultDir) {
            btnSetAsDefaultDir.disabled = true;
            btnSetAsDefaultDir.textContent = '✓ Default Location';
            btnSetAsDefaultDir.classList.remove('highlight');
          }
        } else {
          if (targetDirBadge) {
            targetDirBadge.textContent = 'Active Folder';
            targetDirBadge.className = 'status-pill status-idle';
          }
          if (btnSetAsDefaultDir) {
            btnSetAsDefaultDir.disabled = false;
            btnSetAsDefaultDir.textContent = '⭐ Save as Default Location';
            btnSetAsDefaultDir.classList.add('highlight');
          }
        }

        // Render Quick Places
        renderQuickPlaces(data.quick_shortcuts || [], data.saved_places || []);

        // Render Breadcrumbs
        renderBreadcrumbs(currentBrowsePath);

        // Render Folders Grid
        renderFolders(data.folders || []);

        // Render Files List
        renderFiles(data.files || []);

        // Parent button state
        if (btnBrowseUp) btnBrowseUp.disabled = !parentBrowsePath;
      }
    } catch (e) {
      if (pcFilesList) pcFilesList.innerHTML = '<li class="file-item empty">Error loading folder contents</li>';
    }
  }

  function renderBreadcrumbs(path) {
    if (!dirBreadcrumbs) return;
    dirBreadcrumbs.innerHTML = '';
    const parts = path.split('/').filter(Boolean);
    
    // Root link
    const rootSpan = document.createElement('span');
    rootSpan.className = 'breadcrumb-crumb';
    rootSpan.textContent = '/';
    rootSpan.addEventListener('click', () => loadDirectory('/'));
    dirBreadcrumbs.appendChild(rootSpan);

    let accumulated = '';
    parts.forEach((p, idx) => {
      accumulated += '/' + p;
      const sep = document.createElement('span');
      sep.className = 'breadcrumb-sep';
      sep.textContent = ' › ';
      dirBreadcrumbs.appendChild(sep);

      const crumb = document.createElement('span');
      crumb.className = 'breadcrumb-crumb' + (idx === parts.length - 1 ? ' active' : '');
      crumb.textContent = p;
      const thisPath = accumulated;
      crumb.addEventListener('click', () => loadDirectory(thisPath));
      dirBreadcrumbs.appendChild(crumb);
    });
  }

  function renderQuickPlaces(shortcuts, bookmarks) {
    if (!quickShortcutsBar) return;
    quickShortcutsBar.innerHTML = '';

    shortcuts.forEach(s => {
      const chip = document.createElement('button');
      chip.className = 'quick-place-chip' + (s.path === currentBrowsePath ? ' active' : '');
      chip.innerHTML = `<span>${s.icon || '📁'}</span><span>${escapeHtml(s.name)}</span>`;
      chip.addEventListener('click', () => loadDirectory(s.path));
      quickShortcutsBar.appendChild(chip);
    });

    bookmarks.forEach(b => {
      if (shortcuts.some(s => s.path === b)) return;
      const name = b.split('/').pop() || b;
      const chip = document.createElement('button');
      chip.className = 'quick-place-chip' + (b === currentBrowsePath ? ' active' : '');
      chip.innerHTML = `<span>🔖</span><span>${escapeHtml(name)}</span>`;
      chip.title = b;
      chip.addEventListener('click', () => loadDirectory(b));
      quickShortcutsBar.appendChild(chip);
    });
  }

  function renderFolders(folders) {
    if (!browserFoldersGrid) return;
    browserFoldersGrid.innerHTML = '';
    if (folders.length === 0) {
      browserFoldersGrid.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:6px;">No subdirectories found</div>';
      return;
    }

    folders.forEach(f => {
      const btn = document.createElement('button');
      btn.className = 'folder-card-btn';
      btn.innerHTML = `<span class="folder-card-icon">📁</span><span class="folder-card-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>`;
      btn.addEventListener('click', () => loadDirectory(f.path));
      browserFoldersGrid.appendChild(btn);
    });
  }

  function renderFiles(files) {
    if (!pcFilesList) return;
    pcFilesList.innerHTML = '';
    if (files.length === 0) {
      pcFilesList.innerHTML = '<li class="file-item empty">No files in this folder</li>';
      return;
    }

    files.forEach(f => {
      const li = document.createElement('li');
      li.className = 'file-item';
      li.innerHTML = `
        <div class="file-info">
          <span class="file-name">${escapeHtml(f.name)}</span>
          <span class="file-meta">${f.size} • ${f.time}</span>
        </div>
        <a href="/api/download/${encodeURIComponent(f.name)}?token=${encodeURIComponent(authToken)}&dir=${encodeURIComponent(currentBrowsePath)}" class="btn-download" download>Download</a>
      `;
      pcFilesList.appendChild(li);
    });
  }

  // Set current folder as permanent default save location
  if (btnSetAsDefaultDir) {
    btnSetAsDefaultDir.addEventListener('click', async () => {
      if (!currentBrowsePath) return;
      try {
        const res = await fetch(`/api/files/browse?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'set_default', path: currentBrowsePath })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          showToast(`⭐ Saved as default save location!`);
          loadDirectory(currentBrowsePath);
        } else {
          showToast('Failed to save default location');
        }
      } catch (e) {
        showToast('Error saving default location');
      }
    });
  }

  // Bookmark folder
  if (btnBookmarkCurrentDir) {
    btnBookmarkCurrentDir.addEventListener('click', async () => {
      if (!currentBrowsePath) return;
      try {
        const res = await fetch(`/api/files/browse?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'save_place', path: currentBrowsePath })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          showToast(`🔖 Bookmarked to Quick Places!`);
          loadDirectory(currentBrowsePath);
        }
      } catch (e) {}
    });
  }

  if (btnBrowseUp) {
    btnBrowseUp.addEventListener('click', () => {
      if (parentBrowsePath) loadDirectory(parentBrowsePath);
    });
  }

  if (btnRefreshBrowser) {
    btnRefreshBrowser.addEventListener('click', () => loadDirectory(currentBrowsePath));
  }

  if (btnCreateNewFolder) {
    btnCreateNewFolder.addEventListener('click', async () => {
      const folderName = prompt('Enter new folder name:');
      if (!folderName || !folderName.trim()) return;
      try {
        const res = await fetch(`/api/files/browse?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'mkdir', parent: currentBrowsePath, name: folderName.trim() })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          showToast(`✓ Created folder: ${folderName}`);
          loadDirectory(currentBrowsePath);
        } else {
          showToast(data.message || 'Could not create folder');
        }
      } catch (e) {
        showToast('Error creating folder');
      }
    });
  }

  // Upload handler saving directly to currentBrowsePath
  function uploadFiles(files) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    if (currentBrowsePath) {
      formData.append('target_dir', currentBrowsePath);
    }

    if (uploadProgContainer) uploadProgContainer.style.display = 'block';
    if (progressBar) progressBar.style.width = '10%';
    if (uploadStatusText) uploadStatusText.textContent = 'Uploading to PC...';

    const xhr = new XMLHttpRequest();
    const targetUrl = `/api/upload?token=${encodeURIComponent(authToken)}` + 
                     (currentBrowsePath ? `&target_dir=${encodeURIComponent(currentBrowsePath)}` : '');
    xhr.open('POST', targetUrl, true);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && progressBar) {
        const pct = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = `${pct}%`;
        if (uploadStatusText) uploadStatusText.textContent = `Uploading ${pct}%`;
      }
    };

    xhr.onload = () => {
      if (uploadProgContainer) uploadProgContainer.style.display = 'none';
      if (progressBar) progressBar.style.width = '0%';
      if (xhr.status === 200) {
        const folderName = currentBrowsePath.split('/').pop() || currentBrowsePath;
        showToast(`✓ File(s) saved to ${folderName}`);
        loadDirectory(currentBrowsePath);
      } else {
        showToast('Upload failed');
      }
      if (fileInput) fileInput.value = '';
    };

    xhr.onerror = () => {
      if (uploadProgContainer) uploadProgContainer.style.display = 'none';
      showToast('Network error during upload');
    };

    xhr.send(formData);
  }

  if (dropZone && fileInput) {
    dropZone.addEventListener('click', () => fileInput.click());
  }

  if (dropZone) {
    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
      dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      if (e.dataTransfer.files.length) {
        uploadFiles(e.dataTransfer.files);
      }
    });
  }

  if (fileInput) {
    fileInput.addEventListener('change', () => {
      if (fileInput.files.length) {
        uploadFiles(fileInput.files);
      }
    });
  }

  // ----------------------------------------------------
  // 5. Quick App Actions
  // ----------------------------------------------------
  document.querySelectorAll('.action-card[data-app]').forEach(btn => {
    btn.addEventListener('click', () => {
      const app = btn.getAttribute('data-app');
      fetch(`/api/app/launch?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app })
      })
      .then(res => res.json())
      .then(res => {
        showToast(res.message || 'App launched');
      })
      .catch(() => showToast('Launch failed'));
    });
  });

  // ----------------------------------------------------
  // 6. Tailscale Mesh Control & SSH Info
  // ----------------------------------------------------
  const tailscaleToggle = document.getElementById('tailscaleToggle');
  const tailscaleStatusBadge = document.getElementById('tailscaleStatusBadge');
  const tailscaleToggleHint = document.getElementById('tailscaleToggleHint');
  const remoteTailscaleIp = document.getElementById('remoteTailscaleIp');
  const remoteSshCmd = document.getElementById('remoteSshCmd');
  const btnCopyTailscaleUrl = document.getElementById('btnCopyTailscaleUrl');
  const btnCopySshCmd = document.getElementById('btnCopySshCmd');
  const btnRefreshTunnelStatus = document.getElementById('btnRefreshTunnelStatus');
  let currentTailscaleIp = '';
  let currentSshCmd = '';
  let isTogglingTailscale = false;

  async function loadTunnelStatus() {
    try {
      const res = await fetch(`/api/tunnel?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();
      if (data.status === 'ok') {
        const isRunning = !!data.tailscale_running;
        currentTailscaleIp = data.tailscale_ip || '';

        if (tailscaleToggle && !isTogglingTailscale) {
          tailscaleToggle.checked = isRunning;
        }

        if (isRunning) {
          if (tailscaleStatusBadge) {
            tailscaleStatusBadge.textContent = 'Active';
            tailscaleStatusBadge.className = 'status-pill status-active';
          }
          if (tailscaleToggleHint) {
            tailscaleToggleHint.textContent = 'Connected to Tailscale Mesh';
          }
          if (remoteTailscaleIp) {
            remoteTailscaleIp.textContent = `${data.tailscale_ip} (Active)`;
            remoteTailscaleIp.style.color = '#34c759';
          }
          if (btnCopyTailscaleUrl) btnCopyTailscaleUrl.style.display = 'inline-block';
        } else {
          if (tailscaleStatusBadge) {
            tailscaleStatusBadge.textContent = 'Stopped / Off';
            tailscaleStatusBadge.className = 'status-pill status-idle';
          }
          if (tailscaleToggleHint) {
            tailscaleToggleHint.textContent = 'Tailscale is turned off';
          }
          if (remoteTailscaleIp) {
            remoteTailscaleIp.textContent = 'Inactive / Not Connected';
            remoteTailscaleIp.style.color = 'var(--text-muted)';
          }
          if (btnCopyTailscaleUrl) btnCopyTailscaleUrl.style.display = 'none';
        }

        if (data.ssh) {
          currentSshCmd = data.ssh.cmd_tailscale || (data.local_ip ? `ssh ${data.ssh.user}@${data.local_ip}` : 'ssh unavailable');
          if (remoteSshCmd) remoteSshCmd.textContent = currentSshCmd;
        }
      }
    } catch (e) {}
  }

  if (tailscaleToggle) {
    tailscaleToggle.addEventListener('change', async () => {
      if (isTogglingTailscale) return;
      isTogglingTailscale = true;
      const wantEnable = tailscaleToggle.checked;

      if (tailscaleStatusBadge) {
        tailscaleStatusBadge.textContent = wantEnable ? 'Starting...' : 'Stopping...';
        tailscaleStatusBadge.className = 'status-pill status-idle';
      }

      try {
        const res = await fetch(`/api/tailscale/toggle?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enable: wantEnable })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          showToast(wantEnable ? '✓ Tailscale Connected' : '✓ Tailscale Stopped');
        } else {
          tailscaleToggle.checked = !wantEnable;
          if (data.code === 'OPERATOR_REQUIRED') {
            showToast('⚠️ Permission required on PC', 4000);
            alert("Tailscale Operator Permission Required:\n\nTo toggle Tailscale on/off without entering your root password, run this command once in your Linux PC terminal:\n\nsudo tailscale set --operator=$USER");
          } else {
            showToast(data.message || 'Tailscale toggle failed');
          }
        }
      } catch (e) {
        tailscaleToggle.checked = !wantEnable;
        showToast('Error communicating with Tailscale service');
      } finally {
        isTogglingTailscale = false;
        loadTunnelStatus();
      }
    });
  }

  if (btnCopyTailscaleUrl) {
    btnCopyTailscaleUrl.addEventListener('click', () => {
      if (currentTailscaleIp) {
        const port = window.location.port || '8080';
        const url = `http://${currentTailscaleIp}:${port}/?token=${authToken}`;
        navigator.clipboard.writeText(url);
        showToast(`✓ Tailscale Link Copied!`);
      } else {
        showToast('Tailscale is not active on this PC');
      }
    });
  }

  if (btnCopySshCmd) {
    btnCopySshCmd.addEventListener('click', () => {
      if (currentSshCmd) {
        navigator.clipboard.writeText(currentSshCmd);
        showToast('✓ SSH Command Copied!');
      }
    });
  }

  if (btnRefreshTunnelStatus) {
    btnRefreshTunnelStatus.addEventListener('click', () => {
      loadTunnelStatus();
      showToast('🔄 Tailscale status refreshed');
    });
  }

  // ----------------------------------------------------
  // PWA Service Worker Registration
  // ----------------------------------------------------
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  // ----------------------------------------------------
  // Media & Volume Controller
  // ----------------------------------------------------
  let mediaPollInterval = null;
  const mediaPlayerName = document.getElementById('mediaPlayerName');
  const mediaTitle = document.getElementById('mediaTitle');
  const mediaArtist = document.getElementById('mediaArtist');
  const mediaAlbum = document.getElementById('mediaAlbum');
  const mediaStatusBadge = document.getElementById('mediaStatusBadge');
  const mediaArtImg = document.getElementById('mediaArtImg');
  const mediaArtPlaceholder = document.getElementById('mediaArtPlaceholder');
  const volumeSlider = document.getElementById('volumeSlider');
  const volPercentBadge = document.getElementById('volPercentBadge');
  const btnToggleMute = document.getElementById('btnToggleMute');

  async function loadMediaStatus() {
    try {
      const res = await fetch(`/api/media/status?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();

      // Volume info
      if (data.volume) {
        if (volumeSlider && document.activeElement !== volumeSlider) {
          volumeSlider.value = data.volume.volume;
        }
        if (volPercentBadge) {
          volPercentBadge.textContent = `${data.volume.volume}%`;
        }
        if (btnToggleMute) {
          btnToggleMute.textContent = data.volume.is_muted ? '🔇' : '🔊';
        }
      }

      // Media info
      const active = data.media?.active;
      if (active) {
        if (mediaPlayerName) mediaPlayerName.textContent = active.name || 'Player';
        if (mediaTitle) mediaTitle.textContent = active.title || 'Unknown Title';
        if (mediaArtist) mediaArtist.textContent = active.artist || 'Unknown Artist';
        if (mediaAlbum) mediaAlbum.textContent = active.album || '';

        const st = (active.status || 'idle').toLowerCase();
        if (mediaStatusBadge) {
          mediaStatusBadge.textContent = st;
          mediaStatusBadge.className = `status-pill status-${st}`;
        }

        if (active.art_url && active.art_url.startsWith('http')) {
          if (mediaArtImg) {
            mediaArtImg.src = active.art_url;
            mediaArtImg.style.display = 'block';
          }
          if (mediaArtPlaceholder) mediaArtPlaceholder.style.display = 'none';
        } else {
          if (mediaArtImg) mediaArtImg.style.display = 'none';
          if (mediaArtPlaceholder) mediaArtPlaceholder.style.display = 'block';
        }
      } else {
        if (mediaPlayerName) mediaPlayerName.textContent = 'No Player';
        if (mediaTitle) mediaTitle.textContent = 'No media active';
        if (mediaArtist) mediaArtist.textContent = 'Launch Spotify, VLC, YouTube or Firefox';
        if (mediaAlbum) mediaAlbum.textContent = '';
        if (mediaStatusBadge) {
          mediaStatusBadge.textContent = 'Idle';
          mediaStatusBadge.className = 'status-pill status-idle';
        }
        if (mediaArtImg) mediaArtImg.style.display = 'none';
        if (mediaArtPlaceholder) mediaArtPlaceholder.style.display = 'block';
      }
    } catch (e) {}
  }

  function startMediaLoop() {
    stopMediaLoop();
    mediaPollInterval = setInterval(loadMediaStatus, 2500);
  }

  function stopMediaLoop() {
    if (mediaPollInterval) {
      clearInterval(mediaPollInterval);
      mediaPollInterval = null;
    }
  }

  async function sendMediaAction(action) {
    try {
      await fetch(`/api/media/control?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      setTimeout(loadMediaStatus, 300);
    } catch (e) {
      showToast('Media action failed');
    }
  }

  const btnMediaPlayPause = document.getElementById('btnMediaPlayPause');
  const btnMediaNext = document.getElementById('btnMediaNext');
  const btnMediaPrev = document.getElementById('btnMediaPrev');
  const btnMediaStop = document.getElementById('btnMediaStop');

  if (btnMediaPlayPause) btnMediaPlayPause.addEventListener('click', () => sendMediaAction('PlayPause'));
  if (btnMediaNext) btnMediaNext.addEventListener('click', () => sendMediaAction('Next'));
  if (btnMediaPrev) btnMediaPrev.addEventListener('click', () => sendMediaAction('Previous'));
  if (btnMediaStop) btnMediaStop.addEventListener('click', () => sendMediaAction('Stop'));

  let volDebounce = null;
  if (volumeSlider) {
    volumeSlider.addEventListener('input', () => {
      const val = parseInt(volumeSlider.value);
      if (volPercentBadge) volPercentBadge.textContent = `${val}%`;
      if (volDebounce) clearTimeout(volDebounce);
      volDebounce = setTimeout(async () => {
        await fetch(`/api/media/control?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'set_volume', volume: val })
        });
      }, 100);
    });
  }

  if (btnToggleMute) {
    btnToggleMute.addEventListener('click', async () => {
      await fetch(`/api/media/control?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'toggle_mute' })
      });
      loadMediaStatus();
    });
  }

  document.querySelectorAll('.btn-chip[data-vol]').forEach(chip => {
    chip.addEventListener('click', async () => {
      const val = parseInt(chip.getAttribute('data-vol'));
      if (volumeSlider) volumeSlider.value = val;
      if (volPercentBadge) volPercentBadge.textContent = `${val}%`;
      await fetch(`/api/media/control?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'set_volume', volume: val })
      });
      loadMediaStatus();
    });
  });

  // ----------------------------------------------------
  // System Vitals Monitor
  // ----------------------------------------------------
  let vitalsPollInterval = null;
  const vitalsUptime = document.getElementById('vitalsUptime');
  const btnRefreshVitals = document.getElementById('btnRefreshVitals');

  async function loadSystemStats() {
    try {
      const res = await fetch(`/api/system/stats?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();
      if (!data.cpu) return;

      if (vitalsUptime) vitalsUptime.textContent = `Uptime: ${data.uptime || '--'}`;

      const cpuVal = document.getElementById('vitalCpuVal');
      const cpuBar = document.getElementById('vitalCpuBar');
      const cpuCores = document.getElementById('vitalCpuCores');
      const cpuFreq = document.getElementById('vitalCpuFreq');
      if (cpuVal) cpuVal.textContent = `${data.cpu.percent}%`;
      if (cpuBar) cpuBar.style.width = `${Math.min(100, data.cpu.percent)}%`;
      if (cpuCores) cpuCores.textContent = `${data.cpu.cores} Cores`;
      if (cpuFreq) cpuFreq.textContent = `${data.cpu.freq_mhz || '--'} MHz`;

      const ramVal = document.getElementById('vitalRamVal');
      const ramBar = document.getElementById('vitalRamBar');
      const ramDetail = document.getElementById('vitalRamDetail');
      if (ramVal) ramVal.textContent = `${data.memory.percent}%`;
      if (ramBar) ramBar.style.width = `${Math.min(100, data.memory.percent)}%`;
      if (ramDetail) ramDetail.textContent = `${data.memory.used_mb} / ${data.memory.total_mb} MB`;

      const diskVal = document.getElementById('vitalDiskVal');
      const diskBar = document.getElementById('vitalDiskBar');
      const diskDetail = document.getElementById('vitalDiskDetail');
      if (diskVal) diskVal.textContent = `${data.disk.percent}%`;
      if (diskBar) diskBar.style.width = `${Math.min(100, data.disk.percent)}%`;
      if (diskDetail) diskDetail.textContent = `${data.disk.used_gb} / ${data.disk.total_gb} GB`;

      const tempCpu = document.getElementById('vitalTempCpu');
      const tempGpu = document.getElementById('vitalTempGpu');
      const tempBar = document.getElementById('vitalTempBar');
      const cVal = data.cpu.temp_c || data.temps?.cpu || '--';
      if (tempCpu) tempCpu.textContent = `${cVal}°C`;
      if (tempGpu) tempGpu.textContent = `GPU: ${data.temps?.gpu || '--'}°C`;
      if (tempBar && typeof cVal === 'number') {
        tempBar.style.width = `${Math.min(100, (cVal / 100) * 100)}%`;
      }

      const battVal = document.getElementById('vitalBattVal');
      const battBar = document.getElementById('vitalBattBar');
      const battStatus = document.getElementById('vitalBattStatus');
      if (data.battery?.has_battery) {
        if (battVal) battVal.textContent = `${data.battery.percent}%`;
        if (battBar) battBar.style.width = `${data.battery.percent}%`;
        if (battStatus) battStatus.textContent = data.battery.plugged ? '⚡ Charging / Plugged' : '🔋 On Battery';
      }
    } catch (e) {}
  }

  function startVitalsLoop() {
    stopVitalsLoop();
    vitalsPollInterval = setInterval(loadSystemStats, 2500);
  }

  function stopVitalsLoop() {
    if (vitalsPollInterval) {
      clearInterval(vitalsPollInterval);
      vitalsPollInterval = null;
    }
  }

  if (btnRefreshVitals) btnRefreshVitals.addEventListener('click', loadSystemStats);

  // ----------------------------------------------------
  // 1-Click App Launcher & Power Actions
  // ----------------------------------------------------
  document.querySelectorAll('[data-app]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const appName = btn.getAttribute('data-app');
      try {
        const res = await fetch(`/api/app/launch?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ app: appName })
        });
        const data = await res.json();
        showToast(data.message || `Launched ${appName}`);
      } catch (e) {
        showToast('App launch failed');
      }
    });
  });

  document.querySelectorAll('[data-power]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const action = btn.getAttribute('data-power');
      if (action === 'reboot' && !confirm('Are you sure you want to REBOOT your Linux PC?')) return;
      if (action === 'poweroff' && !confirm('Are you sure you want to SHUT DOWN your Linux PC?')) return;

      try {
        const res = await fetch(`/api/power?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action })
        });
        const data = await res.json();
        showToast(data.message || `Executed ${action}`);
      } catch (e) {
        showToast('Power action failed');
      }
    });
  });

  // Push Desktop Notification
  const btnSendNotif = document.getElementById('btnSendNotification');
  const notifTitleInput = document.getElementById('notifTitleInput');
  const notifMsgInput = document.getElementById('notifMsgInput');

  if (btnSendNotif) {
    btnSendNotif.addEventListener('click', async () => {
      const title = notifTitleInput ? notifTitleInput.value.trim() : '';
      const message = notifMsgInput ? notifMsgInput.value.trim() : '';
      if (!title && !message) {
        showToast('Please enter a title or message');
        return;
      }
      try {
        await fetch(`/api/notification?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, message })
        });
        showToast('✓ Notification pushed to PC!');
        if (notifTitleInput) notifTitleInput.value = '';
        if (notifMsgInput) notifMsgInput.value = '';
      } catch (e) {
        showToast('Failed to send notification');
      }
    });
  }

  // ----------------------------------------------------
  // Camera Preview & Live Microphone Stream
  // ----------------------------------------------------
  const camImg = document.getElementById('camImg');
  const camOverlayText = document.getElementById('camOverlayText');
  const camStatusBadge = document.getElementById('camStatusBadge');
  const btnToggleCamStream = document.getElementById('btnToggleCamStream');
  const btnCamSnapshot = document.getElementById('btnCamSnapshot');
  const btnOpenPcCamApp = document.getElementById('btnOpenPcCamApp');

  const btnToggleMicListen = document.getElementById('btnToggleMicListen');
  const micAudioPlayer = document.getElementById('micAudioPlayer');
  const micStatusText = document.getElementById('micStatusText');
  const micWaveform = document.getElementById('micWaveform');

  let camStreamTimer = null;
  let isListeningMic = false;

  function fetchCameraSnapshot() {
    if (!camImg) return;
    const img = new Image();
    const ts = Date.now();
    img.src = `/api/camera/frame?token=${encodeURIComponent(authToken)}&t=${ts}&w=640&h=360`;
    img.onload = () => {
      camImg.src = img.src;
      if (camOverlayText) camOverlayText.textContent = `Live • ${new Date().toLocaleTimeString()}`;
      if (camStatusBadge) {
        camStatusBadge.textContent = 'Active';
        camStatusBadge.className = 'status-pill status-active';
      }
    };
    img.onerror = () => {
      if (camOverlayText) camOverlayText.textContent = 'Webcam unavailable or in use';
    };
  }

  function toggleCameraStream() {
    if (camStreamTimer) {
      clearInterval(camStreamTimer);
      camStreamTimer = null;
      if (btnToggleCamStream) btnToggleCamStream.textContent = '▶ Start Live Camera';
      if (camStatusBadge) {
        camStatusBadge.textContent = 'Paused';
        camStatusBadge.className = 'status-pill status-idle';
      }
    } else {
      fetchCameraSnapshot();
      camStreamTimer = setInterval(fetchCameraSnapshot, 1500);
      if (btnToggleCamStream) btnToggleCamStream.textContent = '⏸ Pause Live Camera';
    }
  }

  if (btnToggleCamStream) btnToggleCamStream.addEventListener('click', toggleCameraStream);

  if (btnCamSnapshot) {
    btnCamSnapshot.addEventListener('click', () => {
      fetchCameraSnapshot();
      showToast('📸 Photo captured from PC webcam!');
    });
  }

  if (btnOpenPcCamApp) {
    btnOpenPcCamApp.addEventListener('click', async () => {
      try {
        const res = await fetch(`/api/app/launch?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ app: 'camera' })
        });
        const data = await res.json();
        showToast(data.message || 'Opened camera on PC');
      } catch (e) {
        showToast('Could not open camera on PC');
      }
    });
  }

  function toggleMicListen() {
    if (!isListeningMic) {
      isListeningMic = true;
      if (btnToggleMicListen) {
        btnToggleMicListen.textContent = '⏹ Stop Listening';
        btnToggleMicListen.style.backgroundColor = '#ff3b30';
      }
      if (micStatusText) micStatusText.textContent = '🔴 Listening live to PC microphone...';
      if (micWaveform) micWaveform.style.display = 'flex';

      if (micAudioPlayer) {
        micAudioPlayer.src = `/api/mic/stream?token=${encodeURIComponent(authToken)}&t=${Date.now()}`;
        micAudioPlayer.play().catch(e => {
          console.warn('Audio autoplay prevented:', e);
          showToast('Tap again to enable audio playback');
        });
      }
      showToast('🎙️ Streaming PC microphone audio');
    } else {
      isListeningMic = false;
      if (btnToggleMicListen) {
        btnToggleMicListen.textContent = '🎧 Listen to PC Mic';
        btnToggleMicListen.style.backgroundColor = '';
      }
      if (micStatusText) micStatusText.textContent = 'Microphone monitor disconnected';
      if (micWaveform) micWaveform.style.display = 'none';

      if (micAudioPlayer) {
        micAudioPlayer.pause();
        micAudioPlayer.src = '';
      }
      showToast('Microphone stream stopped');
    }
  }

  if (btnToggleMicListen) btnToggleMicListen.addEventListener('click', toggleMicListen);

  // ----------------------------------------------------
  // Remote Trackpad & Mouse with Sensitivity Slider
  // ----------------------------------------------------
  const trackpadSurface = document.getElementById('trackpadSurface');
  const trackpadPointer = document.getElementById('trackpadPointer');
  const trackpadStatus = document.getElementById('trackpadStatus');
  const trackpadSensSlider = document.getElementById('trackpadSensSlider');
  const trackpadSensBadge = document.getElementById('trackpadSensBadge');

  const btnTpLeft = document.getElementById('btnTpLeft');
  const btnTpMiddle = document.getElementById('btnTpMiddle');
  const btnTpRight = document.getElementById('btnTpRight');
  const btnTpDrag = document.getElementById('btnTpDrag');

  const btnTpScrollUp = document.getElementById('btnTpScrollUp');
  const btnTpScrollDown = document.getElementById('btnTpScrollDown');

  const btnToggleTrackpadViewfinder = document.getElementById('btnToggleTrackpadViewfinder');
  const trackpadViewfinderBox = document.getElementById('trackpadViewfinderBox');
  const trackpadScreenImg = document.getElementById('trackpadScreenImg');
  const btnRefreshTrackpadScreen = document.getElementById('btnRefreshTrackpadScreen');

  let trackpadSens = parseFloat(localStorage.getItem('continuity_trackpad_sens') || '1.2');
  if (isNaN(trackpadSens) || trackpadSens < 0.2 || trackpadSens > 4.0) trackpadSens = 1.2;

  function updateSensLabel(val) {
    if (trackpadSensBadge) {
      let speedDesc = 'Normal';
      if (val <= 0.6) speedDesc = 'Precision';
      else if (val <= 0.9) speedDesc = 'Smooth';
      else if (val <= 1.4) speedDesc = 'Normal';
      else if (val <= 2.2) speedDesc = 'Fast';
      else speedDesc = 'Hyper';
      trackpadSensBadge.textContent = `${val.toFixed(1)}x (${speedDesc})`;
    }
  }

  if (trackpadSensSlider) {
    trackpadSensSlider.value = trackpadSens;
    updateSensLabel(trackpadSens);
    trackpadSensSlider.addEventListener('input', () => {
      trackpadSens = parseFloat(trackpadSensSlider.value);
      updateSensLabel(trackpadSens);
      localStorage.setItem('continuity_trackpad_sens', trackpadSens.toString());
    });
  }

  async function sendTrackpadEvent(payload) {
    try {
      await fetch(`/api/trackpad?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } catch (e) {
      // Ignore transient network hiccups
    }
  }

  // Drag state
  let isDragging = false;
  if (btnTpDrag) {
    btnTpDrag.addEventListener('click', () => {
      isDragging = !isDragging;
      if (isDragging) {
        btnTpDrag.textContent = '🔓 Release Drag';
        btnTpDrag.style.backgroundColor = '#ff9f0a';
        btnTpDrag.style.borderColor = '#ffb340';
        if (trackpadStatus) {
          trackpadStatus.textContent = 'Dragging';
          trackpadStatus.style.color = '#ff9f0a';
        }
        sendTrackpadEvent({ type: 'mousedown', button: '1' });
        showToast('Left Click Locked (Drag Active)');
      } else {
        btnTpDrag.textContent = '🔒 Drag & Hold';
        btnTpDrag.style.backgroundColor = '';
        btnTpDrag.style.borderColor = '';
        if (trackpadStatus) {
          trackpadStatus.textContent = 'Ready';
          trackpadStatus.style.color = '';
        }
        sendTrackpadEvent({ type: 'mouseup', button: '1' });
        showToast('Drag Released');
      }
    });
  }

  if (btnTpLeft) {
    btnTpLeft.addEventListener('click', () => {
      sendTrackpadEvent({ type: 'click', button: '1' });
    });
  }
  if (btnTpMiddle) {
    btnTpMiddle.addEventListener('click', () => {
      sendTrackpadEvent({ type: 'click', button: '2' });
    });
  }
  if (btnTpRight) {
    btnTpRight.addEventListener('click', () => {
      sendTrackpadEvent({ type: 'click', button: '3' });
    });
  }

  if (btnTpScrollUp) {
    btnTpScrollUp.addEventListener('click', () => {
      sendTrackpadEvent({ type: 'scroll', direction: 'up', steps: 4 });
    });
  }
  if (btnTpScrollDown) {
    btnTpScrollDown.addEventListener('click', () => {
      sendTrackpadEvent({ type: 'scroll', direction: 'down', steps: 4 });
    });
  }

  // Quick Keys on trackpad tab
  document.querySelectorAll('.tp-key').forEach(btn => {
    btn.addEventListener('click', async () => {
      const key = btn.getAttribute('data-tpkey');
      if (!key) return;
      try {
        await fetch(`/api/screen/key?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key })
        });
      } catch (e) {}
    });
  });

  // Touch handling on the trackpad surface
  if (trackpadSurface) {
    let lastX = 0;
    let lastY = 0;
    let touchStartTime = 0;
    let totalMoved = 0;
    let lastTapTime = 0;
    let moveTimer = null;
    let pendingDx = 0;
    let pendingDy = 0;

    function flushMove() {
      if (Math.abs(pendingDx) >= 0.5 || Math.abs(pendingDy) >= 0.5) {
        const dxToSend = Math.round(pendingDx);
        const dyToSend = Math.round(pendingDy);
        pendingDx -= dxToSend;
        pendingDy -= dyToSend;
        if (dxToSend !== 0 || dyToSend !== 0) {
          sendTrackpadEvent({ type: 'move', dx: dxToSend, dy: dyToSend });
        }
      }
      moveTimer = null;
    }

    trackpadSurface.addEventListener('touchstart', (e) => {
      e.preventDefault();
      if (e.touches.length === 1) {
        const touch = e.touches[0];
        lastX = touch.clientX;
        lastY = touch.clientY;
        touchStartTime = Date.now();
        totalMoved = 0;

        if (trackpadPointer) {
          const rect = trackpadSurface.getBoundingClientRect();
          trackpadPointer.style.left = `${touch.clientX - rect.left}px`;
          trackpadPointer.style.top = `${touch.clientY - rect.top}px`;
          trackpadPointer.style.display = 'block';
        }
      } else if (e.touches.length === 2) {
        // 2-finger gesture start
        lastY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        touchStartTime = Date.now();
        totalMoved = 0;
      }
    }, { passive: false });

    trackpadSurface.addEventListener('touchmove', (e) => {
      e.preventDefault();
      if (e.touches.length === 1) {
        const touch = e.touches[0];
        const rawDx = touch.clientX - lastX;
        const rawDy = touch.clientY - lastY;
        lastX = touch.clientX;
        lastY = touch.clientY;

        const scaledDx = rawDx * trackpadSens;
        const scaledDy = rawDy * trackpadSens;
        totalMoved += Math.hypot(rawDx, rawDy);

        pendingDx += scaledDx;
        pendingDy += scaledDy;

        if (trackpadPointer) {
          const rect = trackpadSurface.getBoundingClientRect();
          trackpadPointer.style.left = `${touch.clientX - rect.left}px`;
          trackpadPointer.style.top = `${touch.clientY - rect.top}px`;
        }

        if (!moveTimer) {
          moveTimer = setTimeout(flushMove, 16);
        }
      } else if (e.touches.length === 2) {
        // 2-finger scroll
        const curY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        const deltaY = curY - lastY;
        lastY = curY;
        totalMoved += Math.abs(deltaY);

        if (Math.abs(deltaY) > 8) {
          const dir = deltaY > 0 ? 'up' : 'down';
          sendTrackpadEvent({ type: 'scroll', direction: dir, steps: 2 });
        }
      }
    }, { passive: false });

    trackpadSurface.addEventListener('touchend', (e) => {
      e.preventDefault();
      if (moveTimer) {
        clearTimeout(moveTimer);
        flushMove();
      }
      if (trackpadPointer) trackpadPointer.style.display = 'none';

      const touchDuration = Date.now() - touchStartTime;

      if (e.changedTouches.length === 1 && totalMoved < 10 && touchDuration < 300) {
        const now = Date.now();
        if (now - lastTapTime < 320) {
          // Double tap -> double click
          sendTrackpadEvent({ type: 'click', button: 'double' });
          lastTapTime = 0;
        } else {
          lastTapTime = now;
          setTimeout(() => {
            if (lastTapTime === now) {
              sendTrackpadEvent({ type: 'click', button: '1' });
            }
          }, 320);
        }
      } else if (e.changedTouches.length === 2 && totalMoved < 12 && touchDuration < 350) {
        // 2-finger tap -> right click
        sendTrackpadEvent({ type: 'click', button: '3' });
      }
    }, { passive: false });

    trackpadSurface.addEventListener('touchcancel', () => {
      if (moveTimer) clearTimeout(moveTimer);
      if (trackpadPointer) trackpadPointer.style.display = 'none';
    });
  }

  // Viewfinder live desktop snapshot in trackpad tab
  async function refreshTrackpadViewfinder() {
    if (!trackpadScreenImg) return;
    try {
      const res = await fetch(`/api/screen?w=800&q=50&token=${encodeURIComponent(authToken)}&t=${Date.now()}`);
      if (res.ok) {
        const blob = await res.blob();
        trackpadScreenImg.src = URL.createObjectURL(blob);
      }
    } catch (e) {}
  }

  if (btnToggleTrackpadViewfinder && trackpadViewfinderBox) {
    btnToggleTrackpadViewfinder.addEventListener('click', () => {
      const isHidden = trackpadViewfinderBox.style.display === 'none';
      trackpadViewfinderBox.style.display = isHidden ? 'block' : 'none';
      btnToggleTrackpadViewfinder.textContent = isHidden ? '🙈 Hide PC Desktop Viewfinder' : '📸 Show / Hide PC Desktop Viewfinder';
      if (isHidden) refreshTrackpadViewfinder();
    });
  }

  if (btnRefreshTrackpadScreen) {
    btnRefreshTrackpadScreen.addEventListener('click', refreshTrackpadViewfinder);
  }

  if (trackpadScreenImg) {
    trackpadScreenImg.addEventListener('click', (e) => {
      const rect = trackpadScreenImg.getBoundingClientRect();
      const normX = (e.clientX - rect.left) / rect.width;
      const normY = (e.clientY - rect.top) / rect.height;
      if (normX >= 0 && normX <= 1 && normY >= 0 && normY <= 1) {
        sendTrackpadEvent({ type: 'click', button: '1', norm_x: normX, norm_y: normY });
        showToast('Clicked PC Screen');
        setTimeout(refreshTrackpadViewfinder, 300);
      }
    });
  }

  // Initialization
  function initAppConnections() {
    loadDesktopWindows();
    startDesktopTermLoop();
    loadSessions();
    connectTerminal(currentSession);
    connectClipboard();
    loadTunnelStatus();
    loadDirectory();
  }

  // Load Host Info & Validate stored token on startup
  fetch('/api/info')
    .then(r => r.json())
    .then(async data => {
      if (data.hostname) document.getElementById('sysHost').textContent = data.hostname;
      if (data.ip) document.getElementById('sysIp').textContent = data.ip;

      if (data.require_pin) {
        if (!authToken) {
          // No stored token → show PIN modal immediately
          setStatus(false, 'PIN Required');
          showPinModal();
          return;
        }
        // Validate the stored token (may be stale if server restarted)
        try {
          const authProbe = await fetch(`/api/system/stats?token=${encodeURIComponent(authToken)}`);
          if (!authProbe.ok) {
            // Stale/invalid token - clear and ask for PIN again
            localStorage.removeItem('continuity_token');
            authToken = '';
            setStatus(false, 'Session Expired');
            showPinModal();
            return;
          }
          // Token still valid → connect normally
          initAppConnections();
        } catch (e) {
          // Network error → try connecting anyway
          initAppConnections();
        }
      } else {
        // PIN not required → connect immediately
        initAppConnections();
      }
    })
    .catch(() => {
      initAppConnections();
    });

  function escapeHtml(str) {
    return str.replace(/[&<>'"]/g, 
      tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
  }
});
