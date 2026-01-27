
import React from "react";
import { Calculator as CalcIcon, PanelLeftClose } from "lucide-react";
import { MathExpression } from "../components/calculator/types";
import { computeSymbolicDerivative, computeSymbolicIntegral } from "../utils/symbolic-math";

interface GraphLegendProps {
    expressions: MathExpression[];
    legendOpen: boolean;
    setLegendOpen: (open: boolean) => void;
    resolvedTheme?: string;
}

// Helper function to invert colors for dark mode (Desmos-style)
// Desmos rotates hue by 180° (complementary color) for dark mode
const invertColorForDarkMode = (color: string, isDark: boolean): string => {
    if (!isDark) return color;
    
    // Convert hex to RGB
    const hex = color.replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);
    
    // Convert to HSL
    const rNorm = r / 255;
    const gNorm = g / 255;
    const bNorm = b / 255;
    
    const max = Math.max(rNorm, gNorm, bNorm);
    const min = Math.min(rNorm, gNorm, bNorm);
    let h = 0, s = 0;
    const l = (max + min) / 2;
    
    if (max !== min) {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case rNorm: h = ((gNorm - bNorm) / d + (gNorm < bNorm ? 6 : 0)) / 6; break;
            case gNorm: h = ((bNorm - rNorm) / d + 2) / 6; break;
            case bNorm: h = ((rNorm - gNorm) / d + 4) / 6; break;
        }
    }
    
    // Desmos inverts by rotating hue 180° (complementary color)
    let newH = (h + 0.5) % 1;
    
    // Keep saturation, slightly adjust lightness for visibility on dark background
    let newS = s;
    let newL = Math.max(0.4, Math.min(0.8, l + 0.1)); // Ensure visible on dark bg
    
    // Convert back to RGB
    const hue2rgb = (p: number, q: number, t: number) => {
        if (t < 0) t += 1;
        if (t > 1) t -= 1;
        if (t < 1/6) return p + (q - p) * 6 * t;
        if (t < 1/2) return q;
        if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
        return p;
    };
    
    const q = newL < 0.5 ? newL * (1 + newS) : newL + newS - newL * newS;
    const p = 2 * newL - q;
    const newR = Math.round(hue2rgb(p, q, newH + 1/3) * 255);
    const newG = Math.round(hue2rgb(p, q, newH) * 255);
    const newB = Math.round(hue2rgb(p, q, newH - 1/3) * 255);
    
    return `#${newR.toString(16).padStart(2, '0')}${newG.toString(16).padStart(2, '0')}${newB.toString(16).padStart(2, '0')}`;
};

