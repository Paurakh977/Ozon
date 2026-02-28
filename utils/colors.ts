
export const DEFAULT_COLORS = ["#c74440", "#2d70b3", "#388c46", "#6042a6", "#fa7e19", "#000000"];
export const getRandomColor = () => DEFAULT_COLORS[Math.floor(Math.random() * DEFAULT_COLORS.length)];
export const getNextColor = (prevColor?: string): string => {
    if (!prevColor) return DEFAULT_COLORS[0];
    const idx = DEFAULT_COLORS.indexOf(prevColor);
    return DEFAULT_COLORS[(idx + 1) % DEFAULT_COLORS.length];
};
