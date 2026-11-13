import {
  OTHER_LANGUAGE_VALUE,
  buildLanguageMenu,
  targetLanguageFromMenuValue,
} from '../shared/language_choices.js';
import { uiTexts } from '../shared/ui_strings.js';
import {
  customNamesForMenu,
  languageFromTypedText,
  placeButtonNextToSubtitlesButton,
  selectValueAfterClose,
  steppedTextScale,
} from '../shared/player_panel_logic.js';

const MAX_TYPED_LANGUAGE_LENGTH = 60;
const KEYBOARD_EVENT_TYPES = ['keydown', 'keyup', 'keypress'];

/**
 * The lingotube button in the player control bar and its settings panel.
 * DOM only: every decision is taken by the shared pure functions or by the callbacks.
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
  #languageSelect;
  #otherLanguageRow;
  #otherLanguageInput;
  #toggleEnabledButton;
  #waitForSubtitlesButton;
  #textScaleValueElement;
  #statusLineElement;
  #retryButton;
  #controlsObserver = null;
  #isOpen = false;

  /**
   * @param {{document: Document, playerElement: HTMLElement,
   *   settings: import('./settings_store.js').Settings,
   *   onEnabledChanged: (isEnabled: boolean) => void,
   *   onLanguageChanged: (language: import('../shared/language_choices.js').TargetLanguage) => void,
   *   onTextScaleChanged: (scale: number) => void,
   *   onWaitForSubtitlesChanged: (isEnabled: boolean) => void,
   *   onRetryRequested: () => void,
   *   texts?: Record<string, any>, isRightToLeft?: boolean}} options
   */
  constructor({ document, playerElement, settings, onEnabledChanged, onLanguageChanged, onTextScaleChanged, onWaitForSubtitlesChanged, onRetryRequested, texts = uiTexts('ru'), isRightToLeft = false }) {
    this.#document = document;
    this.#playerElement = playerElement;
    this.#settings = settings;
    this.#texts = texts;
    this.#isRightToLeft = isRightToLeft;
    this.#callbacks = { onEnabledChanged, onLanguageChanged, onTextScaleChanged, onWaitForSubtitlesChanged, onRetryRequested };

    this.#buildButton();
    this.#buildPanel();
    this.#playerElement.appendChild(this.#panelElement);
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
    this.#toggleEnabledButton.textContent = settings.enabled ? this.#texts.toggleOff : this.#texts.toggleOn;
    this.#buttonElement.classList.toggle('lingotube-player-button-pressed', settings.enabled);
    this.#buttonElement.setAttribute('aria-pressed', String(settings.enabled));
    const isWaiting = settings.waitForSubtitles !== false;
    this.#waitForSubtitlesButton.textContent = isWaiting ? this.#texts.waitOn : this.#texts.waitOff;
    this.#waitForSubtitlesButton.setAttribute('aria-pressed', String(isWaiting));
    this.#textScaleValueElement.textContent = `${Math.round(settings.textScale * 100)}%`;
  }

  destroy() {
    this.#controlsObserver?.disconnect();
    this.#controlsObserver = null;
    this.#document.removeEventListener('pointerdown', this.#handleDocumentPointerDown, true);
    this.#buttonElement.remove();
    this.#panelElement.remove();
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

    this.#toggleEnabledButton = this.#createElement('button', 'lingotube-panel-button lingotube-toggle-button');
    this.#toggleEnabledButton.addEventListener('click', () => {
      this.#callbacks.onEnabledChanged(!this.#settings.enabled);
    });

    this.#waitForSubtitlesButton = this.#createElement('button', 'lingotube-panel-button lingotube-wait-button');
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

  #setOpen(isOpen) {
    this.#isOpen = isOpen;
    // Closing abandons an open "other language" input: the select must show the language in use.
    if (!isOpen) this.#renderLanguageMenu();
    this.#panelElement.hidden = !isOpen;
    this.#buttonElement.setAttribute('aria-expanded', String(isOpen));
  }

  #handleDocumentPointerDown = (event) => {
    if (!this.#isOpen) return;
    const path = event.composedPath();
    if (path.includes(this.#panelElement) || path.includes(this.#buttonElement)) return;
    this.#setOpen(false);
  };
}
