// User-facing status texts of the overlay (Russian).

export const STATUS_TEXTS = {
  translating: 'Перевожу…',
  approximateTiming: 'Время приблизительное',
  captionsNotFetched: 'Не удалось получить субтитры YouTube',
  chatUnavailable: 'Чат «Спросить» недоступен для этого видео или аккаунта',
  notSignedIn: 'Войдите в аккаунт YouTube',
  repeatedFailures: 'Чат не отвечает. Включите субтитры заново, чтобы повторить',
  noSpeech: 'У видео нет субтитров, и чат не дал транскрипцию',
};

/** @param {number} minutesLeft whole minutes until requests may resume */
export function rateLimitedText(minutesLeft) {
  return `Чат ограничил запросы. Повтор через ${minutesLeft} мин`;
}
