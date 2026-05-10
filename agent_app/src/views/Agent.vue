<template>
  <div class="agent-layout">
    <aside class="agent-rail" aria-label="AI 音乐导航">
      <div class="rail-user-card rail-user-card--top">
        <div class="rail-user-avatar">
          <img
            v-if="userAvatarUrl"
            class="rail-user-avatar-image"
            :src="userAvatarUrl"
            :alt="userDisplayName"
            loading="lazy"
            @error="userAvatarFailed = true"
          />
          <span v-else>{{ userInitial }}</span>
        </div>
        <div class="rail-user-copy">
          <div class="rail-user-name">{{ userDisplayName }}</div>
          <div class="rail-user-meta">{{ userProfileMeta }}</div>
        </div>
      </div>

      <nav class="rail-nav" aria-label="主要功能">
        <div
          v-for="item in primarySidebarItems"
          :key="item.key"
          class="rail-nav-row"
          :class="{ active: activeWorkspace === item.key, 'has-action': item.key === 'chat' }"
        >
          <button
            type="button"
            class="rail-nav-item"
            @click="selectWorkspace(item.key)"
          >
            <span class="rail-nav-icon" :class="`is-${item.icon}`" aria-hidden="true">
              <svg class="rail-nav-svg" viewBox="0 0 24 24" focusable="false">
                <path
                  v-for="path in sidebarIconPaths[item.icon]"
                  :key="path.d"
                  :d="path.d"
                  :fill="path.fill || 'none'"
                  :stroke="path.stroke || 'currentColor'"
                  :stroke-width="path.strokeWidth || 1.9"
                  :stroke-linecap="path.strokeLinecap || 'round'"
                  :stroke-linejoin="path.strokeLinejoin || 'round'"
                />
              </svg>
            </span>
            <span class="rail-nav-label">{{ item.label }}</span>
          </button>
          <button
            v-if="item.key === 'chat' && activeWorkspace === 'chat'"
            class="rail-compose-btn"
            type="button"
            title="新建对话"
            aria-label="新建对话"
            :disabled="sidebarLoading || loading"
            @click.stop="handleNewConversationClick"
          >
            <svg class="rail-compose-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M12 20h8" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" />
              <path d="M15.8 4.9a2.12 2.12 0 0 1 3 3L8.7 18l-4.1 1.1L5.7 15 15.8 4.9Z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
        </div>
      </nav>

      <section class="rail-conversations" aria-label="对话列表">
        <div class="rail-section-head">
          <span>最近对话</span>
          <span class="rail-section-count">{{ filteredConversations.length }}</span>
        </div>

        <div class="rail-search">
          <input v-model="query" class="rail-search-input" placeholder="搜索对话" />
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
                <button
                  class="item-action-btn"
                  title="重命名"
                  aria-label="重命名对话"
                  @click.stop="startRenameConversation(conversation)"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true" class="action-icon">
                    <path d="M12 20h9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                    <path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </button>
                <button
                  class="item-action-btn danger"
                  title="删除对话"
                  aria-label="删除对话"
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
          </div>
        </div>

        <div v-else class="rail-empty">
          <div class="rail-empty-title">还没有对话</div>
          <div class="rail-empty-sub">发送一条消息，或者手动新建一个空白会话。</div>
        </div>
      </section>

      <div class="rail-spacer" aria-hidden="true"></div>

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

    <main v-if="activeWorkspace === 'chat'" class="chat-shell">
      <header class="chat-topbar">
        <div>
          <div class="chat-eyebrow">AI MUSIC CONVERSATION</div>
          <div class="chat-topbar-title">{{ activeConversationTitle || DEFAULT_TITLE }}</div>
        </div>
        <div v-if="memorySummary" class="chat-topbar-sub" :title="memorySummary">记忆：{{ memorySummary }}</div>
      </header>

      <section ref="messagesList" class="chat-body">
        <div v-if="messages.length === 0" class="welcome-card">
          <div class="welcome-kicker">今晚想听点什么？</div>
          <div class="welcome-title">你好，我是小听</div>
          <div class="welcome-sub">告诉我你的心情、场景或想听的歌，我会尽量给你一组可直接播放的音乐建议。</div>
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

          <div v-if="observabilityVisible" class="agent-observability">
            <div class="observability-head">
              <span>Agent Trace</span>
              <span v-if="runMetrics.elapsed_ms" class="observability-time">{{ formatElapsed(runMetrics.elapsed_ms) }}</span>
            </div>
            <div v-if="runMetrics.provider || modelSummary" class="observability-meta">
              <span v-if="runMetrics.provider">{{ runMetrics.provider }}</span>
              <span v-if="modelSummary">{{ modelSummary }}</span>
            </div>
            <div v-if="agentThoughts.length > 0" class="thought-list">
              <div v-for="item in agentThoughts" :key="item.id" class="thought-item" :class="`is-${item.kind || 'thought'}`">
                <span class="thought-kind">{{ formatThoughtKind(item.kind) }}</span>
                <span class="thought-text">{{ item.text }}</span>
              </div>
            </div>
            <div v-if="runMetrics.reflection?.summary" class="reflection-box">
              <span class="reflection-label">反思</span>
              <span>{{ runMetrics.reflection.summary }}</span>
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
          :user-profile="userProfile"
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
          :user-profile="userProfile"
        />
      </section>

      <div v-if="requestError" class="chat-error-banner">{{ requestError }}</div>

      <footer class="chat-input">
        <form class="input-form" @submit.prevent="submitChat">
          <input
            v-model="inputMessage"
            type="text"
            class="message-input"
            placeholder="输入你想听的歌、心情或问题"
            :disabled="loading"
            @compositionstart="isComposing = true"
            @compositionend="isComposing = false"
            @keydown.enter.exact.prevent="handleEnter"
          />
          <button class="send-btn" type="submit" :disabled="!inputMessage.trim() || loading">发送</button>
        </form>
      </footer>
    </main>

    <main v-else class="workspace-shell">
      <section class="workspace-hero">
        <div class="workspace-eyebrow">{{ activeWorkspaceMeta.eyebrow }}</div>
        <h1>{{ activeWorkspaceMeta.label }}</h1>
        <p>{{ activeWorkspaceMeta.description }}</p>
      </section>
      <section class="workspace-empty-card">
        <div class="workspace-empty-mark" :class="`is-${activeWorkspaceMeta.icon}`" aria-hidden="true">
          <svg class="workspace-empty-icon" viewBox="0 0 24 24" focusable="false">
            <path
              v-for="path in sidebarIconPaths[activeWorkspaceMeta.icon]"
              :key="path.d"
              :d="path.d"
              :fill="path.fill || 'none'"
              :stroke="path.stroke || 'currentColor'"
              :stroke-width="path.strokeWidth || 1.9"
              :stroke-linecap="path.strokeLinecap || 'round'"
              :stroke-linejoin="path.strokeLinejoin || 'round'"
            />
          </svg>
        </div>
        <div class="workspace-empty-copy">
          <h2>{{ activeWorkspaceMeta.emptyTitle }}</h2>
          <p>{{ activeWorkspaceMeta.emptyText }}</p>
        </div>
      </section>
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
const sidebarIconPaths = Object.freeze({
  chat: [
    { d: 'M6.8 6.25h10.4a3.05 3.05 0 0 1 3.05 3.05v4.25a3.05 3.05 0 0 1-3.05 3.05h-4.45l-4.1 3.15v-3.15H6.8a3.05 3.05 0 0 1-3.05-3.05V9.3A3.05 3.05 0 0 1 6.8 6.25Z' },
    { d: 'M8.15 10.2h7.7' },
    { d: 'M8.15 13.15h4.65' },
  ],
  discover: [
    { d: 'M12 20.25a8.25 8.25 0 1 0 0-16.5 8.25 8.25 0 0 0 0 16.5Z' },
    { d: 'm9.35 14.65 1.28-4.02 4.02-1.28-1.28 4.02-4.02 1.28Z' },
    { d: 'M12 12h.01', strokeWidth: 2.7 },
  ],
  songs: [
    { d: 'M14.75 5.25v9.95a3 3 0 1 1-1.85-2.76V7.15l4.85-1.08' },
    { d: 'M14.75 7.15 17.75 6.48' },
    { d: 'M6.25 6.55 7.1 4.85l.85 1.7 1.75.25-1.27 1.24.3 1.74L7.1 8.96l-1.56.82.3-1.74L4.55 6.8l1.7-.25Z' },
  ],
  playlists: [
    { d: 'M5 7.25h8.7' },
    { d: 'M5 11.6h8.7' },
    { d: 'M5 15.95h6.1' },
    { d: 'M17.2 7.75v8.55a2.25 2.25 0 1 1-1.45-2.1V8.65l3.25-.75' },
  ],
  favorite: [
    { d: 'M12 19.7 10.9 18.7C6.2 14.45 3.55 12 3.55 8.9a3.82 3.82 0 0 1 3.92-3.9A4.5 4.5 0 0 1 12 7.55 4.5 4.5 0 0 1 16.53 5a3.82 3.82 0 0 1 3.92 3.9c0 3.1-2.65 5.55-7.35 9.8L12 19.7Z' },
  ],
  history: [
    { d: 'M4.15 12.15a7.85 7.85 0 1 0 2.3-5.55' },
    { d: 'M4.15 5.05v4.25h4.25' },
    { d: 'M12 8.15v4.25l2.85 1.75' },
  ],
  memory: [
    { d: 'M8.1 4.4h7.8a2.75 2.75 0 0 1 2.75 2.75v9.7a2.75 2.75 0 0 1-2.75 2.75H8.1a2.75 2.75 0 0 1-2.75-2.75v-9.7A2.75 2.75 0 0 1 8.1 4.4Z' },
    { d: 'M9 8.55h6' },
    { d: 'M9 12h6' },
    { d: 'M9 15.45h3.35' },
    { d: 'M7.45 4.4V2.85' },
    { d: 'M16.55 4.4V2.85' },
  ],
})
const SIDEBAR_ITEMS = Object.freeze([
  {
    key: 'chat',
    label: '对话',
    icon: 'chat',
    eyebrow: 'Conversation',
    description: '和 AI 音乐助手沟通，搜索、推荐和播放都从这里开始。',
    emptyTitle: '开始一段音乐对话',
    emptyText: '这里承载聊天主流程，右侧会展示完整对话。',
  },
  {
    key: 'discover',
    label: '探索发现',
    icon: 'discover',
    eyebrow: 'Explore',
    description: '为新歌、热门内容和风格发现预留的入口。',
    emptyTitle: '探索发现还在搭骨架',
    emptyText: '下一步可以接入热搜、排行榜、歌手和主题歌单工具。',
  },
  {
    key: 'recommendedSongs',
    label: '推荐歌曲',
    icon: 'songs',
    eyebrow: 'Songs',
    description: '集中展示每日推荐、场景推荐和 Agent 生成的歌曲列表。',
    emptyTitle: '推荐歌曲区域已预留',
    emptyText: '后续可以把每日推荐、心情推荐和指定歌曲搜索结果都汇聚到这里。',
  },
  {
    key: 'recommendedPlaylists',
    label: '推荐歌单',
    icon: 'playlists',
    eyebrow: 'Playlists',
    description: '承载推荐歌单、精品歌单和场景歌单。',
    emptyTitle: '推荐歌单区域已预留',
    emptyText: '这里后续会接歌单搜索、歌单详情和一键播放能力。',
  },
  {
    key: 'favorites',
    label: '收藏音乐',
    icon: 'favorite',
    eyebrow: 'Library',
    description: '展示用户收藏、点赞和沉淀下来的音乐资产。',
    emptyTitle: '收藏音乐区域已预留',
    emptyText: '后续可以接点赞歌曲、收藏歌单、收藏歌手等工具。',
  },
  {
    key: 'history',
    label: '听歌历史',
    icon: 'history',
    eyebrow: 'History',
    description: '根据播放历史理解用户最近的音乐轨迹。',
    emptyTitle: '听歌历史区域已预留',
    emptyText: '后续可以接播放记录工具，生成最近常听和口味变化。',
  },
  {
    key: 'memory',
    label: 'AI 记忆',
    icon: 'memory',
    eyebrow: 'Memory',
    description: '展示 AI 对用户音乐偏好、场景习惯和长期上下文的记忆。',
    emptyTitle: 'AI 记忆区域已预留',
    emptyText: '后续这里会成为可查看、可编辑、可删除的音乐记忆中心。',
  },
])
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
  metrics: null,
})
const runMetrics = ref({
  elapsed_ms: 0,
  stages: [],
  reflection: null,
  provider: '',
  models: {},
})
const agentThoughts = ref([])
const assistantStreaming = ref(false)
const currentAssistantMessageId = ref(null)
const pendingAutoPlayRequest = ref(null)
const pendingClientAction = ref(null)
const activeWorkspace = ref('chat')
const userProfile = ref(null)
const userAvatarFailed = ref(false)

