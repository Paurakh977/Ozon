
// @ts-ignore - nerdamer doesn't have proper types
import nerdamer from 'nerdamer';
import 'nerdamer/Calculus';
import 'nerdamer/Algebra';
import 'nerdamer/Solve';
import { latexToNerdamer, nerdamerToLatex } from './latex-parser';

/**
 * Compute symbolic derivative using nerdamer
 */
export const computeSymbolicDerivative = (expression: string, variable: string = 'x', order: number = 1): string | null => {
    try {
        const nerdamerExpr = latexToNerdamer(expression);

        let result = nerdamer(nerdamerExpr);

        for (let i = 0; i < order; i++) {
            result = nerdamer.diff(result, variable);
        }

        const tex = nerdamerToLatex(result);

        // If result still contains 'diff' or 'integrate', nerdamer couldn't evaluate it
        const raw = result.toString();
        if (/\bdiff\b/.test(raw) || /\bintegrate\b/.test(raw)) {
            return null;
        }

        return tex;
    } catch {
        return null;
    }
};

/**
 * Compute symbolic integral using nerdamer
 */
export const computeSymbolicIntegral = (expression: string, variable: string = 'x'): string | null => {
    try {
        const nerdamerExpr = latexToNerdamer(expression);

        const result = nerdamer.integrate(nerdamerExpr, variable);
        const tex = nerdamerToLatex(result);

        // If result still contains 'integrate' or '\int', nerdamer couldn't fully evaluate it
        const raw = result.toString();
        if (/\bintegrate\b/.test(raw) || /\bint\b/.test(raw) || tex.includes('\\int')) {
            return null;
        }

        return tex;
    } catch {
        return null;
    }
};
