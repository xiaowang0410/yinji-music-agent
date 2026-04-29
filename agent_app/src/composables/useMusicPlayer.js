import { computed, nextTick, ref } from 'vue'
import { agentApi } from '../services/api'
import { normalizeLikedSong, normalizeLyricLine } from '../utils/agentMessage'

function formatPlayerTime(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  const minutes = String(Math.floor(total / 60)).padStart(2, '0')
  const remain = String(total % 60).padStart(2, '0')
  return `${minutes}:${remain}`
}

function buildSongAgentUrl(songId, { level = 'jymaster', prefer = 'stream', mode = 'redirect' } = {}) {
  const normalizedSongId = String(songId || '').trim()
  if (!normalizedSongId) return ''
  const params = new URLSearchParams({ level, prefer, mode })
  return `/agent/songs/${normalizedSongId}/play?${params.toString()}`
}

function resolvePlayableUrl(song) {
  const raw = String(song?.play_url || '').trim()
  if (raw && !/\.flac(?:$|\?)/i.test(raw)) return agentApi.resolveUrl(raw)
  if (song?.id) return agentApi.resolveUrl(buildSongAgentUrl(song.id))
  return ''
}

function resolveCompatibilityUrl(song) {
  if (!song?.id) return ''
  return agentApi.resolveUrl(buildSongAgentUrl(song.id, { level: 'exhigh', prefer: 'download', mode: 'redirect' }))
}

function buildTrackSource(url) {
  return `${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`
}

