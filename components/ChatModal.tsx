'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { marked } from 'marked';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { motion, AnimatePresence, type Variants, type Transition } from 'framer-motion';

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
type Message = {
  role: 'user' | 'agent';
  content: string;
  isStreaming?: boolean;
};
type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

import { MathExpression } from "./calculator/types";

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
  textareaRef
}: {
  input: string;
  setInput: (v: string) => void;
  handleSend: () => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  isBusy: boolean;
  status: ConnectionStatus;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
}) => {
  return (
    <div className="p-3 bg-zinc-50 dark:bg-zinc-900/80 border-t border-zinc-200/50 dark:border-zinc-800/50">
      <div className={cn(
        'relative flex items-end gap-2 w-full rounded-xl p-1.5 transition-all duration-300',
        'bg-white dark:bg-zinc-800/50',
        'border border-zinc-200/80 dark:border-zinc-700/50',
        'shadow-sm',
        'focus-within:border-violet-300 dark:focus-within:border-violet-600/60',
        'focus-within:shadow-[0_4px_16px_rgba(109,40,217,0.08)]',
      )}>
        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={status !== 'connected'}
          placeholder="Ask a math question..."
          className={cn(
            'flex-1 min-h-[36px] max-h-[120px] resize-none bg-transparent',
            'py-1.5 pl-3 pr-2 text-[14px] leading-relaxed',
            'text-zinc-900 dark:text-zinc-100',
            'placeholder:text-zinc-400 dark:placeholder:text-zinc-500',
            'focus:outline-none disabled:opacity-40',
          )}
        />

        <motion.button
          onClick={handleSend}
          disabled={!input.trim() || isBusy || status !== 'connected'}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.93 }}
          className={cn(
            'flex-none mb-0.5 w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200',
            input.trim() && !isBusy && status === 'connected'
              ? 'bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 shadow-sm'
              : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-300 dark:text-zinc-600 cursor-not-allowed',
          )}
        >
          <AnimatePresence mode="wait" initial={false}>
            {isBusy ? (
              <motion.span key="spin"
                initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.6 }}
                className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin block" />
            ) : (
              <motion.svg key="send"
                initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.6 }}
                xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
              </motion.svg>
            )}
          </AnimatePresence>
        </motion.button>
      </div>

      <p className="mt-2 mb-0.5 text-center text-[9px] font-medium tracking-widest uppercase
        text-zinc-400 dark:text-zinc-500 select-none">
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
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isBusy, setIsBusy] = useState(false);

  const ws = useRef<WebSocket | null>(null);
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

  const connect = useCallback(() => {
    if (ws.current) {
      intentionalCloseRef.current = true;
      ws.current.close();
    }

    setStatus('connecting');
    const socket = new WebSocket('ws://127.0.0.1:8000/ws');
    ws.current = socket;
    intentionalCloseRef.current = false;

    socket.onopen = () => {
      setStatus('connected');
      reconnectAttemptRef.current = 0;
    };

    socket.onclose = (ev) => {
      setStatus('disconnected');
      setIsBusy(false);
      ws.current = null;

      if (!intentionalCloseRef.current) {
        const attempt = reconnectAttemptRef.current;
        const delay = Math.min(1000 * Math.pow(2, attempt), 30000);
        reconnectAttemptRef.current = attempt + 1;
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
  }, []);

  // Connect only when modal is open to save resources, or just connect once.
  // We connect on mount so the websocket is ready when opened.
  useEffect(() => {
    connect();
    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (ws.current) ws.current.close();
    };
  }, [connect]);

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

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isBusy || !ws.current || ws.current.readyState !== WebSocket.OPEN) return;
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text },
      { role: 'agent', content: '', isStreaming: true },
    ]);
    setInput('');
    setIsBusy(true);
    ws.current.send(JSON.stringify({
      text: text,
      expressions: expressions?.map(e => ({ id: e.id, latex: e.latex, color: e.color, visible: e.visible })) || []
    }));
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [input, isBusy]);

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
                          onClick={() => { setInput(s); textareaRef.current?.focus(); }}
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
              setInput={setInput}
              handleSend={handleSend}
              handleKeyDown={handleKeyDown}
              isBusy={isBusy}
              status={status}
              textareaRef={textareaRef}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
