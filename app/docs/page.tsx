"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useTheme } from "next-themes";
import SplashScreen from "@/components/SplashScreen";

// ─── DATA ─────────────────────────────────────────────────────────────────────

const NAV = [
  { id: "intro",        label: "Introduction",         num: "00" },
  { id: "quickstart",   label: "Quick Start",          num: "01" },
  { id: "graphing",     label: "Graphing Basics",      num: "02" },
  { id: "trig",         label: "Trigonometric",        num: "03" },
  { id: "complex",      label: "Complex Numbers",      num: "04" },
  { id: "derivatives",  label: "Derivatives",          num: "05" },
  { id: "integrals",    label: "Integrals",            num: "06" },
  { id: "sliders",      label: "Sliders",              num: "07" },
  { id: "domain-range", label: "Domain & Range",       num: "08" },
  { id: "piecewise",    label: "Piecewise",            num: "09" },
  { id: "polar",        label: "Polar & Parametric",   num: "10" },
  { id: "analysis",     label: "Function Analysis",    num: "11" },
  { id: "series",       label: "Sequences & Series",   num: "12" },
  { id: "agent",        label: "AI Agent",             num: "13" },
  { id: "input",        label: "Input Methods",        num: "14" },
  { id: "shortcuts",    label: "Shortcuts",            num: "15" },
  { id: "visibility",   label: "Colors & Visibility",  num: "16" },
];

// ─── PRIMITIVES ───────────────────────────────────────────────────────────────

const C = ({ children }) => (
  <code style={{
    fontFamily: "'IBM Plex Mono', 'Fira Code', monospace",
    fontSize: "0.78em",
    background: "var(--token-bg)",
    color: "var(--token-fg)",
    padding: "1px 5px",
    borderRadius: 3,
    border: "1px solid var(--line)",
    letterSpacing: 0,
  }}>{children}</code>
);

const K = ({ children }) => (
  <kbd style={{
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: "0.72em",
    background: "var(--surface)",
    color: "var(--text-2)",
    padding: "2px 7px",
    borderRadius: 4,
    border: "1px solid var(--line)",
    boxShadow: "0 1px 0 var(--line)",
    letterSpacing: 0,
  }}>{children}</kbd>
);

const Callout = ({ variant = "note", children }) => {
  const v = {
    note:  { symbol: "—", color: "var(--text-3)" },
    tip:   { symbol: "→", color: "var(--text-1)" },
    warn:  { symbol: "!", color: "var(--text-1)" },
  }[variant];
  return (
    <div style={{
      borderLeft: "2px solid var(--line-strong)",
      paddingLeft: 20,
      margin: "28px 0",
      display: "flex",
      gap: 10,
    }}>
      <span style={{ color: v.color, fontFamily: "'IBM Plex Mono', monospace", fontSize: "0.75rem", paddingTop: 2, flexShrink: 0 }}>{v.symbol}</span>
      <p style={{ margin: 0, fontSize: "0.84rem", color: "var(--text-2)", lineHeight: 1.7 }}>{children}</p>
    </div>
  );
};

