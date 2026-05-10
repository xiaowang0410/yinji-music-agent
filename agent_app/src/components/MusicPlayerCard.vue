<template>
  <div class="mini-player" :class="{ 'is-idle': !hasActiveTrack, 'is-playing': isAudioPlaying }">
    <div class="mini-player-main">
      <button
        type="button"
        class="mini-cover-button"
        :class="{ 'is-clickable': hasActiveTrack && !!onEnterFullscreen }"
        :disabled="!hasActiveTrack || !onEnterFullscreen"
        :aria-label="hasActiveTrack && onEnterFullscreen ? '进入全屏音乐模式' : '当前歌曲封面'"
        @click="handleEnterFullscreen"
      >
        <img
          v-if="playerDisplayTrack.cover_url"
          class="mini-cover"
          :src="playerDisplayTrack.cover_url"
          :alt="playerDisplayTrack.name"
        />
        <div v-else class="mini-cover mini-cover--placeholder" aria-hidden="true">
          <svg viewBox="0 0 24 24" class="mini-cover-icon">
            <path d="M15 5v9.2a3.2 3.2 0 1 1-1.5-2.74V7.1l6-1.4v7.5a3.2 3.2 0 1 1-1.5-2.74V4.1L15 5z" fill="currentColor" />
          </svg>
        </div>
      </button>

      <div class="mini-track-copy">
        <div class="mini-track-name">{{ playerDisplayTrack.name }}</div>
        <div class="mini-track-artist">{{ compactSubtitle }}</div>
      </div>

      <button
        type="button"
        class="mini-heart"
        :class="{ 'is-active': heartModeActive, 'is-loading': heartModeLoading }"
        :disabled="heartModeLoading || !onAccessoryClick"
        :title="accessoryTitle"
        :aria-label="accessoryTitle"
        @click="onAccessoryClick"
      >
        <svg viewBox="0 0 24 24" class="mini-heart-icon" aria-hidden="true">
          <path
            class="mini-heart-fill"
            d="M12 20.45 10.92 19.45C5.56 14.57 2.5 11.76 2.5 8.12 2.5 5.31 4.67 3.25 7.18 3.25c1.79 0 3.24.93 4.07 2.17.83-1.24 2.28-2.17 4.07-2.17 2.51 0 4.68 2.06 4.68 4.87 0 3.64-3.06 6.45-8.42 11.33L12 20.45Z"
          />
          <path
            d="M12 20.45 10.92 19.45C5.56 14.57 2.5 11.76 2.5 8.12 2.5 5.31 4.67 3.25 7.18 3.25c1.79 0 3.24.93 4.07 2.17.83-1.24 2.28-2.17 4.07-2.17 2.51 0 4.68 2.06 4.68 4.87 0 3.64-3.06 6.45-8.42 11.33L12 20.45Z"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </div>

    <div v-if="playerError" class="mini-error">{{ playerError }}</div>

    <input
      class="mini-progress"
      type="range"
      min="0"
      :max="playerDuration || 0"
      step="0.1"
      :value="Math.min(playerCurrentTime, playerDuration || 0)"
      :style="progressSliderStyle"
      :disabled="!hasActiveTrack"
      @input="onSeekTrack"
    />
    <div class="mini-times">
      <span>{{ elapsedTimeLabel }}</span>
      <span>{{ durationTimeLabel }}</span>
    </div>

    <div class="mini-controls">
      <button
        type="button"
        class="mini-control-btn"
        :disabled="!hasActiveTrack || !canPlayPrev"
        title="上一首"
        aria-label="上一首"
        @click="onPlayPrev"
      >
        <svg viewBox="0 0 28 28" class="mini-control-icon">
          <rect x="5" y="6.2" width="2.4" height="15.6" rx="1.2" fill="currentColor" />
          <path d="M20.8 6.8v14.4c0 .54-.6.87-1.07.57L9.4 15.08a1.28 1.28 0 0 1 0-2.16l10.33-6.7c.47-.3 1.07.03 1.07.57Z" fill="currentColor" />
        </svg>
      </button>

      <button
        type="button"
        class="mini-control-btn mini-control-btn--primary"
        :disabled="!hasActiveTrack"
        :title="isAudioPlaying ? '暂停' : '播放'"
        :aria-label="isAudioPlaying ? '暂停' : '播放'"
        @click="onToggleTrack"
      >
        <svg v-if="!isAudioPlaying" viewBox="0 0 28 28" class="mini-control-icon mini-control-icon--primary">
          <path d="M10 7.3v13.4c0 .66.72 1.06 1.28.7l10.32-6.7a.83.83 0 0 0 0-1.4L11.28 6.6c-.56-.36-1.28.04-1.28.7Z" fill="currentColor" />
        </svg>
        <svg v-else viewBox="0 0 28 28" class="mini-control-icon mini-control-icon--primary">
          <rect x="8.6" y="6.5" width="4.1" height="15" rx="1.45" fill="currentColor" />
          <rect x="15.3" y="6.5" width="4.1" height="15" rx="1.45" fill="currentColor" />
        </svg>
      </button>

      <button
        type="button"
        class="mini-control-btn"
        :disabled="!hasActiveTrack || !canPlayNext"
        title="下一首"
        aria-label="下一首"
        @click="onPlayNext"
      >
        <svg viewBox="0 0 28 28" class="mini-control-icon">
          <rect x="20.6" y="6.2" width="2.4" height="15.6" rx="1.2" fill="currentColor" />
          <path d="M7.2 6.8v14.4c0 .54.6.87 1.07.57l10.33-6.7a1.28 1.28 0 0 0 0-2.16L8.27 6.23c-.47-.3-1.07.03-1.07.57Z" fill="currentColor" />
        </svg>
      </button>
    </div>

    <audio
      :ref="audioRef"
      class="mini-player-audio"
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
import { computed } from 'vue'

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

