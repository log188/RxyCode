// Vitest test - verify RxyCode logo renders correctly
import React from 'react';
import { test, expect, describe } from 'vitest';
import { render } from 'ink-testing-library';
import { WORDMARK, centerLine } from '../src/logo.js';

describe('logo structure', () => {
  test('logo has 7 lines (7x7 block style)', () => {
    expect(WORDMARK.length).toBe(7);
  });

  test('logo lines have consistent width of 61 chars (ljust)', () => {
    const widths = WORDMARK.map(line => line.length);
    console.log('Line widths:', widths);
    const allSame = widths.every(w => w === widths[0]);
    expect(allSame).toBe(true);
    expect(widths[0]).toBe(61);
  });

  test('logo uses block characters', () => {
    WORDMARK.forEach(line => {
      expect(line).toMatch(/[█]/);
    });
  });
});

describe('centerLine', () => {
  test('centers short text', () => {
    // centerLine uses Math.floor((width - line.length) / 2)
    // (10 - 3) / 2 = 3 (floor) -> '   abc'
    expect(centerLine('abc', 10)).toBe('   abc');
  });

  test('returns original when wider than terminal', () => {
    expect(centerLine('hello world', 5)).toBe('hello world');
  });

  test('centers exact width text', () => {
    expect(centerLine('abcde', 5)).toBe('abcde');
  });

  test('centers 61-char logo in 100-col terminal', () => {
    // centerLine adds leading spaces equal to floor((width - line.length) / 2)
    // For 61-char logo in 100-col terminal: (100-61)/2 = 19 leading spaces
    const centered = centerLine(WORDMARK[0], 100);
    expect(centered.length).toBe(80); // 19 + 61
    expect(centered.startsWith(' '.repeat(19))).toBe(true);
  });
});

describe('Banner component', () => {
  test('renders all 7 logo lines + subtitle', async () => {
    const BannerModule = await import('../src/components/Banner.js');
    const Banner = BannerModule.default;
    const { lastFrame } = render(React.createElement(Banner));
    const frame = lastFrame();
    console.log('\n=== Banner rendered output ===');
    console.log(frame);
    console.log('=== end ===\n');

    // Verify all 7 logo lines are in the frame (after stripping leading spaces)
    WORDMARK.forEach((line, i) => {
      const trimmedLine = line.trimEnd();
      expect(frame, `Logo line ${i} should be in frame`).toContain(trimmedLine);
    });

    // Verify subtitle
    expect(frame).toContain('General-Purpose AI Agent');
    expect(frame).not.toContain('Coding Assistant');
  });

  test('banner output is centered in 100-col terminal', async () => {
    const BannerModule = await import('../src/components/Banner.js');
    const Banner = BannerModule.default;
    const { lastFrame } = render(React.createElement(Banner));
    const frame = lastFrame();
    const lines = frame.split('\n');

    // Find logo lines (those containing block characters)
    const logoLines = lines.filter(l => l.includes('█'));
    console.log('Logo lines found:', logoLines.length);
    expect(logoLines.length).toBe(7);

    // Each logo line should have same leading whitespace (centering)
    const leadingSpacesList = logoLines.map(line => line.match(/^( *)/)?.[0].length || 0);
    console.log('Leading spaces per line:', leadingSpacesList);

    // All should be 19 (logoWidth=61, termWidth=100, lead=19)
    leadingSpacesList.forEach((s, i) => {
      expect(s, `Line ${i} should have 19 leading spaces`).toBe(19);
    });
  });
});