const Table = ({ head, rows }) => (
  <div style={{ border: "1px solid var(--line)", borderRadius: 6, overflow: "hidden", margin: "20px 0" }}>
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.83rem" }}>
      {head && (
        <thead>
          <tr style={{ borderBottom: "1px solid var(--line)" }}>
            {head.map((h, i) => (
              <th key={i} style={{
                padding: "9px 16px",
                textAlign: "left",
                fontSize: "0.7rem",
                fontWeight: 500,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--text-3)",
                fontFamily: "'IBM Plex Mono', monospace",
              }}>{h}</th>
            ))}
          </tr>
        </thead>
      )}
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} style={{ borderBottom: i < rows.length - 1 ? "1px solid var(--line)" : "none" }}>
            {row.map((cell, j) => (
              <td key={j} style={{
                padding: "9px 16px",
                color: j === 0 ? "var(--text-1)" : "var(--text-2)",
                fontFamily: j === 0 ? "'IBM Plex Mono', monospace" : "inherit",
                fontSize: j === 0 ? "0.78rem" : "0.83rem",
                lineHeight: 1.5,
              }}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const SGrid = ({ items }) => (
  <Table rows={items.map(it => [it.latex, it.desc])} />
);

const DGrid = ({ items }) => (
  <div style={{
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 1,
    border: "1px solid var(--line)",
    borderRadius: 6,
    overflow: "hidden",
    margin: "20px 0",
    background: "var(--line)",
  }}>
    {items.map((it, i) => (
      <div key={i} style={{ background: "var(--bg)", padding: "10px 14px", display: "flex", alignItems: "center", gap: 12 }}>
        <C>{it.fn}</C>
        <span style={{ fontSize: "0.78rem", color: "var(--text-3)" }}>{it.name}</span>
      </div>
    ))}
  </div>
);

const H2 = ({ num, children }) => (
  <div style={{ display: "flex", alignItems: "baseline", gap: 16, margin: "0 0 32px" }}>
    <span style={{
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: "0.68rem",
      color: "var(--text-3)",
      letterSpacing: "0.04em",
      flexShrink: 0,
    }}>{num}</span>
    <h2 style={{
      margin: 0,
      fontFamily: "'Syne', 'DM Sans', sans-serif",
      fontWeight: 700,
      fontSize: "clamp(1.35rem, 2.5vw, 1.75rem)",
      letterSpacing: "-0.03em",
      color: "var(--text-1)",
      lineHeight: 1.15,
    }}>{children}</h2>
  </div>
);

const H3 = ({ children }) => (
  <h3 style={{
    margin: "36px 0 14px",
    fontFamily: "'Syne', sans-serif",
    fontWeight: 600,
    fontSize: "0.78rem",
    letterSpacing: "0.07em",
    textTransform: "uppercase",
    color: "var(--text-3)",
  }}>{children}</h3>
);

const P = ({ children, style }) => (
  <p style={{ margin: "0 0 18px", fontSize: "0.875rem", color: "var(--text-2)", lineHeight: 1.75, ...style }}>{children}</p>
);

const Hr = () => <div style={{ height: 1, background: "var(--line)", margin: "32px 0" }} />;

// ─── SEARCH ───────────────────────────────────────────────────────────────────

function Search({ onClose, onNavigate }) {
  const [q, setQ] = useState("");
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const all = [
    { id: "intro",        label: "Introduction",         desc: "Overview of Ozon calculator" },
    { id: "quickstart",   label: "Quick Start",          desc: "Get up and running in seconds" },
    { id: "graphing",     label: "Graphing Basics",      desc: "Functions, implicit equations, inequalities, named functions" },
    { id: "trig",         label: "Trigonometric",        desc: "Sin, cos, tan, hyperbolic, inverse functions" },
    { id: "complex",      label: "Complex Numbers",      desc: "Imaginary unit, complex arithmetic, polar form" },
    { id: "derivatives",  label: "Derivatives",          desc: "First, higher-order, partial derivatives, evaluation at a point" },
    { id: "integrals",    label: "Integrals",            desc: "Definite, indefinite, area mode, improper integrals" },
    { id: "sliders",      label: "Sliders",              desc: "Parameters, animation, bounds, step" },
    { id: "domain-range", label: "Domain & Range",       desc: "Curly brace restrictions on x and y" },
    { id: "piecewise",    label: "Piecewise",            desc: "Multi-condition functions with default fallback" },
    { id: "polar",        label: "Polar & Parametric",   desc: "r=f(θ) polar curves and (x(t), y(t)) parametric" },
    { id: "analysis",     label: "Function Analysis",    desc: "Domain, range, intercepts, asymptotes, parity, monotonicity" },
    { id: "series",       label: "Sequences & Series",   desc: "Summation notation, convergence, power series" },
    { id: "agent",        label: "AI Agent",             desc: "Natural language, OCR input, voice, LaTeX generation" },
    { id: "input",        label: "Input Methods",        desc: "MathLive keyboard, inline shortcuts, smart parentheses" },
    { id: "shortcuts",    label: "Shortcuts",            desc: "int, ddx, dint, sum, lim and more" },
    { id: "visibility",   label: "Colors & Visibility",  desc: "Color picker, visibility modes, graph legend" },
  ];

  const results = q.trim()
    ? all.filter(i =>
        i.label.toLowerCase().includes(q.toLowerCase()) ||
        i.desc.toLowerCase().includes(q.toLowerCase())
      )
    : all;

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 1000,
      display: "flex", alignItems: "flex-start", justifyContent: "center",
      padding: "120px 20px 20px",
      backdropFilter: "blur(4px)",
    }} onClick={onClose}>
      <div style={{
        background: "var(--bg)",
        border: "1px solid var(--line-strong)",
        borderRadius: 10,
        width: "100%",
        maxWidth: 560,
        overflow: "hidden",
        boxShadow: "0 24px 64px rgba(0,0,0,0.5)",
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" strokeWidth="2" strokeLinecap="round">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          <input
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Search documentation…"
            style={{
              flex: 1, background: "none", border: "none", outline: "none",
              padding: "14px 0", fontSize: "0.88rem", color: "var(--text-1)",
              fontFamily: "'IBM Plex Sans', 'DM Sans', sans-serif",
            }}
            onKeyDown={e => e.key === "Escape" && onClose()}
          />
          <button onClick={onClose} style={{
            background: "none", border: "1px solid var(--line)", borderRadius: 4,
            padding: "2px 7px", color: "var(--text-3)", fontSize: "0.68rem",
            cursor: "pointer", fontFamily: "'IBM Plex Mono', monospace", letterSpacing: "0.04em",
          }}>esc</button>
        </div>
        <div style={{ maxHeight: 360, overflowY: "auto" }}>
          {results.length === 0 ? (
            <div style={{ padding: "28px 20px", textAlign: "center", color: "var(--text-3)", fontSize: "0.82rem" }}>No results</div>
          ) : results.map((r, i) => (
            <div
              key={r.id}
              onClick={() => { onNavigate(r.id); onClose(); }}
              style={{
                padding: "11px 16px",
                display: "flex",
                alignItems: "center",
                gap: 14,
                cursor: "pointer",
                borderBottom: i < results.length - 1 ? "1px solid var(--line)" : "none",
                transition: "background 0.1s",
              }}
              onMouseEnter={e => e.currentTarget.style.background = "var(--surface)"}
              onMouseLeave={e => e.currentTarget.style.background = "none"}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
              </svg>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "0.84rem", color: "var(--text-1)", fontWeight: 500 }}>{r.label}</div>
                <div style={{ fontSize: "0.74rem", color: "var(--text-3)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.desc}</div>
              </div>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" strokeWidth="1.8" strokeLinecap="round">
                <path d="m9 18 6-6-6-6"/>
              </svg>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── PAGE ─────────────────────────────────────────────────────────────────────

export default function DocsPage() {
  const [active, setActive]       = useState("intro");
  const [drawerOpen, setDrawer]   = useState(false);
  const [searchOpen, setSearch]   = useState(false);
  const [splashDone, setSplashDone] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        for (const e of entries) if (e.isIntersecting) setActive(e.target.id);
      },
      { rootMargin: "-15% 0px -75% 0px" }
    );
    NAV.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const handler = e => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setSearch(true); }
      if (e.key === "Escape") setSearch(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const scrollTo = id => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setDrawer(false);
  };

  if (!splashDone) {
    return <SplashScreen onComplete={() => setSplashDone(true)} />;
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        html { scroll-behavior: smooth; }

        :root {
          --bg:          #080808;
          --surface:     #0F0F0F;
          --text-1:      #EBEBEB;
          --text-2:      #888;
          --text-3:      #4A4A4A;
          --line:        #1A1A1A;
          --line-strong: #2A2A2A;
          --token-bg:    #111;
          --token-fg:    #C8C8C8;
          --sidebar-w:   240px;
          --content-max: 720px;
        }

        :root.light {
          --bg:          #FAFAFA;
          --surface:     #FFFFFF;
          --text-1:      #18181B;
          --text-2:      #52525B;
          --text-3:      #71717A;
          --line:        #E4E4E7;
          --line-strong: #D4D4D8;
          --token-bg:    #F4F4F5;
          --token-fg:    #3F3F46;
        }

        body {
          background: var(--bg);
          color: var(--text-1);
          font-family: 'IBM Plex Sans', system-ui, sans-serif;
          font-size: 15px;
          line-height: 1.6;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }

        ::selection { background: rgba(255,255,255,0.12); }

        /* ── SCROLLBAR ── */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--line-strong); border-radius: 3px; }

        /* ── LAYOUT ── */
        .layout { display: flex; min-height: 100vh; }

        /* ── SIDEBAR ── */
        .sidebar {
          position: fixed; top: 0; left: 0;
          width: var(--sidebar-w); height: 100vh;
          display: flex; flex-direction: column;
          background: var(--bg);
          border-right: 1px solid var(--line);
          z-index: 100;
          overflow-y: auto;
          scrollbar-width: none;
        }
        .sidebar::-webkit-scrollbar { display: none; }

        .sidebar-header {
          padding: 24px 20px;
          border-bottom: 1px solid var(--line);
          display: flex;
          align-items: center;
          gap: 10;
          flex-shrink: 0;
        }

        .sidebar-logo {
          display: flex; align-items: center; gap: 10px;
        }
        .logo-mark {
          width: 24px; height: 24px;
          border: 1.5px solid var(--line-strong);
          border-radius: 5px;
          display: flex; align-items: center; justify-content: center;
        }
        .logo-name {
          font-family: 'Syne', sans-serif;
          font-weight: 700;
          font-size: 0.95rem;
          color: var(--text-1);
          letter-spacing: -0.02em;
        }
        .logo-sub {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 0.62rem;
          color: var(--text-3);
          letter-spacing: 0.06em;
          text-transform: uppercase;
          margin-left: auto;
        }

        .search-btn {
          margin: 14px 14px 8px;
          display: flex; align-items: center; gap: 9px;
          padding: 8px 11px;
          background: var(--surface);
          border: 1px solid var(--line-strong);
          border-radius: 6px;
          cursor: pointer;
          color: var(--text-3);
          font-family: 'IBM Plex Sans', sans-serif;
          font-size: 0.78rem;
          transition: border-color 0.15s, color 0.15s;
          flex-shrink: 0;
        }
        .search-btn:hover { border-color: var(--text-3); color: var(--text-2); }
        .search-shortcut {
          margin-left: auto;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 0.66rem;
          padding: 1px 5px;
          border: 1px solid var(--line-strong);
          border-radius: 3px;
          color: var(--text-3);
        }

        .nav-section {
          padding: 6px 0;
          flex: 1;
        }
        .nav-label-group {
          padding: 18px 20px 6px;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 0.6rem;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: var(--text-3);
        }
        .nav-item {
          display: flex; align-items: center; gap: 10px;
          padding: 6px 20px;
          cursor: pointer;
          transition: color 0.12s;
          user-select: none;
        }
        .nav-item:hover .nav-text { color: var(--text-1); }
        .nav-num {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 0.6rem;
          color: var(--text-3);
          width: 18px;
          flex-shrink: 0;
          transition: color 0.12s;
        }
        .nav-text {
          font-size: 0.8rem;
          color: var(--text-3);
          transition: color 0.12s;
          font-weight: 400;
        }
        .nav-item.active .nav-num { color: var(--text-2); }
        .nav-item.active .nav-text { color: var(--text-1); font-weight: 500; }
        .nav-item.active {
          position: relative;
        }
        .nav-item.active::before {
          content: '';
          position: absolute;
          left: 0; top: 2px; bottom: 2px;
          width: 1.5px;
          background: var(--text-1);
          border-radius: 0 1px 1px 0;
        }

        .sidebar-footer {
          padding: 14px;
          border-top: 1px solid var(--line);
          flex-shrink: 0;
        }
        .open-btn {
          display: flex; align-items: center; justify-content: space-between;
          width: 100%;
          padding: 9px 13px;
          background: var(--text-1);
          color: var(--bg);
          border: none; border-radius: 6px;
          font-family: 'IBM Plex Sans', sans-serif;
          font-size: 0.78rem;
          font-weight: 600;
          cursor: pointer;
          letter-spacing: 0.01em;
          text-decoration: none;
          transition: opacity 0.15s;
        }
        .open-btn:hover { opacity: 0.88; }

        /* ── MOBILE NAV ── */
        .mobile-nav {
          display: none;
          position: fixed; top: 0; left: 0; right: 0;
          height: 52px;
          background: var(--bg);
          border-bottom: 1px solid var(--line);
          align-items: center;
          padding: 0 16px;
          gap: 14px;
          z-index: 200;
        }
        .mobile-logo { font-family: 'Syne', sans-serif; font-weight: 700; font-size: 0.92rem; letter-spacing: -0.02em; color: var(--text-1); }
        .icon-btn { background: none; border: none; color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 4px; }

        /* ── CONTENT ── */
        .content {
          margin-left: var(--sidebar-w);
          flex: 1;
          min-width: 0;
        }
        .content-inner {
          max-width: var(--content-max);
          padding: 80px 56px 140px;
        }

        /* ── SECTIONS ── */
        .section {
          padding-top: 88px;
        }
        .section:first-child { padding-top: 0; }

        /* ── HERO ── */
        .hero {
          padding: 64px 0 80px;
          border-bottom: 1px solid var(--line);
          margin-bottom: 0;
        }
        .hero-eyebrow {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 0.68rem;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: var(--text-3);
          margin-bottom: 24px;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .hero-eyebrow::before {
          content: '';
          width: 20px; height: 1px;
          background: var(--text-3);
          display: inline-block;
        }
        .hero-h1 {
          font-family: 'Syne', sans-serif;
          font-weight: 800;
          font-size: clamp(2.2rem, 5vw, 3.2rem);
          letter-spacing: -0.04em;
          line-height: 1.0;
          color: var(--text-1);
          margin-bottom: 24px;
        }
        .hero-desc {
          font-size: 0.92rem;
          color: var(--text-2);
          line-height: 1.75;
          max-width: 520px;
          margin-bottom: 40px;
          font-weight: 300;
        }
        .tag-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .tag {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 0.68rem;
          padding: 4px 10px;
          border: 1px solid var(--line-strong);
          border-radius: 3px;
          color: var(--text-3);
          letter-spacing: 0.02em;
        }

        /* ── STEPS ── */
        .steps { margin: 20px 0 28px; }
        .step {
          display: flex;
          gap: 18px;
          padding: 14px 0;
          border-bottom: 1px solid var(--line);
        }
        .step:last-child { border-bottom: none; }
        .step-n {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 0.65rem;
          color: var(--text-3);
          width: 16px;
          flex-shrink: 0;
          padding-top: 3px;
        }
        .step-body { font-size: 0.85rem; color: var(--text-2); line-height: 1.7; flex: 1; }

        /* ── ANALYSIS GRID ── */
        .a-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          border: 1px solid var(--line);
          border-radius: 6px;
          overflow: hidden;
          margin: 20px 0;
          gap: 1px;
          background: var(--line);
        }
        .a-cell {
          background: var(--bg);
          padding: 16px 18px;
        }
        .a-cell-label {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 0.64rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--text-3);
          margin-bottom: 7px;
        }
        .a-cell-body { font-size: 0.8rem; color: var(--text-2); line-height: 1.6; }

        /* ── VISIBILITY MODES ── */
        .vis-table {
          border: 1px solid var(--line);
          border-radius: 6px;
          overflow: hidden;
          margin: 20px 0;
        }
        .vis-row {
          display: flex; align-items: center; gap: 16px;
          padding: 11px 16px;
          border-bottom: 1px solid var(--line);
          font-size: 0.83rem;
        }
        .vis-row:last-child { border-bottom: none; }
        .vis-mode {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 0.72rem;
          color: var(--text-2);
          min-width: 80px;
          flex-shrink: 0;
        }
        .vis-desc { color: var(--text-2); }

        /* ── AGENT EXAMPLES ── */
        .agent-list { display: flex; flex-direction: column; gap: 1px; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; margin: 20px 0; }
        .agent-item {
          padding: 14px 18px;
          background: var(--bg);
          border-bottom: 1px solid var(--line);
        }
        .agent-item:last-child { border-bottom: none; }
        .agent-q {
          font-size: 0.84rem; color: var(--text-1); margin-bottom: 5px;
          display: flex; gap: 10px; align-items: flex-start;
        }
        .agent-q::before { content: '→'; color: var(--text-3); font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; flex-shrink: 0; padding-top: 1px; }
        .agent-a { font-size: 0.78rem; color: var(--text-3); padding-left: 20px; line-height: 1.6; }

        /* ── SHORTCUT LIST ── */
        .sc-list { display: flex; flex-direction: column; gap: 1px; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; margin: 20px 0; }
        .sc-row {
          display: flex; align-items: center; gap: 16px;
          padding: 9px 16px;
          background: var(--bg);
          border-bottom: 1px solid var(--line);
          font-size: 0.8rem;
        }
        .sc-row:last-child { border-bottom: none; }
        .sc-key { min-width: 90px; flex-shrink: 0; }
        .sc-val { font-family: 'IBM Plex Mono', monospace; font-size: 0.73rem; color: var(--text-3); }

        /* ── COLORS ── */
        .swatch-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
        .swatch { width: 28px; height: 28px; border-radius: 50%; box-shadow: 0 0 0 1px rgba(255,255,255,0.06); }

        /* ── RESPONSIVE ── */
        @media (max-width: 860px) {
          .sidebar { transform: translateX(-100%); transition: transform 0.22s ease; }
          .sidebar.open { transform: translateX(0); box-shadow: 8px 0 40px rgba(0,0,0,0.6); }
          .content { margin-left: 0; }
          .content-inner { padding: 68px 22px 80px; }
          .mobile-nav { display: flex; }
          .hero { padding-top: 32px; }
          .a-grid { grid-template-columns: 1fr; }
          .DGrid2 { grid-template-columns: 1fr !important; }
        }
        @media (max-width: 520px) {
          .hero-h1 { font-size: 2rem; }
        }

        /* ── FADE ── */
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .section { animation: fadeIn 0.35s ease both; }
      `}</style>

      {searchOpen && <Search onClose={() => setSearch(false)} onNavigate={scrollTo} />}

      <div className="layout">

        {/* ── MOBILE NAV ── */}
        <header className="mobile-nav">
          <button className="icon-btn" onClick={() => setDrawer(!drawerOpen)} aria-label="Menu">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <span className="mobile-logo">Ozon</span>
          <button className="icon-btn" onClick={() => setSearch(true)} style={{ marginLeft: "auto" }} aria-label="Search">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
          </button>
        </header>

        {/* ── SIDEBAR ── */}
        <aside className={`sidebar${drawerOpen ? " open" : ""}`}>
          <div className="sidebar-header">
            <div className="sidebar-logo">
              <div className="logo-mark">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-2)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 3h7l3 3 3-3h5v5l-3 3 3 3v5h-5l-3-3-3 3H3v-5l3-3-3-3V3z"/>
                </svg>
              </div>
              <span className="logo-name">Ozon</span>
            </div>
            <span className="logo-sub">docs</span>
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", padding: 4, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-3)" }}
              aria-label="Toggle theme"
            >
              {theme === "dark" ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                </svg>
              )}
            </button>
          </div>

          <button className="search-btn" onClick={() => setSearch(true)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
            Search
            <span className="search-shortcut">⌘K</span>
          </button>

          <nav className="nav-section">
            <div className="nav-label-group">Contents</div>
            {NAV.map(item => (
              <div
                key={item.id}
                className={`nav-item${active === item.id ? " active" : ""}`}
                onClick={() => scrollTo(item.id)}
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === "Enter" && scrollTo(item.id)}
              >
                <span className="nav-num">{item.num}</span>
                <span className="nav-text">{item.label}</span>
              </div>
            ))}
          </nav>

          <div className="sidebar-footer">
            <a href="/" className="open-btn">
              Open Calculator
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                <path d="m9 18 6-6-6-6"/>
              </svg>
            </a>
          </div>
        </aside>

        {/* ── CONTENT ── */}
        <main className="content">
          <div className="content-inner">

            {/* 00 — INTRO */}
            <section id="intro" className="section hero">
              <div className="hero-eyebrow">Built on Desmos Studio</div>
              <h1 className="hero-h1">Ozon<br/>Documentation</h1>
              <p className="hero-desc">
                A graphing calculator built on the Desmos engine. Combines the full Desmos feature set with calculus operations, symbolic computation, complex number support, and an AI agent that understands natural language.
              </p>
              <div className="tag-row">
                {["Desmos-powered","Derivatives","Integrals","Complex Numbers","Function Analysis","AI Agent","OCR & Voice","Polar & Parametric"].map(t => (
                  <span key={t} className="tag">{t}</span>
                ))}
              </div>
            </section>

            {/* 01 — QUICK START */}
            <section id="quickstart" className="section">
              <H2 num="01">Quick Start</H2>
              <P>No setup required. Open Ozon and start typing — graphs render in real time.</P>
              <div className="steps">
                {[
                  [<>Press <K>Enter</K> to create a new expression row, then type any expression — <C>sin(x)</C>, <C>x^2</C>, or <C>x^2 + y^2 = 25</C>.</>],
                  [<>Click the <strong style={{color:"var(--text-1)",fontWeight:500}}>color dot</strong> to change a curve's color. Click the <strong style={{color:"var(--text-1)",fontWeight:500}}>eye icon</strong> to toggle visibility.</>],
                  [<>Click <strong style={{color:"var(--text-1)",fontWeight:500}}>ⓘ</strong> on any expression to open the function analysis panel — domain, range, asymptotes, and more.</>],
                  [<>For derivatives, type <C>{'\\frac{d}{dx}\\sin(x)'}</C>. For integrals, type <C>\int \sin(x)\,dx</C>. Both show as a dual-curve overlay.</>],
                  [<>Open the <strong style={{color:"var(--text-1)",fontWeight:500}}>AI Agent</strong> and ask in plain English: <em style={{color:"var(--text-2)"}}>"plot the tangent line to sin(x) at x=1"</em>.</>],
                ].map(([body], i) => (
                  <div key={i} className="step">
                    <span className="step-n">{String(i + 1).padStart(2, "0")}</span>
                    <div className="step-body">{body}</div>
                  </div>
                ))}
              </div>
              <Callout variant="tip">
                Use the shortcut <K>int</K> + <K>Tab</K> to expand an integral template, or <K>ddx</K> + <K>Tab</K> for a derivative. Full list in section 15.
              </Callout>
            </section>

            {/* 02 — GRAPHING BASICS */}
            <section id="graphing" className="section">
              <H2 num="02">Graphing Basics</H2>
              <P>Ozon accepts the full Desmos expression syntax. Type expressions directly — no <C>y=</C> prefix needed.</P>

              <H3>Functions of x</H3>
              <SGrid items={[
                {latex:"sin(x)",       desc:"Sine wave"},
                {latex:"x^2",          desc:"Parabola"},
                {latex:"ln(x)",        desc:"Natural logarithm"},
                {latex:"e^x",          desc:"Exponential growth"},
                {latex:"abs(x)",       desc:"Absolute value"},
                {latex:"sqrt(x)",      desc:"Square root"},
                {latex:"1/x",          desc:"Hyperbola"},
                {latex:"floor(x)",     desc:"Greatest integer function"},
              ]} />

              <Hr />
              <H3>Implicit Equations</H3>
              <P>Define any relation between x and y — Ozon graphs the full curve without solving for y.</P>
              <SGrid items={[
                {latex:"x^2 + y^2 = 25",     desc:"Circle, radius 5"},
                {latex:"x*y = 1",             desc:"Rectangular hyperbola"},
                {latex:"x^2/4 + y^2/9 = 1",  desc:"Ellipse"},
                {latex:"y^2 = x^3 - x",      desc:"Elliptic curve"},
              ]} />

              <Hr />
              <H3>Inequalities & Regions</H3>
              <SGrid items={[
                {latex:"y > x^2",           desc:"Region above the parabola"},
                {latex:"y <= sin(x)",       desc:"Region below the sine curve"},
                {latex:"x^2 + y^2 < 25",   desc:"Open disk, radius 5"},
              ]} />

              <Hr />
              <H3>Named Functions</H3>
              <P>Define reusable functions by name — available across all expressions in the session.</P>
              <SGrid items={[
                {latex:"f(x) = sin(x)",       desc:"Define f"},
                {latex:"g(x) = x^2 + 1",      desc:"Define g"},
                {latex:"f(x) + g(x)",          desc:"Compose defined functions"},
                {latex:"h(x,y) = x^2 + y^2",  desc:"Multi-variable definition"},
              ]} />
            </section>

            {/* 03 — TRIG */}
            <section id="trig" className="section">
              <H2 num="03">Trigonometric & Hyperbolic</H2>
              <P>Full support for standard, inverse, hyperbolic, and inverse hyperbolic functions. MathLive handles all standard LaTeX notations.</P>

              <H3>Standard Trigonometry</H3>
              <DGrid items={[
                {fn:"\\sin(x)",name:"Sine"},{fn:"\\cos(x)",name:"Cosine"},
                {fn:"\\tan(x)",name:"Tangent"},{fn:"\\cot(x)",name:"Cotangent"},
                {fn:"\\sec(x)",name:"Secant"},{fn:"\\csc(x)",name:"Cosecant"},
              ]} />

              <H3>Inverse Trigonometry</H3>
              <DGrid items={[
                {fn:"\\arcsin(x)",name:"Arcsine"},{fn:"\\arccos(x)",name:"Arccosine"},
                {fn:"\\arctan(x)",name:"Arctangent"},{fn:"\\arccot(x)",name:"Arccotangent"},
                {fn:"\\arcsec(x)",name:"Arcsecant"},{fn:"\\arccsc(x)",name:"Arccosecant"},
              ]} />

              <H3>Hyperbolic</H3>
              <DGrid items={[
                {fn:"\\sinh(x)",name:"Hyp. sine"},{fn:"\\cosh(x)",name:"Hyp. cosine"},
                {fn:"\\tanh(x)",name:"Hyp. tangent"},{fn:"\\coth(x)",name:"Hyp. cotangent"},
                {fn:"\\sech(x)",name:"Hyp. secant"},{fn:"\\csch(x)",name:"Hyp. cosecant"},
              ]} />

              <H3>Inverse Hyperbolic</H3>
              <DGrid items={[
                {fn:"\\arcsinh(x)",name:"Inv. hyp. sine"},{fn:"\\arccosh(x)",name:"Inv. hyp. cosine"},
                {fn:"\\arctanh(x)",name:"Inv. hyp. tangent"},{fn:"\\arccoth(x)",name:"Inv. hyp. cotangent"},
              ]} />

              <Callout variant="note">
                If you type <C>arctan</C> manually, Ozon normalises it before passing it to the Desmos engine. The virtual keyboard assembles complex names automatically.
              </Callout>
            </section>

            {/* 04 — COMPLEX NUMBERS */}
            <section id="complex" className="section">
              <H2 num="04">Complex Numbers</H2>
              <P>Ozon supports complex number arithmetic. Use <C>i</C> as the imaginary unit throughout any expression — the engine handles real and imaginary parts separately.</P>

              <H3>Basic Arithmetic</H3>
              <SGrid items={[
                {latex:"3 + 4i",        desc:"Complex number in rectangular form"},
                {latex:"(1+2i)(3-i)",   desc:"Multiplication — expands to 5+5i"},
                {latex:"(2+3i)/(1-i)",  desc:"Division — rationalised automatically"},
                {latex:"i^2",           desc:"Evaluates to −1"},
                {latex:"i^3",           desc:"Evaluates to −i"},
                {latex:"i^4",           desc:"Evaluates to 1"},
              ]} />

              <Hr />
              <H3>Built-in Complex Functions</H3>
              <DGrid items={[
                {fn:"real(z)",    name:"Real part"},
                {fn:"imag(z)",    name:"Imaginary part"},
                {fn:"abs(z)",     name:"Modulus |z|"},
                {fn:"angle(z)",   name:"Argument arg(z)"},
                {fn:"conj(z)",    name:"Conjugate z̄"},
                {fn:"sign(z)",    name:"Normalised z / |z|"},
              ]} />

              <Hr />
              <H3>Polar & Exponential Form</H3>
              <P>Convert between rectangular and polar forms. Euler's formula <C>e^{"{"}i\\theta{"}"} = cos(θ) + i·sin(θ)</C> works natively.</P>
              <SGrid items={[
                {latex:"e^{i\\pi}",            desc:"Euler's identity — evaluates to −1"},
                {latex:"e^{i\\pi/2}",          desc:"Evaluates to i"},
                {latex:"2 * e^{i * \\pi/4}",   desc:"Polar form r·e^{iθ}"},
                {latex:"r*(cos(θ) + i*sin(θ))", desc:"Explicit polar to rectangular"},
              ]} />

              <Hr />
              <H3>Complex Functions</H3>
              <P>Standard math functions accept complex inputs and return complex outputs.</P>
              <SGrid items={[
                {latex:"sqrt(-1)",        desc:"Returns i"},
                {latex:"sqrt(-4)",        desc:"Returns 2i"},
                {latex:"ln(-1)",          desc:"Returns iπ (principal value)"},
                {latex:"sin(i)",          desc:"Returns i·sinh(1) ≈ 1.1752i"},
                {latex:"cos(1+i)",        desc:"Complex cosine — full support"},
              ]} />

              <Hr />
              <H3>Graphing with Complex Numbers</H3>
              <P>Plot the real or imaginary part of a complex-valued function over a real domain to visualise its behaviour.</P>
              <SGrid items={[
                {latex:"real(e^{ix})",   desc:"Plots cos(x) — real part of e^{ix}"},
                {latex:"imag(e^{ix})",   desc:"Plots sin(x) — imaginary part"},
                {latex:"abs(x + i*x^2)","desc":"Modulus of a complex-valued path"},
              ]} />

              <Callout variant="note">
                Ozon does not render full complex-plane (ℝ² → ℂ) plots. For functions that map real inputs to complex outputs, graph the <C>real()</C> or <C>imag()</C> component. For parametric complex paths, use parametric mode with <C>real(f(t))</C> and <C>imag(f(t))</C> as x and y.
              </Callout>
            </section>

            {/* 05 — DERIVATIVES */}
            <section id="derivatives" className="section">
              <H2 num="05">Derivatives</H2>
              <P>Derivative expressions render as dual-curve plots — dotted for the parent function, solid for the computed derivative — so you can compare them in context.</P>

              <H3>First Derivative</H3>
              <SGrid items={[
                {latex:"\\frac{d}{dx}\\sin(x)",  desc:"Shows sin(x) dotted + cos(x) solid"},
                {latex:"\\frac{d}{dx}f(x)",      desc:"Derivative of a named function"},
                {latex:"\\frac{d}{dt}r(t)",      desc:"Derivative with respect to t"},
              ]} />

              <Hr />
              <H3>Higher-Order Derivatives</H3>
              <SGrid items={[
                {latex:"\\frac{d^2}{dx^2}x^3",       desc:"Second derivative of x³"},
                {latex:"\\frac{d^3}{dx^3}\\sin(x)",   desc:"Third derivative — returns −cos(x)"},
                {latex:"\\frac{d^n}{dx^n}f(x)",       desc:"nth-order derivative"},
              ]} />

              <Hr />
              <H3>Evaluation at a Point</H3>
              <SGrid items={[
                {latex:"\\frac{d}{dx}\\sin(x)\\bigm|_{x=2}",     desc:"Numerical value at x = 2"},
                {latex:"\\frac{d^2}{dx^2}x^3\\bigm|_{x=1}",      desc:"Second derivative at x = 1"},
              ]} />

              <Hr />
              <H3>Partial Derivatives</H3>
              <SGrid items={[
                {latex:"\\frac{\\partial}{\\partial x}f(x,y)", desc:"Partial derivative w.r.t. x"},
                {latex:"\\frac{\\partial}{\\partial y}f(x,y)", desc:"Partial derivative w.r.t. y"},
              ]} />

              <Callout variant="note">
                The dotted curve is always the original function; the solid curve is the computed result. Curve labels appear on hover.
              </Callout>
            </section>

            {/* 06 — INTEGRALS */}
            <section id="integrals" className="section">
              <H2 num="06">Integrals</H2>
              <P>The <C>dx</C> differential is mandatory — it specifies the variable of integration and is required for correct parsing.</P>

              <H3>Indefinite Integrals</H3>
              <SGrid items={[
                {latex:"\\int \\sin(x)\\,dx",  desc:"Antiderivative — shows integrand dotted, −cos(x) solid"},
                {latex:"\\int x^2\\,dx",        desc:"Returns x³/3"},
                {latex:"\\int e^x\\,dx",        desc:"Returns eˣ"},
              ]} />

              <Hr />
              <H3>Definite Integrals</H3>
              <P>Bounds are set with subscript and superscript. The region between the curve and the x-axis is shaded; the numeric result appears in the sidebar.</P>
              <SGrid items={[
                {latex:"\\int_{0}^{\\pi} \\sin(x)\\,dx",   desc:"Area from 0 to π — result: 2"},
                {latex:"\\int_{-1}^{1} x^2\\,dx",          desc:"Result: 2/3"},
                {latex:"\\int_{0}^{\\infty} e^{-x}\\,dx",  desc:"Improper integral — result: 1"},
              ]} />

              <Hr />
              <H3>Area Mode</H3>
              <P>Toggle <strong style={{color:"var(--text-1)",fontWeight:500}}>Area Mode</strong> to integrate <C>|f(x)|</C> — the total unsigned area — useful when the function crosses the x-axis within the bounds.</P>
              <SGrid items={[
                {latex:"\\int_{0}^{2\\pi} \\sin(x)\\,dx",    desc:"Standard: 0 (positive and negative cancel)"},
                {latex:"\\int_{0}^{2\\pi} |\\sin(x)|\\,dx",  desc:"Area Mode: 4 (total geometric area)"},
              ]} />
            </section>

            {/* 07 — SLIDERS */}
            <section id="sliders" className="section">
              <H2 num="07">Sliders & Parameters</H2>
              <P>Any free variable (not x, y, r, or t) automatically becomes a slider. Define sliders explicitly with a simple assignment.</P>

              <H3>Creating Sliders</H3>
              <SGrid items={[
                {latex:"a = 1",         desc:"Slider for a, default value 1"},
                {latex:"k = 2.5",       desc:"Slider with decimal initial value"},
                {latex:"\\omega = \\pi",desc:"Slider initialised at π"},
              ]} />

              <Hr />
              <H3>Using Parameters</H3>
              <SGrid items={[
                {latex:"a*sin(b*x)",          desc:"Amplitude a, frequency b — both sliders"},
                {latex:"x^2 + k*x + c",       desc:"Quadratic with two parameters"},
                {latex:"e^{-a*x}*cos(\\omega x)", desc:"Damped oscillation"},
              ]} />

              <Hr />
              <H3>Bounds, Step & Animation</H3>
              <P>In the slider control row, set custom min, max, and step values. Press <strong style={{color:"var(--text-1)",fontWeight:500}}>▶ Play</strong> to animate the slider across its range, creating smooth real-time animations of dependent curves.</P>

              <Table head={["Property","Default","Notes"]} rows={[
                ["min","−10","Supports expressions: −2π"],
                ["max","10","Supports expressions: 2π"],
                ["step","continuous","Set to 1 for integer stepping"],
              ]} />
            </section>

            {/* 08 — DOMAIN & RANGE */}
            <section id="domain-range" className="section">
              <H2 num="08">Domain & Range Restrictions</H2>
              <P>Restrict which portion of a curve is drawn by appending a condition in curly braces after the expression.</P>

              <H3>Domain Restrictions</H3>
              <SGrid items={[
                {latex:"\\sin(x)\\{-\\pi < x < \\pi\\}",  desc:"Sine, plotted only on (−π, π)"},
                {latex:"\\sqrt{x}\\{x >= 0\\}",            desc:"Square root, x ≥ 0 only"},
                {latex:"x^2\\{0 <= x <= 3\\}",            desc:"Parabola on a closed interval"},
              ]} />

              <Hr />
              <H3>Range Restrictions</H3>
              <SGrid items={[
                {latex:"x^2\\{0 < y < 4\\}",       desc:"Parabola with y clipped to (0, 4)"},
                {latex:"\\sin(x)\\{0 < y <= 1\\}",  desc:"Sine, positive lobe only"},
              ]} />

              <Hr />
              <H3>Combined</H3>
              <SGrid items={[
                {latex:"x^2\\{-2 <= x <= 2, 0 <= y <= 3\\}", desc:"Both x and y constrained"},
              ]} />

              <Callout variant="note">
                Curly braces are normalised by Ozon regardless of how MathLive formats them. Type them directly or use the virtual keyboard — both work identically.
              </Callout>
            </section>

            {/* 09 — PIECEWISE */}
            <section id="piecewise" className="section">
              <H2 num="09">Piecewise Functions</H2>
              <P>Define piecewise functions using curly braces with <C>condition: value</C> pairs separated by commas. The final value without a condition is the default catch-all.</P>

              <H3>Syntax</H3>
              <SGrid items={[
                {latex:"\\{x < 0: -x, x\\}",               desc:"Absolute value in piecewise form"},
                {latex:"\\{x < 0: \\sin(x), \\cos(x)\\}",  desc:"sin for x < 0, cos otherwise"},
                {latex:"\\{-2 < x < 2: x^2, 2x\\}",        desc:"Parabola on (−2,2), linear elsewhere"},
                {latex:"\\{x < 0: -1, x = 0: 0, 1\\}",     desc:"Sign function — three pieces"},
              ]} />

              <Callout variant="tip">
                Stack as many conditions as needed. Ozon evaluates them top-to-bottom; the first matching condition wins.
              </Callout>
            </section>

            {/* 10 — POLAR & PARAMETRIC */}
            <section id="polar" className="section">
              <H2 num="10">Polar & Parametric</H2>

              <H3>Polar Coordinates</H3>
              <P>Use <C>r</C> as radius and <C>θ</C> as angle. The θ-domain is controlled via the slider bounds UI.</P>
              <SGrid items={[
                {latex:"r = \\sin(\\theta)",       desc:"Circle through the origin"},
                {latex:"r = \\cos(2\\theta)",       desc:"Four-petal rose curve"},
                {latex:"r = 1 + \\cos(\\theta)",    desc:"Cardioid"},
                {latex:"r = \\theta",               desc:"Archimedean spiral"},
                {latex:"r = e^{0.1\\theta}",        desc:"Logarithmic spiral"},
              ]} />

              <Hr />
              <H3>Parametric Curves</H3>
              <P>Enter a comma-separated pair of expressions in parentheses using parameter <C>t</C>. Control the t-domain via the slider bounds.</P>
              <SGrid items={[
                {latex:"(\\cos(t), \\sin(t))",                          desc:"Unit circle"},
                {latex:"(\\cos(3t), \\sin(2t))",                        desc:"Lissajous figure (3:2)"},
                {latex:"(t, t^2)",                                       desc:"Parabola, parametric form"},
                {latex:"(t*\\cos(t), t*\\sin(t))",                      desc:"Archimedean spiral"},
                {latex:"((2+\\cos(3t))\\cos(2t), (2+\\cos(3t))\\sin(2t))", desc:"Torus knot projection"},
              ]} />
            </section>

            {/* 11 — FUNCTION ANALYSIS */}
            <section id="analysis" className="section">
              <H2 num="11">Function Analysis</H2>
              <P>Click <strong style={{color:"var(--text-1)",fontWeight:500}}>ⓘ</strong> on any expression to open the full analysis panel. Ozon computes these properties using symbolic computation.</P>

              <div className="a-grid">
                {[
                  {label:"Domain",            body:"All valid x-values. Returned as an interval or union of intervals."},
                  {label:"Range",             body:"All possible output values. Computed symbolically where feasible."},
                  {label:"x-Intercepts",      body:"Where y = 0. All real roots are listed."},
                  {label:"y-Intercept",       body:"The value f(0) — where the function crosses the y-axis."},
                  {label:"Local Minima",      body:"Where f′(x) = 0 and f″(x) > 0. Listed as (x, y)."},
                  {label:"Local Maxima",      body:"Where f′(x) = 0 and f″(x) < 0. Listed as (x, y)."},
                  {label:"Inflection Points", body:"Where concavity changes — f″(x) = 0 with sign change."},
                  {label:"Vertical Asymptotes",body:"x-values where f(x) → ±∞, via one-sided limits."},
                  {label:"Horizontal Asymptotes",body:"Limits as x → ±∞. Both directions computed separately."},
                  {label:"Oblique Asymptotes",body:"Diagonal asymptotes y = mx + b as x → ±∞."},
                  {label:"Parity",            body:"Even (f(−x)=f(x)), Odd (f(−x)=−f(x)), or Neither."},
                  {label:"Monotonicity",      body:"Intervals where f is increasing (f′>0) or decreasing (f′<0)."},
                ].map(c => (
                  <div key={c.label} className="a-cell">
                    <div className="a-cell-label">{c.label}</div>
                    <div className="a-cell-body">{c.body}</div>
                  </div>
                ))}
              </div>

              <Hr />
              <H3>Tangent Line</H3>
              <P>The analysis panel computes the tangent equation in point-slope form. Press <strong style={{color:"var(--text-1)",fontWeight:500}}>Plot Tangent Line</strong> to add it directly to the graph with a draggable slider for the evaluation point.</P>
              <SGrid items={[
                {latex:"y - f(a) = f'(a)(x - a)", desc:"Tangent at x = a — point-slope form"},
              ]} />

              <Callout variant="tip">
                After plotting, drag the slider for <C>a</C> to see the tangent line sweep along the curve in real time — a direct demonstration of local linearity.
              </Callout>
            </section>

            {/* 12 — SERIES */}
            <section id="series" className="section">
              <H2 num="12">Sequences & Series</H2>
              <P>Evaluate summations and analyse convergence using standard sigma notation.</P>

              <H3>Notation</H3>
              <SGrid items={[
                {latex:"\\sum_{n=1}^{\\infty} \\frac{1}{n^2}",   desc:"p-series — converges to π²/6"},
                {latex:"\\sum_{n=0}^{\\infty} \\frac{x^n}{n!}",  desc:"Taylor series for eˣ"},
                {latex:"\\sum_{n=0}^{10} n^2",                    desc:"Finite sum — result shown inline"},
                {latex:"\\sum_{n=1}^{\\infty} \\frac{1}{n}",     desc:"Harmonic series — diverges"},
              ]} />

              <Hr />
              <H3>Analysis Output</H3>
              <Table head={["Property","Description"]} rows={[
                ["Sequence Limit","Whether the sequence of terms aₙ converges as n → ∞ and its limit."],
                ["Series Sum","Whether Σaₙ converges and the closed-form sum if one exists."],
                ["Radius of Convergence","For power series Σcₙxⁿ — the value R and convergence interval."],
              ]} />

              <Callout variant="note">
                Convergence analysis requires a single-variable expression in <C>n</C>. For highly complex series, Ozon may fall back to numerical approximation.
              </Callout>
            </section>

            {/* 13 — AI AGENT */}
            <section id="agent" className="section">
              <H2 num="13">AI Agent</H2>
              <P>The built-in AI agent translates natural language into Desmos-compatible LaTeX. It handles plotting, calculus, function analysis, and tangent line visualizations — without writing a single symbol.</P>

              <H3>Example Prompts</H3>
              <div className="agent-list">
                {[
                  {q:"Plot the derivative of sin(x)",            a:"Graphs sin(x) with its derivative cos(x) as a dual-curve visualization."},
                  {q:"Find the integral of x² from 0 to 1",      a:"Definite integral with shaded area — result: 1/3."},
                  {q:"Show the tangent line to x² at x = 3",     a:"Adds x², the tangent y = 6x − 9, and a slider for the evaluation point."},
                  {q:"Graph a cardioid",                          a:"Plots r = 1 + cos(θ) in polar coordinates."},
                  {q:"Analyse the function 1/x",                  a:"Opens the analysis panel — domain, asymptotes, intercepts."},
                  {q:"Multiply (2+3i) by (1-i)",                  a:"Evaluates the complex product and optionally plots the result on the Argand plane."},
                ].map((ex, i) => (
                  <div key={i} className="agent-item">
                    <div className="agent-q">{ex.q}</div>
                    <div className="agent-a">{ex.a}</div>
                  </div>
                ))}
              </div>

              <Hr />
              <H3>OCR Input</H3>
              <P>Upload or photograph a handwritten or printed expression. The agent uses optical character recognition to parse the formula and convert it to LaTeX. Supports handwritten notes, textbook pages, and printed equations.</P>

              <Hr />
              <H3>Voice Input</H3>
              <P>Press the microphone button and speak — <em style={{color:"var(--text-2)"}}>"integral of sine x from zero to pi"</em> or <em style={{color:"var(--text-2)"}}>"derivative of natural log of x"</em>. Audio is transcribed and interpreted by the agent.</P>

              <Hr />
              <H3>LaTeX Rules the Agent Enforces</H3>
              <Table head={["Context","Rule"]} rows={[
                ["Integrals",     "Always appends dx differential — required by Ozon's parser"],
                ["Derivatives",   "Uses \\frac{d}{dx} notation — never prime notation for plotting"],
                ["Evaluations",   "Uses \\bigm|_{x=a} for point evaluations"],
                ["Tangent lines", "Automatically adds a slider variable a=1 for the evaluation point"],
              ]} />
            </section>

            {/* 14 — INPUT METHODS */}
            <section id="input" className="section">
              <H2 num="14">Input Methods</H2>

              <H3>MathLive Keyboard</H3>
              <P>Every expression field uses MathLive — a professional LaTeX editor with a virtual keyboard. Click any expression field to activate it; the virtual keyboard appears automatically on touch devices.</P>

              <Hr />
              <H3>Inline Shortcuts</H3>
              <P>Type a shortcut string then press <K>Tab</K> to expand it to a full template. Placeholders are navigable with additional <K>Tab</K> presses.</P>

              <div className="sc-list">
                {[
                  ["int",     "\\int □ dx"],
                  ["dint",    "\\int_{□}^{□} □ dx"],
                  ["ddx",     "\\frac{d}{dx} □"],
                  ["d2dx2",   "\\frac{d²}{dx²} □"],
                  ["dndxn",   "\\frac{dⁿ}{dxⁿ} □"],
                  ["deriv",   "\\frac{d}{d□} □ |_{□=□}"],
                  ["pdx",     "\\frac{∂}{∂x} □"],
                  ["pdy",     "\\frac{∂}{∂y} □"],
                  ["lim",     "\\lim_{□ → □} □"],
                  ["limx",    "\\lim_{x → □} □"],
                  ["sum",     "\\sum_{□}^{□} □"],
                  ["sumn",    "\\sum_{n=□}^{□} □"],
                ].map(([s, out]) => (
                  <div key={s} className="sc-row">
                    <span className="sc-key"><K>{s}</K></span>
                    <span className="sc-val">{out}</span>
                  </div>
                ))}
              </div>

              <Hr />
              <H3>Smart Parentheses</H3>
              <P>The <K>)</K> key has smart behaviour: if brackets are balanced, it wraps the current group in <C>\left(...\right)</C>; if there's an open bracket, it closes it naturally instead.</P>

              <Hr />
              <H3>Special Constants</H3>
              <DGrid items={[
                {fn:"\\pi",            name:"π ≈ 3.14159…"},
                {fn:"e",               name:"Euler's number ≈ 2.71828…"},
                {fn:"\\infty",         name:"Infinity"},
                {fn:"\\theta",         name:"θ — polar / angular variable"},
                {fn:"i",               name:"Imaginary unit"},
                {fn:"\\alpha, \\beta", name:"Greek parameter names"},
              ]} />
            </section>

            {/* 15 — SHORTCUTS */}
            <section id="shortcuts" className="section">
              <H2 num="15">Keyboard Shortcuts</H2>
              <P>Complete shortcut reference. Type the string then press <K>Tab</K> to expand.</P>

              <Table head={["Shortcut","Expands To"]} rows={[
                ["int",    "\\int □ \\mathrm{d}x"],
                ["dint",   "\\int_{□}^{□} □ \\mathrm{d}x"],
                ["ddx",    "\\frac{d}{dx} □"],
                ["ddy",    "\\frac{d}{dy} □"],
                ["d2dx2",  "\\frac{d^{2}}{dx^{2}} □"],
                ["dndxn",  "\\frac{d^{□}}{dx^{□}} □ \\bigm|_{x=□}"],
                ["deriv",  "\\frac{d}{d□} □ \\bigm|_{□=□}"],
                ["pdx",    "\\frac{\\partial}{\\partial x} □"],
                ["pdy",    "\\frac{\\partial}{\\partial y} □"],
                ["lim",    "\\lim_{□ \\to □} □"],
                ["limx",   "\\lim_{x \\to □} □"],
                ["sum",    "\\sum_{□}^{□} □"],
                ["sumn",   "\\sum_{n=□}^{□} □"],
              ]} />

              <H3>Global Actions</H3>
              <Table head={["Key","Action"]} rows={[
                ["Enter",     "Add a new expression row below"],
                ["Tab",       "Expand shortcut / jump to next placeholder"],
                ["Backspace", "Delete content, or remove row if empty"],
                ["⌘K",        "Open search"],
              ]} />
            </section>

            {/* 16 — COLORS & VISIBILITY */}
            <section id="visibility" className="section">
              <H2 num="16">Colors & Visibility</H2>

              <H3>Color Picker</H3>
              <P>Click the colored circle beside any expression to open the system color picker. Colors are applied immediately to all associated curves — parent plus derivative or integral.</P>
              <div className="swatch-row">
                {["#2d70b3","#e74c3c","#27ae60","#e67e22","#8e44ad","#1abc9c","#f39c12","#d35400","#2980b9","#c0392b"].map(c => (
                  <div key={c} className="swatch" style={{background:c}} title={c} />
                ))}
              </div>

              <Callout variant="note">
                In dark mode, Ozon inverts graph colors using HSL hue rotation (complementary color), matching Desmos's dark-mode behaviour. The color picker always shows the original; Ozon handles the visual adaptation.
              </Callout>

              <Hr />
              <H3>Visibility Modes</H3>
              <P>Derivative and integral expressions expose a four-mode dropdown for granular curve control.</P>
              <div className="vis-table">
                {[
                  {mode:"all",      desc:"Show both the parent function and the derivative / integral curve"},
                  {mode:"parent",   desc:"Show only the original dotted parent function"},
                  {mode:"operated", desc:"Show only the computed derivative or integral"},
                  {mode:"none",     desc:"Hide all curves — expression is preserved in the list"},
                ].map(r => (
                  <div key={r.mode} className="vis-row">
                    <span className="vis-mode">{r.mode}</span>
                    <span className="vis-desc">{r.desc}</span>
                  </div>
                ))}
              </div>

              <Hr />
              <H3>Graph Legend</H3>
              <P>The floating <strong style={{color:"var(--text-1)",fontWeight:500}}>Graph Legend</strong> panel (top-right of the graph) lists every active expression with its curve type indicator — dotted for parent, solid for result, filled for area — alongside its color and the symbolically computed result label. The panel is draggable and collapsible.</P>

              <div style={{height:56}} />

              <div style={{
                padding: "28px 32px",
                border: "1px solid var(--line-strong)",
                borderRadius: 8,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 24,
                flexWrap: "wrap",
              }}>
                <div>
                  <div style={{fontSize:"0.82rem",color:"var(--text-2)",marginBottom:4}}>Ready to start?</div>
                  <div style={{fontFamily:"'Syne',sans-serif",fontWeight:700,fontSize:"1rem",letterSpacing:"-0.02em",color:"var(--text-1)"}}>Open Ozon Calculator</div>
                </div>
                <a href="/" style={{
                  display:"inline-flex",alignItems:"center",gap:8,
                  padding:"9px 18px",
                  background:"var(--text-1)",color:"var(--bg)",
                  borderRadius:6,
                  fontFamily:"'IBM Plex Sans',sans-serif",
                  fontSize:"0.82rem",fontWeight:600,
                  textDecoration:"none",
                  transition:"opacity 0.15s",
                  whiteSpace:"nowrap",
                  flexShrink:0,
                }}>
                  Launch
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                    <path d="m9 18 6-6-6-6"/>
                  </svg>
                </a>
              </div>
            </section>

          </div>
        </main>
      </div>
    </>
  );
}