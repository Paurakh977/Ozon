"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun, Plus, Trash2, Calculator as CalcIcon, Terminal } from "lucide-react";
import "mathlive";

declare global {
  interface Window {
    Desmos: any;
    MathfieldElement: any;
  }
  namespace JSX {
    interface IntrinsicElements {
      'math-field': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
          'virtual-keyboard-mode'?: string;
      };
    }
  }
}

interface MathExpression {
  id: string;
  latex: string;
}

export function Calculator() {
  const calculatorRef = useRef<HTMLDivElement>(null);
  const calculatorInstance = useRef<any>(null);
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [expressions, setExpressions] = useState<MathExpression[]>([
    { id: "1", latex: "" },
  ]);
  const [debugInfo, setDebugInfo] = useState<string>("Ready");
  const [libLoaded, setLibLoaded] = useState(false);

  // 1. MathLive Configuration
  useEffect(() => {
    if (typeof window !== 'undefined') {
        import("mathlive").then((ml) => {
             // @ts-ignore
             ml.MathfieldElement.fontsDirectory = "https://unpkg.com/mathlive@0.108.2/dist/fonts";
             // @ts-ignore
             ml.MathfieldElement.soundsDirectory = null;
        });
    }
  }, []);

  // 2. Load Desmos
  useEffect(() => {
    if (window.Desmos) {
        setLibLoaded(true);
        return;
    }
    const script = document.createElement("script");
    script.src = "https://www.desmos.com/api/v1.10/calculator.js?apiKey=dcb31709b452b1cf9dc26972add0fda6";
    script.async = true;
    script.onload = () => setLibLoaded(true);
    document.body.appendChild(script);
  }, []);

  // 3. Initialize Desmos
  useEffect(() => {
    if (!libLoaded || !calculatorRef.current || calculatorInstance.current) return;
    
    calculatorInstance.current = window.Desmos.GraphingCalculator(calculatorRef.current, {
        expressions: false, 
        keypad: false, 
        settingsMenu: true, 
        zoomButtons: true,
        invertedColors: resolvedTheme === 'dark', 
        border: false,
    });
    
    expressions.forEach(e => processExpression(e.id, e.latex));
    
    return () => {
        if (calculatorInstance.current) {
            calculatorInstance.current.destroy();
            calculatorInstance.current = null;
        }
    };
  }, [libLoaded]);

  // Theme Sync
  useEffect(() => {
     calculatorInstance.current?.updateSettings({ invertedColors: resolvedTheme === 'dark' });
  }, [resolvedTheme]);


  // ==========================================
  //      THE LOGIC: SMART TRANSFORMER
  // ==========================================
  const processExpression = (id: string, rawLatex: string) => {
      const Calc = calculatorInstance.current;
      if (!Calc) return;

      // 1. Generate Safe Variable ID (Desmos hates dashes or starting numbers)
      const safeId = `E${id.replace(/-/g, "")}`;

      // 2. Clear All Associated Expressions
      // We delete everything related to this ID before re-adding
      const cleanupList = [
          id, 
          `curve-${safeId}`, `shade-${safeId}`, 
          `val-${safeId}`, `func-${safeId}`, `label-${safeId}`,
          `funcD-${safeId}` // Function definition for derivatives
      ];
      cleanupList.forEach(eid => Calc.removeExpression({ id: eid }));

      if (!rawLatex.trim()) return;

      // 3. Clean LaTeX
      let clean = rawLatex
          // Standard Cleanup
          .replace(/\\!/g, "").replace(/\\,/g, " ").replace(/\\:/g, " ").replace(/\\;/g, " ")
          .replace(/\\limits/g, "")
          
          // Derivatives Notation Cleanup
          .replace(/\\differentialD/g, "d")     
          .replace(/\\mathrm\{d\}/g, "d")       
          .replace(/\\mathrm\{([a-zA-Z])\}/g, "$1") 
          .replace(/\\dfrac/g, "\\frac")
          .replace(/\\operatorname\{([a-zA-Z]+)\}/g, "\\$1")
          
          // Fix Evaluation Bar: \bigm|_{x=2} -> |_{x=2}
          .replace(/\\bigm\|/g, "|")
          .replace(/\\left\|/g, "|").replace(/\\right\./g, "")
          
          // General
          .replace(/\\lvert/g, "|").replace(/\\rvert/g, "|")
          .trim();

      setDebugInfo(clean);

      // --- LOGIC BRANCHES ---

      // BRANCH A: Derivative at a Point (e.g. d/dx x^2 |_{x=2})
      // Regex detects: \frac{d}{dx} (body) |_{x=(val)}
      // It captures the body (group 2) and the value (group 4)
      const derivPointRegex = /\\frac\{d\}\{d([a-zA-Z])\}\s*(.+?)\s*\|_\{([a-zA-Z])=([^{}]+)\}/;
      const derivMatch = clean.match(derivPointRegex);

      if (derivMatch) {
          const variable = derivMatch[1]; // x
          const body = derivMatch[2];     // x^2
          const targetVal = derivMatch[4]; // 2

          // Step 1: Define the function hiddenly: f(x) = x^2
          Calc.setExpression({
              id: `funcD-${safeId}`,
              latex: `f_{${safeId}}(${variable}) = ${body}`,
              secret: true
          });

          // Step 2: Calculate the derivative value: V = f'(2)
          Calc.setExpression({
              id: `val-${safeId}`,
              latex: `V_{${safeId}} = \\frac{d}{d${variable}} f_{${safeId}}(${targetVal})`,
              secret: true
          });

          // Step 3: Display Label at (0,0) or (targetVal, 0)
          Calc.setExpression({
              id: `label-${safeId}`,
              latex: `(0,0)`, // Keeping it at origin for visibility
              label: `f'(${targetVal}) = \${V_{${safeId}}}`,
              showLabel: true,
              hidden: true, // Hide the dot
              color: "#000000"
          });
          return;
      }

      // BRANCH B: Definite Integral (e.g. \int_0^1 x^2 dx)
      const defIntegralRegex = /^\\int_(\{([^{}]+)\}|(.))\^(\{([^{}]+)\}|(.))\s*(.+?)\s*d([a-zA-Z])$/;
      const defMatch = clean.match(defIntegralRegex);

      if (defMatch) {
          const min = defMatch[2] || defMatch[3];
          const max = defMatch[5] || defMatch[6];
          const body = defMatch[7];
          const variable = defMatch[8];

          // 1. Calculate Value: I = \int_a^b ...
          Calc.setExpression({
              id: `val-${safeId}`,
              latex: `I_{${safeId}} = ${clean}`,
              secret: true
          });

          // 2. Plot Curve (Dashed)
          const plotBody = variable === 'x' ? body : body.split(variable).join("x");
          Calc.setExpression({
               id: `curve-${safeId}`,
               latex: `y = ${plotBody}`,
               lineStyle: window.Desmos.Styles.DASHED,
               color: "#2d70b3"
          });

          // 3. Shade Area
          const shadeLatex = `0 \\le y \\le ${plotBody} \\left\\{ ${min} \\le x \\le ${max} \\right\\}`;
          Calc.setExpression({
               id: `shade-${safeId}`,
               latex: shadeLatex,
               color: "#2d70b3",
               fillOpacity: 0.3,
               lines: false
          });

          // 4. Show Label at the midpoint of the integral
          // We use a Point ((min+max)/2, 0) to anchor the label
          Calc.setExpression({
              id: `label-${safeId}`,
              latex: `((${min} + ${max})/2, 0)`,
              label: `Area = \${I_{${safeId}}}`,
              showLabel: true,
              hidden: true, // Hide dot
              color: "#000"
          });
          return;
      }

      // BRANCH C: Indefinite Integral
      const indefRegex = /^\\int\s*(.+?)\s*d([a-zA-Z])$/;
      const indefMatch = clean.match(indefRegex);
      if (indefMatch && !clean.includes("_")) {
          const body = indefMatch[1];
          const variable = indefMatch[2];
          // Plot Accumulator: y = \int_0^x f(t) dt
          const bodyWithT = body.split(variable).join("t");
          Calc.setExpression({ 
              id, 
              latex: `y = \\int_{0}^{${variable}} ${bodyWithT} dt`, 
              color: "#2d70b3" 
          });
          return;
      }

      // BRANCH D: Standard Input
      // Fix: Remove trailing 'dx' if user typed it manually for a function (e.g. "sin x dx")
      // but NOT if it's "d/dx"
      let finalLatex = clean;
      if (!finalLatex.includes("int") && !finalLatex.includes("frac") && finalLatex.endsWith("dx")) {
           finalLatex = finalLatex.replace(/d[x-z]$/, "");
      }

      Calc.setExpression({ 
          id: id, 
          latex: finalLatex, 
          color: "#2d70b3",
          showLabel: true // If it evaluates to a constant (e.g. "1+1"), show label
      });
  };

  const handleInput = (id: string, value: string) => {
      setExpressions(prev => prev.map(e => e.id === id ? { ...e, latex: value } : e));
      processExpression(id, value);
  };

  const addExpr = () => {
     const id = Math.random().toString(36).substr(2, 9);
     setExpressions([...expressions, { id, latex: "" }]);
  };

  const removeExpr = (id: string) => {
     setExpressions(expressions.filter(e => e.id !== id));
     if (calculatorInstance.current) {
         // Re-generate safe ID to clean up correctly
         const safeId = `E${id.replace(/-/g, "")}`;
         calculatorInstance.current.removeExpression({ id });
         calculatorInstance.current.removeExpression({ id: `curve-${safeId}` });
         calculatorInstance.current.removeExpression({ id: `shade-${safeId}` });
         calculatorInstance.current.removeExpression({ id: `val-${safeId}` });
         calculatorInstance.current.removeExpression({ id: `func-${safeId}` });
         calculatorInstance.current.removeExpression({ id: `label-${safeId}` });
         calculatorInstance.current.removeExpression({ id: `funcD-${safeId}` });
         calculatorInstance.current.removeExpression({ id: `val-${safeId}` });
     }
  };

  if (!libLoaded) return <div className="h-screen w-full flex items-center justify-center font-mono">Loading Engine...</div>;

  return (
    <div className="flex flex-col h-screen w-full bg-background overflow-hidden">
      <header className="h-14 border-b flex items-center justify-between px-4 bg-card z-20 shadow-sm shrink-0">
        <h1 className="font-bold text-xl flex items-center gap-2">
            <CalcIcon className="text-primary" /> 
            <span className="font-serif italic">ƒ</span>(x) Engine
        </h1>
        <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} className="p-2 rounded-full hover:bg-accent transition-colors">
            {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
        </button>
      </header>

      <div className="flex-1 flex overflow-hidden">
         <div className="w-96 flex flex-col border-r bg-card z-10 shadow-lg">
            <div className="p-4 flex-1 overflow-y-auto space-y-4">
                {expressions.map((expr, i) => (
                    <div key={expr.id} className="group relative flex items-start gap-3 bg-muted/30 p-3 rounded-xl border border-transparent focus-within:border-primary/50 focus-within:bg-muted/50 transition-all">
                        <div className="mt-3 text-xs font-mono opacity-40 select-none w-4 text-center">{i + 1}</div>
                        <div className="flex-1 min-w-0">
                             {/* @ts-ignore */}
                             <math-field 
                                onInput={(e: any) => handleInput(expr.id, e.target.value)}
                                value={expr.latex}
                                style={{
                                    width: '100%', 
                                    backgroundColor: 'transparent', 
                                    outline: 'none',
                                    fontSize: '1.2rem',
                                    '--caret-color': theme === 'dark' ? '#fff' : '#000', 
                                    color: theme === 'dark' ? '#fff' : '#000'
                                }}
                             >
                                {expr.latex}
                             </math-field>
                        </div>
                        <button onClick={() => removeExpr(expr.id)} className="mt-2 opacity-0 group-hover:opacity-100 p-1.5 text-muted-foreground hover:text-red-500 transition-all">
                            <Trash2 size={16} />
                        </button>
                    </div>
                ))}
            </div>
            
            <div className="p-4 border-t bg-muted/10 space-y-4">
                <button onClick={addExpr} className="w-full py-2.5 border-2 border-dashed border-border rounded-xl flex items-center justify-center gap-2 text-muted-foreground hover:text-primary transition-all">
                    <Plus size={16} /> Add Expression
                </button>
                <div className="font-mono text-[10px] bg-black/5 dark:bg-white/5 p-3 rounded">
                    <div className="flex items-center gap-2 font-bold mb-1 opacity-70">
                        <Terminal size={12} /> Parser Output
                    </div>
                    <div className="truncate opacity-50">{debugInfo}</div>
                </div>
            </div>
         </div>

         <div className="flex-1 relative bg-white dark:bg-black">
             <div ref={calculatorRef} className="absolute inset-0 w-full h-full" />
         </div>
      </div>
    </div>
  );
}