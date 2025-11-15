/**
 * EdgeCase Color Palette System
 * Pre-designed color pairs for client type badges and cards
 */

const COLOR_PALETTE = {
    green: { name: 'Green', bg: '#D1F0E8', badge: '#00AA88', text: '#1F2937' },
    blue: { name: 'Blue', bg: '#DBEAFE', badge: '#3B82F6', text: '#1F2937' },
    purple: { name: 'Purple', bg: '#E9D5FF', badge: '#A855F7', text: '#1F2937' },
    pink: { name: 'Pink', bg: '#FCE7F3', badge: '#EC4899', text: '#1F2937' },
    yellow: { name: 'Yellow', bg: '#FEF3C7', badge: '#F59E0B', text: '#1F2937' },
    orange: { name: 'Orange', bg: '#FFEDD5', badge: '#F97316', text: '#1F2937' },
    teal: { name: 'Teal', bg: '#CCFBF1', badge: '#14B8A6', text: '#1F2937' },
    gray: { name: 'Gray', bg: '#F3F4F6', badge: '#6B7280', text: '#1F2937' }
};

/**
 * Get colors for a given palette name
 * @param {string} colorKey - Key from COLOR_PALETTE (e.g., 'green', 'blue')
 * @returns {object} Color object with bg, badge, and text properties
 */
function getColors(colorKey) {
    return COLOR_PALETTE[colorKey] || COLOR_PALETTE.green;
}

/**
 * Get background color for a palette name
 * @param {string} colorKey - Key from COLOR_PALETTE
 * @returns {string} Hex color code for background
 */
function getBackgroundColor(colorKey) {
    return getColors(colorKey).bg;
}

/**
 * Get badge color for a palette name
 * @param {string} colorKey - Key from COLOR_PALETTE
 * @returns {string} Hex color code for badge
 */
function getBadgeColor(colorKey) {
    return getColors(colorKey).badge;
}

/**
 * Get text color for a palette name (always dark gray for readability)
 * @param {string} colorKey - Key from COLOR_PALETTE
 * @returns {string} Hex color code for text
 */
function getTextColor(colorKey) {
    return getColors(colorKey).text;
}
