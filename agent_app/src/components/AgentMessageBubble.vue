<template>
  <div
    class="msg-row"
    :class="{ user: isUserMessage, assistant: !isUserMessage }"
  >
    <div class="msg-bubble" :class="{ 'is-thinking': isThinking, 'has-rich-content': richContent }">
      <div v-if="isThinking" class="thinking-inline" :aria-label="thinkingDisplay.statusText" aria-live="polite">
        <span class="thinking-inline-copy">{{ thinkingDisplay.statusText }}</span>
        <span class="thinking-inline-dots" aria-hidden="true">
          <span></span><span></span><span></span>
        </span>
      </div>
      <div v-else class="msg-stack">
        <div v-if="message?.content" class="msg-text" v-html="renderMessageHtml(message.content)"></div>

        <section v-if="songListPayload" class="rich-list-card rich-list-card--songs">
          <div class="rich-list-head">
            <div class="rich-list-copy">
              <div class="rich-list-title">{{ songListPayload.title || '歌曲列表' }}</div>
              <div v-if="songListPayload.summary" class="rich-list-summary">
                {{ songListPayload.summary }}
              </div>
            </div>
            <div class="rich-list-total">
              {{ formatTotalLabel(songListPayload.total || songListPayload.items.length, '首') }}
            </div>
          </div>

          <div class="song-list">
            <button
              v-for="song in songListPayload.items"
              :key="song.id"
              type="button"
              class="song-row"
              :class="{ 'is-active': isCurrentTrack(song), 'is-loading': pendingSongId === song.id }"
              @click="handlePlaySong(song)"
            >
              <div class="song-rank">{{ formatSongRank(song.rank) }}</div>
              <img
                v-if="song.cover_url"
                class="song-cover"
                :src="song.cover_url"
                :alt="song.name"
                loading="lazy"
              />
              <div v-else class="song-cover placeholder">{{ song.name?.slice(0, 1) || '♪' }}</div>
              <div class="song-meta">
                <div class="song-name">{{ song.name }}</div>
                <div class="song-artist">
                  {{ song.artist || '未知歌手' }}
                  <span v-if="song.album" class="song-album">· {{ song.album }}</span>
                </div>
              </div>
              <div class="song-action">
                <span v-if="pendingSongId === song.id" class="song-state">加载中</span>
                <span v-else-if="isCurrentTrack(song) && isAudioPlaying" class="song-state">播放中</span>
                <span v-else class="song-play-pill">▶</span>
              </div>
            </button>
          </div>
        </section>

        <section v-if="albumListPayload" class="rich-list-card rich-list-card--playlists">
          <div class="rich-list-head">
            <div class="rich-list-copy">
              <div class="rich-list-title">{{ albumListPayload.title || '专辑列表' }}</div>
              <div v-if="albumListPayload.summary" class="rich-list-summary">
                {{ albumListPayload.summary }}
              </div>
            </div>
            <div class="rich-list-total">
              {{ formatTotalLabel(albumListPayload.total || albumListPayload.items.length, '张') }}
            </div>
          </div>

          <div class="playlist-list">
            <div
              v-for="album in albumListPayload.items"
              :key="album.id"
              class="playlist-row playlist-row--static"
            >
              <div class="playlist-rank">{{ formatSongRank(album.rank) }}</div>
              <img
                v-if="album.cover_url"
                class="playlist-cover"
                :src="album.cover_url"
                :alt="album.name"
                loading="lazy"
              />
              <div v-else class="playlist-cover placeholder">{{ album.name?.slice(0, 1) || '专' }}</div>
              <div class="playlist-meta">
                <div class="playlist-name">{{ album.name }}</div>
                <div v-if="album.artist" class="playlist-description">
                  {{ album.artist }}
                </div>
                <div v-if="formatAlbumStats(album)" class="playlist-stats">
                  {{ formatAlbumStats(album) }}
                </div>
              </div>
              <div class="playlist-action">
                <span class="playlist-open-pill">专辑</span>
              </div>
            </div>
          </div>
        </section>

        <section v-if="playlistListPayload" class="rich-list-card rich-list-card--playlists">
          <div class="rich-list-head">
            <div class="rich-list-copy">
              <div class="rich-list-title">{{ playlistListPayload.title || '歌单列表' }}</div>
              <div v-if="playlistListPayload.summary" class="rich-list-summary">
                {{ playlistListPayload.summary }}
              </div>
            </div>
            <div class="rich-list-total">
              {{ formatTotalLabel(playlistListPayload.total || playlistListPayload.items.length, '个') }}
            </div>
          </div>

          <div v-if="playlistDetail" class="playlist-detail-panel">
            <div class="playlist-detail-toolbar">
              <button type="button" class="playlist-back-btn" @click="closePlaylistDetail">
                返回歌单列表
              </button>
              <div class="playlist-detail-copy">
                <div class="playlist-detail-title">{{ playlistDetail.playlist?.name || '歌单详情' }}</div>
                <div v-if="playlistDetailSummary" class="playlist-detail-summary">
                  {{ playlistDetailSummary }}
                </div>
              </div>
            </div>

            <div v-if="playlistDetailSongs.length > 0" class="song-list">
              <button
                v-for="song in playlistDetailSongs"
                :key="song.id"
                type="button"
                class="song-row"
                :class="{ 'is-active': isCurrentTrack(song), 'is-loading': pendingSongId === song.id }"
                @click="handlePlaySong(song)"
              >
                <div class="song-rank">{{ formatSongRank(song.rank) }}</div>
                <img
                  v-if="song.cover_url"
                  class="song-cover"
                  :src="song.cover_url"
                  :alt="song.name"
                  loading="lazy"
                />
                <div v-else class="song-cover placeholder">{{ song.name?.slice(0, 1) || '♫' }}</div>
                <div class="song-meta">
                  <div class="song-name">{{ song.name }}</div>
                  <div class="song-artist">
                    {{ song.artist || '未知歌手' }}
                    <span v-if="song.album" class="song-album">· {{ song.album }}</span>
                  </div>
                </div>
                <div class="song-action">
                  <span v-if="pendingSongId === song.id" class="song-state">加载中</span>
                  <span v-else-if="isCurrentTrack(song) && isAudioPlaying" class="song-state">播放中</span>
                  <span v-else class="song-play-pill">▶</span>
                </div>
              </button>
            </div>
            <div v-else class="playlist-empty">这个歌单暂时没有可展示的歌曲。</div>
          </div>

          <template v-else>
            <div v-if="playlistRequestError" class="playlist-detail-error">{{ playlistRequestError }}</div>
            <div class="playlist-list">
              <button
                v-for="playlist in playlistListPayload.items"
                :key="playlist.id"
                type="button"
                class="playlist-row"
                :class="{ 'is-loading': playlistLoadingId === playlist.id }"
                :disabled="playlistLoadingId === playlist.id"
                @click="openPlaylistDetail(playlist)"
              >
                <div class="playlist-rank">{{ formatSongRank(playlist.rank) }}</div>
                <img
                  v-if="playlist.cover_url"
                  class="playlist-cover"
                  :src="playlist.cover_url"
                  :alt="playlist.name"
                  loading="lazy"
                />
                <div v-else class="playlist-cover placeholder">{{ playlist.name?.slice(0, 1) || '♫' }}</div>
                <div class="playlist-meta">
                  <div class="playlist-name">{{ playlist.name }}</div>
                  <div v-if="playlist.description" class="playlist-description">
                    {{ playlist.description }}
                  </div>
                  <div v-if="formatPlaylistStats(playlist)" class="playlist-stats">
                    {{ formatPlaylistStats(playlist) }}
                  </div>
                </div>
                <div class="playlist-action">
                  <span v-if="playlistLoadingId === playlist.id" class="playlist-state">加载中</span>
                  <span v-else class="playlist-open-pill">查看歌曲</span>
                </div>
              </button>
            </div>
          </template>
        </section>
      </div>
    </div>
    <div v-if="isUserMessage" class="msg-avatar" aria-hidden="true">
      <img
        v-if="userAvatarUrl"
        class="msg-avatar-image"
        :src="userAvatarUrl"
        :alt="userDisplayName"
        loading="lazy"
        @error="avatarLoadFailed = true"
      />
      <span v-else class="msg-avatar-initial">{{ userInitial }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { agentApi } from '../services/api'
import {
  getAlbumListPayload,
  getPlaylistListPayload,
  getSongListPayload,
  hasRichContent,
  isUserRole,
  renderMessageHtml,
} from '../utils/agentMessage'

const props = defineProps({
  currentAssistantMessageId: {
    type: String,
    default: '',
  },
  currentTrackId: {
    type: String,
    default: '',
  },
  forceThinking: {
    type: Boolean,
    default: false,
  },
  isAudioPlaying: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  message: {
    type: Object,
    required: true,
  },
  pendingSongId: {
    type: String,
    default: '',
  },
  thinkingState: {
    type: Object,
    default: null,
  },
  userProfile: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['play-song'])

const isUserMessage = computed(() => isUserRole(props.message?.role))
const richContent = computed(() => hasRichContent(props.message))
const songListPayload = computed(() => getSongListPayload(props.message))
const albumListPayload = computed(() => getAlbumListPayload(props.message))
const playlistListPayload = computed(() => getPlaylistListPayload(props.message))
const playlistLoadingId = ref('')
const playlistDetail = ref(null)
const playlistRequestError = ref('')
const avatarLoadFailed = ref(false)
const playlistDetailSongs = computed(() => Array.isArray(playlistDetail.value?.songs) ? playlistDetail.value.songs : [])
const userAvatarUrl = computed(() => {
  if (avatarLoadFailed.value) return ''
  return String(props.userProfile?.avatar_url || props.userProfile?.avatarUrl || '').trim()
})
const userDisplayName = computed(() => String(props.userProfile?.nickname || props.userProfile?.name || '').trim())
const userInitial = computed(() => {
  const name = userDisplayName.value
  return name ? name.slice(0, 1).toUpperCase() : '我'
})
const playlistDetailSummary = computed(() => {
  const playlist = playlistDetail.value?.playlist
  if (!playlist || typeof playlist !== 'object') return ''
  const parts = []
  const stats = formatPlaylistStats(playlist)
  const description = String(playlist.description ?? '').trim()
  if (stats) parts.push(stats)
  if (description) parts.push(description)
  return parts.join(' · ')
})
const isThinking = computed(() => {
  if (props.forceThinking) return true
  if (!props.message || isUserMessage.value) return false
  if (!props.loading) return false
  if (!props.currentAssistantMessageId || props.currentAssistantMessageId !== props.message.id) return false
  return !String(props.message.content || '').trim() && !richContent.value
})
const thinkingDisplay = computed(() => {
  const state = props.thinkingState && typeof props.thinkingState === 'object' ? props.thinkingState : {}
  return {
    statusText: String(state.statusText || '').trim() || '正在分析用户需求',
  }
})

function formatSongRank(rank) {
  const value = Number(rank)
  if (!Number.isFinite(value) || value <= 0) return '--'
  return String(value).padStart(2, '0')
}

function formatCompactCount(value) {
  const numeric = Number(value)
  if (Number.isFinite(numeric)) {
    if (numeric >= 100000000) {
      const scaled = numeric / 100000000
      return `${scaled >= 10 ? scaled.toFixed(0) : scaled.toFixed(1).replace(/\.0$/, '')}亿`
    }
    if (numeric >= 10000) {
      const scaled = numeric / 10000
      return `${scaled >= 10 ? scaled.toFixed(0) : scaled.toFixed(1).replace(/\.0$/, '')}万`
    }
    return String(Math.round(numeric))
  }
  return String(value ?? '').trim()
}

function formatPlaylistStats(playlist) {
  const parts = []
  const trackCount = formatCompactCount(playlist?.track_count)
  const playCount = formatCompactCount(playlist?.play_count)
  if (trackCount && trackCount !== '0') parts.push(`${trackCount}首`)
  if (playCount && playCount !== '0') parts.push(`${playCount}播放`)
  return parts.join(' · ')
}

function formatAlbumStats(album) {
  const parts = []
  const publishTime = String(album?.publish_time ?? '').trim()
  const size = formatCompactCount(album?.size)
  if (publishTime) parts.push(publishTime)
  if (size && size !== '0') parts.push(`${size}首`)
  return parts.join(' · ')
}

function formatTotalLabel(value, unit) {
  const numeric = Number(value)
  if (Number.isFinite(numeric) && numeric > 0) return `${numeric} ${unit}`
  return `0 ${unit}`
}

function isCurrentTrack(song) {
  if (!song?.id || !props.currentTrackId) return false
  return String(song.id) === String(props.currentTrackId)
}

function handlePlaySong(song) {
  const queue = playlistDetailSongs.value.length > 0
    ? playlistDetailSongs.value
    : songListPayload.value?.items || []
  emit('play-song', {
    song,
    queue,
  })
}

async function openPlaylistDetail(playlist) {
  const playlistId = String(playlist?.id ?? '').trim()
  if (!playlistId || playlistLoadingId.value === playlistId) return

  playlistRequestError.value = ''
  playlistLoadingId.value = playlistId
  try {
    const response = await agentApi.getPlaylistTracks(playlistId, { limit: 100, offset: 0 })
    const songs = Array.isArray(response?.songs) ? response.songs : []
    const detailPlaylist = response?.playlist && typeof response.playlist === 'object'
      ? response.playlist
      : playlist
    playlistDetail.value = {
      playlist: detailPlaylist,
      songs,
    }
  } catch (error) {
    console.error('load playlist tracks error:', error)
    playlistRequestError.value = '这个歌单暂时加载失败，请稍后再试。'
  } finally {
    playlistLoadingId.value = ''
  }
}

function closePlaylistDetail() {
  playlistDetail.value = null
  playlistRequestError.value = ''
}
</script>

<style scoped>
.msg-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 10px 0;
  width: 100%;
  min-width: 0;
}

.msg-row.user {
  justify-content: flex-end;
}

.msg-avatar {
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  border-radius: 14px;
  overflow: hidden;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at 30% 20%, rgba(255, 255, 255, 0.9), transparent 46%),
    linear-gradient(135deg, rgba(245, 245, 244, 0.96), rgba(216, 216, 214, 0.82));
  color: #303330;
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 10px 20px rgba(24, 28, 24, 0.1);
}

