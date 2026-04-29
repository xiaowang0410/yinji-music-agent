const FALLBACK_THEME = Object.freeze({
  bgBase: { r: 15, g: 17, b: 26 },
  bgPrimary: { r: 132, g: 74, b: 105 },
  bgSecondary: { r: 73, g: 88, b: 153 },
  accent: { r: 255, g: 93, b: 141 },
  accentSoft: { r: 193, g: 102, b: 136 },
  highlight: { r: 255, g: 176, b: 198 },
  dominant: { r: 172, g: 97, b: 133 },
  secondary: { r: 78, g: 94, b: 163 },
})

const THEME_CACHE = new Map()
const MAX_CACHE_SIZE = 48

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function componentToHex(value) {
  return clamp(Math.round(value), 0, 255).toString(16).padStart(2, '0')
}

function rgbToCss(rgb) {
  return `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`
}

function rgbToTriplet(rgb) {
  return `${rgb.r}, ${rgb.g}, ${rgb.b}`
}

function mixRgb(first, second, weight = 0.5) {
  const ratio = clamp(Number(weight) || 0, 0, 1)
  return {
    r: Math.round(first.r * (1 - ratio) + second.r * ratio),
    g: Math.round(first.g * (1 - ratio) + second.g * ratio),
    b: Math.round(first.b * (1 - ratio) + second.b * ratio),
  }
}

function rgbToHsl(rgb) {
  const r = clamp(rgb.r, 0, 255) / 255
  const g = clamp(rgb.g, 0, 255) / 255
  const b = clamp(rgb.b, 0, 255) / 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const delta = max - min

  let h = 0
  const l = (max + min) / 2
  let s = 0

  if (delta !== 0) {
    s = delta / (1 - Math.abs(2 * l - 1))
    switch (max) {
      case r:
        h = 60 * (((g - b) / delta) % 6)
        break
      case g:
        h = 60 * ((b - r) / delta + 2)
        break
      default:
        h = 60 * ((r - g) / delta + 4)
        break
    }
  }

  return {
    h: (h + 360) % 360,
    s: Math.round(s * 100),
    l: Math.round(l * 100),
  }
}

function hslToRgb(hsl) {
  const h = ((Number(hsl.h) || 0) % 360 + 360) % 360
  const s = clamp(Number(hsl.s) || 0, 0, 100) / 100
  const l = clamp(Number(hsl.l) || 0, 0, 100) / 100
  const chroma = (1 - Math.abs(2 * l - 1)) * s
  const hueSection = h / 60
  const x = chroma * (1 - Math.abs((hueSection % 2) - 1))

  let r1 = 0
  let g1 = 0
  let b1 = 0

  if (hueSection >= 0 && hueSection < 1) {
    r1 = chroma
    g1 = x
  } else if (hueSection < 2) {
    r1 = x
    g1 = chroma
  } else if (hueSection < 3) {
    g1 = chroma
    b1 = x
  } else if (hueSection < 4) {
    g1 = x
    b1 = chroma
  } else if (hueSection < 5) {
    r1 = x
    b1 = chroma
  } else {
    r1 = chroma
    b1 = x
  }

  const match = l - chroma / 2
  return {
    r: Math.round((r1 + match) * 255),
    g: Math.round((g1 + match) * 255),
    b: Math.round((b1 + match) * 255),
  }
}

function colorDistance(first, second) {
  const dr = first.r - second.r
  const dg = first.g - second.g
  const db = first.b - second.b
  return Math.sqrt(dr * dr + dg * dg + db * db)
}

function quantizeChannel(value) {
  return clamp(Math.round(value / 24) * 24, 0, 255)
}

function normalizeBucketRgb(entry) {
  return {
    r: Math.round(entry.r / entry.count),
    g: Math.round(entry.g / entry.count),
    b: Math.round(entry.b / entry.count),
  }
}

function shouldSkipPixel(rgb, alpha) {
  if (alpha < 140) return true
  const hsl = rgbToHsl(rgb)
  if (hsl.l <= 3) return true
  if (hsl.l >= 98 && hsl.s <= 2) return true
  return false
}

