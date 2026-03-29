<script lang="ts">
	import { onMount } from 'svelte';
	import { Chart, LineController, LineElement, PointElement, LinearScale, Tooltip } from 'chart.js';
	import type { Run } from '$lib/types';
	import { fetchRuns, fetchDiff } from '$lib/api';
	import RunTable from '$lib/components/RunTable.svelte';
	import DiffViewer from '$lib/components/DiffViewer.svelte';
	import LineageGraph from '$lib/components/LineageGraph.svelte';

	Chart.register(LineController, LineElement, PointElement, LinearScale, Tooltip);

	let runs: Run[] = $state([]);
	let selectedRun: Run | null = $state(null);
	let selectedDiff: string = $state('');
	let bpbCanvas: HTMLCanvasElement;
	let bpbChart: Chart | null = null;

	onMount(async () => {
		runs = await fetchRuns();
		buildBpbChart();
		return () => bpbChart?.destroy();
	});

	async function selectRun(run: Run) {
		selectedRun = run;
		selectedDiff = '';
		const diff = await fetchDiff(run.run_id);
		selectedDiff = diff;
	}

	function buildBpbChart() {
		if (!bpbCanvas || runs.length === 0) return;

		const sorted = [...runs].sort((a, b) => a.iteration - b.iteration);

		const accepted = sorted.filter(r => r.val_bpb != null && r.accepted === 1);
		const rejected = sorted.filter(r => r.val_bpb != null && r.accepted !== 1);

		bpbChart = new Chart(bpbCanvas, {
			type: 'line',
			data: {
				datasets: [
					{
						label: 'Accepted',
						data: accepted.map(r => ({ x: r.iteration, y: r.val_bpb! })),
						borderColor: '#16A34A',
						backgroundColor: '#16A34A',
						pointRadius: 5,
						pointHoverRadius: 7,
						pointStyle: 'circle',
						showLine: true,
						borderWidth: 2,
						tension: 0.2,
						fill: false,
					},
					{
						label: 'Rejected',
						data: rejected.map(r => ({ x: r.iteration, y: r.val_bpb! })),
						borderColor: 'transparent',
						backgroundColor: 'rgba(220, 38, 38, 0.35)',
						pointRadius: 4,
						pointHoverRadius: 6,
						pointStyle: 'circle',
						showLine: false,
						fill: false,
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				animation: false,
				scales: {
					x: {
						type: 'linear',
						title: { display: true, text: 'Iteration', color: '#A8A29E', font: { family: "'DM Sans', sans-serif", size: 11, weight: '500' } },
						ticks: { color: '#A8A29E', font: { family: "'JetBrains Mono', monospace", size: 10 }, stepSize: 1 },
						grid: { color: 'rgba(228, 226, 219, 0.6)' },
						border: { color: '#E4E2DB' }
					},
					y: {
						title: { display: true, text: 'val_bpb', color: '#A8A29E', font: { family: "'DM Sans', sans-serif", size: 11, weight: '500' } },
						ticks: { color: '#A8A29E', font: { family: "'JetBrains Mono', monospace", size: 10 } },
						grid: { color: 'rgba(228, 226, 219, 0.6)' },
						border: { color: '#E4E2DB' }
					}
				},
				plugins: {
					tooltip: {
						backgroundColor: '#1C1917',
						titleColor: '#FAFAF9',
						bodyColor: '#E7E5E4',
						borderColor: '#44403C',
						borderWidth: 1,
						cornerRadius: 6,
						padding: 10,
						titleFont: { family: "'DM Sans', sans-serif", weight: '600', size: 12 },
						bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
						callbacks: {
							label: (ctx) => {
								const ds = ctx.dataset.label;
								return `${ds}: ${ctx.parsed.y.toFixed(6)}`;
							}
						}
					}
				},
				onClick: (_evt, elements) => {
					if (elements.length > 0) {
						const idx = elements[0].index;
						const dsIdx = elements[0].datasetIndex;
						const point = bpbChart!.data.datasets[dsIdx].data[idx] as { x: number; y: number };
						const run = runs.find(r => r.iteration === point.x);
						if (run) selectRun(run);
					}
				}
			}
		});
	}

	let selectedNotes = $derived.by(() => {
		if (!selectedRun) return [];
		return [];
	});

	let hyperparamKeys = $derived.by(() => {
		if (!selectedRun) return [];
		const keys: [string, unknown][] = [
			['depth', selectedRun.depth],
			['total_batch_size', selectedRun.total_batch_size],
			['device_batch_size', selectedRun.device_batch_size],
			['embedding_lr', selectedRun.embedding_lr],
			['unembedding_lr', selectedRun.unembedding_lr],
			['matrix_lr', selectedRun.matrix_lr],
			['scalar_lr', selectedRun.scalar_lr],
			['weight_decay', selectedRun.weight_decay],
			['warmup_ratio', selectedRun.warmup_ratio],
			['warmdown_ratio', selectedRun.warmdown_ratio],
			['final_lr_frac', selectedRun.final_lr_frac],
			['adam_betas', selectedRun.adam_betas],
			['window_pattern', selectedRun.window_pattern],
			['aspect_ratio', selectedRun.aspect_ratio],
			['head_dim', selectedRun.head_dim],
			['time_budget', selectedRun.time_budget],
		];
		return keys;
	});
</script>

<div class="history-view">
	<!-- BPB Trajectory -->
	<section class="card">
		<h3>BPB Trajectory</h3>
		<div class="chart-container">
			<canvas bind:this={bpbCanvas}></canvas>
		</div>
	</section>

	<!-- Run Table -->
	<section class="card">
		<h3>All Runs ({runs.length})</h3>
		<RunTable {runs} onSelect={selectRun} />
	</section>

	<!-- Run Detail Panel -->
	{#if selectedRun}
		<section class="card detail-panel">
			<div class="detail-header">
				<h3>Run #{selectedRun.iteration} &mdash; <span class="run-id-inline">{selectedRun.run_id}</span></h3>
				<button onclick={() => (selectedRun = null)} class="close-btn">&times;</button>
			</div>

			<!-- Lineage -->
			<div class="detail-section">
				<h4>Lineage</h4>
				<LineageGraph run={selectedRun} allRuns={runs} />
			</div>

			<!-- Summary -->
			<div class="detail-section">
				<h4>Summary</h4>
				<div class="summary-grid">
					<div class="summary-item"><span class="dim">val_bpb</span> <span class="mono">{selectedRun.val_bpb?.toFixed(6) ?? '-'}</span></div>
					<div class="summary-item"><span class="dim">params</span> <span class="mono">{selectedRun.num_params_m?.toFixed(1) ?? '-'}M</span></div>
					<div class="summary-item"><span class="dim">steps</span> <span class="mono">{selectedRun.num_steps ?? '-'}</span></div>
					<div class="summary-item"><span class="dim">time</span> <span class="mono">{selectedRun.training_seconds?.toFixed(1) ?? '-'}s</span></div>
					<div class="summary-item"><span class="dim">vram</span> <span class="mono">{selectedRun.peak_vram_mb?.toFixed(0) ?? '-'}MB</span></div>
					<div class="summary-item"><span class="dim">mfu</span> <span class="mono">{selectedRun.mfu_percent?.toFixed(2) ?? '-'}%</span></div>
				</div>
			</div>

			<!-- Hyperparameters -->
			<div class="detail-section">
				<h4>Hyperparameters</h4>
				<div class="config-grid">
					{#each hyperparamKeys as [key, val]}
						<div class="config-item">
							<span class="config-key">{key}</span>
							<span class="config-val mono">{val ?? '-'}</span>
						</div>
					{/each}
				</div>
			</div>

			<!-- Diff -->
			<div class="detail-section">
				<h4>Diff vs Parent</h4>
				<DiffViewer diff={selectedDiff} />
			</div>
		</section>
	{/if}
</div>

<style>
	.history-view {
		display: flex;
		flex-direction: column;
		gap: 1rem;
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
	.run-id-inline {
		font-family: var(--font-mono);
		font-weight: 400;
		opacity: 0.6;
	}
	.chart-container {
		position: relative;
		height: 260px;
	}
	.detail-panel {
		border-color: var(--accent);
		border-width: 1px;
		box-shadow: var(--shadow-md), 0 0 0 3px var(--accent-light);
	}
	.detail-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.close-btn {
		background: none;
		border: 1px solid var(--border);
		color: var(--text-dim);
		font-size: 1.2rem;
		cursor: pointer;
		padding: 0;
		width: 28px;
		height: 28px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-sm);
		transition: all 0.15s ease;
		line-height: 1;
	}
	.close-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
		border-color: var(--border-strong);
	}
	.detail-section {
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid var(--border);
	}
	.detail-section h4 {
		font-size: 0.7rem;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 600;
		margin-bottom: 0.6rem;
	}
	.summary-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		gap: 0.5rem;
	}
	.summary-item {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		padding: 0.5rem 0.6rem;
		background: var(--bg-subtle);
		border-radius: var(--radius-sm);
	}
	.dim { font-size: 0.7rem; color: var(--text-dim); font-weight: 500; text-transform: uppercase; letter-spacing: 0.03em; }
	.mono { font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500; color: var(--text); }

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
		font-size: 0.85rem;
	}
</style>
