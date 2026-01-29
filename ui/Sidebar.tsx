
import React, { useRef, useCallback, useEffect, useState } from "react";
import { Plus, Trash2, Terminal, Eye, EyeOff, ChevronDown, Play, Pause } from "lucide-react";
import { MathExpression, VisibilityMode } from "../components/calculator/types";

// Custom inline shortcuts for calculus operations
// These shortcuts allow quick entry of calculus expressions by typing keywords
const CUSTOM_INLINE_SHORTCUTS = {
    // ==========================================
    // INTEGRAL SHORTCUTS
    // ==========================================
    // Indefinite integral with dx (no thin space - required for proper parsing)
    'int': '\\int #?\\mathrm{d}x',
    // Definite integral with bounds
    'dint': '\\int_{#?}^{#?}#?\\mathrm{d}x',
    
    // ==========================================
    // DERIVATIVE SHORTCUTS
    // ==========================================
    // First derivative with respect to x
    'ddx': '\\frac{d}{dx}#?',
    // First derivative with respect to y
    'ddy': '\\frac{d}{dy}#?',
    // Second derivative
    'd2dx2': '\\frac{d^{2}}{dx^{2}}#?',
    // nth derivative at a point (user specifies the order and evaluation point)
    'dndxn': '\\frac{d^{#?}}{dx^{#?}}#?\\bigm|_{x=#?}',
    // General derivative at a point: d/d? □|_{?=?}
    'deriv': '\\frac{d}{d#?}#?\\bigm|_{#?=#?}',
    
    // ==========================================
    // PARTIAL DERIVATIVE SHORTCUTS
    // ==========================================
    // Partial derivative with respect to x
    'pdx': '\\frac{\\partial}{\\partial x}#?',
    // Partial derivative with respect to y  
    'pdy': '\\frac{\\partial}{\\partial y}#?',
    
    // ==========================================
    // LIMIT SHORTCUTS
    // ==========================================
    // General limit: lim_{? → ?} □
    'lim': '\\lim_{#?\\to #?}#?',
    // Limit with x approaching something
    'limx': '\\lim_{x\\to #?}#?',
    
    // ==========================================
    // SUMMATION SHORTCUTS
    // ==========================================
    // General summation
    'sum': '\\sum_{#?}^{#?}#?',
    // Summation with n as index
    'sumn': '\\sum_{n=#?}^{#?}#?',
};

// Helper function to invert colors for dark mode (Desmos-style)
// Desmos rotates hue by 180° (complementary color) for dark mode
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
    
    // Rotate hue 180°
    let newH = (h + 0.5) % 1;
    let newL = Math.max(0.4, Math.min(0.8, l + 0.1));
    
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
    updateSliderBounds: (id: string, min: string, max: string, step: string) => void;
    setExpressionPlaying: (id: string, playing: boolean) => void;
    debugInfo: string;
    resolvedTheme: string | undefined;
}

