<template>
  <div class="agent-layout">
    <aside class="agent-rail">
      <div class="rail-top">
        <div class="rail-title">对话</div>
        <button class="rail-new" @click="createNewConversation" :disabled="sidebarLoading || loading">
          新建对话
        </button>

        <div class="rail-search">
          <input v-model="query" class="rail-search-input" placeholder="搜索对话" />
        </div>
      </div>

      <div v-if="filteredConversations.length > 0" class="rail-list">
        <div
          v-for="conversation in filteredConversations"
          :key="conversation.id"
          class="rail-item"
          :class="{ active: conversation.id === activeConversationId }"
          @click="selectConversation(conversation.id)"
          @keydown.enter.prevent="selectConversation(conversation.id)"
          tabindex="0"
          role="button"
        >
          <div class="rail-item-head">
            <input
              v-if="editingConversationId === conversation.id"
              v-model="editingTitle"
              class="rail-title-input"
              maxlength="20"
              @click.stop
              @keydown.enter.prevent="commitRenameConversation(conversation.id)"
              @keydown.esc.prevent="cancelRenameConversation"
              @blur="commitRenameConversation(conversation.id)"
              autofocus
            />
            <div v-else class="rail-item-title">{{ conversation.title || DEFAULT_TITLE }}</div>
            <div class="rail-item-actions">
              <button class="item-action-btn" title="重命名" @click.stop="startRenameConversation(conversation)">
                <svg viewBox="0 0 24 24" aria-hidden="true" class="action-icon">
                  <path d="M12 20h9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                  <path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>
              <button
                class="item-action-btn danger"
                title="删除对话"
                :disabled="deletingConversationId === conversation.id || loading"
                @click.stop="deleteConversation(conversation.id)"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true" class="action-icon">
                  <path d="M3 6h18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                  <path d="M8 6V4h8v2m-9 0 1 14h8l1-14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                  <path d="M10 11v6M14 11v6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>
            </div>
          </div>
          <div class="rail-item-meta">{{ formatTime(conversation.updated_at) }}</div>
        </div>
      </div>

      <div v-else class="rail-empty">
        <div class="rail-empty-title">还没有对话</div>
        <div class="rail-empty-sub">发送一条消息，或者手动新建一个空白会话。</div>
      </div>

      <div class="rail-player-slot">
        <MusicPlayerCard
          :accessory-title="heartModeAccessoryTitle"
          :audio-ref="bindAudioPlayer"
          :active-lyric-line="activeLyricLine"
          :can-play-next="canPlayNext"
          :can-play-prev="canPlayPrev"
          :elapsed-time-label="elapsedTimeLabel"
          :fullscreen-open="musicFullscreenOpen"
          :has-active-track="hasActiveTrack"
          :has-lyrics-available="hasLyricsAvailable"
          :heart-mode-active="heartModeActive"
          :heart-mode-loading="heartModeLoading"
          :is-audio-playing="isAudioPlaying"
          :is-muted="isMuted"
          :lyrics-loading="lyricsLoading"
          :on-accessory-click="handleHeartModePlay"
          :on-audio-ended="handleAudioEnded"
          :on-audio-error="handleAudioError"
          :on-audio-loaded-metadata="handleAudioLoadedMetadata"
          :on-audio-load-start="handleAudioLoadStart"
          :on-audio-pause="handleAudioPause"
          :on-audio-play="handleAudioPlay"
          :on-audio-playing="handleAudioPlaying"
          :on-audio-time-update="handleAudioTimeUpdate"
          :on-audio-volume-change="handleAudioVolumeChange"
          :on-audio-waiting="handleAudioWaiting"
          :on-enter-fullscreen="openMusicFullscreen"
          :on-play-next="playNextTrack"
          :on-play-prev="playPrevTrack"
          :on-seek-track="seekCurrentTrack"
          :on-toggle-mute="toggleMute"
          :on-toggle-track="toggleCurrentTrack"
          :on-update-volume="updatePlayerVolume"
          :player-current-time="playerCurrentTime"
          :player-display-track="playerDisplayTrack"
          :player-duration="playerDuration"
          :player-error="playerError"
          :player-status-text="playerStatusText"
          :player-volume="playerVolume"
          :progress-slider-style="progressSliderStyle"
          :remaining-time-label="remainingTimeLabel"
          :secondary-lyric-line="secondaryLyricLine"
          :volume-slider-style="volumeSliderStyle"
        />
      </div>
    </aside>

    <main class="chat-shell">
      <header class="chat-topbar">
        <div class="chat-topbar-title">{{ activeConversationTitle || DEFAULT_TITLE }}</div>
        <div v-if="memorySummary" class="chat-topbar-sub" :title="memorySummary">记忆：{{ memorySummary }}</div>
      </header>

      <section ref="messagesList" class="chat-body">
        <div v-if="messages.length === 0" class="welcome-card">
          <div class="welcome-title">你好，我是小听</div>
          <div class="welcome-sub">我是音迹里的智能音乐助手，由小汪开发。我会把执行进度和流式输出同步展示给你。</div>
          <div class="quick-questions">
            <button
              v-for="question in MUSIC_QUICK_QUESTIONS"
              :key="question.label"
              class="quick-question"
              @click="sendQuickQuestion(question.prompt)"
            >
              {{ question.label }}
            </button>
          </div>
        </div>

        <div v-if="shouldShowProgress" class="progress-card">
          <div class="progress-head">
            <div class="progress-title">当前进度</div>
            <div class="progress-current">{{ progress.current_stage_label || '处理中' }}</div>
          </div>
          <div v-if="progress.current_stage_description" class="progress-sub">
            {{ progress.current_stage_description }}
          </div>

          <div v-if="progress.steps.length > 0" class="progress-steps">
            <div
              v-for="step in progress.steps"
              :key="step.key"
              class="progress-step"
              :class="`is-${step.status || 'pending'}`"
            >
              <div class="step-dot"></div>
              <div class="step-body">
                <div class="step-label">{{ step.label }}</div>
                <div v-if="step.description" class="step-desc">{{ step.description }}</div>
              </div>
            </div>
          </div>

          <div v-if="progress.tools.length > 0" class="tool-list">
            <div v-for="tool in progress.tools" :key="tool.tool_name" class="tool-item">
              <span class="tool-name">{{ formatToolName(tool.tool_name) }}</span>
              <span class="tool-status" :class="`is-${tool.status || 'pending'}`">{{ formatToolStatus(tool.status) }}</span>
            </div>
          </div>
        </div>

        <AgentMessageBubble
          v-for="message in messages"
          :key="message.id || message.timestamp"
          :message="message"
          :loading="loading"
          :current-assistant-message-id="currentAssistantMessageId || ''"
          :current-track-id="currentTrackId"
          :pending-song-id="pendingSongId"
          :is-audio-playing="isAudioPlaying"
          :thinking-state="thinkingBubbleState"
          @play-song="handleRichSongPlay"
        />

        <AgentMessageBubble
          v-if="showPrestreamThinking"
          :message="thinkingPlaceholderMessage"
          :force-thinking="true"
          :loading="true"
          :current-assistant-message-id="'prestream-thinking'"
          :current-track-id="currentTrackId"
          :pending-song-id="pendingSongId"
          :is-audio-playing="isAudioPlaying"
          :thinking-state="thinkingBubbleState"
        />
      </section>

      <div v-if="requestError" class="chat-error-banner">{{ requestError }}</div>

      <footer class="chat-input">
        <form class="input-form" @submit.prevent="submitChat">
          <input
            v-model="inputMessage"
            type="text"
            class="message-input"
            placeholder="输入你的问题"
            :disabled="loading"
            @compositionstart="isComposing = true"
            @compositionend="isComposing = false"
            @keydown.enter.exact.prevent="handleEnter"
          />
          <button class="send-btn" type="submit" :disabled="!inputMessage.trim() || loading">发送</button>
        </form>
      </footer>
    </main>

    <Teleport to="body">
      <Transition name="music-fullscreen-page">
        <div
          v-if="musicFullscreenOpen && hasActiveTrack"
          class="music-fullscreen-page"
          :class="{ 'has-cover': !!playerDisplayTrack.cover_url }"
          :style="musicFullscreenBackgroundStyle"
          role="dialog"
          aria-modal="true"
          aria-label="全屏音乐模式"
        >
          <div class="music-fullscreen-page-bg" aria-hidden="true"></div>
          <div class="music-fullscreen-page-orb music-fullscreen-page-orb--primary" aria-hidden="true"></div>
          <div class="music-fullscreen-page-orb music-fullscreen-page-orb--secondary" aria-hidden="true"></div>
          <div class="music-fullscreen-page-glow" aria-hidden="true"></div>
          <div class="music-fullscreen-page-noise" aria-hidden="true"></div>

          <button
            type="button"
            class="music-fullscreen-page-exit"
            aria-label="退出全屏音乐模式"
            @click="closeMusicFullscreen"
          >
            <svg viewBox="0 0 24 24" class="music-fullscreen-page-exit-icon">
              <path
                d="M5 9.5 12 16.5 19 9.5"
                fill="none"
                stroke="currentColor"
                stroke-width="1.9"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>

          <div class="music-fullscreen-page-shell">
            <section class="music-fullscreen-player-side">
              <div class="music-fullscreen-cover-stage">
                <div class="music-fullscreen-vinyl" :class="{ 'is-playing': isAudioPlaying }" aria-hidden="true">
                  <div class="music-fullscreen-vinyl-rings"></div>
                  <div class="music-fullscreen-vinyl-sheen"></div>
                  <div class="music-fullscreen-vinyl-core">
                    <img
                      v-if="playerDisplayTrack.cover_url"
                      class="music-fullscreen-vinyl-core-image"
                      :src="playerDisplayTrack.cover_url"
                      :alt="playerDisplayTrack.name"
                    />
                    <div
                      v-else
                      class="music-fullscreen-vinyl-core-image music-fullscreen-vinyl-core-image--placeholder"
                      aria-hidden="true"
                    >
                      <svg viewBox="0 0 24 24" class="music-fullscreen-cover-placeholder-icon">
                        <path d="M15 5v9.2a3.2 3.2 0 1 1-1.5-2.74V7.1l6-1.4v7.5a3.2 3.2 0 1 1-1.5-2.74V4.1L15 5z" fill="currentColor" />
                      </svg>
                    </div>
                  </div>
                </div>

                <div
                  ref="musicFullscreenCoverCard"
                  class="music-fullscreen-cover-card"
                  :class="{ 'is-view-transition-target': musicFullscreenOpen }"
                >
                  <img
                    v-if="playerDisplayTrack.cover_url"
                    class="music-fullscreen-cover-image"
                    :src="playerDisplayTrack.cover_url"
                    :alt="playerDisplayTrack.name"
                  />
                  <div
                    v-else
                    class="music-fullscreen-cover-image music-fullscreen-cover-image--placeholder"
                    aria-hidden="true"
                  >
                    <svg viewBox="0 0 24 24" class="music-fullscreen-cover-placeholder-icon">
                      <path d="M15 5v9.2a3.2 3.2 0 1 1-1.5-2.74V7.1l6-1.4v7.5a3.2 3.2 0 1 1-1.5-2.74V4.1L15 5z" fill="currentColor" />
                    </svg>
                  </div>
                </div>
              </div>

              <div class="music-fullscreen-song-panel">
                <div class="music-fullscreen-song-head">
                  <div class="music-fullscreen-song-copy">
                    <div class="music-fullscreen-song-title">{{ playerDisplayTrack.name }}</div>
                    <div class="music-fullscreen-song-artist">{{ playerDisplayTrack.artist || '未知歌手' }}</div>
                  </div>
                </div>

                <div class="music-fullscreen-progress-row">
                  <span class="music-fullscreen-time">{{ elapsedTimeLabel }}</span>
                  <input
                    class="music-fullscreen-progress-range"
                    type="range"
                    min="0"
                    :max="playerDuration || 0"
                    step="0.1"
                    :value="Math.min(playerCurrentTime, playerDuration || 0)"
                    :style="musicFullscreenProgressStyle"
                    :disabled="!hasActiveTrack"
                    @input="seekCurrentTrack"
                  />
                  <span class="music-fullscreen-time">{{ musicFullscreenDurationLabel }}</span>
                </div>

                <div class="music-fullscreen-transport-row">
                  <span class="music-fullscreen-transport-spacer" aria-hidden="true"></span>
                  <button
                    type="button"
                    class="music-fullscreen-transport-btn"
                    :disabled="!hasActiveTrack || !canPlayPrev"
                    aria-label="上一首"
                    @click="playPrevTrack"
                  >
                    <svg viewBox="0 0 24 24" class="music-fullscreen-transport-icon">
                      <rect x="5.2" y="6.2" width="2.8" height="11.6" rx="1.2" fill="currentColor" />
                      <path d="M17.8 6.9v10.2c0 .5-.55.82-.99.58l-7.2-5.1a.67.67 0 0 1 0-1.18l7.2-5.1c.44-.24.99.08.99.58Z" fill="currentColor" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    class="music-fullscreen-transport-btn music-fullscreen-transport-btn--primary"
                    :disabled="!hasActiveTrack"
                    :aria-label="isAudioPlaying ? '暂停' : '播放'"
                    @click="toggleCurrentTrack"
                  >
                    <svg v-if="!isAudioPlaying" viewBox="0 0 24 24" class="music-fullscreen-transport-icon music-fullscreen-transport-icon--primary">
                      <path d="M8.3 5.4v13.2c0 .63.69 1.02 1.24.68l10.2-6.6a.81.81 0 0 0 0-1.36L9.54 4.72c-.55-.34-1.24.05-1.24.68Z" fill="currentColor" />
                    </svg>
                    <svg v-else viewBox="0 0 24 24" class="music-fullscreen-transport-icon music-fullscreen-transport-icon--primary">
                      <rect x="6.7" y="4.9" width="4.3" height="14.2" rx="1.4" fill="currentColor" />
                      <rect x="13" y="4.9" width="4.3" height="14.2" rx="1.4" fill="currentColor" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    class="music-fullscreen-transport-btn"
                    :disabled="!hasActiveTrack || !canPlayNext"
                    aria-label="下一首"
                    @click="playNextTrack"
                  >
                    <svg viewBox="0 0 24 24" class="music-fullscreen-transport-icon">
                      <rect x="16" y="6.2" width="2.8" height="11.6" rx="1.2" fill="currentColor" />
                      <path d="M6.2 6.9v10.2c0 .5.55.82.99.58l7.2-5.1a.67.67 0 0 0 0-1.18l-7.2-5.1c-.44-.24-.99.08-.99.58Z" fill="currentColor" />
                    </svg>
                  </button>
                  <span class="music-fullscreen-transport-spacer" aria-hidden="true"></span>
                </div>

                <div ref="musicFullscreenVolumeRow" class="music-fullscreen-volume-row">
                  <button
                    type="button"
                    class="music-fullscreen-transport-btn music-fullscreen-volume-toggle"
                    :disabled="!hasActiveTrack"
                    :aria-label="isMuted ? '取消静音' : '静音'"
                    @click="toggleMute"
                  >
                    <svg v-if="isMuted" viewBox="0 0 24 24" class="music-fullscreen-volume-icon">
                      <path d="M4 10h3.5L12 6.5v11L7.5 14H4zM16 9l4 6M20 9l-4 6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                    <svg v-else-if="playerVolume < 0.34" viewBox="0 0 24 24" class="music-fullscreen-volume-icon">
                      <path d="M4 10h3.5L12 6.5v11L7.5 14H4z" fill="currentColor" />
                      <path d="M16 10.2a3 3 0 0 1 0 3.6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                    <svg v-else viewBox="0 0 24 24" class="music-fullscreen-volume-icon">
                      <path d="M4 10h3.5L12 6.5v11L7.5 14H4z" fill="currentColor" />
                      <path d="M16 9a4.5 4.5 0 0 1 0 6M18.8 6.8a7.6 7.6 0 0 1 0 10.4" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                  </button>
                  <input
                    class="music-fullscreen-volume-range music-fullscreen-volume-range--horizontal"
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    :value="playerVolume"
                    :style="musicFullscreenVolumeStyle"
                    :disabled="!hasActiveTrack"
                    @input="updatePlayerVolume"
                  />
                  <span class="music-fullscreen-volume-spacer" aria-hidden="true"></span>
                </div>
              </div>
            </section>

            <section class="music-fullscreen-lyrics-side" :style="musicFullscreenLyricsSideStyle">
              <div ref="musicFullscreenLyricsViewport" class="music-fullscreen-copy-center">
                <div v-if="musicFullscreenVisibleLyricLines.length" class="music-fullscreen-copy-track">
                  <div
                    v-for="line in musicFullscreenVisibleLyricLines"
                    :key="line.key"
                    class="music-fullscreen-copy-line"
                    :data-lyric-index="line.index"
                    :class="[
                      `is-${line.emphasis}`,
                      {
                        'is-clickable': Number.isFinite(line.time),
                        'is-active': line.offset === 0,
                        'is-above': line.offset < 0,
                        'is-below': line.offset > 0,
                      },
                    ]"
                    :role="Number.isFinite(line.time) ? 'button' : undefined"
                    :tabindex="Number.isFinite(line.time) ? 0 : -1"
                    @click="handleFullscreenLyricClick(line)"
                    @keydown.enter.prevent="handleFullscreenLyricClick(line)"
                  >
                    {{ line.text }}
                  </div>
                </div>
                <template v-else>
                  <div class="music-fullscreen-copy-line is-active">{{ musicFullscreenFallbackLeadText }}</div>
                  <div v-if="musicFullscreenFallbackSubText" class="music-fullscreen-copy-line is-side">
                    {{ musicFullscreenFallbackSubText }}
                  </div>
                </template>
              </div>

            </section>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AgentMessageBubble from '../components/AgentMessageBubble.vue'