function extractPalette(image, count = 3) {
  if (typeof document === 'undefined') {
    return [FALLBACK_THEME.dominant, FALLBACK_THEME.secondary, FALLBACK_THEME.accent].slice(0, count)
  }

  const canvas = document.createElement('canvas')
  const size = 64
  canvas.width = size
  canvas.height = size

  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) {
    return [FALLBACK_THEME.dominant, FALLBACK_THEME.secondary, FALLBACK_THEME.accent].slice(0, count)
  }

  context.drawImage(image, 0, 0, size, size)
  const { data } = context.getImageData(0, 0, size, size)
  const buckets = new Map()

  for (let index = 0; index < data.length; index += 16) {
    const rgb = {
      r: data[index],
      g: data[index + 1],
      b: data[index + 2],
    }
    const alpha = data[index + 3]
    if (shouldSkipPixel(rgb, alpha)) continue

    const key = `${quantizeChannel(rgb.r)}_${quantizeChannel(rgb.g)}_${quantizeChannel(rgb.b)}`
    if (!buckets.has(key)) {
      buckets.set(key, { count: 0, r: 0, g: 0, b: 0 })
    }
    const bucket = buckets.get(key)
    bucket.count += 1
    bucket.r += rgb.r
    bucket.g += rgb.g
    bucket.b += rgb.b
  }

  const ranked = Array.from(buckets.values())
    .map((entry) => {
      const rgb = normalizeBucketRgb(entry)
      const hsl = rgbToHsl(rgb)
      const contrastBonus = hsl.l > 18 && hsl.l < 84 ? 1.08 : 0.74
      const saturationBonus = 0.7 + hsl.s / 90
      const score = entry.count * saturationBonus * contrastBonus
      return { rgb, hsl, score, count: entry.count }
    })
    .sort((first, second) => second.score - first.score)

  const selected = []
  for (const candidate of ranked) {
    const isDistinct = selected.every((existing) => colorDistance(existing.rgb, candidate.rgb) >= 62)
    if (!isDistinct) continue
    selected.push(candidate)
    if (selected.length >= Math.max(count + 2, 5)) break
  }

  if (!selected.length) {
    return [FALLBACK_THEME.dominant, FALLBACK_THEME.secondary, FALLBACK_THEME.accent].slice(0, count)
  }

  const dominant = selected[0]?.rgb || FALLBACK_THEME.dominant
  const secondary =
    selected.find((entry, index) => index > 0 && colorDistance(entry.rgb, dominant) >= 54)?.rgb ||
    FALLBACK_THEME.secondary

  const accentSource =
    [...selected]
      .sort((first, second) => second.hsl.s - first.hsl.s || second.score - first.score)
      .find((entry) => {
        return colorDistance(entry.rgb, dominant) >= 38 || colorDistance(entry.rgb, secondary) >= 38
      })?.rgb || secondary

  return [dominant, secondary, accentSource].slice(0, count)
}

function adjustColor(hsl, { satBoost = 10, lightDrop = 20 } = {}) {
  return {
    h: hsl.h,
    s: clamp(hsl.s + satBoost, 8, 96),
    l: clamp(hsl.l - lightDrop, 8, 86),
  }
}

