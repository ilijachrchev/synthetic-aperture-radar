// The rain slider of the model view: one stop per rain the model was run with (prediction.json). Dragging between
// two stops crossfades their maps on the map; letting go settles on the nearest stop, so every number on the page
// belongs to a map the model made. It moves its own handle, so a drag never redraws the page.

import { useCallback, useEffect, useRef } from 'react'

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x))
const SETTLE_MS = 380

export function RainSlider({
	stops,
	index,
	onInput,
	onStop,
	label = 'Rain',
}: {
	/** `sub` is a second, smaller line over the stop (what that rain changes) */
	stops: { label: string; sub?: string; warn?: boolean }[]
	/** the stop chosen from outside (a key, a script): the handle glides there */
	index: number
	/** every move of the handle, as a position from 0 to stops - 1 */
	onInput: (pos: number) => void
	/** the stop nearest the handle, when it changes */
	onStop: (i: number) => void
	label?: string
}) {
	const track = useRef<HTMLDivElement>(null)
	const thumb = useRef<HTMLDivElement>(null)
	const pos = useRef(index)
	const near = useRef(index)
	const anim = useRef(0)
	const n = stops.length

	const place = useCallback(
		(p: number) => {
			pos.current = p
			if (thumb.current) thumb.current.style.left = `${(n > 1 ? p / (n - 1) : 0) * 100}%`
			onInput(p)
			const i = Math.round(p)
			if (i !== near.current) {
				near.current = i
				onStop(i)
			}
		},
		[n, onInput, onStop],
	)

	/** glide to a stop */
	const settle = useCallback(
		(to: number) => {
			cancelAnimationFrame(anim.current)
			const from = pos.current
			if (Math.abs(from - to) < 1e-4) return place(to)
			const t0 = performance.now()
			const step = (now: number) => {
				const k = clamp((now - t0) / SETTLE_MS, 0, 1)
				const e = 1 - (1 - k) ** 3
				place(from + (to - from) * e)
				if (k < 1) anim.current = requestAnimationFrame(step)
			}
			anim.current = requestAnimationFrame(step)
		},
		[place],
	)

	// a stop chosen from outside; the stops this slider reports itself come back here as `index` and are left alone
	useEffect(() => {
		if (index !== near.current) {
			near.current = index
			settle(index)
		}
	}, [index, settle])
	useEffect(() => () => cancelAnimationFrame(anim.current), [])
	useEffect(() => {
		if (thumb.current) thumb.current.style.left = `${(n > 1 ? pos.current / (n - 1) : 0) * 100}%`
	}, [n])

	const at = (clientX: number) => {
		const r = track.current!.getBoundingClientRect()
		return clamp(((clientX - r.left) / Math.max(1, r.width)) * (n - 1), 0, n - 1)
	}
	const down = (e: React.PointerEvent<HTMLDivElement>) => {
		cancelAnimationFrame(anim.current)
		place(at(e.clientX))
		const move = (ev: PointerEvent) => place(at(ev.clientX))
		const up = () => {
			window.removeEventListener('pointermove', move)
			window.removeEventListener('pointerup', up)
			settle(Math.round(pos.current))
		}
		window.addEventListener('pointermove', move)
		window.addEventListener('pointerup', up)
		e.preventDefault()
	}
	const key = (e: React.KeyboardEvent<HTMLDivElement>) => {
		const dir = e.key === 'ArrowRight' || e.key === 'ArrowUp' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowDown' ? -1 : 0
		if (!dir) return
		e.preventDefault()
		e.stopPropagation()
		settle(clamp(Math.round(pos.current) + dir, 0, n - 1))
	}

	return (
		<div className="rs">
			<span className="rs-name">{label}</span>
			<div
				ref={track}
				className="rs-track"
				onPointerDown={down}
				onKeyDown={key}
				role="slider"
				tabIndex={0}
				aria-label={label}
				aria-valuemin={0}
				aria-valuemax={n - 1}
				aria-valuenow={index}
				aria-valuetext={stops[index]?.label}
			>
				<i className="rs-rail" />
				{stops.map((s, i) => (
					<button
						key={s.label}
						type="button"
						className="rs-stop"
						data-on={i === index || undefined}
						data-warn={s.warn || undefined}
						style={{ left: `${(n > 1 ? i / (n - 1) : 0) * 100}%` }}
						onPointerDown={(e) => e.stopPropagation()}
						onClick={() => settle(i)}
						tabIndex={-1}
					>
						{s.sub && <em>{s.sub}</em>}
						<small>{s.label}</small>
					</button>
				))}
				<div ref={thumb} className="rs-thumb" />
			</div>
		</div>
	)
}