import MusicPlayerCard from '../components/MusicPlayerCard.vue'
import { useMusicPlayer } from '../composables/useMusicPlayer'
import { agentApi } from '../services/api'
import {
  buildMusicCoverThemeStyle,
  DEFAULT_MUSIC_COVER_THEME,
  loadMusicCoverTheme,
} from '../utils/musicCoverTheme'
import {
  formatAxiosError,
  hasRichContent,
  isUserRole,
  normalizeMessage,
  normalizePayload,
  sanitizeInternalFailureText,
} from '../utils/agentMessage'

const DEFAULT_TITLE = '和小听聊聊'
const STORAGE_KEY = 'agent.activeConversationId'
const TOOL_LABELS = Object.freeze({
  liked_songs: '点赞歌曲',
  user_playlist: '我的歌单',
  personalized: '个性化推荐歌单',
  recommend_resource: '每日推荐歌单',
  recommend_songs: '每日推荐歌曲',
  personalized_newsong: '个性化推荐新歌',
  top_playlist: '热门歌单',
  top_playlist_highquality: '精品歌单',
  toplist: '排行榜',
  search: '搜索',
  song_lyrics: '歌词',
  song_url_v1: '播放链接',
  song_download_url_v1: '下载链接',
  song_like: '收藏歌曲',
  get_play_history: '播放历史',
  get_mutual_follow_list: '互关好友',
  get_follow_list: '关注列表',
  user_followeds: '粉丝列表',
  user_follows: '关注用户',
  retrived_music_tool: '工具检索',
})
const TOOL_STATUS_LABELS = Object.freeze({
  pending: '等待中',
  running: '执行中',
  success: '成功',
  failed: '失败',
})
const MUSIC_QUICK_QUESTIONS = [
  { label: '你是谁', prompt: '你是谁' },
  { label: '你能干嘛', prompt: '你能干嘛' },
  { label: '我的点赞歌曲', prompt: '我点赞的歌曲有哪些' },
  { label: '推荐今晚听的歌', prompt: '推荐几首适合今晚循环播放的歌' },
]
const thinkingPlaceholderMessage = Object.freeze({
  id: 'prestream-thinking',
  role: 'assistant',
  content: '',
})