function buildThemeFromPalette(palette) {
  const dominant = rgbToHsl(palette[0] || FALLBACK_THEME.dominant)
  const secondary = rgbToHsl(palette[1] || FALLBACK_THEME.secondary)
  const accentSource = rgbToHsl(palette[2] || FALLBACK_THEME.accent)

  const forceDarken = dominant.l > 70 || secondary.l > 70 || accentSource.l > 70

  const bgBase = hslToRgb({
    h: dominant.h,
    s: clamp(Math.round(dominant.s * 0.52), 18, 48),
    l: forceDarken ? 10 : 12,
  })

  const bgPrimary = hslToRgb({
    h: dominant.h,
    s: clamp(dominant.s + 20, 28, 92),
    l: forceDarken ? 26 : 30,
  })

  const bgSecondary = hslToRgb({
    h: secondary.h,
    s: clamp(secondary.s + 12, 20, 84),
    l: forceDarken ? 24 : 28,
  })

  const accent = hslToRgb({
    h: accentSource.h,
    s: clamp(accentSource.s < 14 ? accentSource.s + 24 : accentSource.s + 18, 24, 96),
    l: clamp(
      accentSource.l < 38
        ? accentSource.l + 24
        : accentSource.l > 76
          ? accentSource.l - 18
          : accentSource.l + 8,
      50,
      70,
    ),
  })

  const accentSoft = mixRgb(bgPrimary, accent, 0.42)
  const highlight = mixRgb(accent, { r: 255, g: 255, b: 255 }, 0.34)

  return {
    bgBase,
    bgPrimary,
    bgSecondary,
    accent,
    accentSoft,
    highlight,
    dominant: palette[0] || FALLBACK_THEME.dominant,
    secondary: palette[1] || FALLBACK_THEME.secondary,
  }
}

function trimThemeCache() {
  if (THEME_CACHE.size <= MAX_CACHE_SIZE) return
  const oldestKey = THEME_CACHE.keys().next().value
  if (oldestKey) THEME_CACHE.delete(oldestKey)
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.decoding = 'async'
    image.referrerPolicy = 'no-referrer'
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('cover_image_load_failed'))
    image.src = url
  })
}

export async function loadMusicCoverTheme(coverUrl) {
  const normalizedUrl = String(coverUrl || '').trim()
  if (!normalizedUrl) return FALLBACK_THEME
  if (THEME_CACHE.has(normalizedUrl)) return THEME_CACHE.get(normalizedUrl)

  try {
    const image = await loadImage(normalizedUrl)
    const palette = extractPalette(image, 3)
    const theme = buildThemeFromPalette(palette)
    THEME_CACHE.set(normalizedUrl, theme)
    trimThemeCache()
    return theme
  } catch (error) {
    console.warn('music cover theme fallback:', error)
    THEME_CACHE.set(normalizedUrl, FALLBACK_THEME)
    trimThemeCache()
    return FALLBACK_THEME
  }
}

export function buildMusicCoverThemeStyle(theme, coverUrl = '') {
  const safeTheme = theme || FALLBACK_THEME
  const cover = String(coverUrl || '').trim()
  const style = {
    '--music-theme-bg-base': rgbToCss(safeTheme.bgBase),
    '--music-theme-bg-base-rgb': rgbToTriplet(safeTheme.bgBase),
    '--music-theme-bg-primary': rgbToCss(safeTheme.bgPrimary),
    '--music-theme-bg-primary-rgb': rgbToTriplet(safeTheme.bgPrimary),
    '--music-theme-bg-secondary': rgbToCss(safeTheme.bgSecondary),
    '--music-theme-bg-secondary-rgb': rgbToTriplet(safeTheme.bgSecondary),
    '--music-theme-accent': rgbToCss(safeTheme.accent),
    '--music-theme-accent-rgb': rgbToTriplet(safeTheme.accent),
    '--music-theme-accent-soft': rgbToCss(safeTheme.accentSoft),
    '--music-theme-accent-soft-rgb': rgbToTriplet(safeTheme.accentSoft),
    '--music-theme-highlight': rgbToCss(safeTheme.highlight),
    '--music-theme-highlight-rgb': rgbToTriplet(safeTheme.highlight),
    '--music-theme-cover-shadow': `#${componentToHex(safeTheme.bgBase.r)}${componentToHex(safeTheme.bgBase.g)}${componentToHex(safeTheme.bgBase.b)}`,
  }

  if (cover) {
    style['--music-fullscreen-cover'] = `url("${cover.replace(/"/g, '\\"')}")`
  }

  return style
}

export const DEFAULT_MUSIC_COVER_THEME = FALLBACK_THEME