const {
  activeLyricLine,
  bindAudioPlayer,
  canPlayNext,
  canPlayPrev,
  currentLyricIndex,
  currentLyrics,
  currentQueue,
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
  pauseCurrentTrack,
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
  resumeCurrentTrack,
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

const primarySidebarItems = computed(() => SIDEBAR_ITEMS)
const activeWorkspaceMeta = computed(() => {
  return SIDEBAR_ITEMS.find((item) => item.key === activeWorkspace.value) || SIDEBAR_ITEMS[0]
})
const userAvatarUrl = computed(() => {
  if (userAvatarFailed.value) return ''
  return String(userProfile.value?.avatar_url || userProfile.value?.avatarUrl || '').trim()
})
const userDisplayName = computed(() => {
  return String(userProfile.value?.nickname || userProfile.value?.name || '').trim() || '音乐用户'
})
const userInitial = computed(() => {
  const name = userDisplayName.value
  return name ? name.slice(0, 1).toUpperCase() : '我'
})
const userProfileMeta = computed(() => {
  const signature = String(userProfile.value?.signature || '').trim()
  if (signature) return signature
  const level = Number(userProfile.value?.level)
  if (Number.isFinite(level) && level > 0) return `Lv.${level} 网易云音乐`
  return '网易云音乐'
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

const observabilityVisible = computed(() => {
  return (
    agentThoughts.value.length > 0 ||
    !!runMetrics.value.provider ||
    !!runMetrics.value.elapsed_ms ||
    !!runMetrics.value.reflection?.summary
  )
})

const modelSummary = computed(() => {
  const models = runMetrics.value.models || {}
  const values = [models.intent, models.tool, models.polish]
    .filter(Boolean)
    .map((item) => String(item))
  return [...new Set(values)].join(' / ')
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

function formatElapsed(ms) {
  const value = Number(ms) || 0
  if (value <= 0) return ''
  if (value < 1000) return `${Math.round(value)}ms`
  return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)}s`
}

function formatThoughtKind(kind) {
  const normalized = String(kind || '').trim().toLowerCase()
  if (normalized === 'reflection') return '反思'
  if (normalized === 'plan') return '思考'
  return '观察'
}

function selectWorkspace(workspaceKey) {
  if (!SIDEBAR_ITEMS.some((item) => item.key === workspaceKey)) return
  activeWorkspace.value = workspaceKey
}

async function handleNewConversationClick() {
  activeWorkspace.value = 'chat'
  await createNewConversation()
}

async function loadUserProfile() {
  try {
    const response = await agentApi.getUserProfile()
    const profile = response?.profile && typeof response.profile === 'object' ? response.profile : null
    if (profile) {
      userProfile.value = profile
      userAvatarFailed.value = false
    }
  } catch (error) {
    console.warn('load user profile error:', error)
  }
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

function appendLocalAssistantMessage(content, payload = null) {
  const normalized = normalizeMessage({
    id: `local_assistant_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    role: 'assistant',
    content,
    payload,
    timestamp: new Date().toISOString(),
  })
  if (!normalized) return
  messages.value.push(normalized)
  messages.value = [...messages.value]
  scrollToBottom()
}

function mergeAssistantActionMessage(content, messageId = currentAssistantMessageId.value) {
  const text = sanitizeInternalFailureText(
    String(content || '').trim(),
    '后端服务刚刚出错了，请稍后再试。',
  )
  if (!text) return

  const target = ensureAssistantMessage(messageId)
  if (!target) {
    appendLocalAssistantMessage(text)
    return
  }

  const current = String(target.content || '').trim()
  if (!current) {
    target.content = text
  } else if (!current.includes(text)) {
    target.content = `${current}\n\n${text}`
  }
  messages.value = [...messages.value]
  scrollToBottom()
}

function normalizeCommandText(value) {
  return String(value || '').replace(/\s+/g, '').toLowerCase()
}

function currentTrackSummary() {
  if (!hasActiveTrack.value) return '现在还没有正在播放的歌曲。'
  const track = playerDisplayTrack.value || {}
  const parts = [
    `当前播放：${track.name || '未知歌曲'}`,
    track.artist ? `歌手：${track.artist}` : '',
    track.album ? `专辑：${track.album}` : '',
    `状态：${isAudioPlaying.value ? '正在播放' : '已暂停'}`,
    playerDuration.value > 0 ? `进度：${elapsedTimeLabel.value} / ${musicFullscreenDurationLabel.value}` : '',
  ].filter(Boolean)
  return parts.join('\n')
}

function buildPlayerStateForAgent() {
  const track = hasActiveTrack.value ? (playerDisplayTrack.value || {}) : null
  const queue = Array.isArray(currentQueue.value)
    ? currentQueue.value.slice(0, 20).map((item) => ({
        id: String(item?.id || ''),
        name: String(item?.name || ''),
        artist: String(item?.artist || ''),
      }))
    : []
  return {
    player: {
      has_active_track: !!track,
      is_playing: !!isAudioPlaying.value,
      status_text: playerStatusText.value,
      current_time_seconds: Number(playerCurrentTime.value) || 0,
      duration_seconds: Number(playerDuration.value) || 0,
      current_track: track
        ? {
            id: String(track.id || ''),
            name: String(track.name || ''),
            artist: String(track.artist || ''),
            album: String(track.album || ''),
          }
        : null,
      queue_size: Array.isArray(currentQueue.value) ? currentQueue.value.length : 0,
      queue,
    },
    capabilities: [
      'answer_current_track',
      'pause',
      'resume',
      'next_track',
      'previous_track',
      'autoplay_song_list',
      'autoplay_playlist_tracks',
    ],
  }
}

function shouldAutoPlayFromRequest(text) {
  const normalized = normalizeCommandText(text)
  if (!/(播放|放一|来点|来首|听|开始放)/.test(normalized)) return false
  return /(点赞|喜欢|收藏|推荐|歌单|忧郁|郁闷|难过|伤感|开心|快乐|放松|安静|治愈|热血|睡前|工作|学习|运动|通勤)/.test(normalized)
}

function pickPlaylistForAutoPlay(payload, requestText = '') {
  const items = Array.isArray(payload?.items) ? payload.items : []
  if (!items.length) return null

  const normalizedRequest = normalizeCommandText(requestText)
  const rankMatch = normalizedRequest.match(/第([一二三四五六七八九十\d]+)个?歌单/)
  if (rankMatch) {
    const digits = {
      一: 1,
      二: 2,
      三: 3,
      四: 4,
      五: 5,
      六: 6,
      七: 7,
      八: 8,
      九: 9,
      十: 10,
    }
    const rawRank = rankMatch[1]
    const rank = /^\d+$/.test(rawRank) ? Number(rawRank) : digits[rawRank]
    if (Number.isFinite(rank) && rank > 0 && items[rank - 1]) {
      return items[rank - 1]
    }
  }

  const named = items.find((item) => {
    const name = normalizeCommandText(item?.name)
    return name && normalizedRequest.includes(name)
  })
  return named || items[0]
}

async function playPlaylistFromPayload(payload, actionPayload = {}) {
  const items = Array.isArray(payload?.items) ? payload.items : []
  const request = pendingAutoPlayRequest.value
  const rank = Number(actionPayload?.rank)
  const selectedPlaylist = Number.isFinite(rank) && rank > 0 && items[rank - 1]
    ? items[rank - 1]
    : pickPlaylistForAutoPlay(payload, request?.text || actionPayload?.playlist_name || '')
  const playlistId = String(selectedPlaylist?.id || '').trim()
  if (!playlistId) return false

  try {
    const response = await agentApi.getPlaylistTracks(playlistId, { limit: 100, offset: 0 })
    const songs = Array.isArray(response?.songs) ? response.songs : []
    if (!songs.length) {
      mergeAssistantActionMessage('我找到了歌单，但这个歌单暂时没有可播放的歌曲。')
      return false
    }

    pendingAutoPlayRequest.value = null
    heartModeActive.value = false
    clearPlayerError()
    await playQueue(songs, 0)
    return true
  } catch (error) {
    console.error('auto play playlist error:', error)
    const message = formatAxiosError(error)
    mergeAssistantActionMessage(message || '我找到了歌单，但暂时没能自动加载里面的歌曲。你可以点开歌单再试一次。')
    return false
  }
}

function maybeAutoPlayPayload(payload) {
  const request = pendingAutoPlayRequest.value
  const clientAction = pendingClientAction.value
  if (!request && !clientAction) return
  if (!payload || typeof payload !== 'object') return
  const items = Array.isArray(payload.items) ? payload.items : []
  if (!items.length) return

  if (payload.kind === 'song_list') {
    pendingAutoPlayRequest.value = null
    pendingClientAction.value = null
    heartModeActive.value = false
    clearPlayerError()
    const rank = Number(clientAction?.payload?.rank)
    const startIndex = Number.isFinite(rank) && rank > 0 ? rank - 1 : 0
    void playQueue(items, startIndex)
    return
  }

  if (payload.kind === 'playlist_list') {
    void playPlaylistFromPayload(payload, clientAction?.payload || {})
  }
}

async function handleClientAction(actionPayload) {
  const actionType = String(actionPayload?.type || '').trim()
  const legacyAction = typeof actionPayload?.action === 'string'
    ? actionPayload.action
    : actionPayload?.action?.action
  const actionFromType = actionType.replace(/^player\./, '').replace(/\./g, '_')
  const action = String(legacyAction || actionFromType || '').trim()
  const payload = actionPayload?.payload && typeof actionPayload.payload === 'object'
    ? actionPayload.payload
    : {}
  const message = String(actionPayload?.message || '').trim()

  if (!action) return

  if (action === 'answer_current_track') {
    mergeAssistantActionMessage(message || currentTrackSummary())
    return
  }

  if (action === 'pause') {
    const ok = pauseCurrentTrack()
    if (!ok) mergeAssistantActionMessage('现在还没有正在播放的歌曲。')
    return
  }

  if (action === 'resume') {
    const ok = await resumeCurrentTrack()
    if (!ok) mergeAssistantActionMessage('现在还没有可继续播放的歌曲。')
    return
  }

  if (action === 'next_track') {
    if (canPlayNext.value) {
      playNextTrack()
    } else {
      mergeAssistantActionMessage('当前队列里没有下一首。')
    }
    return
  }

  if (action === 'previous_track') {
    if (canPlayPrev.value) {
      playPrevTrack()
    } else {
      mergeAssistantActionMessage('当前队列里没有上一首。')
    }
    return
  }

  if (action === 'play_song_list' || action === 'play_playlist_tracks') {
    pendingClientAction.value = { action, payload, message, createdAt: Date.now() }
  }
}

function resetProgress() {
  progress.value = {
    current_stage: null,
    current_stage_label: '',
    current_stage_description: '',
    steps: [],
    tools: [],
    metrics: null,
  }
  runMetrics.value = {
    elapsed_ms: 0,
    stages: [],
    reflection: null,
    provider: '',
    models: {},
  }
  agentThoughts.value = []
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
    maybeAutoPlayPayload(normalizePayload(data.payload))
    return
  }
  if (event === 'client_action' && data.payload) {
    requestError.value = ''
    if (data.message_id) currentAssistantMessageId.value = data.message_id
    void handleClientAction(data.payload)
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
  if (event === 'agent_run') {
    runMetrics.value = {
      ...runMetrics.value,
      ...data,
      models: data.models || runMetrics.value.models || {},
    }
    return
  }
  if (event === 'metrics' && data.metrics) {
    runMetrics.value = {
      ...runMetrics.value,
      ...data.metrics,
      models: data.metrics.models || runMetrics.value.models || {},
    }
    return
  }
  if (event === 'thought' && data.text) {
    agentThoughts.value = [
      ...agentThoughts.value.slice(-5),
      {
        id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
        kind: data.kind || 'thought',
        text: data.text,
        elapsed_ms: data.elapsed_ms || 0,
      },
    ]
    return
  }
  if (event === 'reflection') {
    runMetrics.value = {
      ...runMetrics.value,
      reflection: {
        confidence: data.confidence || '',
        summary: data.summary || '',
        need_retry: !!data.need_retry,
        next_action: data.next_action || '',
      },
    }
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
      metrics: data.metrics || null,
    }
    if (data.metrics) {
      runMetrics.value = {
        ...runMetrics.value,
        ...data.metrics,
        models: data.metrics.models || runMetrics.value.models || {},
      }
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

  pendingAutoPlayRequest.value = shouldAutoPlayFromRequest(text)
    ? { text, createdAt: Date.now() }
    : null
  pendingClientAction.value = null
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
      clientContext: buildPlayerStateForAgent(),
    })

    if (res.conversation) upsertConversation(res.conversation)
    if (res.memory_summary) memorySummary.value = res.memory_summary
    if (res.message) upsertMessage(res.message)
    if (res.metrics) {
      runMetrics.value = {
        ...runMetrics.value,
        ...res.metrics,
        models: res.metrics.models || runMetrics.value.models || {},
      }
    }
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
    void loadUserProfile()
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
  --page-ink: #252722;
  --page-muted: #8a8d82;
  --page-soft: #f8faf7;
  --page-card: rgba(255, 255, 255, 0.86);
  --page-line: rgba(35, 39, 35, 0.1);
  --page-accent: #2f332f;
  --page-accent-strong: #202420;
  --page-honey: #f2f3f1;
  --page-shadow: 0 22px 60px rgba(24, 28, 24, 0.08);
  --page-shadow-soft: 0 12px 30px rgba(24, 28, 24, 0.06);
  --glass-shadow: var(--page-shadow);
  --glass-shadow-soft: var(--page-shadow-soft);
  --text-primary: var(--page-ink);
  --text-secondary: var(--page-muted);
  --text-muted: rgba(128, 134, 121, 0.78);
  --active-color: var(--page-accent-strong);
  width: 100%;
  min-width: 100%;
  max-width: 100%;
  height: 100%;
  min-height: 100%;
  max-height: 100%;
  display: grid;
  grid-template-columns: clamp(248px, 15.5vw, 282px) minmax(0, 1fr);
  gap: 0;
  padding: 0;
  background:
    radial-gradient(circle at 16% 12%, rgba(245, 246, 244, 0.62), transparent 27%),
    radial-gradient(circle at 88% 6%, rgba(250, 250, 249, 0.95), transparent 34%),
    linear-gradient(135deg, #ffffff 0%, #fafafa 48%, #ffffff 100%);
  min-width: 0;
  position: relative;
  -webkit-user-select: none;
  user-select: none;
  overflow: hidden;
  border-radius: 0;
  box-shadow: none;
}

.agent-layout::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.28;
  background-image:
    radial-gradient(rgba(71, 88, 67, 0.08) 0.7px, transparent 0.8px),
    linear-gradient(115deg, transparent 0 48%, rgba(255, 255, 255, 0.34) 48% 52%, transparent 52% 100%);
  background-size: 18px 18px, 100% 100%;
  mix-blend-mode: multiply;
}

