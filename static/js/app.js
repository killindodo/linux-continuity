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

  // Tab Switching
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
        if (target === 'terminal' && window.fitAddon) {
          stopScreenLoop();
          if (typeof stopMediaLoop === 'function') stopMediaLoop();
          if (typeof stopVitalsLoop === 'function') stopVitalsLoop();
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
        } else if (target === 'screen') {
          if (typeof stopMediaLoop === 'function') stopMediaLoop();
          if (typeof stopVitalsLoop === 'function') stopVitalsLoop();
          if (typeof activeScreenSubmode === 'undefined' || activeScreenSubmode === 'mirror') {
            startScreenLoop();
            refreshScreenFrame();
          }
        } else if (target === 'media') {
          stopScreenLoop();
          if (typeof stopVitalsLoop === 'function') stopVitalsLoop();
          if (typeof loadMediaStatus === 'function') loadMediaStatus();
          if (typeof startMediaLoop === 'function') startMediaLoop();
        } else if (target === 'vitals') {
          stopScreenLoop();
          if (typeof stopMediaLoop === 'function') stopMediaLoop();
          if (typeof loadSystemStats === 'function') loadSystemStats();
          if (typeof startVitalsLoop === 'function') startVitalsLoop();
        } else {
          stopScreenLoop();
          if (typeof stopMediaLoop === 'function') stopMediaLoop();
          if (typeof stopVitalsLoop === 'function') stopVitalsLoop();
          if (target === 'files') {
            loadFiles();
          }
        }
      }
    });
  });

  // ----------------------------------------------------
  // 1. Terminal Setup (xterm.js + Shared Tmux Sessions)
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

  // ----------------------------------------------------
  // 2. Live Desktop Screen Mirror & Remote Control
  // ----------------------------------------------------
  const screenImg = document.getElementById('screenImg');
  const screenCanvasBox = document.getElementById('screenCanvasBox');
  const screenRipple = document.getElementById('screenRipple');
  const screenRefreshRate = document.getElementById('screenRefreshRate');
  const btnScreenManualRefresh = document.getElementById('btnScreenManualRefresh');
  const screenTextInput = document.getElementById('screenTextInput');
  const btnScreenSendText = document.getElementById('btnScreenSendText');

  let screenLoopTimer = null;
  let currentClickButton = '1'; // '1', '3', or 'double'
  let isFetchingFrame = false;

  function refreshScreenFrame() {
    if (isFetchingFrame) return;
    isFetchingFrame = true;

    const img = new Image();
    const ts = Date.now();
    img.src = `/api/screen?token=${encodeURIComponent(authToken)}&t=${ts}&w=960&q=55`;

    img.onload = () => {
      screenImg.src = img.src;
      isFetchingFrame = false;
    };

    img.onerror = () => {
      isFetchingFrame = false;
    };
  }

  function startScreenLoop() {
    stopScreenLoop();
    const rate = parseInt(screenRefreshRate.value, 10);
    if (rate > 0) {
      screenLoopTimer = setInterval(refreshScreenFrame, rate);
    }
  }

  function stopScreenLoop() {
    if (screenLoopTimer) {
      clearInterval(screenLoopTimer);
      screenLoopTimer = null;
    }
  }

  if (screenRefreshRate) {
    screenRefreshRate.addEventListener('change', () => {
      const pane = document.getElementById('tab-screen');
      if (pane && pane.classList.contains('active')) {
        startScreenLoop();
      }
    });
  }

  if (btnScreenManualRefresh) {
    btnScreenManualRefresh.addEventListener('click', () => {
      refreshScreenFrame();
    });
  }

  // Click Mode Selection
  const clickModeBtns = document.querySelectorAll('.click-mode-btn');
  clickModeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      clickModeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentClickButton = btn.getAttribute('data-btn');
    });
  });

  // Interactive Touch-to-Click on Screen Canvas
  if (screenCanvasBox) {
    screenCanvasBox.addEventListener('click', async (e) => {
    if (!screenImg || !screenImg.naturalWidth) return;

    const rect = screenImg.getBoundingClientRect();
    const clientX = e.clientX;
    const clientY = e.clientY;

    if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) {
      return;
    }

    const normX = (clientX - rect.left) / rect.width;
    const normY = (clientY - rect.top) / rect.height;

    // Show ripple animation
    const relX = clientX - rect.left;
    const relY = clientY - rect.top;
    screenRipple.style.left = `${relX}px`;
    screenRipple.style.top = `${relY}px`;
    screenRipple.classList.add('active');
    setTimeout(() => screenRipple.classList.remove('active'), 250);

    try {
      await fetch(`/api/screen/click?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          norm_x: normX,
          norm_y: normY,
          button: currentClickButton
        })
      });

      // Quick visual refresh after click
      setTimeout(refreshScreenFrame, 150);
    } catch (err) {}
    });
  }

  // Screen Virtual Keyboard Keys
  document.querySelectorAll('.s-key[data-skey]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const key = btn.getAttribute('data-skey');
      try {
        await fetch(`/api/screen/key?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key: key })
        });
        setTimeout(refreshScreenFrame, 150);
      } catch (e) {}
    });
  });

  // Send Typed Text to Active PC Window
  async function sendScreenText() {
    if (!screenTextInput) return;
    const text = screenTextInput.value;
    if (!text) return;
    try {
      await fetch(`/api/screen/key?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
      });
      screenTextInput.value = '';
      showToast('Text typed on PC');
      setTimeout(refreshScreenFrame, 200);
    } catch (e) {
      showToast('Failed to type text');
    }
  }

  if (btnScreenSendText) btnScreenSendText.addEventListener('click', sendScreenText);
  if (screenTextInput) {
    screenTextInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendScreenText();
    });
  }

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
  // 4. AirDrop File Drop & Downloads
  // ----------------------------------------------------
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const fileList = document.getElementById('pcFilesList');
  const uploadProgContainer = document.getElementById('uploadProgress');
  const progressBar = document.getElementById('progressBarFill');

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

  function uploadFiles(files) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }

    if (uploadProgContainer) uploadProgContainer.style.display = 'block';
    if (progressBar) progressBar.style.width = '10%';

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/upload?token=${encodeURIComponent(authToken)}`, true);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && progressBar) {
        const pct = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = `${pct}%`;
      }
    };

    xhr.onload = () => {
      if (uploadProgContainer) uploadProgContainer.style.display = 'none';
      if (progressBar) progressBar.style.width = '0%';
      if (xhr.status === 200) {
        showToast('✓ File(s) saved to PC ~/Downloads');
        loadFiles();
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

  function loadFiles() {
    if (!fileList) return;
    fetch(`/api/files?token=${encodeURIComponent(authToken)}`)
      .then(res => res.json())
      .then(data => {
        fileList.innerHTML = '';
        if (!data.files || data.files.length === 0) {
          fileList.innerHTML = '<li class="file-item empty">No files found in ~/Downloads</li>';
          return;
        }

        data.files.forEach(f => {
          const li = document.createElement('li');
          li.className = 'file-item';
          li.innerHTML = `
            <div class="file-info">
              <span class="file-name">${escapeHtml(f.name)}</span>
              <span class="file-meta">${f.size} • ${f.time}</span>
            </div>
            <a href="/api/download/${encodeURIComponent(f.name)}?token=${encodeURIComponent(authToken)}" class="btn-download" download>Download</a>
          `;
          fileList.appendChild(li);
        });
      })
      .catch(() => {
        fileList.innerHTML = '<li class="file-item empty">Failed to load files</li>';
      });
  }

  const btnRefreshFiles = document.getElementById('btnRefreshFiles');
  if (btnRefreshFiles) btnRefreshFiles.addEventListener('click', loadFiles);

  // ----------------------------------------------------
  // 5. Quick System Actions
  // ----------------------------------------------------
  document.querySelectorAll('.action-card[data-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.getAttribute('data-action');
      fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: action })
      })
      .then(res => res.json())
      .then(res => {
        showToast(res.message || 'Action executed');
      })
      .catch(() => showToast('Action failed'));
    });
  });

  // ----------------------------------------------------
  // 6. Remote Connectivity & SSH Controller
  // ----------------------------------------------------
  const remoteTunnelStatus = document.getElementById('remoteTunnelStatus');
  const remoteTailscaleIp = document.getElementById('remoteTailscaleIp');
  const remoteSshCmd = document.getElementById('remoteSshCmd');
  const btnTogglePublicTunnel = document.getElementById('btnTogglePublicTunnel');
  const btnCopyTunnelUrl = document.getElementById('btnCopyTunnelUrl');
  const btnCopySshCmd = document.getElementById('btnCopySshCmd');
  const btnRefreshTunnelStatus = document.getElementById('btnRefreshTunnelStatus');
  let currentTunnelUrl = '';
  let currentSshCmd = '';

  async function loadTunnelStatus() {
    if (!remoteTunnelStatus) return;
    try {
      const res = await fetch(`/api/tunnel?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();
      if (data.status === 'ok') {
        if (data.tunnel_active && data.tunnel_url) {
          currentTunnelUrl = data.tunnel_url;
          remoteTunnelStatus.textContent = '● Active (Public HTTPS)';
          remoteTunnelStatus.style.color = '#34c759';
          btnTogglePublicTunnel.textContent = '⏹ Stop Public Tunnel';
          btnCopyTunnelUrl.style.display = 'inline-block';
        } else {
          currentTunnelUrl = '';
          remoteTunnelStatus.textContent = 'Inactive';
          remoteTunnelStatus.style.color = '#8e95a5';
          btnTogglePublicTunnel.textContent = '⚡ Start Public Tunnel';
          btnCopyTunnelUrl.style.display = 'none';
        }

        if (data.tailscale_ip) {
          remoteTailscaleIp.textContent = `${data.tailscale_ip} (Active)`;
          remoteTailscaleIp.style.color = '#34c759';
        } else {
          remoteTailscaleIp.textContent = 'Inactive / Not Connected';
          remoteTailscaleIp.style.color = '#8e95a5';
        }

        if (data.ssh && data.ssh.cmd_tmux_remote) {
          currentSshCmd = data.ssh.cmd_tmux_remote;
          remoteSshCmd.textContent = currentSshCmd;
        } else if (data.ssh && data.ssh.cmd_tailscale) {
          currentSshCmd = data.ssh.cmd_tailscale;
          remoteSshCmd.textContent = currentSshCmd;
        } else {
          currentSshCmd = `ssh ${data.ssh?.user || 'killindodo'}@${data.local_ip}`;
          remoteSshCmd.textContent = currentSshCmd;
        }
      }
    } catch (e) {}
  }

  if (btnTogglePublicTunnel) {
    btnTogglePublicTunnel.addEventListener('click', async () => {
      const isStarting = btnTogglePublicTunnel.textContent.includes('Start');
      btnTogglePublicTunnel.textContent = isStarting ? 'Starting...' : 'Stopping...';
      try {
        const action = isStarting ? 'start' : 'stop';
        await fetch(`/api/tunnel?token=${encodeURIComponent(authToken)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action })
        });
        showToast(isStarting ? 'Cloudflare Tunnel starting...' : 'Cloudflare Tunnel stopped');
        setTimeout(loadTunnelStatus, 3000);
      } catch (e) {
        showToast('Tunnel request failed');
        loadTunnelStatus();
      }
    });
  }

  if (btnCopyTunnelUrl) {
    btnCopyTunnelUrl.addEventListener('click', () => {
      if (currentTunnelUrl) {
        navigator.clipboard.writeText(`${currentTunnelUrl}/?token=${authToken}`);
        showToast('✓ Public Tunnel URL Copied!');
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
    btnRefreshTunnelStatus.addEventListener('click', loadTunnelStatus);
  }

  // ----------------------------------------------------
  // PWA Service Worker Registration
  // ----------------------------------------------------
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  // ----------------------------------------------------
  // Submode: Screen Mirror vs Virtual Trackpad
  // ----------------------------------------------------
  window.activeScreenSubmode = 'mirror';
  const btnSubModeMirror = document.getElementById('btnSubModeMirror');
  const btnSubModeTrackpad = document.getElementById('btnSubModeTrackpad');
  const screenMirrorSubpanel = document.getElementById('screenMirrorSubpanel');
  const trackpadSubpanel = document.getElementById('trackpadSubpanel');

  if (btnSubModeMirror && btnSubModeTrackpad) {
    btnSubModeMirror.addEventListener('click', () => {
      window.activeScreenSubmode = 'mirror';
      btnSubModeMirror.classList.add('active');
      btnSubModeTrackpad.classList.remove('active');
      if (screenMirrorSubpanel) screenMirrorSubpanel.style.display = 'block';
      if (trackpadSubpanel) trackpadSubpanel.style.display = 'none';
      startScreenLoop();
      refreshScreenFrame();
    });

    btnSubModeTrackpad.addEventListener('click', () => {
      window.activeScreenSubmode = 'trackpad';
      btnSubModeTrackpad.classList.add('active');
      btnSubModeMirror.classList.remove('active');
      if (screenMirrorSubpanel) screenMirrorSubpanel.style.display = 'none';
      if (trackpadSubpanel) trackpadSubpanel.style.display = 'block';
      stopScreenLoop();
    });
  }

  // Trackpad Touch Gestures
  const trackpadSurface = document.getElementById('trackpadSurface');
  let tpTouchStartX = 0;
  let tpTouchStartY = 0;
  let tpLastX = 0;
  let tpLastY = 0;
  let tpTouchStartTime = 0;
  let tpHasMoved = false;
  let tpThrottled = false;

  if (trackpadSurface) {
    trackpadSurface.addEventListener('touchstart', (e) => {
      e.preventDefault();
      tpTouchStartTime = Date.now();
      tpHasMoved = false;

      if (e.touches.length === 1) {
        tpTouchStartX = e.touches[0].clientX;
        tpTouchStartY = e.touches[0].clientY;
        tpLastX = tpTouchStartX;
        tpLastY = tpTouchStartY;
      } else if (e.touches.length === 2) {
        tpTouchStartY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        tpLastY = tpTouchStartY;
      }
    }, { passive: false });

    trackpadSurface.addEventListener('touchmove', (e) => {
      e.preventDefault();

      if (e.touches.length === 1) {
        const curX = e.touches[0].clientX;
        const curY = e.touches[0].clientY;
        const dx = (curX - tpLastX) * 1.5;
        const dy = (curY - tpLastY) * 1.5;

        if (Math.abs(curX - tpTouchStartX) > 4 || Math.abs(curY - tpTouchStartY) > 4) {
          tpHasMoved = true;
        }

        tpLastX = curX;
        tpLastY = curY;

        if (!tpThrottled && (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5)) {
          tpThrottled = true;
          fetch(`/api/trackpad?token=${encodeURIComponent(authToken)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: 'move', dx: Math.round(dx), dy: Math.round(dy) })
          }).finally(() => {
            setTimeout(() => { tpThrottled = false; }, 20);
          });
        }
      } else if (e.touches.length === 2) {
        tpHasMoved = true;
        const curY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        const diffY = curY - tpLastY;
        tpLastY = curY;

        if (!tpThrottled && Math.abs(diffY) > 8) {
          tpThrottled = true;
          const direction = diffY > 0 ? 'up' : 'down';
          fetch(`/api/trackpad?token=${encodeURIComponent(authToken)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: 'scroll', direction, steps: 2 })
          }).finally(() => {
            setTimeout(() => { tpThrottled = false; }, 40);
          });
        }
      }
    }, { passive: false });

    trackpadSurface.addEventListener('touchend', (e) => {
      e.preventDefault();
      const duration = Date.now() - tpTouchStartTime;
      if (!tpHasMoved && duration < 300) {
        if (e.changedTouches.length === 1) {
          fetch(`/api/trackpad?token=${encodeURIComponent(authToken)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: 'click', button: '1' })
          });
          showToast('Left Click');
        }
      }
    }, { passive: false });
  }

  // Trackpad Buttons
  const btnTpLeft = document.getElementById('btnTrackpadLeft');
  const btnTpMiddle = document.getElementById('btnTrackpadMiddle');
  const btnTpRight = document.getElementById('btnTrackpadRight');

  if (btnTpLeft) {
    btnTpLeft.addEventListener('click', () => {
      fetch(`/api/trackpad?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'click', button: '1' })
      });
      showToast('Left Click');
    });
  }
  if (btnTpMiddle) {
    btnTpMiddle.addEventListener('click', () => {
      fetch(`/api/trackpad?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'click', button: '2' })
      });
      showToast('Middle Click');
    });
  }
  if (btnTpRight) {
    btnTpRight.addEventListener('click', () => {
      fetch(`/api/trackpad?token=${encodeURIComponent(authToken)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'click', button: '3' })
      });
      showToast('Right Click');
    });
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

  // Initialization
  function initAppConnections() {
    loadSessions();
    connectTerminal(currentSession);
    connectClipboard();
    loadTunnelStatus();
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
