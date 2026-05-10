const INTERNAL_FAILURE_MARKERS = [
  'access violation',
  'maximum call stack',
  'failed to register environment variables',
  'error during request setup',
  'anonymous registration',
  'reasoning_content',
  'not a function',
  'song_play_temporarily_unavailable',
  'song_lyrics_temporarily_unavailable',
  'resolve_song_',
  'nativecommanderror',
  'url using bad/illegal format',
]

const DEFAULT_BACKEND_ERROR = '后端服务刚刚出错了，请稍后再试。'
const keyValueLinePattern = /^[^：:\n]{1,14}[：:]/
const urlLinePattern = /^https?:\/\//i

export function looksLikeInternalFailureText(value) {
  const text = String(value || '').trim().toLowerCase()
  if (!text) return false
  return INTERNAL_FAILURE_MARKERS.some((marker) => text.includes(marker))
}

export function sanitizeInternalFailureText(value, fallback = DEFAULT_BACKEND_ERROR) {
  const text = String(value || '').trim()
  if (!text) return ''
  return looksLikeInternalFailureText(text) ? fallback : text
}

export function normalizeRole(role) {
  const value = String(role || '').toLowerCase().trim()
  if (['user', 'human', 'client', 'me', '用户'].includes(value)) return 'user'
  return 'assistant'
}

export function isUserRole(role) {
  return normalizeRole(role) === 'user'
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function normalizeLikedSong(song, index = 0) {
  if (!song || typeof song !== 'object' || Array.isArray(song)) return null
  const id = String(song.id ?? '').trim()
  const name = String(song.name ?? '').trim()
  if (!id || !name) return null
  const artistSource = Array.isArray(song.artist)
    ? song.artist.map((item) => {
        if (item && typeof item === 'object') return String(item.name ?? '').trim()
        return String(item ?? '').trim()
      }).filter(Boolean).join(' / ')
    : Array.isArray(song.artists)
      ? song.artists.map((item) => {
          if (item && typeof item === 'object') return String(item.name ?? '').trim()
          return String(item ?? '').trim()
        }).filter(Boolean).join(' / ')
      : String(song.artist ?? song.artist_name ?? song.artistName ?? song['歌手name'] ?? '').trim()
  const durationValue = song.duration_ms ?? song.durationMs ?? song.duration ?? null
  const normalizedDuration = durationValue == null || durationValue === '' ? null : Number(durationValue)
  const safePlayUrl = `/agent/songs/${id}/play?level=jymaster&prefer=stream&mode=redirect`
  return {
    ...song,
    id,
    rank: Number(song.rank) > 0 ? Number(song.rank) : index + 1,
    name,
    artist: artistSource,
    album: String(song.album ?? '').trim(),
    cover_url: String(song.cover_url ?? song.coverUrl ?? '').trim(),
    play_url: safePlayUrl,
    duration_ms: Number.isFinite(normalizedDuration) ? normalizedDuration : null,
  }
}

export function normalizeLyricLine(line) {
  if (!line || typeof line !== 'object' || Array.isArray(line)) return null
  const text = String(line.text ?? '').trim()
  if (!text) return null
  const timeValue = line.time == null ? null : Number(line.time)
  return {
    text,
    time: Number.isFinite(timeValue) ? timeValue : null,
  }
}

function normalizeCountValue(value) {
  if (value == null || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : String(value).trim() || null
}

function normalizeSongListPayload(payload) {
  const itemsSource = Array.isArray(payload.items)
    ? payload.items
    : Array.isArray(payload.songs)
      ? payload.songs
      : []
  const items = itemsSource.map((song, index) => normalizeLikedSong(song, index)).filter(Boolean)
  return {
    ...payload,
    kind: 'song_list',
    title: String(payload.title ?? '').trim(),
    summary: String(payload.summary ?? '').trim(),
    total: Number(payload.total) > 0 ? Number(payload.total) : items.length,
    items,
  }
}

function normalizePlaylistItem(item, index = 0) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null
  const id = String(item.id ?? item.playlist_id ?? item.playlistId ?? '').trim()
  const name = String(item.name ?? item.title ?? '').trim()
  if (!id || !name) return null
  return {
    ...item,
    id,
    rank: Number(item.rank) > 0 ? Number(item.rank) : index + 1,
    name,
    cover_url: String(item.cover_url ?? item.coverUrl ?? '').trim(),
    description: String(item.description ?? item['描述'] ?? '').trim(),
    track_count: normalizeCountValue(item.track_count ?? item.trackCount ?? item.song_count ?? item.songCount ?? item['歌曲数量'] ?? item['歌曲数']),
    play_count: normalizeCountValue(item.play_count ?? item.playCount ?? item.playcount ?? item['播放量']),
  }
}

function normalizePlaylistListPayload(payload) {
  const items = Array.isArray(payload.items)
    ? payload.items.map((item, index) => normalizePlaylistItem(item, index)).filter(Boolean)
    : []
  return {
    ...payload,
    kind: 'playlist_list',
    title: String(payload.title ?? '').trim(),
    summary: String(payload.summary ?? '').trim(),
    total: Number(payload.total) > 0 ? Number(payload.total) : items.length,
    items,
  }
}

function normalizeAlbumItem(item, index = 0) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null
  const id = String(item.id ?? item.album_id ?? item.albumId ?? '').trim()
  const name = String(item.name ?? item.title ?? '').trim()
  if (!id || !name) return null
  return {
    ...item,
    id,
    rank: Number(item.rank) > 0 ? Number(item.rank) : index + 1,
    name,
    artist: String(item.artist ?? item.artist_name ?? item.artistName ?? '').trim(),
    cover_url: String(item.cover_url ?? item.coverUrl ?? item.picUrl ?? '').trim(),
    publish_time: String(item.publish_time ?? item.publishTime ?? item.publish_date ?? item.publishDate ?? '').trim(),
    description: String(item.description ?? '').trim(),
    size: normalizeCountValue(item.size ?? item.song_count ?? item.songCount ?? item.track_count ?? item.trackCount),
  }
}

