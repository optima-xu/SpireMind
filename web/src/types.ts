export type SessionStatus = "idle" | "running" | "paused" | "stopping" | "error";
export type PolicyMode = "model" | "rules";
export type RunMode = "start" | "attach";
export type Locale = "zh" | "en";
export type TabId = "cockpit" | "replay" | "settings";

export type Scene =
  | "combat"
  | "card_selection"
  | "card_reward"
  | "shop"
  | "rest"
  | "map"
  | "event"
  | "treasure"
  | "main_menu"
  | "character_select"
  | "modal"
  | "game_over"
  | "unknown";

export type PublicFactsValue = { encoded: string } | Record<string, unknown> | null | undefined;

export interface Power {
  id: string;
  amount?: number | null;
  description?: string;
  trigger_progress?: PublicFactsValue;
}

export interface Intent {
  type: string;
  damage?: number | null;
  hits?: number | null;
  total_damage?: number | null;
  text?: string;
}

export interface Enemy {
  id: string;
  ref: string;
  name: string;
  hp: number;
  max_hp: number;
  block: number;
  powers: Power[];
  intents: Intent[];
  alive: boolean;
}

export interface Card {
  id: string;
  ref: string;
  name: string;
  type: string;
  cost?: number | null;
  star_cost?: number | null;
  upgraded: boolean;
  text: string;
  keywords: string[];
  values?: PublicFactsValue;
  target_values?: PublicFactsValue;
  affliction_id?: string;
  affliction_amount?: number | null;
  affliction_description?: string;
  playable?: boolean | null;
  unplayable_reason?: string;
  count: number;
}

export interface Item {
  id: string;
  name: string;
  text: string;
  slot?: number | null;
  amount?: number | null;
  trigger_progress?: PublicFactsValue;
}

export interface Pile {
  count: number;
  cards: Card[];
}

export interface CombatState {
  turn_phase: string;
  energy: number;
  stars: number;
  focus: number;
  block: number;
  turn: number;
  attacks_played: number;
  hand: Card[];
  draw: Pile;
  discard: Pile;
  exhaust: Pile;
  powers: Power[];
  enemies: Enemy[];
  orbs?: PublicFactsValue;
}

export interface MapNode {
  id: string;
  type: string;
  children: string[];
  reachable: boolean;
}

export interface MapState {
  current_node: string;
  nodes: MapNode[];
}

export interface Choice {
  id: string;
  label: string;
  description?: string;
  card?: Card | null;
  price?: number | null;
}

export interface Action {
  id: string;
  decision_id?: string;
  kind: string;
  label?: string;
  description?: string;
  card_id?: string | null;
  target_id?: string | null;
  node_id?: string | null;
  item_id?: string | null;
  option_id?: string | null;
  character?: string | null;
  ascension?: number | null;
  risk_tags?: string[];
}

export interface RunState {
  id: string;
  character: string;
  ascension: number;
  act?: number | null;
  floor: number;
  max_energy: number;
  hp: number;
  max_hp: number;
  gold: number;
  deck: Card[];
  relics: Item[];
  potions: Item[];
  boss: string;
  second_boss: string;
}

export interface GameState {
  scene: Scene;
  run: RunState;
  combat?: CombatState | null;
  map?: MapState | null;
  choices: Choice[];
  legal_actions: Action[];
  revision: number;
  decision_id: string;
  game_version: string;
  scene_facts?: PublicFactsValue;
  victory?: boolean | null;
}

export interface StrategyUpdateAudit {
  proposed?: Record<string, unknown>;
  applied?: Record<string, unknown>;
  rejected?: Record<string, string>;
}

export interface DecisionPayload {
  action: Action;
  reason?: string;
  confidence?: number;
  strategy_name?: string;
  policy_rule?: string | null;
  model_name?: string | null;
  calculations?: string[];
  fallback?: boolean;
  provider_error?: string | null;
  strategy_update?: Record<string, unknown> | null;
  strategy_update_audit?: StrategyUpdateAudit | null;
  excluded?: Record<string, string>;
  action_evaluation?: Record<string, unknown> | null;
}

export interface ActionReceipt {
  status: string;
  action_id: string;
  previous_decision_id: string;
  next_decision_id?: string | null;
  error?: string | null;
}

export interface StepRecord {
  step: number;
  timestamp?: string | null;
  decision_id?: string | null;
  revision?: number | null;
  scene?: string | null;
  state?: GameState | null;
  decision?: DecisionPayload | null;
  combat_assessment?: Record<string, unknown> | null;
  run_context?: Record<string, unknown> | null;
  receipt?: ActionReceipt | null;
  verify_ok?: boolean | null;
  latency_ms?: number | null;
  input_tokens?: number;
  output_tokens?: number;
  error?: string | null;
}

export interface SessionStats {
  steps: number;
  verified_actions: number;
  fallbacks: number;
  policy_rules: number;
  input_tokens: number;
  output_tokens: number;
}

