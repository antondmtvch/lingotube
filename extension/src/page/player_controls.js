import {
  OTHER_LANGUAGE_VALUE,
  buildLanguageMenu,
  targetLanguageFromMenuValue,
} from '../shared/language_choices.js';
import { uiTexts } from '../shared/ui_strings.js';
import {
  TEXT_COLOR_CSS,
  customNamesForMenu,
  languageFromTypedText,
  placeButtonNextToSubtitlesButton,
  selectValueAfterClose,
  shouldShowHint,
  steppedBackgroundOpacity,
  steppedTextScale,
} from '../shared/player_panel_logic.js';

const MAX_TYPED_LANGUAGE_LENGTH = 60;
const KEYBOARD_EVENT_TYPES = ['keydown', 'keyup', 'keypress'];

/**
 * The lingotube button in the player control bar, its settings panel, the appearance panel
 * and the first-run hint. DOM only: every decision is taken by the shared pure functions or by the callbacks.
 */
export class PlayerControls {
  #document;
  #playerElement;
  #settings;
  #texts;
  #isRightToLeft;
  #callbacks;
  #buttonElement;
  #panelElement;
  #appearancePanelElement;
  #hintElement;
  #languageSelect;
  #otherLanguageRow;
  #otherLanguageInput;
  #toggleEnabledButton;
  #waitForSubtitlesButton;
  #appearanceOpenButton;
  #textScaleValueElement;
  #statusLineElement;
  #retryButton;
  #colorButtons = new Map();
  #opacityValueElement;
  #outlineButton;
  #opacitySlider;
  #controlsObserver = null;
  #hintObserver = null;
  #isOpen = false;

  /**
   * @param {{document: Document, playerElement: HTMLElement,
   *   settings: import('./settings_store.js').Settings,
   *   onEnabledChanged: (isEnabled: boolean) => void,
   *   onLanguageChanged: (language: import('../shared/language_choices.js').TargetLanguage) => void,
   *   onTextScaleChanged: (scale: number) => void,
   *   onWaitForSubtitlesChanged: (isEnabled: boolean) => void,
   *   onRetryRequested: () => void,
   *   onAppearanceChanged: (change: {textColor?: string, backgroundOpacity?: number, outline?: boolean}) => void,
   *   onResetPosition: () => void,
   *   onHintDismissed: () => void,
   *   texts?: Record<string, any>, isRightToLeft?: boolean}} options
   */
  constructor({ document, playerElement, settings, onEnabledChanged, onLanguageChanged, onTextScaleChanged, onWaitForSubtitlesChanged, onRetryRequested, onAppearanceChanged, onResetPosition, onHintDismissed, texts = uiTexts('ru'), isRightToLeft = false }) {
    this.#document = document;
    this.#playerElement = playerElement;
    this.#settings = settings;
    this.#texts = texts;
    this.#isRightToLeft = isRightToLeft;
    this.#callbacks = {
      onEnabledChanged,
      onLanguageChanged,
      onTextScaleChanged,
      onWaitForSubtitlesChanged,
      onRetryRequested,
      onAppearanceChanged,
      onResetPosition,
      onHintDismissed,
    };

