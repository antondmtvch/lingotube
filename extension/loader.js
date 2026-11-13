// Classic content script (ISOLATED world). Starts the storage host here and
// injects the page module into the MAIN world through a module script tag.
(async () => {
  const storageHostModule = await import(chrome.runtime.getURL('src/content/storage_host.js'));
  storageHostModule.startStorageHost({ window, storageArea: chrome.storage.local });

  const pageScript = document.createElement('script');
  pageScript.type = 'module';
  pageScript.src = chrome.runtime.getURL('src/page/main.js');
  document.documentElement.appendChild(pageScript);
})();
