"use client";

import { useState, useRef, useCallback } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────
type ParseResult = {
  text: string;
  fileName: string;
  pageCount: number;
  pages: { pageNum: number; itemCount: number }[];
};

type InputMode = "file" | "url";

// ─── Accepted file types (all formats LiteParse supports) ─────────────────────
const ACCEPTED_TYPES = [
  // PDF
  ".pdf",
  // Word
  ".doc", ".docx", ".docm", ".odt", ".rtf",
  // PowerPoint
  ".ppt", ".pptx", ".pptm", ".odp",
  // Spreadsheets
  ".xls", ".xlsx", ".xlsm", ".ods", ".csv", ".tsv",
  // Images (including screenshots)
  ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg",
].join(",");

// ─── Helpers ──────────────────────────────────────────────────────────────────
function getFileIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return "📄";
  if (["doc", "docx", "odt", "rtf", "docm"].includes(ext)) return "📝";
  if (["ppt", "pptx", "pptm", "odp"].includes(ext)) return "📊";
  if (["xls", "xlsx", "xlsm", "ods", "csv", "tsv"].includes(ext)) return "📈";
  if (["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp", "svg"].includes(ext)) return "🖼️";
  return "📎";
}

function formatBytes(bytes: number) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function ParsePage() {
  const [mode, setMode] = useState<InputMode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ParseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Drag & Drop ─────────────────────────────────────────────────────────────
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);
  const onDragLeave = useCallback(() => setDragging(false), []);
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) { setFile(dropped); setResult(null); setError(null); }
  }, []);

  // ── Submit ───────────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      let res: Response;

      if (mode === "file") {
        if (!file) { setError("Please select a file."); setLoading(false); return; }
        const form = new FormData();
        form.append("file", file);
        res = await fetch("/api/parse", { method: "POST", body: form });
      } else {
        if (!url.trim()) { setError("Please enter a URL."); setLoading(false); return; }
        res = await fetch("/api/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: url.trim() }),
        });
      }

      const data = await res.json();
      if (!res.ok) { setError(data.error ?? "Parsing failed."); }
      else { setResult(data); }
    } catch {
      setError("Network error. Is the dev server running?");
    } finally {
      setLoading(false);
    }
  };

  // ── Copy to clipboard ────────────────────────────────────────────────────────
  const handleCopy = async () => {
    if (!result?.text) return;
    await navigator.clipboard.writeText(result.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // ─── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
          --bg: #0a0a0f;
          --surface: #111118;
          --surface2: #1a1a24;
          --border: #2a2a3a;
          --border-bright: #3d3d58;
          --accent: #6c63ff;
          --accent2: #ff6584;
          --accent3: #43e8c8;
          --text: #e8e8f0;
          --muted: #6b6b85;
          --success: #43e8a8;
          --error: #ff4d6d;
          --font-display: 'Syne', sans-serif;
          --font-mono: 'DM Mono', monospace;
          --radius: 12px;
          --glow: 0 0 40px rgba(108,99,255,.15);
        }

        body {
          background: var(--bg);
          color: var(--text);
          font-family: var(--font-display);
          min-height: 100vh;
        }

        .page {
          min-height: 100vh;
          display: grid;
          grid-template-rows: auto 1fr;
          position: relative;
          overflow: hidden;
        }

        /* bg noise */
        .page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image:
            radial-gradient(ellipse 60% 40% at 20% 10%, rgba(108,99,255,.08) 0%, transparent 60%),
            radial-gradient(ellipse 40% 60% at 80% 90%, rgba(67,232,200,.05) 0%, transparent 60%);
          pointer-events: none;
          z-index: 0;
        }

        .header {
          position: relative;
          z-index: 1;
          padding: 32px 40px 0;
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .logo-mark {
          width: 36px;
          height: 36px;
          background: linear-gradient(135deg, var(--accent), var(--accent3));
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 18px;
          flex-shrink: 0;
        }

        .header h1 {
          font-size: 1.5rem;
          font-weight: 800;
          letter-spacing: -0.02em;
          background: linear-gradient(90deg, var(--text) 0%, var(--muted) 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .header .badge {
          margin-left: auto;
          font-family: var(--font-mono);
          font-size: 0.65rem;
          padding: 4px 10px;
          border: 1px solid var(--border);
          border-radius: 100px;
          color: var(--muted);
          letter-spacing: .05em;
        }

        .main {
          position: relative;
          z-index: 1;
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 24px;
          padding: 28px 40px 40px;
          max-width: 1400px;
          margin: 0 auto;
          width: 100%;
        }

        @media (max-width: 900px) {
          .main { grid-template-columns: 1fr; padding: 20px; }
          .header { padding: 20px 20px 0; }
        }

        .panel {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          overflow: hidden;
        }

        .panel-header {
          padding: 18px 22px;
          border-bottom: 1px solid var(--border);
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: .75rem;
          font-weight: 600;
          letter-spacing: .1em;
          text-transform: uppercase;
          color: var(--muted);
        }

        .panel-header .dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--accent);
          flex-shrink: 0;
        }

        .panel-body { padding: 22px; }

        /* Mode tabs */
        .mode-tabs {
          display: grid;
          grid-template-columns: 1fr 1fr;
          background: var(--surface2);
          border-radius: 8px;
          padding: 4px;
          gap: 4px;
          margin-bottom: 22px;
        }

        .mode-tab {
          padding: 9px;
          border: none;
          border-radius: 6px;
          font-family: var(--font-display);
          font-size: .8rem;
          font-weight: 600;
          cursor: pointer;
          transition: all .2s;
          background: transparent;
          color: var(--muted);
          letter-spacing: .03em;
        }

        .mode-tab.active {
          background: var(--accent);
          color: #fff;
          box-shadow: 0 2px 12px rgba(108,99,255,.4);
        }

        /* Drop zone */
        .dropzone {
          border: 1.5px dashed var(--border-bright);
          border-radius: var(--radius);
          padding: 40px 24px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 10px;
          cursor: pointer;
          transition: all .2s;
          text-align: center;
          position: relative;
          overflow: hidden;
        }

        .dropzone:hover, .dropzone.drag {
          border-color: var(--accent);
          background: rgba(108,99,255,.05);
        }

        .dropzone.drag {
          transform: scale(1.01);
          box-shadow: var(--glow);
        }

        .dropzone-icon {
          font-size: 2.5rem;
          line-height: 1;
        }

        .dropzone-title {
          font-size: .95rem;
          font-weight: 700;
          color: var(--text);
        }

        .dropzone-sub {
          font-size: .72rem;
          color: var(--muted);
          line-height: 1.5;
        }

        .dropzone-formats {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          justify-content: center;
          margin-top: 4px;
        }

        .fmt-badge {
          font-family: var(--font-mono);
          font-size: .6rem;
          padding: 3px 7px;
          border: 1px solid var(--border);
          border-radius: 4px;
          color: var(--muted);
          letter-spacing: .05em;
        }

        .selected-file {
          margin-top: 14px;
          background: var(--surface2);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 12px 16px;
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .selected-file-icon { font-size: 1.5rem; flex-shrink: 0; }

        .selected-file-info { flex: 1; min-width: 0; }

        .selected-file-name {
          font-size: .85rem;
          font-weight: 600;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .selected-file-size {
          font-family: var(--font-mono);
          font-size: .68rem;
          color: var(--muted);
          margin-top: 2px;
        }

        .file-remove {
          background: none;
          border: none;
          cursor: pointer;
          color: var(--muted);
          font-size: 1rem;
          padding: 4px;
          flex-shrink: 0;
          transition: color .15s;
        }
        .file-remove:hover { color: var(--error); }

        /* URL input */
        .url-input-wrap {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .url-label {
          font-size: .72rem;
          font-weight: 600;
          letter-spacing: .08em;
          text-transform: uppercase;
          color: var(--muted);
        }

        .url-input {
          width: 100%;
          background: var(--surface2);
          border: 1.5px solid var(--border);
          border-radius: 8px;
          padding: 12px 14px;
          font-family: var(--font-mono);
          font-size: .8rem;
          color: var(--text);
          outline: none;
          transition: border-color .2s;
        }

        .url-input::placeholder { color: var(--muted); }
        .url-input:focus { border-color: var(--accent); }

        .url-hint {
          font-family: var(--font-mono);
          font-size: .65rem;
          color: var(--muted);
          line-height: 1.5;
        }

        /* Parse button */
        .parse-btn {
          width: 100%;
          margin-top: 20px;
          padding: 14px;
          background: linear-gradient(135deg, var(--accent) 0%, #8b83ff 100%);
          border: none;
          border-radius: 8px;
          font-family: var(--font-display);
          font-size: .9rem;
          font-weight: 700;
          color: #fff;
          cursor: pointer;
          letter-spacing: .03em;
          transition: all .2s;
          position: relative;
          overflow: hidden;
        }

        .parse-btn:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 24px rgba(108,99,255,.45);
        }

        .parse-btn:disabled {
          opacity: .5;
          cursor: not-allowed;
        }

        .parse-btn.loading {
          background: var(--surface2);
          border: 1.5px solid var(--border);
          color: var(--muted);
        }

        /* Spinner */
        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner {
          display: inline-block;
          width: 14px;
          height: 14px;
          border: 2px solid rgba(255,255,255,.3);
          border-top-color: #fff;
          border-radius: 50%;
          animation: spin .7s linear infinite;
          margin-right: 8px;
          vertical-align: middle;
        }

        /* Error */
        .error-box {
          margin-top: 14px;
          background: rgba(255,77,109,.08);
          border: 1px solid rgba(255,77,109,.25);
          border-radius: 8px;
          padding: 12px 14px;
          font-family: var(--font-mono);
          font-size: .75rem;
          color: var(--error);
          line-height: 1.5;
        }

        /* Result panel */
        .result-meta {
          display: flex;
          gap: 12px;
          flex-wrap: wrap;
          margin-bottom: 16px;
        }

        .meta-chip {
          background: var(--surface2);
          border: 1px solid var(--border);
          border-radius: 6px;
          padding: 6px 12px;
          font-family: var(--font-mono);
          font-size: .68rem;
          color: var(--muted);
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .meta-chip strong { color: var(--text); font-weight: 500; }

        .result-actions {
          display: flex;
          gap: 8px;
          margin-bottom: 14px;
        }

        .action-btn {
          padding: 7px 14px;
          border-radius: 6px;
          font-family: var(--font-display);
          font-size: .72rem;
          font-weight: 600;
          cursor: pointer;
          transition: all .15s;
          border: 1.5px solid var(--border);
          background: transparent;
          color: var(--muted);
          letter-spacing: .04em;
        }

        .action-btn:hover { border-color: var(--accent); color: var(--accent); }
        .action-btn.primary {
          background: var(--accent);
          border-color: var(--accent);
          color: #fff;
        }
        .action-btn.primary:hover { background: #7c74ff; }
        .action-btn.success { background: var(--success); border-color: var(--success); color: #000; }

        /* Text output */
        .text-output {
          background: var(--surface2);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 18px;
          font-family: var(--font-mono);
          font-size: .78rem;
          line-height: 1.8;
          color: #c8c8d8;
          white-space: pre-wrap;
          word-break: break-word;
          overflow-y: auto;
          max-height: 65vh;
          min-height: 200px;
        }

        /* Empty state */
        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
          height: 300px;
          color: var(--muted);
        }

        .empty-icon {
          font-size: 3rem;
          opacity: .3;
        }

        .empty-text {
          font-size: .8rem;
          text-align: center;
          line-height: 1.6;
        }

        /* Page list */
        .pages-summary {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
          margin-bottom: 12px;
        }

        .page-chip {
          background: rgba(108,99,255,.1);
          border: 1px solid rgba(108,99,255,.25);
          border-radius: 4px;
          padding: 3px 8px;
          font-family: var(--font-mono);
          font-size: .6rem;
          color: var(--accent);
        }

        /* Hidden file input */
        input[type="file"] { display: none; }
      `}</style>

      <div className="page">
        {/* Header */}
        <header className="header">
          <div className="logo-mark">⚡</div>
          <h1>LiteParse</h1>
          <span className="badge">@llamaindex/liteparse</span>
        </header>

        {/* Main grid */}
        <main className="main">

          {/* ── Left panel: Input ── */}
          <div className="panel">
            <div className="panel-header">
              <span className="dot" />
              Input Source
            </div>

            <div className="panel-body">
              {/* Mode toggle */}
              <div className="mode-tabs">
                <button
                  className={`mode-tab ${mode === "file" ? "active" : ""}`}
                  onClick={() => { setMode("file"); setError(null); setResult(null); }}
                >
                  📁 Upload File
                </button>
                <button
                  className={`mode-tab ${mode === "url" ? "active" : ""}`}
                  onClick={() => { setMode("url"); setError(null); setResult(null); }}
                >
                  🌐 Remote URL
                </button>
              </div>

              {/* File upload */}
              {mode === "file" && (
                <>
                  <div
                    className={`dropzone ${dragging ? "drag" : ""}`}
                    onDragOver={onDragOver}
                    onDragLeave={onDragLeave}
                    onDrop={onDrop}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <div className="dropzone-icon">📂</div>
                    <div className="dropzone-title">Drop your file here</div>
                    <div className="dropzone-sub">
                      or click to browse — any format supported
                    </div>
                    <div className="dropzone-formats">
                      {["PDF", "DOCX", "PPTX", "XLSX", "PNG", "JPG", "SVG", "ODP", "CSV", "RTF"].map((f) => (
                        <span key={f} className="fmt-badge">{f}</span>
                      ))}
                    </div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept={ACCEPTED_TYPES}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) { setFile(f); setResult(null); setError(null); }
                      }}
                    />
                  </div>

                  {file && (
                    <div className="selected-file">
                      <span className="selected-file-icon">{getFileIcon(file.name)}</span>
                      <div className="selected-file-info">
                        <div className="selected-file-name">{file.name}</div>
                        <div className="selected-file-size">{formatBytes(file.size)}</div>
                      </div>
                      <button
                        className="file-remove"
                        onClick={() => { setFile(null); setResult(null); setError(null); }}
                        title="Remove file"
                      >✕</button>
                    </div>
                  )}
                </>
              )}

              {/* URL input */}
              {mode === "url" && (
                <div className="url-input-wrap">
                  <label className="url-label">Document URL</label>
                  <input
                    className="url-input"
                    type="url"
                    placeholder="https://example.com/document.pdf"
                    value={url}
                    onChange={(e) => { setUrl(e.target.value); setResult(null); setError(null); }}
                  />
                  <span className="url-hint">
                    Supports direct links to PDFs, DOCX, PPTX, images, and more.<br />
                    The server will fetch and parse the remote file in memory.
                  </span>
                </div>
              )}

              {/* Error */}
              {error && <div className="error-box">⚠ {error}</div>}

              {/* Parse button */}
              <button
                className={`parse-btn ${loading ? "loading" : ""}`}
                onClick={handleSubmit}
                disabled={loading || (mode === "file" ? !file : !url.trim())}
              >
                {loading ? (
                  <><span className="spinner" />Parsing…</>
                ) : (
                  "⚡ Parse Document"
                )}
              </button>
            </div>
          </div>

          {/* ── Right panel: Output ── */}
          <div className="panel">
            <div className="panel-header">
              <span className="dot" style={{ background: "var(--accent3)" }} />
              Parsed Output
              {result && (
                <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: ".65rem", color: "var(--success)" }}>
                  ✓ {result.fileName}
                </span>
              )}
            </div>

            <div className="panel-body">
              {result ? (
                <>
                  {/* Meta chips */}
                  <div className="result-meta">
                    <div className="meta-chip">
                      Pages: <strong>{result.pageCount}</strong>
                    </div>
                    <div className="meta-chip">
                      Chars: <strong>{result.text.length.toLocaleString()}</strong>
                    </div>
                    <div className="meta-chip">
                      Words: <strong>{result.text.split(/\s+/).filter(Boolean).length.toLocaleString()}</strong>
                    </div>
                  </div>

                  {/* Page breakdown */}
                  {result.pages.length > 1 && (
                    <div className="pages-summary">
                      {result.pages.map((p) => (
                        <span key={p.pageNum} className="page-chip" title={`${p.itemCount} text items`}>
                          p{p.pageNum}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="result-actions">
                    <button
                      className={`action-btn ${copied ? "success" : "primary"}`}
                      onClick={handleCopy}
                    >
                      {copied ? "✓ Copied!" : "Copy Text"}
                    </button>
                    <button
                      className="action-btn"
                      onClick={() => {
                        const blob = new Blob([result.text], { type: "text/plain" });
                        const a = document.createElement("a");
                        a.href = URL.createObjectURL(blob);
                        a.download = `${result.fileName.replace(/\.[^.]+$/, "")}-parsed.txt`;
                        a.click();
                      }}
                    >
                      ↓ Save as .txt
                    </button>
                    <button
                      className="action-btn"
                      onClick={() => { setResult(null); setFile(null); setUrl(""); setError(null); }}
                      style={{ marginLeft: "auto" }}
                    >
                      Clear
                    </button>
                  </div>

                  {/* Text */}
                  <div className="text-output">
                    {result.text || "(No text extracted — the document may be empty or image-only without OCR data.)"}
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <div className="empty-icon">📋</div>
                  <div className="empty-text">
                    Parsed text will appear here.<br />
                    Upload a file or paste a URL, then hit Parse.
                  </div>
                </div>
              )}
            </div>
          </div>

        </main>
      </div>
    </>
  );
}