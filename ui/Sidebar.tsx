import React, { useRef, useCallback, useEffect, useState } from "react";
import { Plus, Trash2, Terminal, Eye, EyeOff, ChevronDown, Play, Pause, Info, Loader2, Activity, TrendingUp, Maximize, Infinity as InfinityIcon, List, Crosshair } from "lucide-react";
import { MathExpression, VisibilityMode } from "../components/calculator/types";
import { analyzeFunction } from "../app/actions";
import { latexToHuman, extractCoreFunctionForAnalysis } from "../utils/latexToHuman";

// In-memory browser cache for function analysis. Persists until page reload.
// Stores Promises to handle concurrent requests for the exact same expression.
const analysisCache = new Map<string, Promise<any>>();

// Custom inline shortcuts for calculus operations
const CUSTOM_INLINE_SHORTCUTS = {
    // INTEGRAL SHORTCUTS
    'int': '\\int #?\\mathrm{d}x',
    'dint': '\\int_{#?}^{#?}#?\\mathrm{d}x',
    
    // DERIVATIVE SHORTCUTS
    'ddx': '\\frac{d}{dx}#?',
    'ddy': '\\frac{d}{dy}#?',
    'd2dx2': '\\frac{d^{2}}{dx^{2}}#?',
    'dndxn': '\\frac{d^{#?}}{dx^{#?}}#?\\bigm|_{x=#?}',
    'deriv': '\\frac{d}{d#?}#?\\bigm|_{#?=#?}',
    
    // PARTIAL DERIVATIVE SHORTCUTS
    'pdx': '\\frac{\\partial}{\\partial x}#?',
    'pdy': '\\frac{\\partial}{\\partial y}#?',
    
    // LIMIT SHORTCUTS
    'lim': '\\lim_{#?\\to #?}#?',
    'limx': '\\lim_{x\\to #?}#?',
    
    // SUMMATION SHORTCUTS
    'sum': '\\sum_{#?}^{#?}#?',
    'sumn': '\\sum_{n=#?}^{#?}#?',
};

// Helper function to invert colors for dark mode (Desmos-style)
const invertColorForDarkMode = (color: string, isDark: boolean): string => {
    if (!isDark) return color;
    
    const hex = color.replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);
    
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
    
    const newH = (h + 0.5) % 1;
    const newL = Math.max(0.4, Math.min(0.8, l + 0.1));
    
    const hue2rgb = (p: number, q: number, t: number) => {
        if (t < 0) t += 1;
        if (t > 1) t -= 1;
        if (t < 1/6) return p + (q - p) * 6 * t;
        if (t < 1/2) return q;
        if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
        return p;
    };
    
    const q = newL < 0.5 ? newL * (1 + s) : newL + s - newL * s;
    const p = 2 * newL - q;
    const newR = Math.round(hue2rgb(p, q, newH + 1/3) * 255);
    const newG = Math.round(hue2rgb(p, q, newH) * 255);
    const newB = Math.round(hue2rgb(p, q, newH - 1/3) * 255);
    
    return `#${newR.toString(16).padStart(2, '0')}${newG.toString(16).padStart(2, '0')}${newB.toString(16).padStart(2, '0')}`;
};

interface SidebarProps {
    expressions: MathExpression[];
    handleColorChange: (id: string, color: string) => void;
    handleInput: (id: string, value: string) => void;
    removeExpr: (id: string) => void;
    addExpr: (initialLatex?: string) => void;
    toggleVisibility: (id: string) => void;
    setVisibilityMode: (id: string, mode: VisibilityMode) => void;
    toggleAreaMode: (id: string) => void;
    updateSliderBounds: (id: string, min: string, max: string, step: string) => void;
    setExpressionPlaying: (id: string, playing: boolean) => void;
    debugInfo: string;
    resolvedTheme: string | undefined;
}

const isMultiCurveExpression = (latex: string): boolean => {
    if (!latex) return false;
    const clean = latex
        .replace(/\\mathrm\{d\}/g, "d")
        .replace(/\\differentialD/g, "d")
        .replace(/\\dfrac/g, "\\frac")
        .replace(/\\bigm/g, "")
        .trim();
    const derivRegex = /^\\frac\s*\{\s*d(\^\{?[0-9]+\}?)?\s*\}\s*\{\s*d/;
    return derivRegex.test(clean) || clean.startsWith("\\int");
};

const isDefiniteIntegral = (latex: string): boolean => {
    if (!latex) return false;
    const hasInt = latex.includes('\\int');
    const hasLower = /_\{?[^}]+\}?/.test(latex);
    const hasUpper = /\^\{?[^}]+\}?/.test(latex);
    return hasInt && hasLower && hasUpper;
};