.msg-avatar-image {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.msg-bubble {
  width: fit-content;
  max-width: min(720px, 78%);
  min-width: 0;
  padding: 14px 16px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.52);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.34), rgba(255, 255, 255, 0.2));
  box-shadow: var(--glass-shadow-soft);
  color: var(--text-primary);
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;
  overflow-wrap: anywhere;
  backdrop-filter: blur(22px) saturate(165%);
  -webkit-user-select: none;
  user-select: none;
}

.msg-bubble.is-thinking {
  min-width: 0;
  padding: 11px 14px;
  border-color: rgba(255, 255, 255, 0.54);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.5), rgba(246, 246, 245, 0.34));
  box-shadow: 0 14px 30px rgba(24, 28, 24, 0.08);
  position: relative;
  overflow: hidden;
}

.msg-bubble.is-thinking::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent 0%, rgba(32, 36, 32, 0.045) 50%, transparent 100%);
  transform: translateX(-100%);
  animation: thinking-sheen 1.8s ease-in-out infinite;
  pointer-events: none;
}

.msg-row.user .msg-bubble {
  margin-left: auto;
  background: linear-gradient(180deg, rgba(250, 250, 249, 0.82), rgba(244, 244, 243, 0.62));
  border-color: rgba(255, 255, 255, 0.58);
  box-shadow: 0 14px 28px rgba(24, 28, 24, 0.08);
  -webkit-user-select: text;
  user-select: text;
}

