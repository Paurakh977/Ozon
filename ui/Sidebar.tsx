
import React from "react";
import { Plus, Trash2, Terminal } from "lucide-react";
import { MathExpression } from "../components/calculator/types";

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
    return (
        <div className="p-3 flex-1 overflow-y-auto space-y-2">
            {expressions.map((expr, i) => (
                <div key={expr.id} className="group relative flex items-start gap-2 bg-muted/30 p-2 rounded-lg border border-transparent focus-within:border-primary/50 focus-within:bg-muted/50 transition-all">
                    <div className="flex flex-col items-center gap-1 mt-2">
                        <div className="text-xs font-mono opacity-30 select-none w-4 text-center">{i + 1}</div>
                        <input
                            type="color"
                            value={expr.color}
                            onChange={(e) => handleColorChange(expr.id, e.target.value)}
                            className="w-4 h-4 rounded-full overflow-hidden p-0 border-0 cursor-pointer"
                            title="Change Graph Color"
                        />
                    </div>
                    <div className="flex-1 min-w-0 overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden" style={{ scrollbarWidth: 'none' }}>
                        {/* @ts-ignore */}
                        <math-field
                            smart-fence="on"
                            onInput={(e: any) => handleInput(expr.id, e.target.value)}
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
            ))}

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