const compactSubtitle = computed(() => {
  const artist = String(props.playerDisplayTrack?.artist || '').trim()
  if (props.hasActiveTrack) return artist || '未知歌手'
  return props.playerStatusText || artist || '等待播放'
})

const durationTimeLabel = computed(() => {
  if (!props.hasActiveTrack) return '00:00'
  const duration = Number(props.playerDuration)
  if (!Number.isFinite(duration) || duration <= 0) return String(props.remainingTimeLabel || '00:00').replace(/^-/, '')
  const total = Math.max(0, Math.floor(duration))
  const minutes = String(Math.floor(total / 60)).padStart(2, '0')
  const seconds = String(total % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
})
</script>

<style scoped>
.mini-player {
  position: relative;
  width: 100%;
  min-width: 0;
  padding: 11px;
  border-radius: 18px;
  border: 1px solid rgba(222, 229, 218, 0.86);
  background:
    radial-gradient(circle at 18% 8%, rgba(255, 255, 255, 0.96), transparent 36%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.96), rgba(249, 249, 248, 0.86));
  box-shadow:
    0 14px 30px rgba(24, 28, 24, 0.07),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
  color: #2f332b;
  overflow: hidden;
  backdrop-filter: blur(22px) saturate(132%);
}

.mini-player::before {
  content: '';
  position: absolute;
  inset: auto 24px -38px 24px;
  height: 86px;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(32, 36, 32, 0.06), transparent 68%);
  pointer-events: none;
}

.mini-player.is-idle {
  opacity: 0.94;
}

.mini-player-main {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr) 28px;
  align-items: start;
  gap: 10px;
}

.mini-cover-button {
  width: 54px;
  height: 54px;
  padding: 0;
  border: none;
  border-radius: 14px;
  background: transparent;
  overflow: hidden;
  box-shadow: 0 10px 20px rgba(24, 28, 24, 0.09);
  transition: transform 0.22s ease, box-shadow 0.22s ease, filter 0.22s ease;
}

.mini-cover-button.is-clickable {
  cursor: pointer;
}

.mini-cover-button.is-clickable:hover,
.mini-cover-button.is-clickable:focus-visible {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 18px 34px rgba(24, 28, 24, 0.13);
  filter: saturate(1.04) brightness(1.02);
  outline: none;
}

.mini-cover-button:disabled {
  cursor: default;
}

