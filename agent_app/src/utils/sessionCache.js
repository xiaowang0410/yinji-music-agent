/** 同标签页内刷新仍可用：推荐/喜欢/歌单等列表的短期快照 */
const PREFIX = 'musicapp:'

export function getJson(key, fallback = null) {
  try {
    const raw = sessionStorage.getItem(PREFIX + key)
    if (raw == null) return fallback
    return JSON.parse(raw)
  } catch {
    return fallback
  }
}

export function setJson(key, value) {
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch (e) {
    console.warn('[sessionCache] write failed', key, e)
  }
}

export function removeKey(key) {
  try {
    sessionStorage.removeItem(PREFIX + key)
  } catch {
    /* ignore */
  }
}
