/**
 * Pure geometry of the subtitle box. The position is stored as fractions of the
 * container so it survives resizing and fullscreen.
 * centerXFraction: horizontal centre of the box / container width.
 * bottomYFraction: BOTTOM edge of the box / container height (measured from the top).
 * @typedef {{centerXFraction: number, bottomYFraction: number}} OverlayPosition
 */

/** @type {OverlayPosition} */
export const DEFAULT_OVERLAY_POSITION = { centerXFraction: 0.5, bottomYFraction: 0.86 };

/** Limits a value to [low, high]; when the range is empty or inverted the fallback wins. */
function clampWithin(value, low, high, fallback) {
  if (!(low <= high)) return fallback;
  return Math.min(high, Math.max(low, value));
}

/**
 * Turns a centre and a bottom edge in pixels into clamped fractions,
 * so that the whole box stays inside the container.
 */
function fractionsFromPixels(centerX, bottomY, { boxWidth, boxHeight, containerWidth, containerHeight }) {
  if (!(containerWidth > 0) || !(containerHeight > 0)) {
    return { ...DEFAULT_OVERLAY_POSITION };
  }
  const halfWidth = boxWidth / 2;
  // A box wider than the container is centred; a taller one sits on the bottom edge.
  const clampedCenterX = clampWithin(
    centerX,
    halfWidth,
    containerWidth - halfWidth,
    containerWidth / 2,
  );
  const clampedBottomY = clampWithin(bottomY, boxHeight, containerHeight, containerHeight);
  return {
    centerXFraction: clampedCenterX / containerWidth,
    bottomYFraction: clampedBottomY / containerHeight,
  };
}

/**
 * Pulls a position back so the whole box is visible in the container.
 * @param {OverlayPosition} position
 * @param {{boxWidth: number, boxHeight: number, containerWidth: number, containerHeight: number}} sizes
 * @returns {OverlayPosition}
 */
export function clampOverlayPosition(position, sizes) {
  const { containerWidth, containerHeight } = sizes;
  return fractionsFromPixels(
    position.centerXFraction * containerWidth,
    position.bottomYFraction * containerHeight,
    sizes,
  );
}

/**
 * Position for a box dragged by a point inside it.
 * All coordinates are pixels relative to the container's top-left corner;
 * the grab offset is the grab point measured from the box's top-left corner.
 * @param {{pointerX: number, pointerY: number, grabOffsetX: number, grabOffsetY: number,
 *   boxWidth: number, boxHeight: number, containerWidth: number, containerHeight: number}} drag
 * @returns {OverlayPosition}
 */
export function positionFromDrag(drag) {
  const { pointerX, pointerY, grabOffsetX, grabOffsetY, boxWidth, boxHeight } = drag;
  const boxLeft = pointerX - grabOffsetX;
  const boxTop = pointerY - grabOffsetY;
  return fractionsFromPixels(boxLeft + boxWidth / 2, boxTop + boxHeight, drag);
}