.mini-cover {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.mini-cover--placeholder {
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at 28% 20%, rgba(255, 255, 255, 0.9), transparent 38%),
    linear-gradient(135deg, #f2f2f1, #d6d7d5);
  color: rgba(255, 255, 255, 0.86);
}

.mini-cover-icon {
  width: 34px;
  height: 34px;
}

.mini-track-copy {
  min-width: 0;
  padding-top: 3px;
}

.mini-track-name {
  font-size: 14px;
  line-height: 1.18;
  font-weight: 860;
  letter-spacing: -0.04em;
  color: #292d25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mini-track-artist {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.35;
  font-weight: 650;
  color: rgba(86, 89, 75, 0.62);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mini-heart {
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: rgba(72, 76, 72, 0.82);
  cursor: pointer;
  transition: transform 0.2s ease, color 0.2s ease, background 0.2s ease;
}

.mini-heart:hover:not(:disabled),
.mini-heart:focus-visible {
  transform: scale(1.06);
  background: rgba(32, 36, 32, 0.06);
  color: #2f332f;
  outline: none;
}

.mini-heart:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.mini-heart.is-active {
  color: #2f332f;
  background: rgba(32, 36, 32, 0.08);
}

.mini-heart.is-active .mini-heart-fill {
  opacity: 0.2;
}

.mini-heart.is-loading {
  animation: mini-heart-pulse 1.1s ease-in-out infinite;
}

.mini-heart-icon {
  width: 19px;
  height: 19px;
  display: block;
}

.mini-heart-fill {
  fill: currentColor;
  opacity: 0;
}

.mini-error {
  position: relative;
  z-index: 1;
  margin-top: 9px;
  padding: 7px 9px;
  border-radius: 12px;
  background: rgba(183, 75, 65, 0.08);
  color: #9b463d;
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.mini-progress {
  position: relative;
  z-index: 1;
  width: 100%;
  margin-top: 10px;
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  border: none;
  outline: none;
  box-shadow: none;
  padding: 0;
}

.mini-progress:disabled {
  opacity: 0.45;
}

.mini-progress::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    var(--slider-fill-color, #303330) 0%,
    var(--slider-fill-color, #303330) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(32, 36, 32, 0.12)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(32, 36, 32, 0.12)) 100%
  );
}

.mini-progress::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 13px;
  height: 13px;
  margin-top: -4.5px;
  border-radius: 999px;
  border: 3px solid #ffffff;
  background: #303330;
  box-shadow: 0 4px 12px rgba(24, 28, 24, 0.18);
}

.mini-progress::-moz-range-track {
  height: 4px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    var(--slider-fill-color, #303330) 0%,
    var(--slider-fill-color, #303330) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(32, 36, 32, 0.12)) var(--slider-fill, 0%),
    var(--slider-rest-color, rgba(32, 36, 32, 0.12)) 100%
  );
}

.mini-progress::-moz-range-thumb {
  width: 13px;
  height: 13px;
  border-radius: 999px;
  border: 3px solid #ffffff;
  background: #303330;
  box-shadow: 0 4px 12px rgba(24, 28, 24, 0.18);
}

.mini-times {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 6px;
  font-size: 11px;
  line-height: 1;
  color: rgba(89, 94, 78, 0.58);
  font-variant-numeric: tabular-nums;
}

.mini-controls {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
  margin-top: 10px;
}

.mini-control-btn {
  width: 30px;
  height: 30px;
  padding: 0;
  border: none;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: rgba(44, 48, 43, 0.9);
  cursor: pointer;
  transition: transform 0.2s ease, color 0.2s ease, opacity 0.2s ease, box-shadow 0.2s ease;
}

.mini-control-btn:hover:not(:disabled),
.mini-control-btn:focus-visible {
  transform: translateY(-1px) scale(1.04);
  color: #2f332f;
  outline: none;
}

.mini-control-btn:disabled {
  opacity: 0.24;
  cursor: not-allowed;
}

.mini-control-btn--primary {
  width: 42px;
  height: 42px;
  color: #ffffff;
  background:
    radial-gradient(circle at 34% 24%, rgba(255, 255, 255, 0.36), transparent 38%),
    linear-gradient(135deg, #8a8f8a, #3b403b);
  box-shadow: 0 16px 30px rgba(24, 28, 24, 0.16);
}

.mini-control-btn--primary:hover:not(:disabled),
.mini-control-btn--primary:focus-visible {
  color: #ffffff;
  box-shadow: 0 20px 36px rgba(24, 28, 24, 0.2);
}

.mini-control-icon {
  width: 22px;
  height: 22px;
  display: block;
}

.mini-control-icon--primary {
  width: 25px;
  height: 25px;
}

.mini-player-audio {
  display: none;
}

@keyframes mini-heart-pulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.08);
  }
}
</style>
