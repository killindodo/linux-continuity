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
          setTimeout(() => {
            window.fitAddon.fit();
            if (termWs && termWs.readyState === WebSocket.OPEN) {
              termWs.send(JSON.stringify({
                type: 'resize',
                cols: term.cols,
                rows: term.rows
              }));
            }
          }, 150);
        } else if (target === 'screen') {
          startScreenLoop();
          refreshScreenFrame();
        } else {
          stopScreenLoop();
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
  window.fitAddon = fitAddon;
  term.loadAddon(fitAddon);
  term.open(termContainer);
  fitAddon.fit();

  let termWs = null;
  let currentSession = 'main';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

  function connectTerminal(sessionName) {
    if (sessionName) currentSession = sessionName;
    if (termWs) {
      try { termWs.close(); } catch (e) {}
      termWs = null;
    }

    term.write(`\r\n\x1b[36m[*] Attaching to Terminal session: [${currentSession}]...\x1b[0m\r\n`);
    const termUrl = `${protocol}//${window.location.host}/ws/terminal?token=${encodeURIComponent(authToken)}&session=${encodeURIComponent(currentSession)}`;
    termWs = new WebSocket(termUrl);
    termWs.binaryType = 'arraybuffer';

    termWs.onopen = () => {
      setStatus(true, 'Connected');
      fitAddon.fit();
      termWs.send(JSON.stringify({
        type: 'resize',
        cols: term.cols,
        rows: term.rows
      }));
    };

    termWs.onmessage = (evt) => {
      if (typeof evt.data === 'string') {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'output') {
            term.write(msg.data);
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
      setStatus(false, 'Disconnected');
      term.write('\r\n\x1b[31m[!] Terminal session detached or closed.\x1b[0m\r\n');
    };

    termWs.onerror = () => {
      setStatus(false, 'Conn Error');
    };
  }

  term.onData((data) => {
    if (termWs && termWs.readyState === WebSocket.OPEN) {
      termWs.send(JSON.stringify({ type: 'input', data: data }));
    }
  });

  // Mobile Keyboard Helper Keys
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

  // Session Management Controls
  const termSessionSelect = document.getElementById('termSessionSelect');
  const btnNewSession = document.getElementById('btnNewSession');
  const btnLaunchPcTerm = document.getElementById('btnLaunchPcTerm');
  const btnToggleProcs = document.getElementById('btnToggleProcs');
  const procsDrawer = document.getElementById('procsDrawer');
  const procsContent = document.getElementById('procsContent');
  const btnRefreshProcs = document.getElementById('btnRefreshProcs');
  const btnCloseProcs = document.getElementById('btnCloseProcs');

  async function loadSessions() {
    try {
      const res = await fetch(`/api/terminals?token=${encodeURIComponent(authToken)}`);
      const data = await res.json();
      if (data.status === 'ok' && data.tmux_sessions) {
        termSessionSelect.innerHTML = '';
        let found = false;
        data.tmux_sessions.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.name;
          opt.textContent = `${s.name} (${s.windows} win)`;
          if (s.name === currentSession) {
            opt.selected = true;
            found = true;
          }
          termSessionSelect.appendChild(opt);
        });

        if (!found) {
          const opt = document.createElement('option');
          opt.value = currentSession;
          opt.textContent = currentSession;
          opt.selected = true;
          termSessionSelect.appendChild(opt);
        }
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
        showToast(`⚡ Terminal launched on PC desktop (Session: ${currentSession})`);
      } else {
        showToast('Could not launch terminal emulator on PC');
      }
    } catch (e) {
      showToast('Request failed');
    }
  });

  // Running Desktop Terminals (PTS) Inspector
  btnToggleProcs.addEventListener('click', () => {
    if (procsDrawer.style.display === 'none') {
      procsDrawer.style.display = 'block';
      loadRunningProcesses();
    } else {
      procsDrawer.style.display = 'none';
    }
  });

  btnCloseProcs.addEventListener('click', () => {
    procsDrawer.style.display = 'none';
  });

  btnRefreshProcs.addEventListener('click', () => {
    loadRunningProcesses();
  });

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
      if (termWs && termWs.readyState === WebSocket.OPEN) {
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

  screenRefreshRate.addEventListener('change', () => {
    const pane = document.getElementById('tab-screen');
    if (pane && pane.classList.contains('active')) {
      startScreenLoop();
    }
  });

  btnScreenManualRefresh.addEventListener('click', () => {
    refreshScreenFrame();
  });

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

  btnScreenSendText.addEventListener('click', sendScreenText);
  screenTextInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendScreenText();
  });

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
          if (currentPcText.trim()) {
            pcClipBox.textContent = currentPcText;
            pcClipBox.classList.remove('placeholder');
          } else {
            pcClipBox.textContent = '(PC Clipboard is currently empty)';
            pcClipBox.classList.add('placeholder');
          }
        }
      } catch (e) {}
    };

    clipWs.onclose = () => {
      setTimeout(connectClipboard, 3000);
    };
  }

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

  btnSendToPc.addEventListener('click', () => {
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

  // ----------------------------------------------------
  // 4. AirDrop File Drop & Downloads
  // ----------------------------------------------------
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const fileList = document.getElementById('fileList');
  const uploadProgContainer = document.getElementById('uploadProgress');
  const progressBar = document.getElementById('progressBar');

  dropZone.addEventListener('click', () => fileInput.click());

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

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
      uploadFiles(fileInput.files);
    }
  });

  function uploadFiles(files) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }

    uploadProgContainer.style.display = 'block';
    progressBar.style.width = '10%';

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload', true);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = `${pct}%`;
      }
    };

    xhr.onload = () => {
      uploadProgContainer.style.display = 'none';
      progressBar.style.width = '0%';
      if (xhr.status === 200) {
        showToast('✓ File(s) saved to PC ~/Downloads');
        loadFiles();
      } else {
        showToast('Upload failed');
      }
      fileInput.value = '';
    };

    xhr.onerror = () => {
      uploadProgContainer.style.display = 'none';
      showToast('Network error during upload');
    };

    xhr.send(formData);
  }

  function loadFiles() {
    fetch('/api/files')
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
            <a href="/api/download/${encodeURIComponent(f.name)}" class="btn-download" download>Download</a>
          `;
          fileList.appendChild(li);
        });
      })
      .catch(() => {
        fileList.innerHTML = '<li class="file-item empty">Failed to load files</li>';
      });
  }

  document.getElementById('btnRefreshFiles').addEventListener('click', loadFiles);

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

  // Initialization
  function initAppConnections() {
    loadSessions();
    connectTerminal(currentSession);
    connectClipboard();
  }

  // Load Host Info & Initialize Connection
  fetch('/api/info')
    .then(r => r.json())
    .then(data => {
      if (data.hostname) document.getElementById('sysHost').textContent = data.hostname;
      if (data.ip) document.getElementById('sysIp').textContent = data.ip;
      if (data.require_pin && !authToken) {
        showPinModal();
      } else {
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