const formatAnalysisValue = (val: any, isInterval: boolean = false): React.ReactNode => {
    if (val === null || val === undefined || val === 'None' || (!isInterval && val === '[]') || val === '{}' || val === '' || val === 'EmptySet' || val === '∅') return '-';
    let s = String(val);
    
    if (!isInterval) {
        // Remove outer brackets for arrays of tuples like [(0, 0)] -> (0, 0)
        s = s.replace(/^\[(.*)\]$/, '$1');
    }
    
    if (s === '') return '-';
    
    // Polish the math string representation
    s = s
        .replace(/\*\*/g, '^')
        .replace(/-oo/g, '-∞')
        .replace(/\boo\b/g, '∞')
        .replace(/\bpi\b/g, 'π')
        .replace(/ U /g, ' ∪ ')
        .replace(/\bU_\{/g, '⋃_{')
        .replace(/ \\ /g, ' ∖ ')
        .replace(/ ∩ /g, ' ∩ ')
        .replace(/\bR\b/g, 'ℝ')
        .replace(/\bZ\b/g, 'ℤ')
        .replace(/\bE\b/g, 'e')
        .replace(/\bin\b/g, ' ∈ ')
        .replace(/\bEmptySet\b/g, '∅')
        .replace(/sqrt\(([^)]+)\)/g, '√($1)')
        .replace(/\bexp\(/g, 'e^(')
        .replace(/\bfactorial\(([^)]+)\)/g, '($1)!')
        .replace(/\*/g, '·'); // replace remaining asterisks with a cleaner middle dot

    // Parse the string and wrap exponents and subscripts in <sup> and <sub>
    const parseMathString = (str: string, keyPrefix: string = ''): React.ReactNode => {
        const parts = [];
        let i = 0;
        while (i < str.length) {
            if (str[i] === '^' || str[i] === '_') {
                const isSup = str[i] === '^';
                i++;
                if (i < str.length && str[i] === '(') {
                    let j = i + 1;
                    let depth = 1;
                    while (j < str.length && depth > 0) {
                        if (str[j] === '(') depth++;
                        if (str[j] === ')') depth--;
                        j++;
                    }
                    const content = parseMathString(str.substring(i + 1, j - 1), `${keyPrefix}-${i}`);
                    parts.push(isSup ? <sup key={`${keyPrefix}-${i}`}>{content}</sup> : <sub key={`${keyPrefix}-${i}`}>{content}</sub>);
                    i = j;
                } else if (i < str.length && str[i] === '{') {
                    let j = i + 1;
                    let depth = 1;
                    while (j < str.length && depth > 0) {
                        if (str[j] === '{') depth++;
                        if (str[j] === '}') depth--;
                        j++;
                    }
                    const content = parseMathString(str.substring(i + 1, j - 1), `${keyPrefix}-${i}`);
                    parts.push(isSup ? <sup key={`${keyPrefix}-${i}`}>{content}</sup> : <sub key={`${keyPrefix}-${i}`}>{content}</sub>);
                    i = j;
                } else {
                    let j = i;
                    // match single character or continuous alphanumeric sequence
                    while (j < str.length && /[a-zA-Z0-9\.]/.test(str[j])) j++;
                    if (j > i) {
                        const content = parseMathString(str.substring(i, j), `${keyPrefix}-${i}`);
                        parts.push(isSup ? <sup key={`${keyPrefix}-${i}`}>{content}</sup> : <sub key={`${keyPrefix}-${i}`}>{content}</sub>);
                        i = j;
                    } else {
                        // just a standalone ^ or _
                        parts.push(isSup ? '^' : '_');
                    }
                }
            } else {
                let nextChar = str.substring(i).search(/[\^_]/);
                if (nextChar === -1) {
                    parts.push(<React.Fragment key={`txt-${keyPrefix}-${i}`}>{str.substring(i)}</React.Fragment>);
                    break;
                } else {
                    nextChar += i;
                    parts.push(<React.Fragment key={`txt-${keyPrefix}-${i}`}>{str.substring(i, nextChar)}</React.Fragment>);
                    i = nextChar;
                }
            }
        }
        return <>{parts}</>;
    };

    return parseMathString(s);
};

const getVisibilityIcon = (mode: VisibilityMode, visible: boolean) => {
    if (!visible || mode === 'none') return <EyeOff size={15} />;
    return <Eye size={15} />;
};

