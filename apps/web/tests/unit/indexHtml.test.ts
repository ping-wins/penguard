import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('index.html', () => {
  it('uses FortiDashboard as the initial browser title', () => {
    const html = readFileSync(resolve(__dirname, '../../index.html'), 'utf8')

    expect(html).toContain('<title>FortiDashboard</title>')
  })
})
