'use client'

import { Cloud, Pause, Play } from 'lucide-react'
import Link from 'next/link'
import { type CSSProperties, type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { Mark } from '@/components/brand'
import './views.css'

// The four NISAR views, read from public/layers/<site>/views.json (web/scripts/bake_views.py writes them). This page
// only shows them: every number on it is in that file, with the files it comes from.

type Source = string | { file: string; path: string }
type Num = { value: number | null; unit: string; what: string; source: Source[] }
type Nums = Record<string, Num>
type Pic = { file: string; bytes: number }
type Context = { text: string }
type SwipeItem = { date: string; nisar: Pic & { time_utc: string }; s1: Pic & { time_utc: string }; caption: string[] }
type CohItem = {
	date: string
	dark: Pic
	coh: Pic
	removed?: Pic
	photo: (Pic & { day: string; credit: string; scenes: string[] }) | null
	caption: string[]
}
type SoilPoint = { date: string; median: number; p90: number }
type Frame = Pic & { date: string; time_utc: string; numbers: Nums }
type Doc = {
	site: string
	width: number
	height: number
	baked_utc: string
	ground?: { file: string; credit: string } | null
	/** where a view may zoom first, as fractions of the picture: x0, y0, x1, y1 from the top left */
	focus?: { box: number[] } | null
	views: {
		swipe?: { title: string; what: string; items: SwipeItem[]; context: Context[] }
		coherence?: { title: string; what: string; items: CohItem[]; context: Context[] }
		soil?: {
			title: string
			what: string
			items: (Pic & { date: string })[]
			series: SoilPoint[]
			caption: string[]
			legend: { stops: { value: number; color: string }[]; alpha: number }
		}
		timeline?: { title: string; what: string; frames: Frame[]; caption: string[]; context?: Context[] }
	}
}

const NAMES = { albufera: 'Albufera', pego_oliva: 'Pego-Oliva', donana: 'Doñana' } as const
type Site = keyof typeof NAMES
type Docs = Partial<Record<Site, Doc>>
const ALL: readonly Site[] = ['pego_oliva', 'albufera', 'donana']
const MAP_SITES: readonly Site[] = ['pego_oliva', 'albufera']
const COH_SITES: readonly Site[] = ['donana', 'albufera']

// ---------------------------------------------------------------- data

const pending = new Map<Site, Promise<Doc>>()
function load(site: Site): Promise<Doc> {
	let p = pending.get(site)
	if (!p) {
		p = fetch(`/layers/${site}/views.json`).then((r) => {
			if (!r.ok) throw new Error(`${site}: views.json answered ${r.status}`)
			return r.json() as Promise<Doc>
		})
		pending.set(site, p)
	}
	return p
}

function useDocs(): Docs {
	const [docs, setDocs] = useState<Docs>({})
	useEffect(() => {
		let live = true
		for (const site of ALL) {
			load(site)
				.then((doc) => {
					if (live) setDocs((prev) => ({ ...prev, [site]: doc }))
				})
				.catch(() => {})
		}
		return () => {
			live = false
		}
	}, [])
	return docs
}

// Files are asked for with the time of their bake: the server keeps pictures for a year, so a new bake gets a new address.
const url = (doc: Doc, file: string) => `/layers/${doc.site}/${file}?v=${encodeURIComponent(doc.baked_utc)}`
// Dates are written as in the captions of views.json ("7 Sep", "28 Oct"), whatever the browser's locale.
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const day = (d: string) => `${Number(d.slice(8, 10))} ${MONTHS[Number(d.slice(5, 7)) - 1]}`
const clock = (t: string) => t.slice(11, 16)
const ha = (v: number | null | undefined) => (v == null ? '' : `${new Intl.NumberFormat('en-GB').format(Math.round(v))} ha`)
// as the captions round: 99.7 % stays 99.7 %, not 100 %
const pct = (v: number | null | undefined) => {
	if (v == null) return ''
	const p = v * 100
	return (p > 0 && p < 1) || (p > 99 && p < 100) ? `${p.toFixed(1)} %` : `${Math.round(p)} %`
}

// ---------------------------------------------------------------- pieces

function Layer({ doc, file, alt = '', style }: { doc: Doc; file: string; alt?: string; style?: CSSProperties }) {
	// eslint-disable-next-line @next/next/no-img-element
	return <img className="vw-layer" src={url(doc, file)} alt={alt} style={style} loading="lazy" decoding="async" draggable={false} />
}

/** Pictures that cover the same box, stacked. With a focus box (fractions of the picture) the stage shows only that
 *  part, at the same pixels; what sits on top of the pictures (tags, the swipe line) stays in stage coordinates. */
function Stage({ doc, focus, layers, children, whole, onWhole }: {
	doc?: Doc
	focus?: number[] | null
	layers?: ReactNode
	children?: ReactNode
	whole?: boolean
	onWhole?: (whole: boolean) => void
}) {
	const [x0, y0, x1, y1] = focus ?? [0, 0, 1, 1]
	const fw = x1 - x0
	const fh = y1 - y0
	const ar = doc ? (doc.width * fw) / (doc.height * fh) : 1
	const world: CSSProperties = { left: `${(-x0 / fw) * 100}%`, top: `${(-y0 / fh) * 100}%`, width: `${100 / fw}%`, height: `${100 / fh}%` }
	return (
		<div className="vw-stage" style={{ '--ar': ar } as CSSProperties} data-loading={doc ? undefined : ''}>
			{doc ? (
				<>
					<div className="vw-world" style={world}>
						{layers}
					</div>
					{children}
					{onWhole ? (
						<button type="button" className="vw-zoom" onClick={() => onWhole(!whole)}>
							{whole ? 'Zoom to the flood' : 'Whole site'}
						</button>
					) : null}
				</>
			) : null}
		</div>
	)
}

function Pills<T extends string>({ label, value, options, onChange }: {
	label: string
	value: T
	options: { id: T; label: string }[]
	onChange: (id: T) => void
}) {
	return (
		<div className="vw-pills" role="radiogroup" aria-label={label}>
			{options.map((o) => (
				<button key={o.id} type="button" role="radio" aria-checked={o.id === value} onClick={() => onChange(o.id)}>
					{o.label}
				</button>
			))}
		</div>
	)
}

function Legend({ items }: { items: { color: string; label: string }[] }) {
	return (
		<p className="vw-legend">
			{items.map((i) => (
				<span key={i.label}>
					<i style={{ background: i.color }} />
					{i.label}
				</span>
			))}
		</p>
	)
}

function View({ n, title, what, controls, caption, context, stage, below }: {
	n: number
	title: string
	what?: string
	controls?: ReactNode
	caption?: string[]
	context?: Context[]
	stage: ReactNode
	below?: ReactNode
}) {
	return (
		<section className="vw-view" aria-labelledby={`vw-h${n}`}>
			<div className="vw-text">
				<p className="vw-n mono">0{n}</p>
				<h2 id={`vw-h${n}`} className="display vw-h">
					{title}
				</h2>
				{what ? <p className="vw-what">{what}</p> : null}
				{controls ? <div className="vw-controls">{controls}</div> : null}
				{caption ? (
					<div className="vw-caption" aria-live="polite">
						{caption.map((line) => (
							<p key={line}>{line}</p>
						))}
					</div>
				) : null}
				{context?.length ? (
					<ul className="vw-context">
						{context.map((c) => (
							<li key={c.text}>{c.text}</li>
						))}
					</ul>
				) : null}
			</div>
			<div className="vw-figure">
				{stage}
				{below}
			</div>
		</section>
	)
}

const siteOptions = (sites: readonly Site[]) => sites.map((s) => ({ id: s, label: NAMES[s] }))

// ---------------------------------------------------------------- 1. Sentinel-1 against NISAR, the same evening

function SwipeView({ docs }: { docs: Docs }) {
	const [site, setSite] = useState<Site>('pego_oliva')
	const [date, setDate] = useState<string>('2026-10-28')
	const [pos, setPos] = useState(50)
	const [whole, setWhole] = useState(false)
	const doc = docs[site]
	const view = doc?.views.swipe
	const item = view?.items.find((x) => x.date === date) ?? view?.items.at(-1)
	const focus = whole ? null : doc?.focus?.box
	// the line sits at pos % of the stage; the pictures are clipped at the same place in their own coordinates
	const [fx0, , fx1] = focus ?? [0, 0, 1, 1]
	const cut = (fx0 + (pos / 100) * (fx1 - fx0)) * 100
	return (
		<View
			n={1}
			title={view?.title ?? 'Sentinel-1 against NISAR, the same evening'}
			what={view?.what}
			controls={
				<>
					<Pills label="Place" value={site} options={siteOptions(MAP_SITES)} onChange={setSite} />
					{view ? (
						<Pills label="Evening" value={item?.date ?? date} options={view.items.map((x) => ({ id: x.date, label: day(x.date) }))} onChange={setDate} />
					) : null}
				</>
			}
			caption={item?.caption}
			context={view?.context}
			stage={
				<Stage
					doc={doc}
					focus={focus}
					whole={whole}
					onWhole={doc?.focus ? setWhole : undefined}
					layers={
						doc && item ? (
							<>
								{doc.ground ? <Layer doc={doc} file={doc.ground.file} /> : null}
								<Layer doc={doc} file={item.s1.file} alt={`Sentinel-1 water map, ${day(item.date)}`} style={{ clipPath: `inset(0 ${100 - cut}% 0 0)` }} />
								<Layer doc={doc} file={item.nisar.file} alt={`NISAR water map, ${day(item.date)}`} style={{ clipPath: `inset(0 0 0 ${cut}%)` }} />
							</>
						) : null
					}
				>
					{doc && item ? (
						<>
							<input
								className="vw-range"
								type="range"
								min={0}
								max={100}
								step={0.5}
								value={pos}
								onChange={(e) => setPos(Number(e.target.value))}
								aria-label="Move the line: Sentinel-1 map on the left, NISAR map on the right"
							/>
							<div className="vw-handle" style={{ left: `${pos}%` }} aria-hidden>
								<span />
							</div>
							<span className="vw-tag vw-tag-left">
								Sentinel-1 <b className="mono">{clock(item.s1.time_utc)} UTC</b>
							</span>
							<span className="vw-tag vw-tag-right">
								NISAR <b className="mono">{clock(item.nisar.time_utc)} UTC</b>
							</span>
						</>
					) : null}
				</Stage>
			}
			below={
				<>
					<Legend items={[{ color: 'var(--vw-water)', label: 'Water' }, { color: 'var(--vw-unseen)', label: 'Not covered by that map' }]} />
					{doc?.ground ? <p className="vw-credit">Ground: {doc.ground.credit}.</p> : null}
				</>
			}
		/>
	)
}

// ---------------------------------------------------------------- 2. Coherence takes out the dry ground

function CoherenceView({ docs }: { docs: Docs }) {
	const [site, setSite] = useState<Site>('donana')
	const [on, setOn] = useState(false)
	const [showRemoved, setShowRemoved] = useState(false)
	const doc = docs[site]
	const view = doc?.views.coherence
	const item = view?.items[0]
	const options = COH_SITES.map((s) => {
		const d = docs[s]?.views.coherence?.items[0]?.date
		return { id: s, label: d ? `${NAMES[s]}, ${day(d)}` : NAMES[s] }
	})
	return (
		<View
			n={2}
			title={view?.title ?? 'Coherence takes out the dry ground'}
			what={view?.what}
			controls={
				<>
					<Pills label="Place" value={site} options={options} onChange={setSite} />
					<button type="button" className="vw-switch" role="switch" aria-checked={on} onClick={() => setOn((v) => !v)}>
						<i aria-hidden />
						Coherence {on ? 'on' : 'off'}
					</button>
					<label className="vw-check" data-off={on ? undefined : ''}>
						<input type="checkbox" checked={showRemoved} disabled={!on} onChange={(e) => setShowRemoved(e.target.checked)} />
						Show the dry ground it takes out
					</label>
				</>
			}
			caption={item?.caption}
			context={view?.context}
			stage={
				<Stage
					doc={doc}
					layers={
						doc && item ? (
							<>
								{item.photo ? <Layer doc={doc} file={item.photo.file} alt={`Sentinel-2 photo of ${day(item.photo.day)}`} /> : null}
								{on && showRemoved && item.removed ? <Layer doc={doc} file={item.removed.file} /> : null}
								<Layer
									doc={doc}
									file={on ? item.coh.file : item.dark.file}
									alt={on ? 'Dark pixels with low coherence, kept as water' : 'Every pixel the radar sees as dark as water'}
								/>
							</>
						) : null
					}
				>
					{doc && item ? (
						<>
							<span className="vw-tag vw-tag-left">{on ? 'Dark and low coherence' : 'Every dark pixel'}</span>
							{item.photo ? <span className="vw-tag vw-tag-right">Photo of {day(item.photo.day)}</span> : null}
						</>
					) : null}
				</Stage>
			}
			below={
				<>
					<Legend
						items={[
							{ color: 'var(--vw-water)', label: on ? 'Water: dark and low coherence' : 'Water by darkness alone' },
							...(on && showRemoved ? [{ color: 'var(--vw-removed)', label: 'Dry ground coherence takes out' }] : []),
						]}
					/>
					{item?.photo ? <p className="vw-credit">Photo: {item.photo.credit} ({item.photo.scenes.join(', ')}). Not retouched.</p> : null}
				</>
			}
		/>
	)
}

// ---------------------------------------------------------------- 3. Soil wetness before the storm

function SoilChart({ series, active }: { series: SoilPoint[]; active: string }) {
	const W = 320
	const H = 120
	const top = 0.4
	const t0 = Date.parse(series[0].date)
	const span = Date.parse(series[series.length - 1].date) - t0 || 1
	const x = (d: string) => 14 + ((Date.parse(d) - t0) / span) * (W - 28)
	const y = (v: number) => H - 18 - (Math.min(v, top) / top) * (H - 30)
	const last = series[series.length - 1].date
	return (
		<svg className="vw-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Median soil moisture of every pass, the last one before the storm marked">
			{[0, 0.2, 0.4].map((v) => (
				<g key={v}>
					<line x1={0} x2={W} y1={y(v)} y2={y(v)} className="vw-chart-grid" />
					<text x={W} y={y(v) - 3} textAnchor="end" className="vw-chart-tick">
						{v.toFixed(1)}
					</text>
				</g>
			))}
			{series.map((s) => (
				<rect
					key={s.date}
					x={x(s.date) - 5}
					y={y(s.median)}
					width={10}
					height={y(0) - y(s.median)}
					rx={2}
					className={s.date === last ? 'vw-bar vw-bar-last' : 'vw-bar'}
					data-active={s.date === active ? '' : undefined}
				>
					<title>{`${day(s.date)}: median ${s.median.toFixed(3)} m³/m³`}</title>
				</rect>
			))}
			<text x={x(series[0].date)} y={H - 4} className="vw-chart-tick">
				{day(series[0].date)}
			</text>
			<text x={x(last)} y={H - 4} textAnchor="end" className="vw-chart-tick">
				{day(last)}
			</text>
		</svg>
	)
}

function SoilView({ docs }: { docs: Docs }) {
	const [site, setSite] = useState<Site>('pego_oliva')
	const [date, setDate] = useState<string | null>(null)
	const doc = docs[site]
	const view = doc?.views.soil
	const item = view?.items.find((x) => x.date === date) ?? view?.items.at(-1)
	const stops = view?.legend.stops ?? []
	const lo = stops[0]?.value ?? 0
	const hi = stops[stops.length - 1]?.value ?? 1
	return (
		<View
			n={3}
			title={view?.title ?? 'Soil wetness before the storm'}
			what={view?.what}
			controls={
				<>
					<Pills label="Place" value={site} options={siteOptions(MAP_SITES)} onChange={setSite} />
					{view ? (
						<Pills label="Pass" value={item?.date ?? ''} options={view.items.map((x) => ({ id: x.date, label: day(x.date) }))} onChange={setDate} />
					) : null}
				</>
			}
			caption={view?.caption}
			stage={
				<Stage
					doc={doc}
					layers={
						doc && item ? (
							<>
								{doc.ground ? <Layer doc={doc} file={doc.ground.file} /> : null}
								<Layer doc={doc} file={item.file} alt={`NISAR soil moisture, ${day(item.date)}`} />
							</>
						) : null
					}
				>
					{doc && item ? (
						<>
							<span className="vw-tag vw-tag-left">
								Soil moisture <b className="mono">{day(item.date)}</b>
							</span>
						</>
					) : null}
				</Stage>
			}
			below={
				view ? (
					<div className="vw-soil-key">
						<div>
							<div
								className="vw-ramp"
								style={{ background: `linear-gradient(90deg, ${stops.map((s) => `${s.color} ${((s.value - lo) / (hi - lo)) * 100}%`).join(', ')})` }}
							/>
							<p className="vw-ticks mono">
								<span>{lo.toFixed(2)} dry</span>
								<span>m³/m³</span>
								<span>wet {hi.toFixed(2)}</span>
							</p>
						</div>
						<SoilChart series={view.series} active={item?.date ?? ''} />
					</div>
				) : null
			}
		/>
	)
}

// ---------------------------------------------------------------- 4. Water every 12 days, through cloud

function TimelineView({ docs }: { docs: Docs }) {
	const [site, setSite] = useState<Site>('pego_oliva')
	const [i, setI] = useState<number | null>(null)
	const [playing, setPlaying] = useState(false)
	const [whole, setWhole] = useState(false)
	const ref = useRef<HTMLDivElement>(null)
	const doc = docs[site]
	const view = doc?.views.timeline
	const frames = useMemo(() => view?.frames ?? [], [view])
	const k = i == null ? frames.length - 1 : Math.min(i, frames.length - 1)
	const frame = frames[k]

	// The frames are fetched once the view comes near, so the film plays without waiting.
	useEffect(() => {
		const el = ref.current
		if (!el || !doc || !frames.length) return
		const io = new IntersectionObserver(
			(entries) => {
				if (!entries.some((e) => e.isIntersecting)) return
				for (const f of frames) new Image().src = url(doc, f.file)
				io.disconnect()
			},
			{ rootMargin: '400px' },
		)
		io.observe(el)
		return () => io.disconnect()
	}, [doc, frames])

	useEffect(() => {
		if (!playing || !frames.length) return
		const id = window.setInterval(() => setI((prev) => ((prev ?? frames.length - 1) + 1) % frames.length), 900)
		return () => window.clearInterval(id)
	}, [playing, frames.length])

	const max = Math.max(1, ...frames.map((f) => f.numbers.water_ha.value ?? 0))
	const t0 = frames.length ? Date.parse(frames[0].date) : 0
	const span = frames.length ? Date.parse(frames[frames.length - 1].date) - t0 || 1 : 1
	const clear = frame?.numbers.optical_clear.value ?? 0
	return (
		<View
			n={4}
			title={view?.title ?? 'Water every 12 days, through cloud'}
			what={view?.what}
			controls={<Pills label="Place" value={site} options={siteOptions(MAP_SITES)} onChange={(s) => { setSite(s); setI(null) }} />}
			caption={view?.caption}
			context={view?.context}
			stage={
				<div ref={ref} className="vw-stage-wrap">
					<Stage
						doc={doc}
						focus={whole ? null : doc?.focus?.box}
						whole={whole}
						onWhole={doc?.focus ? setWhole : undefined}
						layers={
							doc && frame ? (
								<>
									{doc.ground ? <Layer doc={doc} file={doc.ground.file} /> : null}
									<Layer doc={doc} file={frame.file} alt={`NISAR water, ${day(frame.date)}`} />
								</>
							) : null
						}
					>
						{doc && frame ? (
							<>
								<span className="vw-tag vw-tag-left">
									NISAR <b className="mono">{day(frame.date)}, {clock(frame.time_utc)} UTC</b>
								</span>
							</>
						) : null}
					</Stage>
				</div>
			}
			below={
				frame ? (
					<div className="vw-film">
						<div className="vw-readout">
							<button type="button" className="vw-play" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play the passes'}>
								{playing ? <Pause size={18} /> : <Play size={18} />}
							</button>
							<p className="vw-big">
								<b className="mono">{ha(frame.numbers.water_ha.value)}</b>
								<span>
									of water on {day(frame.date)}. Radar saw {pct(frame.numbers.radar_saw.value)} of the land; optical, within a day,{' '}
									{pct(clear)} clear{clear < 0.5 ? <Cloud size={14} className="vw-cloud" aria-label="cloudy" /> : null}
								</span>
							</p>
						</div>
						<div className="vw-bars" role="group" aria-label="Passes, the height is the water">
							{frames.map((f, j) => (
								<button
									key={f.date}
									type="button"
									style={{ left: `${((Date.parse(f.date) - t0) / span) * 100}%`, '--h': (f.numbers.water_ha.value ?? 0) / max } as CSSProperties}
									aria-pressed={j === k}
									aria-label={`${day(f.date)}: ${ha(f.numbers.water_ha.value)}`}
									title={`${day(f.date)}: ${ha(f.numbers.water_ha.value)}`}
									onClick={() => {
										setPlaying(false)
										setI(j)
									}}
								>
									{(f.numbers.optical_clear.value ?? 0) < 0.5 ? <Cloud size={12} className="vw-cloud" aria-hidden /> : null}
									<i />
								</button>
							))}
						</div>
						<p className="vw-ticks mono">
							<span>{day(frames[0].date)}</span>
							<span>a cloud: optical saw less than half clear</span>
							<span>{day(frames[frames.length - 1].date)}</span>
						</p>
					</div>
				) : null
			}
		/>
	)
}

// ---------------------------------------------------------------- the page

export function ViewsDemo() {
	const docs = useDocs()
	return (
		<main className="vw">
			<header className="vw-head">
				<Link href="/" className="vw-brand">
					<Mark size={20} />
					Dancing with the SARs
				</Link>
				<h1 className="display vw-title">Where is NISAR?</h1>
				<p className="vw-lead">
					Four views of what only NISAR gives, baked from the radar data. A demo of the pictures and numbers for the final screens, not the screens
					themselves.
				</p>
			</header>
			<SwipeView docs={docs} />
			<CoherenceView docs={docs} />
			<SoilView docs={docs} />
			<TimelineView docs={docs} />
			<footer className="vw-foot">
				<p>
					Every picture and number on this page is in <code>public/layers/&lt;site&gt;/views.json</code>, with the files it comes from; made by{' '}
					<code>web/scripts/bake_views.py</code>.
				</p>
				<p>
					NISAR data: NASA and ISRO (L2 GCOV, GUNW and L3 SME2, provisional), from the ASF DAAC. Water maps: OPERA DSWx-S1 and DSWx-HLS (NASA JPL), from
					PO.DAAC. Photos: Copernicus Sentinel-2, Element 84 Earth Search. Ground: Sentinel-2 cloudless 2017 by EOX IT Services GmbH.
				</p>
				<p>Written with SI assistance (Claude Code), reviewed by the team.</p>
			</footer>
		</main>
	)
}