const conversations = ref([])
const activeConversationId = ref(null)
const messages = ref([])
const memorySummary = ref('')
const inputMessage = ref('')
const loading = ref(false)
const sidebarLoading = ref(false)
const messagesList = ref(null)
const query = ref('')
const isComposing = ref(false)
const editingConversationId = ref(null)
const editingTitle = ref('')
const deletingConversationId = ref(null)
const requestError = ref('')
const progress = ref({
  current_stage: null,
  current_stage_label: '',
  current_stage_description: '',
  steps: [],
  tools: [],
})
const assistantStreaming = ref(false)
const currentAssistantMessageId = ref(null)

const {
  activeLyricLine,
  bindAudioPlayer,
  canPlayNext,
  canPlayPrev,
  currentLyricIndex,
  currentLyrics,
  currentTrackId,
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
  toggleCurrentTrack,
  toggleMute,
  updatePlayerVolume,
  volumeSliderStyle,
  clearPlayerError,
} = useMusicPlayer()

const heartModeLoading = ref(false)
const heartModeActive = ref(false)
const musicFullscreenOpen = ref(false)
const musicFullscreenCoverCard = ref(null)
const musicFullscreenVolumeRow = ref(null)
const musicFullscreenLyricsViewport = ref(null)
const musicFullscreenLyricsOffset = ref(0)
const MUSIC_FULLSCREEN_LYRICS_VISUAL_OFFSET = 44
const musicFullscreenTheme = ref(DEFAULT_MUSIC_COVER_THEME)
let previousBodyOverflow = ''
let previousHtmlOverflow = ''
let musicThemeRequestToken = 0
let musicFullscreenLyricsAlignFrame = 0
let musicFullscreenLyricsScrollFrame = 0
let musicFullscreenLyricsScrollTarget = 0

playbackOrderMode.value = 'sequence'
repeatMode.value = 'off'

const activeConversationTitle = computed(() => {
  const found = conversations.value.find((item) => item.id === activeConversationId.value)
  return found?.title || ''
})

const heartModeAccessoryTitle = computed(() => {
  if (heartModeLoading.value) return '正在准备心动模式'
  if (heartModeActive.value) return '重新生成心动模式'
  return '开启心动模式'
})

const filteredConversations = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return conversations.value
  return conversations.value.filter((item) => (item.title || '').toLowerCase().includes(keyword))
})

const shouldShowProgress = computed(() => {
  if (!loading.value && progress.value.current_stage === 'done') return false
  return (
    progress.value.steps.length > 0 ||
    progress.value.tools.length > 0 ||
    !!progress.value.current_stage_label ||
    !!progress.value.current_stage_description
  )
})

const musicFullscreenBackgroundStyle = computed(() => {
  const coverUrl = String(playerDisplayTrack.value?.cover_url || '').trim()
  return buildMusicCoverThemeStyle(musicFullscreenTheme.value, coverUrl)
})

const musicFullscreenLyricLines = computed(() => {
  if (Array.isArray(currentLyrics.value) && currentLyrics.value.length) return currentLyrics.value
  if (hasActiveTrack.value && activeLyricLine.value) {
    return [{ text: activeLyricLine.value, time: null }]
  }
  return []
})

const musicFullscreenActiveLyricIndex = computed(() => {
  if (!musicFullscreenLyricLines.value.length) return -1
  if (currentLyricIndex.value >= 0) {
    return Math.min(currentLyricIndex.value, musicFullscreenLyricLines.value.length - 1)
  }
  return activeLyricLine.value ? 0 : -1
})

const musicFullscreenVisibleLyricLines = computed(() => {
  const lines = musicFullscreenLyricLines.value
  if (!lines.length) return []

  const activeIndex = musicFullscreenActiveLyricIndex.value >= 0 ? musicFullscreenActiveLyricIndex.value : 0
  return lines.map((line, index) => {
    const offset = index - activeIndex
    const distance = Math.abs(offset)

    return {
      ...line,
      key: `${line.time ?? 'plain'}_${index}_${line.text}`,
      index,
      offset,
      emphasis:
        offset === 0
          ? 'active'
          : distance === 1
            ? 'near'
            : distance <= 3
              ? 'side'
              : 'far',
    }
  })
})

const musicFullscreenFallbackLeadText = computed(() => {
  if (lyricsLoading.value) return '歌词同步中...'
  return activeLyricLine.value || playerDisplayTrack.value?.name || ''
})

const musicFullscreenFallbackSubText = computed(() => {
  return secondaryLyricLine.value || playerDisplayTrack.value?.artist || ''
})

