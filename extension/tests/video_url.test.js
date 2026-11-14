import { test } from 'node:test';
import assert from 'node:assert/strict';
import { watchVideoIdFromUrl } from '../src/shared/video_url.js';

test('watch URL gives the id; a leading-dash id works', () => {
  assert.equal(watchVideoIdFromUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ'), 'dQw4w9WgXcQ');
  assert.equal(watchVideoIdFromUrl('https://www.youtube.com/watch?v=-n5MqamatXE'), '-n5MqamatXE');
  assert.equal(
    watchVideoIdFromUrl('https://www.youtube.com/watch?list=PL1&v=-n5MqamatXE&t=42s#comments'),
    '-n5MqamatXE',
  );
});

test('shorts, embed, channel and non-YouTube URLs give null', () => {
  const urls = [
    'https://www.youtube.com/shorts/dQw4w9WgXcQ',
    'https://www.youtube.com/embed/dQw4w9WgXcQ',
    'https://www.youtube.com/@somechannel',
    'https://www.youtube.com/',
    'https://www.youtube.com/results?search_query=v',
    'https://www.youtube.com/watch',
    'https://www.youtube.com/watch?v=',
    'https://www.youtube.com/watch?v=too-short',
    'https://www.youtube.com/watch?v=has%20space%20x',
    'http://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://m.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://youtu.be/dQw4w9WgXcQ',
    'https://example.com/watch?v=dQw4w9WgXcQ',
    'not a url',
    '',
  ];
  for (const url of urls) assert.equal(watchVideoIdFromUrl(url), null, url);
});