.msg-row.user .msg-bubble *,
.msg-row.user .msg-text,
.msg-row.user .msg-text * {
  -webkit-user-select: text;
  user-select: text;
}

.msg-bubble.has-rich-content {
  max-width: min(840px, 92%);
}

.msg-stack {
  display: grid;
  gap: 14px;
}

.msg-text {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.msg-bubble.has-rich-content .msg-text {
  order: 20;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.24);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.26);
}

.msg-bubble.has-rich-content .rich-list-card {
  order: 1;
}

.msg-text :deep(> * + *) {
  margin-top: 10px;
}

.msg-text :deep(.msg-block) {
  display: grid;
  gap: 8px;
}

.msg-text :deep(.msg-title) {
  font-weight: 700;
  color: var(--text-primary);
}

.msg-text :deep(.msg-list) {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.msg-text :deep(.msg-list-item) {
  position: relative;
  padding-left: 14px;
}

.msg-text :deep(.msg-list-item::before) {
  content: '';
  position: absolute;
  left: 0;
  top: 0.72em;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: rgba(32, 36, 32, 0.42);
}

.msg-text :deep(.msg-kv-list) {
  display: grid;
  gap: 6px;
}

.msg-text :deep(.msg-kv-row) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}

.msg-text :deep(.msg-kv-label) {
  font-weight: 700;
  color: var(--text-primary);
}

