"use client";

import React, {
  useState,
  useRef,
  useCallback,
  DragEvent,
  ClipboardEvent,
  ChangeEvent,
} from "react";

// ─── Types (mirror API response) ─────────────────────────────────────────────
interface ParsedPage {
  index: number;
  markdown: string;
  hasEmbeddedImages: boolean;
}

interface ParseSuccess {
  status: "success";
  engine: string;
  fileName: string;
  mimeType: string;
  fileSize: number;
  pageCount: number;
  truncated: boolean;
  truncatedAt?: number;
  pages: ParsedPage[];
  fullMarkdown: string;
  model?: string;
  usageInfo?: Record<string, unknown>;
}

interface ParseError {
  status: "error";
  fileName: string;
  error: string;
}

type ParseResult = ParseSuccess | ParseError;

// ─── Constants ────────────────────────────────────────────────────────────────
const MAX_IMAGES = 5;
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB
const MAX_PDF_PAGES = 5;

const IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/webp",
  "image/avif",
  "image/gif",
]);

const ACCEPT_TYPES = [
  ".pdf",
  ".docx",
  ".doc",
  ".xlsx",
  ".xls",
  ".pptx",
  ".ppt",
  ".txt",
  ".csv",
  ".html",
  ".odt",
  ".ods",
  ".odp",
  ".rtf",
].join(",");

// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function engineLabel(engine: string) {
  if (engine === "mistral-ocr") return { label: "Mistral OCR", color: "#f97316" };
  if (engine === "liteparse") return { label: "LiteParse", color: "#6366f1" };
  if (engine.includes("fallback")) return { label: "Fallback → LiteParse", color: "#eab308" };
  return { label: engine, color: "#94a3b8" };
}

function fileIcon(mimeType: string) {
  if (mimeType.startsWith("image/")) return "🖼️";
  if (mimeType === "application/pdf") return "📄";
  if (mimeType.includes("word") || mimeType.includes("odt") || mimeType.includes("rtf")) return "📝";
  if (mimeType.includes("sheet") || mimeType.includes("excel") || mimeType.includes("ods") || mimeType.includes("csv")) return "📊";
  if (mimeType.includes("presentation") || mimeType.includes("powerpoint") || mimeType.includes("odp")) return "📊";
  return "📎";
}

/** Render markdown string to HTML (minimal, no external lib needed for this use-case) */
function markdownToHtml(md: string): string {
  // Preserve base64 images — don't escape them
  return md
    // Headings
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    // Bold / italic
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Inline code
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    // Images (including base64 data URIs)
    .replace(/!\[([^\]]*)\]\((data:[^)]+|https?:[^)]+|[^)]+)\)/g, '<img alt="$1" src="$2" style="max-width:100%;border-radius:6px;margin:8px 0;" />')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    // Horizontal rule
    .replace(/^---$/gm, "<hr />")
    // Unordered lists
    .replace(/^\s*[-*]\s+(.+)$/gm, "<li>$1</li>")
    // Ordered lists
    .replace(/^\s*\d+\.\s+(.+)$/gm, "<li>$1</li>")
    // Line breaks → paragraphs (wrap consecutive non-tag lines)
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br />");
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ImageThumb({
  file,
  onRemove,
}: {
  file: File;
  onRemove: () => void;
}) {
  const url = URL.createObjectURL(file);
  return (
    <div style={styles.thumb}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt={file.name}
        onLoad={() => URL.revokeObjectURL(url)}
        style={styles.thumbImg}
      />
      <button onClick={onRemove} style={styles.thumbRemove} title="Remove">
        ×
      </button>
      <span style={styles.thumbName}>{formatBytes(file.size)}</span>
    </div>
  );
}

function AttachedFile({ file, onRemove }: { file: File; onRemove: () => void }) {
  const mime = file.type || "";
  return (
    <div style={styles.attachedFile}>
      <span style={styles.attachedIcon}>{fileIcon(mime)}</span>
      <span style={styles.attachedName}>{file.name}</span>
      <span style={styles.attachedSize}>{formatBytes(file.size)}</span>
      <button onClick={onRemove} style={styles.attachedRemove} title="Remove">
        ×
      </button>
    </div>
  );
}

