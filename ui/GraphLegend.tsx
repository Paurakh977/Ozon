
import React from "react";
import { Calculator as CalcIcon, PanelLeftClose } from "lucide-react";
import { MathExpression } from "../components/calculator/types";
import { computeSymbolicDerivative, computeSymbolicIntegral } from "../utils/symbolic-math";

interface GraphLegendProps {
    expressions: MathExpression[];
    legendOpen: boolean;
    setLegendOpen: (open: boolean) => void;
}

export const GraphLegend: React.FC<GraphLegendProps> = ({ expressions, legendOpen, setLegendOpen }) => {

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

        // Fix Logarithm bases
        clean = clean.replace(/\\log_(\d+)/g, "\\log_{$1}");

        // ==========================================
        //      DERIVATIVE PARSING WITH SYMBOLIC RESULT
        // ==========================================
        const derivRegex = /^\\frac\s*\{\s*d(\^\{?([0-9]+)\}?)?\s*\}\s*\{\s*d(\\[a-zA-Z]+|[a-zA-Z])(\^\{?([0-9]+)\}?)?\s*\}\s*(.+)$/;
        const derivMatch = clean.match(derivRegex);
        if (derivMatch) {
            const order = derivMatch[2] ? parseInt(derivMatch[2]) : 1;
            const variable = derivMatch[3] ? derivMatch[3].replace('\\', '') : 'x';

            // Extract the function being derived
            let content = derivMatch[6];
            const barIndex = content.lastIndexOf("|_{");
            if (barIndex !== -1 && content.trim().endsWith("}")) {
                content = content.substring(0, barIndex).trim();
            }

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
            const boundsRegex = /^\\int(?:_\{([^}]*)\}|_(-?[0-9a-zA-Z\\]+))?(?:\^\{([^}]*)\}|\^(-?[0-9a-zA-Z\\]+))?/;
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
        <div className={`absolute top-4 right-4 bg-card/90 backdrop-blur-sm rounded-lg shadow-md border text-xs z-10 select-none transition-all duration-200 overflow-hidden flex flex-col ${legendOpen ? 'max-h-[60vh] w-[220px]' : 'w-auto h-auto'}`}>
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
                        return (
                            <div key={expr.id} className="flex flex-col gap-1.5">
                                <div className="flex items-center gap-2 font-medium opacity-90 text-[10px] uppercase tracking-wider text-muted-foreground">
                                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: expr.color }}></div>
                                    <span>Expr {i + 1}</span>
                                </div>
                                <div className="grid grid-cols-[24px_1fr] gap-x-2 gap-y-2 items-center pl-1">
                                    {items.map((item: any, idx: number) => (
                                        <React.Fragment key={idx}>
                                            <div className="flex items-center justify-center">
                                                {item.type === 'dotted' && (
                                                    <div className="w-full border-t-[3px] border-dotted" style={{ borderColor: expr.color }}></div>
                                                )}
                                                {item.type === 'solid' && (
                                                    <div className="w-full h-0.5" style={{ backgroundColor: expr.color }}></div>
                                                )}
                                                {item.type === 'area' && (
                                                    <div className="w-full h-3 rounded-[2px] opacity-40 border border-transparent" style={{ backgroundColor: expr.color }}></div>
                                                )}
                                            </div>
                                            <div className="min-w-0">
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