.agent-rail,
.chat-shell,
.workspace-shell {
  position: relative;
  z-index: 1;
}

.agent-rail {
  height: 100%;
  display: flex;
  flex-direction: column;
  border: none;
  border-right: 1px solid rgba(35, 39, 35, 0.09);
  background:
    radial-gradient(circle at 18% -8%, rgba(255, 255, 255, 1), transparent 34%),
    radial-gradient(circle at 92% 40%, rgba(246, 247, 245, 0.5), transparent 32%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(249, 249, 248, 0.96));
  backdrop-filter: blur(28px) saturate(136%);
  box-shadow:
    inset -12px 0 34px rgba(24, 28, 24, 0.024),
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    inset 0 -1px 0 rgba(255, 255, 255, 0.42);
  border-radius: 0;
  overflow: hidden;
  min-width: 0;
  min-height: 0;
  padding: 14px 14px 12px;
}

.agent-rail::before,
.chat-shell::before,
.workspace-shell::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 170px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.58), rgba(255, 255, 255, 0));
  pointer-events: none;
}

.rail-nav {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 4px;
  margin-top: 10px;
}

.rail-nav-row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
}

.rail-nav-row.has-action {
  grid-template-columns: minmax(0, 1fr);
}

.rail-nav-item {
  appearance: none;
  width: 100%;
  min-height: 36px;
  border: 1px solid transparent;
  border-radius: 13px;
  background: transparent;
  color: rgba(39, 43, 36, 0.82);
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 9px;
  text-align: left;
  cursor: pointer;
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast),
    box-shadow var(--transition-fast),
    color var(--transition-fast),
  transform var(--transition-fast);
}

