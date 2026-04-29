<template>
  <div class="floating-player" :class="{ 'is-idle': !hasActiveTrack }">
    <div class="floating-player-head">
      <div class="floating-player-heading">
        <div class="floating-player-label">媒体播放</div>
        <div class="floating-player-status">{{ playerStatusText }}</div>
      </div>
      <div class="floating-player-actions">
        <button
          type="button"
          class="floating-player-fullscreen"
          title="进入全屏音乐模式"
          aria-label="进入全屏音乐模式"
          :disabled="!hasActiveTrack || !onEnterFullscreen"
          @click="onEnterFullscreen"
        >
          <svg viewBox="0 0 24 24" class="floating-player-fullscreen-icon">
            <rect
              x="10.25"
              y="4.75"
              width="8"
              height="8"
              rx="0.7"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linejoin="round"
            />
            <rect
              x="5.75"
              y="9.25"
              width="8"
              height="8"
              rx="0.7"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linejoin="round"
            />
          </svg>
        </button>
        <button
          type="button"
          class="floating-player-accessory"
          :class="{ 'is-active': heartModeActive, 'is-loading': heartModeLoading }"
          :disabled="heartModeLoading || !onAccessoryClick"
          :title="accessoryTitle"
          :aria-label="accessoryTitle"
          @click="onAccessoryClick"
        >
          <svg viewBox="0 0 24 24" class="floating-player-accessory-icon">
            <path
              class="floating-player-accessory-heart-fill"
              d="M12 20.45 10.92 19.45C5.56 14.57 2.5 11.76 2.5 8.12 2.5 5.31 4.67 3.25 7.18 3.25c1.79 0 3.24.93 4.07 2.17.83-1.24 2.28-2.17 4.07-2.17 2.51 0 4.68 2.06 4.68 4.87 0 3.64-3.06 6.45-8.42 11.33L12 20.45Z"
            />
            <path
              d="M12 20.45 10.92 19.45C5.56 14.57 2.5 11.76 2.5 8.12 2.5 5.31 4.67 3.25 7.18 3.25c1.79 0 3.24.93 4.07 2.17.83-1.24 2.28-2.17 4.07-2.17 2.51 0 4.68 2.06 4.68 4.87 0 3.64-3.06 6.45-8.42 11.33L12 20.45Z"
              fill="none"
              stroke="currentColor"
              stroke-width="1.7"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </button>
      </div>
    </div>

    <div class="floating-player-spacer" aria-hidden="true">
      <span></span><span></span><span></span>
    </div>

    <div
      class="floating-player-cover-wrap"
      :class="{
        'is-fullscreen-ready': hasActiveTrack && !!onEnterFullscreen,
        'is-view-transition-source': hasActiveTrack && !!onEnterFullscreen && !fullscreenOpen,
      }"
      :role="hasActiveTrack && !!onEnterFullscreen ? 'button' : undefined"
      :tabindex="hasActiveTrack && !!onEnterFullscreen ? 0 : -1"
      :aria-label="hasActiveTrack && !!onEnterFullscreen ? '进入全屏音乐模式' : undefined"
      @click="handleEnterFullscreen"
      @keydown.enter.prevent="handleEnterFullscreen"
      @keydown.space.prevent="handleEnterFullscreen"
    >
      <img
        v-if="playerDisplayTrack.cover_url"
        class="floating-player-cover"
        :src="playerDisplayTrack.cover_url"
        :alt="playerDisplayTrack.name"
      />
      <div v-else class="floating-player-cover placeholder" aria-hidden="true">
        <svg viewBox="0 0 24 24" class="player-placeholder-icon">
          <path d="M15 5v9.2a3.2 3.2 0 1 1-1.5-2.74V7.1l6-1.4v7.5a3.2 3.2 0 1 1-1.5-2.74V4.1L15 5z" fill="currentColor" />
        </svg>
      </div>
    </div>

    <div class="floating-player-name">{{ playerDisplayTrack.name }}</div>
    <div v-if="!hasActiveTrack" class="floating-player-subtitle">
      {{ playerDisplayTrack.artist }}
      <span v-if="playerDisplayTrack.album"> / {{ playerDisplayTrack.album }}</span>
    </div>
    <div v-if="!hasActiveTrack && !playerError" class="floating-player-hint">
      点右上角心动模式，或者点击歌曲卡片后，这里会开始播放。
    </div>
    <div
      v-if="hasActiveTrack"
      class="floating-player-lyrics"
      :class="{ 'is-placeholder': lyricsLoading || !hasLyricsAvailable }"
    >
      <div class="floating-player-lyrics-current">{{ activeLyricLine }}</div>
      <div v-if="secondaryLyricLine" class="floating-player-lyrics-next">{{ secondaryLyricLine }}</div>
    </div>
    <div v-if="playerError" class="floating-player-error">{{ playerError }}</div>

    <input
      class="floating-player-range"
      type="range"
      min="0"
      :max="playerDuration || 0"
      step="0.1"
      :value="Math.min(playerCurrentTime, playerDuration || 0)"
      :style="progressSliderStyle"
      :disabled="!hasActiveTrack"
      @input="onSeekTrack"
    />
    <div class="floating-player-times">
      <span>{{ elapsedTimeLabel }}</span>
      <span>{{ remainingTimeLabel }}</span>
    </div>

    <div class="floating-player-controls">
      <button
        type="button"
        class="player-icon-btn player-icon-btn--transport"
        :disabled="!hasActiveTrack || !canPlayPrev"
        title="上一首"
        aria-label="上一首"
        @click="onPlayPrev"
      >
        <svg viewBox="0 0 28 28" class="player-icon player-icon--transport">
          <rect x="5" y="6.2" width="2.4" height="15.6" rx="1.2" fill="currentColor" />
          <path d="M20.8 6.8v14.4c0 .54-.6.87-1.07.57L9.4 15.08a1.28 1.28 0 0 1 0-2.16l10.33-6.7c.47-.3 1.07.03 1.07.57Z" fill="currentColor" />
        </svg>
      </button>
      <button
        type="button"
        class="player-icon-btn player-icon-btn--primary"
        :disabled="!hasActiveTrack"
        :title="isAudioPlaying ? '暂停' : '播放'"
        :aria-label="isAudioPlaying ? '暂停' : '播放'"
        @click="onToggleTrack"
      >
        <svg v-if="!isAudioPlaying" viewBox="0 0 28 28" class="player-icon player-icon--primary">
          <path d="M9.2 6.8v14.4c0 .58.63.94 1.14.63l11.08-7.2c.48-.32.48-1.02 0-1.34L10.34 6.17c-.5-.32-1.14.04-1.14.63Z" fill="currentColor" />
        </svg>
        <svg v-else viewBox="0 0 28 28" class="player-icon player-icon--primary">
          <rect x="8" y="6.2" width="4.3" height="15.6" rx="1.6" fill="currentColor" />
          <rect x="15.7" y="6.2" width="4.3" height="15.6" rx="1.6" fill="currentColor" />
        </svg>
      </button>
      <button
        type="button"
        class="player-icon-btn player-icon-btn--transport"
        :disabled="!hasActiveTrack || !canPlayNext"
        title="下一首"
        aria-label="下一首"
        @click="onPlayNext"
      >
        <svg viewBox="0 0 28 28" class="player-icon player-icon--transport">
          <rect x="20.6" y="6.2" width="2.4" height="15.6" rx="1.2" fill="currentColor" />
          <path d="M7.2 6.8v14.4c0 .54.6.87 1.07.57l10.33-6.7a1.28 1.28 0 0 0 0-2.16L8.27 6.23c-.47-.3-1.07.03-1.07.57Z" fill="currentColor" />
        </svg>
      </button>
    </div>

    <div class="floating-player-volume">
      <button
        type="button"
        class="player-icon-btn player-icon-btn--volume"
        :disabled="!hasActiveTrack"
        :title="isMuted ? '取消静音' : '静音'"
        :aria-label="isMuted ? '取消静音' : '静音'"
        @click="onToggleMute"
      >
        <svg v-if="isMuted" viewBox="0 0 24 24" class="player-icon">
          <path d="M4 10h3.5L12 6.5v11L7.5 14H4zM16 9l4 6M20 9l-4 6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <svg v-else-if="playerVolume < 0.34" viewBox="0 0 24 24" class="player-icon">
          <path d="M4 10h3.5L12 6.5v11L7.5 14H4z" fill="currentColor" />
          <path d="M16 10.2a3 3 0 0 1 0 3.6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <svg v-else viewBox="0 0 24 24" class="player-icon">
          <path d="M4 10h3.5L12 6.5v11L7.5 14H4z" fill="currentColor" />
          <path d="M16 9a4.5 4.5 0 0 1 0 6M18.8 6.8a7.6 7.6 0 0 1 0 10.4" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <input
        class="floating-volume-range"
        type="range"
        min="0"
        max="1"
        step="0.01"
        :value="playerVolume"
        :style="volumeSliderStyle"
        :disabled="!hasActiveTrack"
        @input="onUpdateVolume"
      />
      <div class="floating-player-volume-indicator" aria-hidden="true">
        <svg viewBox="0 0 24 24" class="player-icon player-icon--volume-trailing">
          <path d="M4 10h3.5L12 6.5v11L7.5 14H4z" fill="currentColor" />
          <path d="M16 9a4.5 4.5 0 0 1 0 6M18.8 6.8a7.6 7.6 0 0 1 0 10.4" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </div>
    </div>

    <audio
      :ref="audioRef"
      class="floating-player-audio"
      preload="none"
      @loadstart="onAudioLoadStart"
      @play="onAudioPlay"
      @playing="onAudioPlaying"
      @pause="onAudioPause"
      @waiting="onAudioWaiting"
      @stalled="onAudioWaiting"
      @ended="onAudioEnded"
      @loadedmetadata="onAudioLoadedMetadata"
      @timeupdate="onAudioTimeUpdate"
      @volumechange="onAudioVolumeChange"
      @error="onAudioError"
    ></audio>
  </div>
