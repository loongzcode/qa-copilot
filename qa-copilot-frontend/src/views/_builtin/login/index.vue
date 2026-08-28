<script setup lang="ts">
import { useAppStore } from '@/store/modules/app';
import { useThemeStore } from '@/store/modules/theme';
import PwdLogin from './modules/pwd-login.vue';

defineOptions({ name: 'LoginPage' });

const appStore = useAppStore();
const themeStore = useThemeStore();
</script>

<template>
  <div class="knowledge-login">
    <div class="knowledge-login__grid" aria-hidden="true"></div>

    <section class="knowledge-login__intro">
      <div class="brand-mark" aria-hidden="true">
        <SvgIcon icon="mdi:clipboard-check-outline" />
      </div>
      <div class="brand-copy">
        <span class="brand-eyebrow">QA Copilot · Intelligent Testing Platform</span>
        <h1>
          让测试知识
          <br />
          转化为质量生产力
        </h1>
        <p>面向企业测试团队，统一完成知识问答、需求解析、用例补全、人工审核与受控自动化执行。</p>
      </div>

      <div class="knowledge-flow" aria-label="QA Copilot 测试工作流程">
        <div class="flow-item">
          <span class="flow-index">01</span>
          <div>
            <strong>测试知识问答</strong>
            <small>统一检索用例、流程、接口与缺陷经验</small>
          </div>
        </div>
        <div class="flow-item">
          <span class="flow-index">02</span>
          <div>
            <strong>需求解析补全</strong>
            <small>拆解需求点，识别覆盖缺口并生成建议</small>
          </div>
        </div>
        <div class="flow-item">
          <span class="flow-index">03</span>
          <div>
            <strong>审核与执行</strong>
            <small>人工确认用例，批准后受控自动化执行</small>
          </div>
        </div>
      </div>
    </section>

    <section class="knowledge-login__panel">
      <div class="panel-tools">
        <ThemeSchemaSwitch
          :theme-schema="themeStore.themeScheme"
          :show-tooltip="false"
          class="panel-tool"
          @switch="themeStore.toggleThemeScheme"
        />
        <LangSwitch
          v-if="themeStore.header.multilingual.visible"
          :lang="appStore.locale"
          :lang-options="appStore.localeOptions"
          :show-tooltip="false"
          class="panel-tool"
          @change-lang="appStore.changeLocale"
        />
      </div>

      <main class="login-card">
        <div class="login-card__brand">
          <span class="login-card__logo"><SvgIcon icon="mdi:clipboard-check-outline" /></span>
          <span>QA Copilot</span>
        </div>
        <header>
          <span class="login-card__eyebrow">智能测试协作平台</span>
          <h2>欢迎回来</h2>
          <p>登录后进入项目知识库、需求与测试资产工作台。</p>
        </header>
        <PwdLogin />
        <footer>
          <SvgIcon icon="mdi:shield-check-outline" />
          <span>AI 辅助生成 · 人工审核发布 · 受控自动化执行</span>
        </footer>
      </main>
    </section>
  </div>
</template>

<style scoped>
.knowledge-login {
  --login-ink: #10221d;
  --login-muted: #61716b;
  --login-line: rgb(18 86 65 / 12%);
  --login-surface: rgb(255 255 255 / 88%);
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(460px, 0.92fr);
  min-height: 100%;
  overflow: hidden;
  color: var(--login-ink);
  background: #edf4ef;
}

.knowledge-login::before {
  position: absolute;
  top: -18%;
  left: -10%;
  width: 640px;
  height: 640px;
  border-radius: 50%;
  background: rgb(80 164 123 / 13%);
  content: '';
  filter: blur(2px);
}