.rail-nav-row.has-action .rail-nav-item {
  padding-right: 42px;
}

.rail-nav-item:hover,
.rail-nav-item:focus-visible,
.rail-nav-row.active .rail-nav-item {
  background: rgba(255, 255, 255, 0.84);
  border-color: rgba(222, 228, 219, 0.9);
  box-shadow: 0 10px 22px rgba(46, 55, 42, 0.045);
  outline: none;
}

.rail-nav-row.active .rail-nav-item,
.rail-nav-item.active {
  color: var(--page-accent-strong);
  background:
    radial-gradient(circle at 10% 16%, rgba(255, 255, 255, 0.96), transparent 38%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(239, 244, 236, 0.82));
  border-color: rgba(218, 226, 212, 0.9);
  box-shadow:
    0 10px 24px rgba(46, 55, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.84);
}

.rail-nav-row.active .rail-nav-icon,
.rail-nav-item.active .rail-nav-icon {
  background:
    radial-gradient(circle at 30% 18%, rgba(255, 255, 255, 0.84), transparent 34%),
    rgba(32, 36, 32, 0.08);
  color: var(--page-accent-strong);
  box-shadow:
    inset 0 0 0 1px rgba(32, 36, 32, 0.1),
    0 8px 18px rgba(24, 28, 24, 0.08);
}