</template>

<script setup>
const props = defineProps({
  accessoryTitle: {
    type: String,
    default: '开启心动模式',
  },
  activeLyricLine: {
    type: String,
    default: '',
  },
  audioRef: {
    type: [Object, Function],
    default: null,
  },
  canPlayNext: {
    type: Boolean,
    default: false,
  },
  canPlayPrev: {
    type: Boolean,
    default: false,
  },
  elapsedTimeLabel: {
    type: String,
    default: '00:00',
  },
  hasActiveTrack: {
    type: Boolean,
    default: false,
  },
  heartModeActive: {
    type: Boolean,
    default: false,
  },
  heartModeLoading: {
    type: Boolean,
    default: false,
  },
  fullscreenOpen: {
    type: Boolean,
    default: false,
  },
  hasLyricsAvailable: {
    type: Boolean,
    default: false,
  },
  isAudioPlaying: {
    type: Boolean,
    default: false,
  },
  isMuted: {
    type: Boolean,
    default: false,
  },
  lyricsLoading: {
    type: Boolean,
    default: false,
  },
  onAccessoryClick: {
    type: Function,
    default: undefined,
  },
  onAudioEnded: {
    type: Function,
    default: undefined,
  },
  onAudioError: {
    type: Function,
    default: undefined,
  },
  onAudioLoadedMetadata: {
    type: Function,
    default: undefined,
  },
  onAudioLoadStart: {
    type: Function,
    default: undefined,
  },
  onAudioPause: {
    type: Function,
    default: undefined,
  },
  onAudioPlay: {
    type: Function,
    default: undefined,
  },
  onAudioPlaying: {
    type: Function,
    default: undefined,
  },
  onAudioTimeUpdate: {
    type: Function,
    default: undefined,
  },
  onAudioVolumeChange: {
    type: Function,
    default: undefined,
  },
  onAudioWaiting: {
    type: Function,
    default: undefined,
  },
  onEnterFullscreen: {
    type: Function,
    default: undefined,
  },
  onPlayNext: {
    type: Function,
    default: undefined,
  },
  onPlayPrev: {
    type: Function,
    default: undefined,
  },
  onSeekTrack: {
    type: Function,
    default: undefined,
  },
  onToggleMute: {
    type: Function,
    default: undefined,
  },
  onToggleTrack: {
    type: Function,
    default: undefined,
  },
  onUpdateVolume: {
    type: Function,
    default: undefined,
  },
  playerCurrentTime: {
    type: Number,
    default: 0,
  },
  playerDisplayTrack: {
    type: Object,
    required: true,
  },
  playerDuration: {
    type: Number,
    default: 0,
  },
  playerError: {
    type: String,
    default: '',
  },
  playerStatusText: {
    type: String,
    default: '等待播放',
  },
  playerVolume: {
    type: Number,
    default: 0.82,
  },
  progressSliderStyle: {
    type: Object,
    default: () => ({}),
  },
  remainingTimeLabel: {
    type: String,
    default: '-00:00',
  },
  secondaryLyricLine: {
    type: String,
    default: '',
  },
  volumeSliderStyle: {
    type: Object,
    default: () => ({}),
  },
})

