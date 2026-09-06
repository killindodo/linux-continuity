// Linux Continuity - Mobile Web Client Controller
// Developed by killindodo

document.addEventListener('DOMContentLoaded', () => {
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
        } else if (target === 'files') {
          loadFiles();
        }
      }
    });
  });

  // Connection Status Element
  const connStatus = document.getElementById('connStatus');

  function setStatus(connected, text) {
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

  // ----------------------------------------------------
  // 1. Terminal Setup (xterm.js)
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
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const termUrl = `${protocol}//${window.location.host}/ws/terminal`;

  function connectTerminal() {
    term.write('\r\n\x1b[36m[*] Connecting to Linux Terminal...\x1b[0m\r\n');
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
      term.write('\r\n\x1b[31m[!] Terminal session disconnected.\x1b[0m\r\n');
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
    if (termWs) termWs.close();
    connectTerminal();
  });

  document.getElementById('btnClearTerm').addEventListener('click', () => {
    term.clear();
  });

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

  connectTerminal();

  // ----------------------------------------------------
  // 2. Clipboard Sync
  // ----------------------------------------------------
  const clipUrl = `${protocol}//${window.location.host}/ws/clipboard`;
  const pcClipBox = document.getElementById('pcClipboardText');
  const phoneClipInput = document.getElementById('phoneClipboardInput');
  const btnSendToPc = document.getElementById('btnSendToPc');
  const btnCopyFromPc = document.getElementById('btnCopyFromPc');
  let clipWs = null;
  let currentPcText = '';

  function connectClipboard() {
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
      // Fallback
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

  connectClipboard();

  // ----------------------------------------------------
  // 3. AirDrop File Drop & Downloads
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
  // 4. Quick System Actions
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

  // Load Host Info
  fetch('/api/info')
    .then(r => r.json())
    .then(data => {
      if (data.hostname) document.getElementById('sysHost').textContent = data.hostname;
      if (data.ip) document.getElementById('sysIp').textContent = data.ip;
    })
    .catch(() => {});

  function escapeHtml(str) {
    return str.replace(/[&<>'"]/g, 
      tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
  }
});