.rail-nav-label {
  min-width: 0;
  font-size: 13px;
  font-weight: 820;
  letter-spacing: 0.01em;
}

.rail-nav-icon {
  position: relative;
  flex: 0 0 23px;
  width: 23px;
  height: 23px;
  border-radius: 8px;
  color: rgba(74, 79, 74, 0.72);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: inset 0 0 0 1px rgba(34, 38, 34, 0.08);
  display: inline-grid;
  place-items: center;
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-fast);
}

.rail-nav-item:hover .rail-nav-icon,
.rail-nav-item:focus-visible .rail-nav-icon {
  color: var(--page-accent-strong);
  background: rgba(255, 255, 255, 0.92);
  transform: translateY(-1px);
}

.rail-nav-svg {
  width: 17px;
  height: 17px;
  display: block;
  overflow: visible;
}

.rail-nav-svg path {
  vector-effect: non-scaling-stroke;
}

.rail-compose-btn {
  appearance: none;
  position: absolute;
  right: 6px;
  top: 50%;
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: rgba(46, 50, 46, 0.66);
  display: inline-grid;
  place-items: center;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  box-shadow: none;
  transform: translateY(-50%) translateX(4px);
  transition:
    opacity var(--transition-fast),
    color var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-fast);
}

.rail-nav-row.has-action:hover .rail-compose-btn {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(-50%) translateX(0);
}

