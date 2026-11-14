import {
  DEFAULT_OVERLAY_POSITION,
  clampOverlayPosition,
  positionFromDrag,
} from '../shared/overlay_position.js';
import { appearanceVariables } from '../shared/player_panel_logic.js';
import { uiTexts } from '../shared/ui_strings.js';
import { DEFAULT_SETTINGS } from './settings_store.js';

/** A pointer movement shorter than this many pixels is a click, not a drag. */
const DRAG_THRESHOLD_PX = 4;

/**
 * A draggable subtitle box over any element that wraps a video.
 * It knows nothing about the text source: it only displays what it is given.
 */
export class OverlayView {
  #container;
  #onPositionChanged;
  #position;
  #boxElement;
  #textElement;
  #labelElement;
  #resizeObserver;
  #isEmpty = true;
  #isHiddenByOwner = false;
  #drag = null;
  #isNextClickSwallowed = false;

  /**
   * @param {{document: Document, containerElement: HTMLElement,
   *   position: import('../shared/overlay_position.js').OverlayPosition|null,
   *   textScale: number, onPositionChanged: (position: object) => void,
   *   appearance?: {textColor: string, backgroundOpacity: number, outline: boolean},
   *   texts?: Record<string, any>, isRightToLeft?: boolean}} options
   */
  constructor({ document, containerElement, position, textScale, onPositionChanged, appearance = DEFAULT_SETTINGS, texts = uiTexts('ru'), isRightToLeft = false }) {
    this.#container = containerElement;
    this.#onPositionChanged = onPositionChanged;
    this.#position = position ?? { ...DEFAULT_OVERLAY_POSITION };

    this.#boxElement = document.createElement('div');
    this.#boxElement.className = 'lingotube-overlay';
    if (isRightToLeft) this.#boxElement.dir = 'rtl';
    this.#textElement = document.createElement('div');
    this.#textElement.className = 'lingotube-overlay-text';
    this.#labelElement = document.createElement('div');
    this.#labelElement.className = 'lingotube-overlay-label';
    this.#labelElement.textContent = texts.approximateTiming;
    this.#labelElement.hidden = true;
    this.#boxElement.append(this.#textElement, this.#labelElement);
    this.#boxElement.hidden = true;
    this.#boxElement.style.setProperty('--lingotube-text-scale', String(textScale));
    this.applyAppearance(appearance);

    this.#boxElement.addEventListener('pointerdown', this.#handlePointerDown);
    this.#boxElement.addEventListener('pointermove', this.#handlePointerMove);
    this.#boxElement.addEventListener('pointerup', this.#handlePointerUp);
    this.#boxElement.addEventListener('pointercancel', this.#handlePointerCancel);
    // Capture phase: the click that ends a drag must not reach the player, which toggles playback on click.
    this.#boxElement.addEventListener('click', this.#handleClick, true);

    this.#container.appendChild(this.#boxElement);
    // Re-place the box when the container resizes (including fullscreen) or the box changes size.
    this.#resizeObserver = new ResizeObserver(() => this.#applyPosition());
    this.#resizeObserver.observe(this.#container);
    this.#resizeObserver.observe(this.#boxElement);
  }

  /** Shows a translated or source cue text. */
  showCueText(text) {
    this.#textElement.classList.remove('lingotube-overlay-status');
    this.#showText(text);
  }

  /** Shows a status such as "Перевожу…" in a muted style. */
  showStatus(text) {
    this.#textElement.classList.add('lingotube-overlay-status');
    this.#showText(text);
  }

  /** Empties and hides the box. */
  clear() {
    this.#showText('');
  }

  /** @param {boolean} isVisible */
  setApproximateTimingLabel(isVisible) {
    this.#labelElement.hidden = !isVisible;
    this.#applyPosition();
  }

  /** @param {number} scale multiplier of the base font size */
  setTextScale(scale) {
    this.#boxElement.style.setProperty('--lingotube-text-scale', String(scale));
    this.#applyPosition();
  }

