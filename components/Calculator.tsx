"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun, Plus, Trash2, Calculator as CalcIcon, Terminal } from "lucide-react";
import "mathlive";

// 1. Type Definitions
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

  // 2. Configure MathLive Fonts (Crucial for avoiding 404s)
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

  // 3. Load Desmos Script
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

  // 4. Initialize Desmos
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
  //      THE LOGIC: CLEANER & PARSER
  // ==========================================
  const processExpression = (id: string, rawLatex: string) => {
      const Calc = calculatorInstance.current;
      if (!Calc) return;

      // 1. Cleanup old helper expressions for this ID
      Calc.removeExpression({ id });
      Calc.removeExpression({ id: `curve-${id}` });
      Calc.removeExpression({ id: `shade-${id}` });

      if (!rawLatex.trim()) return;

      // 2. Aggressive Cleaning
      // MathLive generates verbose LaTeX (\differentialD, \mathrm, \!). Desmos needs simple LaTeX.
      let clean = rawLatex
          .replace(/\\differentialD/g, "d")     // Fix specific MathLive derivative symbol
          .replace(/\\mathrm\{d\}/g, "d")       // Fix Roman d
          .replace(/\\mathrm\{([a-zA-Z])\}/g, "$1") // Fix other Roman chars
          .replace(/\\!/g, "")                  // Remove negative space
          .replace(/\\,/g, " ")                 // Remove thin space
          .replace(/\\:/g, " ")                 // Remove medium space
          .replace(/\\;/g, " ")                 // Remove thick space
          .replace(/\\limits/g, "")             // Remove limits layout
          .replace(/\\operatorname\{([a-zA-Z]+)\}/g, "\\$1") // Fix operatornames (sin, cos)
          .trim();

      setDebugInfo(clean); // Show in UI

      // 3. Parser Logic
      const isIntegral = clean.startsWith("\\int");

      if (isIntegral) {
          // --- DEFINITE INTEGRAL DETECTION ---
          // Regex Explanation:
          // \\int_               -> Starts with int_
          // (\{([^{}]+)\}|(.))   -> Group 1: Min is either {complex} or (single char)
          // \^                   -> Followed by ^
          // (\{([^{}]+)\}|(.))   -> Group 4: Max is either {complex} or (single char)
          // \s*(.+?)\s*          -> Group 7: Body (lazy match)
          // d([a-zA-Z])          -> Ends with d(var)
          const definiteRegex = /^\\int_(\{([^{}]+)\}|(.))\^(\{([^{}]+)\}|(.))\s*(.+?)\s*d([a-zA-Z])$/;
          const defMatch = clean.match(definiteRegex);

          if (defMatch) {
              // Extract Groups
              const min = defMatch[2] || defMatch[3]; // The content inside {} OR the single char
              const max = defMatch[5] || defMatch[6]; 
              const body = defMatch[7];
              const variable = defMatch[8];

              // A. Set the Main Expression (Calculates the Value)
              Calc.setExpression({ id: id, latex: clean, color: "#000" });

              // B. Set the Curve (Plots y = f(x))
              // We replace the integration variable with 'x' so Desmos can graph it on the x-axis
              const plotBody = variable === 'x' ? body : body.split(variable).join("x");
              Calc.setExpression({
                   id: `curve-${id}`,
                   latex: `y = ${plotBody}`,
                   lineStyle: window.Desmos.Styles.DASHED,
                   color: "#2d70b3",
                   fillOpacity: 0
              });

              // C. Set the Shading
              // Logic: 0 <= y <= f(x) restricted to min <= x <= max
              const shadeLatex = `0 \\le y \\le ${plotBody} \\left\\{ ${min} \\le x \\le ${max} \\right\\}`;
              Calc.setExpression({
                   id: `shade-${id}`,
                   latex: shadeLatex,
                   color: "#2d70b3",
                   fillOpacity: 0.3,
                   lines: false
              });

              return;
          }

          // --- INDEFINITE INTEGRAL DETECTION ---
          // If it starts with \int but didn't match the Definite regex (likely no bounds)
          // Regex: \int (body) d(var)
          const indefRegex = /^\\int\s*(.+?)\s*d([a-zA-Z])$/;
          const indefMatch = clean.match(indefRegex);

          if (indefMatch && !clean.includes("_")) {
              const body = indefMatch[1];
              const variable = indefMatch[2];
              
              // We convert \int f(x) dx  -->  y = \int_0^x f(t) dt
              // This forces Desmos to plot the antiderivative
              const bodyWithT = body.split(variable).join("t");
              const finalExpr = `y = \\int_{0}^{${variable}} ${bodyWithT} dt`;
              
              Calc.setExpression({ 
                  id, 
                  latex: finalExpr, 
                  color: "#2d70b3" 
              });
              return;
          }
      }

      // 4. Default Fallback (Standard Math, Derivatives d/dx)
      // Since we cleaned \differentialD to d, d/dx works natively
      Calc.setExpression({ 
          id: id, 
          latex: clean, 
          color: "#2d70b3" 
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
         calculatorInstance.current.removeExpression({ id });
         calculatorInstance.current.removeExpression({ id: `curve-${id}` });
         calculatorInstance.current.removeExpression({ id: `shade-${id}` });
     }
  };

  if (!libLoaded) return <div className="h-screen w-full flex items-center justify-center font-mono">Loading Desmos...</div>;

  return (
    <div className="flex flex-col h-screen w-full bg-background overflow-hidden">
      {/* Header */}
      <header className="h-14 border-b flex items-center justify-between px-4 bg-card z-20 shadow-sm shrink-0">
        <h1 className="font-bold text-xl flex items-center gap-2">
            <CalcIcon className="text-primary" /> 
            <span className="font-serif italic">ƒ</span>(x) Engine
        </h1>
        <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} className="p-2 rounded-full hover:bg-accent transition-colors">
            {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
        </button>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
         {/* Sidebar */}
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
                {/* Debug Panel */}
                <div className="font-mono text-[10px] bg-black/5 dark:bg-white/5 p-3 rounded">
                    <div className="flex items-center gap-2 font-bold mb-1 opacity-70">
                        <Terminal size={12} /> Parser Output
                    </div>
                    <div className="truncate opacity-50">{debugInfo}</div>
                </div>
            </div>
         </div>

         {/* Graph Area */}
         <div className="flex-1 relative bg-white dark:bg-black">
             <div ref={calculatorRef} className="absolute inset-0 w-full h-full" />
         </div>
      </div>
    </div>
  );
}