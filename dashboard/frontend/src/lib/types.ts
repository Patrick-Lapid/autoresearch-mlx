export interface Run {
	run_id: string;
	iteration: number;
	started_at: number;
	ended_at: number | null;
	status: 'running' | 'completed' | 'failed';
	accepted: number | null; // 1 | 0 | null
	val_bpb: number | null;
	parent_run_id: string | null;

	depth: number | null;
	total_batch_size: number | null;
	device_batch_size: number | null;
	embedding_lr: number | null;
	unembedding_lr: number | null;
	matrix_lr: number | null;
	scalar_lr: number | null;
	weight_decay: number | null;
	warmup_ratio: number | null;
	warmdown_ratio: number | null;
	final_lr_frac: number | null;
	adam_betas: string | null;
	window_pattern: string | null;
	aspect_ratio: number | null;
	head_dim: number | null;
	time_budget: number | null;

	num_params_m: number | null;
	total_tokens_m: number | null;
	num_steps: number | null;
	training_seconds: number | null;
	peak_vram_mb: number | null;
	mfu_percent: number | null;

	diff_patch: string | null;
}

export interface StepEvent {
	type: 'step';
	run_id: string;
	step: number;
	wall_time: number;
	loss: number;
	smooth_loss: number;
	lrm: number;
	tok_per_sec: number;
	pct_done: number;
	epoch: number;
}

export interface AgentNote {
	id: number;
	run_id: string;
	ts: number;
	intent: string | null;
	hypothesis: string | null;
	raw: string | null;
}

export interface RunDetail {
	run: Run;
	steps: StepEvent[];
	notes: AgentNote[];
}

export const HYPERPARAM_KEYS = [
	'depth', 'total_batch_size', 'device_batch_size', 'embedding_lr', 'unembedding_lr',
	'matrix_lr', 'scalar_lr', 'weight_decay', 'warmup_ratio', 'warmdown_ratio',
	'final_lr_frac', 'window_pattern', 'aspect_ratio', 'head_dim', 'time_budget',
] as const;

export type HyperparamKey = (typeof HYPERPARAM_KEYS)[number];

export interface ParamChange {
	key: string;
	from: string | number;
	to: string | number;
}

export interface PlateauChild {
	run: Run;
	note: AgentNote | null;
	paramChanges: ParamChange[];
}

export interface Plateau {
	parent: Run;
	children: PlateauChild[];
	noteForParent: AgentNote | null;
}

export type SSEEvent =
	| { type: 'run_start'; run_id: string; iteration: number; parent_run_id: string | null; config: Record<string, unknown> }
	| StepEvent
	| { type: 'run_end'; run_id: string; val_bpb: number | null; accepted: boolean | null; summary: Record<string, unknown> }
	| { type: 'agent_note'; run_id: string; intent: string; hypothesis: string }
	| { type: 'accept_decision'; run_id: string; accepted: boolean };
