
import { useEffect, useRef, useState } from "react";

export const useGraphEngine = (resolvedTheme: string | undefined) => {
    const calculatorRef = useRef<HTMLDivElement>(null);
    const calculatorInstance = useRef<any>(null);
    const [libLoaded, setLibLoaded] = useState(false);

    // 1. MathLive Configuration
    useEffect(() => {
        if (typeof window !== 'undefined') {
            import("mathlive").then((ml) => {
                // @ts-ignore
                ml.MathfieldElement.fontsDirectory = "https://unpkg.com/mathlive@0.108.2/dist/fonts";
                // @ts-ignore
                ml.MathfieldElement.soundsDirectory = null;
                
                // Store original menuItems getter to patch it
                const MathfieldElement = ml.MathfieldElement as any;
                
                // Try to set a custom menu items filter globally
                // @ts-ignore
                if (MathfieldElement.prototype) {
                    const originalMenuItemsDescriptor = Object.getOwnPropertyDescriptor(
                        MathfieldElement.prototype, 'menuItems'
                    );
                    
                    if (originalMenuItemsDescriptor && originalMenuItemsDescriptor.get) {
                        const originalGetter = originalMenuItemsDescriptor.get;
                        const unwantedIds = ['color', 'background-color', 'variant', 'mode'];
                        
                        const filterItems = (items: any[]): any[] => {
                            if (!Array.isArray(items)) return items;
                            return items
                                .filter((item: any) => {
                                    if (!item || item.type === 'divider') return true;
                                    const itemId = (item.id || '').toLowerCase();
                                    return !unwantedIds.includes(itemId);
                                })
                                .map((item: any) => {
                                    if (item?.submenu && Array.isArray(item.submenu)) {
                                        return { ...item, submenu: filterItems(item.submenu) };
                                    }
                                    return item;
                                });
                        };
                        
                        Object.defineProperty(MathfieldElement.prototype, 'menuItems', {
                            get: function() {
                                const items = originalGetter.call(this);
                                return filterItems(items);
                            },
                            set: originalMenuItemsDescriptor.set,
                            configurable: true,
                            enumerable: true
                        });
                    }
                }
                
                // Fallback: Use MutationObserver to hide menu items based on text content
                const hideUnwantedMenuItems = () => {
                    const menus = document.querySelectorAll('.ui-menu, .ui-menu-container, .ML__menu, [role="menu"]');
                    menus.forEach((menu) => {
                        const items = menu.querySelectorAll('li, [role="menuitem"]');
                        items.forEach((item) => {
                            const el = item as HTMLElement;
                            // Get the direct label text, not including submenu text
                            const label = el.querySelector(':scope > .label, :scope > span.label');
                            const labelText = (label?.textContent || '').trim().toLowerCase();
                            
                            // Match exact menu item names
                            const unwantedLabels = ['color', 'background', 'font style', 'mode'];
                            if (unwantedLabels.includes(labelText)) {
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
                        hideUnwantedMenuItems();
                        setTimeout(hideUnwantedMenuItems, 0);
                        setTimeout(hideUnwantedMenuItems, 20);
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
