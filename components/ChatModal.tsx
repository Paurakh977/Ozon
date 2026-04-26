'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { marked } from 'marked';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { motion, AnimatePresence, type Variants, type Transition } from 'framer-motion';
import { MathExpression } from "./calculator/types";
import { authClient, useSession as useAuthSession } from "@/lib/auth-client";

// --- Utility ---
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ─── Configure marked ───────────────────────────────────────────────
marked.setOptions({ breaks: true });

// ─── Robust math + markdown renderer ─────────────────────────────────────────
function renderContent(text: string): string {
  // Step 0: Fix unclosed inline math
  text = text.replace(/^((?:[^$\n]|\$\$)*[^$\n\\])\$([^$\n]+)$/gm, (line, pre, tex) => {
    const dollarCount = (line.match(/(?<!\\)\$/g) || []).length;
    if (dollarCount % 2 === 1) return `${pre}$${tex}$`;
    return line;
  });
  text = text.replace(/\$(\\displaystyle\b[^$\n]+)(?!\$)/g, (_, tex) => `$${tex}$`);

  // Step 1: Protect math, replace with placeholders
  const segments: string[] = [];
  const protected_ = text.replace(
    /(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|(?<!\\)\$[^\n$]*?(?<!\\)\$)/g,
    (m) => { segments.push(m); return `%%%M${segments.length - 1}%%%`; }
  );

  // Step 2: Markdown → HTML
  let html = marked.parse(protected_) as string;

  html = html.replace(/<table\b[^>]*>[\s\S]*?<\/table>/gi, (match) => {
    return `<div class="overflow-x-auto max-w-full w-full pb-2 custom-scrollbar">${match}</div>`;
  });

  // Step 3: Restore placeholders with KaTeX HTML
  html = html.replace(/%%%M(\d+)%%%/g, (_, i) => {
    const raw = segments[+i];
    let math = raw, display = false;
    if (raw.startsWith('$$')) { math = raw.slice(2, -2); display = true; }
    else if (raw.startsWith('\\[')) { math = raw.slice(2, -2); display = true; }
    else if (raw.startsWith('\\(')) { math = raw.slice(2, -2); }
    else if (raw.startsWith('$')) { math = raw.slice(1, -1); }

    // Unescape markdown formatting characters if the LLM placed them inside math wrappers
    math = math.replace(/\\\*/g, '*').replace(/\\_/g, '_');

    try {
      return katex.renderToString(math, { displayMode: display, throwOnError: false });
    } catch {
      return raw;
    }
  });

  return html;
}

// --- Types ---
type MessageAttachment = {
  id: string;
  name: string;
  size: number;
  mimeType: string;
  previewUrl?: string; // objectURL or dataURI
};

type Message = {
  role: 'user' | 'agent';
  content: string;
  isStreaming?: boolean;
  attachments?: MessageAttachment[];
};
type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

export interface AttachedFile {
  id: string;
  file: File;
  mimeType: string;
  previewUrl?: string; // object URL for images
  ocrState: 'pending' | 'processing' | 'done' | 'error';
  ocrMarkdown?: string;
  ocrError?: string;
  engine?: string;
  abortController: AbortController;
}

const MAX_IMAGES = 5;
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB
const MAX_TOTAL_FILES = 10;
const IMAGE_TYPES = new Set([
  'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/avif', 'image/gif'
]);
const ACCEPT_TYPES = [
  '.pdf', '.png', '.jpg', '.jpeg', '.webp', '.avif', '.gif',
  '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt',
  '.txt', '.csv', '.html', '.odt', '.ods', '.odp', '.rtf'
].join(',');

function getFileIcon(mime: string) {
  if (mime === 'application/pdf') return '📄';
  if (mime.includes('word') || mime.includes('odt') || mime.includes('rtf')) return '📝';
  if (mime.includes('sheet') || mime.includes('excel') || mime.includes('ods') || mime.includes('csv')) return '📊';
  if (mime.includes('presentation') || mime.includes('powerpoint') || mime.includes('odp')) return '📊';
  return '📎';
}


// --- Framer Motion Variants ---
const springTrans: Transition = { type: 'spring', stiffness: 340, damping: 28 };

const msgVariants: Variants = {
  hidden: { opacity: 0, y: 16, scale: 0.98 },
  visible: { opacity: 1, y: 0, scale: 1, transition: springTrans },
  exit: { opacity: 0, y: -8, transition: { duration: 0.18 } },
};

const emptyStateVariants: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { delay: 0.1, duration: 0.6, ease: [0.22, 1, 0.36, 1] as any } },
};

