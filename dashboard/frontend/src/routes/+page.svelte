<script lang="ts">
	import { onMount } from 'svelte';
	import { liveRun, connectSSE } from '$lib/stores.svelte';
	import LossChart from '$lib/components/LossChart.svelte';

	onMount(() => {
		const disconnect = connectSSE();
		return disconnect;
	});

	let lastStep = $derived(liveRun.steps.at(-1));

	let configEntries = $derived.by(() => {
		const cfg = liveRun.run?.config;
		if (!cfg) return [];
		return Object.entries(cfg);
	});

	function statusLabel(): string {
		if (!liveRun.run) return 'idle';
		if (liveRun.run.accepted === 1) return 'accepted';
		if (liveRun.run.accepted === 0) return 'rejected';
		return liveRun.run.status;
	}

	function statusClass(): string {
		if (!liveRun.run) return '';
		if (liveRun.run.accepted === 1) return 'accepted';
		if (liveRun.run.accepted === 0) return 'rejected';
		if (liveRun.run.status === 'failed') return 'failed';
		return 'running';
	}
</script>

<div class="live-view">
	<!-- Status Bar -->
	<section class="status-bar">
		<div class="status-left">
			{#if liveRun.run}
				<span class="iteration">Iteration {liveRun.run.iteration}</span>
				<span class="run-id">{liveRun.run.run_id}</span>
				<span class="badge {statusClass()}">{statusLabel()}</span>
			{:else}
				<span class="iteration">No active run</span>
				<span class="hint">Waiting for SSE events...</span>
			{/if}
		</div>
		{#if lastStep}
			<div class="progress-wrap">
				<div class="progress-bar">
					<div class="progress-fill" style="width: {Math.min(lastStep.pct_done, 100)}%"></div>
				</div>
				<span class="pct">{lastStep.pct_done.toFixed(1)}%</span>
			</div>
		{/if}
	</section>

	{#if liveRun.run}
		<!-- Config Table -->
		{#if configEntries.length > 0}
			<section class="card">
				<h3>Hyperparameters</h3>
				<div class="config-grid">
					{#each configEntries as [key, val]}
						<div class="config-item">
							<span class="config-key">{key}</span>
							<span class="config-val">{JSON.stringify(val)}</span>
						</div>
					{/each}
				</div>
			</section>
		{/if}

		<!-- Loss Chart -->
		<section class="card">
			<h3>Loss</h3>
			<LossChart steps={liveRun.steps} />
		</section>

		<!-- Throughput Row -->
		{#if lastStep}
			<section class="stat-tiles">
				<div class="tile">
					<span class="tile-label">tok/sec</span>
					<span class="tile-value">{lastStep.tok_per_sec.toLocaleString()}</span>
				</div>
				<div class="tile">
					<span class="tile-label">lr mult</span>
					<span class="tile-value">{lastStep.lrm.toFixed(3)}</span>
				</div>
				<div class="tile">
					<span class="tile-label">epoch</span>
					<span class="tile-value">{lastStep.epoch}</span>
				</div>
				<div class="tile">
					<span class="tile-label">step</span>
					<span class="tile-value">{lastStep.step}</span>
				</div>
				<div class="tile">
					<span class="tile-label">wall time</span>
					<span class="tile-value">{lastStep.wall_time.toFixed(1)}s</span>
				</div>
			</section>
		{/if}

		<!-- Agent Reasoning Log -->
		{#if liveRun.notes.length > 0}
			<section class="card">
				<h3>Agent Reasoning</h3>
				<div class="notes-log">
					{#each liveRun.notes as note, i (i)}
						<div class="note">
							<div class="note-intent">{note.intent}</div>
							<div class="note-hypothesis">{note.hypothesis}</div>
						</div>
					{/each}
				</div>
			</section>
		{/if}
	{/if}
</div>

<style>
	.live-view {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.status-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem 1.25rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		box-shadow: var(--shadow-sm);
		flex-wrap: wrap;
	}
	.status-left {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	.iteration {
		font-size: 1.3rem;
		font-weight: 700;
		letter-spacing: -0.02em;
		color: var(--text);
	}
	.run-id {
		font-family: var(--font-mono);
		font-size: 0.8rem;
		color: var(--text-dim);
		background: var(--bg-hover);
		padding: 0.15rem 0.5rem;
		border-radius: var(--radius-sm);
	}
	.hint {
		color: var(--text-dim);
		font-size: 0.85rem;
	}
	.badge {
		padding: 0.2rem 0.6rem;
		border-radius: var(--radius-sm);
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.badge.running { background: var(--amber-bg); color: var(--amber); }
	.badge.completed { background: var(--accent-light); color: var(--accent); }
	.badge.accepted { background: var(--green-bg); color: var(--green); }
	.badge.rejected { background: var(--red-bg); color: var(--red); }
	.badge.failed { background: var(--red-bg); color: var(--red); }

	.progress-wrap {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		min-width: 220px;
	}
	.progress-bar {
		flex: 1;
		height: 6px;
		background: var(--bg-hover);
		border-radius: 3px;
		overflow: hidden;
	}
	.progress-fill {
		height: 100%;
		background: var(--accent);
		border-radius: 3px;
		transition: width 0.3s ease;
	}
	.pct {
		font-family: var(--font-mono);
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--text-secondary);
		min-width: 3.5rem;
		text-align: right;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 1.25rem;
		box-shadow: var(--shadow-sm);
	}
	.card h3 {
		font-size: 0.7rem;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 600;
		margin-bottom: 0.75rem;
	}

	.config-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: 0.5rem;
	}
	.config-item {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		padding: 0.5rem 0.6rem;
		background: var(--bg-subtle);
		border-radius: var(--radius-sm);
	}
	.config-key {
		font-size: 0.7rem;
		color: var(--text-dim);
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.config-val {
		font-family: var(--font-mono);
		font-size: 0.82rem;
		font-weight: 500;
		color: var(--text);
	}

	.stat-tiles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		gap: 0.75rem;
	}
	.tile {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 0.85rem 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		box-shadow: var(--shadow-sm);
		transition: box-shadow 0.15s ease;
	}
	.tile:hover {
		box-shadow: var(--shadow-md);
	}
	.tile-label {
		font-size: 0.7rem;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-weight: 500;
	}
	.tile-value {
		font-family: var(--font-mono);
		font-size: 1.15rem;
		font-weight: 600;
		color: var(--text);
		letter-spacing: -0.02em;
	}

	.notes-log {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-height: 300px;
		overflow-y: auto;
	}
	.note {
		padding: 0.6rem 0.85rem;
		background: var(--bg-subtle);
		border-radius: var(--radius-sm);
		border-left: 3px solid var(--accent);
	}
	.note-intent {
		font-weight: 600;
		font-size: 0.85rem;
		color: var(--text);
	}
	.note-hypothesis {
		font-size: 0.8rem;
		color: var(--text-secondary);
		margin-top: 0.2rem;
		line-height: 1.45;
	}
</style>
