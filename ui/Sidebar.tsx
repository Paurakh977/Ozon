
import React, { useRef, useCallback, useEffect } from "react";
import { Plus, Trash2, Terminal } from "lucide-react";
import { MathExpression } from "../components/calculator/types";

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
    debugInfo: string;
    resolvedTheme: string | undefined;
}

export const Sidebar: React.FC<SidebarProps> = ({
    expressions,
    handleColorChange,
    handleInput,
    removeExpr,
    addExpr,
    debugInfo,
    resolvedTheme
}) => {
    const mathFieldRefs = useRef<Map<string, HTMLElement>>(new Map());
    
    // Handle focus management for virtual keyboard
    const handleMathFieldRef = useCallback((id: string, el: HTMLElement | null) => {
        if (el) {
            mathFieldRefs.current.set(id, el);
            
            // Add focus event handler to ensure proper keyboard behavior
            el.addEventListener('focus', () => {
                // Ensure the math field is properly focused when clicked
                if (el && typeof (el as any).focus === 'function') {
                    (el as any).focus();
                }
            });
            
            // Handle virtual keyboard toggle - ensure focus stays in field
            el.addEventListener('virtual-keyboard-toggle', (e: any) => {
                // When virtual keyboard is toggled, ensure the field retains focus
                setTimeout(() => {
                    if (el && typeof (el as any).focus === 'function') {
                        (el as any).focus();
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
                <div key={expr.id} className="group relative flex items-start gap-2 bg-muted/30 p-2 rounded-lg border border-transparent focus-within:border-primary/50 focus-within:bg-muted/50 transition-all">
                    <div className="flex flex-col items-center gap-1 mt-2">
                        <div className="text-xs font-mono opacity-30 select-none w-4 text-center">{i + 1}</div>
                        {/* Show display color as indicator, but keep original in picker */}
                        <div className="relative">
                            <input
                                type="color"
                                value={expr.color}
                                onChange={(e) => handleColorChange(expr.id, e.target.value)}
                                className="w-4 h-4 rounded-full overflow-hidden p-0 border-0 cursor-pointer opacity-0 absolute inset-0"
                                title="Change Graph Color"
                            />
                            <div 
                                className="w-4 h-4 rounded-full cursor-pointer border border-border/50"
                                style={{ backgroundColor: displayColor }}
                                title="Change Graph Color"
                            />
                        </div>
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
                        <div className="flex items-center justify-center px-2 py-0.5 bg-primary/10 text-primary font-mono text-sm rounded select-all whitespace-nowrap self-center">
                            = {expr.result}
                        </div>
                    )}
                    <button onClick={() => removeExpr(expr.id)} className="mt-1 opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-red-500 transition-all">
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
