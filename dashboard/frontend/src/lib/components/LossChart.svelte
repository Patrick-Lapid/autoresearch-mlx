<script lang="ts">
	import { onMount } from 'svelte';
	import type { StepEvent } from '$lib/types';
	import { Chart, LineController, LineElement, PointElement, LinearScale, Tooltip, Filler } from 'chart.js';

	Chart.register(LineController, LineElement, PointElement, LinearScale, Tooltip, Filler);

	let { steps = [] }: { steps: StepEvent[] } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;
	let lastLen = 0;

	onMount(() => {
		chart = new Chart(canvas, {
			type: 'line',
			data: {
				datasets: [
					{
						label: 'Loss',
						data: [],
						borderColor: 'rgba(59, 91, 219, 0.2)',
						borderWidth: 1,
						pointRadius: 0,
						tension: 0,
						fill: false,
					},
					{
						label: 'Smooth Loss',
						data: [],
						borderColor: '#3B5BDB',
						borderWidth: 2,
						pointRadius: 0,
						tension: 0.3,
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
						title: { display: true, text: 'Step', color: '#A8A29E', font: { family: "'DM Sans', sans-serif", size: 11, weight: '500' } },
						ticks: { color: '#A8A29E', font: { family: "'JetBrains Mono', monospace", size: 10 } },
						grid: { color: 'rgba(228, 226, 219, 0.6)' },
						border: { color: '#E4E2DB' }
					},
					y: {
						title: { display: true, text: 'Loss', color: '#A8A29E', font: { family: "'DM Sans', sans-serif", size: 11, weight: '500' } },
						ticks: { color: '#A8A29E', font: { family: "'JetBrains Mono', monospace", size: 10 } },
						grid: { color: 'rgba(228, 226, 219, 0.6)' },
						border: { color: '#E4E2DB' }
					}
				},
				plugins: {
					tooltip: {
						mode: 'index',
						intersect: false,
						backgroundColor: '#1C1917',
						titleColor: '#FAFAF9',
						bodyColor: '#E7E5E4',
						borderColor: '#44403C',
						borderWidth: 1,
						cornerRadius: 6,
						padding: 10,
						titleFont: { family: "'DM Sans', sans-serif", weight: '600', size: 12 },
						bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
					}
				}
			}
		});

		return () => chart?.destroy();
	});

	$effect(() => {
		if (!chart || steps.length === lastLen) return;

		const newSteps = steps.slice(lastLen);
		for (const s of newSteps) {
			chart.data.datasets[0].data.push({ x: s.step, y: s.loss });
			chart.data.datasets[1].data.push({ x: s.step, y: s.smooth_loss });
		}
		lastLen = steps.length;
		chart.update('none');
	});
</script>

<div class="chart-container">
	<canvas bind:this={canvas}></canvas>
</div>

<style>
	.chart-container {
		position: relative;
		height: 300px;
		width: 100%;
	}
</style>
