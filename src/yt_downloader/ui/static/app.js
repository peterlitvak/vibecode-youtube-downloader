"use strict";

(function () {
  const statusEl = document.getElementById("status");
  const probeBtn = document.getElementById("probeBtn");
  const downloadBtn = document.getElementById("downloadBtn");
  const qualitySel = document.getElementById("quality");
  const urlInput = document.getElementById("url");
  const targetDirInput = document.getElementById("targetDir");
  const progressFill = document.getElementById("progressFill");
  const progressText = document.getElementById("progressText");
  const themeToggle = document.getElementById("themeToggle");
  const alertContainer = document.getElementById("alertContainer");
  const fileBox = document.getElementById("fileBox");
  const filePathInput = document.getElementById("filePath");
  const copyBtn = document.getElementById("copyBtn");
  const copyMsg = document.getElementById("copyMsg");
  let lastProbe = null;
  let currentWS = null;
  let currentJobId = null;
  let lastProgress = 0;

  function setStatus(message) {
    statusEl.textContent = message;
  }

  function setProgress(percent, text) {
    const p = Math.max(0, Math.min(100, Number(percent || 0)));
    if (progressFill) progressFill.style.width = `${p}%`;
    if (progressText) {
      if (text !== undefined) {
        progressText.textContent = String(text);
      } else {
        progressText.textContent = ""; // no percent text, bar only
      }
    }
  }

  const clearAlerts = () => {
    if (alertContainer) alertContainer.innerHTML = "";
  };

  const pushAlert = (type, message) => {
    if (!alertContainer) return;
    let classes = "rounded-md px-3 py-2 text-sm flex justify-between items-start border ";
    if (type === "error") {
      classes += "border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200";
    } else if (type === "success") {
      classes += "border-green-300 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200";
    } else {
      classes += "border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200";
    }
    const wrapper = document.createElement("div");
    wrapper.className = classes;
    const span = document.createElement("span");
    span.textContent = String(message || "");
    const btn = document.createElement("button");
    btn.className = "ml-3 text-sm opacity-80 hover:opacity-100";
    btn.textContent = "×";
    btn.onclick = () => wrapper.remove();
    wrapper.appendChild(span);
    wrapper.appendChild(btn);
    alertContainer.appendChild(wrapper);
  };

  function controlsDisabled(disabled) {
    urlInput.disabled = disabled;
    qualitySel.disabled = disabled || qualitySel.options.length === 0;
    targetDirInput.disabled = disabled;
    probeBtn.disabled = disabled;
    downloadBtn.disabled = disabled || !qualitySel.value;
  }

  function openJobWebSocket(jobId) {
    if (currentWS) {
      try { currentWS.close(); } catch (_) {}
    }
    const loc = window.location;
    const scheme = loc.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${scheme}//${loc.host}/ws/jobs/${jobId}`;
    const ws = new WebSocket(wsUrl);
    currentWS = ws;

    ws.onopen = () => {
      setStatus("Downloading...");
      lastProgress = 0;
      setProgress(0, "");
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "progress") {
          const raw = msg.progressPercent != null ? Number(msg.progressPercent) : 0;
          const p = Math.max(lastProgress, Math.min(100, Math.floor(raw)));
          lastProgress = p;
          setProgress(p, "");
        } else if (msg.type === "complete" || msg.type === "final") {
          setProgress(100, "");
          const file = msg.filePath ? ` File: ${msg.filePath}` : "";
          setStatus(`Done.${file}`);
          if (msg.filePath && fileBox && filePathInput) {
            filePathInput.value = msg.filePath;
            fileBox.classList.remove("hidden");
          }
          if (msg.filePath) {
            pushAlert("success", "Download completed.");
          }
          controlsDisabled(false);
          try { ws.close(); } catch (_) {}
        } else if (msg.type === "error") {
          const emsg = msg.error || "unknown";
          setStatus(`Error: ${emsg}`);
          pushAlert("error", emsg);
          setProgress(0, "");
          controlsDisabled(false);
          try { ws.close(); } catch (_) {}
        } else if (msg.type === "status") {
          setStatus(`Status: ${msg.status}`);
        }
      } catch (_) {
        // ignore
      }
    };
    ws.onclose = () => {
      currentWS = null;
      currentJobId = null;
    };
  }

  async function doDownload() {
    const url = (urlInput.value || "").trim();
    const formatId = (qualitySel.value || "").trim();
    const targetDir = (targetDirInput.value || "").trim();
    if (!url) {
      setStatus("Please enter a YouTube URL.");
      return;
    }
    if (!formatId) {
      setStatus("Please select a quality.");
      return;
    }
    controlsDisabled(true);
    setStatus("Starting download...");
    setProgress(0, "");
    clearAlerts();
    if (fileBox && filePathInput) {
      fileBox.classList.add("hidden");
      filePathInput.value = "";
    }
    try {
      const resp = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, formatId, targetDir: targetDir || undefined }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        pushAlert("error", text || `HTTP ${resp.status}`);
        throw new Error(text || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      currentJobId = data.jobId;
      openJobWebSocket(currentJobId);
    } catch (err) {
      setStatus(`Failed to start download: ${err.message || String(err)}`);
      controlsDisabled(false);
    }
  }

  function optionLabel(fmt) {
    const parts = [];
    if (fmt.resolution) parts.push(fmt.resolution);
    if (fmt.fps) parts.push(`${fmt.fps}fps`);
    if (fmt.ext) parts.push(fmt.ext);
    const note = fmt.note ? ` - ${fmt.note}` : "";
    return `${parts.join(" ")} [${fmt.id}]${note}`.trim();
  }

  function populateFormats(formats) {
    qualitySel.innerHTML = "";
    const list = Array.isArray(formats) ? formats : [];
    // Only show progressive formats that include both audio and video
    const usable = list.filter((f) => {
      const ac = (f.acodec || "").toLowerCase();
      const vc = (f.vcodec || "").toLowerCase();
      return ac && ac !== "none" && vc && vc !== "none";
    });

    if (usable.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No progressive (audio+video) formats found";
      qualitySel.appendChild(opt);
      qualitySel.disabled = true;
      downloadBtn.disabled = true;
      return;
    }

    for (const f of usable) {
      const opt = document.createElement("option");
      opt.value = f.id;
      opt.textContent = optionLabel(f);
      qualitySel.appendChild(opt);
    }
    qualitySel.disabled = false;
    downloadBtn.disabled = qualitySel.value === "";
  }

  async function doProbe() {
    const url = (urlInput.value || "").trim();
    if (!url) {
      setStatus("Please enter a YouTube URL.");
      return;
    }
    setStatus("Probing...");
    setProgress(0, "");
    clearAlerts();
    qualitySel.disabled = true;
    downloadBtn.disabled = true;

    try {
      const resp = await fetch("/api/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      lastProbe = data;
      populateFormats(data.formats || []);
      const title = data.title || "video";
      setStatus(`Found ${data.formats?.length || 0} formats for: ${title}`);
    } catch (err) {
      setStatus(`Probe failed: ${err.message || String(err)}`);
    }
  }

  function init() {
    setStatus("Ready. Enter URL and click Check to load available qualities.");

    probeBtn.addEventListener("click", () => { void doProbe(); });
    qualitySel.addEventListener("change", () => {
      downloadBtn.disabled = qualitySel.value === "";
    });

    // Auto-probe when a URL is pasted into the input
    urlInput.addEventListener("paste", () => {
      setTimeout(() => { void doProbe(); }, 0);
    });

    downloadBtn.addEventListener("click", () => { void doDownload(); });

    // Copy to clipboard
    copyBtn?.addEventListener("click", async () => {
      const text = filePathInput?.value || "";
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        if (copyMsg) {
          copyMsg.classList.remove("hidden");
          setTimeout(() => copyMsg.classList.add("hidden"), 1500);
        }
      } catch (_) {
        pushAlert("error", "Failed to copy to clipboard");
      }
    });

    // Theme toggle with persistence
    // Note: theme is already applied in HTML head to avoid flash
    const updateThemeLabel = () => {
      if (!themeToggle) return;
      const isDark = document.documentElement.classList.contains("dark");
      themeToggle.textContent = isDark ? "☀️ Light" : "🌙 Dark";
    };
    
    // Update label on init
    updateThemeLabel();
    
    // Handle toggle clicks
    themeToggle?.addEventListener("click", () => {
      const html = document.documentElement;
      const currentlyDark = html.classList.contains("dark");
      
      if (currentlyDark) {
        // Switch to light mode
        html.classList.remove("dark");
        localStorage.setItem("theme", "light");
      } else {
        // Switch to dark mode
        html.classList.add("dark");
        localStorage.setItem("theme", "dark");
      }
      
      // Update button label
      updateThemeLabel();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