function getDotAnim(i: number) {
  return {
    animate: {
      y: [0, -5, 0] as number[],
      transition: { duration: 0.7, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' } as Transition,
    },
  };
}

// Maximum continuous recording per session (ms). After this the recorder is auto-stopped.
const MAX_RECORD_MS = 2 * 60 * 1000; // 2 minutes

const AgentContent = React.memo(function AgentContent({ content, isUser }: { content: string; isUser: boolean }) {
  const html = useMemo(() => renderContent(content), [content]);
  return (
    <div
      className={cn(
        'text-[14px] leading-[1.6] prose max-w-none break-words',
        // KaTeX display-mode overflow
        '[&_.katex-display]:my-3 [&_.katex-display]:overflow-x-auto [&_.katex-display]:overflow-y-hidden',
        // Code block styling
        '[&_pre]:bg-[#1e1e1e] [&_pre]:text-[#d4d4d4] [&_pre]:p-2.5 [&_pre]:rounded-md [&_pre]:overflow-x-auto [&_pre]:text-[12px] [&_pre]:my-2',
        '[&_code]:bg-zinc-100 [&_code]:dark:bg-zinc-800 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[0.875em] [&_code]:font-mono',
        '[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-inherit',
        // Table styling
        '[&_table]:border-collapse [&_table]:my-0 [&_table]:text-[13px] [&_table]:w-full [&_table]:min-w-[max-content]',
        '[&_th]:border [&_th]:border-zinc-300 [&_th]:dark:border-zinc-600 [&_th]:px-3 [&_th]:py-2.5 [&_th]:bg-zinc-50 [&_th]:dark:bg-zinc-800 [&_th]:font-semibold [&_th]:text-left [&_th]:whitespace-nowrap',
        '[&_td]:border [&_td]:border-zinc-300 [&_td]:dark:border-zinc-600 [&_td]:px-3 [&_td]:py-2.5',
        isUser
          ? 'prose-invert prose-p:text-white/90 prose-headings:text-white'
          : [
            'prose-zinc dark:prose-invert',
            'prose-p:text-zinc-700 dark:prose-p:text-zinc-300',
            'prose-headings:font-semibold prose-headings:tracking-tight prose-headings:text-[1.1em] prose-headings:mt-4 prose-headings:mb-2',
            'prose-headings:text-zinc-900 dark:prose-headings:text-zinc-100',
            'prose-code:text-violet-600 dark:prose-code:text-violet-400',
            'prose-strong:text-zinc-900 dark:prose-strong:text-zinc-100',
            'prose-a:text-violet-600 dark:prose-a:text-violet-400',
            'prose-blockquote:border-violet-400 dark:prose-blockquote:border-violet-500',
          ].join(' '),
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
});

const ChatMessage = React.memo(({ msg, i }: { msg: Message, i: number }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div
      key={i}
      variants={msgVariants}
      initial="hidden"
      animate="visible"
      className={cn('flex w-full group', msg.role === 'user' ? 'justify-end' : 'justify-start')}
    >
      {/* Avatar dot */}
      {msg.role === 'agent' && (
        <div className="flex-none mr-2 mt-1">
          <div className="w-6 h-6 rounded-full flex items-center justify-center
            bg-gradient-to-br from-violet-500 to-indigo-600 dark:from-violet-600 dark:to-indigo-700
            text-white shadow-sm">
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l2.4 7.6A2 2 0 0 0 16.4 12l7.6 2.4-7.6 2.4a2 2 0 0 0-2 2L12 22l-2.4-7.6a2 2 0 0 0-2-2L0 12l7.6-2.4a2 2 0 0 0 2-2z" />
            </svg>
          </div>
        </div>
      )}

      <div className={cn(
        'relative min-w-0',
        msg.role === 'user'
          ? 'max-w-[75%]'
          : 'max-w-[85%] flex-1',
      )}>
        <div className={cn(
          'rounded-2xl px-4 py-3',
          msg.role === 'user'
            ? [
              'rounded-tr-sm',
              'bg-gradient-to-br from-zinc-900 to-zinc-800',
              'dark:from-zinc-100 dark:to-zinc-200',
              'text-white dark:text-zinc-900',
              'shadow-sm',
            ].join(' ')
            : [
              'rounded-tl-sm',
              'bg-white dark:bg-zinc-900/80',
              'border border-zinc-200/70 dark:border-zinc-700/40',
              'shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)]',
            ].join(' '),
        )}>
          {msg.attachments && msg.attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {msg.attachments.map(att => (
                <div 
                  key={att.id}
                  className="flex items-center bg-black/20 dark:bg-white/10 rounded-lg p-1.5 cursor-pointer hover:bg-black/30 dark:hover:bg-white/20 transition-colors"
                  onClick={() => {
                    if (att.previewUrl) window.open(att.previewUrl, '_blank');
                  }}
                  title={att.name}
                >
                  {IMAGE_TYPES.has(att.mimeType) && att.previewUrl ? (
                    <img src={att.previewUrl} alt={att.name} className="w-8 h-8 rounded object-cover mr-2" />
                  ) : (
                    <span className="text-xl ml-1 mr-2">{getFileIcon(att.mimeType)}</span>
                  )}
                  <div className="flex flex-col min-w-0 pr-2">
                    <span className="text-[11px] font-medium truncate max-w-[120px] text-white/90 dark:text-black/90 leading-tight">
                      {att.name}
                    </span>
                    <span className="text-[9px] text-white/50 dark:text-black/50 uppercase tracking-widest mt-0.5">
                      {(att.size / 1024).toFixed(0)} KB
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          <AgentContent content={msg.content} isUser={msg.role === 'user'} />

          <div className={cn(
            "absolute bottom-1 right-2 h-4 flex items-center transition-opacity duration-300",
            "opacity-0 group-hover:opacity-100"
          )}>
            <button
              onClick={handleCopy}
              className={cn(
                "flex items-center gap-1 text-[9px] font-medium tracking-tight group/btn",
                msg.role === 'user' ? "text-white/40 hover:text-white" : "text-zinc-400 hover:text-violet-500"
              )}
            >
              <AnimatePresence mode="wait" initial={false}>
                {copied ? (
                  <motion.span
                    key="copied"
                    initial={{ opacity: 0, y: 2 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -2 }}
                    className={msg.role === 'user' ? "text-white" : "text-emerald-500"}
                  >
                    Copied
                  </motion.span>
                ) : (
                  <motion.div
                    key="copy"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="flex items-center gap-1 bg-white/70 dark:bg-zinc-900/70 backdrop-blur rounded px-1"
                  >
                    <svg className="w-2.5 h-2.5 transition-transform group-hover/btn:scale-110" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </motion.div>
                )}
              </AnimatePresence>
            </button>
          </div>

          {msg.isStreaming && (
            <div className="flex items-center gap-1 mt-2 ml-0.5">
              {[0, 1, 2].map((j) => (
                <motion.span
                  key={j}
                  animate={getDotAnim(j).animate}
                  className="w-1.5 h-1.5 rounded-full bg-violet-400 dark:bg-violet-500 block"
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
});

const ChatInput = React.memo(({
  input,
  setInput,
  handleSend,
  handleKeyDown,
  isBusy,
  status,
  textareaRef,
  isRecording,
  toggleRecording,
  attachments,
  addFiles,
  removeAttachment,
  openPreview
}: {
  input: string;
  setInput: (v: string) => void;
  handleSend: () => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  isBusy: boolean;
  status: ConnectionStatus;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  isRecording: boolean;
  toggleRecording: () => void;
  attachments: AttachedFile[];
  addFiles: (files: File[]) => void;
  removeAttachment: (id: string) => void;
  openPreview: (att: AttachedFile) => void;
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isProcessingAnything = attachments.some(a => a.ocrState === 'pending' || a.ocrState === 'processing');

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    const files = items
      .filter(item => item.kind === 'file' && IMAGE_TYPES.has(item.type))
      .map(item => item.getAsFile())
      .filter((f): f is File => f !== null);

    if (files.length > 0) {
      e.preventDefault();
      addFiles(files);
    }
  }, [addFiles]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      addFiles(Array.from(e.target.files));
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [addFiles]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files?.length) {
      addFiles(Array.from(e.dataTransfer.files));
    }
  }, [addFiles]);

  return (
    <div 
      className="p-3 bg-zinc-50 dark:bg-zinc-900/80 border-t border-zinc-200/50 dark:border-zinc-800/50"
      onDragOver={e => e.preventDefault()}
      onDrop={handleDrop}
    >
      <div className={cn(
        'relative flex flex-col gap-2 w-full rounded-xl p-2 transition-all duration-300',
        'bg-white dark:bg-zinc-800/50',
        'border border-zinc-200/80 dark:border-zinc-700/50',
        'shadow-sm focus-within:border-violet-300 dark:focus-within:border-violet-600/60',
      )}>
        {attachments.length > 0 && (
          <div className="flex gap-2 w-full overflow-x-auto pb-1 custom-scrollbar items-center px-1">
            {attachments.map(att => (
              <div 
                key={att.id} 
                className={cn(
                  "relative flex-shrink-0 rounded-lg overflow-hidden border cursor-pointer",
                  att.ocrState === 'error' ? 'border-red-500' : 'border-zinc-300 dark:border-zinc-600'
                )}
                onClick={() => openPreview(att)}
                title={att.file.name}
              >
                {att.mimeType.startsWith('image/') && att.previewUrl ? (
                  <div className="w-14 h-14 relative">
                    <img src={att.previewUrl} alt={att.file.name} className="w-full h-full object-cover opacity-90 hover:opacity-100 transition-opacity" />
                  </div>
                ) : (
                  <div className="flex items-center gap-2 bg-zinc-100 dark:bg-zinc-900 px-2 py-1 h-14 min-w-[120px] max-w-[180px]">
                    <span className="text-xl flex-shrink-0">{getFileIcon(att.mimeType)}</span>
                    <div className="flex flex-col min-w-0 overflow-hidden">
                      <span className="text-xs truncate font-medium text-zinc-700 dark:text-zinc-300">{att.file.name}</span>
                      <span className="text-[10px] text-zinc-500">{(att.file.size / 1024).toFixed(0)} KB</span>
                    </div>
                  </div>
                )}
                
                {/* Status Overlay */}
                <div className="absolute top-1 right-1 flex items-center justify-center p-0.5 rounded-full bg-black/50 backdrop-blur-sm">
                  {att.ocrState === 'processing' && <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin block" />}
                  {att.ocrState === 'done' && <span className="text-[10px] leading-none text-emerald-400 font-bold px-0.5">✓</span>}
                  {att.ocrState === 'error' && <span className="text-[10px] leading-none text-red-400 font-bold px-0.5">!</span>}
                </div>

                <button 
                  onClick={(e) => { e.stopPropagation(); removeAttachment(att.id); }}
                  className="absolute top-1 left-1 bg-black/60 hover:bg-black text-white rounded-full w-4 h-4 flex items-center justify-center text-[10px] transition-colors"
                >
                  ×
                </button>

                {att.mimeType === 'application/pdf' && (
                  <span className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-[8px] text-center py-0.5 truncate px-1">
                    First 5 pages
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2 w-full px-1">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={status !== 'connected' || isBusy || attachments.length >= MAX_TOTAL_FILES}
            className="flex-none mb-0.5 w-8 h-8 rounded-lg flex items-center justify-center bg-transparent text-zinc-400 dark:text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors relative"
            title="Attach file"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            {attachments.length > 0 && (
              <span className="absolute -top-1 -right-1 bg-violet-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
                {attachments.length}
              </span>
            )}
          </button>
          <input type="file" hidden multiple ref={fileInputRef} accept={ACCEPT_TYPES} onChange={handleFileChange} />

          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            disabled={status !== 'connected'}
            placeholder="Ask a math question..."
            className={cn(
              'flex-1 min-h-[36px] max-h-[120px] resize-none bg-transparent',
              'py-1.5 px-2 text-[14px] leading-relaxed',
              'text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-500',
              'focus:outline-none disabled:opacity-40',
            )}
          />

          <motion.button
            onClick={toggleRecording}
            disabled={status !== 'connected' || isBusy}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.93 }}
            className={cn(
              'flex-none mb-0.5 w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200',
              isRecording 
                ? 'bg-red-500/15 text-red-500 dark:bg-red-500/20 shadow-sm animate-pulse' 
                : 'bg-transparent text-zinc-400 dark:text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800'
            )}
            title={isRecording ? "Stop Dictation" : "Voice Typing"}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
              {isRecording ? (
                <rect x="7" y="7" width="10" height="10" rx="1.5" />
              ) : (
                <>
                  <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Zm5-3a1 1 0 0 1 2 0 7 7 0 0 1-14 0 1 1 0 0 1 2 0 5 5 0 0 0 10 0Z" />
                  <path d="M12 21a1 1 0 0 1-1-1v-2a1 1 0 1 1 2 0v2a1 1 0 0 1-1 1Z" />
                </>
              )}
            </svg>
          </motion.button>

          <motion.button
            onClick={handleSend}
            disabled={(!input.trim() && attachments.length === 0) || isBusy || status !== 'connected' || isProcessingAnything}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.93 }}
            className={cn(
              'flex-none mb-0.5 w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200',
              (input.trim() || attachments.length > 0) && !isBusy && status === 'connected' && !isProcessingAnything
                ? 'bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 shadow-sm'
                : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-300 dark:text-zinc-600 cursor-not-allowed',
            )}
          >
            <AnimatePresence mode="wait" initial={false}>
              {isBusy ? (
                <motion.span key="spin" initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.6 }} className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin block" />
              ) : (
                <motion.svg key="send" initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.6 }} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                  <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
                </motion.svg>
              )}
            </AnimatePresence>
          </motion.button>
        </div>
        {isProcessingAnything && (
          <div className="absolute -top-6 left-2 right-2 text-xs text-amber-600 dark:text-amber-500 font-medium">
             ⏳ Processing attachments...
          </div>
        )}
      </div>
      <p className="mt-2 mb-0.5 text-center text-[9px] font-medium tracking-widest uppercase text-zinc-400 dark:text-zinc-500 select-none">
        {status === 'connected' ? 'Agent Online' : status === 'connecting' ? 'Connecting…' : 'Agent Offline'}
      </p>
    </div>
  );
});

const ScrollToBottomButton = React.memo(({ scrollRef, onClick }: { scrollRef: React.RefObject<HTMLDivElement | null>; onClick: () => void }) => {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = el;
      const isPinned = scrollHeight - scrollTop - clientHeight < 80;
      setShow(!isPinned);
    };
    onScroll();
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, [scrollRef]);

  return (
    <AnimatePresence>
      {show && (
        <motion.button
          initial={{ opacity: 0, y: 10, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.9 }}
          onClick={onClick}
          className="absolute bottom-[90px] left-1/2 -translate-x-1/2 z-[70] p-2 rounded-full bg-white dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 shadow-[0_4px_16px_rgba(0,0,0,0.12)] border border-zinc-200 dark:border-zinc-700 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        </motion.button>
      )}
    </AnimatePresence>
  );
});

export function ChatModal({ 
  actions, 
  expressions 
}: { 
  actions?: { 
    addExpr: (initialLatex?: string, color?: string) => void;
    updateSliderBounds: (id: string, min: string, max: string, step?: string) => void;
    removeExpr: (id: string) => void;
  };
  expressions?: MathExpression[];
}) {
  if (!process.env.NEXT_PUBLIC_API_URL) {
    throw new Error('NEXT_PUBLIC_API_URL environment variable is required');
  }

  const [isOpen, setIsOpen] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);

  const [dimensions, setDimensions] = useState({ width: 380, height: 550 });
  const isResizingRef = useRef<'width' | 'height' | 'both' | null>(null);

  // Maintain refs for actions and expressions to avoid stale closures in websocket
  const actionsRef = useRef(actions);
  const expressionsRef = useRef(expressions);

  useEffect(() => {
    actionsRef.current = actions;
    expressionsRef.current = expressions;
  }, [actions, expressions]);

  const startResize = useCallback((e: React.MouseEvent, type: 'width' | 'height' | 'both') => {
    e.preventDefault();
    isResizingRef.current = type;
    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = dimensions.width;
    const startHeight = dimensions.height;

    const onMouseMove = (e: MouseEvent) => {
      if (!isResizingRef.current) return;
      // Because it's anchored at bottom-right, moving mouse left (negative deltaX) increases width
      const deltaX = startX - e.clientX;
      const deltaY = startY - e.clientY;

      let newWidth = startWidth;
      let newHeight = startHeight;

      if (isResizingRef.current === 'both' || isResizingRef.current === 'width') {
        newWidth = Math.max(320, Math.min(window.innerWidth - 32, startWidth + deltaX));
      }
      if (isResizingRef.current === 'both' || isResizingRef.current === 'height') {
        newHeight = Math.max(400, Math.min(window.innerHeight - 32, startHeight + deltaY));
      }

      setDimensions({ width: newWidth, height: newHeight });
    };

    const onMouseUp = () => {
      isResizingRef.current = null;
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = 'default';
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);

    if (type === 'both') document.body.style.cursor = 'nwse-resize';
    else if (type === 'width') document.body.style.cursor = 'ew-resize';
    else if (type === 'height') document.body.style.cursor = 'ns-resize';
  }, [dimensions]);

  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [reasoningEffort, setReasoningEffort] = useState<'low' | 'medium' | 'high'>('medium');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isBusy, setIsBusy] = useState(false);
  const {
    data: sessionData,
    error: sessionError,
    isPending: isSessionPending,
  } = useAuthSession();
  const sessionErrorStatus =
    typeof sessionError === 'object' && sessionError !== null
      ? (
        (sessionError as { status?: number; error?: { status?: number } }).status
        ?? (sessionError as { status?: number; error?: { status?: number } }).error?.status
      )
      : undefined;

  // --- Attachments State ---
  const [attachments, setAttachments] = useState<AttachedFile[]>([]);

  const processFile = useCallback(async (id: string, file: File, controller: AbortController) => {
    try {
      const fd = new FormData();
      fd.append('file', file);
      
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/parse`, {
        method: 'POST',
        body: fd,
        credentials:"include",
        signal: controller.signal
      });
      
      if (!res.ok) {
        let errMsg = `Server returned ${res.status}`;
        try {
          const errData = await res.json();
          if (errData.error) errMsg = errData.error;
        } catch { /* ignore */ }
        throw new Error(errMsg);
      }
      
      const data = await res.json();
      const result = data.results[0];
      
      if (result.status === 'error') {
        throw new Error(result.error);
      }

      setAttachments(prev => prev.map(a => a.id === id ? {
        ...a,
        ocrState: 'done',
        ocrMarkdown: result.fullMarkdown,
        engine: result.engine
      } : a));
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setAttachments(prev => prev.map(a => a.id === id ? {
        ...a,
        ocrState: 'error',
        ocrError: err.message
      } : a));
    }
  }, []);

  const addFiles = useCallback((files: File[]) => {
    const newFiles = files.filter(f => {
      const mime = f.type || 'application/octet-stream';
      if (f.size > MAX_FILE_SIZE) {
        alert(`File ${f.name} is too large (max 5MB)`);
        return false;
      }
      return true;
    });

    if (!newFiles.length) return;

    setAttachments(prev => {
      const currentImageCount = prev.filter(a => IMAGE_TYPES.has(a.mimeType)).length;
      const newImages = newFiles.filter(f => IMAGE_TYPES.has(f.type || 'application/octet-stream'));
      
      let allowedNewFiles = newFiles;
      
      if (currentImageCount + newImages.length > MAX_IMAGES) {
        alert(`Maximum ${MAX_IMAGES} images allowed in a single message.`);
        let imgBudget = MAX_IMAGES - currentImageCount;
        allowedNewFiles = newFiles.filter(f => {
          if (IMAGE_TYPES.has(f.type || 'application/octet-stream')) {
            if (imgBudget > 0) { imgBudget--; return true; }
            return false;
          }
          return true;
        });
      }

      if (prev.length + allowedNewFiles.length > MAX_TOTAL_FILES) {
        alert(`Maximum ${MAX_TOTAL_FILES} files allowed in a single message.`);
        allowedNewFiles = allowedNewFiles.slice(0, Math.max(0, MAX_TOTAL_FILES - prev.length));
      }

      const toAdd = allowedNewFiles.map(f => {
        const id = crypto.randomUUID();
        const isImg = IMAGE_TYPES.has(f.type || 'application/octet-stream');
        const abortController = new AbortController();
        
        return {
          id,
          file: f,
          mimeType: f.type || 'application/octet-stream',
          previewUrl: isImg ? URL.createObjectURL(f) : undefined,
          ocrState: 'processing',
          abortController
        } as AttachedFile;
      });

      // Start processing immediately
      toAdd.forEach(att => processFile(att.id, att.file, att.abortController));

      return [...prev, ...toAdd];
    });
  }, [processFile]);

  const removeAttachment = useCallback((id: string) => {
    setAttachments(prev => {
      const att = prev.find(a => a.id === id);
      if (att) {
        att.abortController.abort();
        if (att.previewUrl) URL.revokeObjectURL(att.previewUrl);
      }
      return prev.filter(a => a.id !== id);
    });
  }, []);

  const openPreview = useCallback((att: AttachedFile) => {
    if (IMAGE_TYPES.has(att.mimeType) && att.previewUrl) {
      window.open(att.previewUrl, '_blank');
    } else if (att.mimeType === 'application/pdf' || att.mimeType.match(/text|csv|html/)) {
      const url = URL.createObjectURL(att.file);
      window.open(url, '_blank');
      // Intentionally not revoking immediately so the new window can load it
    } else {
      // DOCX, XLSX, PPTX, etc (LiteParse)
      const win = window.open('', '_blank');
      if (win) {
        win.document.write(`
          <html>
            <head><title>Preview - ${att.file.name}</title></head>
            <body style="font-family: system-ui, sans-serif; padding: 2rem; color: #3f3f46;">
              <h2 style="color: #18181b;">${att.file.name}</h2>
              <p style="font-size: 14px; margin-bottom: 2rem;">Size: ${(att.file.size / 1024).toFixed(2)} KB | Engine: ${att.engine || 'Pending/Unavailable'}</p>
              ${
                att.ocrState === 'processing' ? '<p>Still processing...</p>' :
                att.ocrState === 'error' ? `<p style="color: red;">Error: ${att.ocrError}</p>` :
                att.ocrMarkdown ? `<div style="background: #f4f4f5; padding: 1.5rem; border-radius: 8px; font-size: 14px; white-space: pre-wrap; font-family: monospace;">${att.ocrMarkdown}</div>` : 
                '<p>Preview not available for this file type.</p>'
              }
            </body>
          </html>
        `);
        win.document.close();
      }
    }
  }, []);

  // Cleanup all attachments when modal is closed
  useEffect(() => {
    if (!isOpen) {
      setAttachments(prev => {
        prev.forEach(att => {
          att.abortController.abort();
          if (att.previewUrl) URL.revokeObjectURL(att.previewUrl);
        });
        return [];
      });
    }
  }, [isOpen]);

  // --- Voice State ---
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const deepgramSocketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const finalTranscriptRef = useRef<string>('');
  // Timer that forces recording stop after MAX_RECORD_MS
  const stopRecordingTimerRef = useRef<number | null>(null);
  
  // Keep an up-to-date ref of input so toggleRecording doesn't re-create endlessly
  const currentInputRef = useRef(input);
  useEffect(() => { currentInputRef.current = input; }, [input]);


  //  Reusable stop function to cleanly cut the WebSocket and Mic
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    }
    if (deepgramSocketRef.current) {
      if (deepgramSocketRef.current.readyState === WebSocket.OPEN) {
        deepgramSocketRef.current.send(new Uint8Array(0));
      }
      deepgramSocketRef.current.close();
      deepgramSocketRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    // clear any outstanding auto-stop timer
    if (stopRecordingTimerRef.current) {
      clearTimeout(stopRecordingTimerRef.current);
      stopRecordingTimerRef.current = null;
    }
    setIsRecording(false);
  },[]);
  
  const toggleRecording = useCallback(async () => {
    // 1. Stop Recording logic (delegate to shared cleanup)
    if (isRecording) {
      stopRecording();
      return;
    }

    // 2. Start Recording logic
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/stt`, {
        credentials: 'include',  // <-- Add this
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error((data && (data.error || data.message)) || 'Failed to fetch temporary key.');
      }

      if (!data.key) throw new Error('Could not retrieve Deepgram temporary key.');

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      
      const params = new URLSearchParams({
        model: 'nova-3',
        language: 'en',
        smart_format: 'true',
        interim_results: 'true',
        endpointing: '10',
        numerals: 'true'
      });

      const socket = new WebSocket(`wss://api.deepgram.com/v1/listen?${params.toString()}`, ['token', data.key]);
      deepgramSocketRef.current = socket;

      // Preserve any text already typed before we started speaking
      finalTranscriptRef.current = currentInputRef.current ? currentInputRef.current + ' ' : '';

      socket.onopen = () => {
        setIsRecording(true);
        const mediaRecorder = new MediaRecorder(stream);
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.addEventListener('dataavailable', (event) => {
          if (event.data.size > 0 && socket.readyState === WebSocket.OPEN) {
            socket.send(event.data);
          }
        });
        mediaRecorder.start(250);

        // Start an auto-stop timer to ensure sessions can't run indefinitely
        if (stopRecordingTimerRef.current) {
          clearTimeout(stopRecordingTimerRef.current);
          stopRecordingTimerRef.current = null;
        }
        stopRecordingTimerRef.current = window.setTimeout(() => {
          stopRecording();
          setMessages((prev) => [...prev, { role: 'agent', content: '**Notice:** Recording stopped after 2 minutes.' }]);
        }, MAX_RECORD_MS);
      };

      socket.onmessage = (message) => {
        const res = JSON.parse(message.data);
        const transcript = res.channel?.alternatives[0]?.transcript;
        if (transcript) {
          if (res.is_final) {
            finalTranscriptRef.current += transcript + ' ';
            setInput(finalTranscriptRef.current.trim());
          } else {
            setInput((finalTranscriptRef.current + transcript).trim());
          }
        }
      };

      socket.onclose = () => {
        // socket closed: ensure resources are cleaned up
        try { stream.getTracks().forEach(t => t.stop()); } catch {}
        if (stopRecordingTimerRef.current) {
          clearTimeout(stopRecordingTimerRef.current);
          stopRecordingTimerRef.current = null;
        }
        setIsRecording(false);
      };
      
      socket.onerror = () => {
        try { stream.getTracks().forEach(t => t.stop()); } catch {}
        if (stopRecordingTimerRef.current) {
          clearTimeout(stopRecordingTimerRef.current);
          stopRecordingTimerRef.current = null;
        }
        setIsRecording(false);
      };

    } catch (err) {
      console.error('Microphone or API Error:', err);
      // Ensure resources are cleaned up and inform the user
      stopRecording();
      const msg = err instanceof Error ? err.message : String(err);
      setMessages((prev) => [...prev, { role: 'agent', content: `**Error:** ${msg}` }]);
    }
  }, [isRecording, stopRecording]);

  const ws = useRef<WebSocket | null>(null);
  const jwtTokenRef = useRef<string | null>(null);
  const lastSessionUserIdRef = useRef<string | null | undefined>(undefined);
  const authRefreshInFlightRef = useRef(false);
  const tokenRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef(0);
  const pinnedRef = useRef(true);

  const scrollToBottom = useCallback((behavior: 'smooth' | 'instant' = 'smooth') => {
    if (!scrollRef.current) return;
    if (behavior === 'smooth') {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    } else {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    pinnedRef.current = true;
  }, []);

  // ── Reconnection state ──
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);
  const authTierRef = useRef<'authenticated' | 'anonymous' | null>(null);
  const reconnectBlockedUntilRef = useRef(0);
  const sessionUserIdRef = useRef<string | null>(sessionData?.user?.id ?? null);
  const logoutProbeInFlightRef = useRef(false);
  const authRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTokenRefreshTimer = useCallback(() => {
    if (tokenRefreshTimerRef.current) {
      clearTimeout(tokenRefreshTimerRef.current);
      tokenRefreshTimerRef.current = null;
    }
  }, []);

  const clearAuthRetryTimer = useCallback(() => {
    if (authRetryTimerRef.current) {
      clearTimeout(authRetryTimerRef.current);
      authRetryTimerRef.current = null;
    }
  }, []);

  const fetchJwtToken = useCallback(async (): Promise<string | null> => {
    try {
      const { data, error } = await authClient.token();
      const errorStatus =
        typeof error === 'object' && error !== null
          ? (
            (error as { status?: number; error?: { status?: number } }).status
            ?? (error as { status?: number; error?: { status?: number } }).error?.status
          )
          : undefined;

      // Better Auth endpoints can transiently 429 during bursts; keep current token
      // to avoid accidental auth downgrade on active sockets.
      if (errorStatus === 429) {
        return jwtTokenRef.current;
      }

      if (error || !data?.token) return null;
      return data.token;
    } catch {
      return null;
    }
  }, []);

  const sendAuthFrame = useCallback(async (socket?: WebSocket | null) => {
    if (authRefreshInFlightRef.current) return;

    const target = socket ?? ws.current;
    if (!target || target.readyState !== WebSocket.OPEN) return;

    authRefreshInFlightRef.current = true;

    try {
      const token = await fetchJwtToken();
      jwtTokenRef.current = token;

      // Don't accidentally downgrade an authenticated socket because token fetch
      // temporarily returned null during session revalidation.
      if (!token && (authTierRef.current === 'authenticated' || sessionUserIdRef.current)) {
        if (sessionUserIdRef.current && !authRetryTimerRef.current) {
          authRetryTimerRef.current = setTimeout(() => {
            authRetryTimerRef.current = null;
            void sendAuthFrame(target);
          }, 700);
        }
        return;
      }

      clearAuthRetryTimer();

      target.send(JSON.stringify({
        type: 'auth',
        ...(token ? { token } : {}),
      }));
    } catch (err) {
      console.error('[ws] failed to send auth frame:', err);
    } finally {
      authRefreshInFlightRef.current = false;
    }
  }, [clearAuthRetryTimer, fetchJwtToken]);

  const scheduleTokenRefresh = useCallback((tokenExp?: number | null) => {
    clearTokenRefreshTimer();

    if (!tokenExp) return;

    // Refresh shortly before expiry so active sockets keep the correct tier.
    const refreshAtMs = tokenExp * 1000 - 30000;
    const delayMs = refreshAtMs - Date.now();

    if (delayMs <= 0) {
      void sendAuthFrame();
      return;
    }

    tokenRefreshTimerRef.current = setTimeout(() => {
      void sendAuthFrame();
    }, delayMs);
  }, [clearTokenRefreshTimer, sendAuthFrame]);

  const forceAnonymousAuthFrame = useCallback((socket?: WebSocket | null) => {
    const target = socket ?? ws.current;
    if (!target || target.readyState !== WebSocket.OPEN) return;

    authRefreshInFlightRef.current = false;
    jwtTokenRef.current = null;
    clearAuthRetryTimer();
    clearTokenRefreshTimer();

    try {
      target.send(JSON.stringify({ type: 'auth', logout: true }));
    } catch (err) {
      console.error('[ws] failed to send anonymous auth frame:', err);
    }
  }, [clearAuthRetryTimer, clearTokenRefreshTimer]);

  const connect = useCallback(() => {
    if (ws.current) {
      intentionalCloseRef.current = true;
      ws.current.close();
    }

    setStatus('connecting');
    const wsUrl = process.env.NEXT_PUBLIC_AGENT_WS_URL;
    if (!wsUrl) {
      throw new Error("NEXT_PUBLIC_AGENT_WS_URL environment variable is not set");
    }
    const socket = new WebSocket(wsUrl);
    ws.current = socket;
    intentionalCloseRef.current = false;

    socket.onopen = async () => {
      // Send auth frame as the first WS message.
      await sendAuthFrame(socket);
    };

    socket.onclose = (ev) => {
      setStatus('disconnected');
      setIsBusy(false);
      ws.current = null;
      jwtTokenRef.current = null;
      authTierRef.current = null;
      authRefreshInFlightRef.current = false;
      clearAuthRetryTimer();
      clearTokenRefreshTimer();

      if (!intentionalCloseRef.current) {
        let delay: number;
        if (ev.code === 1008) {
          // Handshake policy violation (often anon rate-limit). Don't reconnect
          // aggressively and burn more anonymous quota.
          const now = Date.now();
          if (sessionUserIdRef.current) {
            // If user is signed in, retry quickly to re-handshake as authenticated.
            reconnectBlockedUntilRef.current = 0;
            reconnectAttemptRef.current = 0;
            delay = 1500;
          } else {
            const blockedFor = reconnectBlockedUntilRef.current - now;
            delay = blockedFor > 0 ? blockedFor : 6000;
            reconnectAttemptRef.current = 0;
          }
        } else {
          const attempt = reconnectAttemptRef.current;
          delay = Math.min(1000 * Math.pow(2, attempt), 30000);
          reconnectAttemptRef.current = attempt + 1;
        }

        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };

    socket.onerror = (err) => {
      console.error('[ws] error:', err);
    };

    socket.onmessage = (event) => {
      let data: Record<string, any>;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      if (data.type === 'auth_ok') {
        const nextTier = data.tier === 'authenticated' ? 'authenticated' : 'anonymous';
        const shouldForceReauth = nextTier === 'anonymous' && !!sessionUserIdRef.current;

        setStatus(shouldForceReauth ? 'connecting' : 'connected');
        reconnectAttemptRef.current = 0;
        authTierRef.current = nextTier;
        authRefreshInFlightRef.current = false;

        const tokenExp =
          typeof data.tokenExp === 'number'
            ? data.tokenExp
            : typeof data.tokenExp === 'string'
              ? Number.parseInt(data.tokenExp, 10)
              : null;
        if (authTierRef.current === 'authenticated' && Number.isFinite(tokenExp)) {
          scheduleTokenRefresh(tokenExp);
        } else {
          scheduleTokenRefresh(null);

          // If client session says logged-in but socket came up anonymous,
          // try upgrading again once token/session fetch settles.
          if (shouldForceReauth) {
            setTimeout(() => {
              void sendAuthFrame();
            }, 300);
          }
        }
        return;
      }

      if (data.type === 'rate_limited') {
        setStatus('connected');
        const isAnon = data.tier === 'anonymous';
        const defaultMsg = isAnon
          ? 'Anonymous users can send 3 prompts per minute. [Sign in](/auth/sign-in) for higher limits.'
          : 'Please wait a moment before sending another message.';
        const serverMsg = typeof data.message === 'string' && data.message.trim().length > 0
          ? data.message.trim()
          : defaultMsg;
        const warningText = `⚠️ **Rate limit reached.** ${serverMsg}`;

        setMessages(prev => {
          const last = prev[prev.length - 1];
          const withoutStreaming = last?.role === 'agent' && last.isStreaming
            ? prev.slice(0, -1)
            : prev;
          const finalLast = withoutStreaming[withoutStreaming.length - 1];
          if (finalLast?.role === 'agent' && finalLast.content === warningText) {
            return withoutStreaming;
          }
          return [...withoutStreaming, {
            role: 'agent',
            content: warningText,
          }];
        });
        setIsBusy(false);

        if (isAnon) {
          reconnectBlockedUntilRef.current = Date.now() + 60000;
        }

        // If user has just signed in, try to upgrade this existing socket from anon to auth.
        if (isAnon && sessionUserIdRef.current) {
          setStatus('connecting');
          void sendAuthFrame();
        }
        return;
      }

      if (data.type === 'ping') {
        try { socket.send('__pong__'); } catch { }
        return;
      }

      if (data.type === 'action') {
        console.log("🛠️ Received agent action:", data);
        const currentActions = actionsRef.current;
        const currentExpressions = expressionsRef.current;
        
        if (data.action === 'addExpr' && currentActions?.addExpr) {
          currentActions.addExpr(data.latex, data.color);
        } else if (data.action === 'removeExpr' && currentActions?.removeExpr && currentExpressions) {
          const targetExpr = currentExpressions.find((e: any) => {
            if (typeof e.latex !== 'string') return false;
            return e.id === data.latex || e.latex.includes(data.latex);
          });
          if (targetExpr) {
            currentActions.removeExpr(targetExpr.id);
          }
        } else if (data.action === 'updateSliderBounds' && currentActions?.updateSliderBounds && currentExpressions) {
          const targetExpr = currentExpressions.find((e: any) => {
            const match = typeof e.latex === 'string' ? e.latex.match(/^([a-zA-Z](?:_\{?[a-zA-Z0-9]+\}?)?)\s*=/) : null;
            return match && match[1] === (data as any).variable;
          });
          if (targetExpr) {
            currentActions.updateSliderBounds(targetExpr.id, (data as any).min, (data as any).max, (data as any).step);
          }
        }
        return;
      }

      if (data.type === 'thinking') {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === 'agent' && last.isStreaming) return prev;
          return [...prev, { role: 'agent', content: '', isStreaming: true }];
        });
        return;
      }

      if (data.type === 'chunk') {
        const text = data.text ?? '';
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === 'agent' && last.isStreaming) {
            return [
              ...prev.slice(0, -1),
              { ...last, content: text, isStreaming: true },
            ];
          }
          return [...prev, { role: 'agent', content: text, isStreaming: true }];
        });
      }
      else if (data.type === 'done') {
        setIsBusy(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === 'agent') {
            if (!last.content) return prev.slice(0, -1);
            return [...prev.slice(0, -1), { ...last, isStreaming: false }];
          }
          return prev;
        });
      }
      else if (data.type === 'error') {
        setIsBusy(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === 'agent' && last.isStreaming) {
            const finalized = last.content ? [{ ...last, isStreaming: false }] : [];
            return [
              ...prev.slice(0, -1),
              ...finalized,
              { role: 'agent', content: `**Error:** ${data.text}` },
            ];
          }
          return [...prev, { role: 'agent', content: `**Error:** ${data.text}` }];
        });
      }
    };
    
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clearAuthRetryTimer, clearTokenRefreshTimer, scheduleTokenRefresh, sendAuthFrame]);

  const sessionUserId = sessionData?.user?.id ?? null;

  // Keep the same socket but refresh auth tier whenever sign-in/sign-out state changes.
  useEffect(() => {
    if (sessionUserId) {
      sessionUserIdRef.current = sessionUserId;
    }

    if (lastSessionUserIdRef.current === undefined) {
      lastSessionUserIdRef.current = sessionUserId;
      return;
    }

    const sessionChanged = lastSessionUserIdRef.current !== sessionUserId;
    if (sessionChanged) {
      lastSessionUserIdRef.current = sessionUserId;
    }

    // Login: immediately unblock reconnect and authenticate current/new socket.
    if (sessionUserId) {
      if (sessionChanged) {
        reconnectBlockedUntilRef.current = 0;
        if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
          connect();
        } else {
          setStatus('connecting');
          void sendAuthFrame();
        }
      }
      return;
    }

    // Session hooks can transiently report null during refresh/rate-limit hiccups.
    // Don't downgrade until we can confirm token truly disappeared.
    if (isSessionPending || sessionErrorStatus === 429) {
      return;
    }

    // Only probe potential logout when state actually changes to null.
    if (!sessionChanged) {
      return;
    }

    const openSocket = ws.current && ws.current.readyState === WebSocket.OPEN;
    if (!openSocket) {
      sessionUserIdRef.current = null;
      return;
    }

    if (logoutProbeInFlightRef.current) return;
    logoutProbeInFlightRef.current = true;

    void (async () => {
      try {
        // Double-check token with a short delay to avoid false sign-out downgrades
        // caused by transient session hook flips.
        let token = await fetchJwtToken();
        if (!token) {
          await new Promise((resolve) => setTimeout(resolve, 500));
          token = await fetchJwtToken();
        }

        // Ignore stale async result if auth state changed again.
        if (lastSessionUserIdRef.current !== null) return;

        if (token) {
          jwtTokenRef.current = token;
          void sendAuthFrame();
          return;
        }

        // Confirmed sign-out: now downgrade existing socket tier.
        sessionUserIdRef.current = null;
        forceAnonymousAuthFrame();
      } finally {
        logoutProbeInFlightRef.current = false;
      }
    })();
  }, [
    sessionUserId,
    isSessionPending,
    sessionErrorStatus,
    fetchJwtToken,
    sendAuthFrame,
    forceAnonymousAuthFrame,
    connect,
  ]);

  // Connect only when modal is open to save resources, or just connect once.
  // We connect on mount so the websocket is ready when opened.
  useEffect(() => {
    connect();
    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      clearAuthRetryTimer();
      clearTokenRefreshTimer();
      if (ws.current) ws.current.close();
    };
  }, [clearAuthRetryTimer, clearTokenRefreshTimer, connect]);

  // Scroll logic
  useEffect(() => {
    const THRESHOLD = 60;
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = el;
      pinnedRef.current = scrollHeight - scrollTop - clientHeight < THRESHOLD;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, [isOpen]); 

  // Auto-jump to bottom when modal freshly opens
  useEffect(() => {
    if (isOpen) {
      const timer = requestAnimationFrame(() => {
        scrollToBottom('instant');
      });
      return () => cancelAnimationFrame(timer);
    }
  }, [isOpen, scrollToBottom]);

  useEffect(() => {
    const currentCount = messages.length;
    const isNewMessage = currentCount !== prevMessageCountRef.current;
    prevMessageCountRef.current = currentCount;

    if (isOpen) {
      if (isNewMessage) {
        scrollToBottom('smooth');
      } else if (pinnedRef.current) {
        scrollToBottom('instant');
      }
    }
  }, [messages, isOpen, scrollToBottom]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
    }
  }, [input, isOpen]);

  // Safety: ensure microphone / streams are stopped when the modal closes
  useEffect(() => {
    if (!isOpen) {
      stopRecording();
    }
  }, [isOpen, stopRecording]);

  const handleInputChange = useCallback((val: string) => {
    setInput(val);
    finalTranscriptRef.current = val;
  }, []);

  const handleSend = useCallback(() => {
    const text = input.trim();
    const isProcessingAnything = attachments.some(a => a.ocrState === 'pending' || a.ocrState === 'processing');
    
    if ((!text && attachments.length === 0) || isBusy || !ws.current || ws.current.readyState !== WebSocket.OPEN || isProcessingAnything) return;

    // IMMEDIATELY KILL RECORDING AND WS CONNECTION TO SAVE QUOTA
    stopRecording();

    let payloadText = text;
    
    if (attachments.length > 0) {
      if (payloadText) payloadText += '\n\n---\n\n';
      attachments.forEach(att => {
        payloadText += `**${att.file.name} (${att.engine || 'unknown engine'}):**\n`;
        if (att.ocrState === 'done' && att.ocrMarkdown) {
          payloadText += att.ocrMarkdown + '\n\n';
        } else if (att.ocrState === 'error') {
          payloadText += `[Error: could not process this file: ${att.ocrError}]\n\n`;
        } else {
          payloadText += `[Content unavailable]\n\n`;
        }
      });
      payloadText += '---\n';
    }

    // Add empty space text if only files were sent so UI renders a bubble properly or handle it better
    setMessages((prev) => [
      ...prev,
      { 
        role: 'user', 
        content: text, // Only text
        attachments: attachments.map(a => ({
          id: a.id,
          name: a.file.name,
          size: a.file.size,
          mimeType: a.mimeType,
          previewUrl: a.previewUrl,
          engine: a.engine
        }))
      },
      { role: 'agent', content: '', isStreaming: true },
    ]);
    
    setInput('');
    // Cleanup attachments (don't revoke URL so chat history still has preview)
    attachments.forEach(att => {
      att.abortController.abort();
    });
    setAttachments([]);
    finalTranscriptRef.current = ''; // Clear voice transcript when sending
    setIsBusy(true);

    ws.current.send(JSON.stringify({
      text: payloadText,
      expressions: expressions?.map(e => ({ id: e.id, latex: e.latex, color: e.color, visible: e.visible })) || [],
      reasoningEffort: reasoningEffort
    }));
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [input, isBusy, stopRecording, expressions, attachments, reasoningEffort]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }, [handleSend]);

  const statusColor = status === 'connected' ? 'bg-emerald-500' : status === 'connecting' ? 'bg-amber-400' : 'bg-red-500';

  return (
    <>
      {/* Floating Action Island (Covers Desmos logo) */}
      <AnimatePresence>
        {!isOpen && (
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 20, opacity: 0 }}
            className="fixed bottom-0 right-0 z-50 p-2"
          >
            <div className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-lg shadow-black/5">
              <div className="flex items-center gap-2 border-r border-zinc-200 dark:border-zinc-800 pr-3 mr-1">
                <div className={cn("w-2 h-2 rounded-full", statusColor, status === 'connecting' && "animate-pulse")} />
                <span className="text-[10px] font-bold tracking-[0.15em] uppercase text-zinc-400 dark:text-zinc-500 select-none">
                  Ozone AI
                </span>
              </div>

              <motion.button
                onClick={() => setIsOpen(true)}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className={cn(
                  "w-9 h-9 rounded-lg flex items-center justify-center shadow-sm transition-all duration-300",
                  "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900",
                  "hover:shadow-md hover:bg-zinc-800 dark:hover:bg-white"
                )}
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="none" className="w-5 h-5">
                  <path d="M12 2l2.4 7.6A2 2 0 0 0 16.4 12l7.6 2.4-7.6 2.4a2 2 0 0 0-2 2L12 22l-2.4-7.6a2 2 0 0 0-2-2L0 12l7.6-2.4a2 2 0 0 0 2-2z" />
                </svg>
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Chat Modal */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 30, scale: 0.95, transition: { duration: 0.2 } }}
            className={cn(
              "fixed z-[60] flex flex-col shadow-[0_8px_40px_rgba(0,0,0,0.12)] overflow-hidden",
              "bg-[#f8f8f7] dark:bg-[#121212] border border-zinc-200/80 dark:border-zinc-800/80",
              "origin-bottom-right transition-all duration-300",
              isMaximized ? "bottom-0 right-0 w-full sm:w-[85vw] md:w-[75vw] lg:w-[900px] h-full sm:h-[85vh] md:h-[88vh] rounded-none sm:rounded-tl-3xl" : "bottom-0 right-0 w-full sm:w-[var(--modal-width,380px)] h-[50vh] sm:h-[var(--modal-height,550px)] rounded-none sm:rounded-tl-2xl shadow-2xl"
            )}
            style={!isMaximized ? {
              '--modal-width': `${dimensions.width}px`,
              '--modal-height': `${dimensions.height}px`
            } as any : {}}
          >
            {/* Custom Edge Handles for Dynamic Resizing */}
            {!isMaximized && (
              <>
                <div onMouseDown={(e) => startResize(e, 'both')} className="absolute top-0 left-0 w-6 h-6 z-50 cursor-nwse-resize" />
                <div onMouseDown={(e) => startResize(e, 'height')} className="absolute top-0 left-6 right-0 h-2 z-50 cursor-ns-resize" />
                <div onMouseDown={(e) => startResize(e, 'width')} className="absolute top-6 left-0 w-2 bottom-0 z-50 cursor-ew-resize" />
              </>
            )}

            {/* Header */}
            <div className="flex-none flex items-center justify-between px-4 py-3 bg-white/60 dark:bg-zinc-900/60 backdrop-blur-md border-b border-zinc-200/50 dark:border-zinc-800/50">
              <div className="flex items-center gap-2.5">
                <div className="relative flex items-center justify-center">
                  <span className={cn('absolute w-2 h-2 rounded-full', statusColor, status === 'connecting' && 'animate-ping')} />
                  <span className={cn('relative w-2 h-2 rounded-full', statusColor)} />
                </div>
                <span className="text-[13px] font-semibold tracking-wide text-zinc-800 dark:text-zinc-200">
                  Ozone Agent
                </span>
                <select
                  value={reasoningEffort}
                  onChange={(e) => setReasoningEffort(e.target.value as 'low' | 'medium' | 'high')}
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded-md bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-violet-500 cursor-pointer"
                  title="Reasoning Effort: higher = more thorough reasoning, lower = faster responses"
                >
                  <option value="low">Instant</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
              <div className="flex items-center gap-1.5 text-zinc-400 dark:text-zinc-500">
                <button
                  onClick={() => setIsMaximized(!isMaximized)}
                  className="p-1 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded transition-colors"
                  title={isMaximized ? "Minimize" : "Maximize"}
                >
                  {isMaximized ? (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-4 h-4">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 9V4.5M9 9H4.5M9 9 3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5 5.25 5.25" />
                    </svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-4 h-4">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
                    </svg>
                  )}
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  className="p-1 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded transition-colors"
                  title="Close"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor" className="w-4 h-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Scroll Area */}
            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto overflow-x-hidden p-4 space-y-5"
              style={{ scrollbarWidth: 'thin', scrollbarColor: 'rgba(120,120,140,0.2) transparent' }}
            >
              <AnimatePresence initial={false}>
                {messages.length === 0 && (
                  <motion.div
                    key="empty"
                    variants={emptyStateVariants}
                    initial="hidden"
                    animate="visible"
                    exit={{ opacity: 0 }}
                    className="flex flex-col items-center justify-center min-h-[60%] text-center px-4 pt-10"
                  >
                    <div className="w-12 h-12 mb-4 rounded-2xl flex items-center justify-center
                      bg-gradient-to-br from-violet-100 to-indigo-50 dark:from-violet-900/30 dark:to-indigo-900/20
                      ring-1 ring-violet-200/60 dark:ring-violet-700/30
                      shadow-[0_4px_16px_rgba(109,40,217,0.08)]">
                      <svg className="w-7 h-7 text-violet-500 dark:text-violet-400" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2l2.4 7.6A2 2 0 0 0 16.4 12l7.6 2.4-7.6 2.4a2 2 0 0 0-2 2L12 22l-2.4-7.6a2 2 0 0 0-2-2L0 12l7.6-2.4a2 2 0 0 0 2-2z" />
                      </svg>
                    </div>
                    <h2 className="text-lg font-semibold tracking-tight mb-2 text-zinc-900 dark:text-zinc-100">
                      Ozone Calculus Agent
                    </h2>
                    <p className="text-[13px] text-zinc-500 dark:text-zinc-400 max-w-[250px] leading-relaxed mx-auto">
                      Ask me anything about math, calculus, or to explain functions.
                    </p>
                    <div className="mt-6 flex flex-col gap-2 w-full">
                      {[
                        'Integrate sec³x dx',
                        'Prove √2 is irrational'
                      ].map((s) => (
                        <button key={s}
                          onClick={() => { handleInputChange(s); textareaRef.current?.focus(); }}
                          className="px-3 py-2 rounded-xl text-[12px] font-medium
                            bg-white dark:bg-zinc-800/60
                            border border-zinc-200/80 dark:border-zinc-700/60
                            text-zinc-600 dark:text-zinc-400
                            hover:border-violet-300 dark:hover:border-violet-600/60
                            hover:text-violet-700 dark:hover:text-violet-300
                            transition-all duration-200">
                          "{s}"
                        </button>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <AnimatePresence initial={false}>
                {messages.map((msg, i) => (
                  <ChatMessage key={i} msg={msg} i={i} />
                ))}
              </AnimatePresence>
              <div ref={messagesEndRef} className="h-2" />
            </div>

            <ScrollToBottomButton scrollRef={scrollRef} onClick={() => scrollToBottom('smooth')} />

            {/* Input */}
            <ChatInput
              input={input}
              setInput={handleInputChange}
              handleSend={handleSend}
              handleKeyDown={handleKeyDown}
              isBusy={isBusy}
              status={status}
              textareaRef={textareaRef}
              isRecording={isRecording}         
              toggleRecording={toggleRecording}
              attachments={attachments}
              addFiles={addFiles}
              removeAttachment={removeAttachment}
              openPreview={openPreview}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
