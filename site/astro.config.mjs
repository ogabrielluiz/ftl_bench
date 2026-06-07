// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	// GitHub Pages (project site): served under https://ogabrielluiz.github.io/ftl_bench/
	site: 'https://ogabrielluiz.github.io',
	base: '/ftl_bench',
	integrations: [
		starlight({
			title: 'ftl_bench',
			description:
				'A game benchmark for LLM agents: evaluate your model or agent by having it play ' +
				'FTL: Faster Than Light through a clean, intent-level interface.',
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/ogabrielluiz/ftl_bench' },
			],
			sidebar: [
				{
					label: 'Introduction',
					items: [
						{ label: 'The benchmark', slug: 'introduction/the-benchmark' },
						{ label: 'How scoring works', slug: 'introduction/scoring' },
					],
				},
				{
					label: 'Evaluate your model',
					items: [
						{ label: 'Quickstart', slug: 'evaluate/quickstart' },
						{ label: 'Bring your model or agent', slug: 'evaluate/bring-your-model' },
						{ label: 'Running & results', slug: 'evaluate/running' },
					],
				},
				{
					label: 'Install the game',
					items: [
						{ label: 'PC — native x86 (recommended)', slug: 'install/pc', badge: 'recommended' },
						{ label: 'macOS — Rosetta', slug: 'install/macos' },
					],
				},
				{
					label: 'Reference',
					items: [
						{ label: 'Observation schema', slug: 'reference/observation' },
						{ label: 'Action set', slug: 'reference/actions' },
						{ label: 'Play-to-game-over mode', slug: 'reference/play-to-gameover' },
					],
				},
				{
					label: 'Project',
					items: [
						{ label: 'Architecture', slug: 'project/architecture' },
						{ label: 'Results & baselines', slug: 'project/status' },
					],
				},
			],
		}),
	],
});