.msg-text :deep(.msg-kv-value),
.msg-text :deep(.msg-link-row) {
  min-width: 0;
  color: var(--text-secondary);
  overflow-wrap: anywhere;
  word-break: break-word;
}

.msg-text :deep(.msg-paragraph) {
  margin: 0;
}

.msg-text :deep(.msg-link) {
  color: #303330;
  text-decoration: underline;
  word-break: break-all;
}

.rich-list-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.42);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.44), rgba(247, 247, 246, 0.28));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.rich-list-card--playlists {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.42), rgba(246, 246, 245, 0.32));
}

.rich-list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.rich-list-copy {
  min-width: 0;
}

.rich-list-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.rich-list-summary {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.rich-list-total {
  flex: 0 0 auto;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(32, 36, 32, 0.06);
  color: var(--active-color);
  font-size: 12px;
  font-weight: 700;
}

.song-list,
.playlist-list {
  display: grid;
  gap: 10px;
  max-height: 430px;
  overflow: auto;
  padding-right: 4px;
}

.song-row,
.playlist-row {
  appearance: none;
  display: grid;
  grid-template-columns: 38px 56px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.38);
  background: rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(10px);
  color: inherit;
  font: inherit;
  text-align: left;
}

.playlist-row {
  cursor: pointer;
  transition: all var(--transition-fast);
}

