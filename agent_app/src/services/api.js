import axios from 'axios'

const BACKEND_READY_TIMEOUT_MS = 12000
const BACKEND_READY_RETRY_INTERVAL_MS = 250

let backendReady = false
let backendReadyPromise = null

function resolveBaseURL() {
  const fromEnv = import.meta.env.VITE_API_BASE_URL
  if (fromEnv) return fromEnv.replace(/\/$/, '')
  if (import.meta.env.DEV) return '/api'
  return 'http://127.0.0.1:8002'
}

function resolveBackendOrigin() {
  const readyFromEnv = import.meta.env.VITE_API_READY_URL
  if (readyFromEnv) return readyFromEnv.replace(/\/$/, '')

  const fromEnv = import.meta.env.VITE_API_BASE_URL
  if (fromEnv && /^https?:\/\//i.test(fromEnv)) {
    return fromEnv.replace(/\/$/, '')
  }

  if (import.meta.env.DEV) return 'http://127.0.0.1:8002'
  return resolveBaseURL()
}

function resolveUrl(path = '') {
  const value = String(path || '').trim()
  if (!value) return ''
  if (/^https?:\/\//i.test(value)) return value
  const base = resolveBaseURL()
  if (value.startsWith('/')) return `${base}${value}`
  return `${base}/${value}`
}

function resolveHealthcheckURL() {
  const base = resolveBackendOrigin()
  if (base.startsWith('/')) return resolveUrl('/healthz')
  return `${base}/healthz`
}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup()
      resolve()
    }, ms)

    const cleanup = () => {
      window.clearTimeout(timer)
      signal?.removeEventListener?.('abort', onAbort)
    }

    const onAbort = () => {
      cleanup()
      const error = new Error('backend_wait_aborted')
      error.name = 'AbortError'
      reject(error)
    }

    if (signal?.aborted) {
      onAbort()
      return
    }

    signal?.addEventListener?.('abort', onAbort, { once: true })
  })
}

async function pingBackend(signal) {
  const response = await fetch(resolveHealthcheckURL(), {
    method: 'GET',
    cache: 'no-store',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    const error = new Error(`backend_healthcheck_failed_${response.status}`)
    error.response = { status: response.status, data: { detail: `HTTP ${response.status}` } }
    throw error
  }
}

async function waitForBackendReady({ signal, timeoutMs = BACKEND_READY_TIMEOUT_MS } = {}) {
  if (backendReady) return
  if (backendReadyPromise) {
    await backendReadyPromise
    return
  }

  backendReadyPromise = (async () => {
    const deadline = Date.now() + timeoutMs
    let lastError = null

    while (Date.now() < deadline) {
      if (signal?.aborted) {
        const aborted = new Error('backend_wait_aborted')
        aborted.name = 'AbortError'
        throw aborted
      }

      try {
        await pingBackend(signal)
        backendReady = true
        return
      } catch (error) {
        lastError = error
      }

      const remaining = deadline - Date.now()
      if (remaining <= 0) break
      await sleep(Math.min(BACKEND_READY_RETRY_INTERVAL_MS, remaining), signal)
    }

    const timeoutError = lastError || new Error('backend_not_ready')
    timeoutError.code = timeoutError.code || 'BACKEND_NOT_READY'
    throw timeoutError
  })()

  try {
    await backendReadyPromise
  } finally {
    backendReadyPromise = null
  }
}

function isRetryableBackendError(error) {
  const status = Number(error?.response?.status)
  if ([502, 503, 504].includes(status)) return true

  const code = String(error?.code || '').toUpperCase()
  if (['ERR_NETWORK', 'ECONNABORTED', 'BACKEND_NOT_READY'].includes(code)) return true

  const message = String(error?.message || '').toLowerCase()
  return (
    message.includes('network error') ||
    message.includes('failed to fetch') ||
    message.includes('backend_not_ready') ||
    message.includes('backend_healthcheck_failed')
  )
}

async function runWithBackendRetry(run, { signal, waitUntilReady = false } = {}) {
  if (waitUntilReady && !backendReady) {
    try {
      await waitForBackendReady({ signal })
    } catch {
      // Let the real request surface the final error if readiness polling timed out.
    }
  }

  try {
    const result = await run()
    backendReady = true
    return result
  } catch (error) {
    if (!isRetryableBackendError(error)) throw error
    backendReady = false
    await waitForBackendReady({ signal })
    const result = await run()
    backendReady = true
    return result
  }
}

const api = axios.create({
  baseURL: resolveBaseURL(),
  timeout: 600000,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error)
    return Promise.reject(error)
  },
)