function handleEnterFullscreen() {
  if (!props.hasActiveTrack || typeof props.onEnterFullscreen !== 'function') return
  props.onEnterFullscreen()
}
</script>

<style scoped>
.floating-player {
  position: relative;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  padding: 16px 16px 14px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.32), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.38), rgba(217, 230, 238, 0.24));
  border: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow: 0 14px 30px rgba(111, 137, 157, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.34);
  backdrop-filter: blur(30px) saturate(168%);
  color: var(--text-primary);
  overflow: hidden;
}

.floating-player::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 96px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0));
  pointer-events: none;
}

.floating-player.is-idle {
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.26), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.3), rgba(209, 222, 231, 0.2));
}

.floating-player-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  position: relative;
  z-index: 1;
}

.floating-player-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.floating-player-heading {
  min-width: 0;
  flex: 1;
}

.floating-player-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.floating-player-status {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.floating-player-accessory,
.floating-player-fullscreen {
  width: 34px;
  height: 34px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
  color: rgba(108, 133, 153, 0.76);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.32);
  transition:
    transform var(--transition-fast),
    color var(--transition-fast),
    background var(--transition-fast),
    box-shadow var(--transition-fast);
}

.floating-player-fullscreen {
  display: none;
}

.floating-player-accessory:hover:not(:disabled),
.floating-player-fullscreen:hover:not(:disabled) {
  transform: scale(1.04);
  color: rgba(191, 78, 106, 0.98);
  background: rgba(255, 255, 255, 0.3);
  box-shadow: 0 8px 18px rgba(191, 78, 106, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.42);
}

