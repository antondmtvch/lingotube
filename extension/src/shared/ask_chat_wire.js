// Pure functions for YouTube's internal Ask-chat requests (port of src/lingotube/ask/wire.py).
// No network and no clocks here: data in, data out.

const CHAT_PANEL_ID = 'PAyouchat';

/** @typedef {{continuation: string, clickTrackingParams: string}} SendCommand */

/** Yield every object of a JSON tree (iterative: answers are deep and large). */
function* walkObjects(root) {
  const stack = [root];
  while (stack.length) {
    const current = stack.pop();
    if (Array.isArray(current)) {
      for (let i = current.length - 1; i >= 0; i--) stack.push(current[i]);
    } else if (current !== null && typeof current === 'object') {
      yield current;
      const values = Object.values(current);
      for (let i = values.length - 1; i >= 0; i--) stack.push(values[i]);
    }
  }
}

function* chatPanels(data) {
  for (const node of walkObjects(data)) {
    const renderer = node.engagementPanelSectionListRenderer;
    if (renderer !== null && typeof renderer === 'object' && renderer.panelIdentifier === CHAT_PANEL_ID) {
      yield renderer;
    }
  }
}

const isNonEmptyString = (value) => typeof value === 'string' && value !== '';

/** @returns {SendCommand|null} */
function commandFrom(raw) {
  const inner = raw?.innertubeCommand;
  const token = inner?.continuationCommand?.token;
  const clickTrackingParams = inner?.clickTrackingParams;
  if (isNonEmptyString(token) && isNonEmptyString(clickTrackingParams)) {
    return { continuation: token, clickTrackingParams };
  }
  return null;
}

/**
 * First complete `sendUserQueryCommand` inside a `PAyouchat` panel (or anywhere if not panelOnly).
 * @param {object} response
 * @param {{panelOnly?: boolean}} [options]
 * @returns {SendCommand|null}
 */
export function findSendCommand(response, { panelOnly = true } = {}) {
  const roots = panelOnly ? [...chatPanels(response)] : [response];
  for (const root of roots) {
    for (const node of walkObjects(root)) {
      const command = commandFrom(node.sendUserQueryCommand);
      if (command !== null) return command;
    }
  }
  return null;
}

/**
 * First continuation token of the `PAyouchat` panel (for the "empty initial get_panel").
 * @returns {string|null}
 */
export function findChatPanelToken(nextResponse) {
  for (const panel of chatPanels(nextResponse)) {
    for (const node of walkObjects(panel)) {
      const token = node.continuationCommand?.token;
      if (isNonEmptyString(token)) return token;
    }
  }
  return null;
}

/** @returns {boolean} true only when YouTube explicitly says the user is not logged out */
export function isSignedIn(nextResponse) {
  return nextResponse?.responseContext?.mainAppWebResponseContext?.loggedOut === false;
}

/**
 * Body of a get_panel request that sends one chat message. Does not mutate `context`.
 * @param {{context: object, command: SendCommand, prompt: string, nowMs: number}} params
 */
export function buildAskBody({ context, command, prompt, nowMs }) {
  return {
    context: { ...context, clickTracking: { clickTrackingParams: command.clickTrackingParams } },
    continuation: command.continuation,
    formData: {
      inputComposerFormData: {
        clientMessageId: `youchat-${nowMs}`,
        playerOffsetMs: '0',
        userInputText: prompt,
      },
    },
  };
}

/**
 * Only `youChatItemViewModel.text.content`; snackbars, chips and disclaimers are ignored.
 * @returns {string} '' when there is no answer
 */
export function extractAnswer(getPanelResponse) {
  const parts = [];
  for (const node of walkObjects(getPanelResponse)) {
    const content = node.youChatItemViewModel?.text?.content;
    if (typeof content === 'string' && content.trim()) parts.push(content);
  }
  return parts.join('\n');
}
