'use client';

import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { motion, AnimatePresence, type Variants, type Transition } from 'framer-motion';

// --- Utility ---
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Normalize \[...\] → $$...$$ and \(...\) → $...$
const preprocessLaTeX = (content: string) => {
  return content
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, tex) => `$$${tex}$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, tex) => `$${tex}$`);
};

// --- Types ---
type Message = {
  role: 'user' | 'agent';
  content: string;
  isStreaming?: boolean;
};
type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

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

// --- Math Block Wrapper ---
function MathBlock({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative my-5 w-full">
      <div className="overflow-x-auto overflow-y-hidden py-4 px-5 rounded-xl 
        bg-zinc-50 dark:bg-zinc-900/60 
        border border-zinc-200/80 dark:border-zinc-700/50
        text-center [&_.katex-display]:my-0 [&_.katex-display]:overflow-x-auto 
        [&_.katex-display]:overflow-y-hidden [&_.katex]:max-w-full">
        {children}
      </div>
    </div>
  );
}

// --- Markdown Renderer ---
function AgentContent({ content, isUser }: { content: string; isUser: boolean }) {
  return (
    <div className={cn(
      'text-[15px] leading-[1.75] prose max-w-none break-words',
      isUser
        ? 'prose-invert prose-p:text-white/90 prose-headings:text-white'
        : [
            'prose-zinc dark:prose-invert',
            'prose-p:text-zinc-700 dark:prose-p:text-zinc-300',
            'prose-headings:font-semibold prose-headings:tracking-tight',
            'prose-headings:text-zinc-900 dark:prose-headings:text-zinc-100',
            'prose-code:text-violet-600 dark:prose-code:text-violet-400',
            'prose-strong:text-zinc-900 dark:prose-strong:text-zinc-100',
            'prose-a:text-violet-600 dark:prose-a:text-violet-400',
            'prose-blockquote:border-violet-400 dark:prose-blockquote:border-violet-500',
            'prose-pre:bg-transparent prose-pre:p-0 prose-pre:m-0',
          ].join(' '),
    )}>
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex]}
        components={{
          div: ({ className, children, ...props }: any) => {
            if (className?.includes('math-display')) return <MathBlock>{children}</MathBlock>;
            return <div className={className} {...props}>{children}</div>;
          },
          span: ({ className, children, ...props }: any) => {
            if (className?.includes('katex-display')) {
              return (
                <span
                  className={cn(className, 'block my-4 overflow-x-auto overflow-y-hidden [&_.katex]:max-w-full')}
                  {...props}
                >{children}</span>
              );
            }
            return <span className={className} {...props}>{children}</span>;
          },
          code({ node, inline, className, children, ...props }: any) {
            const lang = /language-(\w+)/.exec(className || '')?.[1];
            if (!inline) {
              return (
                <div className="relative my-4 rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-700/60 bg-zinc-50 dark:bg-zinc-900/70">
                  {lang && (
                    <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-200 dark:border-zinc-700/60">
                      <span className="text-[11px] font-mono font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wider">{lang}</span>
                    </div>
                  )}
                  <pre className="p-4 overflow-x-auto text-[13px] font-mono text-zinc-800 dark:text-zinc-200 m-0 leading-relaxed">
                    <code className={className} {...props}>{children}</code>
                  </pre>
                </div>
              );
            }
            return (
              <code className="px-1.5 py-0.5 rounded-md text-[0.875em] font-mono bg-zinc-100 dark:bg-zinc-800 text-violet-600 dark:text-violet-400" {...props}>
                {children}
              </code>
            );
          },
          p: ({ children }) => <div className="mb-3.5 last:mb-0 leading-[1.75]">{children}</div>,
          ul: ({ children }) => <ul className="list-disc pl-5 mb-3.5 space-y-1.5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 mb-3.5 space-y-1.5">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          h1: ({ children }) => <h1 className="text-xl font-semibold mb-4 mt-7 first:mt-0 tracking-tight">{children}</h1>,
          h2: ({ children }) => <h2 className="text-lg font-semibold mb-3 mt-6 first:mt-0 tracking-tight">{children}</h2>,
          h3: ({ children }) => <h3 className="text-base font-semibold mb-2.5 mt-5 first:mt-0">{children}</h3>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-violet-400 dark:border-violet-500 pl-4 py-0.5 my-4 text-zinc-500 dark:text-zinc-400 bg-violet-50/40 dark:bg-violet-900/10 rounded-r-lg italic">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer"
              className="text-violet-600 dark:text-violet-400 hover:underline underline-offset-4 decoration-violet-300 dark:decoration-violet-600">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="my-5 overflow-x-auto rounded-xl border border-zinc-200 dark:border-zinc-700/60">
              <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-700/60 text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="px-4 py-3 bg-zinc-50 dark:bg-zinc-800/60 text-left text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300 border-t border-zinc-100 dark:border-zinc-800">
              {children}
            </td>
          ),
          hr: () => <hr className="my-5 border-zinc-200 dark:border-zinc-700/60" />,
        }}
      >
        {preprocessLaTeX(content)}
      </ReactMarkdown>
    </div>
  );
}

// --- Main Page ---
export default function ChatPage() {
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isBusy, setIsBusy] = useState(false);

  const ws = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const socket = new WebSocket('ws://127.0.0.1:8000/ws');
    ws.current = socket;
    socket.onopen = () => setStatus('connected');
    socket.onclose = () => { setStatus('disconnected'); setIsBusy(false); };
    socket.onerror = () => setStatus('disconnected');
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'chunk') {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === 'agent') return [...prev.slice(0, -1), { ...last, content: data.text, isStreaming: true }];
          return [...prev, { role: 'agent', content: data.text, isStreaming: true }];
        });
      } else if (data.type === 'done') {
        setIsBusy(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === 'agent') return [...prev.slice(0, -1), { ...last, isStreaming: false }];
          return prev;
        });
      } else if (data.type === 'error') {
        setIsBusy(false);
        setMessages((prev) => [...prev, { role: 'agent', content: `**Error:** ${data.text}` }]);
      }
    };
    return () => { socket.close(); };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
    }
  }, [input]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isBusy || !ws.current || ws.current.readyState !== WebSocket.OPEN) return;
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    setIsBusy(true);
    ws.current.send(text);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const statusColor = status === 'connected' ? 'bg-emerald-500' : status === 'connecting' ? 'bg-amber-400' : 'bg-red-500';

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden
      bg-[#f8f8f7] dark:bg-[#0c0c0d]
      text-zinc-900 dark:text-zinc-100
      selection:bg-violet-200 dark:selection:bg-violet-800/50
      selection:text-violet-900 dark:selection:text-violet-100
      font-sans antialiased transition-colors duration-300">

      {/* ── Grid texture overlay ── */}
      <div className="pointer-events-none fixed inset-0 z-0 opacity-[0.025] dark:opacity-[0.04]
        [background-image:linear-gradient(to_right,#6366f1_1px,transparent_1px),linear-gradient(to_bottom,#6366f1_1px,transparent_1px)]
        [background-size:40px_40px]" />

      {/* ── Status Pill ── */}
      <motion.div
        className="fixed top-5 left-5 z-50"
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.2, duration: 0.4 }}
      >
        <div className={cn(
          'flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-semibold tracking-widest uppercase transition-all duration-500',
          'bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md',
          'border border-zinc-200/60 dark:border-zinc-700/40 shadow-sm',
          'text-zinc-500 dark:text-zinc-400',
          status === 'connected' ? 'opacity-40 hover:opacity-100' : 'opacity-100',
        )}>
          <span className={cn('w-1.5 h-1.5 rounded-full', statusColor,
            status === 'connecting' && 'animate-pulse')} />
          {status}
        </div>
      </motion.div>

      {/* ── Messages Scroll Area ── */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto overflow-x-hidden w-full px-6 md:px-10 lg:px-16 xl:px-24 2xl:px-32 pt-20 pb-2"
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
              className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4"
            >
              <div className="w-16 h-16 mb-6 rounded-2xl flex items-center justify-center
                bg-gradient-to-br from-violet-100 to-indigo-50 dark:from-violet-900/30 dark:to-indigo-900/20
                ring-1 ring-violet-200/60 dark:ring-violet-700/30
                shadow-[0_8px_32px_rgba(109,40,217,0.08)] dark:shadow-[0_8px_32px_rgba(109,40,217,0.15)]">
                <svg className="w-7 h-7 text-violet-500 dark:text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                </svg>
              </div>
              <h2 className="text-2xl font-semibold tracking-tight mb-2.5
                text-zinc-900 dark:text-zinc-100">
                Mathematical Reasoning Agent
              </h2>
              <p className="text-[15px] text-zinc-400 dark:text-zinc-500 max-w-md leading-relaxed">
                Ask anything — calculus, linear algebra, proofs, logic, statistics.
                I reason step-by-step and render every expression cleanly.
              </p>
              <div className="mt-8 flex flex-wrap gap-2 justify-center">
                {[
                  'Integrate sec³x dx',
                  'Prove √2 is irrational',
                  'Eigenvalues of [[1,2],[3,4]]',
                  'Taylor series of ln(1+x)',
                ].map((s) => (
                  <button key={s}
                    onClick={() => { setInput(s); textareaRef.current?.focus(); }}
                    className="px-3.5 py-1.5 rounded-xl text-[13px] font-medium
                      bg-white dark:bg-zinc-800/60
                      border border-zinc-200 dark:border-zinc-700/60
                      text-zinc-600 dark:text-zinc-400
                      hover:border-violet-300 dark:hover:border-violet-600
                      hover:text-violet-700 dark:hover:text-violet-300
                      hover:bg-violet-50 dark:hover:bg-violet-900/20
                      transition-all duration-200 shadow-sm">
                    {s}
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Message list */}
        <div className="w-full space-y-8 pb-[120px]">
          <AnimatePresence initial={false}>
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                variants={msgVariants}
                initial="hidden"
                animate="visible"
                className={cn('flex w-full', msg.role === 'user' ? 'justify-end' : 'justify-start')}
              >
                {/* Avatar dot */}
                {msg.role === 'agent' && (
                  <div className="flex-none mr-3 mt-1">
                    <div className="w-7 h-7 rounded-full flex items-center justify-center
                      bg-gradient-to-br from-violet-500 to-indigo-600 dark:from-violet-600 dark:to-indigo-700
                      text-white shadow-sm shadow-violet-200 dark:shadow-violet-900/30">
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5" />
                      </svg>
                    </div>
                  </div>
                )}

                <div className={cn(
                  'relative min-w-0',
                  msg.role === 'user'
                    ? 'max-w-[70%] xl:max-w-[60%]'
                    : 'max-w-[78%] xl:max-w-[72%] 2xl:max-w-[68%] flex-1',
                )}>
                  <div className={cn(
                    'rounded-2xl px-5 py-4',
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
                          'shadow-[0_2px_12px_rgba(0,0,0,0.04)] dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)]',
                        ].join(' '),
                  )}>
                    <AgentContent content={msg.content} isUser={msg.role === 'user'} />

                    {/* Streaming indicator */}
                    {msg.isStreaming && (
                      <div className="flex items-center gap-1 mt-3 ml-0.5">
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
            ))}
          </AnimatePresence>
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* ── Floating Input Bar ── */}
      <div className="fixed bottom-0 left-0 right-0 z-40
        px-4 sm:px-6 md:px-10 lg:px-16 xl:px-24 2xl:px-32
        pb-5 pt-8
        bg-gradient-to-t from-[#f8f8f7] via-[#f8f8f7]/95 to-transparent
        dark:from-[#0c0c0d] dark:via-[#0c0c0d]/95 dark:to-transparent
        pointer-events-none">
        <div className="pointer-events-auto w-full">
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.3, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className={cn(
              'relative flex items-end gap-2 w-full rounded-2xl p-2 transition-all duration-300',
              'bg-white dark:bg-zinc-900',
              'border border-zinc-200/80 dark:border-zinc-700/50',
              'shadow-[0_8px_40px_rgba(0,0,0,0.07)] dark:shadow-[0_8px_40px_rgba(0,0,0,0.4)]',
              'focus-within:border-violet-300 dark:focus-within:border-violet-600/60',
              'focus-within:shadow-[0_12px_48px_rgba(109,40,217,0.08)] dark:focus-within:shadow-[0_12px_48px_rgba(109,40,217,0.2)]',
            )}
          >
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={status !== 'connected'}
              placeholder="Ask a mathematical question..."
              className={cn(
                'flex-1 min-h-[48px] max-h-[180px] resize-none bg-transparent',
                'py-3 pl-4 pr-2 text-[15px] leading-relaxed',
                'text-zinc-900 dark:text-zinc-100',
                'placeholder:text-zinc-400 dark:placeholder:text-zinc-600',
                'focus:outline-none disabled:opacity-40',
              )}
            />

            <motion.button
              onClick={handleSend}
              disabled={!input.trim() || isBusy || status !== 'connected'}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.93 }}
              className={cn(
                'flex-none mb-1 w-9 h-9 rounded-[10px] flex items-center justify-center transition-all duration-200',
                input.trim() && !isBusy && status === 'connected'
                  ? 'bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 shadow-sm'
                  : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-300 dark:text-zinc-600 cursor-not-allowed',
              )}
            >
              <AnimatePresence mode="wait" initial={false}>
                {isBusy ? (
                  <motion.span key="spin"
                    initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.6 }}
                    className="w-4 h-4 border-2 border-current/30 border-t-current rounded-full animate-spin block" />
                ) : (
                  <motion.svg key="send"
                    initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.6 }}
                    xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                    <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
                  </motion.svg>
                )}
              </AnimatePresence>
            </motion.button>
          </motion.div>

          <p className="mt-2 text-center text-[10px] font-medium tracking-widest uppercase
            text-zinc-400 dark:text-zinc-600 select-none">
            Math Agent · {status === 'connected' ? 'Online' : status === 'connecting' ? 'Connecting…' : 'Offline'}
          </p>
        </div>
      </div>
    </div>
  );
}