export const GraphLegend: React.FC<GraphLegendProps> = ({ expressions, legendOpen, setLegendOpen, resolvedTheme }) => {
    const isDark = resolvedTheme === 'dark';

    const getLegendData = (rawLatex: string) => {
        let clean = rawLatex
            .replace(/\\bigm/g, "")
            .replace(/\\!/g, "")
            .replace(/\\,/g, " ").replace(/\\:/g, " ").replace(/\\;/g, " ")
            .replace(/\\limits/g, "")
            .replace(/\\differentialD/g, "d")
            .replace(/\\mathrm\{d\}/g, "d")
            .replace(/\\dfrac/g, "\\frac")
            .trim();

        // ==========================================
        // HANDLE MALFORMED \mathrm{} BLOCKS
        // ==========================================
        // Handle cases like \mathrm{\sin^2xd} where trig function is inside \mathrm{}
        // Extract trig functions from inside \mathrm{} blocks
        // Pattern: \mathrm{\sin^2xd} -> \sin^2x d (extract trig and separate d)
        clean = clean
            // \mathrm{\sin^nx d} or \mathrm{\sin^{n}x d} -> \sin^{n}x d
            .replace(/\\mathrm\{\\?(sin|cos|tan|cot|sec|csc)\^\{?([^}\s]+)\}?([a-zA-Z])\s*d\}/g, '\\$1^{$2}$3 d')
            // \mathrm{\sinx d} -> \sin x d (no power)
            .replace(/\\mathrm\{\\?(sin|cos|tan|cot|sec|csc)([a-zA-Z])\s*d\}/g, '\\$1 $2 d')
            // \mathrm{\sin(expr)d} -> \sin(expr) d
            .replace(/\\mathrm\{\\?(sin|cos|tan|cot|sec|csc)\s*\(([^)]+)\)\s*d\}/g, '\\$1($2) d')
            // Generic: \mathrm{content} where content has a trailing 'd' for differential
            // \mathrm{...d} at end of integral body -> extract content + d
            .replace(/\\mathrm\{([^}]+)d\}([a-zA-Z])$/g, '$1 d$2');

        // Fix Logarithm bases
        clean = clean.replace(/\\log_(\d+)/g, "\\log_{$1}");

        // ==========================================
        // NORMALIZE TRIG^N NOTATION FOR DISPLAY
        // ==========================================
        // Convert \sin^2x to \sin^{2}x for consistent display
        // Convert \sin^{2}x to (\sin x)^{2} for cleaner legend display
        // This ensures the legend shows the full expression correctly
        clean = clean
            // First normalize unbraced powers: \sin^2x -> \sin^{2}x
            .replace(/\\(sin|cos|tan|cot|sec|csc)\^(\d+)([a-zA-Z])/g, '\\$1^{$2}$3')
            // Then convert to explicit notation: \sin^{n}x -> (\sin x)^{n}
            .replace(/\\(sin|cos|tan|cot|sec|csc)\^\{([^}]+)\}([a-zA-Z])/g, '(\\$1 $3)^{$2}')
            // Also handle with parentheses: \sin^{n}(expr) -> (\sin(expr))^{n}
            .replace(/\\(sin|cos|tan|cot|sec|csc)\^\{([^}]+)\}\s*\(([^)]+)\)/g, '(\\$1($3))^{$2}')
            .replace(/\\(sin|cos|tan|cot|sec|csc)\^(\d+)\s*\(([^)]+)\)/g, '(\\$1($3))^{$2}');

        // ==========================================
        //      DERIVATIVE PARSING WITH SYMBOLIC RESULT
        // ==========================================
        // Updated regex to handle spaces like "d x" instead of "dx" and various derivative notations
        const derivRegex = /^\\frac\s*\{\s*d(\^\{?([0-9]+)\}?)?\s*\}\s*\{\s*d\s*(\\[a-zA-Z]+|[a-zA-Z])(\^\{?([0-9]+)\}?)?\s*\}\s*(.+)$/;
        const derivMatch = clean.match(derivRegex);
        if (derivMatch) {
            const order = derivMatch[2] ? parseInt(derivMatch[2]) : 1;
            const variable = derivMatch[3] ? derivMatch[3].replace('\\', '') : 'x';

            // Extract the function being derived
            let content = derivMatch[6];
            
            // Handle evaluation point notation: |_{x=...} or \bigm|_{x=...}
            const barIndex = content.lastIndexOf("|_{");
            if (barIndex !== -1 && content.trim().endsWith("}")) {
                content = content.substring(0, barIndex).trim();
            }
            
            // Also handle \placeholder{} that might be in evaluation expressions
            content = content.replace(/\\placeholder\{[^}]*\}/g, '').trim();

            // Clean up parent label
            let parentLabel = content
                .replace(/\\left\s*/g, '')
                .replace(/\\right\s*/g, '')
                .trim();

            if (parentLabel.length > 30) {
                parentLabel = `f(${variable})`;
            }

            // Compute symbolic derivative using nerdamer
            const symbolicResult = computeSymbolicDerivative(content, variable, order);

            // Build the result label with proper order indication
            let resultLabel: string;
            let orderLabel = '';
            if (order === 1) {
                orderLabel = "f'(" + variable + ")";
            } else if (order === 2) {
                orderLabel = "f''(" + variable + ")";
            } else if (order === 3) {
                orderLabel = "f'''(" + variable + ")";
            } else {
                orderLabel = `f^{(${order})}(${variable})`;
            }

            if (symbolicResult) {
                // We got a symbolic result! Show it with the order notation
                resultLabel = symbolicResult;
            } else {
                // Fallback to showing the derivative notation
                const derivNotation = order > 1
                    ? `\\frac{d^{${order}}}{d${variable}^{${order}}}`
                    : `\\frac{d}{d${variable}}`;
                resultLabel = `${derivNotation}\\left(${parentLabel}\\right)`;
            }

            return [
                { type: 'dotted', label: parentLabel, math: true, description: 'Parent Function' },
                { type: 'solid', label: resultLabel, math: true, description: symbolicResult ? `${orderLabel} = Result` : 'Derivative' }
            ];
        }

        // ==========================================
        //      INTEGRAL PARSING WITH SYMBOLIC RESULT
        // ==========================================
        if (clean.startsWith("\\int")) {
            // Robust regex to capture integral bounds
            // For bare bounds (without braces), only match:
            // - Digits with optional minus sign: -?\d+
            // - Single letter: [a-zA-Z]
            // - LaTeX command: \\[a-zA-Z]+
            // This prevents capturing part of the integrand (e.g., ^3x should only capture 3)
            const boundsRegex = /^\\int(?:_\{([^}]*)\}|_(-?\d+|[a-zA-Z]|\\[a-zA-Z]+))?(?:\^\{([^}]*)\}|\^(-?\d+|[a-zA-Z]|\\[a-zA-Z]+))?/;
            const boundsMatch = clean.match(boundsRegex);

            // Extract and CLEAN bounds
            let lowerBound = boundsMatch ? (boundsMatch[1] ?? boundsMatch[2] ?? null) : null;
            let upperBound = boundsMatch ? (boundsMatch[3] ?? boundsMatch[4] ?? null) : null;

            if (lowerBound) lowerBound = lowerBound.replace(/\\left\s*/g, '').replace(/\\right\s*/g, '').trim();
            if (upperBound) upperBound = upperBound.replace(/\\left\s*/g, '').replace(/\\right\s*/g, '').trim();

            const hasBounds = lowerBound !== null && upperBound !== null;

            // Extract body
            let body = boundsMatch ? clean.substring(boundsMatch[0].length).trim() : clean.substring(4).trim();

            // Extract differential variable
            let diffVar = 'x';
            // Clean thin spaces (\,) from the body first - these are formatting only
            body = body.replace(/\\,/g, '').trim();
            
            const dMatch = body.match(/(?:\\mathrm\{d\}|d)(\\[a-zA-Z]+|[a-zA-Z])$/);
            if (dMatch) {
                const rawVar = dMatch[1];
                diffVar = rawVar.replace('\\', '');
                const dPattern = new RegExp(`(?:\\\\mathrm\\{d\\}|d)${rawVar.replace('\\', '\\\\')}$`);
                body = body.replace(dPattern, '').trim();
            }

            let cleanBody = body.replace(/\\left\s*/g, '').replace(/\\right\s*/g, '').trim();

            if (cleanBody.startsWith('(') && cleanBody.endsWith(')')) {
                let depth = 0;
                let isOuter = true;
                for (let i = 0; i < cleanBody.length - 1; i++) {
                    if (cleanBody[i] === '(') depth++;
                    else if (cleanBody[i] === ')') depth--;
                    if (depth === 0 && i < cleanBody.length - 1) {
                        isOuter = false;
                        break;
                    }
                }
                if (isOuter) {
                    cleanBody = cleanBody.substring(1, cleanBody.length - 1).trim();
                }
            }

            const parentLabel = cleanBody.length > 25 ? `f(${diffVar})` : cleanBody;
            const symbolicIntegral = computeSymbolicIntegral(cleanBody, diffVar);

            if (hasBounds) {
                let antiderivLabel: string;
                if (symbolicIntegral) {
                    antiderivLabel = symbolicIntegral;
                } else {
                    antiderivLabel = `F(${diffVar})`;
                }

                const areaLabel = `\\int_{${lowerBound}}^{${upperBound}} ${parentLabel} \\, d${diffVar}`;

                return [
                    { type: 'dotted', label: parentLabel, math: true, description: 'Parent Function (Integrand)' },
                    { type: 'solid', label: antiderivLabel, math: true, description: symbolicIntegral ? 'Antiderivative' : 'Antiderivative F(x)' },
                    { type: 'area', label: areaLabel, math: true, description: 'Definite Integral (Area)' }
                ];
            } else {
                let antiderivLabel: string;
                if (symbolicIntegral) {
                    antiderivLabel = `${symbolicIntegral} + C`;
                } else {
                    antiderivLabel = `\\int ${parentLabel}\\, d${diffVar}`;
                }

                return [
                    { type: 'dotted', label: parentLabel, math: true, description: 'Parent Function (Integrand)' },
                    { type: 'solid', label: antiderivLabel, math: true, description: symbolicIntegral ? 'Antiderivative' : 'Integral' }
                ];
            }
        }

        return [{ type: 'solid', label: clean, math: true }];
    };

    return (
        <div className={`absolute top-4 right-4 bg-card/90 backdrop-blur-sm rounded-lg shadow-md border text-xs z-10 select-none transition-all duration-200 overflow-hidden flex flex-col ${legendOpen ? 'max-h-[60vh] min-w-[220px] max-w-[400px] w-auto' : 'w-auto h-auto'}`}>
            <div
                className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/50 border-b border-border/50"
                onClick={() => setLegendOpen(!legendOpen)}
            >
                <div className="flex items-center gap-2">
                    {/* @ts-ignore */}
                    <CalcIcon size={14} className="opacity-70" />
                    <span className={`font-bold opacity-70 ${!legendOpen && 'hidden'}`}>Graph Legend</span>
                </div>
                <div className={`transition-transform duration-200 ${legendOpen ? 'rotate-0' : 'rotate-180'}`}>
                    <PanelLeftClose size={14} className="rotate-90" />
                </div>
            </div>

            {legendOpen && (
                <div className="p-3 pt-2 overflow-y-auto space-y-4">
                    {expressions.filter(e => e.latex.trim()).map((expr, i) => {
                        const items = getLegendData(expr.latex);
                        // Apply color inversion for dark mode to match Desmos graph colors
                        const displayColor = invertColorForDarkMode(expr.color, isDark);
                        return (
                            <div key={expr.id} className="flex flex-col gap-1.5">
                                <div className="flex items-center gap-2 font-medium opacity-90 text-[10px] uppercase tracking-wider text-muted-foreground">
                                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: displayColor }}></div>
                                    <span>Expr {i + 1}</span>
                                </div>
                                <div className="grid grid-cols-[24px_1fr] gap-x-2 gap-y-2 items-center pl-1">
                                    {items.map((item: any, idx: number) => (
                                        <React.Fragment key={idx}>
                                            <div className="flex items-center justify-center">
                                                {item.type === 'dotted' && (
                                                    <div className="w-full border-t-[3px] border-dotted" style={{ borderColor: displayColor }}></div>
                                                )}
                                                {item.type === 'solid' && (
                                                    <div className="w-full h-0.5" style={{ backgroundColor: displayColor }}></div>
                                                )}
                                                {item.type === 'area' && (
                                                    <div className="w-full h-3 rounded-[2px] opacity-40 border border-transparent" style={{ backgroundColor: displayColor }}></div>
                                                )}
                                            </div>
                                            <div className="min-w-0 overflow-x-auto max-w-full">
                                                {item.math ? (
                                                    /* @ts-ignore */
                                                    <math-field read-only style={{
                                                        fontSize: '0.85rem',
                                                        backgroundColor: 'transparent',
                                                        color: 'inherit',
                                                        padding: 0,
                                                        margin: 0,
                                                        border: 'none',
                                                        outline: 'none',
                                                        '--caret-color': 'transparent',
                                                        display: 'inline-block',
                                                        maxWidth: '100%',
                                                        overflowX: 'auto',
                                                        whiteSpace: 'nowrap',
                                                    }}>{item.label}</math-field>
                                                ) : (
                                                    <span className="opacity-70 truncate block">{item.label}</span>
                                                )}
                                            </div>
                                        </React.Fragment>
                                    ))}
                                </div>
                            </div>
                        );
                    })}

                    {expressions.every(e => !e.latex.trim()) && (
                        <div className="text-muted-foreground italic text-center py-2 opacity-50">No graphs active</div>
                    )}
                </div>
            )}
        </div>
    );
};
