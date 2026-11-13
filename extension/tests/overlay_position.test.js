import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_OVERLAY_POSITION,
  clampOverlayPosition,
  positionFromDrag,
} from '../src/shared/overlay_position.js';

const box = { boxWidth: 200, boxHeight: 40 };
const container = { containerWidth: 1000, containerHeight: 500 };

test('the default position is bottom centre above the control bar', () => {
  assert.deepEqual(DEFAULT_OVERLAY_POSITION, { centerXFraction: 0.5, bottomYFraction: 0.86 });
});

test('a position inside the container is left unchanged', () => {
  const position = { centerXFraction: 0.5, bottomYFraction: 0.86 };
  assert.deepEqual(clampOverlayPosition(position, { ...box, ...container }), position);
});

test('a position outside the container is pulled back so the whole box is visible', () => {
  const size = { ...box, ...container };
  // Left edge: centre must be at least half a box width from the left.
  assert.deepEqual(clampOverlayPosition({ centerXFraction: 0, bottomYFraction: 1 }, size), {
    centerXFraction: 0.1,
    bottomYFraction: 1,
  });
  assert.deepEqual(clampOverlayPosition({ centerXFraction: 1, bottomYFraction: 0 }, size), {
    centerXFraction: 0.9,
    bottomYFraction: 0.08,
  });
  assert.deepEqual(clampOverlayPosition({ centerXFraction: 5, bottomYFraction: -3 }, size), {
    centerXFraction: 0.9,
    bottomYFraction: 0.08,
  });
});

test('a box wider than the container is centred', () => {
  const result = clampOverlayPosition(
    { centerXFraction: 0.9, bottomYFraction: 0.5 },
    { boxWidth: 1200, boxHeight: 40, ...container },
  );
  assert.equal(result.centerXFraction, 0.5);
});

test('a box taller than the container sits on the bottom edge', () => {
  const result = clampOverlayPosition(
    { centerXFraction: 0.5, bottomYFraction: 0.5 },
    { boxWidth: 200, boxHeight: 600, ...container },
  );
  assert.equal(result.bottomYFraction, 1);
});

test('the same fractions give the same relative place after the container doubles in size', () => {
  const position = { centerXFraction: 0.3, bottomYFraction: 0.7 };
  const small = clampOverlayPosition(position, { ...box, ...container });
  const large = clampOverlayPosition(position, {
    boxWidth: 200,
    boxHeight: 40,
    containerWidth: 2000,
    containerHeight: 1000,
  });
  assert.deepEqual(small, position);
  assert.deepEqual(large, position);
});

test('fractions 0 and 1 are valid extremes for a box that fits only at the edge', () => {
  const edge = { boxWidth: 1000, boxHeight: 500, ...container };
  assert.deepEqual(clampOverlayPosition({ centerXFraction: 0, bottomYFraction: 0 }, edge), {
    centerXFraction: 0.5,
    bottomYFraction: 1,
  });
  const zeroBox = { boxWidth: 0, boxHeight: 0, ...container };
  assert.deepEqual(clampOverlayPosition({ centerXFraction: 0, bottomYFraction: 0 }, zeroBox), {
    centerXFraction: 0,
    bottomYFraction: 0,
  });
  assert.deepEqual(clampOverlayPosition({ centerXFraction: 1, bottomYFraction: 1 }, zeroBox), {
    centerXFraction: 1,
    bottomYFraction: 1,
  });
});

test('a zero-size container never produces NaN', () => {
  for (const sizes of [
    { containerWidth: 0, containerHeight: 500 },
    { containerWidth: 1000, containerHeight: 0 },
    { containerWidth: 0, containerHeight: 0 },
  ]) {
    const clamped = clampOverlayPosition(
      { centerXFraction: 0.5, bottomYFraction: 0.86 },
      { ...box, ...sizes },
    );
    const dragged = positionFromDrag({
      pointerX: 10,
      pointerY: 10,
      grabOffsetX: 5,
      grabOffsetY: 5,
      ...box,
      ...sizes,
    });
    for (const position of [clamped, dragged]) {
      assert.ok(Number.isFinite(position.centerXFraction));
      assert.ok(Number.isFinite(position.bottomYFraction));
      assert.ok(position.centerXFraction >= 0 && position.centerXFraction <= 1);
      assert.ok(position.bottomYFraction >= 0 && position.bottomYFraction <= 1);
    }
  }
});

test('positionFromDrag keeps the grab point under the pointer', () => {
  // Box 200x40; grabbed 30px from its left edge and 10px from its top edge.
  // Pointer at (400, 300) in container coordinates puts the box at left=370, top=290.
  const position = positionFromDrag({
    pointerX: 400,
    pointerY: 300,
    grabOffsetX: 30,
    grabOffsetY: 10,
    ...box,
    ...container,
  });
  assert.equal(position.centerXFraction, (370 + 100) / 1000);
  assert.equal(position.bottomYFraction, (290 + 40) / 500);
});

test('positionFromDrag keeps the box inside the container', () => {
  const position = positionFromDrag({
    pointerX: -500,
    pointerY: 9000,
    grabOffsetX: 30,
    grabOffsetY: 10,
    ...box,
    ...container,
  });
  assert.equal(position.centerXFraction, 0.1);
  assert.equal(position.bottomYFraction, 1);
});

test('a non-finite fraction is replaced by the default fraction, each field independently', () => {
  const size = { ...box, ...container };
  const defaults = DEFAULT_OVERLAY_POSITION;
  for (const bad of [NaN, Infinity, -Infinity, undefined, null, 'x']) {
    assert.deepEqual(clampOverlayPosition({ centerXFraction: bad, bottomYFraction: 0.5 }, size), {
      centerXFraction: defaults.centerXFraction,
      bottomYFraction: 0.5,
    });
    assert.deepEqual(clampOverlayPosition({ centerXFraction: 0.3, bottomYFraction: bad }, size), {
      centerXFraction: 0.3,
      bottomYFraction: defaults.bottomYFraction,
    });
  }
});

test('a missing field or a non-object position gives the default for the missing part', () => {
  const size = { ...box, ...container };
  assert.deepEqual(clampOverlayPosition({}, size), DEFAULT_OVERLAY_POSITION);
  assert.deepEqual(clampOverlayPosition({ centerXFraction: 0.3 }, size), {
    centerXFraction: 0.3,
    bottomYFraction: DEFAULT_OVERLAY_POSITION.bottomYFraction,
  });
  for (const bad of [null, undefined, 'x', 5]) {
    assert.deepEqual(clampOverlayPosition(bad, size), DEFAULT_OVERLAY_POSITION);
  }
});
