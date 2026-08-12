import { test } from 'node:test'
import assert from 'node:assert/strict'
import { groupModelsByProvider, modelGroupLabel } from './modelPresentation.mts'

const model = (overrides: Record<string, unknown> = {}) => ({
  id: 'model-1',
  name: 'model-1',
  nickname: '',
  provider_model_id: 'model-1',
  base_url: 'https://custom.example/v1',
  active: false,
  category: '其他',
  provider_name: '其他',
  provider_id: 'custom',
  ...overrides
})

test('custom and empty provider metadata use the stable Others group', () => {
  assert.equal(modelGroupLabel(model()), 'Others')
  assert.equal(modelGroupLabel(model({ provider_name: '', provider_id: '' })), 'Others')
})

test('known provider labels stay grouped consistently across the desktop', () => {
  const grouped = groupModelsByProvider([
    model({ id: 'zen-1', provider_name: 'OpenCode Zen', provider_id: 'zen' }),
    model({ id: 'zen-2', provider_name: 'OpenCode Zen', provider_id: 'zen' }),
    model({ id: 'custom-1' })
  ])

  assert.deepEqual(grouped.map(([label, entries]) => [label, entries.map((entry) => entry.id)]), [
    ['OpenCode Zen', ['zen-1', 'zen-2']],
    ['Others', ['custom-1']]
  ])
})
