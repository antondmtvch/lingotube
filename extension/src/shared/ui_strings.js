/** Interface languages of the overlay, as BCP 47 tags. */
export const UI_LANGUAGES = ['ru', 'en', 'zh-CN', 'es', 'hi', 'ar', 'pt-BR', 'ja', 'fr', 'de'];

/** Interface language used when the browser language is missing or unsupported. */
export const FALLBACK_UI_LANGUAGE = 'en';

const RIGHT_TO_LEFT_LANGUAGES = new Set(['ar']);

/** Primary subtags that map to a language whose code carries a region. */
const PRIMARY_SUBTAG_TO_UI_LANGUAGE = { zh: 'zh-CN', pt: 'pt-BR' };

/** Texts per language; `rateLimited` holds a template with the {minutes} placeholder. */
const TEXTS = {
  ru: {
    translating: 'Перевожу…',
    translationDelayed: 'Перевод задерживается',
    approximateTiming: 'Время приблизительное',
    captionsNotFetched: 'Не удалось получить субтитры YouTube',
    chatUnavailable: 'Чат «Спросить» недоступен для этого видео или аккаунта',
    notSignedIn: 'Войдите в аккаунт YouTube',
    repeatedFailures: 'Чат не отвечает. Включите субтитры заново, чтобы повторить',
    noSpeech: 'У видео нет субтитров, и чат не дал транскрипцию',
    rateLimited: 'Чат ограничил запросы. Повтор через {minutes} мин',
    toggleOn: 'Включить субтитры',
    toggleOff: 'Выключить субтитры',
    waitOn: 'Ждать субтитры: вкл',
    waitOff: 'Ждать субтитры: выкл',
    targetLanguageLabel: 'Язык перевода:',
    otherLanguagePlaceholder: 'Название языка',
    otherLanguageOption: 'Другой язык…',
    done: 'Готово',
    smallerText: 'Уменьшить текст',
    largerText: 'Увеличить текст',
    textSizeLabel: 'Размер текста:',
    retryNow: 'Повторить сейчас',
  },
  en: {
    translating: 'Translating…',
    translationDelayed: 'Translation is delayed',
    approximateTiming: 'Approximate timing',
    captionsNotFetched: 'Could not load YouTube captions',
    chatUnavailable: 'The Ask chat is not available for this video or account',
    notSignedIn: 'Sign in to your YouTube account',
    repeatedFailures: 'The chat is not responding. Turn subtitles off and on again to retry',
    noSpeech: 'The video has no captions, and the chat gave no transcript',
    rateLimited: 'The chat limited requests. Retrying in {minutes} min',
    toggleOn: 'Turn subtitles on',
    toggleOff: 'Turn subtitles off',
    waitOn: 'Wait for subtitles: on',
    waitOff: 'Wait for subtitles: off',
    targetLanguageLabel: 'Translation language:',
    otherLanguagePlaceholder: 'Language name',
    otherLanguageOption: 'Another language…',
    done: 'Done',
    smallerText: 'Decrease text size',
    largerText: 'Increase text size',
    textSizeLabel: 'Text size:',
    retryNow: 'Retry now',
  },
  'zh-CN': {
    translating: '正在翻译…',
    translationDelayed: '翻译有延迟',
    approximateTiming: '时间为近似值',
    captionsNotFetched: '无法获取 YouTube 字幕',
    chatUnavailable: '“提问”聊天对此视频或账号不可用',
    notSignedIn: '请登录您的 YouTube 账号',
    repeatedFailures: '聊天没有响应。请关闭字幕后重新开启以重试',
    noSpeech: '该视频没有字幕，聊天也未提供文字记录',
    rateLimited: '聊天限制了请求频率，{minutes} 分钟后重试',
    toggleOn: '开启字幕',
    toggleOff: '关闭字幕',
    waitOn: '等待字幕：开',
    waitOff: '等待字幕：关',
    targetLanguageLabel: '翻译语言：',
    otherLanguagePlaceholder: '语言名称',
    otherLanguageOption: '其他语言…',
    done: '完成',
    smallerText: '缩小文字',
    largerText: '放大文字',
    textSizeLabel: '文字大小：',
    retryNow: '立即重试',
  },
  es: {
    translating: 'Traduciendo…',
    translationDelayed: 'La traducción se retrasa',
    approximateTiming: 'Tiempos aproximados',
    captionsNotFetched: 'No se pudieron obtener los subtítulos de YouTube',
    chatUnavailable: 'El chat «Preguntar» no está disponible para este vídeo o cuenta',
    notSignedIn: 'Inicia sesión en tu cuenta de YouTube',
    repeatedFailures: 'El chat no responde. Desactiva y vuelve a activar los subtítulos para reintentar',
    noSpeech: 'El vídeo no tiene subtítulos y el chat no devolvió ninguna transcripción',
    rateLimited: 'El chat limitó las solicitudes. Reintentando en {minutes} min',
    toggleOn: 'Activar subtítulos',
    toggleOff: 'Desactivar subtítulos',
    waitOn: 'Esperar subtítulos: sí',
    waitOff: 'Esperar subtítulos: no',
    targetLanguageLabel: 'Idioma de traducción:',
    otherLanguagePlaceholder: 'Nombre del idioma',
    otherLanguageOption: 'Otro idioma…',
    done: 'Listo',
    smallerText: 'Reducir texto',
    largerText: 'Aumentar texto',
    textSizeLabel: 'Tamaño del texto:',
    retryNow: 'Reintentar ahora',
  },
  hi: {
    translating: 'अनुवाद हो रहा है…',
    translationDelayed: 'अनुवाद में देरी हो रही है',
    approximateTiming: 'समय लगभग सही है',
    captionsNotFetched: 'YouTube के सबटाइटल नहीं मिल सके',
    chatUnavailable: 'इस वीडियो या खाते के लिए "पूछें" चैट उपलब्ध नहीं है',
    notSignedIn: 'अपने YouTube खाते में साइन इन करें',
    repeatedFailures: 'चैट जवाब नहीं दे रहा है। दोबारा कोशिश करने के लिए सबटाइटल बंद करके फिर चालू करें',
    noSpeech: 'इस वीडियो में सबटाइटल नहीं हैं, और चैट से ट्रांसक्रिप्ट नहीं मिला',
    rateLimited: 'चैट ने अनुरोधों को सीमित कर दिया है। {minutes} मिनट बाद फिर कोशिश होगी',
    toggleOn: 'सबटाइटल चालू करें',
    toggleOff: 'सबटाइटल बंद करें',
    waitOn: 'सबटाइटल की प्रतीक्षा: चालू',
    waitOff: 'सबटाइटल की प्रतीक्षा: बंद',
    targetLanguageLabel: 'अनुवाद की भाषा:',
    otherLanguagePlaceholder: 'भाषा का नाम',
    otherLanguageOption: 'अन्य भाषा…',
    done: 'हो गया',
    smallerText: 'टेक्स्ट छोटा करें',
    largerText: 'टेक्स्ट बड़ा करें',
    textSizeLabel: 'टेक्स्ट का आकार:',
    retryNow: 'अभी दोबारा कोशिश करें',
  },
  ar: {
    translating: 'جارٍ الترجمة…',
    translationDelayed: 'الترجمة متأخرة',
    approximateTiming: 'التوقيت تقريبي',
    captionsNotFetched: 'تعذّر تحميل ترجمات يوتيوب',
    chatUnavailable: 'دردشة «اسأل» غير متاحة لهذا الفيديو أو الحساب',
    notSignedIn: 'سجّل الدخول إلى حسابك على يوتيوب',
    repeatedFailures: 'الدردشة لا تستجيب. أوقف الترجمات ثم شغّلها مجددًا لإعادة المحاولة',
    noSpeech: 'لا توجد ترجمات لهذا الفيديو، ولم تقدّم الدردشة نصًا مكتوبًا',
    rateLimited: 'قيّدت الدردشة عدد الطلبات. إعادة المحاولة بعد {minutes} د',
    toggleOn: 'تشغيل الترجمات',
    toggleOff: 'إيقاف الترجمات',
    waitOn: 'انتظار الترجمات: مفعّل',
    waitOff: 'انتظار الترجمات: متوقف',
    targetLanguageLabel: 'لغة الترجمة:',
    otherLanguagePlaceholder: 'اسم اللغة',
    otherLanguageOption: 'لغة أخرى…',
    done: 'تم',
    smallerText: 'تصغير النص',
    largerText: 'تكبير النص',
    textSizeLabel: 'حجم النص:',
    retryNow: 'أعد المحاولة الآن',
  },
  'pt-BR': {
    translating: 'Traduzindo…',
    translationDelayed: 'A tradução está atrasada',
    approximateTiming: 'Tempo aproximado',
    captionsNotFetched: 'Não foi possível obter as legendas do YouTube',
    chatUnavailable: 'O chat «Perguntar» não está disponível para este vídeo ou conta',
    notSignedIn: 'Entre na sua conta do YouTube',
    repeatedFailures: 'O chat não está respondendo. Desative e ative as legendas novamente para tentar de novo',
    noSpeech: 'O vídeo não tem legendas e o chat não forneceu transcrição',
    rateLimited: 'O chat limitou as solicitações. Nova tentativa em {minutes} min',
    toggleOn: 'Ativar legendas',
    toggleOff: 'Desativar legendas',
    waitOn: 'Aguardar legendas: ativado',
    waitOff: 'Aguardar legendas: desativado',
    targetLanguageLabel: 'Idioma da tradução:',
    otherLanguagePlaceholder: 'Nome do idioma',
    otherLanguageOption: 'Outro idioma…',
    done: 'Concluído',
    smallerText: 'Diminuir texto',
    largerText: 'Aumentar texto',
    textSizeLabel: 'Tamanho do texto:',
    retryNow: 'Tentar agora',
  },
  ja: {
    translating: '翻訳中…',
    translationDelayed: '翻訳が遅れています',
    approximateTiming: 'タイミングは概算です',
    captionsNotFetched: 'YouTube の字幕を取得できませんでした',
    chatUnavailable: 'この動画またはアカウントでは「質問」チャットを利用できません',
    notSignedIn: 'YouTube アカウントにログインしてください',
    repeatedFailures: 'チャットが応答しません。字幕をオフにしてからもう一度オンにすると再試行できます',
    noSpeech: 'この動画には字幕がなく、チャットからも文字起こしを取得できませんでした',
    rateLimited: 'チャットがリクエストを制限しています。{minutes} 分後に再試行します',
    toggleOn: '字幕をオンにする',
    toggleOff: '字幕をオフにする',
    waitOn: '字幕を待つ：オン',
    waitOff: '字幕を待つ：オフ',
    targetLanguageLabel: '翻訳言語：',
    otherLanguagePlaceholder: '言語名',
    otherLanguageOption: 'その他の言語…',
    done: '完了',
    smallerText: '文字を小さくする',
    largerText: '文字を大きくする',
    textSizeLabel: '文字サイズ：',
    retryNow: '今すぐ再試行',
  },
  fr: {
    translating: 'Traduction en cours…',
    translationDelayed: 'La traduction est retardée',
    approximateTiming: 'Synchronisation approximative',
    captionsNotFetched: 'Impossible de récupérer les sous-titres YouTube',
    chatUnavailable: 'Le chat « Demander » n’est pas disponible pour cette vidéo ou ce compte',
    notSignedIn: 'Connectez-vous à votre compte YouTube',
    repeatedFailures: 'Le chat ne répond pas. Désactivez puis réactivez les sous-titres pour réessayer',
    noSpeech: 'La vidéo n’a pas de sous-titres et le chat n’a fourni aucune transcription',
    rateLimited: 'Le chat a limité les requêtes. Nouvel essai dans {minutes} min',
    toggleOn: 'Activer les sous-titres',
    toggleOff: 'Désactiver les sous-titres',
    waitOn: 'Attendre les sous-titres : oui',
    waitOff: 'Attendre les sous-titres : non',
    targetLanguageLabel: 'Langue de traduction :',
    otherLanguagePlaceholder: 'Nom de la langue',
    otherLanguageOption: 'Autre langue…',
    done: 'Terminé',
    smallerText: 'Réduire le texte',
    largerText: 'Agrandir le texte',
    textSizeLabel: 'Taille du texte :',
    retryNow: 'Réessayer maintenant',
  },
  de: {
    translating: 'Übersetze…',
    translationDelayed: 'Die Übersetzung verzögert sich',
    approximateTiming: 'Zeitangaben ungefähr',
    captionsNotFetched: 'YouTube-Untertitel konnten nicht geladen werden',
    chatUnavailable: 'Der Chat „Fragen“ ist für dieses Video oder Konto nicht verfügbar',
    notSignedIn: 'Melde dich in deinem YouTube-Konto an',
    repeatedFailures: 'Der Chat antwortet nicht. Schalte die Untertitel aus und wieder ein, um es erneut zu versuchen',
    noSpeech: 'Das Video hat keine Untertitel und der Chat lieferte kein Transkript',
    rateLimited: 'Der Chat hat die Anfragen begrenzt. Neuer Versuch in {minutes} Min.',
    toggleOn: 'Untertitel einschalten',
    toggleOff: 'Untertitel ausschalten',
    waitOn: 'Auf Untertitel warten: an',
    waitOff: 'Auf Untertitel warten: aus',
    targetLanguageLabel: 'Übersetzungssprache:',
    otherLanguagePlaceholder: 'Name der Sprache',
    otherLanguageOption: 'Andere Sprache…',
    done: 'Fertig',
    smallerText: 'Text verkleinern',
    largerText: 'Text vergrößern',
    textSizeLabel: 'Textgröße:',
    retryNow: 'Jetzt erneut versuchen',
  },
};

