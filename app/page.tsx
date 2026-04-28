"use client";

import { useState, useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import Link from "next/link";
import SplashScreen from "@/components/SplashScreen";
import {
  ArrowRight, Sigma, Zap, Layers, FunctionSquare,
  ChevronRight, Sparkles, ArrowUpRight, MousePointer2,
  Infinity, BarChart2, Brain, GitBranch
} from "lucide-react";
import { ReactLenis } from "@studio-freight/react-lenis";
import { motion, useInView, useScroll, useTransform, AnimatePresence } from "framer-motion";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger, useGSAP);
}

// ─── MAGNETIC BUTTON ─────────────────────────────────────────────────────────
const MagneticButton = ({
  children, href, primary, secondary, className = "", style = {}
}: {
  children?: React.ReactNode; href?: string; primary?: boolean;
  secondary?: boolean; className?: string; style?: any;
}) => {
  const buttonRef = useRef<any>(null);
  const textRef = useRef<any>(null);

  const handleMouseMove = (e: any) => {
    const { clientX, clientY } = e;
    const { height, width, left, top } = buttonRef.current.getBoundingClientRect();
    const x = clientX - (left + width / 2);
    const y = clientY - (top + height / 2);
    gsap.to(buttonRef.current, { x: x * 0.3, y: y * 0.3, duration: 1, ease: "power3.out" });
    gsap.to(textRef.current, { x: x * 0.15, y: y * 0.15, duration: 1, ease: "power3.out" });
  };

  const handleMouseLeave = () => {
    gsap.to(buttonRef.current, { x: 0, y: 0, duration: 1, ease: "elastic.out(1.2, 0.4)" });
    gsap.to(textRef.current, { x: 0, y: 0, duration: 1, ease: "elastic.out(1.2, 0.4)" });
  };

  const Element = href ? Link : ("button" as any);
  return (
    <Element
      href={href}
      ref={buttonRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={`magnetic-btn ${primary ? "primary" : "secondary"} ${className}`}
      style={style}
    >
      <span ref={textRef} style={{ display: "inline-flex", alignItems: "center", gap: "10px", pointerEvents: "none" }}>
        {children}
      </span>
    </Element>
  );
};

// ─── CUSTOM CURSOR COMPONENT ──────────────────────────────────────────────────
// Separate component so it always mounts independent of splashDone
const CustomCursor = () => {
  const cursorDot = useRef<HTMLDivElement>(null);
  const cursorRing = useRef<HTMLDivElement>(null);
  const isHovering = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia("(pointer: coarse)").matches) return;

    const dot = cursorDot.current;
    const ring = cursorRing.current;
    if (!dot || !ring) return;

    // Make visible immediately
    gsap.set([dot, ring], { opacity: 1, xPercent: -50, yPercent: -50 });

    const moveCursor = (e: MouseEvent) => {
      gsap.to(dot, { x: e.clientX, y: e.clientY, duration: 0.08, ease: "power2.out" });
      gsap.to(ring, { x: e.clientX, y: e.clientY, duration: 0.35, ease: "power3.out" });
    };

    const onMouseDown = () => {
      gsap.to(ring, { scale: 0.75, duration: 0.15, ease: "power2.out" });
      gsap.to(dot, { scale: 0.5, duration: 0.15 });
    };
    const onMouseUp = () => {
      gsap.to(ring, { scale: 1, duration: 0.5, ease: "elastic.out(1, 0.4)" });
      gsap.to(dot, { scale: 1, duration: 0.4, ease: "elastic.out(1, 0.4)" });
    };

    const onMouseEnterLink = () => {
      isHovering.current = true;
      gsap.to(ring, { scale: 2.2, opacity: 0.6, duration: 0.3, ease: "power2.out" });
      gsap.to(dot, { scale: 0, duration: 0.2 });
    };
    const onMouseLeaveLink = () => {
      isHovering.current = false;
      gsap.to(ring, { scale: 1, opacity: 1, duration: 0.4, ease: "elastic.out(1, 0.4)" });
      gsap.to(dot, { scale: 1, duration: 0.3, ease: "elastic.out(1, 0.4)" });
    };

    window.addEventListener("mousemove", moveCursor);
    window.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mouseup", onMouseUp);

    // Attach to all interactive elements
    const attachHover = () => {
      const els = document.querySelectorAll("a, button, .magnetic-btn, .glow-card");
      els.forEach(el => {
        el.addEventListener("mouseenter", onMouseEnterLink);
        el.addEventListener("mouseleave", onMouseLeaveLink);
      });
    };
    // Use MutationObserver to handle dynamically added elements
    attachHover();
    const observer = new MutationObserver(attachHover);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      window.removeEventListener("mousemove", moveCursor);
      window.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mouseup", onMouseUp);
      observer.disconnect();
    };
  }, []);

  return (
    <>
      <div ref={cursorDot} style={{
        position: "fixed", top: 0, left: 0, width: 8, height: 8,
        background: "#fff", borderRadius: "50%",
        pointerEvents: "none", zIndex: 99999,
        opacity: 0, mixBlendMode: "difference",
        willChange: "transform",
      }} />
      <div ref={cursorRing} style={{
        position: "fixed", top: 0, left: 0, width: 38, height: 38,
        border: "1.5px solid rgba(255,255,255,0.7)", borderRadius: "50%",
        pointerEvents: "none", zIndex: 99998,
        opacity: 0, mixBlendMode: "difference",
        willChange: "transform",
      }} />
    </>
  );
};

