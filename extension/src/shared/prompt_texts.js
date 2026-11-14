/** Version of the prompt texts; matches PROMPT_VERSION of the Python package. */
export const PROMPT_VERSION = '1';

/**
 * Exact copies of src/lingotube/prompts/<name>.v1.txt (there is no build step to share them);
 * tests/prompt_texts.test.js compares them with the package files.
 */
export const PROMPT_TEXTS = Object.freeze({
  translate_batch: "Переведи на язык: {language}.\nНа входе строки вида «номер<TAB>текст», где <TAB> — символ табуляции, например:\n12\tHello, world\n13\tSee you\nНа выходе дай строки в том же виде «номер<TAB>перевод»: те же номера, в том же порядке и в том же количестве, по одной строке на каждую входную; переводи только текст после табуляции. Не объединяй и не разделяй строки, не пропускай их, ничего не добавляй. Без вступления, без заключения, без комментариев — только строки перевода.\n",
  transcript_translated: "Дай полную дословную транскрипцию всей речи в видео с {start} по {end} и переведи её дословно на язык: {language}. Одна строка на одну реплику в формате (м:сс) текст, где время — начало реплики (после первого часа — (ч:мм:сс)), а текст — перевод этой реплики. Выводи только строки перевода: оригинал не выводи совсем, не чередуй оригинал и перевод, не повторяй тайм-коды. Одна реплика — одна строка, в том же порядке, без пропусков и объединения реплик; ничего не добавляй от себя, не пересказывай и не сокращай. Без вступления, без заключения, без комментариев — только строки перевода.\n",
});

const PLACEHOLDER_PATTERN = /\{(\w+)\}/g;

/**
 * Fills the {word} placeholders of a prompt in one pass; values are not scanned again.
 * @param {keyof typeof PROMPT_TEXTS} name
 * @param {Record<string, string>} variables
 * @returns {string}
 */
export function fillPrompt(name, variables) {
  return PROMPT_TEXTS[name].replace(PLACEHOLDER_PATTERN, (_placeholder, word) => {
    if (!Object.hasOwn(variables, word)) {
      throw new Error(`Prompt variable is missing: ${word}`);
    }
    return variables[word];
  });
}
