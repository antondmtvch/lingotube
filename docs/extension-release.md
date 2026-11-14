# Выпуск расширения из GitHub

Расширение распространяется как два файла в GitHub Release: zip для Chrome и Edge (ставится через «Загрузить распакованное») и подписанный `.xpi` для Firefox. Подпись выполняет Mozilla (AMO) в режиме `unlisted`: расширение не попадает в каталог, но Firefox принимает такой файл.

## Предпосылки

- Репозиторий открыт: Mozilla просит исходный код, а релиз должен быть доступен пользователям.
- В корне репозитория есть файл `LICENSE`.
- Есть ключи AMO со страницы <https://addons.mozilla.org/developers/addon/api/key/>. Задайте их в переменных окружения (имена проверены по справке `web-ext sign`: параметры `--api-key` и `--api-secret` читаются из переменных с префиксом `WEB_EXT_`):

  ```sh
  export WEB_EXT_API_KEY=user:12345:67
  export WEB_EXT_API_SECRET=<секрет>
  ```

## Шаги

1. Поднимите `version` в `extension/manifest.json`. AMO не принимает повторно уже загруженный номер версии.
2. Если менялись исходники страницы, пересоберите бандл и закоммитьте его: `node scripts/build-page-bundle.mjs`. Скрипт упаковки откажется работать с устаревшим `extension/src/page/bundle.js`.
3. Запустите тесты: `node --test extension/tests/`.
4. Соберите архивы (версия `<версия>` берётся из манифеста; файлы появятся в `dist/`):

   ```sh
   node scripts/package-extension.mjs chromium
   node scripts/package-extension.mjs source
   ```

   Первая команда пишет `dist/lingotube-<версия>-chromium.zip`, вторая (`git archive HEAD`, поэтому всё должно быть закоммичено) пишет `dist/lingotube-<версия>-source.zip`.
5. Подпишите расширение для Firefox:

   ```sh
   npx web-ext@10.8.0 sign --source-dir extension --channel unlisted --artifacts-dir dist --ignore-files "tests/**" "package.json" --upload-source-code dist/lingotube-<версия>-source.zip
   ```

   В `dist/` появится подписанный `.xpi`.
6. Переименуйте его в `dist/lingotube-<версия>-firefox.xpi`.
7. Создайте релиз:

   ```sh
   gh release create extension-v<версия> dist/lingotube-<версия>-chromium.zip dist/lingotube-<версия>-firefox.xpi --title "Расширение lingotube <версия>" --notes "Что изменилось..."
   ```

## Проверка вручную

Проверьте сборки в Chrome, Edge (zip, «Загрузить распакованное» после распаковки) и Firefox (`.xpi`):

- [ ] кнопка расширения в плеере появляется;
- [ ] перевод субтитров работает;
- [ ] пауза и продолжение;
- [ ] полноэкранный режим;
- [ ] перетаскивание оверлея;
- [ ] перемотка.

Линтер должен проходить без ошибок:

```sh
npx web-ext@10.8.0 lint --source-dir extension --ignore-files "tests/**" "package.json"
```

Два предупреждения о `data_collection_permissions` (`KEY_FIREFOX_UNSUPPORTED_BY_MIN_VERSION` и `KEY_FIREFOX_ANDROID_UNSUPPORTED_BY_MIN_VERSION`) ожидаемы: ключ появился в Firefox 140 для настольной версии и 142 для Android, а более старые версии его игнорируют.
