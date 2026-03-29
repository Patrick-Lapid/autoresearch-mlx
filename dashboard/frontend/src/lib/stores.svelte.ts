import type { Run, StepEvent, AgentNote, SSEEvent } from './types';

export const liveRun = $state<{
	run: (Run & { config?: Record<string, unknown> }) | null;
	steps: StepEvent[];
	notes: Array<{ intent: string; hypothesis: string }>;
}>({
	run: null,
	steps: [],
	notes: []
});

export const allRuns = $state<{ list: Run[] }>({ list: [] });

export function connectSSE() {
	const es = new EventSource('/stream');
	es.onmessage = (e) => {
		const event: SSEEvent = JSON.parse(e.data);

		if (event.type === 'run_start') {
			liveRun.run = {
				run_id: event.run_id,
				iteration: event.iteration,
				started_at: Date.now() / 1000,
				ended_at: null,
				status: 'running',
				accepted: null,
				val_bpb: null,
				parent_run_id: event.parent_run_id,
				depth: null,
				total_batch_size: null,
				device_batch_size: null,
				embedding_lr: null,
				unembedding_lr: null,
				matrix_lr: null,
				scalar_lr: null,
				weight_decay: null,
				warmup_ratio: null,
				warmdown_ratio: null,
				final_lr_frac: null,
				adam_betas: null,
				window_pattern: null,
				aspect_ratio: null,
				head_dim: null,
				time_budget: null,
				num_params_m: null,
				total_tokens_m: null,
				num_steps: null,
				training_seconds: null,
				peak_vram_mb: null,
				mfu_percent: null,
				diff_patch: null,
				config: event.config
			};
			liveRun.steps = [];
			liveRun.notes = [];
		} else if (event.type === 'step') {
			liveRun.steps.push(event);
		} else if (event.type === 'run_end') {
			if (liveRun.run?.run_id === event.run_id) {
				liveRun.run = { ...liveRun.run, ...event, status: 'completed' } as any;
			}
		} else if (event.type === 'agent_note') {
			if (liveRun.run?.run_id === event.run_id) {
				liveRun.notes.push({ intent: event.intent, hypothesis: event.hypothesis });
			}
		} else if (event.type === 'accept_decision') {
			if (liveRun.run?.run_id === event.run_id) {
				liveRun.run = { ...liveRun.run, accepted: event.accepted ? 1 : 0 } as any;
			}
		}
	};

	return () => es.close();
}
