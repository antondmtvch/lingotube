import { fillPrompt } from '../shared/prompt_texts.js';
import {
  formatPromptTime,
  parseTimestampedAnswer,
  withReadingTimeEnds,
} from '../shared/timestamped_transcript.js';
import { chunkBounds, linesInsideChunk } from '../shared/transcript_chunks.js';

/**
 * The fallback source without YouTube captions: asks the Ask chat for a literal translated
 * transcript of one chunk (prompt `transcript_translated`). One call sends one message;
 * a truncated answer is not asked again (a gap simply shows nothing).
 */
export class ChatTranscriptSource {
  #chatSession;
  #languageName;
  #durationMs;

  /**
   * @param {{chatSession: {ask: (prompt: string) => Promise<string>}, languageName: string, durationMs: number}} options
   */
  constructor({ chatSession, languageName, durationMs }) {
    this.#chatSession = chatSession;
    this.#languageName = languageName;
    this.#durationMs = durationMs;
  }

  /**
   * Cues of one chunk on the video timeline; [] when the answer has no timestamped lines.
   * Errors of the chat session propagate unchanged.
   * @param {number} index
   * @returns {Promise<import('../shared/timestamped_transcript.js').TimedLine[]>}
   */
  async requestChunk(index) {
    const bounds = chunkBounds(index, this.#durationMs);
    const prompt = fillPrompt('transcript_translated', {
      start: formatPromptTime(bounds.startMs),
      end: formatPromptTime(bounds.endMs, { roundUp: true }),
      language: this.#languageName,
    });
    const answer = await this.#chatSession.ask(prompt);
    return withReadingTimeEnds(linesInsideChunk(parseTimestampedAnswer(answer), bounds), bounds.endMs);
  }
}
