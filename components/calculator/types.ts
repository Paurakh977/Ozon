
import React from "react";

declare global {
    interface Window {
        Desmos: any;
    }
    namespace JSX {
        interface IntrinsicElements {
            'math-field': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
                'virtual-keyboard-mode'?: 'auto' | 'manual' | 'onfocus' | 'off';
                'read-only'?: boolean;
                'smart-fence'?: string;
                ref?: React.Ref<HTMLElement>;
                value?: string;
            };
        }
    }
}

// Visibility modes for expressions with multiple curves (derivatives, integrals)
// - 'all': Show all curves (parent + operated)
// - 'parent': Show only the parent function curve
// - 'operated': Show only the derivative/integral curve
// - 'none': Hide all curves
export type VisibilityMode = 'all' | 'parent' | 'operated' | 'none';

export interface MathExpression {
    id: string;
    latex: string;
    result?: string;
    color: string;
    visible: boolean; // Simple show/hide for basic expressions
    visibilityMode: VisibilityMode; // Granular control for multi-curve expressions
}