.floating-player-accessory:disabled,
.floating-player-fullscreen:disabled {
  opacity: 0.52;
  cursor: not-allowed;
}

.floating-player-accessory.is-active {
  color: rgba(198, 77, 108, 0.98);
  background: rgba(255, 244, 247, 0.82);
  box-shadow: 0 8px 18px rgba(198, 77, 108, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.56);
}

.floating-player-accessory.is-active .floating-player-accessory-heart-fill {
  opacity: 0.22;
  transform: scale(0.92);
}

.floating-player-accessory.is-loading {
  animation: floating-heart-pulse 1.1s ease-in-out infinite;
}

.floating-player-accessory-icon {
  width: 18px;
  height: 18px;
  display: block;
}

.floating-player-accessory-heart-fill {
  fill: currentColor;
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}

.floating-player-fullscreen-icon {
  width: 17px;
  height: 17px;
  display: block;
}

@keyframes floating-heart-pulse {
  0%,
  100% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.08);
  }
}

.floating-player-spacer {
  display: flex;
  justify-content: center;
  gap: 4px;
  margin-top: 10px;
  position: relative;
  z-index: 1;
  opacity: 0.34;
}

.floating-player-spacer span {
  width: 4px;
  height: 4px;
  border-radius: 999px;
  background: rgba(103, 128, 148, 0.46);
}