.rail-compose-btn:hover:not(:disabled),
.rail-compose-btn:focus-visible {
  color: var(--page-accent-strong);
  background: rgba(32, 36, 32, 0.06);
  border-color: transparent;
  box-shadow: none;
  transform: translateY(-50%) translateX(0);
  outline: none;
}

.rail-compose-btn:disabled {
  opacity: 0.48;
  cursor: not-allowed;
}

.rail-compose-icon {
  width: 17px;
  height: 17px;
  display: block;
}

.rail-conversations {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1 1 160px;
  margin-top: 10px;
  padding: 10px 4px 0;
  border-top: 1px solid rgba(35, 39, 35, 0.08);
}

.rail-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 5px;
  font-size: 11px;
  font-weight: 820;
  letter-spacing: 0.02em;
  color: rgba(82, 84, 80, 0.66);
}

.rail-section-count {
  min-width: 24px;
  height: 22px;
  padding: 0 7px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(32, 36, 32, 0.055);
  color: rgba(62, 66, 62, 0.72);
  font-variant-numeric: tabular-nums;
}

.rail-search {
  margin-top: 8px;
  position: relative;
  padding: 0 3px;
}

.rail-search::before {
  content: '';
  position: absolute;
  left: 18px;
  top: 50%;
  width: 9px;
  height: 9px;
  border: 1.6px solid rgba(112, 114, 110, 0.32);
  border-radius: 999px;
  transform: translateY(-60%);
  pointer-events: none;
}

.rail-search::after {
  content: '';
  position: absolute;
  left: 27px;
  top: 25px;
  width: 6px;
  height: 1.6px;
  border-radius: 999px;
  background: rgba(112, 114, 110, 0.32);
  transform: rotate(45deg);
  pointer-events: none;
}

.rail-search-input {
  height: 32px;
  border-radius: 12px;
  border: 1px solid transparent;
  background: rgba(246, 246, 245, 0.74);
  padding: 0 12px 0 35px;
  box-shadow: none;
  color: var(--page-ink);
  font-size: 12px;
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast),
    box-shadow var(--transition-fast);
}

.rail-search-input::placeholder {
  color: rgba(116, 118, 114, 0.62);
}

.rail-search-input:focus {
  background: rgba(255, 255, 255, 0.94);
  border-color: rgba(32, 36, 32, 0.12);
  box-shadow: 0 8px 18px rgba(24, 28, 24, 0.035);
}

.rail-list {
  flex: 1 1 auto;
  min-height: 0;
  margin-top: 8px;
  padding: 2px 0 8px;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 1px;
  scrollbar-width: thin;
  scrollbar-color: rgba(116, 120, 116, 0.22) transparent;
  overscroll-behavior: contain;
}

.rail-list::-webkit-scrollbar {
  width: 6px;
}

.rail-list::-webkit-scrollbar-track {
  background: transparent;
}

.rail-list::-webkit-scrollbar-thumb {
  background: rgba(116, 120, 116, 0.2);
  border-radius: 999px;
}

.rail-item {
  text-align: left;
  width: 100%;
  min-height: 44px;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 8px;
  padding: 7px 6px 7px 16px;
  cursor: pointer;
  transition:
    background-color var(--transition-fast),
    color var(--transition-fast),
    transform var(--transition-fast);
  box-shadow: none;
  position: relative;
  overflow: hidden;
}

.rail-item::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 10px;
  bottom: 10px;
  width: 2px;
  border-radius: 999px;
  background: rgba(32, 36, 32, 0);
  opacity: 0;
  transform: scaleY(0.72);
  transform-origin: center;
  transition:
    background-color var(--transition-fast),
    opacity var(--transition-fast),
    transform var(--transition-fast);
}

.rail-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.rail-item:hover {
  background: rgba(32, 36, 32, 0.024);
  border-color: transparent;
  box-shadow: none;
}

.rail-item.active {
  background: transparent;
  border-color: transparent;
  box-shadow: none;
}

.rail-item.active::before {
  background: rgba(32, 36, 32, 0.68);
  opacity: 1;
  transform: scaleY(1);
}