// ─── SCROLL PROGRESS BAR ─────────────────────────────────────────────────────
const ScrollProgress = () => {
  const { scrollYProgress } = useScroll();
  return (
    <motion.div
      style={{
        position: "fixed", top: 0, left: 0, right: 0, height: "2px",
        background: "var(--fg)", transformOrigin: "0%",
        scaleX: scrollYProgress, zIndex: 9999,
        opacity: 0.6,
      }}
    />
  );
};

// ─── GLOW CARD ────────────────────────────────────────────────────────────────
const GlowCard = ({ children, className = "", style = {}, delay = 0, index = 0 }: any) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const handleMouseMove = (e: any) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    cardRef.current.style.setProperty("--mouse-x", `${x}px`);
    cardRef.current.style.setProperty("--mouse-y", `${y}px`);
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = ((y - centerY) / centerY) * -3;
    const rotateY = ((x - centerX) / centerX) * 3;
    gsap.to(contentRef.current, {
      rotateX, rotateY, duration: 0.5, ease: "power2.out", transformPerspective: 1000
    });
  };

  const handleMouseLeave = () => {
    if (contentRef.current) {
      gsap.to(contentRef.current, { rotateX: 0, rotateY: 0, duration: 0.8, ease: "power3.out" });
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 60, filter: "blur(12px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.9, delay: delay + index * 0.12, ease: [0.16, 1, 0.3, 1] }}
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={`glow-card ${className}`}
      style={style}
    >
      <div ref={contentRef} className="glow-card-content">{children}</div>
    </motion.div>
  );
};

// ─── HORIZONTAL CARD (separate entrance animation) ────────────────────────────
const HCard = ({ children, style = {}, delay = 0 }: any) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.1 });
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, x: 120, filter: "blur(16px)" }}
      animate={inView ? { opacity: 1, x: 0, filter: "blur(0px)" } : {}}
      transition={{ duration: 1.1, delay, ease: [0.16, 1, 0.3, 1] }}
      style={style}
    >
      {children}
    </motion.div>
  );
};

// ─── STAT COUNTER ─────────────────────────────────────────────────────────────
const StatItem = ({ value, label, delay = 0 }: { value: string; label: string; delay?: number }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 30 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] }}
      style={{ textAlign: "center" }}
    >
      <div className="syne" style={{ fontSize: "clamp(2.5rem, 5vw, 4rem)", fontWeight: 800, letterSpacing: "-0.04em", color: "var(--fg)" }}>
        {value}
      </div>
      <div className="mono" style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: "8px" }}>{label}</div>
    </motion.div>
  );
};

// ─── FLOATING FORMULA ─────────────────────────────────────────────────────────
const FloatingFormula = ({ text, style = {} }: { text: string; style?: any }) => (
  <motion.div
    animate={{ y: [0, -12, 0], opacity: [0.3, 0.7, 0.3] }}
    transition={{ duration: 4 + Math.random() * 3, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: Math.random() * 2 }}
    className="mono"
    style={{
      position: "absolute", fontSize: "0.85rem", color: "var(--muted)",
      pointerEvents: "none", userSelect: "none", ...style
    }}
  >
    {text}
  </motion.div>
);

