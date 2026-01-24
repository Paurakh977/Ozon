
import { useEffect, useRef, useState } from "react";

export const useGraphEngine = (resolvedTheme: string | undefined) => {
    const calculatorRef = useRef<HTMLDivElement>(null);
    const calculatorInstance = useRef<any>(null);
    const [libLoaded, setLibLoaded] = useState(false);

    // Custom inline shortcuts for calculus operations
    // These are defined outside useEffect to avoid recreation
    const customInlineShortcuts = {
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

    // 1. MathLive Configuration
    useEffect(() => {
        if (typeof window !== 'undefined') {
            import("mathlive").then((ml) => {
                // @ts-ignore
                ml.MathfieldElement.fontsDirectory = "https://unpkg.com/mathlive@0.108.2/dist/fonts";
                // @ts-ignore
                ml.MathfieldElement.soundsDirectory = null;
                
                // Configure global inline shortcuts by extending the default shortcuts
                // This ensures our calculus shortcuts work across all math-field elements
                // @ts-ignore - MathfieldElement has inlineShortcuts property
                const defaultShortcuts = ml.MathfieldElement.inlineShortcuts || {};
                // @ts-ignore
                ml.MathfieldElement.inlineShortcuts = {
                    ...defaultShortcuts,
                    ...customInlineShortcuts,
                };
                
                // Use CSS-only approach to hide unwanted menu items
                // This is safer and doesn't interfere with menu functionality
                const style = document.createElement('style');
                style.textContent = `
                    /* Hide unwanted MathLive menu items by their data-command attribute or label */
                    .ML__menu [data-command="color"],
                    .ML__menu [data-command="background-color"],
                    .ML__menu [data-command="variant"],
                    .ML__menu [data-command="mode"],
                    .ML__menu-item:has(> .label:is([data-l10n-id="menu.color"], [data-l10n-id="menu.background-color"])),
                    .ui-menu li[data-command="color"],
                    .ui-menu li[data-command="background-color"],
                    .ui-menu li[data-command="variant"],
                    .ui-menu li[data-command="mode"] {
                        display: none !important;
                    }
                `;
                document.head.appendChild(style);
                
                // Fallback: Use MutationObserver to hide menu items based on text content
                // This catches any items the CSS might miss
                const hideUnwantedMenuItems = () => {
                    const menus = document.querySelectorAll('.ui-menu, .ui-menu-container, .ML__menu, [role="menu"]');
                    menus.forEach((menu) => {
                        const items = menu.querySelectorAll('li, [role="menuitem"], .ML__menu-item');
                        items.forEach((item) => {
                            const el = item as HTMLElement;
                            // Get the direct label text, not including submenu text
                            const label = el.querySelector(':scope > .label, :scope > span.label, :scope > .ML__menu-item-label');
                            const labelText = (label?.textContent || el.textContent || '').trim().toLowerCase();
                            
                            // Match menu item names that should be hidden
                            const unwantedLabels = ['color', 'background', 'font style', 'mode'];
                            // Only hide if it's an exact match (not partial like "factorial")
                            if (unwantedLabels.some(unwanted => labelText === unwanted)) {
                                el.style.display = 'none';
                            }
                        });
                    });
                };
                
                const observer = new MutationObserver((mutations) => {
                    let shouldCheck = false;
                    for (const mutation of mutations) {
                        for (const node of Array.from(mutation.addedNodes)) {
                            if (node instanceof HTMLElement) {
                                if (node.classList?.contains('ui-menu') ||
                                    node.classList?.contains('ui-menu-container') ||
                                    node.classList?.contains('ML__menu') ||
                                    node.matches?.('[role="menu"]') ||
                                    node.querySelector?.('.ui-menu, .ML__menu, [role="menu"]')) {
                                    shouldCheck = true;
                                    break;
                                }
                            }
                        }
                        if (shouldCheck) break;
                    }
                    if (shouldCheck) {
                        // Use requestAnimationFrame for better timing
                        requestAnimationFrame(() => {
                            hideUnwantedMenuItems();
                        });
                    }
                });
                
                observer.observe(document.body, { childList: true, subtree: true });
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
        script.src = "https://www.desmos.com/api/v1.11/calculator.js?apiKey=dcb31709b452b1cf9dc26972add0fda6";
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

        // We can't init expressions here easily because they are in the other hook.
        // The other hook should handle initial processing if needed, 
        // or we rely on useEffect there.

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

    return { calculatorRef, calculatorInstance, libLoaded };
};