.floating-player-cover-wrap {
  display: flex;
  justify-content: center;
  margin-top: 8px;
  padding: 8px 0 2px;
  position: relative;
  z-index: 1;
  min-width: 0;
  transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
}

.floating-player-cover-wrap::before {
  content: '';
  position: absolute;
  inset: 14px 18px 8px;
  border-radius: 34px;
  background: radial-gradient(circle at center, rgba(136, 176, 201, 0.22), rgba(136, 176, 201, 0) 72%);
  opacity: 0;
  transform: scale(0.9);
  transition:
    opacity 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
  pointer-events: none;
}

.floating-player-cover-wrap.is-fullscreen-ready {
  cursor: pointer;
}

.floating-player-cover-wrap.is-fullscreen-ready:hover,
.floating-player-cover-wrap.is-fullscreen-ready:focus-visible {
  transform: translateY(-2px);
}

.floating-player-cover-wrap.is-fullscreen-ready:hover::before,
.floating-player-cover-wrap.is-fullscreen-ready:focus-visible::before {
  opacity: 1;
  transform: scale(1.04);
}

.floating-player-cover-wrap.is-fullscreen-ready:focus-visible {
  outline: none;
}

.floating-player-cover {
  width: 172px;
  height: 172px;
  border-radius: 28px;
  object-fit: cover;
  box-shadow: 0 14px 24px rgba(103, 132, 152, 0.12);
  transition:
    transform 0.3s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.3s cubic-bezier(0.22, 1, 0.36, 1),
    filter 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}

.floating-player-cover-wrap.is-fullscreen-ready:hover .floating-player-cover,
.floating-player-cover-wrap.is-fullscreen-ready:focus-visible .floating-player-cover {
  transform: scale(1.04);
  box-shadow: 0 22px 34px rgba(91, 122, 147, 0.2);
  filter: saturate(1.04) brightness(1.03);
}

.floating-player-cover.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(101, 129, 149, 0.44), rgba(183, 206, 220, 0.3));
}

.floating-player-cover-wrap.is-view-transition-source {
  view-transition-name: music-player-cover-art;
}

.floating-player-name {
  margin-top: 12px;
  text-align: center;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  padding: 0 10px;
  min-width: 0;
  overflow: hidden;
  line-height: 1.16;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  text-overflow: ellipsis;
  overflow-wrap: anywhere;
  text-wrap: balance;
  position: relative;
  z-index: 1;
}

.floating-player-subtitle {
  margin-top: 6px;
  text-align: center;
  font-size: 12px;
  color: rgba(95, 118, 138, 0.82);
  padding: 0 14px;
  min-width: 0;
  overflow: hidden;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  text-overflow: ellipsis;
  overflow-wrap: anywhere;
  position: relative;
  z-index: 1;
}

.floating-player-lyrics {
  min-height: 62px;
  margin-top: 8px;
  padding: 0 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  text-align: center;
  position: relative;
  z-index: 1;
}

.floating-player-lyrics.is-placeholder {
  min-height: 40px;
}

.floating-player-lyrics-current,
.floating-player-lyrics-next {
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  overflow-wrap: anywhere;
}

.floating-player-lyrics-current {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.38;
  color: rgba(58, 80, 98, 0.88);
  transition: color 0.22s ease, opacity 0.22s ease;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  white-space: normal;
  text-wrap: balance;
}

.floating-player-lyrics-next {
  font-size: 11px;
  line-height: 1.32;
  color: rgba(112, 131, 147, 0.62);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  white-space: normal;
}

.floating-player-lyrics.is-placeholder .floating-player-lyrics-current {
  font-size: 12px;
  font-weight: 500;
  color: rgba(112, 131, 147, 0.72);
}