export interface SessionSnapshot {
  status: SessionStatus;
  run_mode: RunMode;
  policy: PolicyMode;
  attempt_id: string | null;
  state: GameState | null;
  state_view: Record<string, unknown> | null;
  latest_decision: DecisionPayload | null;
  combat_assessment: Record<string, unknown> | null;
  run_context: Record<string, unknown> | null;
  recent_steps: StepRecord[];
  stats: SessionStats;
  last_error: string | null;
}

export interface ModelSettings {
  base_url: string;
  model: string;
  api_key_env: string;
  timeout_seconds: number;
  attempts: number;
  backoff_seconds: number;
  retry_budget_seconds: number;
  temperature: number | null;
  max_tokens: number | null;
  max_completion_tokens: number | null;
  reasoning_effort: string | null;
  json_mode: boolean;
  extra_body: Record<string, unknown>;
  calculator_mode: "off" | "auto" | "required";
  calculator_max_rounds: number;
  require_exact_model: boolean;
}

export interface GameSettings {
  base_url: string;
  timeout_seconds: number;
  transition_timeout: number;
  character: string;
  ascension: number;
  retry_budget_seconds: number;
}

export interface RuntimeSettings {
  runs_dir: string;
  step_delay_seconds: number;
  context_tokens: number;
  max_context_tokens: number;
  max_steps: number;
  max_errors: number;
  error_retry_seconds: number;
  max_total_tokens: number | null;
  max_seconds: number | null;
  allow_fallback: boolean;
  verify_effects: boolean;
}

export interface StrategySettings {
  combat_guards: boolean;
  boss_potion_damage_fraction: number;
  policy_version: string;
}

export interface ServerSettings {
  host: string;
  port: number;
}

export interface AppConfigPayload {
  model: ModelSettings;
  game: GameSettings;
  runtime: RuntimeSettings;
  strategy: StrategySettings;
  server: ServerSettings;
}

export interface ProviderPreset {
  label: string;
  base_url: string;
  model: string;
  api_key_env: string;
  json_mode: boolean;
  calculator_mode: "off" | "auto" | "required";
  temperature: number | null;
  max_tokens: number | null;
  extra_body?: Record<string, unknown>;
}

export interface ApiKeyStatus {
  env_var: string;
  configured: boolean;
  masked: string;
}

export interface SettingsPayload {
  config: AppConfigPayload;
  api_key: ApiKeyStatus;
  presets: Record<string, ProviderPreset>;
  config_path: string;
  env_path: string;
}

export interface BridgeProbeResult {
  ok: boolean;
  base_url: string;
  latency_ms?: number | null;
  protocol?: string | null;
  health?: Record<string, unknown> | null;
  observable?: boolean;
  scene?: string | null;
  phase?: string | null;
  game_version?: string | null;
  hp?: number | null;
  max_hp?: number | null;
  floor?: number | null;
  character?: string | null;
  legal_actions?: number;
  error?: string | null;
}

export interface LlmProbeResult {
  ok: boolean;
  configured_model: string;
  response_model?: string | null;
  base_url: string;
  latency_ms?: number | null;
  input_tokens?: number;
  output_tokens?: number;
  error?: string | null;
}

export interface RunSummaryItem {
  attempt_id: string;
  created_at?: string | null;
  mode: string;
  model?: string | null;
  character?: string | null;
  ascension?: number | null;
  game_version?: string | null;
  outcome: string;
  floor?: number | null;
  hp?: number | null;
  max_hp?: number | null;
  steps_count: number;
  format: string;
}

export interface RunDetailPayload {
  attempt_id: string;
  meta: RunSummaryItem;
  manifest: Record<string, unknown>;
  summary: Record<string, unknown>;
  steps: StepRecord[];
}

export type WsEvent =
  | { type: "session_snapshot"; data: SessionSnapshot }
  | {
      type: "session_status";
      data: {
        status: SessionStatus;
        run_mode: RunMode;
        policy: PolicyMode;
        attempt_id: string | null;
        last_error: string | null;
      };
    }
  | {
      type: "state_updated";
      data: {
        state: GameState | null;
        state_view: Record<string, unknown> | null;
        combat_assessment: Record<string, unknown> | null;
        run_context: Record<string, unknown> | null;
      };
    }
  | {
      type: "decision_made";
      data: {
        step: number;
        scene: string;
        decision: DecisionPayload;
        receipt: ActionReceipt;
        verify_ok: boolean;
        latency_ms: number;
        stats: SessionStats;
        step_record: StepRecord;
      };
    }
  | {
      type: "run_finished";
      data: {
        attempt_id: string | null;
        outcome?: string;
        summary?: Record<string, unknown>;
      };
    }
  | {
      type: "error";
      data: { message?: string; error?: string };
    }
  | {
      type: "pong";
      data: { status: SessionStatus };
    };