function ResultCard({ result }: { result: ParseResult }) {
  const [activeTab, setActiveTab] = useState<"preview" | "raw">("preview");
  const [expandedPages, setExpandedPages] = useState<Set<number>>(new Set([0]));

  if (result.status === "error") {
    return (
      <div style={{ ...styles.card, borderLeft: "3px solid #ef4444" }}>
        <div style={styles.cardHeader}>
          <span>📎 {result.fileName}</span>
          <span style={styles.errorBadge}>Error</span>
        </div>
        <p style={styles.errorText}>{result.error}</p>
      </div>
    );
  }

  const eng = engineLabel(result.engine);

  const togglePage = (i: number) => {
    setExpandedPages((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  };

  return (
    <div style={styles.card}>
      {/* Card header */}
      <div style={styles.cardHeader}>
        <span style={styles.cardTitle}>
          {fileIcon(result.mimeType)} {result.fileName}
        </span>
        <div style={styles.badgeRow}>
          <span style={{ ...styles.badge, background: eng.color }}>{eng.label}</span>
          <span style={styles.badge2}>{result.pageCount} page{result.pageCount !== 1 ? "s" : ""}</span>
          <span style={styles.badge2}>{formatBytes(result.fileSize)}</span>
          {result.model && <span style={styles.badge2}>{result.model}</span>}
        </div>
      </div>

      {result.truncated && (
        <div style={styles.warningBanner}>
          ⚠️ Document has more than {MAX_PDF_PAGES} pages. Only the first {result.truncatedAt} pages were processed.
        </div>
      )}

      {/* Usage info */}
      {result.usageInfo && (
        <div style={styles.usageInfo}>
          {Object.entries(result.usageInfo).map(([k, v]) => (
            <span key={k} style={styles.usageChip}>
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={styles.tabRow}>
        <button
          style={activeTab === "preview" ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab("preview")}
        >
          Preview
        </button>
        <button
          style={activeTab === "raw" ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab("raw")}
        >
          Raw Markdown
        </button>
      </div>

      {/* Content */}
      {activeTab === "preview" ? (
        <div style={styles.pageList}>
          {result.pages.map((page) => (
            <div key={page.index} style={styles.pageItem}>
              <button
                style={styles.pageToggle}
                onClick={() => togglePage(page.index)}
              >
                <span>Page {page.index + 1}</span>
                <div style={styles.pageToggleRight}>
                  {page.hasEmbeddedImages && <span style={styles.imgChip}>🖼 Images</span>}
                  <span style={styles.chevron}>
                    {expandedPages.has(page.index) ? "▲" : "▼"}
                  </span>
                </div>
              </button>
              {expandedPages.has(page.index) && (
                <div
                  style={styles.pageContent}
                  dangerouslySetInnerHTML={{
                    __html: `<p>${markdownToHtml(page.markdown)}</p>`,
                  }}
                />
              )}
            </div>
          ))}
        </div>
      ) : (
        <div style={styles.rawContainer}>
          <button
            style={styles.copyBtn}
            onClick={() => navigator.clipboard.writeText(result.fullMarkdown)}
          >
            Copy
          </button>
          <pre style={styles.rawText}>{result.fullMarkdown}</pre>
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function ParsePage() {
  const [message, setMessage] = useState("");
  const [pastedImages, setPastedImages] = useState<File[]>([]);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [results, setResults] = useState<ParseResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Paste handler (images only) ────────────────────────────────────────────
  const handlePaste = useCallback(
    (e: ClipboardEvent<HTMLTextAreaElement>) => {
      const items = Array.from(e.clipboardData?.items ?? []);
      const imageItems = items.filter((item) => item.kind === "file" && IMAGE_TYPES.has(item.type));
      if (imageItems.length === 0) return;

      e.preventDefault();
      const newImages: File[] = [];

      for (const item of imageItems) {
        const file = item.getAsFile();
        if (!file) continue;
        if (pastedImages.length + newImages.length >= MAX_IMAGES) {
          setError(`Maximum ${MAX_IMAGES} images allowed.`);
          break;
        }
        if (file.size > MAX_FILE_SIZE) {
          setError(`"${file.name}" exceeds 5 MB limit.`);
          continue;
        }
        newImages.push(file);
      }

      if (newImages.length) {
        setPastedImages((prev) => [...prev, ...newImages]);
        setError(null);
      }
    },
    [pastedImages]
  );

  // ── File attach handler ────────────────────────────────────────────────────
  const handleFileAttach = useCallback(
    (files: FileList | null) => {
      if (!files) return;
      const added: File[] = [];
      for (const file of Array.from(files)) {
        if (file.size > MAX_FILE_SIZE) {
          setError(`"${file.name}" exceeds 5 MB limit.`);
          continue;
        }
        // Images via attach also count toward image cap
        if (IMAGE_TYPES.has(file.type)) {
          if (pastedImages.length + added.filter((f) => IMAGE_TYPES.has(f.type)).length >= MAX_IMAGES) {
            setError(`Maximum ${MAX_IMAGES} images allowed.`);
            continue;
          }
        }
        added.push(file);
      }
      if (added.length) {
        setAttachedFiles((prev) => [...prev, ...added]);
        setError(null);
      }
    },
    [pastedImages]
  );

  // ── Drag-and-drop ──────────────────────────────────────────────────────────
  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      handleFileAttach(e.dataTransfer.files);
    },
    [handleFileAttach]
  );

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    const allFiles = [...pastedImages, ...attachedFiles];
    if (allFiles.length === 0) {
      setError("Please attach at least one file or paste an image.");
      return;
    }

    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const formData = new FormData();
      for (const file of allFiles) {
        formData.append("files", file);
      }

      const res = await fetch("/api/parse", { method: "POST", body: formData });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error ?? "Server error");
      }

      setResults(data.results as ParseResult[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [pastedImages, attachedFiles]);

  const totalFiles = pastedImages.length + attachedFiles.length;
  const canSubmit = totalFiles > 0 && !loading;

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        {/* Header */}
        <div style={styles.header}>
          <h1 style={styles.title}>Document Parser</h1>
          <p style={styles.subtitle}>
            PDF & images via <strong>Mistral OCR</strong> · Docs, spreadsheets & slides via{" "}
            <strong>LiteParse</strong>
          </p>
        </div>

        {/* Drop zone + input area */}
        <div
          style={{
            ...styles.inputArea,
            ...(dragOver ? styles.inputAreaDragOver : {}),
          }}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          {/* Pasted images row */}
          {pastedImages.length > 0 && (
            <div style={styles.thumbRow}>
              {pastedImages.map((f, i) => (
                <ImageThumb
                  key={i}
                  file={f}
                  onRemove={() => setPastedImages((prev) => prev.filter((_, idx) => idx !== i))}
                />
              ))}
            </div>
          )}

          {/* Attached non-image files */}
          {attachedFiles.length > 0 && (
            <div style={styles.attachedList}>
              {attachedFiles.map((f, i) => (
                <AttachedFile
                  key={i}
                  file={f}
                  onRemove={() => setAttachedFiles((prev) => prev.filter((_, idx) => idx !== i))}
                />
              ))}
            </div>
          )}

          {/* Text area */}
          <textarea
            style={styles.textarea}
            placeholder={
              totalFiles === 0
                ? "Paste images here with Ctrl+V, or attach files with the + button below…"
                : "Add a note (optional) — press Process to extract text from your files"
            }
            value={message}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setMessage(e.target.value)}
            onPaste={handlePaste}
            rows={3}
          />

          {/* Bottom toolbar */}
          <div style={styles.toolbar}>
            <div style={styles.toolbarLeft}>
              {/* Attach button */}
              <button
                style={styles.attachBtn}
                onClick={() => fileInputRef.current?.click()}
                title="Attach file (PDF, DOCX, XLSX, PPTX, etc.)"
              >
                +
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={ACCEPT_TYPES}
                style={{ display: "none" }}
                onChange={(e: ChangeEvent<HTMLInputElement>) => handleFileAttach(e.target.files)}
                onClick={(e) => { (e.target as HTMLInputElement).value = ""; }}
              />

              {/* Limits hint */}
              <span style={styles.hint}>
                Max 5 MB · PDF ≤ {MAX_PDF_PAGES} pages · Max {MAX_IMAGES} images
              </span>
            </div>

            {/* Process button */}
            <button
              style={{ ...styles.processBtn, opacity: canSubmit ? 1 : 0.45 }}
              disabled={!canSubmit}
              onClick={handleSubmit}
            >
              {loading ? (
                <span style={styles.spinner}>⏳ Processing…</span>
              ) : (
                `Process ${totalFiles > 0 ? `(${totalFiles} file${totalFiles > 1 ? "s" : ""})` : ""}`
              )}
            </button>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div style={styles.errorBanner}>
            <span>⚠️ {error}</span>
            <button style={styles.errorClose} onClick={() => setError(null)}>×</button>
          </div>
        )}

        {/* Results */}
        {results && (
          <div style={styles.results}>
            <div style={styles.resultsHeader}>
              <span style={styles.resultsTitle}>
                Results · {results.length} file{results.length !== 1 ? "s" : ""}
              </span>
              <button
                style={styles.clearBtn}
                onClick={() => {
                  setResults(null);
                  setPastedImages([]);
                  setAttachedFiles([]);
                  setMessage("");
                }}
              >
                Clear all
              </button>
            </div>
            {results.map((r, i) => (
              <ResultCard key={i} result={r} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "#0f0f10",
    color: "#e2e8f0",
    fontFamily: "'Inter', system-ui, sans-serif",
    padding: "24px 16px 80px",
  },
  container: {
    maxWidth: 780,
    margin: "0 auto",
  },
  header: {
    textAlign: "center",
    marginBottom: 32,
  },
  title: {
    fontSize: 26,
    fontWeight: 700,
    color: "#f8fafc",
    margin: "0 0 6px",
    letterSpacing: "-0.5px",
  },
  subtitle: {
    fontSize: 13,
    color: "#64748b",
    margin: 0,
  },

  // Input area
  inputArea: {
    background: "#18181b",
    border: "1.5px solid #27272a",
    borderRadius: 14,
    padding: "14px 14px 10px",
    transition: "border-color 0.15s",
  },
  inputAreaDragOver: {
    borderColor: "#f97316",
    background: "#1c1917",
  },

  // Thumbnail row (pasted images)
  thumbRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
    marginBottom: 10,
  },
  thumb: {
    position: "relative",
    width: 72,
    height: 72,
    borderRadius: 8,
    overflow: "hidden",
    border: "1px solid #3f3f46",
    flexShrink: 0,
  },
  thumbImg: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  thumbRemove: {
    position: "absolute",
    top: 2,
    right: 2,
    background: "rgba(0,0,0,0.7)",
    color: "#fff",
    border: "none",
    borderRadius: "50%",
    width: 18,
    height: 18,
    fontSize: 13,
    lineHeight: "18px",
    textAlign: "center",
    cursor: "pointer",
    padding: 0,
  },
  thumbName: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    background: "rgba(0,0,0,0.6)",
    fontSize: 9,
    color: "#fff",
    padding: "2px 4px",
    textAlign: "center",
  },

  // Attached non-image files
  attachedList: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    marginBottom: 10,
  },
  attachedFile: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "#27272a",
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 13,
  },
  attachedIcon: { fontSize: 16 },
  attachedName: {
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: "#e2e8f0",
  },
  attachedSize: { color: "#52525b", fontSize: 12, flexShrink: 0 },
  attachedRemove: {
    background: "none",
    border: "none",
    color: "#71717a",
    cursor: "pointer",
    fontSize: 16,
    lineHeight: 1,
    padding: "0 2px",
    flexShrink: 0,
  },

  // Textarea
  textarea: {
    width: "100%",
    background: "transparent",
    border: "none",
    outline: "none",
    color: "#e2e8f0",
    fontSize: 14,
    lineHeight: 1.6,
    resize: "none",
    fontFamily: "inherit",
    boxSizing: "border-box",
    padding: "2px 0",
  },

  // Toolbar
  toolbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 10,
    gap: 12,
  },
  toolbarLeft: {
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  attachBtn: {
    width: 32,
    height: 32,
    borderRadius: "50%",
    border: "1.5px solid #3f3f46",
    background: "#27272a",
    color: "#a1a1aa",
    fontSize: 20,
    lineHeight: "30px",
    textAlign: "center",
    cursor: "pointer",
    padding: 0,
    flexShrink: 0,
    transition: "border-color 0.15s, color 0.15s",
  },
  hint: {
    fontSize: 11,
    color: "#52525b",
  },
  processBtn: {
    background: "#f97316",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    padding: "8px 18px",
    fontWeight: 600,
    fontSize: 13,
    cursor: "pointer",
    transition: "opacity 0.15s",
    whiteSpace: "nowrap",
    flexShrink: 0,
  },
  spinner: { fontStyle: "normal" },

  // Error banner
  errorBanner: {
    marginTop: 12,
    background: "#451a1a",
    border: "1px solid #7f1d1d",
    borderRadius: 8,
    padding: "10px 14px",
    fontSize: 13,
    color: "#fca5a5",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  errorClose: {
    background: "none",
    border: "none",
    color: "#fca5a5",
    cursor: "pointer",
    fontSize: 18,
    lineHeight: 1,
    padding: 0,
    flexShrink: 0,
  },

  // Results section
  results: {
    marginTop: 28,
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  resultsHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  resultsTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: "#94a3b8",
    letterSpacing: "0.02em",
    textTransform: "uppercase",
  },
  clearBtn: {
    background: "none",
    border: "1px solid #3f3f46",
    borderRadius: 6,
    color: "#71717a",
    cursor: "pointer",
    fontSize: 12,
    padding: "4px 10px",
  },

  // Result card
  card: {
    background: "#18181b",
    border: "1px solid #27272a",
    borderRadius: 12,
    overflow: "hidden",
  },
  cardHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: 8,
    padding: "14px 16px",
    borderBottom: "1px solid #27272a",
  },
  cardTitle: {
    fontWeight: 600,
    fontSize: 14,
    color: "#f1f5f9",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: "60%",
  },
  badgeRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexWrap: "wrap",
  },
  badge: {
    borderRadius: 20,
    padding: "2px 9px",
    fontSize: 11,
    fontWeight: 600,
    color: "#fff",
  },
  badge2: {
    borderRadius: 20,
    padding: "2px 9px",
    fontSize: 11,
    background: "#27272a",
    color: "#94a3b8",
  },
  errorBadge: {
    borderRadius: 20,
    padding: "2px 9px",
    fontSize: 11,
    fontWeight: 600,
    background: "#ef4444",
    color: "#fff",
  },
  errorText: {
    padding: "12px 16px",
    fontSize: 13,
    color: "#fca5a5",
    margin: 0,
  },
  warningBanner: {
    background: "#451a00",
    borderBottom: "1px solid #92400e",
    padding: "8px 16px",
    fontSize: 12,
    color: "#fcd34d",
  },
  usageInfo: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    padding: "8px 16px",
    borderBottom: "1px solid #27272a",
  },
  usageChip: {
    fontSize: 11,
    background: "#1e293b",
    color: "#64748b",
    borderRadius: 20,
    padding: "2px 8px",
  },

  // Tabs
  tabRow: {
    display: "flex",
    borderBottom: "1px solid #27272a",
    padding: "0 16px",
  },
  tab: {
    background: "none",
    border: "none",
    borderBottom: "2px solid transparent",
    color: "#52525b",
    cursor: "pointer",
    fontSize: 13,
    padding: "10px 14px 9px",
    fontFamily: "inherit",
    transition: "color 0.1s",
  },
  tabActive: {
    background: "none",
    border: "none",
    borderBottom: "2px solid #f97316",
    color: "#f97316",
    cursor: "pointer",
    fontSize: 13,
    padding: "10px 14px 9px",
    fontFamily: "inherit",
    fontWeight: 600,
  },

  // Page list
  pageList: {
    padding: "12px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  pageItem: {
    border: "1px solid #27272a",
    borderRadius: 8,
    overflow: "hidden",
  },
  pageToggle: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "#1e1e21",
    border: "none",
    color: "#94a3b8",
    cursor: "pointer",
    padding: "9px 14px",
    fontSize: 13,
    fontFamily: "inherit",
    textAlign: "left",
  },
  pageToggleRight: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  imgChip: {
    fontSize: 10,
    background: "#172554",
    color: "#60a5fa",
    borderRadius: 20,
    padding: "1px 7px",
  },
  chevron: {
    fontSize: 10,
    color: "#52525b",
  },
  pageContent: {
    padding: "14px 16px",
    fontSize: 14,
    lineHeight: 1.7,
    color: "#cbd5e1",
    overflowX: "auto",
  },

  // Raw markdown
  rawContainer: {
    position: "relative",
    margin: "12px 16px",
  },
  copyBtn: {
    position: "absolute",
    top: 8,
    right: 8,
    background: "#27272a",
    border: "1px solid #3f3f46",
    borderRadius: 6,
    color: "#94a3b8",
    cursor: "pointer",
    fontSize: 12,
    padding: "4px 10px",
  },
  rawText: {
    background: "#09090b",
    border: "1px solid #27272a",
    borderRadius: 8,
    color: "#94a3b8",
    fontSize: 12,
    lineHeight: 1.6,
    maxHeight: 400,
    overflow: "auto",
    padding: "14px 16px",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    margin: 0,
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  },
};