  /** @param {{textColor: string, backgroundOpacity: number, outline: boolean}} appearance */
  applyAppearance({ textColor, backgroundOpacity, outline }) {
    for (const [name, value] of Object.entries(appearanceVariables({ textColor, backgroundOpacity }))) {
      this.#boxElement.style.setProperty(name, value);
    }
    this.#boxElement.classList.toggle('lingotube-overlay-outlined', outline === true);
  }

  /** Puts the box back to its default place; safe while the box is not shown. */
  resetPosition() {
    this.#position = { ...DEFAULT_OVERLAY_POSITION };
    this.#applyPosition();
  }

  /** Hides the box regardless of its text, for example during ads. */
  setHidden(isHidden) {
    this.#isHiddenByOwner = isHidden;
    this.#updateVisibility();
  }

  /** Removes the element, the observer and all listeners. */
  destroy() {
    this.#resizeObserver.disconnect();
    this.#boxElement.removeEventListener('pointerdown', this.#handlePointerDown);
    this.#boxElement.removeEventListener('pointermove', this.#handlePointerMove);
    this.#boxElement.removeEventListener('pointerup', this.#handlePointerUp);
    this.#boxElement.removeEventListener('pointercancel', this.#handlePointerCancel);
    this.#boxElement.removeEventListener('click', this.#handleClick, true);
    this.#boxElement.remove();
  }

  #showText(text) {
    this.#textElement.textContent = text;
    this.#isEmpty = text === '';
    this.#updateVisibility();
  }

  #updateVisibility() {
    this.#boxElement.hidden = this.#isEmpty || this.#isHiddenByOwner;
    this.#applyPosition();
  }

  #measureSizes() {
    return {
      boxWidth: this.#boxElement.offsetWidth,
      boxHeight: this.#boxElement.offsetHeight,
      containerWidth: this.#container.clientWidth,
      containerHeight: this.#container.clientHeight,
    };
  }

  /** Places the box by the stored position clamped to the current sizes; the stored position is kept. */
  #applyPosition() {
    if (this.#boxElement.hidden) return;
    const placed = clampOverlayPosition(this.#position, this.#measureSizes());
    this.#boxElement.style.left = `${placed.centerXFraction * 100}%`;
    this.#boxElement.style.top = `${placed.bottomYFraction * 100}%`;
    this.#boxElement.style.transform = 'translate(-50%, -100%)';
  }

  #handlePointerDown = (event) => {
    if (event.button !== 0 || this.#drag) return;
    const boxRect = this.#boxElement.getBoundingClientRect();
    this.#isNextClickSwallowed = false;
    this.#drag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      grabOffsetX: event.clientX - boxRect.left,
      grabOffsetY: event.clientY - boxRect.top,
      isMoving: false,
    };
    this.#boxElement.setPointerCapture(event.pointerId);
  };

  #handlePointerMove = (event) => {
    const drag = this.#drag;
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (!drag.isMoving) {
      const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
      if (distance < DRAG_THRESHOLD_PX) return;
      drag.isMoving = true;
      this.#boxElement.classList.add('lingotube-dragging');
    }
    const containerRect = this.#container.getBoundingClientRect();
    this.#position = positionFromDrag({
      pointerX: event.clientX - containerRect.left,
      pointerY: event.clientY - containerRect.top,
      grabOffsetX: drag.grabOffsetX,
      grabOffsetY: drag.grabOffsetY,
      ...this.#measureSizes(),
    });
    this.#applyPosition();
  };

  #handlePointerUp = (event) => {
    const drag = this.#drag;
    if (!drag || event.pointerId !== drag.pointerId) return;
    this.#finishDrag();
    if (drag.isMoving) {
      this.#isNextClickSwallowed = true;
      this.#onPositionChanged({ ...this.#position });
    }
  };

  #handlePointerCancel = (event) => {
    if (this.#drag && event.pointerId === this.#drag.pointerId) this.#finishDrag();
  };

  #finishDrag() {
    this.#boxElement.classList.remove('lingotube-dragging');
    this.#drag = null;
  }

  #handleClick = (event) => {
    if (!this.#isNextClickSwallowed) return;
    this.#isNextClickSwallowed = false;
    event.stopPropagation();
    event.preventDefault();
  };
}