const musicFullscreenDurationLabel = computed(() => {
  const total = Math.max(0, Math.floor(Number(playerDuration.value) || 0))
  const minutes = String(Math.floor(total / 60)).padStart(2, '0')
  const seconds = String(total % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
})

const musicFullscreenProgressStyle = computed(() => ({
  '--slider-fill-color': 'var(--music-theme-accent)',
  '--slider-rest-color': 'rgba(255, 255, 255, 0.28)',
  '--slider-thumb-color': 'var(--music-theme-accent)',
  '--slider-thumb-shadow': 'rgba(var(--music-theme-accent-rgb), 0.26)',
  '--slider-fill': playerDuration.value > 0
    ? `${Math.max(0, Math.min(100, (playerCurrentTime.value / playerDuration.value) * 100))}%`
    : '0%',
}))

const musicFullscreenVolumeStyle = computed(() => ({
  '--slider-fill-color': 'var(--music-theme-accent)',
  '--slider-rest-color': 'rgba(255, 255, 255, 0.24)',
  '--slider-thumb-color': '#ffffff',
  '--slider-thumb-shadow': 'rgba(var(--music-theme-accent-rgb), 0.24)',
  '--slider-fill': `${Math.max(0, Math.min(100, (Number(playerVolume.value) || 0) * 100))}%`,
}))

const musicFullscreenLyricsSideStyle = computed(() => ({
  '--music-fullscreen-lyrics-offset': `${Math.round(musicFullscreenLyricsOffset.value + MUSIC_FULLSCREEN_LYRICS_VISUAL_OFFSET)}px`,
}))

function formatToolName(toolName) {
  const normalized = String(toolName || '').trim()
  if (!normalized) return '工具'
  return TOOL_LABELS[normalized] || normalized.replace(/_/g, ' ')
}

function formatToolStatus(status) {
  const normalized = String(status || '').trim().toLowerCase()
  return TOOL_STATUS_LABELS[normalized] || '处理中'
}

function isToolRunningStatus(status) {
  const normalized = String(status || '').trim().toLowerCase()
  return ['running', 'in_progress', 'processing', 'active'].includes(normalized)
}

function resolveThinkingToolName(tool) {
  return String(tool?.tool_name || tool?.name || tool?.tool || '').trim()
}

function resolveThinkingStatusText() {
  const currentProgress = progress.value || {}
  const tools = Array.isArray(currentProgress.tools) ? currentProgress.tools : []
  const steps = Array.isArray(currentProgress.steps) ? currentProgress.steps : []

  const activeStep = steps.find((step) => isToolRunningStatus(step?.status))
  const stageSource = [
    currentProgress.current_stage,
    currentProgress.current_stage_label,
    currentProgress.current_stage_description,
    activeStep?.label,
    activeStep?.description,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()

  const activeTool = tools.find((tool) => isToolRunningStatus(tool?.status))
  const activeToolName = resolveThinkingToolName(activeTool)
  if (activeToolName) return `调用${activeToolName}`

  const pendingTool = tools.find((tool) => String(tool?.status || '').trim().toLowerCase() === 'pending')
  const pendingToolName = resolveThinkingToolName(pendingTool)
  if (pendingToolName && /tool|invoke|call|execute|执行工具|调用工具/.test(stageSource)) {
    return `调用${pendingToolName}`
  }

  if (/output|reply|response|compose|draft|write|final|summary|summarize|polish|整理|输出|回复|润色|总结/.test(stageSource)) {
    return '正在输出'
  }

  if (/search|lookup|query|retrieve|find|match|检索|搜索|查找|匹配|召回/.test(stageSource)) {
    return '正在查找相关信息'
  }

  if (/tool|invoke|call|execute|执行工具|调用工具/.test(stageSource)) {
    return '正在调用工具'
  }

  if (/analy|understand|intent|plan|parse|think|理解|分析|需求|问题|思考/.test(stageSource)) {
    return '正在分析用户需求'
  }

  if (stageSource) return '正在思考'
  return '正在分析用户需求'
}

const thinkingBubbleState = computed(() => ({
  statusText: resolveThinkingStatusText(),
}))

const showPrestreamThinking = computed(() => {
  if (!loading.value || assistantStreaming.value) return false
  return !messages.value.some((item) => !isUserRole(item.role) && !String(item.content || '').trim() && !hasRichContent(item))
})

function formatTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  if (sameDay) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return date.toLocaleDateString()
}

function upsertConversation(conversation) {
  if (!conversation?.id) return
  const next = { ...conversation }
  const index = conversations.value.findIndex((item) => item.id === next.id)
  if (index >= 0) {
    conversations.value[index] = { ...conversations.value[index], ...next }
  } else {
    conversations.value.unshift(next)
  }
  conversations.value = [...conversations.value].sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
}

function upsertMessage(message) {
  const normalized = normalizeMessage(message)
  if (!normalized) return
  const index = messages.value.findIndex((item) => item.id === normalized.id)
  if (index >= 0) {
    messages.value[index] = { ...messages.value[index], ...normalized }
  } else {
    messages.value.push(normalized)
  }
  messages.value = [...messages.value]
}

function upsertServerUserMessage(message) {
  const normalized = normalizeMessage(message)
  if (!normalized) return

  const existingIndex = messages.value.findIndex((item) => item.id === normalized.id)
  if (existingIndex >= 0) {
    messages.value[existingIndex] = { ...messages.value[existingIndex], ...normalized, pending: false }
    messages.value = [...messages.value]
    return
  }

  const pendingIndex = messages.value.findIndex(
    (item) => item.pending && isUserRole(item.role) && String(item.content || '') === normalized.content,
  )
  if (pendingIndex >= 0) {
    messages.value[pendingIndex] = {
      ...messages.value[pendingIndex],
      ...normalized,
      pending: false,
    }
    messages.value = [...messages.value]
    return
  }

  upsertMessage({ ...normalized, pending: false })
}

function ensureAssistantMessage(messageId) {
  const targetId = messageId || currentAssistantMessageId.value
  if (!targetId) return null
  let existing = messages.value.find((item) => item.id === targetId)
  if (existing) return existing
  existing = normalizeMessage({
    id: targetId,
    role: 'assistant',
    content: '',
    payload: null,
    timestamp: new Date().toISOString(),
  })
  messages.value.push(existing)
  messages.value = [...messages.value]
  return existing
}

function cleanupEmptyAssistantMessage(messageId = currentAssistantMessageId.value) {
  const targetId = String(messageId || '').trim()
  if (!targetId) return
  const index = messages.value.findIndex((item) => item.id === targetId)
  if (index < 0) return
  const target = messages.value[index]
  if (String(target?.content || '').trim()) return
  if (hasRichContent(target)) return
  messages.value.splice(index, 1)
  messages.value = [...messages.value]
}

function attachMessagePayload(payload, messageId) {
  const target = ensureAssistantMessage(messageId)
  if (!target) return
  target.payload = normalizePayload(payload)
  messages.value = [...messages.value]
}

function appendAssistantDelta(text, messageId) {
  const target = ensureAssistantMessage(messageId)
  if (!target) return
  target.content = sanitizeInternalFailureText(
    `${target.content || ''}${text || ''}`,
    '后端服务刚刚出错了，请稍后再试。',
  )
  messages.value = [...messages.value]
}

function resetProgress() {
  progress.value = {
    current_stage: null,
    current_stage_label: '',
    current_stage_description: '',
    steps: [],
    tools: [],
  }
}

async function loadConversations() {
  sidebarLoading.value = true
  try {
    const res = await agentApi.listConversations({ limit: 50, offset: 0 })
    conversations.value = (res.conversations || []).slice().sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
  } finally {
    sidebarLoading.value = false
  }
}

async function loadConversationMessages(conversationId) {
  if (!conversationId) return
  requestError.value = ''
  resetProgress()
  assistantStreaming.value = false
  currentAssistantMessageId.value = null
  const res = await agentApi.getConversationMessages(conversationId, { limit: 200, offset: 0 })
  if (res.conversation) upsertConversation(res.conversation)
  messages.value = (res.messages || []).map((item) => normalizeMessage(item)).filter(Boolean)
  memorySummary.value = res.memory_summary || res.conversation?.memory_summary || ''
  scrollToBottom()
}

async function selectConversation(conversationId) {
  if (!conversationId || conversationId === activeConversationId.value) return
  requestError.value = ''
  activeConversationId.value = conversationId
  localStorage.setItem(STORAGE_KEY, conversationId)
  try {
    await loadConversationMessages(conversationId)
  } catch (error) {
    activeConversationId.value = null
    messages.value = []
    memorySummary.value = ''
    if (error?.response?.status === 404) {
      localStorage.removeItem(STORAGE_KEY)
    }
    throw error
  }
}

async function createNewConversation() {
  sidebarLoading.value = true
  try {
    const res = await agentApi.createConversation(DEFAULT_TITLE)
    if (res.conversation?.id) {
      upsertConversation(res.conversation)
      activeConversationId.value = res.conversation.id
      localStorage.setItem(STORAGE_KEY, res.conversation.id)
      messages.value = []
      memorySummary.value = ''
      requestError.value = ''
      resetProgress()
      assistantStreaming.value = false
      currentAssistantMessageId.value = null
    }
  } finally {
    sidebarLoading.value = false
  }
}

function startRenameConversation(conversation) {
  editingConversationId.value = conversation.id
  editingTitle.value = (conversation.title || '').trim() || DEFAULT_TITLE
}

function cancelRenameConversation() {
  editingConversationId.value = null
  editingTitle.value = ''
}

async function commitRenameConversation(conversationId) {
  if (!conversationId || editingConversationId.value !== conversationId) return
  const title = (editingTitle.value || '').trim() || DEFAULT_TITLE
  try {
    const res = await agentApi.renameConversation(conversationId, title)
    if (res.conversation) upsertConversation(res.conversation)
  } catch (error) {
    console.error('rename conversation error:', error)
  } finally {
    cancelRenameConversation()
  }
}

async function deleteConversation(conversationId) {
  if (!conversationId) return
  if (!window.confirm('确定删除这个对话吗？删除后不可恢复。')) return
  deletingConversationId.value = conversationId
  try {
    await agentApi.deleteConversation(conversationId)
    conversations.value = conversations.value.filter((item) => item.id !== conversationId)
    if (activeConversationId.value === conversationId) {
      activeConversationId.value = null
      messages.value = []
      memorySummary.value = ''
      resetProgress()
      assistantStreaming.value = false
      currentAssistantMessageId.value = null
      localStorage.removeItem(STORAGE_KEY)
    }
    if (!activeConversationId.value && conversations.value.length > 0) {
      await selectConversation(conversations.value[0].id)
    }
  } catch (error) {
    console.error('delete conversation error:', error)
  } finally {
    deletingConversationId.value = null
  }
}

function sendQuickQuestion(question) {
  inputMessage.value = question
  sendMessage(question)
}

function submitChat() {
  sendMessage()
}

function handleEnter() {
  if (isComposing.value) return
  sendMessage()
}

function handleRichSongPlay(payload) {
  if (!payload?.song) return
  heartModeActive.value = false
  clearPlayerError()
  playSong(payload.song, payload.queue)
}

async function handleHeartModePlay() {
  if (heartModeLoading.value) return

  requestError.value = ''
  heartModeLoading.value = true
  clearPlayerError()

  try {
    const response = await agentApi.getHeartModeQueue()
    const songs = Array.isArray(response?.songs) ? response.songs : []
    if (!songs.length) {
      throw new Error('当前没有可播放的心动模式歌曲。')
    }

    await playQueue(songs, 0)
    heartModeActive.value = true
  } catch (error) {
    heartModeActive.value = false
    const message = formatAxiosError(error)
    setPlayerError(message || '暂时无法开启心动模式。')
    requestError.value = message || '暂时无法开启心动模式。'
  } finally {
    heartModeLoading.value = false
  }
}

function lockFullscreenPageScroll() {
  previousBodyOverflow = document.body.style.overflow
  previousHtmlOverflow = document.documentElement.style.overflow
  document.body.style.overflow = 'hidden'
  document.documentElement.style.overflow = 'hidden'
}

function unlockFullscreenPageScroll() {
  document.body.style.overflow = previousBodyOverflow
  document.documentElement.style.overflow = previousHtmlOverflow
}

function scrollMusicFullscreenLyricsToActive(behavior = 'smooth') {
  nextTick(() => {
    const container = musicFullscreenLyricsViewport.value
    const activeIndex = musicFullscreenActiveLyricIndex.value
    if (!container || activeIndex < 0) return

    const target = container.querySelector(`[data-lyric-index="${activeIndex}"]`)
    if (!target) return

    const targetTop = target.offsetTop - container.clientHeight / 2 + target.clientHeight / 2
    scrollMusicFullscreenLyricsViewportTo(Math.max(0, targetTop), behavior)
  })
}

function stopMusicFullscreenLyricsScroll() {
  if (!musicFullscreenLyricsScrollFrame) return
  window.cancelAnimationFrame(musicFullscreenLyricsScrollFrame)
  musicFullscreenLyricsScrollFrame = 0
}

function tickMusicFullscreenLyricsScroll() {
  const container = musicFullscreenLyricsViewport.value
  if (!container) {
    musicFullscreenLyricsScrollFrame = 0
    return
  }

  const delta = musicFullscreenLyricsScrollTarget - container.scrollTop
  const distance = Math.abs(delta)

  if (distance < 0.6) {
    container.scrollTop = musicFullscreenLyricsScrollTarget
    musicFullscreenLyricsScrollFrame = 0
    return
  }

  const step = Math.sign(delta) * Math.min(Math.max(distance * 0.18, 0.9), 28)
  container.scrollTop += step
  musicFullscreenLyricsScrollFrame = window.requestAnimationFrame(tickMusicFullscreenLyricsScroll)
}

function scrollMusicFullscreenLyricsViewportTo(targetTop, behavior = 'smooth') {
  const container = musicFullscreenLyricsViewport.value
  if (!container) return

  musicFullscreenLyricsScrollTarget = Math.max(0, targetTop)

  if (behavior !== 'smooth') {
    stopMusicFullscreenLyricsScroll()
    container.scrollTop = musicFullscreenLyricsScrollTarget
    return
  }

  if (!musicFullscreenLyricsScrollFrame) {
    musicFullscreenLyricsScrollFrame = window.requestAnimationFrame(tickMusicFullscreenLyricsScroll)
  }
}

function shouldAlignMusicFullscreenLyrics() {
  return window.innerWidth > 992
}

function queueMusicFullscreenLyricsAlignment() {
  if (!musicFullscreenOpen.value) return
  if (!shouldAlignMusicFullscreenLyrics()) {
    musicFullscreenLyricsOffset.value = 0
    return
  }
  if (musicFullscreenLyricsAlignFrame) {
    window.cancelAnimationFrame(musicFullscreenLyricsAlignFrame)
  }

  musicFullscreenLyricsAlignFrame = window.requestAnimationFrame(() => {
    musicFullscreenLyricsAlignFrame = 0
    const coverCard = musicFullscreenCoverCard.value
    const volumeRow = musicFullscreenVolumeRow.value
    const lyricsViewport = musicFullscreenLyricsViewport.value
    if (!lyricsViewport) return

    const lyricsRect = lyricsViewport.getBoundingClientRect()
    let alignmentDelta = 0

    if (volumeRow) {
      const volumeRect = volumeRow.getBoundingClientRect()
      const targetBottom = volumeRect.top + volumeRect.height / 2
      alignmentDelta = targetBottom - lyricsRect.bottom
    } else if (coverCard) {
      const coverRect = coverCard.getBoundingClientRect()
      alignmentDelta = coverRect.top + coverRect.height / 2 - (lyricsRect.top + lyricsRect.height / 2)
    } else {
      return
    }

    if (!Number.isFinite(alignmentDelta) || Math.abs(alignmentDelta) < 0.5) return
    musicFullscreenLyricsOffset.value += alignmentDelta
  })
}

function handleMusicFullscreenResize() {
  if (!musicFullscreenOpen.value) return
  scrollMusicFullscreenLyricsToActive('auto')
  queueMusicFullscreenLyricsAlignment()
}

function runMusicFullscreenViewTransition(update) {
  const startViewTransition = typeof document !== 'undefined' && typeof document.startViewTransition === 'function'
    ? document.startViewTransition.bind(document)
    : null

  if (!startViewTransition) {
    update()
    return
  }

  startViewTransition(() => {
    update()
    return nextTick()
  })
}

function openMusicFullscreen() {
  if (!hasActiveTrack.value) return
  runMusicFullscreenViewTransition(() => {
    musicFullscreenOpen.value = true
  })
}

function closeMusicFullscreen() {
  runMusicFullscreenViewTransition(() => {
    musicFullscreenOpen.value = false
  })
}

function handleMusicFullscreenKeydown(event) {
  if (event.key === 'Escape') {
    closeMusicFullscreen()
  }
}

function handleFullscreenLyricClick(line) {
  const targetTime = Number(line?.time)
  if (!Number.isFinite(targetTime) || targetTime < 0) return
  void seekToTime(targetTime, { forcePlay: true })
}

function handleStreamEvent(event, data) {
  if (event === 'meta') {
    requestError.value = ''
    if (data.conversation) upsertConversation(data.conversation)
    if (data.conversation_id) {
      activeConversationId.value = data.conversation_id
      localStorage.setItem(STORAGE_KEY, data.conversation_id)
    }
    return
  }
  if (event === 'message' && data.message) {
    requestError.value = ''
    if (isUserRole(data.message.role)) upsertServerUserMessage(data.message)
    else upsertMessage(data.message)
    return
  }
  if (event === 'message_start' && data.message) {
    requestError.value = ''
    currentAssistantMessageId.value = data.message.id
    assistantStreaming.value = true
    upsertMessage(data.message)
    return
  }
  if (event === 'rich_content' && data.payload) {
    requestError.value = ''
    if (data.message_id) currentAssistantMessageId.value = data.message_id
    attachMessagePayload(data.payload, data.message_id)
    return
  }
  if (event === 'delta' && typeof data.text === 'string') {
    requestError.value = ''
    assistantStreaming.value = true
    if (data.message_id) currentAssistantMessageId.value = data.message_id
    appendAssistantDelta(data.text, data.message_id)
    return
  }
  if (event === 'final' && typeof data.text === 'string') {
    requestError.value = ''
    if (data.message_id) currentAssistantMessageId.value = data.message_id
    const target = ensureAssistantMessage(data.message_id)
    if (target && String(data.text).length > String(target.content || '').length) {
      target.content = sanitizeInternalFailureText(
        String(data.text),
        '后端服务刚刚出错了，请稍后再试。',
      )
      messages.value = [...messages.value]
    }
    return
  }
  if ((event === 'message_commit' || event === 'message_final') && data.message) {
    requestError.value = ''
    assistantStreaming.value = false
    upsertMessage(data.message)
    return
  }
  if (event === 'progress') {
    progress.value = {
      current_stage: data.current_stage || null,
      current_stage_label: data.current_stage_label || '',
      current_stage_description: sanitizeInternalFailureText(
        data.current_stage_description || '',
        '后端服务刚刚出错了，本次处理已中断。',
      ),
      steps: Array.isArray(data.steps) ? data.steps : [],
      tools: Array.isArray(data.tools) ? data.tools : [],
    }
    return
  }
  if (event === 'memory') {
    memorySummary.value = data.memory_summary || ''
  }
}

async function sendMessage(explicitText) {
  const text = (typeof explicitText === 'string' ? explicitText : inputMessage.value).trim()
  if (!text || loading.value) return

  requestError.value = ''
  loading.value = true
  assistantStreaming.value = false
  currentAssistantMessageId.value = null
  resetProgress()
  inputMessage.value = ''
  messages.value.push(
    normalizeMessage({
      id: `local_user_${Date.now()}_${Math.random().toString(16).slice(2)}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
      pending: true,
    }),
  )
  messages.value = [...messages.value]
  scrollToBottom()

  try {
    const res = await agentApi.chatStream(text, activeConversationId.value, {
      onEvent: handleStreamEvent,
    })

    if (res.conversation) upsertConversation(res.conversation)
    if (res.memory_summary) memorySummary.value = res.memory_summary
    if (res.message) upsertMessage(res.message)
    const resolvedConversationId = res.conversation_id || activeConversationId.value
    if (resolvedConversationId) {
      activeConversationId.value = resolvedConversationId
      localStorage.setItem(STORAGE_KEY, resolvedConversationId)
    }
    await loadConversations()
  } catch (error) {
    console.error('Agent chat error:', error)
    cleanupEmptyAssistantMessage()
    requestError.value = formatAxiosError(error)
  } finally {
    assistantStreaming.value = false
    loading.value = false
    scrollToBottom()
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesList.value) {
      messagesList.value.scrollTop = messagesList.value.scrollHeight
    }
  })
}

watch(
  [messages, activeConversationId],
  () => {
    scrollToBottom()
  },
  { deep: true },
)

watch(progress, () => {
  scrollToBottom()
}, { deep: true })

watch(
  () => String(playerDisplayTrack.value?.cover_url || '').trim(),
  async (coverUrl) => {
    const requestToken = ++musicThemeRequestToken

    if (!coverUrl) {
      musicFullscreenTheme.value = DEFAULT_MUSIC_COVER_THEME
      return
    }

    const nextTheme = await loadMusicCoverTheme(coverUrl)
    if (requestToken !== musicThemeRequestToken) return
    musicFullscreenTheme.value = nextTheme
  },
  { immediate: true },
)

watch(
  () => musicFullscreenOpen.value,
  (open) => {
    if (open) {
      lockFullscreenPageScroll()
      window.addEventListener('keydown', handleMusicFullscreenKeydown)
      window.addEventListener('resize', handleMusicFullscreenResize)
      musicFullscreenLyricsOffset.value = 0
      scrollMusicFullscreenLyricsToActive('auto')
      queueMusicFullscreenLyricsAlignment()
      return
    }

    window.removeEventListener('keydown', handleMusicFullscreenKeydown)
    window.removeEventListener('resize', handleMusicFullscreenResize)
    if (musicFullscreenLyricsAlignFrame) {
      window.cancelAnimationFrame(musicFullscreenLyricsAlignFrame)
      musicFullscreenLyricsAlignFrame = 0
    }
    stopMusicFullscreenLyricsScroll()
    unlockFullscreenPageScroll()
  },
)

watch(
  () => musicFullscreenActiveLyricIndex.value,
  (nextIndex, previousIndex) => {
    if (musicFullscreenOpen.value) {
      const shouldJumpImmediately = !Number.isFinite(previousIndex) || previousIndex < 0 || Math.abs(nextIndex - previousIndex) > 3
      scrollMusicFullscreenLyricsToActive(shouldJumpImmediately ? 'auto' : 'smooth')
    }
  },
)

watch(
  () => musicFullscreenLyricLines.value.length,
  () => {
    if (musicFullscreenOpen.value) {
      scrollMusicFullscreenLyricsToActive('auto')
    }
  },
)

watch(
  () => hasActiveTrack.value,
  (active) => {
    if (!active && musicFullscreenOpen.value) {
      closeMusicFullscreen()
    }
  },
)

onMounted(() => {
  ;(async () => {
    try {
    await loadConversations()
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      try {
        await selectConversation(saved)
        return
      } catch (error) {
        if (error?.response?.status !== 404) {
          console.warn('恢复会话失败：', error)
        }
      }
    }
    if (conversations.value.length > 0) {
      await selectConversation(conversations.value[0].id)
    }
    } catch (error) {
      console.error('initial load error:', error)
      requestError.value = formatAxiosError(error)
    }
  })()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleMusicFullscreenKeydown)
  window.removeEventListener('resize', handleMusicFullscreenResize)
  if (musicFullscreenLyricsAlignFrame) {
    window.cancelAnimationFrame(musicFullscreenLyricsAlignFrame)
  }
  stopMusicFullscreenLyricsScroll()
  unlockFullscreenPageScroll()
})
</script>

<style scoped>
.agent-layout {
  width: 100%;
  min-width: 100%;
  max-width: 100%;
  height: 100%;
  min-height: 100%;
  max-height: 100%;
  display: grid;
  grid-template-columns: 292px minmax(0, 1fr);
  gap: 18px;
  padding: 18px;
  background: transparent;
  min-width: 0;
  position: relative;
  -webkit-user-select: none;
  user-select: none;
}

.agent-rail {
  height: auto;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255, 255, 255, 0.48);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.34), rgba(255, 255, 255, 0.18));
  backdrop-filter: blur(28px) saturate(165%);
  box-shadow: var(--glass-shadow);
  border-radius: 30px;
  overflow: hidden;
  min-width: 0;
  min-height: 0;
  position: relative;
}

.agent-rail::before,
.chat-shell::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 140px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.34), rgba(255, 255, 255, 0));
  pointer-events: none;
}

.rail-top {
  padding: 18px 16px 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.18), rgba(255, 255, 255, 0.05));
  border-bottom: 1px solid rgba(255, 255, 255, 0.24);
  position: relative;
  z-index: 1;
}

.rail-title {
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.rail-new {
  width: 100%;
  height: 40px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.42);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.36), rgba(206, 226, 236, 0.22));
  color: var(--active-color);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-weight: 600;
  backdrop-filter: blur(16px);
  box-shadow: var(--glass-shadow-soft);
}

.rail-new:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 10px 26px rgba(74, 114, 158, 0.14);
}

.rail-new:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.rail-search {
  margin-top: 12px;
}

.rail-search-input {
  height: 40px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.34);
  background: rgba(255, 255, 255, 0.22);
  padding: 0 12px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.rail-list {
  flex: 0 0 198px;
  height: 198px;
  min-height: 0;
  margin: 10px 0 0;
  padding: 0 12px 12px;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 10px;
  scrollbar-width: thin;
  scrollbar-color: rgba(113, 139, 158, 0.48) transparent;
  overscroll-behavior: contain;
  position: relative;
  z-index: 1;
}

.rail-list::-webkit-scrollbar {
  width: 6px;
}

.rail-list::-webkit-scrollbar-track {
  background: transparent;
}

.rail-list::-webkit-scrollbar-thumb {
  background: rgba(113, 139, 158, 0.38);
  border-radius: 999px;
}

.rail-item {
  text-align: left;
  width: 100%;
  min-height: 82px;
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.16);
  border-radius: 18px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
  backdrop-filter: blur(14px);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18);
}

.rail-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.rail-item:hover {
  background: rgba(255, 255, 255, 0.24);
  border-color: rgba(255, 255, 255, 0.42);
  box-shadow: 0 12px 26px rgba(127, 153, 171, 0.12);
}

.rail-item.active {
  background: linear-gradient(135deg, rgba(203, 226, 236, 0.34), rgba(255, 255, 255, 0.26));
  border-color: rgba(255, 255, 255, 0.46);
  box-shadow: 0 16px 32px rgba(119, 149, 170, 0.16);
}

.rail-item-title {
  flex: 1;
  font-size: 14px;
  font-weight: 650;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rail-title-input {
  flex: 1;
  min-width: 0;
  border: 1px solid rgba(255, 255, 255, 0.46);
  border-radius: 10px;
  padding: 4px 8px;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.34);
}

.rail-item-actions {
  display: flex;
  gap: 6px;
}

.item-action-btn {
  border: none;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.24);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.item-action-btn:hover:not(:disabled) {
  background: rgba(74, 114, 158, 0.18);
  color: var(--active-color);
}

.item-action-btn.danger:hover:not(:disabled) {
  background: rgba(220, 53, 69, 0.18);
  color: #dc3545;
}

.item-action-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.action-icon {
  width: 14px;
  height: 14px;
  display: block;
}

.rail-item-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.rail-empty {
  flex: 0 0 198px;
  height: 198px;
  padding: 16px;
  color: var(--text-secondary);
  min-height: 0;
}

.rail-empty-title {
  font-weight: 650;
  color: var(--text-primary);
}

.rail-empty-sub {
  margin-top: 6px;
  font-size: 13px;
}

.rail-player-slot {
  margin-top: auto;
  padding: 14px 12px 14px;
  position: relative;
  z-index: 1;
  min-width: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.28);
  background:
    linear-gradient(180deg, rgba(238, 247, 250, 0.68), rgba(238, 247, 250, 0.16) 26%, rgba(255, 255, 255, 0));
  box-shadow: 0 -16px 28px rgba(224, 239, 244, 0.42);
}

.chat-shell {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.34), rgba(255, 255, 255, 0.2));
  border-radius: 34px;
  box-shadow: var(--glass-shadow);
  border: 1px solid rgba(255, 255, 255, 0.52);
  overflow: hidden;
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr auto;
  min-width: 0;
  position: relative;
  backdrop-filter: blur(30px) saturate(170%);
}

.chat-topbar {
  padding: 16px 18px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.1);
  min-width: 0;
  position: relative;
  z-index: 1;
}

.chat-topbar-title {
  font-weight: 700;
  color: var(--text-primary);
}

.chat-topbar-sub {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.chat-body {
  padding: 20px 22px;
  overflow: auto;
  scroll-behavior: smooth;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.03));
  min-width: 0;
}

.welcome-card,
.progress-card {
  background: rgba(255, 255, 255, 0.24);
  border: 1px solid rgba(255, 255, 255, 0.42);
  border-radius: 24px;
  padding: 18px 16px;
  margin: 4px 0 16px;
  box-shadow: var(--glass-shadow-soft);
  backdrop-filter: blur(22px);
}

.welcome-title,
.progress-title {
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.welcome-sub,
.progress-sub {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  justify-content: center;
}

.quick-question {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid rgba(255, 255, 255, 0.34);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.24);
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all var(--transition-normal);
  backdrop-filter: blur(14px);
}

.quick-question:hover {
  background: rgba(255, 255, 255, 0.34);
  border-color: rgba(255, 255, 255, 0.46);
}

.progress-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.progress-current {
  font-size: 13px;
  color: var(--active-color);
  font-weight: 600;
}

.progress-steps {
  display: grid;
  gap: 10px;
}

.progress-step {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.step-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  margin-top: 6px;
  background: rgba(0, 0, 0, 0.15);
  flex: 0 0 auto;
}

.progress-step.is-completed .step-dot {
  background: #2f9e44;
}

.progress-step.is-in_progress .step-dot {
  background: #1b6bce;
  box-shadow: 0 0 0 6px rgba(27, 107, 206, 0.12);
}

.progress-step.is-failed .step-dot {
  background: #dc3545;
}

.step-body {
  min-width: 0;
}

.step-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.step-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.tool-list {
  display: grid;
  gap: 8px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.24);
}

.tool-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}

.tool-name {
  color: var(--text-primary);
  word-break: break-all;
}

.tool-status {
  text-transform: capitalize;
  color: var(--text-secondary);
}

.tool-status.is-running {
  color: #1b6bce;
}

.tool-status.is-success {
  color: #2f9e44;
}

.tool-status.is-failed {
  color: #dc3545;
}

.chat-error-banner {
  margin: 0 18px 8px;
  padding: 10px 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.34);
  background: rgba(255, 240, 244, 0.6);
  color: #8e3b4b;
  font-size: 13px;
  line-height: 1.5;
  box-shadow: var(--glass-shadow-soft);
  backdrop-filter: blur(18px);
}

.chat-input {
  padding: 14px 16px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.26);
  background: rgba(255, 255, 255, 0.08);
  min-width: 0;
}

.input-form {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
  padding: 6px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.42);
  background: rgba(255, 255, 255, 0.2);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28), var(--glass-shadow-soft);
  backdrop-filter: blur(24px);
}

.message-input {
  flex: 1;
  min-width: 0;
  border-radius: 999px;
  padding: 12px 14px;
  border: none;
  background: transparent;
  box-shadow: none;
}

.rail-search-input,
.rail-title-input,
.message-input {
  -webkit-user-select: text;
  user-select: text;
}

.send-btn {
  height: 42px;
  padding: 0 18px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.34);
  background: linear-gradient(135deg, rgba(84, 119, 147, 0.94), rgba(133, 168, 187, 0.88));
  color: #fff;
  cursor: pointer;
  transition: all var(--transition-fast);
  box-shadow: 0 10px 22px rgba(89, 122, 149, 0.24);
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: linear-gradient(135deg, rgba(73, 109, 138, 0.96), rgba(124, 159, 179, 0.92));
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.music-fullscreen-page {
  position: fixed;
  inset: 0;
  z-index: 4000;
  overflow: hidden;
  color: rgba(255, 255, 255, 0.96);
  background:
    radial-gradient(circle at 20% 18%, rgba(var(--music-theme-bg-primary-rgb), 0.18), transparent 24%),
    radial-gradient(circle at 80% 18%, rgba(var(--music-theme-bg-secondary-rgb), 0.14), transparent 28%),
    linear-gradient(
      135deg,
      rgb(var(--music-theme-bg-base-rgb)) 0%,
      rgb(var(--music-theme-bg-base-rgb)) 56%,
      rgb(var(--music-theme-bg-secondary-rgb)) 100%
    );
  -webkit-user-select: none;
  user-select: none;
  -webkit-touch-callout: none;
  backdrop-filter: blur(28px) saturate(128%);
  isolation: isolate;
}

.music-fullscreen-page-bg,
.music-fullscreen-page-orb,
.music-fullscreen-page-glow,
.music-fullscreen-page-noise {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.music-fullscreen-page-bg {
  inset: -10%;
  opacity: 0.16;
  transform: scale(1.22);
}

.music-fullscreen-page.has-cover .music-fullscreen-page-bg {
  background-image: var(--music-fullscreen-cover);
  background-size: cover;
  background-position: center;
  filter: blur(168px) saturate(1.22) brightness(0.36);
  mix-blend-mode: lighten;
}

.music-fullscreen-page-orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(152px);
  opacity: 0.92;
}

.music-fullscreen-page-orb--primary {
  inset: auto;
  width: min(38vw, 620px);
  height: min(38vw, 620px);
  top: 10%;
  left: 2%;
  background: rgba(var(--music-theme-accent-rgb), 0.8);
  animation: music-fullscreen-bg-float-primary 12s ease-in-out infinite;
}

.music-fullscreen-page-orb--secondary {
  inset: auto;
  width: min(34vw, 520px);
  height: min(34vw, 520px);
  right: 8%;
  bottom: 8%;
  background: rgba(var(--music-theme-bg-primary-rgb), 0.42);
  animation: music-fullscreen-bg-float-secondary 15s ease-in-out infinite;
}

.music-fullscreen-page-glow {
  background:
    radial-gradient(circle at 20% 30%, rgba(var(--music-theme-highlight-rgb), 0.12), transparent 16%),
    radial-gradient(circle at 72% 52%, rgba(var(--music-theme-accent-rgb), 0.07), transparent 18%),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0) 24%, rgba(0, 0, 0, 0.2) 54%, rgba(255, 255, 255, 0) 74%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0) 28%, rgba(0, 0, 0, 0.24) 100%);
}

.music-fullscreen-page-noise {
  opacity: 0.06;
  background-image:
    radial-gradient(rgba(255, 255, 255, 0.14) 0.55px, transparent 0.8px),
    radial-gradient(rgba(0, 0, 0, 0.12) 0.55px, transparent 0.8px);
  background-size: 24px 24px, 32px 32px;
  background-position: 0 0, 11px 11px;
  mix-blend-mode: soft-light;
}

.music-fullscreen-page-exit {
  position: absolute;
  top: 26px;
  left: 24px;
  z-index: 3;
  width: 44px;
  height: 44px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.94);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.music-fullscreen-page-exit:hover {
  transform: translateY(-1px);
  opacity: 1;
}

.music-fullscreen-page-exit-icon {
  width: 26px;
  height: 26px;
  display: block;
}

.music-fullscreen-page-shell {
  position: relative;
  z-index: 2;
  height: 100%;
  width: min(100%, 1360px);
  max-width: 1360px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(460px, 620px) minmax(460px, 620px);
  align-items: center;
  justify-content: center;
  gap: clamp(52px, 6vw, 112px);
  padding: 56px 42px 40px;
}

.music-fullscreen-player-side {
  --music-fullscreen-stage-width: 356px;
  --music-fullscreen-cover-width: 316px;
  --music-fullscreen-panel-offset: calc((var(--music-fullscreen-stage-width) - var(--music-fullscreen-cover-width)) / -2);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 24px;
  min-height: 0;
  padding-left: 0;
}

.music-fullscreen-cover-stage {
  position: relative;
  width: min(30vw, var(--music-fullscreen-stage-width));
  max-width: var(--music-fullscreen-stage-width);
  height: 328px;
  display: grid;
  align-items: start;
  justify-items: start;
}

.music-fullscreen-cover-stage::before {
  content: '';
  position: absolute;
  inset: 20px -16px 0 -24px;
  border-radius: 999px;
  background: radial-gradient(circle at 30% 42%, rgba(var(--music-theme-accent-rgb), 0.42), transparent 58%);
  filter: blur(48px);
  opacity: 0.92;
}

.music-fullscreen-vinyl {
  position: absolute;
  left: 174px;
  top: 34px;
  width: 170px;
  aspect-ratio: 1;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 48%, #1d1d1d 0%, #090909 56%, #010101 84%, #242424 100%);
  box-shadow:
    0 18px 34px rgba(0, 0, 0, 0.36),
    inset 0 0 0 1px rgba(255, 255, 255, 0.05);
}

.music-fullscreen-vinyl.is-playing {
  animation: music-fullscreen-vinyl-spin 16s linear infinite;
}

.music-fullscreen-vinyl-rings,
.music-fullscreen-vinyl-sheen,
.music-fullscreen-vinyl-core {
  position: absolute;
  border-radius: 50%;
}

.music-fullscreen-vinyl-rings {
  inset: 3%;
  background:
    repeating-radial-gradient(
      circle at center,
      rgba(255, 255, 255, 0.06) 0 2px,
      rgba(255, 255, 255, 0.01) 2px 7px,
      rgba(0, 0, 0, 0.16) 7px 10px
    );
  opacity: 0.48;
}

.music-fullscreen-vinyl-sheen {
  inset: 0;
  background: linear-gradient(130deg, rgba(255, 255, 255, 0.24), transparent 38%, rgba(255, 255, 255, 0) 58%, rgba(255, 255, 255, 0.08) 78%, transparent 100%);
  mix-blend-mode: screen;
  opacity: 0.54;
}

.music-fullscreen-vinyl-core {
  inset: 40%;
  overflow: hidden;
  background: radial-gradient(circle, #434343 0%, #262626 58%, #141414 100%);
  box-shadow: 0 0 0 8px rgba(0, 0, 0, 0.32);
}

.music-fullscreen-vinyl-core-image {
  display: none;
}

.music-fullscreen-vinyl-core-image--placeholder,
.music-fullscreen-cover-image--placeholder {
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, rgba(var(--music-theme-highlight-rgb), 0.82), rgba(var(--music-theme-bg-primary-rgb), 0.86));
  color: rgba(255, 255, 255, 0.92);
}

.music-fullscreen-cover-card {
  position: relative;
  z-index: 2;
  width: min(100%, var(--music-fullscreen-cover-width));
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.04);
  box-shadow:
    0 22px 44px rgba(0, 0, 0, 0.28),
    0 0 0 1px rgba(255, 255, 255, 0.14),
    inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

.music-fullscreen-cover-card.is-view-transition-target {
  view-transition-name: music-player-cover-art;
}

.music-fullscreen-cover-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.18), transparent 26%, rgba(0, 0, 0, 0.14) 100%);
  pointer-events: none;
}

.music-fullscreen-cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.music-fullscreen-cover-placeholder-icon {
  width: 76px;
  height: 76px;
}

.music-fullscreen-song-panel {
  position: relative;
  width: min(100%, var(--music-fullscreen-cover-width));
  align-self: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  transform: translateX(var(--music-fullscreen-panel-offset));
}

.music-fullscreen-song-head {
  width: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
}

.music-fullscreen-song-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.music-fullscreen-song-title {
  font-size: clamp(18px, 1.65vw, 28px);
  line-height: 1.08;
  font-weight: 760;
  letter-spacing: 0.01em;
  text-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
}

.music-fullscreen-song-artist {
  font-size: clamp(14px, 0.92vw, 17px);
  color: rgba(255, 255, 255, 0.78);
}

.music-fullscreen-progress-row {
  width: 100%;
  margin-top: 2px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
}

.music-fullscreen-time {
  min-width: 46px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.9);
  font-variant-numeric: tabular-nums;
}

.music-fullscreen-progress-range {
  width: 100%;
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  border: none;
  outline: none;
  box-shadow: none;
  padding: 0;
}

.music-fullscreen-progress-range::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    var(--slider-fill-color, rgba(78, 162, 255, 0.98)) 0%,
    var(--slider-fill-color, rgba(78, 162, 255, 0.98)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(168, 181, 203, 0.34)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(168, 181, 203, 0.34)) 100%
  );
}

.music-fullscreen-progress-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  margin-top: -6px;
  border-radius: 50%;
  border: none;
  background: var(--slider-thumb-color, #4ea2ff);
  box-shadow:
    0 0 0 4px rgba(36, 123, 212, 0.16),
    0 0 14px var(--slider-thumb-shadow, rgba(78, 162, 255, 0.28));
}

.music-fullscreen-progress-range::-moz-range-track {
  height: 4px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    var(--slider-fill-color, rgba(78, 162, 255, 0.98)) 0%,
    var(--slider-fill-color, rgba(78, 162, 255, 0.98)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(168, 181, 203, 0.34)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(168, 181, 203, 0.34)) 100%
  );
}

.music-fullscreen-progress-range::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border: none;
  border-radius: 50%;
  background: var(--slider-thumb-color, #4ea2ff);
  box-shadow:
    0 0 0 4px rgba(36, 123, 212, 0.16),
    0 0 14px var(--slider-thumb-shadow, rgba(78, 162, 255, 0.28));
}

.music-fullscreen-transport-row {
  width: 100%;
  margin-top: 10px;
  display: grid;
  grid-template-columns: 42px 42px 54px 42px 42px;
  align-items: center;
  justify-content: center;
  column-gap: 18px;
}

.music-fullscreen-transport-spacer {
  width: 42px;
  height: 42px;
  opacity: 0;
  pointer-events: none;
}

.music-fullscreen-transport-btn {
  position: relative;
  width: 42px;
  height: 42px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.2s ease, opacity 0.2s ease, color 0.2s ease, filter 0.2s ease;
}

.music-fullscreen-transport-btn:hover:not(:disabled) {
  transform: translateY(-1px) scale(1.04);
  color: rgba(255, 255, 255, 1);
  filter: brightness(1.02);
}

.music-fullscreen-transport-btn:disabled {
  opacity: 0.22;
  cursor: not-allowed;
}

.music-fullscreen-transport-btn--primary {
  width: 54px;
  height: 54px;
  border-radius: 0;
  color: rgba(255, 255, 255, 0.98);
  background: transparent;
  box-shadow: none;
  filter: drop-shadow(0 6px 16px rgba(255, 255, 255, 0.16));
}

.music-fullscreen-transport-btn--primary:hover:not(:disabled) {
  color: rgba(255, 255, 255, 1);
  filter: drop-shadow(0 8px 18px rgba(255, 255, 255, 0.2));
  box-shadow: none;
}

.music-fullscreen-transport-icon {
  width: 28px;
  height: 28px;
  display: block;
}

.music-fullscreen-transport-icon--primary {
  width: 38px;
  height: 38px;
}

.music-fullscreen-volume-shell {
  width: 42px;
  height: 42px;
}

.music-fullscreen-volume-row {
  width: 100%;
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr) 46px;
  align-items: center;
  gap: 12px;
}

.music-fullscreen-volume-toggle {
  justify-self: start;
  color: rgba(255, 255, 255, 0.84);
}

.music-fullscreen-volume-toggle:hover:not(:disabled) {
  color: #fff;
}

.music-fullscreen-volume-spacer {
  width: 46px;
  height: 42px;
  opacity: 0;
  pointer-events: none;
}

.music-fullscreen-lyrics-side {
  min-height: 0;
  position: relative;
  justify-self: end;
  width: min(100%, 620px);
  height: min(100%, 820px);
  display: flex;
  align-items: center;
  color: rgba(255, 255, 255, 0.96);
  padding-right: 56px;
  transform: translateY(var(--music-fullscreen-lyrics-offset, 0px));
  -webkit-user-select: none;
  user-select: none;
  -webkit-touch-callout: none;
}

.music-fullscreen-copy-center {
  position: relative;
  width: 100%;
  max-width: 620px;
  height: 700px;
  overflow-y: auto;
  scrollbar-width: none;
  mask-image: linear-gradient(180deg, transparent 0%, #000 15%, #000 93%, transparent 100%);
  padding: 320px 0;
  margin: 0 auto;
}

.music-fullscreen-copy-center::-webkit-scrollbar {
  display: none;
}

.music-fullscreen-copy-track {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.music-fullscreen-copy-line {
  position: relative;
  width: min(100%, 560px);
  text-align: center;
  font-size: clamp(15px, 1.06vw, 20px);
  line-height: 1.6;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.24);
  transition:
    color 0.38s ease,
    opacity 0.38s ease,
    transform 0.38s ease,
    filter 0.38s ease;
  transform-origin: center center;
  will-change: transform;
  text-shadow: 0 0 14px rgba(0, 0, 0, 0.06);
  -webkit-user-select: none;
  user-select: none;
}

.music-fullscreen-copy-line.is-clickable {
  cursor: pointer;
}

.music-fullscreen-copy-line.is-clickable:hover {
  color: rgba(255, 255, 255, 0.5);
}

.music-fullscreen-copy-line.is-near {
  color: rgba(255, 255, 255, 0.46);
}

.music-fullscreen-copy-line.is-side {
  color: rgba(255, 255, 255, 0.3);
}

.music-fullscreen-copy-line.is-far {
  color: rgba(255, 255, 255, 0.18);
}

.music-fullscreen-copy-line.is-active {
  color: #fff;
  font-size: clamp(20px, 1.42vw, 31px);
  font-weight: 770;
  transform: none;
  filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.16));
  text-shadow: 0 0 24px rgba(var(--music-theme-highlight-rgb), 0.2);
  animation: music-fullscreen-lyric-breathe 2.6s ease-in-out infinite;
}

.music-fullscreen-copy-line.is-active::before,
.music-fullscreen-copy-line.is-active::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 16px;
  height: 18px;
  transform: translateY(-50%);
  opacity: 0.94;
  background: repeating-linear-gradient(90deg, rgba(var(--music-theme-accent-rgb), 1) 0 3px, transparent 3px 7px);
  filter: drop-shadow(0 0 14px rgba(var(--music-theme-accent-rgb), 0.42));
}

.music-fullscreen-copy-line.is-active::before {
  left: -28px;
}

.music-fullscreen-copy-line.is-active::after {
  right: -28px;
}

.music-fullscreen-volume-icon {
  width: 20px;
  height: 20px;
  display: block;
}

.music-fullscreen-volume-range {
  width: 100%;
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  border: none;
  outline: none;
  box-shadow: none;
  padding: 0;
}

.music-fullscreen-volume-range--horizontal {
  margin: 0;
}

.music-fullscreen-volume-range::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    var(--slider-fill-color, rgba(255, 255, 255, 0.96)) 0%,
    var(--slider-fill-color, rgba(255, 255, 255, 0.96)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(255, 255, 255, 0.26)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(255, 255, 255, 0.26)) 100%
  );
}

.music-fullscreen-volume-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -5px;
  border-radius: 50%;
  border: none;
  background: var(--slider-thumb-color, #ffffff);
  box-shadow: 0 0 0 4px var(--slider-thumb-shadow, rgba(255, 255, 255, 0.18));
}

.music-fullscreen-volume-range::-moz-range-track {
  height: 4px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    var(--slider-fill-color, rgba(255, 255, 255, 0.96)) 0%,
    var(--slider-fill-color, rgba(255, 255, 255, 0.96)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(255, 255, 255, 0.26)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(255, 255, 255, 0.26)) 100%
  );
}

.music-fullscreen-volume-range::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border: none;
  border-radius: 50%;
  background: var(--slider-thumb-color, #ffffff);
  box-shadow: 0 0 0 4px var(--slider-thumb-shadow, rgba(255, 255, 255, 0.18));
}

.music-fullscreen-page-enter-active,
.music-fullscreen-page-leave-active {
  transition: opacity 0.32s ease;
}

.music-fullscreen-page-enter-from,
.music-fullscreen-page-leave-to {
  opacity: 0;
}

.music-fullscreen-page-enter-from .music-fullscreen-cover-stage,
.music-fullscreen-page-leave-to .music-fullscreen-cover-stage {
  transform: scale(0.96) translateY(22px);
  opacity: 0;
}

.music-fullscreen-page-enter-from .music-fullscreen-lyrics-side,
.music-fullscreen-page-leave-to .music-fullscreen-lyrics-side {
  transform: translateX(24px) translateY(var(--music-fullscreen-lyrics-offset, 0px));
  opacity: 0;
}

@keyframes music-fullscreen-vinyl-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes music-fullscreen-bg-float-primary {
  0%, 100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(36px, -24px, 0);
  }
}

@keyframes music-fullscreen-bg-float-secondary {
  0%, 100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(-28px, 24px, 0);
  }
}

@keyframes music-fullscreen-lyric-breathe {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.04);
  }
}

</style>
