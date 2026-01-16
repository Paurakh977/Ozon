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
      const cleanupList = [
          id, 
          `curve-${safeId}`, `shade-${safeId}`, 
          `val-${safeId}`, `func-${safeId}`, `label-${safeId}`,
          `funcD-${safeId}`,
          `plot-orig-${safeId}`, `plot-deriv-${safeId}`
      ];
      cleanupList.forEach(eid => Calc.removeExpression({ id: eid }));

      if (!rawLatex.trim()) return;

      // 3. Clean LaTeX
      let clean = rawLatex
          .replace(/\\!/g, "").replace(/\\,/g, " ").replace(/\\:/g, " ").replace(/\\;/g, " ")
          .replace(/\\limits/g, "")
          .replace(/\\differentialD/g, "d")     
          .replace(/\\mathrm\{d\}/g, "d")       
          .replace(/\\mathrm\{([a-zA-Z])\}/g, "$1") 
          .replace(/\\dfrac/g, "\\frac")
          .replace(/\\operatorname\{([a-zA-Z]+)\}/g, "\\$1")
          .replace(/\\bigm\|/g, "|")
          .replace(/\\left\|/g, "|")
          .replace(/\\right\|/g, "|")
          .replace(/\\right\./g, "")
          .replace(/\\lvert/g, "|").replace(/\\rvert/g, "|")
          // Ensure standard functions have backslashes (e.g. "sin" -> "\sin") if user typed manually
          .replace(/(^|[^\\a-zA-Z])(sin|cos|tan|sec|csc|cot|ln|log|exp)(?![a-zA-Z])/g, "$1\\$2")
          .trim();

      setDebugInfo(clean);

      // --- Helper: Parse Substript/Superscript Bounds ---
      // Returns { min, max, end } where min/max are the contents of _{...} and ^{...}
      const parseBounds = (startIdx: number, str: string) => {
          let i = startIdx;
          let min = "", max = "";
          
          const parseGroup = () => {
             if (i >= str.length) return "";
             if (str[i] === "{") {
                let depth = 1; 
                i++;
                let start = i;
                while(i < str.length && depth > 0) {
                    if (str[i] === '{') depth++;
                    if (str[i] === '}') depth--;
                    i++;
                }
                return str.substring(start, i-1);
             }
             // Single char (approximate for simple latex)
             const start = i;
             // Advance until next special char or space - simplified: just 1 char
             // But if it's a command like \infty? 
             if (str[i] === '\\') {
                 i++;
                 while(i < str.length && /[a-zA-Z]/.test(str[i])) i++;
                 return str.substring(start, i);
             }
             return str[i++]; 
          };
    
          // Order of _ and ^ doesn't matter, try to pick both
          for(let step=0; step<2; step++) {
              // skip spaces
              while(i < str.length && str[i] === ' ') i++;
              
              if (i < str.length && str[i] === '_') {
                  i++;
                  min = parseGroup();
              } else if (i < str.length && str[i] === '^') {
                  i++; 
                  max = parseGroup();
              } else {
                  break; 
              }
          }
          return { min, max, end: i };
      };

      // --- BRANCH A: Summation ---
      if (clean.startsWith("\\sum")) {
          const bounds = parseBounds(4, clean);
          // If we successfully parsed bounds, use them
          if (bounds.min && bounds.max) {
             Calc.setExpression({
                 id: `val-${safeId}`,
                 latex: `S_{${safeId}} = ${clean}`,
                 secret: true
             });
             Calc.setExpression({
                id: `label-${safeId}`,
                latex: `(0,0)`,
                label: `Sum = \${S_{${safeId}}}`,
                showLabel: true,
                hidden: true,
                color: "#000"
             });
             return;
          }
      }

      // --- BRANCH B: Definite/Indefinite Integral ---
      if (clean.startsWith("\\int")) {
          const bounds = parseBounds(4, clean);
          const rest = clean.substring(bounds.end).trim();
          
          // Regex to split body and variable (look for 'd' + var at end)
          // e.g. "sin x dx" -> var=x, body="sin x"
          const varMatch = rest.match(/d([a-zA-Z])$/);

          if (varMatch) {
              const variable = varMatch[1];
              const body = rest.substring(0, rest.lastIndexOf('d' + variable)).trim();

              if (bounds.min && bounds.max) {
                 // Definite
                 Calc.setExpression({
                    id: `val-${safeId}`,
                    latex: `I_{${safeId}} = ${clean}`,
                    secret: true
                 });
                 // To plot, replace variable with x
                 const plotBody = variable === 'x' ? body : body.split(variable).join("x");
                 Calc.setExpression({
                     id: `curve-${safeId}`,
                     latex: `y = ${plotBody}`,
                     lineStyle: window.Desmos.Styles.DASHED,
                     color: "#2d70b3"
                 });
  
                 const shadeLatex = `0 \\le y \\le ${plotBody} \\left\\{ ${bounds.min} \\le x \\le ${bounds.max} \\right\\}`;
                 Calc.setExpression({
                      id: `shade-${safeId}`,
                      latex: shadeLatex,
                      color: "#2d70b3",
                      fillOpacity: 0.3,
                      lines: false
                 });
  
                 Calc.setExpression({
                     id: `label-${safeId}`,
                     latex: `((${bounds.min} + ${bounds.max})/2, 0)`,
                     label: `Area = \${I_{${safeId}}}`,
                     showLabel: true,
                     hidden: true,
                     color: "#000"
                 });
                 return;
              } else {
                  // Indefinite (if no bounds or partial bounds, treat as indefinite)
                  
                  // 1. Plot Original Function (Dashed/Secondary)
                  const plotOriginal = variable === 'x' ? body : body.split(variable).join("x");
                  Calc.setExpression({
                      id: `curve-${safeId}`,
                      latex: `y = ${plotOriginal}`,
                      lineStyle: window.Desmos.Styles.DASHED,
                      color: "#999999"
                  });

                  // 2. Plot Antiderivative
                  const bodyWithT = body.split(variable).join("t");
                  Calc.setExpression({ 
                      id, 
                      latex: `y = \\int_{0}^{x} ${bodyWithT} dt`, 
                      color: "#2d70b3" 
                  });
                  return;
              }
          }
      }

      // --- BRANCH C: Derivative (Symbolic & Numeric) ---
      // Pattern: \frac{d}{dx} ... |_{x=val} or \frac{d^n}{dx^n} ...
      const derivRegex = /^\\frac\{d(\^\{?([0-9]+)\}?)?\}\{d([a-zA-Z])(\^\{?([0-9]+)\}?)?\}\s*(.+)$/;
      const derivMatch = clean.match(derivRegex);
      
      if (derivMatch) {
         const order = derivMatch[2] ? parseInt(derivMatch[2]) : 1;
         const variable = derivMatch[3];
         let content = derivMatch[6];
         
         let isEvaluation = false;
         let targetVal = "";
         let body = content;

         // Check for Evaluation Bar |_{x=...} at the end
         const barIndex = content.lastIndexOf("|_{");
         if (barIndex !== -1 && content.trim().endsWith("}")) {
             const possibleBody = content.substring(0, barIndex).trim();
             const evalPart = content.substring(barIndex + 3, content.length - 1); 
             const parts = evalPart.split("=");
             if (parts.length === 2 && parts[0].trim() === variable) {
                 isEvaluation = true;
                 targetVal = parts[1].trim();
                 body = possibleBody;
             }
         }

         // 1. Define the Function Secretly
         Calc.setExpression({
            id: `funcD-${safeId}`,
            latex: `f_{${safeId}}(${variable}) = ${body}`,
            secret: true
         });

         // 2. Plot Original Function (Dashed/Secondary)
         // Map variable to x for plotting if needed, but f(x) works if defined as f(t)
         // But Desmos `y = ...` expects x usually.
         Calc.setExpression({
             id: `plot-orig-${safeId}`,
             latex: `y = f_{${safeId}}(x)`,
             lineStyle: window.Desmos.Styles.DASHED, // Dashed to distinguish from derivative
             color: "#999999", // Grayish
             label: "f(x)"
         });

         // 3. Plot Derivative Function (Solid/Primary)
         {
             let derivNotation = "";
             if (order <= 3) {
                 let primes = "";
                 for(let k=0; k<order; k++) primes += "'";
                 derivNotation = `f_{${safeId}}${primes}(x)`;
             } else {
                 derivNotation = `\\frac{d^${order}}{dx^${order}} f_{${safeId}}(x)`; 
             }
             
             Calc.setExpression({
                 id: `plot-deriv-${safeId}`,
                 latex: `y = ${derivNotation}`,
                 color: "#2d70b3", // Main blue
                 label: `f${order > 1 ? `^(${order})` : "'"}(x)`
             });
         }

         // 4. If Evaluation, Show Point and Label
         if (isEvaluation) {
             let valLatex = "";
             let labelStr = "";
             
             if (order <= 3) {
                 let primes = "";
                 for(let k=0; k<order; k++) primes += "'";
                 valLatex = `f_{${safeId}}${primes}(${targetVal})`;
                 labelStr = `f${primes}(${targetVal})`;
             } else {
                 valLatex = `\\frac{d^${order}}{d${variable}^${order}} f_{${safeId}}(${targetVal})`;
                 labelStr = `f^(${order})(${targetVal})`;
             }

             Calc.setExpression({
                id: `val-${safeId}`,
                latex: `V_{${safeId}} = ${valLatex}`,
                secret: true
             });
    
             Calc.setExpression({
                id: `label-${safeId}`,
                latex: `(0,0)`, // Or maybe (${targetVal}, V_{safeId})? Keeping at origin/corner per user preference usually
                label: `${labelStr} = \${V_{${safeId}}}`,
                showLabel: true,
                hidden: true,
                color: "#000000"
             });
         }
         return;
      }

      // --- BRANCH D: Standard ---
      let finalLatex = clean;
      if (!finalLatex.includes("int") && !finalLatex.includes("frac") && finalLatex.endsWith("dx")) {
           finalLatex = finalLatex.replace(/d[x-z]$/, "");
      }

      Calc.setExpression({ 
          id: id, 
          latex: finalLatex, 
          color: "#2d70b3",
          showLabel: true 
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