// Helper to detect if expression is a multi-curve type (derivative or integral)
const isMultiCurveExpression = (latex: string): boolean => {
    if (!latex) return false;
    // Normalize the latex for detection - same as processExpression cleaning
    const clean = latex
        .replace(/\\mathrm\{d\}/g, "d")
        .replace(/\\differentialD/g, "d")
        .replace(/\\dfrac/g, "\\frac") // Handle \dfrac -> \frac
        .replace(/\\bigm/g, "") // Remove \bigm
        .trim();
    
    // Derivative detection: \frac{d...}{d...} pattern
    // Matches: \frac{d}{dx}, \frac{d^2}{dx^2}, \frac{d^{2}}{dx^{2}}, etc.
    // The pattern allows for optional spaces and both d^2 and d^{2} formats
    const derivRegex = /^\\frac\s*\{\s*d(\^\{?[0-9]+\}?)?\s*\}\s*\{\s*d/;
    const isDerivative = derivRegex.test(clean);
    
    // Integral: starts with \int
    const isIntegral = clean.startsWith("\\int");
    
    return isDerivative || isIntegral;
};

// Get visibility icon based on mode
const getVisibilityIcon = (mode: VisibilityMode, visible: boolean) => {
    if (!visible || mode === 'none') return <EyeOff size={16} />;
    return <Eye size={16} />;
};

export const Sidebar: React.FC<SidebarProps> = ({
    expressions,
    handleColorChange,
    handleInput,
    removeExpr,
    addExpr,
    toggleVisibility,
    setVisibilityMode,
    updateSliderBounds,
    setExpressionPlaying,
    debugInfo,
    resolvedTheme
}) => {
    const mathFieldRefs = useRef<Map<string, HTMLElement>>(new Map());
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    const prevExpressionsLength = useRef(expressions.length);

    // Auto-focus new expressions
    useEffect(() => {
        if (expressions.length > prevExpressionsLength.current) {
            const lastExpr = expressions[expressions.length - 1];
            // Small timeout to ensure DOM is ready
            setTimeout(() => {
                const el = mathFieldRefs.current.get(lastExpr.id);
                if (el && typeof (el as any).focus === 'function') {
                    (el as any).focus();
                }
            }, 100);
        }
        prevExpressionsLength.current = expressions.length;
    }, [expressions.length]);
    
    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (openMenuId && !(e.target as Element).closest('.visibility-menu-container')) {
                setOpenMenuId(null);
            }
        };
        document.addEventListener('click', handleClickOutside);
        return () => document.removeEventListener('click', handleClickOutside);
    }, [openMenuId]);
    
    // Handle focus management for virtual keyboard and configure inline shortcuts
    const handleMathFieldRef = useCallback((id: string, el: HTMLElement | null) => {
        if (el) {
            mathFieldRefs.current.set(id, el);
            
            const mf = el as any;
            
            // Configure inline shortcuts
            if (mf.inlineShortcuts !== undefined) {
                const existingShortcuts = mf.inlineShortcuts || {};
                mf.inlineShortcuts = {
                    ...existingShortcuts,
                    ...CUSTOM_INLINE_SHORTCUTS,
                };
            }
            
            // Fix Bug 1: Remove existing keydown listener before adding new one
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
            
            // Handle focus
            el.addEventListener('focus', () => {
                if (typeof mf.focus === 'function') {
                    mf.focus();
                }
            });
            
            // Handle virtual keyboard
            el.addEventListener('virtual-keyboard-toggle', () => {
                setTimeout(() => {
                    if (typeof mf.focus === 'function') {
                        mf.focus();
                    }
                }, 0);
            });
        } else {
            mathFieldRefs.current.delete(id);
        }
    }, [addExpr]); // Depend on addExpr so new listener uses fresh closure
    
    return (
        <div className="p-3 flex-1 overflow-y-auto overflow-x-hidden space-y-2">
            {expressions.map((expr, i) => {
                const isDark = resolvedTheme === 'dark';
                const displayColor = invertColorForDarkMode(expr.color, isDark);
                const isMenuOpen = openMenuId === expr.id;

                // Fix Bug 2 & Slider Detection
                // Safeguard against undefined/null expr.latex
                const safeLatex = typeof expr.latex === 'string' ? expr.latex : '';
                const sliderMatch = safeLatex.match(/^([a-zA-Z](?:_\{?[a-zA-Z0-9]+\}?)?)\s*=\s*([-+]?[0-9]*\.?[0-9]+)$/);
                const isSlider = !!sliderMatch;
                const sliderVal = isSlider ? parseFloat(sliderMatch![2]) : 0;
                const sliderVar = isSlider ? sliderMatch![1] : '';
                
                // Slider bounds
                const min = expr.sliderBounds?.min ?? "-10";
                const max = expr.sliderBounds?.max ?? "10";
                const step = expr.sliderBounds?.step ?? "";

                return (
                <div key={expr.id} className={`group relative flex flex-col gap-1 bg-muted/30 p-2 rounded-lg border border-transparent focus-within:border-primary/50 focus-within:bg-muted/50 transition-all ${!expr.visible ? 'opacity-60' : ''} ${isMenuOpen ? 'z-50' : ''}`}>
                    
                    <div className="flex items-center gap-2">
                        {/* Left side: Number + Color picker stacked */}
                        <div className="flex flex-col items-center gap-1 shrink-0">
                            <div className="text-xs font-mono opacity-40 select-none w-5 text-center">{i + 1}</div>
                            {/* Color picker */}
                            <div className="relative">
                                <input
                                    type="color"
                                    value={expr.color}
                                    onChange={(e) => handleColorChange(expr.id, e.target.value)}
                                    className="w-5 h-5 rounded-full overflow-hidden p-0 border-0 cursor-pointer opacity-0 absolute inset-0 z-10"
                                    title="Change Graph Color"
                                />
                                <div 
                                    className="w-5 h-5 rounded-full cursor-pointer border border-border/50 transition-opacity"
                                    style={{ backgroundColor: displayColor, opacity: expr.visible ? 1 : 0.4 }}
                                    title="Change Graph Color"
                                />
                            </div>
                        </div>
                        
                        {/* Visibility toggle button - with dropdown for multi-curve expressions */}
                        <div className="relative shrink-0 visibility-menu-container">
                            {isMultiCurveExpression(safeLatex) ? (
                                <>
                                    <button 
                                        onClick={() => setOpenMenuId(openMenuId === expr.id ? null : expr.id)}
                                        className={`flex items-center gap-0.5 p-1 rounded transition-all hover:bg-muted/50 ${expr.visible ? 'text-muted-foreground/70 hover:text-primary' : 'text-muted-foreground/40 hover:text-muted-foreground'}`}
                                        title="Visibility options"
                                    >
                                        {getVisibilityIcon(expr.visibilityMode, expr.visible)}
                                        <ChevronDown size={12} className={`transition-transform ${openMenuId === expr.id ? 'rotate-180' : ''}`} />
                                    </button>
                                    {/* Dropdown menu for visibility options */}
                                    {openMenuId === expr.id && (
                                        <div className="absolute top-full left-0 mt-1 z-50 bg-popover border border-border rounded-lg shadow-lg py-1 min-w-[140px]">
                                            <button
                                                onClick={() => { setVisibilityMode(expr.id, 'all'); setOpenMenuId(null); }}
                                                className={`w-full px-3 py-1.5 text-left text-sm hover:bg-muted/50 transition-colors flex items-center gap-2 ${expr.visibilityMode === 'all' ? 'text-primary font-medium' : 'text-foreground'}`}
                                            >
                                                <Eye size={14} /> Show All
                                            </button>
                                            <button
                                                onClick={() => { setVisibilityMode(expr.id, 'parent'); setOpenMenuId(null); }}
                                                className={`w-full px-3 py-1.5 text-left text-sm hover:bg-muted/50 transition-colors flex items-center gap-2 ${expr.visibilityMode === 'parent' ? 'text-primary font-medium' : 'text-foreground'}`}
                                            >
                                                <Eye size={14} /> Parent Only
                                            </button>
                                            <button
                                                onClick={() => { setVisibilityMode(expr.id, 'operated'); setOpenMenuId(null); }}
                                                className={`w-full px-3 py-1.5 text-left text-sm hover:bg-muted/50 transition-colors flex items-center gap-2 ${expr.visibilityMode === 'operated' ? 'text-primary font-medium' : 'text-foreground'}`}
                                            >
                                                <Eye size={14} /> {safeLatex.startsWith("\\int") ? "Integral Only" : "Derivative Only"}
                                            </button>
                                            <button
                                                onClick={() => { setVisibilityMode(expr.id, 'none'); setOpenMenuId(null); }}
                                                className={`w-full px-3 py-1.5 text-left text-sm hover:bg-muted/50 transition-colors flex items-center gap-2 ${expr.visibilityMode === 'none' ? 'text-primary font-medium' : 'text-foreground'}`}
                                            >
                                                <EyeOff size={14} /> Hide All
                                            </button>
                                        </div>
                                    )}
                                </>
                            ) : (
                                <button 
                                    onClick={() => toggleVisibility(expr.id)}
                                    className={`p-1 rounded transition-all hover:bg-muted/50 ${expr.visible ? 'text-muted-foreground/70 hover:text-primary' : 'text-muted-foreground/40 hover:text-muted-foreground'}`}
                                    title={expr.visible ? "Hide graph" : "Show graph"}
                                >
                                    {expr.visible ? <Eye size={16} /> : <EyeOff size={16} />}
                                </button>
                            )}
                        </div>

                        <div className="flex-1 min-w-0 flex flex-col">
                            <div className="overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden" style={{ scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' }}>
                                {/* @ts-ignore */}
                                <math-field
                                    ref={(el: HTMLElement | null) => handleMathFieldRef(expr.id, el)}
                                    smart-fence="on"
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
                                    style={{
                                        minWidth: '100%',
                                        width: 'fit-content',
                                        backgroundColor: 'transparent',
                                        outline: 'none',
                                        fontSize: '1.1rem',
                                        '--caret-color': resolvedTheme === 'dark' ? '#fff' : '#1a1a1a',
                                        '--smart-fence-color': resolvedTheme === 'dark' ? '#fff' : '#1a1a1a',
                                        '--smart-fence-opacity': '1',
                                        '--selection-background-color': resolvedTheme === 'dark' ? 'rgba(120, 100, 255, 0.3)' : 'rgba(80, 70, 229, 0.2)',
                                        '--selection-color': resolvedTheme === 'dark' ? '#fff' : '#1a1a1a',
                                        color: resolvedTheme === 'dark' ? '#fff' : '#1a1a1a'
                                    } as React.CSSProperties}
                                >
                                    {safeLatex}
                                </math-field>
                            </div>
                        </div>

                        {/* Show result if exists AND NOT a slider (sliders show value in input) */}
                        {expr.result && !isSlider && (
                            <div className="flex items-center justify-center px-1.5 py-0.5 bg-primary/10 text-primary font-mono text-xs sm:text-sm rounded select-all whitespace-nowrap max-w-[40%] overflow-hidden text-ellipsis">
                                = {expr.result}
                            </div>
                        )}
                        <button onClick={() => removeExpr(expr.id)} className="shrink-0 opacity-100 sm:opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-red-500 transition-all">
                            <Trash2 size={14} />
                        </button>
                    </div>

                    {/* Advanced Slider UI */}
                    {isSlider && (
                        <div className="pl-8 pr-2 pb-2 pt-1 flex flex-col gap-2 animate-in fade-in slide-in-from-top-1">
                            {/* Slider Row: Play | Range | Max */}
                            <div className="flex items-center gap-3">
                                <button
                                    onClick={() => setExpressionPlaying(expr.id, !expr.isPlaying)}
                                    className={`p-1 rounded-full border transition-colors ${expr.isPlaying ? 'bg-primary text-primary-foreground border-primary' : 'bg-transparent text-muted-foreground border-border hover:text-foreground'}`}
                                >
                                    {expr.isPlaying ? <Pause size={12} fill="currentColor" /> : <Play size={12} fill="currentColor" />}
                                </button>
                                
                                <div className="flex-1 flex items-center gap-2">
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
                                        className="flex-1 h-1.5 bg-muted rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary hover:[&::-webkit-slider-thumb]:scale-110 transition-all"
                                    />
                                </div>
                            </div>
                            
                             {/* Bounds Inputs Row */}
                            <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
                                <div className="flex items-center gap-1">
                                    <input
                                        type="text"
                                        value={min}
                                        onChange={(e) => updateSliderBounds(expr.id, e.target.value, max, step)}
                                        className="w-12 bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:outline-none text-center transition-colors"
                                        placeholder="Min"
                                    />
                                    <span>≤ {sliderVar} ≤</span>
                                     <input
                                        type="text"
                                        value={max}
                                        onChange={(e) => updateSliderBounds(expr.id, min, e.target.value, step)}
                                        className="w-12 bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:outline-none text-center transition-colors"
                                        placeholder="Max"
                                    />
                                </div>
                                <div className="flex items-center gap-1">
                                    <span className="opacity-50">step:</span>
                                    <input
                                        type="text"
                                        value={step}
                                        onChange={(e) => updateSliderBounds(expr.id, min, max, e.target.value)}
                                        className="w-10 bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:outline-none text-center transition-colors"
                                        placeholder="auto"
                                    />
                                </div>
                            </div>
                        </div>
                    )}
                    
                    {/* Missing Variables Sliders */}
                    {expr.missingVariables && expr.missingVariables.length > 0 && (
                        <div className="flex flex-wrap gap-2 pl-8 pr-2 pb-1 items-center animate-in fade-in slide-in-from-top-1 duration-200">
                            <span className="text-xs text-muted-foreground italic font-mono">add slider:</span>
                            <button
                                onClick={() => expr.missingVariables?.forEach(v => addExpr(`${v}=1`))}
                                className="text-xs px-2 py-0.5 border border-primary/20 bg-primary/5 text-primary rounded-md hover:bg-primary/10 transition-colors font-mono"
                            >
                                all
                            </button>
                            {expr.missingVariables.map(v => (
                                <button
                                    key={v}
                                    onClick={() => addExpr(`${v}=1`)}
                                    className="text-xs px-2 py-0.5 border border-muted bg-muted/30 text-muted-foreground rounded-md hover:bg-muted/50 hover:text-foreground transition-colors font-mono"
                                >
                                    {v}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            );
            })}

            <div className="p-3 border-t bg-muted/10 space-y-2 mt-4">

                <button onClick={addExpr} className="w-full py-2 border border-dashed border-border rounded-lg flex items-center justify-center gap-2 text-sm text-muted-foreground hover:text-primary transition-all hover:bg-muted/50 hover:border-primary/30">
                    <Plus size={14} /> Add Expression
                </button>
                <div className="font-mono text-[10px] bg-black/5 dark:bg-white/5 p-2 rounded flex justify-between items-center opacity-50 hover:opacity-100 transition-opacity">
                    <div className="flex items-center gap-2 font-bold whitespace-nowrap">
                        <Terminal size={10} /> Output
                    </div>
                    <div className="truncate max-w-[200px] text-right">{debugInfo}</div>
                </div>
            </div>
        </div>
    );
};