.floating-player-hint {
  margin-top: 8px;
  font-size: 11px;
  text-align: center;
  color: var(--text-muted);
  padding: 0 14px;
  line-height: 1.4;
  position: relative;
  z-index: 1;
}

.floating-player-error {
  margin-top: 8px;
  font-size: 12px;
  text-align: center;
  color: #ffb0bc;
  padding: 0 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
  position: relative;
  z-index: 1;
}

.floating-player-times {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  gap: 10px;
  min-width: 0;
  font-size: 11px;
  color: rgba(95, 118, 138, 0.82);
  position: relative;
  z-index: 1;
}

.floating-player-times span {
  min-width: 0;
  white-space: nowrap;
}

.floating-player-range,
.floating-volume-range {
  width: 100%;
  accent-color: #5b7e9c;
  position: relative;
  z-index: 1;
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  border: none;
  outline: none;
  box-shadow: none;
  padding: 0;
  border-radius: 0;
}

.floating-player-range:disabled,
.floating-volume-range:disabled {
  opacity: 0.35;
}

.floating-player-range:focus,
.floating-volume-range:focus {
  outline: none;
  box-shadow: none;
}

.floating-player-range {
  margin-top: 8px;
}

.floating-player-range::-webkit-slider-runnable-track,
.floating-volume-range::-webkit-slider-runnable-track {
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    var(--slider-fill-color, rgba(255, 255, 255, 0.96)) 0%,
    var(--slider-fill-color, rgba(255, 255, 255, 0.96)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(186, 203, 218, 0.62)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(186, 203, 218, 0.62)) 100%
  );
}

.floating-player-range::-webkit-slider-thumb,
.floating-volume-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  margin-top: -7.5px;
  border-radius: 0;
  border: none;
  background: transparent;
  box-shadow: none;
}

.floating-player-range::-moz-range-track,
.floating-volume-range::-moz-range-track {
  height: 3px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    var(--slider-fill-color, rgba(255, 255, 255, 0.96)) 0%,
    var(--slider-fill-color, rgba(255, 255, 255, 0.96)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(186, 203, 218, 0.62)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(186, 203, 218, 0.62)) 100%
  );
}

.floating-player-range::-moz-range-thumb,
.floating-volume-range::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.floating-player-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 26px;
  margin-top: 20px;
  position: relative;
  z-index: 1;
}

.player-icon-btn {
  width: auto;
  height: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  background: transparent;
  color: rgba(90, 121, 146, 0.92);
  cursor: pointer;
  box-shadow: none;
  transition: transform var(--transition-fast), opacity var(--transition-fast), color var(--transition-fast);
}

.player-icon-btn:hover:not(:disabled) {
  transform: scale(1.05);
  background: transparent;
  box-shadow: none;
  color: rgba(79, 110, 136, 1);
}

.player-icon-btn:disabled {
  opacity: 0.24;
  cursor: not-allowed;
  box-shadow: none;
}

.player-icon-btn--primary {
  color: rgba(83, 115, 141, 0.98);
}

.player-icon-btn--transport .player-icon {
  width: 34px;
  height: 34px;
}

.player-icon-btn--primary .player-icon {
  width: 46px;
  height: 46px;
}

.player-icon-btn--volume {
  color: rgba(95, 122, 143, 0.9);
}

.player-icon-btn--volume .player-icon {
  width: 22px;
  height: 22px;
}

.player-icon {
  width: 20px;
  height: 20px;
  display: block;
}

.player-placeholder-icon {
  width: 62px;
  height: 62px;
  color: rgba(84, 119, 147, 0.52);
}

.floating-player-volume {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 24px;
  gap: 10px;
  align-items: center;
  margin-top: 18px;
  position: relative;
  z-index: 1;
  min-width: 0;
}

.floating-player-volume-indicator {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: rgba(95, 122, 143, 0.72);
}

.player-icon--volume-trailing {
  width: 20px;
  height: 20px;
}

.floating-player-audio {
  display: none;
}

</style>