    this.#buildButton();
    this.#buildPanel();
    this.#buildAppearancePanel();
    this.#buildHint();
    this.#playerElement.appendChild(this.#panelElement);
    this.#playerElement.appendChild(this.#appearancePanelElement);
    this.#playerElement.appendChild(this.#hintElement);
    this.#attachButtonWhenControlsExist();
    this.#document.addEventListener('pointerdown', this.#handleDocumentPointerDown, true);
    this.applySettings(settings);
  }

  /** @param {string|null} text null clears the line */
  setStatusLine(text) {
    this.#statusLineElement.textContent = text ?? '';
    this.#statusLineElement.hidden = !text;
  }

  /** @param {boolean} isVisible */
  setRetryButtonVisible(isVisible) {
    this.#retryButton.hidden = !isVisible;
  }

  /** @param {import('./settings_store.js').Settings} settings */
  applySettings(settings) {
    this.#settings = settings;
    this.#renderLanguageMenu();
    this.#setSwitch(this.#toggleEnabledButton, settings.enabled ? this.#texts.toggleOff : this.#texts.toggleOn, settings.enabled);
    this.#toggleEnabledButton.setAttribute('aria-pressed', String(settings.enabled));
    this.#buttonElement.classList.toggle('lingotube-player-button-pressed', settings.enabled);
    this.#buttonElement.setAttribute('aria-pressed', String(settings.enabled));
    const isWaiting = settings.waitForSubtitles !== false;
    this.#setSwitch(this.#waitForSubtitlesButton, isWaiting ? this.#texts.waitOn : this.#texts.waitOff, isWaiting);
    this.#textScaleValueElement.textContent = `${Math.round(settings.textScale * 100)}%`;
    this.#renderAppearance(settings);
    this.#hintElement.hidden = !shouldShowHint(settings);
  }

  destroy() {
    this.#controlsObserver?.disconnect();
    this.#controlsObserver = null;
    this.#hintObserver?.disconnect();
    this.#hintObserver = null;
    this.#document.removeEventListener('pointerdown', this.#handleDocumentPointerDown, true);
    this.#buttonElement.remove();
    this.#panelElement.remove();
    this.#appearancePanelElement.remove();
    this.#hintElement.remove();
  }

  /** A row-wide switch: label on the left, a track with a thumb on the right. */
  #createSwitch(className) {
    const button = this.#createElement('button', `lingotube-panel-button lingotube-switch ${className}`);
    button.setAttribute('role', 'switch');
    const track = this.#createElement('span', 'lingotube-switch-track');
    track.append(this.#createElement('span', 'lingotube-switch-thumb'));
    button.append(this.#createElement('span', 'lingotube-switch-label'), track);
    return button;
  }

  #setSwitch(button, text, isOn) {
    button.querySelector('.lingotube-switch-label').textContent = text;
    button.setAttribute('aria-checked', String(isOn));
    button.classList.toggle('lingotube-switch-on', isOn);
  }

  #createElement(tagName, className, text) {
    const element = this.#document.createElement(tagName);
    element.className = className;
    if (text !== undefined) element.textContent = text;
    if (tagName === 'button') element.type = 'button';
    return element;
  }

  #buildButton() {
    this.#buttonElement = this.#createElement('button', 'ytp-button lingotube-player-button', 'LT');
    this.#buttonElement.title = 'lingotube';
    this.#buttonElement.setAttribute('aria-label', 'lingotube');
    this.#buttonElement.setAttribute('aria-haspopup', 'dialog');
    this.#buttonElement.addEventListener('click', () => this.#setOpen(!this.#isOpen));
    this.#buttonElement.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && this.#isOpen) this.#setOpen(false);
    });
  }

  #buildPanel() {
    const panel = this.#createElement('div', 'lingotube-panel');
    panel.id = 'lingotube-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'lingotube');
    panel.hidden = true;
    if (this.#isRightToLeft) panel.dir = 'rtl';

    const title = this.#createElement('div', 'lingotube-panel-title', 'lingotube');

    const languageRow = this.#createElement('label', 'lingotube-panel-row');
    languageRow.append(this.#createElement('span', 'lingotube-panel-label', this.#texts.targetLanguageLabel));
    this.#languageSelect = this.#createElement('select', 'lingotube-language-select');
    this.#languageSelect.id = 'lingotube-language-select';
    this.#languageSelect.addEventListener('change', this.#handleLanguageSelected);
    languageRow.append(this.#languageSelect);

    this.#otherLanguageRow = this.#createElement('div', 'lingotube-panel-row lingotube-other-language-row');
    this.#otherLanguageRow.hidden = true;
    this.#otherLanguageInput = this.#createElement('input', 'lingotube-other-language-input');
    this.#otherLanguageInput.type = 'text';
    this.#otherLanguageInput.setAttribute('maxlength', String(MAX_TYPED_LANGUAGE_LENGTH));
    this.#otherLanguageInput.placeholder = this.#texts.otherLanguagePlaceholder;
    this.#otherLanguageInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') this.#confirmTypedLanguage();
    });
    const confirmButton = this.#createElement('button', 'lingotube-panel-button', this.#texts.done);
    confirmButton.addEventListener('click', () => this.#confirmTypedLanguage());
    this.#otherLanguageRow.append(this.#otherLanguageInput, confirmButton);

    this.#toggleEnabledButton = this.#createSwitch('lingotube-toggle-button');
    this.#toggleEnabledButton.addEventListener('click', () => {
      this.#callbacks.onEnabledChanged(!this.#settings.enabled);
    });

    this.#waitForSubtitlesButton = this.#createSwitch('lingotube-wait-button');
    this.#waitForSubtitlesButton.addEventListener('click', () => {
      this.#callbacks.onWaitForSubtitlesChanged(this.#settings.waitForSubtitles === false);
    });

    const scaleRow = this.#createElement('div', 'lingotube-panel-row');
    const smallerButton = this.#createElement('button', 'lingotube-panel-button lingotube-scale-button', '−');
    smallerButton.setAttribute('aria-label', this.#texts.smallerText);
    smallerButton.addEventListener('click', () => this.#changeTextScale(-1));
    const largerButton = this.#createElement('button', 'lingotube-panel-button lingotube-scale-button', '+');
    largerButton.setAttribute('aria-label', this.#texts.largerText);
    largerButton.addEventListener('click', () => this.#changeTextScale(1));
    this.#textScaleValueElement = this.#createElement('span', 'lingotube-scale-value');
    scaleRow.append(
      this.#createElement('span', 'lingotube-panel-label', this.#texts.textSizeLabel),
      smallerButton,
      this.#textScaleValueElement,
      largerButton,
    );

    this.#appearanceOpenButton = this.#createElement('button', 'lingotube-panel-button lingotube-appearance-open', this.#texts.appearanceOpen);
    this.#appearanceOpenButton.addEventListener('click', () => this.#showAppearance());

    this.#statusLineElement = this.#createElement('div', 'lingotube-status-line');
    this.#statusLineElement.hidden = true;
    this.#statusLineElement.setAttribute('role', 'status');

    this.#retryButton = this.#createElement('button', 'lingotube-panel-button lingotube-retry-button', this.#texts.retryNow);
    this.#retryButton.hidden = true;
    this.#retryButton.addEventListener('click', () => this.#callbacks.onRetryRequested());

    panel.append(
      title,
      languageRow,
      this.#otherLanguageRow,
      this.#toggleEnabledButton,
      scaleRow,
      this.#waitForSubtitlesButton,
      this.#appearanceOpenButton,
      this.#statusLineElement,
      this.#retryButton,
    );

    // YouTube binds letters and space as player shortcuts; keep keys typed here away from the player.
    panel.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') this.#setOpen(false);
    });
    for (const type of KEYBOARD_EVENT_TYPES) {
      panel.addEventListener(type, (event) => event.stopPropagation());
    }
    this.#panelElement = panel;
  }

  #buildAppearancePanel() {
    const panel = this.#createElement('div', 'lingotube-panel lingotube-appearance-panel');
    panel.id = 'lingotube-appearance-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', this.#texts.appearanceTitle);
    panel.hidden = true;
    if (this.#isRightToLeft) panel.dir = 'rtl';

    const header = this.#createElement('div', 'lingotube-panel-row');
    const backButton = this.#createElement('button', 'lingotube-panel-button lingotube-appearance-back', this.#texts.back);
    backButton.addEventListener('click', () => this.#showMain());
    header.append(backButton, this.#createElement('span', 'lingotube-panel-title', this.#texts.appearanceTitle));

    const colorRow = this.#createElement('div', 'lingotube-panel-row');
    colorRow.append(this.#createElement('span', 'lingotube-panel-label', this.#texts.textColorLabel));
    const colorNames = { white: this.#texts.colorWhite, yellow: this.#texts.colorYellow, cyan: this.#texts.colorCyan };
    for (const color of Object.keys(TEXT_COLOR_CSS)) {
      const button = this.#createElement('button', 'lingotube-color-button');
      button.dataset.color = color;
      button.title = colorNames[color];
      button.setAttribute('aria-label', colorNames[color]);
      button.addEventListener('click', () => this.#callbacks.onAppearanceChanged({ textColor: color }));
      this.#colorButtons.set(color, button);
      colorRow.append(button);
    }

    const backgroundRow = this.#createElement('div', 'lingotube-panel-row');
    const backgroundLabel = this.#createElement('span', 'lingotube-panel-label', this.#texts.backgroundLabel);
    const fewerButton = this.#createElement('button', 'lingotube-panel-button lingotube-opacity-button', '−');
    fewerButton.addEventListener('click', () => this.#changeBackgroundOpacity(-1));
    const moreButton = this.#createElement('button', 'lingotube-panel-button lingotube-opacity-button', '+');
    moreButton.addEventListener('click', () => this.#changeBackgroundOpacity(1));
    this.#opacitySlider = this.#createElement('input', 'lingotube-opacity-slider');
    this.#opacitySlider.type = 'range';
    this.#opacitySlider.min = '0';
    this.#opacitySlider.max = '100';
    this.#opacitySlider.step = '5';
    this.#opacitySlider.setAttribute('aria-label', this.#texts.backgroundLabel);
    this.#opacitySlider.addEventListener('input', () => {
      this.#callbacks.onAppearanceChanged({ backgroundOpacity: Number(this.#opacitySlider.value) / 100 });
    });
    this.#opacityValueElement = this.#createElement('span', 'lingotube-scale-value');
    backgroundRow.append(backgroundLabel, fewerButton, this.#opacitySlider, moreButton, this.#opacityValueElement);

    const outlineRow = this.#createElement('div', 'lingotube-panel-row');
    this.#outlineButton = this.#createElement('button', 'lingotube-panel-button lingotube-outline-button', this.#texts.outlineLabel);
    this.#outlineButton.addEventListener('click', () => this.#callbacks.onAppearanceChanged({ outline: this.#settings.outline !== true }));
    outlineRow.append(this.#outlineButton);

    const resetButton = this.#createElement('button', 'lingotube-panel-button lingotube-toggle-button', this.#texts.resetPosition);
    resetButton.addEventListener('click', () => this.#callbacks.onResetPosition());

    panel.append(header, colorRow, backgroundRow, outlineRow, resetButton);
    panel.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') this.#setOpen(false);
    });
    for (const type of KEYBOARD_EVENT_TYPES) {
      panel.addEventListener(type, (event) => event.stopPropagation());
    }
    this.#appearancePanelElement = panel;
  }

  #buildHint() {
    this.#hintElement = this.#createElement('div', 'lingotube-hint', this.#texts.hintFirstRun);
    this.#hintElement.hidden = true;
    this.#hintElement.addEventListener('click', () => {
      this.#hintElement.hidden = true;
      this.#callbacks.onHintDismissed();
    });
  }

  #positionHint() {
    if (!this.#buttonElement.isConnected) return;
    const button = this.#buttonElement.getBoundingClientRect();
    const player = this.#playerElement.getBoundingClientRect();
    this.#hintElement.style.left = `${button.left - player.left + button.width / 2}px`;
    this.#hintElement.style.top = `${button.top - player.top}px`;
  }

  #attachButtonWhenControlsExist() {
    if (this.#tryAttachButton()) return;
    // The control bar may be built after this object; watch until it appears.
    this.#controlsObserver = new MutationObserver(() => {
      if (this.#tryAttachButton()) {
        this.#controlsObserver.disconnect();
        this.#controlsObserver = null;
      }
    });
    this.#controlsObserver.observe(this.#playerElement, { childList: true, subtree: true });
  }

  #tryAttachButton() {
    const rightControls = this.#playerElement.querySelector('.ytp-right-controls');
    if (!rightControls) return false;
    const subtitlesButton = rightControls.querySelector('.ytp-subtitles-button');
    placeButtonNextToSubtitlesButton({ rightControls, subtitlesButton, button: this.#buttonElement });
    // The hint follows the button: re-place it when the player changes size (fullscreen too).
    this.#hintObserver = new ResizeObserver(() => this.#positionHint());
    this.#hintObserver.observe(this.#playerElement);
    this.#positionHint();
    return true;
  }

  #renderLanguageMenu() {
    const language = this.#settings.language;
    const items = buildLanguageMenu(customNamesForMenu(this.#settings.customLanguageNames, language), this.#texts.otherLanguageOption);
    this.#languageSelect.replaceChildren();
    for (const item of items) {
      const option = this.#document.createElement('option');
      option.value = item.value;
      option.textContent = item.label;
      this.#languageSelect.append(option);
    }
    this.#languageSelect.value = selectValueAfterClose(language);
    this.#otherLanguageRow.hidden = true;
  }

  #renderAppearance(settings) {
    for (const [color, button] of this.#colorButtons) {
      button.setAttribute('aria-pressed', String(settings.textColor === color));
    }
    this.#opacitySlider.value = String(Math.round(settings.backgroundOpacity * 100));
    this.#opacityValueElement.textContent = `${Math.round(settings.backgroundOpacity * 100)}%`;
    this.#outlineButton.setAttribute('aria-pressed', String(settings.outline === true));
  }

  #handleLanguageSelected = () => {
    const value = this.#languageSelect.value;
    if (value === OTHER_LANGUAGE_VALUE) {
      this.#otherLanguageInput.value = '';
      this.#otherLanguageRow.hidden = false;
      this.#otherLanguageInput.focus();
      return;
    }
    const language = targetLanguageFromMenuValue(value);
    if (!language) {
      this.#renderLanguageMenu();
      return;
    }
    // The language may equal the current one, so no settings change would re-render the select.
    this.#renderLanguageMenu();
    this.#callbacks.onLanguageChanged(language);
  };

  #confirmTypedLanguage() {
    const language = languageFromTypedText(this.#otherLanguageInput.value);
    if (!language) {
      // Nothing usable was typed: go back to the language that was selected before.
      this.#renderLanguageMenu();
      return;
    }
    // The typed name may equal the current language, so no settings change would re-render the select.
    this.#renderLanguageMenu();
    this.#callbacks.onLanguageChanged(language);
  }

  #changeTextScale(direction) {
    const scale = steppedTextScale(this.#settings.textScale, direction);
    if (scale !== this.#settings.textScale) this.#callbacks.onTextScaleChanged(scale);
  }

  #changeBackgroundOpacity(direction) {
    const opacity = steppedBackgroundOpacity(this.#settings.backgroundOpacity, direction);
    if (opacity !== this.#settings.backgroundOpacity) this.#callbacks.onAppearanceChanged({ backgroundOpacity: opacity });
  }

  #showAppearance() {
    this.#panelElement.hidden = true;
    this.#appearancePanelElement.hidden = false;
    this.#appearancePanelElement.querySelector('.lingotube-appearance-back')?.focus();
  }

  #showMain() {
    this.#appearancePanelElement.hidden = true;
    this.#panelElement.hidden = false;
    this.#appearanceOpenButton.focus();
  }

  #setOpen(isOpen) {
    this.#isOpen = isOpen;
    // Closing abandons an open "other language" input: the select must show the language in use.
    if (!isOpen) this.#renderLanguageMenu();
    this.#panelElement.hidden = !isOpen;
    this.#appearancePanelElement.hidden = true;
    this.#buttonElement.setAttribute('aria-expanded', String(isOpen));
  }

  #handleDocumentPointerDown = (event) => {
    if (!this.#isOpen) return;
    const path = event.composedPath();
    const inside = [this.#panelElement, this.#appearancePanelElement, this.#buttonElement];
    if (inside.some((element) => path.includes(element))) return;
    this.#setOpen(false);
  };
}