.rail-item-title {
  flex: 1;
  padding-left: 2px;
  font-size: 13px;
  line-height: 1.2;
  font-weight: 680;
  color: var(--page-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rail-item.active .rail-item-title {
  font-weight: 820;
  letter-spacing: -0.01em;
}

.rail-title-input {
  flex: 1;
  min-width: 0;
  border: 1px solid rgba(32, 36, 32, 0.14);
  border-radius: 11px;
  padding: 4px 8px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.92);
}

.rail-item-actions {
  display: flex;
  gap: 3px;
  opacity: 0;
  transform: translateX(2px);
  transition:
    opacity var(--transition-fast),
    transform var(--transition-fast);
}

.rail-item:hover .rail-item-actions {
  opacity: 1;
  transform: translateX(0);
}

.item-action-btn {
  border: 1px solid transparent;
  width: 24px;
  height: 24px;
  border-radius: 9px;
  background: transparent;
  color: rgba(86, 88, 84, 0.5);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.item-action-btn:hover:not(:disabled) {
  background: rgba(32, 36, 32, 0.06);
  border-color: transparent;
  color: rgba(32, 36, 32, 0.82);
}

.item-action-btn.danger:hover:not(:disabled) {
  background: rgba(188, 77, 67, 0.1);
  color: #a33d35;
}

.item-action-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.action-icon {
  width: 13px;
  height: 13px;
  display: block;
}

.rail-empty {
  flex: 1 1 auto;
  min-height: 88px;
  margin-top: 8px;
  padding: 14px 12px;
  color: var(--page-muted);
  border-radius: 18px;
  border: 1px dashed rgba(97, 112, 89, 0.16);
  background: rgba(255, 255, 255, 0.7);
}

.rail-empty-title {
  font-weight: 720;
  color: var(--page-ink);
}

.rail-empty-sub {
  margin-top: 5px;
  font-size: 12px;
  line-height: 1.45;
}

.rail-spacer {
  flex: 0 0 4px;
}

.rail-player-slot {
  position: relative;
  z-index: 1;
  min-width: 0;
  padding-top: 6px;
}

.rail-user-card {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  padding: 10px;
  border-radius: 18px;
  border: 1px solid rgba(222, 229, 218, 0.86);
  background: rgba(255, 255, 255, 0.9);
  box-shadow:
    0 12px 28px rgba(46, 55, 42, 0.055),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.rail-user-card--top {
  margin-top: 0;
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 20px;
}

.rail-user-avatar {
  flex: 0 0 42px;
  width: 42px;
  height: 42px;
  border-radius: 15px;
  overflow: hidden;
  display: grid;
  place-items: center;
  color: #ffffff;
  font-size: 14px;
  font-weight: 840;
  background:
    radial-gradient(circle at 30% 20%, rgba(255, 255, 255, 0.9), transparent 42%),
    linear-gradient(135deg, #f5f5f4, #d9d9d6);
  box-shadow: 0 10px 20px rgba(24, 28, 24, 0.1);
}

.rail-user-avatar-image {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.rail-user-copy {
  min-width: 0;
}

.rail-user-name {
  font-size: 14px;
  font-weight: 800;
  color: var(--page-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rail-user-meta {
  margin-top: 2px;
  font-size: 11px;
  color: rgba(92, 101, 86, 0.66);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-shell {
  background:
    radial-gradient(circle at 88% 10%, rgba(248, 248, 247, 0.72), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 250, 250, 0.94));
  border-radius: 0;
  box-shadow: none;
  border: none;
  border-left: none;
  overflow: hidden;
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-rows: auto 1fr auto;
  min-width: 0;
  backdrop-filter: blur(26px) saturate(140%);
}

.chat-topbar {
  padding: 20px clamp(18px, 2vw, 30px) 16px;
  border-bottom: 1px solid rgba(69, 83, 64, 0.08);
  background: rgba(255, 255, 255, 0.42);
  min-width: 0;
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.chat-eyebrow {
  font-size: 11px;
  font-weight: 850;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(112, 116, 112, 0.68);
}

.chat-topbar-title {
  margin-top: 4px;
  font-size: clamp(20px, 1.6vw, 28px);
  line-height: 1.18;
  font-weight: 860;
  letter-spacing: -0.035em;
  color: var(--page-ink);
}

.chat-topbar-sub {
  max-width: min(42%, 520px);
  padding: 9px 12px;
  border-radius: 16px;
  border: 1px solid rgba(32, 36, 32, 0.08);
  background: rgba(255, 255, 255, 0.42);
  font-size: 12px;
  color: rgba(83, 91, 67, 0.72);
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
  padding: clamp(16px, 1.6vw, 28px);
  overflow: auto;
  scroll-behavior: smooth;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.03));
  min-width: 0;
}

.welcome-card,
.progress-card {
  background:
    radial-gradient(circle at 100% 0%, rgba(231, 237, 227, 0.68), transparent 30%),
    rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(222, 229, 218, 0.82);
  border-radius: 28px;
  padding: 22px;
  margin: 4px 0 18px;
  box-shadow: var(--page-shadow-soft);
  backdrop-filter: blur(18px);
}

.welcome-kicker {
  margin-bottom: 8px;
  color: rgba(92, 96, 92, 0.7);
  font-size: 12px;
  font-weight: 840;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.welcome-title,
.progress-title {
  font-weight: 840;
  color: var(--page-ink);
  margin-bottom: 6px;
}

.welcome-title {
  font-size: clamp(24px, 2vw, 34px);
  letter-spacing: -0.04em;
}

.welcome-sub,
.progress-sub {
  font-size: 13px;
  color: var(--page-muted);
  margin-bottom: 14px;
  line-height: 1.7;
}

.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  justify-content: flex-start;
}

.quick-question {
  padding: 9px 14px;
  border: 1px solid rgba(124, 143, 99, 0.16);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.5);
  color: rgba(60, 72, 49, 0.78);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-normal);
  backdrop-filter: blur(14px);
}

.quick-question:hover {
  background: rgba(32, 36, 32, 0.06);
  border-color: rgba(32, 36, 32, 0.14);
  transform: translateY(-1px);
}

.progress-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.progress-current {
  font-size: 13px;
  color: var(--page-accent-strong);
  font-weight: 720;
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
  background: rgba(93, 87, 63, 0.18);
  flex: 0 0 auto;
}

.progress-step.is-completed .step-dot {
  background: #5d7f47;
}

.progress-step.is-in_progress .step-dot {
  background: #d0a251;
  box-shadow: 0 0 0 6px rgba(208, 162, 81, 0.14);
}

.progress-step.is-failed .step-dot {
  background: #bc4d43;
}

.step-body {
  min-width: 0;
}

.step-label {
  font-size: 14px;
  font-weight: 720;
  color: var(--page-ink);
}

.step-desc {
  font-size: 12px;
  color: var(--page-muted);
  margin-top: 2px;
}

.tool-list {
  display: grid;
  gap: 8px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(97, 90, 64, 0.1);
}

.tool-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}

.tool-name {
  color: var(--page-ink);
  word-break: break-all;
}

.tool-status {
  text-transform: capitalize;
  color: var(--page-muted);
}

.tool-status.is-running {
  color: #b58132;
}

.tool-status.is-success {
  color: #5d7f47;
}

.tool-status.is-failed {
  color: #bc4d43;
}

.agent-observability {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid rgba(93, 83, 57, 0.12);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.7), rgba(247, 241, 228, 0.62)),
    repeating-linear-gradient(90deg, rgba(80, 74, 54, 0.035) 0 1px, transparent 1px 18px);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.75);
}

