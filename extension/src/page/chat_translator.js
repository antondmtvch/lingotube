import { buildTranslationPrompt, parseTranslationReply } from '../shared/translation_batch.js';

/** @typedef {import('../shared/sentence_cues.js').Cue} Cue */

/** Translates cue batches through the Ask chat; one call sends at most two messages. */
export class ChatTranslator {
  /**
   * @param {{chatSession: {ask: (prompt: string) => Promise<string>}, languageName: string}} options
   */
  constructor({ chatSession, languageName }) {
    this.chatSession = chatSession;
    this.languageName = languageName;
  }

  /**
   * Asks for all cues, then once more for the cues the chat dropped.
   * Errors of the chat session propagate unchanged.
   * @param {Cue[]} cues
   * @returns {Promise<{translationsByCueId: Map<number, string>, failedCueIds: number[]}>}
   */
  async translateCues(cues) {
    const translationsByCueId = new Map();
    let pendingCues = cues;
    for (let attempt = 0; attempt < 2 && pendingCues.length > 0; attempt += 1) {
      const answer = await this.chatSession.ask(buildTranslationPrompt(this.languageName, pendingCues));
      const reply = parseTranslationReply(answer, pendingCues.map((cue) => cue.id));
      for (const [cueId, text] of reply.translationsByCueId) translationsByCueId.set(cueId, text);
      const missing = new Set(reply.missingCueIds);
      pendingCues = pendingCues.filter((cue) => missing.has(cue.id));
    }
    return { translationsByCueId, failedCueIds: pendingCues.map((cue) => cue.id) };
  }
}