function normalizeAlbumListPayload(payload) {
  const items = Array.isArray(payload.items)
    ? payload.items.map((item, index) => normalizeAlbumItem(item, index)).filter(Boolean)
    : []
  return {
    ...payload,
    kind: 'album_list',
    title: String(payload.title ?? '').trim(),
    summary: String(payload.summary ?? '').trim(),
    total: Number(payload.total) > 0 ? Number(payload.total) : items.length,
    items,
  }
}

export function normalizePayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null
  if (payload.kind === 'liked_songs' || payload.kind === 'song_list') return normalizeSongListPayload(payload)
  if (payload.kind === 'playlist_list') return normalizePlaylistListPayload(payload)
  if (payload.kind === 'album_list') return normalizeAlbumListPayload(payload)
  return { ...payload }
}

export function normalizeMessage(message) {
  if (!message) return null
  const role = normalizeRole(message.role)
  const content = message.content == null ? '' : String(message.content)
  return {
    ...message,
    role,
    content:
      role === 'user'
        ? content
        : sanitizeInternalFailureText(content, DEFAULT_BACKEND_ERROR),
    timestamp: message.created_at || message.timestamp || new Date().toISOString(),
    payload: normalizePayload(message.payload),
    pending: !!message.pending,
  }
}

export function hasRichContent(message) {
  const payload = message?.payload
  if (!payload || typeof payload !== 'object') return false
  if (payload.kind === 'song_list') return Array.isArray(payload.items) && payload.items.length > 0
  if (payload.kind === 'playlist_list') return Array.isArray(payload.items) && payload.items.length > 0
  if (payload.kind === 'album_list') return Array.isArray(payload.items) && payload.items.length > 0
  return true
}

export function getLikedSongsPayload(message) {
  return getSongListPayload(message)
}

export function getSongListPayload(message) {
  const payload = message?.payload
  return payload?.kind === 'song_list' && Array.isArray(payload.items) && payload.items.length > 0 ? payload : null
}

export function getPlaylistListPayload(message) {
  const payload = message?.payload
  return payload?.kind === 'playlist_list' && Array.isArray(payload.items) && payload.items.length > 0 ? payload : null
}

export function getAlbumListPayload(message) {
  const payload = message?.payload
  return payload?.kind === 'album_list' && Array.isArray(payload.items) && payload.items.length > 0 ? payload : null
}

function linkifyEscapedText(text) {
  return escapeHtml(text == null ? '' : String(text)).replace(
    /(https?:\/\/[^\s<]+[^<.,;:\s)\]\}])/g,
    '<a class="msg-link" href="$1" target="_blank" rel="noopener noreferrer">$1</a>',
  )
}