.observability-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  font-weight: 850;
  letter-spacing: 0.08em;
  color: var(--page-ink);
  text-transform: uppercase;
}

.observability-time {
  font-variant-numeric: tabular-nums;
  color: var(--page-accent-strong);
}

.observability-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--page-muted);
}

.observability-meta span {
  padding: 4px 7px;
  border: 1px solid rgba(93, 83, 57, 0.1);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.58);
}

.thought-list {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.thought-item {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  font-size: 12px;
  line-height: 1.55;
}

.thought-kind {
  color: #8f6632;
  font-weight: 820;
}

.thought-text {
  color: var(--page-ink);
  overflow-wrap: anywhere;
}

.thought-item.is-reflection .thought-kind,
.reflection-label {
  color: var(--page-accent-strong);
}

.reflection-box {
  display: flex;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(93, 83, 57, 0.1);
  font-size: 12px;
  line-height: 1.55;
  color: var(--page-ink);
}

.reflection-label {
  flex: 0 0 auto;
  font-weight: 840;
}

.chat-error-banner {
  margin: 0 20px 10px;
  padding: 10px 14px;
  border-radius: 16px;
  border: 1px solid rgba(188, 77, 67, 0.16);
  background: rgba(255, 241, 235, 0.74);
  color: #9b4439;
  font-size: 13px;
  line-height: 1.5;
  box-shadow: var(--page-shadow-soft);
  backdrop-filter: blur(18px);
}

.chat-input {
  padding: 14px clamp(14px, 1.4vw, 22px) 18px;
  border-top: 1px solid rgba(110, 100, 69, 0.08);
  background: rgba(255, 255, 255, 0.18);
  min-width: 0;
}

.input-form {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
  padding: 7px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  background: rgba(255, 255, 255, 0.52);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.58), var(--page-shadow-soft);
  backdrop-filter: blur(22px);
}

.message-input {
  flex: 1;
  min-width: 0;
  border-radius: 999px;
  padding: 12px 15px;
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
  border: 1px solid rgba(32, 36, 32, 0.12);
  background: linear-gradient(135deg, #2f332f, #6f746f);
  color: #ffffff;
  cursor: pointer;
  transition: all var(--transition-fast);
  box-shadow: 0 13px 24px rgba(24, 28, 24, 0.16);
  font-weight: 760;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.03);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.workspace-shell {
  height: 100%;
  min-height: 0;
  min-width: 0;
  border-radius: 0;
  border: none;
  border-left: none;
  background:
    radial-gradient(circle at 78% 12%, rgba(248, 248, 247, 0.72), transparent 28%),
    radial-gradient(circle at 18% 88%, rgba(250, 250, 249, 0.86), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 250, 250, 0.94));
  box-shadow: none;
  overflow: hidden;
  padding: clamp(22px, 2.2vw, 38px);
  display: grid;
  grid-template-rows: auto 1fr;
  gap: clamp(18px, 2vw, 28px);
}

.workspace-hero {
  position: relative;
  z-index: 1;
  max-width: 720px;
}

.workspace-eyebrow {
  font-size: 12px;
  font-weight: 860;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(112, 116, 112, 0.68);
}

.workspace-hero h1 {
  margin: 8px 0 10px;
  font-size: clamp(32px, 4vw, 58px);
  line-height: 1;
  font-weight: 900;
  letter-spacing: -0.07em;
  color: var(--page-ink);
}

.workspace-hero p {
  max-width: 620px;
  margin: 0;
  font-size: 15px;
  line-height: 1.8;
  color: var(--page-muted);
}

.workspace-empty-card {
  position: relative;
  z-index: 1;
  align-self: stretch;
  min-height: 0;
  border-radius: 34px;
  border: 1px dashed rgba(32, 36, 32, 0.14);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.88), rgba(249, 249, 248, 0.78));
  display: grid;
  place-items: center;
  padding: clamp(22px, 3vw, 48px);
  text-align: center;
}

.workspace-empty-mark {
  position: relative;
  width: 76px;
  height: 76px;
  margin: 0 auto 18px;
  border-radius: 28px;
  color: var(--page-accent-strong);
  background: rgba(255, 255, 255, 0.62);
  display: grid;
  place-items: center;
  box-shadow: 0 18px 36px rgba(24, 28, 24, 0.07), inset 0 0 0 1px rgba(224, 224, 222, 0.82);
}

.workspace-empty-icon {
  width: 36px;
  height: 36px;
  display: block;
  overflow: visible;
}

.workspace-empty-icon path {
  vector-effect: non-scaling-stroke;
}

.workspace-empty-copy h2 {
  margin: 0;
  font-size: clamp(20px, 2vw, 30px);
  font-weight: 860;
  letter-spacing: -0.04em;
  color: var(--page-ink);
}

.workspace-empty-copy p {
  max-width: 560px;
  margin: 10px auto 0;
  font-size: 14px;
  line-height: 1.8;
  color: var(--page-muted);
}

@media (max-width: 980px) {
  .agent-layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
    overflow: auto;
    border-radius: 0;
  }

  .agent-rail {
    height: auto;
    max-height: none;
    border-radius: 0;
    border-right: none;
    border-bottom: 1px solid rgba(126, 117, 82, 0.1);
  }

  .rail-conversations {
    max-height: 280px;
  }

  .chat-shell,
  .workspace-shell {
    min-height: 680px;
    border-radius: 0;
    border-left: none;
    border-top: none;
  }
}

@media (max-width: 640px) {
  .agent-layout {
    padding: 0;
    gap: 0;
  }

  .agent-rail,
  .chat-shell,
  .workspace-shell {
    border-radius: 0;
  }

  .agent-rail {
    padding: 12px;
  }

  .rail-nav {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .rail-nav-item {
    min-height: 36px;
    padding: 0 9px;
  }

  .chat-topbar {
    flex-direction: column;
  }

  .chat-topbar-sub {
    max-width: 100%;
  }

  .input-form {
    border-radius: 22px;
    align-items: stretch;
  }

  .send-btn {
    padding: 0 14px;
  }
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
