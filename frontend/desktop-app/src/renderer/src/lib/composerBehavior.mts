export function canSubmitComposer(input: {
  disabled: boolean
  running: boolean
  text: string
}): boolean {
  return !input.disabled && !input.running && input.text.trim() !== ''
}

export function shouldSubmitOnKey(input: {
  key: string
  shiftKey: boolean
  running: boolean
}): boolean {
  return input.key === 'Enter' && !input.shiftKey && !input.running
}
