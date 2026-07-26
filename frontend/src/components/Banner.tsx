import React from 'react';
import { Box, Text, useStdout } from 'ink';
import { WORDMARK, centerLine } from '../logo.js';

export default React.memo(function Banner() {
  const { stdout } = useStdout();
  const termWidth = stdout?.columns ?? 80;

  // Logo 实际可见宽度 = 61 字符 (7x7 方块字, 所有行已 ljust 到 61)
  // Subtitle 视觉宽度 = 30 字符
  // 用 ZWJ 补齐 logo 每行到 61, 让所有行字符数一致
  const logoWidth = 61;
  const logoLeading = Math.floor((termWidth - logoWidth) / 2);

  const subtitleWidth = 24;
  const subtitleLeading = Math.floor((termWidth - subtitleWidth) / 2);

  // 把每行 rstrip 后, 用 ZWJ 补齐到 61 (ZWJ 0 宽度, 不影响视觉)
  const lines: string[] = [];
  for (let i = 0; i < WORDMARK.length; i++) {
    const rstrip = WORDMARK[i].replace(/ +$/, '');
    const padding = logoWidth - rstrip.length;
    lines.push(rstrip + '\u200D'.repeat(padding));
  }

  return (
    <Box flexDirection="column" alignItems="flex-start" width={termWidth} paddingTop={1} paddingBottom={1}>
      {lines.map((line, i) => (
        <Text key={i} color={i === 0 ? '#FFB6C1' : '#FF69B4'} bold>{' '.repeat(logoLeading) + line}</Text>
      ))}
      <Box marginTop={1} marginBottom={1}>
        <Text>{' '.repeat(subtitleLeading)}</Text>
        <Text color="#FFB6C1">{'\u2726 '}</Text>
        <Text color="#FF69B4">General-Purpose AI Agent</Text>
        <Text color="#FFB6C1">{' \u2726'}</Text>
      </Box>
    </Box>
  );
});