export function useMusicPlayer() {
  const audioPlayer = ref(null)
  const currentTrack = ref(null)
  const currentQueue = ref([])
  const currentQueueSignature = ref('')
  const pendingSongId = ref('')
  const playerError = ref('')
  const isAudioPlaying = ref(false)
  const isAudioBuffering = ref(false)
  const playerCurrentTime = ref(0)
  const playerDuration = ref(0)
  const playerVolume = ref(0.82)
  const lastVolumeBeforeMute = ref(0.82)
  const currentLyrics = ref([])
  const currentLyricIndex = ref(-1)
  const lyricsLoading = ref(false)
  const lyricsRequestToken = ref(0)
  const playbackOrderMode = ref('sequence')
  const repeatMode = ref('off')
  const playedTrackHistory = ref([])

  function bindAudioPlayer(element) {
    audioPlayer.value = element || null
  }

  function syncCurrentLyricIndex(currentTime = playerCurrentTime.value) {
    if (!currentLyrics.value.length) {
      currentLyricIndex.value = -1
      return
    }

    const timedEntries = currentLyrics.value
      .map((line, index) => ({ index, time: line.time }))
      .filter((entry) => Number.isFinite(entry.time))

    if (!timedEntries.length) {
      currentLyricIndex.value = 0
      return
    }

    let nextIndex = -1
    const safeTime = Math.max(0, Number(currentTime) || 0)
    for (const entry of timedEntries) {
      if (safeTime + 0.08 >= entry.time) {
        nextIndex = entry.index
        continue
      }
      break
    }

    currentLyricIndex.value = nextIndex
  }

  function resetLyricsState() {
    lyricsRequestToken.value += 1
    currentLyrics.value = []
    currentLyricIndex.value = -1
    lyricsLoading.value = false
  }

  function maybeLoadLyricsForCurrentTrack() {
    const songId = String(currentTrack.value?.id || '').trim()
    if (!songId || lyricsLoading.value || currentLyrics.value.length) return
    void loadLyricsForSong(songId)
  }

  async function loadLyricsForSong(songId) {
    const normalizedSongId = String(songId || '').trim()
    lyricsRequestToken.value += 1
    const requestToken = lyricsRequestToken.value
    currentLyrics.value = []
    currentLyricIndex.value = -1

    if (!normalizedSongId) {
      lyricsLoading.value = false
      return
    }

    lyricsLoading.value = true
    try {
      const response = await agentApi.getSongLyrics(normalizedSongId)
      if (requestToken !== lyricsRequestToken.value || String(currentTrack.value?.id || '') !== normalizedSongId) return
      currentLyrics.value = Array.isArray(response.lines)
        ? response.lines.map((line) => normalizeLyricLine(line)).filter(Boolean)
        : []
      syncCurrentLyricIndex(playerCurrentTime.value)
    } catch (error) {
      if (requestToken !== lyricsRequestToken.value || String(currentTrack.value?.id || '') !== normalizedSongId) return
      console.error('load song lyrics error:', error)
      currentLyrics.value = []
      currentLyricIndex.value = -1
    } finally {
      if (requestToken === lyricsRequestToken.value && String(currentTrack.value?.id || '') === normalizedSongId) {
        lyricsLoading.value = false
      }
    }
  }

  function isCurrentTrack(song) {
    if (!song?.id || !currentTrack.value?.id) return false
    return String(song.id) === String(currentTrack.value.id)
  }

  function getQueueSignature(queue) {
    return queue.map((item) => String(item?.id || '').trim()).filter(Boolean).join('|')
  }

  function setCurrentQueue(queue) {
    const normalizedQueue = Array.isArray(queue) ? queue.filter(Boolean) : []
    const signature = getQueueSignature(normalizedQueue)
    if (signature !== currentQueueSignature.value) {
      playedTrackHistory.value = []
    }
    currentQueueSignature.value = signature
    currentQueue.value = normalizedQueue
  }

  function rememberPlaybackHistory(index) {
    if (!Number.isInteger(index) || index < 0) return
    const history = playedTrackHistory.value
    if (history[history.length - 1] === index) return
    playedTrackHistory.value = [...history, index].slice(-80)
  }

  function pickRandomQueueIndex(excludedIndex = -1) {
    const total = currentQueue.value.length
    if (!total) return -1
    if (total === 1) return 0

    let nextIndex = excludedIndex
    let attempts = 0
    while (nextIndex === excludedIndex && attempts < 12) {
      nextIndex = Math.floor(Math.random() * total)
      attempts += 1
    }
    if (nextIndex === excludedIndex) {
      nextIndex = (excludedIndex + 1) % total
    }
    return nextIndex
  }

  async function playSong(song, queue = []) {
    const normalizedSong = normalizeLikedSong(song)
    if (!normalizedSong) return

    const sourceUrl = resolvePlayableUrl(normalizedSong)
    const compatibilityUrl = resolveCompatibilityUrl(normalizedSong)
    if (!sourceUrl) {
      playerError.value = '当前歌曲暂时没有可用的播放地址。'
      return
    }

    const normalizedQueue = Array.isArray(queue)
      ? queue.map((item, index) => normalizeLikedSong(item, index)).filter(Boolean)
      : []
    setCurrentQueue(normalizedQueue.length ? normalizedQueue : [normalizedSong])

    const audio = audioPlayer.value
    const sameTrack = isCurrentTrack(normalizedSong) && audio?.src
    playerError.value = ''

    if (sameTrack) {
      try {
        if (audio.paused) {
          pendingSongId.value = normalizedSong.id
          isAudioBuffering.value = true
          await audio.play()
        } else {
          pendingSongId.value = ''
          isAudioBuffering.value = false
          audio.pause()
        }
      } catch (error) {
        console.error('toggle track error:', error)
        playerError.value = '这首歌暂时无法自动播放。'
        pendingSongId.value = ''
        isAudioBuffering.value = false
      }
      return
    }

    currentTrack.value = {
      ...normalizedSong,
      sourceUrl: buildTrackSource(sourceUrl),
      compatibilitySourceUrl: compatibilityUrl ? buildTrackSource(compatibilityUrl) : '',
      sourceMode: 'preferred',
    }
    playerCurrentTime.value = 0
    playerDuration.value = 0
    isAudioPlaying.value = false
    isAudioBuffering.value = true
    pendingSongId.value = normalizedSong.id
    resetLyricsState()

    await nextTick()

    const target = audioPlayer.value
    if (!target) {
      playerError.value = '播放器还没有准备好，请再点一次试试。'
      pendingSongId.value = ''
      isAudioBuffering.value = false
      return
    }

    try {
      target.pause()
      target.src = currentTrack.value.sourceUrl
      target.volume = playerVolume.value
      target.load()
      await target.play()
    } catch (error) {
      console.error('play song error:', error)
      playerError.value = '这首歌暂时无法播放。'
      pendingSongId.value = ''
      isAudioBuffering.value = false
    }
  }

  const currentTrackIndex = computed(() => {
    if (!currentTrack.value?.id) return -1
    return currentQueue.value.findIndex((item) => String(item.id) === String(currentTrack.value.id))
  })

  const hasActiveTrack = computed(() => !!currentTrack.value)
  const playerStatusText = computed(() => {
    if (playerError.value) return '播放失败'
    if (pendingSongId.value || isAudioBuffering.value) return '正在加载'
    if (isAudioPlaying.value) return '正在播放'
    if (hasActiveTrack.value) return '已暂停'
    return '等待播放'
  })
  const isMuted = computed(() => playerVolume.value <= 0.001)
  const progressRatio = computed(() => {
    if (!hasActiveTrack.value || playerDuration.value <= 0) return 0
    const ratio = (playerCurrentTime.value / playerDuration.value) * 100
    return Math.max(0, Math.min(100, ratio))
  })
  const volumeRatio = computed(() => Math.max(0, Math.min(100, playerVolume.value * 100)))
  const playerDisplayTrack = computed(() => {
    if (currentTrack.value) {
      return currentTrack.value
    }
    return {
      name: '还没有播放歌曲',
      artist: '点右上角心动模式，或点一下歌曲列表，这里就会开始播放。',
      album: '',
      cover_url: '',
    }
  })
  const hasLyricsAvailable = computed(() => currentLyrics.value.length > 0)
  const activeLyricLine = computed(() => {
    if (!hasActiveTrack.value) return ''
    if (lyricsLoading.value) return '正在同步歌词...'
    if (!currentLyrics.value.length) return '暂无同步歌词'
    const activeIndex = currentLyricIndex.value >= 0 ? currentLyricIndex.value : 0
    return currentLyrics.value[activeIndex]?.text || '暂无同步歌词'
  })
  const secondaryLyricLine = computed(() => {
    if (!hasActiveTrack.value || lyricsLoading.value || currentLyrics.value.length < 2) return ''
    if (currentLyricIndex.value >= 0) {
      return currentLyrics.value[currentLyricIndex.value + 1]?.text || ''
    }
    return currentLyrics.value[1]?.text || ''
  })
  const elapsedTimeLabel = computed(() => formatPlayerTime(playerCurrentTime.value))
  const remainingTimeLabel = computed(() => {
    const remaining = Math.max(0, playerDuration.value - playerCurrentTime.value)
    return `-${formatPlayerTime(remaining)}`
  })
  const progressSliderStyle = computed(() => ({
    '--slider-fill': `${progressRatio.value}%`,
    '--slider-fill-color': 'rgba(255, 255, 255, 0.96)',
    '--slider-rest-color': 'rgba(186, 203, 218, 0.62)',
  }))
  const volumeSliderStyle = computed(() => ({
    '--slider-fill': `${volumeRatio.value}%`,
    '--slider-fill-color': 'rgba(255, 255, 255, 0.98)',
    '--slider-rest-color': 'rgba(189, 204, 217, 0.58)',
  }))
  const canPlayPrev = computed(() => {
    if (!currentQueue.value.length) return false
    if (playbackOrderMode.value === 'shuffle') {
      return playedTrackHistory.value.length > 0 || (repeatMode.value === 'all' && currentQueue.value.length > 1)
    }
    return currentTrackIndex.value > 0 || (repeatMode.value === 'all' && currentQueue.value.length > 1)
  })
  const canPlayNext = computed(() => {
    if (!currentQueue.value.length) return false
    if (playbackOrderMode.value === 'shuffle') {
      return currentQueue.value.length > 1 || repeatMode.value === 'all'
    }
    return currentTrackIndex.value >= 0 && (
      currentTrackIndex.value < currentQueue.value.length - 1 ||
      (repeatMode.value === 'all' && currentQueue.value.length > 1)
    )
  })
  const currentTrackId = computed(() => String(currentTrack.value?.id || ''))

  async function playTrackAt(index, { rememberCurrent = false } = {}) {
    if (index < 0 || index >= currentQueue.value.length) return
    if (rememberCurrent && currentTrackIndex.value >= 0 && currentTrackIndex.value !== index) {
      rememberPlaybackHistory(currentTrackIndex.value)
    }
    await playSong(currentQueue.value[index], currentQueue.value)
  }

  async function playQueue(queue, startIndex = 0) {
    const normalizedQueue = Array.isArray(queue)
      ? queue.map((item, index) => normalizeLikedSong(item, index)).filter(Boolean)
      : []

    if (!normalizedQueue.length) {
      playerError.value = '当前没有可播放的歌曲。'
      return
    }

    const safeIndex = Math.min(Math.max(Number(startIndex) || 0, 0), normalizedQueue.length - 1)
    await playSong(normalizedQueue[safeIndex], normalizedQueue)
  }

  function playPrevTrack() {
    if (!currentQueue.value.length) return

    if (playbackOrderMode.value === 'shuffle') {
      const history = [...playedTrackHistory.value]
      while (history.length) {
        const previousIndex = history.pop()
        if (
          Number.isInteger(previousIndex) &&
          previousIndex >= 0 &&
          previousIndex < currentQueue.value.length &&
          previousIndex !== currentTrackIndex.value
        ) {
          playedTrackHistory.value = history
          void playTrackAt(previousIndex, { rememberCurrent: false })
          return
        }
      }

      if (repeatMode.value === 'all' && currentQueue.value.length > 1) {
        const randomIndex = pickRandomQueueIndex(currentTrackIndex.value)
        if (randomIndex >= 0) {
          void playTrackAt(randomIndex, { rememberCurrent: false })
        }
      }
      return
    }

    if (currentTrackIndex.value > 0) {
      void playTrackAt(currentTrackIndex.value - 1, { rememberCurrent: false })
      return
    }

    if (repeatMode.value === 'all' && currentQueue.value.length > 1) {
      void playTrackAt(currentQueue.value.length - 1, { rememberCurrent: false })
    }
  }

  function playNextTrack() {
    if (!currentQueue.value.length) return

    if (playbackOrderMode.value === 'shuffle') {
      const randomIndex = pickRandomQueueIndex(currentTrackIndex.value)
      if (randomIndex >= 0 && (randomIndex !== currentTrackIndex.value || currentQueue.value.length === 1)) {
        void playTrackAt(randomIndex, { rememberCurrent: true })
      }
      return
    }

    if (currentTrackIndex.value >= 0 && currentTrackIndex.value < currentQueue.value.length - 1) {
      void playTrackAt(currentTrackIndex.value + 1, { rememberCurrent: false })
      return
    }

    if (repeatMode.value === 'all' && currentQueue.value.length > 1) {
      void playTrackAt(0, { rememberCurrent: false })
    }
  }

  async function toggleCurrentTrack() {
    const audio = audioPlayer.value
    if (!audio || !currentTrack.value) return
    playerError.value = ''
    try {
      if (audio.paused) {
        pendingSongId.value = currentTrack.value.id
        isAudioBuffering.value = true
        await audio.play()
      } else {
        pendingSongId.value = ''
        isAudioBuffering.value = false
        audio.pause()
      }
    } catch (error) {
      console.error('toggle current track error:', error)
      pendingSongId.value = ''
      isAudioBuffering.value = false
      playerError.value = '播放器暂时无法继续播放。'
    }
  }

  function handleAudioLoadStart() {
    isAudioPlaying.value = false
    if (currentTrack.value) {
      isAudioBuffering.value = true
    }
  }

  function handleAudioPlay() {
    playerError.value = ''
  }

  function handleAudioPlaying() {
    isAudioPlaying.value = true
    isAudioBuffering.value = false
    pendingSongId.value = ''
    playerError.value = ''
    maybeLoadLyricsForCurrentTrack()
  }

  function handleAudioPause() {
    isAudioPlaying.value = false
    if (!pendingSongId.value) {
      isAudioBuffering.value = false
    }
  }

  function handleAudioWaiting() {
    if (!currentTrack.value || playerError.value) return
    isAudioPlaying.value = false
    isAudioBuffering.value = true
  }

  function handleAudioEnded() {
    const audio = audioPlayer.value
    isAudioPlaying.value = false
    isAudioBuffering.value = false
    pendingSongId.value = ''

    if (repeatMode.value === 'one' && audio && currentTrack.value) {
      audio.currentTime = 0
      playerCurrentTime.value = 0
      syncCurrentLyricIndex(0)
      pendingSongId.value = currentTrack.value.id
      isAudioBuffering.value = true
      void audio.play().catch((error) => {
        console.error('repeat current track error:', error)
        pendingSongId.value = ''
        isAudioBuffering.value = false
      })
      return
    }

    if (playbackOrderMode.value === 'shuffle') {
      if (currentQueue.value.length > 1 || repeatMode.value === 'all') {
        playNextTrack()
      }
      return
    }

    if (currentTrackIndex.value >= 0 && currentTrackIndex.value < currentQueue.value.length - 1) {
      playNextTrack()
      return
    }

    if (repeatMode.value === 'all' && currentQueue.value.length > 1) {
      void playTrackAt(0, { rememberCurrent: false })
    }
  }

  function handleAudioError() {
    const audio = audioPlayer.value
    if (
      audio &&
      currentTrack.value?.id &&
      currentTrack.value?.compatibilitySourceUrl &&
      currentTrack.value?.sourceMode !== 'compatibility'
    ) {
      currentTrack.value = {
        ...currentTrack.value,
        sourceMode: 'compatibility',
      }
      playerError.value = ''
      pendingSongId.value = currentTrack.value.id
      isAudioBuffering.value = true
      audio.pause()
      audio.src = currentTrack.value.compatibilitySourceUrl
      audio.load()
      void audio.play().catch((error) => {
        console.error('compatibility playback error:', error)
        isAudioPlaying.value = false
        isAudioBuffering.value = false
        pendingSongId.value = ''
        playerError.value = currentTrack.value ? `《${currentTrack.value.name}》暂时无法播放。` : '当前歌曲暂时无法播放。'
      })
      return
    }

    isAudioPlaying.value = false
    isAudioBuffering.value = false
    pendingSongId.value = ''
    playerError.value = currentTrack.value ? `《${currentTrack.value.name}》暂时无法播放。` : '当前歌曲暂时无法播放。'
  }

  function handleAudioLoadedMetadata() {
    const audio = audioPlayer.value
    if (!audio) return
    playerDuration.value = Number.isFinite(audio.duration) ? audio.duration : 0
  }

  function handleAudioTimeUpdate() {
    const audio = audioPlayer.value
    if (!audio) return
    playerCurrentTime.value = Number.isFinite(audio.currentTime) ? audio.currentTime : 0
    if (Number.isFinite(audio.duration)) {
      playerDuration.value = audio.duration
    }
    syncCurrentLyricIndex(playerCurrentTime.value)
  }

  function handleAudioVolumeChange() {
    const audio = audioPlayer.value
    if (!audio) return
    const nextVolume = Number.isFinite(audio.volume) ? audio.volume : playerVolume.value
    playerVolume.value = nextVolume
    if (nextVolume > 0) {
      lastVolumeBeforeMute.value = nextVolume
    }
  }

  function seekCurrentTrack(event) {
    const audio = audioPlayer.value
    const value = Number(event?.target?.value)
    if (!audio || !Number.isFinite(value)) return
    audio.currentTime = value
    playerCurrentTime.value = value
    syncCurrentLyricIndex(value)
  }

  async function seekToTime(seconds, { forcePlay = false } = {}) {
    const audio = audioPlayer.value
    const targetSeconds = Number(seconds)
    if (!audio || !currentTrack.value || !Number.isFinite(targetSeconds)) return false

    const boundedSeconds = Math.max(
      0,
      playerDuration.value > 0 ? Math.min(targetSeconds, playerDuration.value) : targetSeconds,
    )

    audio.currentTime = boundedSeconds
    playerCurrentTime.value = boundedSeconds
    syncCurrentLyricIndex(boundedSeconds)

    if (!forcePlay) return true

    playerError.value = ''
    try {
      pendingSongId.value = currentTrack.value.id
      isAudioBuffering.value = true
      await audio.play()
      return true
    } catch (error) {
      console.error('seek to lyric time error:', error)
      pendingSongId.value = ''
      isAudioBuffering.value = false
      playerError.value = '跳转到这句歌词时播放失败。'
      return false
    }
  }

  function updatePlayerVolume(event) {
    const audio = audioPlayer.value
    const value = Number(event?.target?.value)
    if (!Number.isFinite(value)) return
    playerVolume.value = value
    if (value > 0) {
      lastVolumeBeforeMute.value = value
    }
    if (audio) {
      audio.volume = value
    }
  }

  function toggleMute() {
    const audio = audioPlayer.value
    if (isMuted.value) {
      const nextVolume = lastVolumeBeforeMute.value > 0 ? lastVolumeBeforeMute.value : 0.82
      playerVolume.value = nextVolume
      if (audio) {
        audio.volume = nextVolume
      }
      return
    }

    if (playerVolume.value > 0) {
      lastVolumeBeforeMute.value = playerVolume.value
    }
    playerVolume.value = 0
    if (audio) {
      audio.volume = 0
    }
  }

  function setPlayerError(message = '') {
    playerError.value = String(message || '').trim()
  }

  function clearPlayerError() {
    playerError.value = ''
  }

  function togglePlaybackOrderMode() {
    playbackOrderMode.value = playbackOrderMode.value === 'shuffle' ? 'sequence' : 'shuffle'
    if (playbackOrderMode.value === 'sequence') {
      playedTrackHistory.value = []
    }
  }

  function cycleRepeatMode() {
    repeatMode.value =
      repeatMode.value === 'off'
        ? 'all'
        : repeatMode.value === 'all'
          ? 'one'
          : 'off'
  }

  return {
    activeLyricLine,
    audioPlayer,
    bindAudioPlayer,
    canPlayNext,
    canPlayPrev,
    currentTrack,
    currentTrackId,
    currentLyricIndex,
    currentLyrics,
    elapsedTimeLabel,
    handleAudioEnded,
    handleAudioError,
    handleAudioLoadedMetadata,
    handleAudioLoadStart,
    handleAudioPause,
    handleAudioPlay,
    handleAudioPlaying,
    handleAudioTimeUpdate,
    handleAudioVolumeChange,
    handleAudioWaiting,
    hasActiveTrack,
    hasLyricsAvailable,
    isAudioPlaying,
    isMuted,
    lyricsLoading,
    pendingSongId,
    playNextTrack,
    playbackOrderMode,
    playQueue,
    playerCurrentTime,
    playerDisplayTrack,
    playerDuration,
    playerError,
    playerStatusText,
    playerVolume,
    playPrevTrack,
    playSong,
    progressSliderStyle,
    remainingTimeLabel,
    repeatMode,
    secondaryLyricLine,
    setPlayerError,
    seekCurrentTrack,
    seekToTime,
    togglePlaybackOrderMode,
    toggleCurrentTrack,
    toggleMute,
    cycleRepeatMode,
    updatePlayerVolume,
    volumeSliderStyle,
    clearPlayerError,
  }
}