function isKeyValueLine(line) {
  return keyValueLinePattern.test(String(line || '').trim())
}

function isUrlLine(line) {
  return urlLinePattern.test(String(line || '').trim())
}

function renderKeyValueRows(lines) {
  const rows = lines
    .map((line) => String(line || '').trim())
    .filter(Boolean)
    .map((line) => {
      const separator = line.includes('：') ? '：' : ':'
      const index = line.indexOf(separator)
      if (index <= 0) {
        return `<div class="msg-kv-row">${linkifyEscapedText(line)}</div>`
      }
      const label = line.slice(0, index + 1)
      const value = line.slice(index + 1).trimStart()
      return `
        <div class="msg-kv-row">
          <span class="msg-kv-label">${escapeHtml(label)}</span>
          <span class="msg-kv-value">${linkifyEscapedText(value)}</span>
        </div>
      `
    })
    .join('')

  return `<div class="msg-kv-list">${rows}</div>`
}

function renderMessageBlock(block) {
  const lines = String(block || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  if (!lines.length) return ''

  const first = lines[0]
  const rest = lines.slice(1)
  const hasTitle = /[：:]$/.test(first)

  if (hasTitle && rest.length > 0 && isUrlLine(rest[0])) {
    const urlLine = rest[0]
    const metaLines = rest.slice(1)
    return `
      <section class="msg-block is-link">
        <div class="msg-title">${linkifyEscapedText(first)}</div>
        <div class="msg-link-row">${linkifyEscapedText(urlLine)}</div>
        ${metaLines.length ? renderKeyValueRows(metaLines) : ''}
      </section>
    `
  }

  if (hasTitle && rest.length > 0 && rest.every((line) => isKeyValueLine(line))) {
    return `
      <section class="msg-block is-kv">
        <div class="msg-title">${linkifyEscapedText(first)}</div>
        ${renderKeyValueRows(rest)}
      </section>
    `
  }

  if (hasTitle && rest.length > 0 && rest.every((line) => !isKeyValueLine(line) && !isUrlLine(line))) {
    const items = rest
      .map((line) => `<li class="msg-list-item">${linkifyEscapedText(line)}</li>`)
      .join('')
    return `
      <section class="msg-block is-list">
        <div class="msg-title">${linkifyEscapedText(first)}</div>
        <ul class="msg-list">${items}</ul>
      </section>
    `
  }

  if (lines.every((line) => isKeyValueLine(line))) {
    return `<section class="msg-block is-kv">${renderKeyValueRows(lines)}</section>`
  }

  return `<p class="msg-paragraph">${lines.map((line) => linkifyEscapedText(line)).join('<br/>')}</p>`
}

export function renderMessageHtml(text) {
  const normalized = String(text == null ? '' : text).replace(/\r\n/g, '\n').trim()
  if (!normalized) return ''
  const blocks = normalized.split(/\n{2,}/).filter((block) => block.trim())
  return blocks.map((block) => renderMessageBlock(block)).join('')
}

export function formatAxiosError(error) {
  const status = error.response?.status
  if (
    error?.code === 'BACKEND_NOT_READY' ||
    error?.message === 'backend_not_ready' ||
    error?.message === 'backend_wait_aborted'
  ) {
    return '后端正在启动，请稍等片刻后再试。'
  }
  if (status === 502 || status === 503) {
    return '后端暂时不可用，请先启动服务后再重试。'
  }
  if (error.response?.data != null) {
    const detail = error.response.data.detail
    if (typeof detail === 'string') {
      if (looksLikeInternalFailureText(detail)) {
        return DEFAULT_BACKEND_ERROR
      }
      return detail
    }
    if (Array.isArray(detail)) return detail.map((item) => item.msg || JSON.stringify(item)).join('；')
    if (error.response.data.message) return sanitizeInternalFailureText(error.response.data.message)
  }
  if (error.code === 'ECONNABORTED') return '请求超时，请稍后重试。'
  if (error.message?.includes('Network') || error.code === 'ERR_NETWORK' || error.message === 'Network Error') {
    return '无法连接后端，请确认服务已经启动。'
  }
  if (looksLikeInternalFailureText(error.message)) {
    return DEFAULT_BACKEND_ERROR
  }
  return error.message || '请求失败'
}
