import http from 'node:http'
import util from 'node:util'

const LOG_SECRET_PATTERNS = [
  [/(MUSIC_U=)[^;,\s"]+/gi, '$1<redacted>'],
  [/("MUSIC_U"\s*:\s*")[^"]+(")/gi, '$1<redacted>$2'],
  [/(MUSIC_R_U=)[^;,\s"]+/gi, '$1<redacted>'],
  [/("MUSIC_R_U"\s*:\s*")[^"]+(")/gi, '$1<redacted>$2'],
  [/(__csrf=)[^;,\s"]+/gi, '$1<redacted>'],
  [/("__csrf"\s*:\s*")[^"]+(")/gi, '$1<redacted>$2'],
]

function redactLogSecrets(text) {
  let output = String(text ?? '')
  for (const [pattern, replacement] of LOG_SECRET_PATTERNS) {
    output = output.replace(pattern, replacement)
  }
  return output
}

function patchConsoleMethod(methodName) {
  const original = console[methodName].bind(console)
  console[methodName] = (...args) => {
    original(redactLogSecrets(util.format(...args)))
  }
}

patchConsoleMethod('log')
patchConsoleMethod('warn')
patchConsoleMethod('error')

const { default: NCMModule } = await import('NeteaseCloudMusicApi')
const NCM = NCMModule?.default ?? NCMModule

const host = process.env.NCM_RPC_HOST || '127.0.0.1'
const port = Number.parseInt(process.env.NCM_RPC_PORT || '37231', 10)

const proxyKeys = [
  'http_proxy',
  'https_proxy',
  'HTTP_PROXY',
  'HTTPS_PROXY',
]

if ((process.env.NCM_RPC_DISABLE_PROXY || '1') !== '0') {
  for (const key of proxyKeys) {
    process.env[key] = ''
  }
}

const noProxy = new Set(
  String(process.env.NO_PROXY || process.env.no_proxy || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean),
)
noProxy.add('127.0.0.1')
noProxy.add('localhost')
process.env.NO_PROXY = Array.from(noProxy).join(',')
process.env.no_proxy = process.env.NO_PROXY

function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload)
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'Content-Length': Buffer.byteLength(body),
  })
  res.end(body)
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    req.on('data', (chunk) => {
      chunks.push(chunk)
    })
    req.on('end', () => {
      resolve(Buffer.concat(chunks).toString('utf8'))
    })
    req.on('error', reject)
  })
}

function sanitizeParams(rawParams) {
  const params =
    rawParams && typeof rawParams === 'object' && !Array.isArray(rawParams)
      ? { ...rawParams }
      : {}

  const env =
    params.__env && typeof params.__env === 'object'
      ? params.__env
      : params.env && typeof params.env === 'object'
        ? params.env
        : null

  delete params.__env
  delete params.env

  if (env && !params.realIP) {
    const cnIp = String(env.cnIp || '').trim()
    if (cnIp) {
      params.realIP = cnIp
    }
  }

  return params
}

function serializeResult(result) {
  if (!result || typeof result !== 'object') {
    return {
      status: 200,
      body: result,
      cookie: null,
    }
  }

  return {
    status: Number(result.status || 200),
    body: result.body ?? {},
    cookie: result.cookie ?? result.body?.cookie ?? null,
  }
}

async function handleCall(payload) {
  const method = String(payload?.method || '').trim()
  if (!method) {
    throw new Error('missing_method')
  }

  const fn = NCM[method]
  if (typeof fn !== 'function') {
    throw new Error(`unknown_method:${method}`)
  }

  const params = sanitizeParams(payload?.params)
  const result = await fn(params)
  return serializeResult(result)
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === 'GET' && req.url === '/health') {
      return sendJson(res, 200, { ok: true, status: 'ready' })
    }

    if (req.method === 'POST' && req.url === '/call') {
      const rawBody = await readRequestBody(req)
      const payload = rawBody ? JSON.parse(rawBody) : {}
      const result = await handleCall(payload)
      return sendJson(res, 200, {
        ok: true,
        ...result,
      })
    }

    return sendJson(res, 404, { ok: false, error: 'not_found' })
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    const stack = error instanceof Error ? error.stack : ''
    console.error('[ncm-rpc] request failed:', message)
    if (stack) {
      console.error(stack)
    }
    return sendJson(res, 500, {
      ok: false,
      error: message,
    })
  }
})

server.listen(port, host, () => {
  console.log(`[ncm-rpc] listening on http://${host}:${port}`)
})
