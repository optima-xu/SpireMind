import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Locale } from "./types";

const MESSAGES = {
  zh: {
    brandSubtitle: "杀戮尖塔 2 AI 控制台",
    navCockpit: "实时控制台",
    navReplay: "历史回放",
    navSettings: "设置与诊断",
    wsConnected: "WS 已连接",
    wsReconnecting: "WS 重连中",
    statusIdle: "空闲",
    statusRunning: "运行中",
    statusPaused: "已暂停",
    statusStopping: "停止中",
    statusError: "异常",
    startNewRun: "开新局",
    attachRun: "接管当前对局",
    observeBridge: "刷新画面",
    stepOnce: "单步执行",
    pause: "暂停",
    resume: "继续",
    stop: "停止",
    character: "角色",
    ascension: "进阶",
    policy: "策略",
    policyModel: "AI 模型 + 规则护栏",
    policyRules: "仅确定性规则",
    steps: "步数",
    verified: "已验证",
    rulesCount: "规则直出",
    fallbacks: "保底回退",
    tokens: "Tokens",
    attemptId: "局次 ID",
    backToLive: "回到最新状态",
    inspectingStep: "正在查看历史步骤",
    noStateTitle: "尚未观测到游戏状态",
    noStateHint: "请先启动《杀戮尖塔 2》并加载 STS2AIMCP Mod，然后点击「刷新画面」、「开新局」或「接管当前对局」。",
    hp: "生命",
    gold: "金币",
    actFloor: "阶段 / 层数",
    boss: "Boss",
    deck: "牌组",
    relics: "遗物",
    potions: "药水",
    emptyPotions: "空药水槽",
    energy: "能量",
    block: "格挡",
    turn: "回合",
    stars: "星辰",
    drawPile: "抽牌堆",
    discardPile: "弃牌堆",
    exhaustPile: "消耗堆",
    enemies: "场上敌人",
    hand: "手牌",
    intents: "意图",
    dead: "已阵亡",
    unplayable: "不可打出",
    selfLethalRisk: "自伤致死风险",
    excluded: "安全过滤",
    mapSection: "地图路径",
    currentNode: "当前节点",
    reachableNodes: "可达节点",
    choicesSection: "可选项",
    legalActionsSection: "当前合法动作",
    decisionTitle: "AI 决策面板",
    noDecisionHint: "等待首次决策...",
    chosenAction: "选定动作",
    confidence: "置信度",
    sourceRule: "确定性规则",
    sourceModel: "大模型决策",
    sourceFallback: "安全保底",
    reasoning: "决策理由",
    calculations: "算术校验",
    runContext: "对局策略上下文",
    combatAssessment: "战斗确定性评估",
    providerError: "模型调用异常",
    timeline: "本局最近步骤",
    viewDeck: "查看完整牌组",
    viewRelics: "查看遗物详情",
    close: "关闭",
    runsListTitle: "历史对局记录",
    searchRuns: "按局次 ID 或角色筛选...",
    refresh: "刷新",
    noRuns: "暂无历史记录",
    selectRunHint: "请在左侧选择一局历史记录开始逐步回放。",
    prevStep: "上一步",
    nextStep: "下一步",
    allScenes: "全部场景",
    formatV2: "V2 统一日志",
    formatLegacy: "V1 兼容日志",
    hotkeyHint: "快捷键：← / → 切换步骤",
    settingsTitle: "模型与运行配置",
    presetsTitle: "一键模型预设",
    saveSettings: "保存配置",
    saving: "保存中...",
    savedSuccess: "配置已保存至 config.local.toml / .env",
    modelSection: "大模型配置",
    gameSection: "游戏桥接配置",
    strategySection: "策略与战斗护栏",
    runtimeSection: "运行时限制",
    apiKeyStatus: "API Key 状态",
    configured: "已配置",
    missing: "未配置",
    newApiKeyLabel: "更新 API Key（留空保持不变）",
    newApiKeyPlaceholder: "输入新 Key 将加密/本地写入 .env",
    doctorTitle: "连通性诊断 (Doctor)",
    testBridge: "检测游戏桥接",
    testLlm: "测试 LLM API",
    testing: "检测中...",
    ok: "正常",
    failed: "失败",
    latency: "耗时",
    configPath: "配置文件路径",
    envPath: "密钥文件路径",
    confirmRunningDisabled: "运行中请先停止任务再修改保存配置。",
    combatIncoming: "来袭伤害",
    combatUnblocked: "未格挡伤害",
    combatMargin: "回合结束预估 HP",
    survivalStatus: "存活判定",
    none: "无",
    cardsCount: "张",
  },
  en: {
    brandSubtitle: "Slay the Spire 2 AI Console",
    navCockpit: "Cockpit",
    navReplay: "Replay",
    navSettings: "Settings & Doctor",
    wsConnected: "WS Connected",
    wsReconnecting: "WS Reconnecting",
    statusIdle: "Idle",
    statusRunning: "Running",
    statusPaused: "Paused",
    statusStopping: "Stopping",
    statusError: "Error",
    startNewRun: "Start New Run",
    attachRun: "Attach Run",
    observeBridge: "Observe Bridge",
    stepOnce: "Step Once",
    pause: "Pause",
    resume: "Resume",
    stop: "Stop",
    character: "Character",
    ascension: "Ascension",
    policy: "Policy",
    policyModel: "AI + Safety Guards",
    policyRules: "Rules Only",
    steps: "Steps",
    verified: "Verified",
    rulesCount: "Rules",
    fallbacks: "Fallbacks",
    tokens: "Tokens",
    attemptId: "Attempt ID",
    backToLive: "Back to Live",
    inspectingStep: "Inspecting historical step",
    noStateTitle: "No Game State Observed Yet",
    noStateHint: "Launch Slay the Spire 2 with the STS2AIMCP mod loaded, then click Observe Bridge, Start New Run, or Attach Run.",
    hp: "HP",
    gold: "Gold",
    actFloor: "Act / Floor",
    boss: "Boss",
    deck: "Deck",
    relics: "Relics",
    potions: "Potions",
    emptyPotions: "No potions",
    energy: "Energy",
    block: "Block",
    turn: "Turn",
    stars: "Stars",
    drawPile: "Draw",
    discardPile: "Discard",
    exhaustPile: "Exhaust",
    enemies: "Enemies",
    hand: "Hand",
    intents: "Intents",
    dead: "Defeated",
    unplayable: "Unplayable",
    selfLethalRisk: "Self-Lethal Risk",
    excluded: "Safety Filtered",
    mapSection: "Map Route",
    currentNode: "Current Node",
    reachableNodes: "Reachable Nodes",
    choicesSection: "Choices",
    legalActionsSection: "Legal Actions",
    decisionTitle: "AI Decision",
    noDecisionHint: "Waiting for first decision...",
    chosenAction: "Chosen Action",
    confidence: "Confidence",
    sourceRule: "Policy Rule",
    sourceModel: "LLM Decision",
    sourceFallback: "Fallback",
    reasoning: "Reasoning",
    calculations: "Calculations",
    runContext: "Run Context",
    combatAssessment: "Combat Assessment",
    providerError: "Provider Error",
    timeline: "Recent Session Steps",
    viewDeck: "View Full Deck",
    viewRelics: "View Relics",
    close: "Close",
    runsListTitle: "Recorded Runs",
    searchRuns: "Filter by attempt ID or character...",
    refresh: "Refresh",
    noRuns: "No recorded runs found",
    selectRunHint: "Select a run on the left to inspect its steps.",
    prevStep: "Prev",
    nextStep: "Next",
    allScenes: "All Scenes",
    formatV2: "V2 Trace",
    formatLegacy: "Legacy V1",
    hotkeyHint: "Hotkeys: ← / → to step",
    settingsTitle: "Model & Runtime Configuration",
    presetsTitle: "Provider Presets",
    saveSettings: "Save Settings",
    saving: "Saving...",
    savedSuccess: "Settings saved to config.local.toml / .env",
    modelSection: "Model Configuration",
    gameSection: "Game Bridge Configuration",
    strategySection: "Strategy & Combat Guards",
    runtimeSection: "Runtime Limits",
    apiKeyStatus: "API Key Status",
    configured: "Configured",
    missing: "Missing",
    newApiKeyLabel: "Update API Key (leave blank to keep current)",
    newApiKeyPlaceholder: "Saved only to local .env",
    doctorTitle: "Live Diagnostics (Doctor)",
    testBridge: "Test Game Bridge",
    testLlm: "Test LLM API",
    testing: "Testing...",
    ok: "Healthy",
    failed: "Failed",
    latency: "Latency",
    configPath: "Config file",
    envPath: "Env file",
    confirmRunningDisabled: "Stop the active session before saving settings.",
    combatIncoming: "Incoming",
    combatUnblocked: "Unblocked",
    combatMargin: "End-now HP",
    survivalStatus: "Survival",
    none: "None",
    cardsCount: "cards",
  },
} as const;

export type MessageKey = keyof typeof MESSAGES.zh;

interface I18nValue {
  locale: Locale;
  setLocale: (loc: Locale) => void;
  toggleLocale: () => void;
  t: (key: MessageKey) => string;
}

const I18nContext = createContext<I18nValue | null>(null);
const STORAGE_KEY = "spiremind.locale";

function readInitialLocale(): Locale {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "zh" || saved === "en") {
      return saved;
    }
  } catch {
    // Ignore storage failures in restricted contexts.
  }
  return "zh";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readInitialLocale);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      // Ignore storage errors.
    }
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  const setLocale = (next: Locale) => setLocaleState(next);
  const toggleLocale = () => setLocaleState((prev) => (prev === "zh" ? "en" : "zh"));
  const t = (key: MessageKey): string => MESSAGES[locale][key];

  return (
    <I18nContext.Provider value={{ locale, setLocale, toggleLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used inside I18nProvider");
  }
  return ctx;
}