async function buildStreamError(response) {
  let detail = `HTTP ${response.status}`
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') detail = data.detail
    else if (typeof data?.message === 'string') detail = data.message
  } catch {
    // ignore parse error
  }
  const error = new Error(detail)
  error.response = { status: response.status, data: { detail } }
  return error
}

export const agentApi = {
  resolveUrl,

  createConversation: (title = '') =>
    runWithBackendRetry(() => api.post('/agent/conversations', { title }), { waitUntilReady: true }),

  listConversations: (params = {}) =>
    runWithBackendRetry(() => api.get('/agent/conversations', { params }), { waitUntilReady: true }),

  getConversationMessages: (conversationId, params = {}) =>
    runWithBackendRetry(() => api.get(`/agent/conversations/${conversationId}/messages`, { params }), { waitUntilReady: true }),

  getSongLyrics: (songId) =>
    runWithBackendRetry(() => api.get(`/agent/songs/${songId}/lyrics`), { waitUntilReady: true }),

  getHeartModeQueue: (params = {}) =>
    runWithBackendRetry(() => api.get('/agent/player/heart-mode', { params }), { waitUntilReady: true }),

  getPlaylistTracks: (playlistId, params = {}) =>
    runWithBackendRetry(() => api.get(`/agent/playlists/${playlistId}/tracks`, { params }), { waitUntilReady: true }),

  getUserProfile: () =>
    runWithBackendRetry(() => api.get('/agent/user/profile'), { waitUntilReady: true }),

  renameConversation: (conversationId, title) =>
    runWithBackendRetry(() => api.patch(`/agent/conversations/${conversationId}`, { title }), { waitUntilReady: true }),

  deleteConversation: (conversationId) =>
    runWithBackendRetry(() => api.delete(`/agent/conversations/${conversationId}`), { waitUntilReady: true }),

  chat: (message, conversationId = null, clientContext = null) =>
    runWithBackendRetry(
      () => api.post('/agent/chat', {
        message,
        conversation_id: conversationId,
        client_context: clientContext,
      }),
      { waitUntilReady: true },
    ),

  chatStream: async (message, conversationId = null, { onEvent, signal, clientContext = null } = {}) => {
    return runWithBackendRetry(async () => {
      const response = await fetch(`${resolveBaseURL()}/agent/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
          client_context: clientContext,
        }),
        signal,
      })

      if (!response.ok) {
        throw await buildStreamError(response)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('stream_reader_unavailable')
      }

      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      const finalState = {
        success: false,
        reply: '',
        conversation_id: conversationId,
        conversation: null,
        memory_summary: '',
        message: null,
        metrics: null,
      }

      const separatorIndex = (text) => {
        const lf = text.indexOf('\n\n')
        const crlf = text.indexOf('\r\n\r\n')
        if (lf === -1) return crlf
        if (crlf === -1) return lf
        return Math.min(lf, crlf)
      }

      const flush = (chunk) => {
        buffer += chunk
        let index
        while ((index = separatorIndex(buffer)) >= 0) {
          const separatorLength = buffer.slice(index, index + 4) === '\r\n\r\n' ? 4 : 2
          const rawEvent = buffer.slice(0, index)
          buffer = buffer.slice(index + separatorLength)

          const lines = rawEvent.split(/\r?\n/)
          let event = 'message'
          let dataLine = ''
          for (const line of lines) {
            if (line.startsWith(':')) continue
            if (line.startsWith('event:')) event = line.slice(6).trim()
            if (line.startsWith('data:')) dataLine += `${dataLine ? '\n' : ''}${line.slice(5).trimStart()}`
          }

          let data = {}
          try {
            data = dataLine ? JSON.parse(dataLine) : {}
          } catch {
            data = { raw: dataLine }
          }

          onEvent?.(event, data)

          if (event === 'meta') {
            if (data.conversation_id) finalState.conversation_id = data.conversation_id
            if (data.conversation) finalState.conversation = data.conversation
          }
          if (event === 'delta' && typeof data.text === 'string') {
            finalState.reply += data.text
          }
          if (event === 'final' && typeof data.text === 'string') {
            finalState.reply = data.text
          }
          if (event === 'memory' && typeof data.memory_summary === 'string') {
            finalState.memory_summary = data.memory_summary
          }
          if (event === 'metrics' && data.metrics) {
            finalState.metrics = data.metrics
          }
          if (event === 'message_commit' && data.message) {
            finalState.message = data.message
          }
          if (event === 'done') {
            finalState.success = !!data.success
            if (data.metrics) finalState.metrics = data.metrics
          }
          if (event === 'error') {
            throw new Error(data.message || 'stream_error')
          }
        }
      }

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        flush(decoder.decode(value, { stream: true }))
      }
      flush(decoder.decode())

      return finalState
    }, { signal, waitUntilReady: true })
  },
}

export default api
