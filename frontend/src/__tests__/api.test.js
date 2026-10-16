import { describe, it, expect, vi, afterEach } from 'vitest'
import { analyzePhoto, getHealth, ApiError } from '../api.js'

const jsonResponse = (status, body) => ({ ok: status < 400, status, json: async () => body, text: async () => JSON.stringify(body) })

afterEach(() => vi.restoreAllMocks())

describe('api.js', () => {
  it('posts the photo as multipart field "photo" to /api/analyze with xai=true', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(200, { items: [] }))
    await analyzePhoto(new File([new Uint8Array([1, 2])], 'a.jpg', { type: 'image/jpeg' }))
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/analyze\?xai=true$/)
    expect(opts.method).toBe('POST')
    expect(opts.body.get('photo')).toBeInstanceOf(File)
  })

  it('surfaces the backend structured error message and code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(503, { detail: { code: 'model_unavailable', message: 'The analysis model is not loaded.' } }))
    const err = await analyzePhoto(new Blob([1])).catch(e => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(503)
    expect(err.code).toBe('model_unavailable')
    expect(err.message).toBe('The analysis model is not loaded.')
  })

  it('reports a network error clearly when the backend is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const err = await getHealth().catch(e => e)
    expect(err.code).toBe('network_error')
    expect(err.message).toMatch(/Could not reach the analysis backend/)
  })

  it('handles non-JSON error bodies', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 500, json: async () => { throw new Error('x') } })
    const err = await getHealth().catch(e => e)
    expect(err.status).toBe(500)
    expect(err.message).toMatch(/HTTP 500/)
  })
})