export const Sidebar: React.FC<SidebarProps> = ({
    expressions,
    handleColorChange,
    handleInput,
    removeExpr,
    addExpr,
    toggleVisibility,
    setVisibilityMode,
    toggleAreaMode,
    updateSliderBounds,
    setExpressionPlaying,
    debugInfo,
    resolvedTheme
}) => {
    const mathFieldRefs = useRef<Map<string, HTMLElement>>(new Map());
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    const prevExpressionsLength = useRef(expressions.length);

    // Analysis state
    const [analysisData, setAnalysisData] = useState<Record<string, any>>({});
    const [analyzingIds, setAnalyzingIds] = useState<Set<string>>(new Set());
    const [activeAnalysisId, setActiveAnalysisId] = useState<string | null>(null);

    const handleAnalyze = async (id: string, latex: string) => {
        setActiveAnalysisId(id);

        const humanExpr = extractCoreFunctionForAnalysis(latex);
        if (!humanExpr) return;

        const cacheKey = humanExpr.trim();

        setAnalyzingIds(prev => new Set(prev).add(id));

        try {
            let resultPromise = analysisCache.get(cacheKey);
            
            if (!resultPromise) {
                // Initiate the request and cache the promise to handle concurrent calls
                resultPromise = analyzeFunction(humanExpr) as Promise<any>;
                analysisCache.set(cacheKey, resultPromise);
            }
            
            const result = await resultPromise;
            
            // Do not cache server connection/gRPC errors so users can retry
            if (result && result.is_server_error) {
                analysisCache.delete(cacheKey);
            }
            
            setAnalysisData(prev => ({ ...prev, [id]: result }));
        } catch (error) {
            console.error("Analysis failed:", error);
            analysisCache.delete(cacheKey);
            setAnalysisData(prev => ({ 
                ...prev, 
                [id]: { has_error: true, error_message: "An unexpected error occurred." } 
            }));
        } finally {
            setAnalyzingIds(prev => {
                const next = new Set(prev);
                next.delete(id);
                return next;
            });
        }
    };

    useEffect(() => {
        if (expressions.length > prevExpressionsLength.current) {
            const lastExpr = expressions[expressions.length - 1];
            setTimeout(() => {
                const el = mathFieldRefs.current.get(lastExpr.id);
                if (el && typeof (el as any).focus === 'function') {
                    (el as any).focus();
                }
            }, 100);
        }
        prevExpressionsLength.current = expressions.length;
    }, [expressions.length]);
    
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (openMenuId && !(e.target as Element).closest('.visibility-menu-container')) {
                setOpenMenuId(null);
            }
        };
        document.addEventListener('click', handleClickOutside);
        return () => document.removeEventListener('click', handleClickOutside);
    }, [openMenuId]);
    
    const handleMathFieldRef = useCallback((id: string, el: HTMLElement | null) => {
        if (el) {
            mathFieldRefs.current.set(id, el);
            const mf = el as any;
            
            if (mf.inlineShortcuts !== undefined) {
                mf.inlineShortcuts = {
                    ...(mf.inlineShortcuts || {}),
                    ...CUSTOM_INLINE_SHORTCUTS,
                };
            }
            
            const oldListener = (el as any).__enterKeyListener;
            if (oldListener) {
                el.removeEventListener('keydown', oldListener);
            }
            
            const newListener = (e: KeyboardEvent) => {
                if ((e.key === 'Enter' || e.code === 'Enter') && !e.shiftKey) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    addExpr();
                }
            };
            (el as any).__enterKeyListener = newListener;
            el.addEventListener('keydown', newListener);
            
            el.addEventListener('focus', () => {
                if (typeof mf.focus === 'function') mf.focus();
            });
            
            el.addEventListener('virtual-keyboard-toggle', () => {
                setTimeout(() => {
                    if (typeof mf.focus === 'function') mf.focus();
                }, 0);
            });
        } else {
            mathFieldRefs.current.delete(id);
        }
    }, [addExpr]); 
    
    return (
        <div className="flex flex-col h-full relative overflow-hidden">
            {activeAnalysisId ? (
                (() => {
                    const expr = expressions.find(e => e.id === activeAnalysisId);
                    if (!expr) {
                        setTimeout(() => setActiveAnalysisId(null), 0);
                        return null;
                    }

                    const data = analysisData[activeAnalysisId];
                    const isLoading = analyzingIds.has(activeAnalysisId);

                    return (
                        <div className="flex flex-col h-full bg-background animate-in slide-in-from-right-8 fade-in duration-300 z-50 absolute inset-0">
                            {/* Header */}
                            <div className="flex items-center p-3 border-b border-border/50 gap-3 shrink-0 bg-card">
                                <button 
                                    onClick={() => setActiveAnalysisId(null)}
                                    className="flex items-center justify-center w-10 h-10 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-all shadow-sm shrink-0"
                                    title="Back to expressions"
                                >
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                                </button>
                                <div className="flex-1 min-w-0 bg-muted/40 rounded-lg px-4 py-2.5 flex items-center overflow-x-auto custom-scrollbar border border-border/50">
                                    {/* @ts-ignore */}
                                    <math-field read-only style={{ backgroundColor: 'transparent', border: 'none', padding: 0, margin: 0, minWidth: 'min-content' }}>
                                        {expr.latex}
                                    </math-field>
                                </div>
                            </div>

                            {/* Content */}
                            <div className="flex-1 overflow-y-auto p-6 custom-scrollbar bg-background">
                                <h2 className="text-xl font-bold mb-8 text-foreground/90">Function analysis</h2>
                                
                                {isLoading ? (
                                    <div className="flex flex-col items-center justify-center py-20 opacity-60">
                                        <Loader2 size={40} className="animate-spin mb-6 text-primary" />
                                        <p className="text-sm font-medium">Analyzing mathematical properties...</p>
                                    </div>
                                ) : data?.has_error ? (
                                    <div className="text-destructive bg-destructive/10 p-5 rounded-xl border border-destructive/20 shadow-sm">
                                        <p className="font-semibold mb-2">Analysis Failed</p>
                                        <p className="text-sm opacity-90">{data.error_message}</p>
                                    </div>
                                ) : data ? (
                                    <div className="space-y-7 text-[13px]">
                                        {/* Domain & Range */}
                                        {data.domain_range && !data.domain_range.error && (
                                            <>
                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Domain</div>
                                                    <div className="font-mono text-base">{formatAnalysisValue(data.domain_range.domain, true)}</div>
                                                </div>
                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Range</div>
                                                    <div className="font-mono text-base">{formatAnalysisValue(data.domain_range.range, true)}</div>
                                                </div>
                                            </>
                                        )}
                                        
                                        {/* Intercepts */}
                                        {data.function_analysis && !data.function_analysis.error && (
                                            <>
                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">X-Intercept</div>
                                                    <div className="font-mono text-base">
                                                        {formatAnalysisValue(data.function_analysis.Intercepts?.x) !== '-' ? <React.Fragment>x = {formatAnalysisValue(data.function_analysis.Intercepts?.x)}</React.Fragment> : <span className="font-sans text-[13px] opacity-70">The function does not have any x-intercepts.</span>}
                                                    </div>
                                                </div>
                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Y-Intercept</div>
                                                    <div className="font-mono text-base">
                                                        {formatAnalysisValue(data.function_analysis.Intercepts?.y) !== '-' ? <React.Fragment>y = {formatAnalysisValue(data.function_analysis.Intercepts?.y)}</React.Fragment> : <span className="font-sans text-[13px] opacity-70">The function does not have any y-intercepts.</span>}
                                                    </div>
                                                </div>

                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Minima</div>
                                                    <div className="font-mono text-base">
                                                        {formatAnalysisValue(data.function_analysis.Extrema?.minima) !== '-' ? formatAnalysisValue(data.function_analysis.Extrema?.minima) : <span className="font-sans text-[13px] opacity-70">The function does not have any minima points.</span>}
                                                    </div>
                                                </div>
                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Maxima</div>
                                                    <div className="font-mono text-base">
                                                        {formatAnalysisValue(data.function_analysis.Extrema?.maxima) !== '-' ? formatAnalysisValue(data.function_analysis.Extrema?.maxima) : <span className="font-sans text-[13px] opacity-70">The function does not have any maxima points.</span>}
                                                    </div>
                                                </div>

                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Inflection points</div>
                                                    <div className="font-mono text-base">
                                                        {formatAnalysisValue(data.function_analysis['Inflection Points']) !== '-' ? formatAnalysisValue(data.function_analysis['Inflection Points']) : <span className="font-sans text-[13px] opacity-70">The function does not have any inflection points.</span>}
                                                    </div>
                                                </div>

                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Vertical asymptotes</div>
                                                    <div className="font-mono text-base">
                                                        {formatAnalysisValue(data.function_analysis.Asymptotes?.vertical) !== '-' ? formatAnalysisValue(data.function_analysis.Asymptotes?.vertical) : <span className="font-sans text-[13px] opacity-70">The function does not have any vertical asymptotes.</span>}
                                                    </div>
                                                </div>
                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Horizontal asymptotes</div>
                                                    <div className="font-mono text-base">
                                                        {formatAnalysisValue(data.function_analysis.Asymptotes?.horizontal) !== '-' ? formatAnalysisValue(data.function_analysis.Asymptotes?.horizontal) : <span className="font-sans text-[13px] opacity-70">The function does not have any horizontal asymptotes.</span>}
                                                    </div>
                                                </div>
                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Oblique asymptotes</div>
                                                    <div className="font-mono text-base">
                                                        {formatAnalysisValue(data.function_analysis.Asymptotes?.oblique) !== '-' ? formatAnalysisValue(data.function_analysis.Asymptotes?.oblique) : <span className="font-sans text-[13px] opacity-70">The function does not have any oblique asymptotes.</span>}
                                                    </div>
                                                </div>

                                                <div className="space-y-1.5">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold">Parity</div>
                                                    <div className="font-sans text-[13px]">
                                                        {data.function_analysis.Parity ? `The function is ${String(data.function_analysis.Parity).toLowerCase()}.` : 'Neither even nor odd.'}
                                                    </div>
                                                </div>
                                                
                                                <div className="space-y-2">
                                                    <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold mb-1">Monotonicity</div>
                                                    {formatAnalysisValue(data.function_analysis.Monotonicity?.increasing, true) !== '-' && (
                                                        <div className="flex items-center gap-5">
                                                            <div className="font-mono text-base min-w-[100px]">{formatAnalysisValue(data.function_analysis.Monotonicity?.increasing, true)}</div>
                                                            <div className="font-medium text-[13px]">Increasing</div>
                                                        </div>
                                                    )}
                                                    {formatAnalysisValue(data.function_analysis.Monotonicity?.decreasing, true) !== '-' && (
                                                        <div className="flex items-center gap-5 mt-2">
                                                            <div className="font-mono text-base min-w-[100px]">{formatAnalysisValue(data.function_analysis.Monotonicity?.decreasing, true)}</div>
                                                            <div className="font-medium text-[13px]">Decreasing</div>
                                                        </div>
                                                    )}
                                                    {formatAnalysisValue(data.function_analysis.Monotonicity?.increasing, true) === '-' && formatAnalysisValue(data.function_analysis.Monotonicity?.decreasing, true) === '-' && (
                                                        <div className="font-sans text-[13px] opacity-70">Constant or undefined.</div>
                                                    )}
                                                </div>

                                                {/* Tangent Equation */}
                                                {data.function_analysis['Tangent Equation'] && (
                                                    <div className="space-y-3 pt-6 border-t border-border/40 mt-4">
                                                        <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold flex items-center gap-2">
                                                            <TrendingUp size={14} /> Tangent Equation (at x = a)
                                                        </div>
                                                        <div className="bg-muted/30 p-4 rounded-xl overflow-x-auto custom-scrollbar border border-border/50">
                                                            {/* @ts-ignore */}
                                                            <math-field read-only style={{ backgroundColor: 'transparent', border: 'none', padding: 0, margin: 0, minWidth: 'min-content' }} className="text-base">
                                                                {data.function_analysis['Tangent Equation']}
                                                            </math-field>
                                                        </div>
                                                        <button 
                                                            onClick={() => {
                                                                // Convert tangent equation to use graphable format if necessary
                                                                // The engine returns y - f(a) = f'(a)(x-a) or similar
                                                                // Desmos/Ozon handles this perfectly if we just pass the raw equation!
                                                                addExpr(data.function_analysis['Tangent Equation']);
                                                                addExpr('a=1');
                                                                setActiveAnalysisId(null); // Return to graph list so user sees it
                                                            }}
                                                            className="px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-sm font-medium transition-colors shadow-sm inline-flex items-center gap-2"
                                                        >
                                                            <Plus size={16} /> Plot Tangent Line
                                                        </button>
                                                    </div>
                                                )}
                                            </>
                                        )}
                                        
                                        {/* Sequence / Series */}
                                        {(() => {
                                            const seqData = data.sequence_series;
                                            const hasValidData = seqData && !seqData.error && (
                                                seqData.seq_result || 
                                                seqData.ser_result || 
                                                (seqData.is_power_series && seqData.power_series_result && !seqData.power_series_result[1]?.includes('Could not parse'))
                                            );

                                            if (!hasValidData) return null;

                                            return (
                                                <div className="space-y-4 pt-6 border-t border-border/40 mt-4">
                                                    <div className="text-base font-bold flex items-center gap-2">
                                                        <List size={18} /> Sequence & Series
                                                    </div>
                                                    <div className="space-y-5">
                                                        {seqData.seq_result && (
                                                            <div className="space-y-1.5">
                                                                <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold flex items-center justify-between">
                                                                    <span>Sequence Limit</span>
                                                                    <span className={seqData.seq_result[0] ? 'text-green-500 font-bold' : 'text-amber-500 font-bold'}>{seqData.seq_result[0] ? 'Converges' : 'Diverges'}</span>
                                                                </div>
                                                                <div className="font-mono text-base">{formatAnalysisValue(seqData.seq_result[1])}</div>
                                                            </div>
                                                        )}
                                                        {seqData.ser_result && (
                                                            <div className="space-y-1.5">
                                                                <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold flex items-center justify-between">
                                                                    <span>Series Sum</span>
                                                                    <span className={seqData.ser_result[0] ? 'text-green-500 font-bold' : 'text-amber-500 font-bold'}>{seqData.ser_result[0] ? 'Converges' : 'Diverges'}</span>
                                                                </div>
                                                                <div className="font-mono text-base">{formatAnalysisValue(seqData.ser_result[1])}</div>
                                                            </div>
                                                        )}
                                                        {seqData.is_power_series && seqData.power_series_result && (
                                                            <div className="space-y-1.5">
                                                                <div className="text-muted-foreground text-xs uppercase tracking-wider font-semibold flex items-center justify-between">
                                                                    <span>Power Series</span>
                                                                    <span className={seqData.power_series_result[0] ? 'text-green-500 font-bold' : 'text-amber-500 font-bold'}>{seqData.power_series_result[0] ? 'Converges' : 'Diverges'}</span>
                                                                </div>
                                                                <div className="font-mono text-base">{formatAnalysisValue(seqData.power_series_result[1], true)}</div>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })()}
                                    </div>
                                ) : null}
                            </div>
                        </div>
                    );
                })()
            ) : (
                <>
                    <div className="p-3 flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar space-y-3 pb-6">
                {expressions.map((expr, i) => {
                    const isDark = resolvedTheme === 'dark';
                    const displayColor = invertColorForDarkMode(expr.color, isDark);
                    const isMenuOpen = openMenuId === expr.id;

                    const safeLatex = typeof expr.latex === 'string' ? expr.latex : '';
                    const sliderMatch = safeLatex.match(/^([a-zA-Z](?:_\{?[a-zA-Z0-9]+\}?)?)\s*=\s*([-+]?[0-9]*\.?[0-9]+)$/);
                    const isSlider = !!sliderMatch;
                    const sliderVal = isSlider ? parseFloat(sliderMatch![2]) : 0;
                    const sliderVar = isSlider ? sliderMatch![1] : '';
                    
                    const min = expr.sliderBounds?.min ?? "-10";
                    const max = expr.sliderBounds?.max ?? "10";
                    const step = expr.sliderBounds?.step ?? "";

                    return (
                    <div key={expr.id} className={`group relative flex gap-3 bg-card hover:bg-muted/30 focus-within:bg-muted/30 p-3 rounded-xl border border-border/50 focus-within:border-primary/40 shadow-sm transition-all duration-200 ${!expr.visible ? 'opacity-60' : ''} ${isMenuOpen ? 'z-50' : ''}`}>
                        
                        {/* Left Column: Number, Color, Visibility */}
                        <div className="flex flex-col items-center gap-3 shrink-0 pt-1">
                            <div className="text-[11px] font-bold text-muted-foreground/50 select-none w-5 text-center leading-none">{i + 1}</div>
                            
                            {/* Color picker */}
                            <div className="relative flex items-center justify-center">
                                <input
                                    type="color"
                                    value={expr.color}
                                    onChange={(e) => handleColorChange(expr.id, e.target.value)}
                                    className="w-5 h-5 absolute inset-0 opacity-0 cursor-pointer z-10"
                                    title="Change Graph Color"
                                />
                                <div 
                                    className="w-4 h-4 rounded-full shadow-sm transition-transform group-hover:scale-110"
                                    style={{ backgroundColor: displayColor, opacity: expr.visible ? 1 : 0.4, border: `2px solid ${displayColor}` }}
                                />
                            </div>

                            {/* Visibility toggle */}
                            <div className="relative shrink-0 visibility-menu-container">
                                {isMultiCurveExpression(safeLatex) ? (
                                    <>
                                        <button 
                                            onClick={() => setOpenMenuId(openMenuId === expr.id ? null : expr.id)}
                                            className={`flex items-center justify-center w-6 h-6 rounded-md transition-colors ${expr.visible ? 'text-foreground/70 hover:text-primary hover:bg-primary/10' : 'text-foreground/30 hover:text-foreground/60 hover:bg-muted'}`}
                                            title="Visibility options"
                                        >
                                            {getVisibilityIcon(expr.visibilityMode, expr.visible)}
                                        </button>
                                        {/* Dropdown menu */}
                                        {openMenuId === expr.id && (
                                            <div className="absolute top-full left-0 mt-1.5 z-50 bg-popover border border-border rounded-lg shadow-lg py-1 min-w-[150px] animate-in fade-in slide-in-from-top-2">
                                                <button
                                                    onClick={() => { setVisibilityMode(expr.id, 'all'); setOpenMenuId(null); }}
                                                    className={`w-full px-3 py-2 text-left text-xs hover:bg-muted/50 transition-colors flex items-center gap-2 ${expr.visibilityMode === 'all' ? 'text-primary font-medium' : 'text-foreground'}`}
                                                >
                                                    <Eye size={14} /> Show All
                                                </button>
                                                <button
                                                    onClick={() => { setVisibilityMode(expr.id, 'parent'); setOpenMenuId(null); }}
                                                    className={`w-full px-3 py-2 text-left text-xs hover:bg-muted/50 transition-colors flex items-center gap-2 ${expr.visibilityMode === 'parent' ? 'text-primary font-medium' : 'text-foreground'}`}
                                                >
                                                    <Eye size={14} /> Parent Only
                                                </button>
                                                <button
                                                    onClick={() => { setVisibilityMode(expr.id, 'operated'); setOpenMenuId(null); }}
                                                    className={`w-full px-3 py-2 text-left text-xs hover:bg-muted/50 transition-colors flex items-center gap-2 ${expr.visibilityMode === 'operated' ? 'text-primary font-medium' : 'text-foreground'}`}
                                                >
                                                    <Eye size={14} /> {safeLatex.startsWith("\\int") ? "Integral Only" : "Derivative Only"}
                                                </button>
                                                <button
                                                    onClick={() => { setVisibilityMode(expr.id, 'none'); setOpenMenuId(null); }}
                                                    className={`w-full px-3 py-2 text-left text-xs hover:bg-muted/50 transition-colors flex items-center gap-2 ${expr.visibilityMode === 'none' ? 'text-primary font-medium' : 'text-foreground'}`}
                                                >
                                                    <EyeOff size={14} /> Hide All
                                                </button>
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    <button 
                                        onClick={() => toggleVisibility(expr.id)}
                                        className={`flex items-center justify-center w-6 h-6 rounded-md transition-colors ${expr.visible ? 'text-foreground/70 hover:text-primary hover:bg-primary/10' : 'text-foreground/30 hover:text-foreground/60 hover:bg-muted'}`}
                                        title={expr.visible ? "Hide graph" : "Show graph"}
                                    >
                                        {expr.visible ? <Eye size={15} /> : <EyeOff size={15} />}
                                    </button>
                                )}
                            </div>
                        </div>

                        {/* Right Column: Math Field, Results, Sliders */}
                        <div className="flex-1 min-w-0 flex flex-col gap-1.5 relative">
                            {/* Top row of right column: Math Field & Delete */}
                            <div className="flex items-start gap-2 w-full">
                                <div className="flex-1 min-w-0 bg-transparent rounded-md flex items-center">
                                    {/* @ts-ignore */}
                                    <math-field
                                        ref={(el: HTMLElement | null) => handleMathFieldRef(expr.id, el)}
                                        smart-fence="off"
                                        virtual-keyboard-mode="onfocus"
                                        onInput={(e: any) => handleInput(expr.id, e.target.value)}
                                        onFocus={(e: any) => {
                                            const target = e.target;
                                            if (target && typeof target.focus === 'function') {
                                                requestAnimationFrame(() => target.focus());
                                            }
                                        }}
                                        onClick={(e: any) => {
                                            const target = e.currentTarget;
                                            if (target && typeof target.focus === 'function') {
                                                target.focus();
                                            }
                                        }}
                                        value={safeLatex}
                                        className="math-field-custom"
                                    >
                                        {safeLatex}
                                    </math-field>
                                </div>
                                <div className="flex gap-1 mt-1 shrink-0">
                                    <button 
                                        onClick={() => handleAnalyze(expr.id, safeLatex)} 
                                        className="opacity-0 group-hover:opacity-100 focus-within:opacity-100 p-1.5 text-muted-foreground hover:text-blue-500 hover:bg-blue-500/10 rounded-md transition-all"
                                        title="Analyze function"
                                    >
                                        {analyzingIds.has(expr.id) ? (
                                            <Loader2 size={16} className="animate-spin" />
                                        ) : (
                                            <Info size={16} />
                                        )}
                                    </button>
                                    <button 
                                        onClick={() => removeExpr(expr.id)} 
                                        className="opacity-0 group-hover:opacity-100 focus-within:opacity-100 p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-all"
                                        title="Remove expression"
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </div>
                            </div>

                            {/* Bottom Rows: Result and Modes */}
                            {expr.result && !isSlider && (
                                <div className="flex flex-wrap items-center gap-2 mt-0.5">
                                    <div className="flex items-center px-2 py-1 bg-primary/10 text-primary font-mono text-sm rounded-md whitespace-nowrap overflow-hidden text-ellipsis max-w-full">
                                        <span className="opacity-60 mr-1.5 font-sans select-none">=</span>
                                        <span className="truncate">{expr.result}</span>
                                    </div>
                                    {isDefiniteIntegral(safeLatex) && (
                                        <button 
                                            onClick={() => toggleAreaMode(expr.id)}
                                            className={`text-[11px] px-2.5 py-1 rounded-md border transition-colors whitespace-nowrap font-medium ${
                                                expr.isAreaMode 
                                                    ? 'bg-primary text-primary-foreground border-primary shadow-sm' 
                                                    : 'bg-background/50 text-muted-foreground border-border hover:text-foreground hover:bg-background'
                                            }`}
                                            title="Toggle Area Mode (Calculate |f(x)|)"
                                        >
                                            Area Mode
                                        </button>
                                    )}
                                </div>
                            )}

                            {/* Advanced Slider UI */}
                            {isSlider && (
                                <div className="flex flex-col gap-3 mt-1.5 p-3 bg-muted/20 rounded-lg border border-border/50">
                                    {/* Slider Row */}
                                    <div className="flex items-center gap-3">
                                        <button
                                            onClick={() => setExpressionPlaying(expr.id, !expr.isPlaying)}
                                            className={`flex items-center justify-center w-7 h-7 shrink-0 rounded-full border transition-all hover:scale-105 active:scale-95 ${expr.isPlaying ? 'bg-primary text-primary-foreground border-primary shadow-sm' : 'bg-background text-foreground/70 border-border hover:text-foreground hover:bg-muted'}`}
                                        >
                                            {expr.isPlaying ? <Pause size={12} fill="currentColor" /> : <Play size={12} fill="currentColor" className="ml-0.5" />}
                                        </button>
                                        
                                        <div className="flex-1 flex items-center min-w-0">
                                             <input 
                                                type="range"
                                                min={min} 
                                                max={max} 
                                                step={step !== "" ? step : "0.01"}
                                                value={sliderVal}
                                                onInput={(e) => {
                                                    const val = (e.target as HTMLInputElement).value;
                                                    handleInput(expr.id, `${sliderVar}=${val}`);
                                                }}
                                                className="w-full h-1.5 bg-border/50 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-md hover:[&::-webkit-slider-thumb]:scale-125 transition-all focus:outline-none"
                                            />
                                        </div>
                                    </div>
                                    
                                    {/* Bounds Row */}
                                    <div className="flex flex-wrap items-center gap-2 justify-between text-xs text-muted-foreground font-mono">
                                        <div className="flex items-center bg-background/60 rounded-md px-2 py-1 border border-border/50 focus-within:border-primary/50 transition-colors">
                                            <input
                                                type="text"
                                                value={min}
                                                onChange={(e) => updateSliderBounds(expr.id, e.target.value, max, step)}
                                                className="w-10 bg-transparent border-none focus:ring-0 focus:outline-none text-right transition-colors text-foreground"
                                                placeholder="-10"
                                            />
                                            <span className="opacity-40 select-none mx-1.5">≤</span>
                                            <span className="text-primary font-semibold">{sliderVar}</span>
                                            <span className="opacity-40 select-none mx-1.5">≤</span>
                                             <input
                                                type="text"
                                                value={max}
                                                onChange={(e) => updateSliderBounds(expr.id, min, e.target.value, step)}
                                                className="w-10 bg-transparent border-none focus:ring-0 focus:outline-none text-left transition-colors text-foreground"
                                                placeholder="10"
                                            />
                                        </div>
                                        <div className="flex items-center bg-background/60 rounded-md px-2 py-1 border border-border/50 focus-within:border-primary/50 transition-colors">
                                            <span className="opacity-50 select-none mr-1.5">step:</span>
                                            <input
                                                type="text"
                                                value={step}
                                                onChange={(e) => updateSliderBounds(expr.id, min, max, e.target.value)}
                                                className="w-10 bg-transparent border-none focus:ring-0 focus:outline-none text-center transition-colors text-foreground"
                                                placeholder="auto"
                                            />
                                        </div>
                                    </div>
                                </div>
                            )}
                            
                            {/* Missing Variables Sliders */}
                            {expr.missingVariables && expr.missingVariables.length > 0 && (
                                <div className="flex flex-wrap gap-1.5 items-center mt-1">
                                    <span className="text-[11px] text-muted-foreground/70 italic font-mono mr-1">add slider:</span>
                                    <button
                                        onClick={() => expr.missingVariables?.forEach(v => addExpr(`${v}=1`))}
                                        className="text-[11px] px-2.5 py-1 border border-primary/20 bg-primary/5 text-primary rounded-md hover:bg-primary/15 transition-colors font-mono font-medium"
                                    >
                                        all
                                    </button>
                                    {expr.missingVariables.map(v => (
                                        <button
                                            key={v}
                                            onClick={() => addExpr(`${v}=1`)}
                                            className="text-[11px] px-2.5 py-1 border border-border/60 bg-background text-foreground/80 rounded-md hover:bg-muted hover:text-foreground transition-colors font-mono"
                                        >
                                            {v}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                );
                })}
            </div>

            {/* Sticky Bottom Bar */}
            <div className="p-3 border-t bg-background/80 backdrop-blur-md space-y-3 shrink-0 sticky bottom-0 z-20">
                <button onClick={() => addExpr()} className="w-full py-2.5 border border-dashed border-border/80 rounded-xl flex items-center justify-center gap-2 text-sm font-medium text-muted-foreground hover:text-primary transition-all hover:bg-primary/5 hover:border-primary/30 shadow-sm">
                    <Plus size={16} /> Add Expression
                </button>
                <div className="font-mono text-[10px] bg-muted/30 border border-border/50 p-2 rounded-lg flex justify-between items-center opacity-70 hover:opacity-100 transition-opacity">
                    <div className="flex items-center gap-2 font-bold whitespace-nowrap text-foreground/70">
                        <Terminal size={12} /> Output
                    </div>
                    <div className="truncate max-w-[200px] text-right text-muted-foreground" title={debugInfo}>{debugInfo}</div>
                </div>
            </div>
            </>
            )}
        </div>
    );
};