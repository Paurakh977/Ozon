
import React, { useRef, useCallback, useEffect, useState } from "react";
import { Plus, Trash2, Terminal, Eye, EyeOff, ChevronDown } from "lucide-react";
import { MathExpression, VisibilityMode } from "../components/calculator/types";

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
    addExpr: () => void;
    toggleVisibility: (id: string) => void;
    setVisibilityMode: (id: string, mode: VisibilityMode) => void;
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
    debugInfo,
    resolvedTheme
}) => {
    const mathFieldRefs = useRef<Map<string, HTMLElement>>(new Map());
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    
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
    
    // Handle focus management for virtual keyboard
    const handleMathFieldRef = useCallback((id: string, el: HTMLElement | null) => {
        if (el) {
            mathFieldRefs.current.set(id, el);
            
            const mf = el as any;
            
            // Handle focus to ensure cursor is active
            el.addEventListener('focus', () => {
                if (typeof mf.focus === 'function') {
                    mf.focus();
                }
            });
            
            // Handle virtual keyboard toggle - ensure focus stays in field
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
    }, []);
    
    return (
        <div className="p-3 flex-1 overflow-y-auto space-y-2">
            {expressions.map((expr, i) => {
                const isDark = resolvedTheme === 'dark';
                const displayColor = invertColorForDarkMode(expr.color, isDark);
                return (
                <div key={expr.id} className={`group relative flex items-center gap-2 bg-muted/30 p-2 rounded-lg border border-transparent focus-within:border-primary/50 focus-within:bg-muted/50 transition-all ${!expr.visible ? 'opacity-60' : ''}`}>
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
                        {isMultiCurveExpression(expr.latex) ? (
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
                                            <Eye size={14} /> {expr.latex.startsWith("\\int") ? "Integral Only" : "Derivative Only"}
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
                    <div className="flex-1 min-w-0 overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden" style={{ scrollbarWidth: 'none' }}>
                        {/* @ts-ignore */}
                        <math-field
                            ref={(el: HTMLElement | null) => handleMathFieldRef(expr.id, el)}
                            smart-fence="on"
                            virtual-keyboard-mode="onfocus"
                            onInput={(e: any) => handleInput(expr.id, e.target.value)}
                            onFocus={(e: any) => {
                                // Ensure cursor is active when focused
                                const target = e.target;
                                if (target && typeof target.focus === 'function') {
                                    // Small delay to ensure proper activation
                                    requestAnimationFrame(() => {
                                        target.focus();
                                    });
                                }
                            }}
                            onClick={(e: any) => {
                                // Ensure clicking the field activates cursor
                                const target = e.currentTarget;
                                if (target && typeof target.focus === 'function') {
                                    target.focus();
                                }
                            }}
                            value={expr.latex}
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
                            {expr.latex}
                        </math-field>
                    </div>
                    {expr.result && (
                        <div className="flex items-center justify-center px-2 py-0.5 bg-primary/10 text-primary font-mono text-sm rounded select-all whitespace-nowrap">
                            = {expr.result}
                        </div>
                    )}
                    <button onClick={() => removeExpr(expr.id)} className="shrink-0 opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-red-500 transition-all">
                        <Trash2 size={14} />
                    </button>
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
