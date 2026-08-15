import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  formatTokenCount,
  formatUsageRate,
  isStartupProgress,
  modelStatusLabel,
  shouldShowStartupProgress,
  visibleRunProgress
} from './taskPresentation.mts'

test('formatTokenCount makes absent usage explicit instead of presenting zero', () => {
  assert.equal(formatTokenCount(null), 'not reported')
  assert.equal(formatTokenCount(0), '0')
  assert.equal(formatTokenCount(12_340), '12.3k')
})

test('formatUsageRate only calculates cache rate from reported positive input', () => {
  assert.equal(formatUsageRate({ inputTokens: 200, cacheHitTokens: 50 }), '25%')
  assert.equal(formatUsageRate({ inputTokens: null, cacheHitTokens: 0 }), 'not reported')
  assert.equal(formatUsageRate({ inputTokens: 0, cacheHitTokens: 0 }), 'not reported')
})

test('empty new-task pages do not keep a stale Preparing Agent worker banner', () => {
  assert.equal(shouldShowStartupProgress({
    timelineLength: 0,
    running: false,
    progress: 'Preparing Agent worker…'
  }), false)
  assert.equal(shouldShowStartupProgress({
    timelineLength: 0,
    running: true,
    progress: 'Preparing Agent worker…'
  }), true)
})

test('modelStatusLabel does not flash Model not connected before models/list', () => {
  assert.equal(modelStatusLabel({
    selectedModelId: '',
    loading: true,
    snapshotLoaded: false
  }), 'Connecting model…')
  assert.equal(modelStatusLabel({
    selectedModelId: '',
    loading: false,
    snapshotLoaded: false
  }), 'Connecting model…')
  assert.equal(modelStatusLabel({
    selectedModelId: '',
    loading: false,
    snapshotLoaded: true
  }), 'Model not connected')
  assert.equal(modelStatusLabel({
    selectedModelId: 'deepseek/deepseek-v4-flash',
    loading: true,
    snapshotLoaded: false
  }), 'deepseek/deepseek-v4-flash')
})

test('visibleRunProgress drops leftover startup text once the timeline has real work', () => {
  assert.equal(isStartupProgress('Starting Agent worker…'), true)
  assert.equal(visibleRunProgress({
    progress: 'Starting Agent worker…',
    timelineLength: 1
  }), 'Starting Agent worker…')
  assert.equal(visibleRunProgress({
    progress: 'Starting Agent worker…',
    timelineLength: 5
  }), null)
  assert.equal(visibleRunProgress({
    progress: '正在处理 write',
    timelineLength: 5
  }), '正在处理 write')
})