/**
 * Picks the interface language for a browser language tag.
 * An exact tag wins over the primary subtag; anything unknown falls back to English.
 * @param {unknown} navigatorLanguage value of `navigator.language`
 * @returns {string} one of UI_LANGUAGES
 */
export function pickUiLanguage(navigatorLanguage) {
  if (typeof navigatorLanguage !== 'string') return FALLBACK_UI_LANGUAGE;
  const tag = navigatorLanguage.trim().toLowerCase();
  const exact = UI_LANGUAGES.find((code) => code.toLowerCase() === tag);
  if (exact) return exact;
  const primarySubtag = tag.split(/[-_]/)[0];
  const mapped = Object.hasOwn(PRIMARY_SUBTAG_TO_UI_LANGUAGE, primarySubtag)
    ? PRIMARY_SUBTAG_TO_UI_LANGUAGE[primarySubtag]
    : undefined;
  if (mapped) return mapped;
  return UI_LANGUAGES.includes(primarySubtag) ? primarySubtag : FALLBACK_UI_LANGUAGE;
}

/**
 * @param {string} languageCode interface language code
 * @returns {boolean} true when the language is written right to left
 */
export function isRightToLeft(languageCode) {
  return RIGHT_TO_LEFT_LANGUAGES.has(languageCode);
}

/**
 * @param {string} languageCode interface language code; unknown codes use English
 * @returns {Record<string, any>} all interface texts; `rateLimited` is `(minutes) => string`
 */
export function uiTexts(languageCode) {
  const texts = Object.hasOwn(TEXTS, languageCode) ? TEXTS[languageCode] : TEXTS[FALLBACK_UI_LANGUAGE];
  const { rateLimited: rateLimitedTemplate, ...plainTexts } = texts;
  return {
    ...plainTexts,
    rateLimited: (minutes) => rateLimitedTemplate.replace('{minutes}', String(minutes)),
  };
}