.playlist-row--static {
  cursor: default;
}

.playlist-row:hover:not(:disabled) {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.28);
  border-color: rgba(255, 255, 255, 0.5);
}

.playlist-row--static:hover {
  transform: none;
}

.playlist-row:disabled,
.playlist-row.is-loading {
  opacity: 0.78;
}

.song-row {
  cursor: pointer;
  transition: all var(--transition-fast);
}

.song-row:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.28);
  border-color: rgba(255, 255, 255, 0.5);
}

.song-row.is-active {
  background: linear-gradient(135deg, rgba(32, 36, 32, 0.08), rgba(255, 255, 255, 0.34));
  border-color: rgba(32, 36, 32, 0.16);
  box-shadow: 0 12px 24px rgba(24, 28, 24, 0.08);
}

.song-row.is-loading {
  opacity: 0.78;
}

.song-rank,
.playlist-rank {
  font-size: 18px;
  font-weight: 700;
  color: rgba(64, 68, 64, 0.72);
  text-align: center;
}

.song-cover,
.playlist-cover {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  object-fit: cover;
  box-shadow: 0 10px 18px rgba(24, 28, 24, 0.12);
}

.song-cover.placeholder,
.playlist-cover.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(96, 100, 96, 0.36), rgba(220, 220, 218, 0.46));
  color: #fff;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.song-meta,
.playlist-meta {
  min-width: 0;
}

.song-name,
.playlist-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.song-artist,
.playlist-description,
.playlist-stats {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
}

.song-artist {
  white-space: nowrap;
}

.playlist-description {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  white-space: normal;
}

.song-album {
  color: var(--text-muted);
}

.playlist-stats {
  color: var(--text-muted);
}

.song-action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 54px;
}

.playlist-action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 88px;
}

.song-state {
  font-size: 12px;
  font-weight: 700;
  color: var(--active-color);
}

.playlist-state {
  font-size: 12px;
  font-weight: 700;
  color: var(--active-color);
}

.song-play-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.42);
  color: rgba(64, 68, 64, 0.88);
  font-size: 12px;
  font-weight: 700;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.36);
}

.playlist-open-pill,
.playlist-back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.46);
  background: rgba(255, 255, 255, 0.34);
  color: rgba(64, 68, 64, 0.92);
  font-size: 12px;
  font-weight: 700;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.36);
}

.playlist-open-pill {
  min-width: 74px;
  height: 30px;
  padding: 0 12px;
  border-radius: 999px;
}

.playlist-detail-panel {
  display: grid;
  gap: 12px;
}

.playlist-detail-toolbar {
  display: grid;
  gap: 10px;
}

.playlist-back-btn {
  width: fit-content;
  min-height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.playlist-back-btn:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.44);
}

.playlist-detail-copy {
  min-width: 0;
}

.playlist-detail-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.playlist-detail-summary,
.playlist-detail-error,
.playlist-empty {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.playlist-detail-summary {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.playlist-detail-error {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 244, 244, 0.4);
  color: rgba(147, 73, 73, 0.92);
}

.playlist-empty {
  padding: 12px 4px 2px;
}

.thinking-inline {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: fit-content;
  max-width: 100%;
  min-height: 22px;
}

.thinking-inline-copy {
  flex: 0 1 auto;
  min-width: 0;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.45;
  color: rgba(92, 114, 129, 0.64);
  letter-spacing: 0.01em;
}

.thinking-inline-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex: 0 0 auto;
  transform: translateY(1px);
}

.thinking-inline-dots span {
  width: 3px;
  height: 3px;
  border-radius: 999px;
  background: rgba(128, 128, 124, 0.36);
  animation: thinking-dot-fade 1.15s infinite ease-in-out both;
}

.thinking-inline-dots span:nth-child(2) {
  animation-delay: 0.16s;
}

.thinking-inline-dots span:nth-child(3) {
  animation-delay: 0.32s;
}

@keyframes thinking-dot-fade {
  0%, 80%, 100% {
    opacity: 0.28;
    transform: scale(0.78);
  }

  40% {
    opacity: 0.72;
    transform: scale(1);
  }
}

@keyframes thinking-sheen {
  0%, 100% {
    transform: translateX(-100%);
    opacity: 0;
  }

  25% {
    opacity: 1;
  }

  60% {
    transform: translateX(100%);
    opacity: 0.8;
  }
}

</style>