.knowledge-login__grid {
  position: absolute;
  inset: 0;
  opacity: 0.42;
  background-image:
    linear-gradient(rgb(22 77 61 / 5%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(22 77 61 / 5%) 1px, transparent 1px);
  background-size: 42px 42px;
  mask-image: linear-gradient(to right, #000, transparent 75%);
  pointer-events: none;
}

.knowledge-login__intro,
.knowledge-login__panel {
  position: relative;
  z-index: 1;
}

.knowledge-login__intro {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: clamp(48px, 7vw, 112px);
}

.brand-mark {
  display: grid;
  width: 52px;
  height: 52px;
  margin-bottom: 34px;
  border: 1px solid rgb(16 104 78 / 16%);
  border-radius: 16px;
  color: #fff;
  font-size: 27px;
  place-items: center;
  background: #176d54;
  box-shadow: 0 12px 30px rgb(22 109 83 / 20%);
}

.brand-eyebrow,
.login-card__eyebrow {
  color: #1b765c;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.brand-copy h1 {
  max-width: 620px;
  margin: 15px 0 22px;
  font-size: clamp(46px, 5.1vw, 76px);
  font-weight: 650;
  letter-spacing: -0.055em;
  line-height: 1.06;
}

.brand-copy p {
  max-width: 620px;
  margin: 0;
  color: var(--login-muted);
  font-size: 17px;
  line-height: 1.8;
}

.knowledge-flow {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  max-width: 680px;
  margin-top: 46px;
  border-top: 1px solid var(--login-line);
  border-bottom: 1px solid var(--login-line);
}

.flow-item {
  padding: 18px 20px 20px;
  border-right: 1px solid var(--login-line);
}

.flow-item:first-child {
  padding-left: 0;
}

.flow-item:last-child {
  padding-right: 0;
  border-right: 0;
}

.flow-index {
  display: block;
  margin-bottom: 15px;
  color: #329070;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.flow-item strong,
.flow-item small {
  display: block;
}

.flow-item strong {
  margin-bottom: 5px;
  font-size: 15px;
}

.flow-item small {
  color: var(--login-muted);
  font-size: 13px;
}

.knowledge-login__panel {
  display: grid;
  min-height: 100%;
  padding: 32px clamp(32px, 6vw, 96px);
  place-items: center;
  background: rgb(255 255 255 / 50%);
  border-left: 1px solid rgb(16 86 65 / 8%);
}

.panel-tools {
  position: absolute;
  top: 28px;
  right: 32px;
  display: flex;
  gap: 6px;
}

.panel-tool {
  display: grid;
  width: 36px;
  height: 36px;
  border: 1px solid var(--login-line);
  border-radius: 10px;
  background: rgb(255 255 255 / 72%);
  place-items: center;
}

.login-card {
  width: min(100%, 430px);
  padding: 38px 42px;
  border: 1px solid rgb(17 85 65 / 10%);
  border-radius: 24px;
  background: var(--login-surface);
  box-shadow: 0 26px 80px rgb(25 64 52 / 12%);
  backdrop-filter: blur(18px);
  transition:
    opacity 240ms cubic-bezier(0.23, 1, 0.32, 1),
    transform 240ms cubic-bezier(0.23, 1, 0.32, 1);
  @starting-style {
    opacity: 0;
    transform: translateY(10px) scale(0.985);
  }
}

.login-card__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 36px;
  color: var(--login-ink);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.login-card__logo {
  display: grid;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  color: #fff;
  font-size: 18px;
  background: #176d54;
  place-items: center;
}

.login-card h2 {
  margin: 9px 0 8px;
  font-size: 32px;
  font-weight: 650;
  letter-spacing: -0.035em;
}

.login-card header p {
  margin: 0 0 24px;
  color: var(--login-muted);
  font-size: 14px;
}

.login-card footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-top: 22px;
  color: #83908b;
  font-size: 12px;
}

:global(.dark) .knowledge-login {
  --login-ink: #edf8f3;
  --login-muted: #9aaca5;
  --login-line: rgb(168 215 197 / 13%);
  --login-surface: rgb(19 30 27 / 88%);
  background: #0e1714;
}

:global(.dark) .knowledge-login__panel {
  background: rgb(8 15 13 / 35%);
}

:global(.dark) .panel-tool {
  background: rgb(22 35 31 / 80%);
}

@media (max-width: 900px) {
  .knowledge-login {
    display: block;
  }

  .knowledge-login__intro {
    display: none;
  }

  .knowledge-login__panel {
    min-height: 100%;
    padding: 76px 20px 32px;
    border-left: 0;
  }

  .login-card {
    padding: 32px 24px;
    border-radius: 20px;
  }
}

@media (max-height: 760px) and (min-width: 901px) {
  .knowledge-login__intro {
    padding-top: 42px;
    padding-bottom: 42px;
  }

  .brand-mark {
    margin-bottom: 22px;
  }

  .brand-copy h1 {
    margin-top: 10px;
    margin-bottom: 16px;
    font-size: clamp(42px, 4.4vw, 62px);
  }

  .brand-copy p {
    font-size: 15px;
    line-height: 1.65;
  }

  .knowledge-flow {
    margin-top: 30px;
  }

  .login-card {
    padding-top: 30px;
    padding-bottom: 30px;
  }

  .login-card__brand {
    margin-bottom: 28px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-card {
    transition: opacity 160ms ease;
  }
}
</style>