// ─── MAIN PAGE ────────────────────────────────────────────────────────────────
export default function Home() {
  const [splashDone, setSplashDone] = useState(false);
  const [mounted, setMounted] = useState(false);
  const { theme, setTheme } = useTheme();
  const mainRef = useRef(null);

  useEffect(() => setMounted(true), []);

  const isDark = mounted ? theme === "dark" : true;

  // ── GSAP SCROLL ANIMATIONS ──
  useGSAP(() => {
    if (!splashDone) return;

    // Hero text reveal
    gsap.fromTo(".hero-line",
      { y: 110, opacity: 0, rotateX: -25, filter: "blur(12px)" },
      { y: 0, opacity: 1, rotateX: 0, filter: "blur(0px)", duration: 1.4, stagger: 0.14, ease: "power4.out", delay: 0.1 }
    );
    gsap.fromTo(".fade-in-up",
      { y: 40, opacity: 0, filter: "blur(6px)" },
      { y: 0, opacity: 1, filter: "blur(0px)", duration: 1.2, stagger: 0.12, ease: "power3.out", delay: 0.6 }
    );

    // Hero video parallax
    ScrollTrigger.create({
      trigger: ".hero-section",
      start: "top top",
      end: "bottom top",
      animation: gsap.to(".hero-video-wrapper", {
        scale: 0.88, borderRadius: "36px", opacity: 0.25, y: 180, filter: "blur(6px)", ease: "none"
      }),
      scrub: 1.5,
    });

    // Line draws
    gsap.utils.toArray<HTMLElement>(".draw-line").forEach(line => {
      gsap.fromTo(line,
        { scaleX: 0 },
        { scaleX: 1, duration: 1.8, ease: "expo.inOut", scrollTrigger: { trigger: line, start: "top 90%" } }
      );
    });

    // Horizontal scroll
    const scrollContainer = document.querySelector(".horizontal-scroll-container");
    if (scrollContainer) {
      const getScrollAmount = () => {
        return -((scrollContainer as HTMLElement).scrollWidth - window.innerWidth + 100);
      };
      const tween = gsap.to(scrollContainer, { x: () => getScrollAmount(), ease: "none" });
      ScrollTrigger.create({
        trigger: ".features-wrapper",
        start: "top 8%",
        end: () => `+=${Math.abs(getScrollAmount())}`,
        pin: true,
        animation: tween,
        scrub: 1,
        invalidateOnRefresh: true,
      });
    }

    // Noise overlay subtle animation
    gsap.to(".noise-overlay", { opacity: 0.04, duration: 3, ease: "none", yoyo: true, repeat: -1 });

  }, { scope: mainRef, dependencies: [splashDone] });

  if (!splashDone) return (
    <>
      <CustomCursor />
      <SplashScreen onComplete={() => setSplashDone(true)} />
    </>
  );

  return (
    <ReactLenis root options={{ lerp: 0.07, smoothWheel: true }}>
      <CustomCursor />
      <ScrollProgress />

      <div ref={mainRef} className="app-wrapper">
        <style>{`
          @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;700;800&family=IBM+Plex+Mono:wght@400;500&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap');

          :root {
            --bg: #040404;
            --surface: rgba(12, 12, 12, 0.65);
            --surface-hover: rgba(22, 22, 22, 0.85);
            --surface-solid: #0e0e0e;
            --fg: #f5f5f3;
            --muted: #666666;
            --muted-light: #999999;
            --border: rgba(255,255,255,0.07);
            --border-strong: rgba(255,255,255,0.13);
            --accent: #f5f5f3;
            --accent-fg: #040404;
            --glow: rgba(255,255,255,0.07);
            --glow-strong: rgba(255,255,255,0.13);
            --card-shadow: 0 24px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.06);
            --glass: rgba(4,4,4,0.75);
            --radius-card: 20px;
          }
          :root.light {
            --bg: #f8f8f6;
            --surface: rgba(255,255,255,0.85);
            --surface-hover: rgba(248,248,246,0.95);
            --surface-solid: #ffffff;
            --fg: #0a0a0a;
            --muted: #999999;
            --muted-light: #bbbbbb;
            --border: rgba(0,0,0,0.07);
            --border-strong: rgba(0,0,0,0.14);
            --accent: #0a0a0a;
            --accent-fg: #f8f8f6;
            --glow: rgba(0,0,0,0.04);
            --glow-strong: rgba(0,0,0,0.08);
            --card-shadow: 0 24px 60px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.06);
            --glass: rgba(248,248,246,0.8);
          }

          *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

          html { scroll-behavior: auto; }

          body {
            background: var(--bg);
            color: var(--fg);
            font-family: 'DM Sans', sans-serif;
            overflow-x: hidden;
            -webkit-font-smoothing: antialiased;
          }

          @media (pointer: fine) { *, *::before, *::after { cursor: none !important; } }

          ::selection { background: var(--accent); color: var(--accent-fg); }

          .syne { font-family: 'Syne', sans-serif; }
          .mono { font-family: 'IBM Plex Mono', monospace; letter-spacing: 0.08em; }

          /* ── NOISE TEXTURE ── */
          .noise-overlay {
            position: fixed; inset: 0; z-index: 1000;
            pointer-events: none;
            opacity: 0.035;
            background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='1'/%3E%3C/svg%3E");
            background-size: 200px 200px;
          }

          /* ── TYPOGRAPHY ── */
          .display-huge { font-size: clamp(3.8rem, 9.5vw, 9.5rem); line-height: 0.92; font-weight: 800; letter-spacing: -0.04em; }
          .display-large { font-size: clamp(2.5rem, 5.5vw, 4.8rem); line-height: 1.0; font-weight: 800; letter-spacing: -0.03em; }
          .display-medium { font-size: clamp(1.8rem, 3vw, 2.8rem); line-height: 1.1; font-weight: 700; letter-spacing: -0.025em; }
          .text-gradient { background: linear-gradient(165deg, var(--fg) 0%, var(--muted) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
          .text-dim { color: var(--muted); }

          /* ── NAV ── */
          .nav-glass {
            background: var(--glass);
            backdrop-filter: saturate(180%) blur(16px);
            -webkit-backdrop-filter: saturate(180%) blur(16px);
          }

          /* ── MAGNETIC BUTTON ── */
          .magnetic-btn {
            padding: 15px 34px; border-radius: 100px; font-weight: 500;
            font-size: 0.92rem; text-decoration: none; display: inline-flex;
            justify-content: center; align-items: center; position: relative;
            z-index: 10; transition: box-shadow 0.3s, background 0.3s, border-color 0.3s;
            font-family: 'DM Sans', sans-serif;
          }
          .magnetic-btn.primary {
            background: var(--accent); color: var(--accent-fg);
            box-shadow: 0 6px 24px rgba(0,0,0,0.15);
          }
          .magnetic-btn.primary:hover { box-shadow: 0 12px 36px rgba(0,0,0,0.25); }
          .magnetic-btn.secondary {
            border: 1px solid var(--border-strong); color: var(--fg);
            background: var(--surface); backdrop-filter: blur(12px);
          }
          .magnetic-btn.secondary:hover { background: var(--surface-hover); border-color: var(--muted); }

          /* ── GRID BG ── */
          .bg-grid {
            position: absolute; inset: 0; z-index: 0;
            background-image:
              linear-gradient(to right, var(--border) 1px, transparent 1px),
              linear-gradient(to bottom, var(--border) 1px, transparent 1px);
            background-size: 70px 70px;
            mask-image: radial-gradient(ellipse 80% 80% at 50% 0%, black 20%, transparent 75%);
            -webkit-mask-image: radial-gradient(ellipse 80% 80% at 50% 0%, black 20%, transparent 75%);
          }

          /* ── GLOW CARD ── */
          .glow-card {
            position: relative; border-radius: var(--radius-card);
            overflow: visible; box-shadow: var(--card-shadow);
          }
          .glow-card::before {
            content: ""; position: absolute; inset: -1px; border-radius: calc(var(--radius-card) + 1px);
            background: radial-gradient(600px circle at var(--mouse-x, 50%) var(--mouse-y, 50%), var(--glow-strong), transparent 40%);
            z-index: 0; opacity: 0; transition: opacity 0.5s;
          }
          .glow-card:hover::before { opacity: 1; }
          .glow-card-content {
            background: var(--surface);
            backdrop-filter: blur(24px);
            -webkit-backdrop-filter: blur(24px);
            border: 1px solid var(--border);
            border-radius: var(--radius-card);
            padding: 44px;
            height: 100%; position: relative; z-index: 1;
            display: flex; flex-direction: column;
            transition: border-color 0.3s;
            transform-style: preserve-3d;
          }
          .glow-card:hover .glow-card-content { border-color: var(--border-strong); }

          /* ── ICON CHIP ── */
          .icon-chip {
            display: inline-flex; align-items: center; justify-content: center;
            width: 48px; height: 48px; border-radius: 12px;
            background: var(--bg); border: 1px solid var(--border);
            margin-bottom: 24px; flex-shrink: 0; align-self: flex-start;
          }

          /* ── MARQUEE ── */
          @keyframes scroll-left { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
          .marquee-container {
            overflow: hidden; white-space: nowrap;
            border-top: 1px solid var(--border);
            border-bottom: 1px solid var(--border);
            padding: 36px 0; background: var(--bg);
          }
          .marquee-track { display: inline-flex; width: max-content; animation: scroll-left 50s linear infinite; }
          .marquee-item {
            font-size: clamp(1.2rem, 2.5vw, 2rem); font-weight: 700;
            color: var(--muted); padding: 0 36px;
            display: inline-flex; align-items: center; gap: 36px;
            transition: color 0.3s;
          }
          .marquee-container:hover .marquee-track { animation-play-state: paused; }
          .marquee-container:hover .marquee-item { color: var(--fg); }

          /* ── STATS STRIP ── */
          .stats-strip {
            display: grid; grid-template-columns: repeat(4, 1fr);
            border-top: 1px solid var(--border);
            border-bottom: 1px solid var(--border);
            overflow: hidden;
          }
          .stat-cell {
            padding: 60px 40px; text-align: center;
            border-right: 1px solid var(--border);
            position: relative;
          }
          .stat-cell:last-child { border-right: none; }
          .stat-cell::before {
            content: "";
            position: absolute; inset: 0;
            background: var(--glow);
            opacity: 0;
            transition: opacity 0.4s;
          }
          .stat-cell:hover::before { opacity: 1; }

          /* ── PROCESS STEPS ── */
          .process-row {
            display: grid; grid-template-columns: 1fr 1fr 1fr;
            gap: 0; border: 1px solid var(--border); border-radius: 20px; overflow: hidden;
          }
          .process-cell {
            padding: 48px 40px;
            border-right: 1px solid var(--border);
            position: relative; overflow: hidden;
            transition: background 0.3s;
          }
          .process-cell:last-child { border-right: none; }
          .process-cell:hover { background: var(--surface); }

          /* ── HERO TAG ── */
          .hero-tag {
            display: inline-flex; align-items: center; gap: 10px;
            padding: 8px 16px; border-radius: 100px;
            border: 1px solid var(--border-strong);
            background: var(--surface);
            backdrop-filter: blur(10px);
            font-size: 0.82rem;
          }

          /* ── EQUATION DISPLAY ── */
          .eq-display {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.9rem;
            color: var(--muted);
            padding: 10px 16px;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            display: inline-block;
            transition: color 0.3s, border-color 0.3s;
          }
          .eq-display:hover { color: var(--fg); border-color: var(--muted); }

          /* ── BENTO GRID ── */
          .bento-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            grid-template-rows: auto auto;
            gap: 16px;
          }
          .bento-tall { grid-row: span 2; }

          /* ── REVEAL LINE ── */
          .draw-line { transform-origin: left; }

          /* mobile */
          @media (max-width: 768px) {
            .stats-strip { grid-template-columns: 1fr 1fr; }
            .stat-cell:nth-child(2) { border-right: none; }
            .stat-cell:nth-child(3) { border-top: 1px solid var(--border); border-right: 1px solid var(--border); }
            .stat-cell:nth-child(4) { border-top: 1px solid var(--border); border-right: none; }
            .process-row { grid-template-columns: 1fr; }
            .process-cell { border-right: none; border-bottom: 1px solid var(--border); }
            .process-cell:last-child { border-bottom: none; }
            .bento-grid { grid-template-columns: 1fr; }
            .bento-tall { grid-row: span 1; }
          }
        `}</style>

        {/* Noise overlay */}
        <div className="noise-overlay" />

        {/* ── NAVIGATION ── */}
        <nav className="nav-glass" style={{
          position: "fixed", top: 0, width: "100%", zIndex: 500,
          padding: "0 40px", height: "70px",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          borderBottom: "1px solid var(--border)", transition: "all 0.3s",
        }}>
          <Link href="/" style={{ textDecoration: "none", color: "inherit", display: "flex", alignItems: "center", gap: "12px" }}>
            <img src="/logo.svg" alt="Ozon" style={{ width: "26px", height: "26px", filter: isDark ? "invert(1)" : "none" }} />
            <span className="syne" style={{ fontWeight: 800, fontSize: "1.25rem", letterSpacing: "-0.02em" }}>Ozon</span>
          </Link>

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {["Docs", "Examples", "Changelog"].map(item => (
              <Link key={item} href={`/${item.toLowerCase()}`} className="mono" style={{
                fontSize: "0.78rem", color: "var(--muted)", textDecoration: "none",
                padding: "8px 16px", borderRadius: "8px",
                transition: "color 0.2s, background 0.2s",
              }}
                onMouseEnter={e => { (e.target as any).style.color = "var(--fg)"; (e.target as any).style.background = "var(--border)"; }}
                onMouseLeave={e => { (e.target as any).style.color = "var(--muted)"; (e.target as any).style.background = "transparent"; }}
              >{item}</Link>
            ))}
            {mounted && (
              <button onClick={() => setTheme(isDark ? "light" : "dark")} className="mono" style={{
                background: "none", border: "1px solid var(--border)", color: "var(--muted)",
                fontSize: "0.75rem", padding: "7px 14px", borderRadius: "8px",
                transition: "all 0.2s",
              }}
                onMouseEnter={e => { (e.target as any).style.color = "var(--fg)"; (e.target as any).style.borderColor = "var(--muted)"; }}
                onMouseLeave={e => { (e.target as any).style.color = "var(--muted)"; (e.target as any).style.borderColor = "var(--border)"; }}
              >
                {isDark ? "LIGHT" : "DARK"}
              </button>
            )}
            <MagneticButton href="/calculator" primary style={{ padding: "10px 22px", fontSize: "0.88rem", marginLeft: "8px" }}>
              Open App <ArrowRight size={15} />
            </MagneticButton>
          </div>
        </nav>

        {/* ── HERO ── */}
        <section className="hero-section" style={{
          position: "relative", minHeight: "100vh",
          display: "flex", flexDirection: "column",
          paddingTop: "160px", overflow: "hidden",
        }}>
          <div className="bg-grid" />

          {/* Floating formulas */}
          <FloatingFormula text="∂f/∂x" style={{ top: "22%", right: "8%" }} />
          <FloatingFormula text="∫₀^∞ e^-x dx" style={{ top: "35%", right: "18%" }} />
          <FloatingFormula text="∇·F = 0" style={{ bottom: "30%", right: "6%" }} />
          <FloatingFormula text="eiπ + 1 = 0" style={{ top: "20%", left: "5%" }} />
          <FloatingFormula text="lim x→0" style={{ bottom: "35%", left: "8%" }} />

          {/* Ambient glow */}
          <div style={{
            position: "absolute", top: "10%", left: "30%", width: "600px", height: "400px",
            background: "radial-gradient(ellipse, rgba(255,255,255,0.035) 0%, transparent 70%)",
            pointerEvents: "none", zIndex: 0,
          }} />

          <div style={{ padding: "0 40px", maxWidth: "1400px", margin: "0 auto", width: "100%", position: "relative", zIndex: 10 }}>

            {/* Tag */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              className="hero-tag mono fade-in-up"
              style={{ marginBottom: "48px", color: "var(--muted-light)", fontSize: "0.8rem" }}
            >
              <span style={{ width: "6px", height: "6px", background: "#4ade80", borderRadius: "50%", boxShadow: "0 0 8px #4ade80" }} />
              Graphing Engine v2.0 — Now with AI Canvas
            </motion.div>

            {/* Headline */}
            <div style={{ perspective: "1200px", marginBottom: "60px" }}>
              <div style={{ overflow: "hidden", paddingBottom: "8px" }}>
                <h1 className="syne display-huge hero-line text-gradient">Compute</h1>
              </div>
              <div style={{ overflow: "hidden", paddingBottom: "8px" }}>
                <h1 className="syne display-huge hero-line" style={{ color: "var(--muted)" }}>Without</h1>
              </div>
              <div style={{ overflow: "hidden", paddingBottom: "8px" }}>
                <h1 className="syne display-huge hero-line text-gradient">Boundaries.</h1>
              </div>
            </div>

            {/* Sub-row */}
            <div className="fade-in-up" style={{ display: "flex", gap: "20px", alignItems: "center", flexWrap: "wrap" }}>
              <MagneticButton href="/calculator" primary>
                Launch Canvas <ArrowRight size={17} />
              </MagneticButton>
              <MagneticButton href="/docs" secondary>
                Read Docs
              </MagneticButton>

              {/* Divider */}
              <div style={{ width: "1px", height: "40px", background: "var(--border)", margin: "0 10px" }} />

              {/* Equation pills */}
              <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                {["d/dx[sin(x)]", "∫₀¹ x² dx", "lim→∞"].map(eq => (
                  <span key={eq} className="eq-display">{eq}</span>
                ))}
              </div>
            </div>

            {/* Body text */}
            <p className="fade-in-up" style={{
              marginTop: "40px", maxWidth: "500px", color: "var(--muted)",
              fontSize: "1.05rem", lineHeight: 1.75, fontWeight: 300,
            }}>
              A world-class plotting engine merged with native calculus, complex arithmetic, and an AI agent that understands plain English.
            </p>
          </div>

          {/* Hero showcase */}
          <div style={{ width: "100%", padding: "80px 40px 60px", flex: 1, display: "flex", alignItems: "flex-end", position: "relative", zIndex: 5 }}>
            <div
              className="hero-video-wrapper"
              style={{
                width: "100%", height: "68vh",
                background: "var(--surface-solid)", border: "1px solid var(--border)",
                display: "flex", alignItems: "center", justifyContent: "center",
                overflow: "hidden", position: "relative",
                transformOrigin: "bottom center", borderRadius: "16px",
                boxShadow: "0 40px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)",
              }}
            >
              <div className="mono" style={{ color: "var(--muted)", letterSpacing: "0.2em", fontSize: "0.85rem", zIndex: 2 }}>
                [ BRAND SHOWCASE UI / VIDEO ]
              </div>
              <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to top, var(--bg) 0%, transparent 55%)", pointerEvents: "none", zIndex: 1 }} />
            </div>
          </div>
        </section>

        {/* ── STATS STRIP ── */}
        <div className="stats-strip">
          {[
            { value: "10M+", label: "EQUATIONS PLOTTED" },
            { value: "<4ms", label: "RENDER LATENCY" },
            { value: "∞", label: "ZOOM RESOLUTION" },
            { value: "99.9%", label: "UPTIME SLA" },
          ].map((s, i) => (
            <div key={s.label} className="stat-cell">
              <StatItem value={s.value} label={s.label} delay={i * 0.1} />
            </div>
          ))}
        </div>

        {/* ── HORIZONTAL FEATURES ── */}
        <section className="features-wrapper" style={{
          height: "100vh", display: "flex", flexDirection: "column",
          justifyContent: "center", overflow: "hidden", position: "relative",
        }}>
          <div style={{ display: "flex", alignItems: "flex-end", gap: "32px", padding: "0 40px", marginBottom: "72px" }}>
            <h2 className="syne display-large text-gradient">Engineered<br />For Speed.</h2>
            <div className="draw-line" style={{ width: "8vw", height: "1px", background: "var(--border-strong)", flexShrink: 0 }} />
            <span className="mono text-dim" style={{ fontSize: "0.78rem", paddingBottom: "12px" }}>[ 01 / FEATURES ]</span>
          </div>

          <div className="horizontal-scroll-container" style={{
            display: "flex", gap: "28px", padding: "0 40px",
            width: "max-content", willChange: "transform",
            alignItems: "stretch",
          }}>

            {/* Card 1 – Calculus */}
            <HCard delay={0} style={{ width: "clamp(600px, 80vw, 900px)", height: "clamp(420px, 55vh, 600px)" }}>
              <GlowCard style={{ height: "100%", width: "100%" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "32px", height: "100%" }}>
                  <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                    <div>
                      <div className="icon-chip"><Sigma size={28} /></div>
                      <div className="mono text-dim" style={{ fontSize: "0.72rem", marginBottom: "16px" }}>01 — CALCULUS ENGINE</div>
                      <h3 className="syne" style={{ fontSize: "clamp(1.6rem, 2.5vw, 2.2rem)", marginBottom: "18px", fontWeight: 800 }}>Native Calculus</h3>
                      <p style={{ color: "var(--muted)", fontSize: "1rem", lineHeight: 1.75, fontWeight: 300 }}>
                        Evaluate derivatives and definite integrals instantly. Dotted and solid lines update dynamically as you type. Parent and result curves coexist on the same canvas.
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "24px" }}>
                      {["d/dx", "∫ dx", "∂/∂x", "d²/dx²"].map(t => (
                        <span key={t} className="eq-display" style={{ fontSize: "0.8rem" }}>{t}</span>
                      ))}
                    </div>
                  </div>
                  <div style={{
                    background: "var(--bg)", borderRadius: "14px",
                    border: "1px solid var(--border)", display: "flex",
                    alignItems: "center", justifyContent: "center",
                    boxShadow: "inset 0 0 50px rgba(0,0,0,0.3)",
                    position: "relative", overflow: "hidden",
                  }}>
                    <span className="mono" style={{ color: "var(--muted)", fontSize: "0.75rem" }}>[ SCREENSHOT ]</span>
                  </div>
                </div>
              </GlowCard>
            </HCard>

            {/* Card 2 – AI */}
            <HCard delay={0.1} style={{ width: "clamp(600px, 80vw, 900px)", height: "clamp(420px, 55vh, 600px)" }}>
              <GlowCard style={{ height: "100%", width: "100%" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "32px", height: "100%" }}>
                  <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                    <div>
                      <div className="icon-chip"><Brain size={28} /></div>
                      <div className="mono text-dim" style={{ fontSize: "0.72rem", marginBottom: "16px" }}>02 — AI AGENT</div>
                      <h3 className="syne" style={{ fontSize: "clamp(1.6rem, 2.5vw, 2.2rem)", marginBottom: "18px", fontWeight: 800 }}>AI & OCR Agent</h3>
                      <p style={{ color: "var(--muted)", fontSize: "1rem", lineHeight: 1.75, fontWeight: 300 }}>
                        Type "plot the tangent to sin(x) at x=π". The agent interprets English and injects precise LaTeX into the engine. Upload handwritten equations via OCR.
                      </p>
                    </div>
                    {/* Fake chat UI */}
                    <div style={{ background: "var(--bg)", borderRadius: "12px", border: "1px solid var(--border)", padding: "14px 16px", marginTop: "24px" }}>
                      <div className="mono" style={{ fontSize: "0.75rem", color: "var(--muted-light)", marginBottom: "8px" }}>USER</div>
                      <div style={{ fontSize: "0.88rem", color: "var(--fg)", lineHeight: 1.5 }}>plot tangent of sin(x) at x=π/4</div>
                      <div className="mono" style={{ fontSize: "0.75rem", color: "var(--muted-light)", marginTop: "12px", marginBottom: "6px" }}>OZON AI</div>
                      <div className="mono" style={{ fontSize: "0.78rem", color: "var(--muted)", lineHeight: 1.5 }}>→ y = (√2/2)(x − π/4) + √2/2</div>
                    </div>
                  </div>
                  <div style={{
                    background: "var(--bg)", borderRadius: "14px",
                    border: "1px solid var(--border)", display: "flex",
                    alignItems: "center", justifyContent: "center",
                    boxShadow: "inset 0 0 50px rgba(0,0,0,0.3)",
                  }}>
                    <span className="mono" style={{ color: "var(--muted)", fontSize: "0.75rem" }}>[ AI SCREENSHOT ]</span>
                  </div>
                </div>
              </GlowCard>
            </HCard>

            {/* Card 3 – Split */}
            <HCard delay={0.2} style={{ width: "clamp(600px, 80vw, 900px)", height: "clamp(420px, 55vh, 600px)", display: "flex", gap: "20px" }}>
              <GlowCard style={{ flex: 1, height: "100%" }}>
                <div className="icon-chip"><Layers size={24} /></div>
                <div className="mono text-dim" style={{ fontSize: "0.72rem", marginBottom: "16px" }}>03 — COMPLEX MATH</div>
                <h3 className="syne" style={{ fontSize: "1.6rem", marginBottom: "16px", fontWeight: 800 }}>Complex Arithmetic</h3>
                <p style={{ color: "var(--muted)", fontSize: "0.95rem", lineHeight: 1.75, fontWeight: 300, flex: 1 }}>
                  Full support for the imaginary unit <code style={{ fontFamily: "monospace", fontSize: "0.9em" }}>i</code>. Graph real parts, imaginary parts, and polar curves via Euler's identity.
                </p>
                <div style={{ display: "flex", gap: "8px", marginTop: "24px", flexWrap: "wrap" }}>
                  {["Re(z)", "Im(z)", "e^iθ", "|z|"].map(t => (
                    <span key={t} className="eq-display" style={{ fontSize: "0.77rem" }}>{t}</span>
                  ))}
                </div>
              </GlowCard>
              <GlowCard style={{ flex: 1, height: "100%" }}>
                <div className="icon-chip"><BarChart2 size={24} /></div>
                <div className="mono text-dim" style={{ fontSize: "0.72rem", marginBottom: "16px" }}>04 — ANALYSIS</div>
                <h3 className="syne" style={{ fontSize: "1.6rem", marginBottom: "16px", fontWeight: 800 }}>Symbolic Analysis</h3>
                <p style={{ color: "var(--muted)", fontSize: "0.95rem", lineHeight: 1.75, fontWeight: 300, flex: 1 }}>
                  One click reveals domain, range, asymptotes, and extrema. Inject tangent and normal lines at any point effortlessly.
                </p>
                <div style={{ display: "flex", gap: "8px", marginTop: "24px", flexWrap: "wrap" }}>
                  {["Domain", "Range", "Extrema", "Asymptotes"].map(t => (
                    <span key={t} className="eq-display" style={{ fontSize: "0.77rem" }}>{t}</span>
                  ))}
                </div>
              </GlowCard>
            </HCard>

            {/* Spacer */}
            <div style={{ width: "40px", flexShrink: 0 }} />
          </div>
        </section>

        {/* ── MARQUEE ── */}
        <div className="marquee-container">
          <div className="marquee-track syne">
            {Array(8).fill(null).map((_, i) => (
              <div key={i} className="marquee-item">
                STOP CALCULATING&nbsp;&nbsp;•&nbsp;&nbsp;START EXPLORING&nbsp;&nbsp;
                <Zap size={32} strokeWidth={1.5} />
              </div>
            ))}
          </div>
        </div>

        {/* ── HOW IT WORKS ── */}
        <section style={{ padding: "160px 40px", maxWidth: "1400px", margin: "0 auto", width: "100%" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "32px", marginBottom: "80px" }}>
            <div>
              <div className="mono text-dim" style={{ fontSize: "0.78rem", marginBottom: "20px" }}>[ 02 / WORKFLOW ]</div>
              <h2 className="syne display-large text-gradient">Three steps.<br />Zero friction.</h2>
            </div>
            <div className="draw-line" style={{ flex: 1, height: "1px", background: "var(--border-strong)", marginLeft: "40px" }} />
          </div>

          <div className="process-row">
            {[
              {
                num: "01", title: "Type or Speak", icon: <MousePointer2 size={22} />,
                desc: "Enter any expression in plain text, LaTeX, or English. No syntax memorization required."
              },
              {
                num: "02", title: "Engine Computes", icon: <Sigma size={22} />,
                desc: "The graphing engine evaluates derivatives, integrals, and limits in under 4ms. Results stream in real-time."
              },
              {
                num: "03", title: "Explore & Export", icon: <ArrowUpRight size={22} />,
                desc: "Pan, zoom to any precision. Export to SVG, PNG, or share a live link with collaborators."
              },
            ].map((step, i) => (
              <motion.div
                key={step.num}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.8, delay: i * 0.12, ease: [0.16, 1, 0.3, 1] }}
                className="process-cell"
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "40px" }}>
                  <span className="mono text-dim" style={{ fontSize: "0.8rem" }}>{step.num}</span>
                  <span style={{ color: "var(--muted)" }}>{step.icon}</span>
                </div>
                <h3 className="syne" style={{ fontSize: "1.6rem", fontWeight: 800, marginBottom: "16px" }}>{step.title}</h3>
                <p style={{ color: "var(--muted)", lineHeight: 1.75, fontWeight: 300 }}>{step.desc}</p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── BENTO FEATURE GRID ── */}
        <section style={{ padding: "0 40px 160px", maxWidth: "1400px", margin: "0 auto", width: "100%" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "32px", marginBottom: "80px" }}>
            <div>
              <div className="mono text-dim" style={{ fontSize: "0.78rem", marginBottom: "20px" }}>[ 03 / CAPABILITIES ]</div>
              <h2 className="syne display-large text-gradient">Everything.<br />Nothing extra.</h2>
            </div>
          </div>

          <div className="bento-grid">
            {/* Tall left */}
            <GlowCard className="bento-tall" index={0}>
              <div className="icon-chip"><Infinity size={26} /></div>
              <div className="mono text-dim" style={{ fontSize: "0.72rem", marginBottom: "16px" }}>INFINITE PRECISION</div>
              <h3 className="syne" style={{ fontSize: "1.8rem", fontWeight: 800, marginBottom: "16px" }}>Zoom to Any Scale</h3>
              <p style={{ color: "var(--muted)", lineHeight: 1.75, fontWeight: 300, flex: 1 }}>
                Our rendering engine uses adaptive sampling — the further you zoom, the more detail it renders. No pixelation, no approximation.
              </p>
              <div style={{
                marginTop: "40px", background: "var(--bg)", borderRadius: "14px",
                border: "1px solid var(--border)", height: "200px",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <span className="mono" style={{ color: "var(--muted)", fontSize: "0.75rem" }}>[ ZOOM DEMO ]</span>
              </div>
            </GlowCard>

            {/* Top middle */}
            <GlowCard index={1}>
              <div className="icon-chip"><GitBranch size={22} /></div>
              <div className="mono text-dim" style={{ fontSize: "0.72rem", marginBottom: "12px" }}>MULTI-FUNCTION</div>
              <h3 className="syne" style={{ fontSize: "1.4rem", fontWeight: 800, marginBottom: "14px" }}>Layered Graphs</h3>
              <p style={{ color: "var(--muted)", lineHeight: 1.7, fontWeight: 300, fontSize: "0.95rem" }}>
                Plot up to 20 functions simultaneously. Each layer has independent color, opacity, and line-weight controls.
              </p>
            </GlowCard>

            {/* Top right */}
            <GlowCard index={2}>
              <div className="icon-chip"><Sparkles size={22} /></div>
              <div className="mono text-dim" style={{ fontSize: "0.72rem", marginBottom: "12px" }}>LIVE PREVIEW</div>
              <h3 className="syne" style={{ fontSize: "1.4rem", fontWeight: 800, marginBottom: "14px" }}>Real-Time Render</h3>
              <p style={{ color: "var(--muted)", lineHeight: 1.7, fontWeight: 300, fontSize: "0.95rem" }}>
                Every keypress triggers a new render in under 4ms. Watch your equation take shape as you type.
              </p>
            </GlowCard>

            {/* Bottom middle */}
            <GlowCard index={3}>
              <div className="icon-chip"><FunctionSquare size={22} /></div>
              <div className="mono text-dim" style={{ fontSize: "0.72rem", marginBottom: "12px" }}>DARK / LIGHT</div>
              <h3 className="syne" style={{ fontSize: "1.4rem", fontWeight: 800, marginBottom: "14px" }}>Theme Engine</h3>
              <p style={{ color: "var(--muted)", lineHeight: 1.7, fontWeight: 300, fontSize: "0.95rem" }}>
                Gorgeous in every context. Export graphs with transparent backgrounds for slides or papers.
              </p>
            </GlowCard>

            {/* Bottom right */}
            <GlowCard index={4}>
              <div className="icon-chip"><BarChart2 size={22} /></div>
              <div className="mono text-dim" style={{ fontSize: "0.72rem", marginBottom: "12px" }}>POLAR & PARAMETRIC</div>
              <h3 className="syne" style={{ fontSize: "1.4rem", fontWeight: 800, marginBottom: "14px" }}>All Coordinate Systems</h3>
              <p style={{ color: "var(--muted)", lineHeight: 1.7, fontWeight: 300, fontSize: "0.95rem" }}>
                Cartesian, polar, and parametric — switch fluidly between any mode with a single toggle.
              </p>
            </GlowCard>
          </div>
        </section>

        {/* ── FOOTER CTA ── */}
        <section style={{
          padding: "180px 40px", display: "flex", flexDirection: "column",
          alignItems: "center", textAlign: "center", position: "relative", overflow: "hidden",
          borderTop: "1px solid var(--border)",
        }}>
          {/* Background glow */}
          <div style={{
            position: "absolute", top: "50%", left: "50%",
            transform: "translate(-50%, -50%)",
            width: "900px", height: "600px",
            background: "var(--fg)", opacity: 0.025, filter: "blur(140px)",
            borderRadius: "50%", pointerEvents: "none",
          }} />

          <motion.div
            initial={{ opacity: 0, scale: 0.85 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
            style={{ position: "relative", zIndex: 1 }}
          >
            <div className="mono text-dim" style={{ fontSize: "0.78rem", marginBottom: "40px" }}>[ LAUNCH ]</div>
            <h2 className="syne display-large text-gradient" style={{ marginBottom: "60px" }}>
              Ready to chart<br />the unknown?
            </h2>
            <MagneticButton href="/calculator" primary className="syne" style={{ padding: "22px 48px", fontSize: "1.1rem" }}>
              Launch Ozon Canvas <ChevronRight size={22} />
            </MagneticButton>
          </motion.div>
        </section>

        {/* ── FOOTER ── */}
        <footer style={{
          padding: "48px 40px",
          borderTop: "1px solid var(--border)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          fontSize: "0.88rem", color: "var(--muted)", background: "var(--bg)",
          flexWrap: "wrap", gap: "20px",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
            <img src="/logo.svg" alt="Ozon" style={{ width: "22px", filter: isDark ? "invert(1)" : "none", opacity: 0.6 }} />
            <span className="mono" style={{ fontSize: "0.78rem" }}>© {new Date().getFullYear()} Ozon Engine. All rights reserved.</span>
          </div>
          <div style={{ display: "flex", gap: "32px" }}>
            {["DOCUMENTATION", "GITHUB", "TWITTER", "CHANGELOG"].map(link => (
              <a key={link} href="#" className="mono" style={{
                color: "inherit", textDecoration: "none", fontSize: "0.75rem",
                transition: "color 0.2s",
              }}
                onMouseEnter={e => (e.target as any).style.color = "var(--fg)"}
                onMouseLeave={e => (e.target as any).style.color = "var(--muted)"}
              >{link}</a>
            ))}
          </div>
        </footer>
      </div>
    </ReactLenis>
  );
}