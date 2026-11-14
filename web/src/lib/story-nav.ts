// Where the reader is on the landing (-1 the overview, 0 to 3 a story playing in the monitor), shared between the
// stories, which know it, and the pill navbar, which shows it and can jump to a story. Client only.
type Listener = () => void

let active = -1
const listeners = new Set<Listener>()
let jump: (i: number) => void = (i) => {
	if (i < 0) window.scrollTo({ top: 0, behavior: 'smooth' })
}

export const storyNav = {
	get: () => active,
	set(i: number) {
		if (i === active) return
		active = i
		listeners.forEach((f) => f())
	},
	subscribe(f: Listener) {
		listeners.add(f)
		return () => {
			listeners.delete(f)
		}
	},
	/** go to a story (or -1 for the top); the stories register how */
	go: (i: number) => jump(i),
	register(f: (i: number) => void) {
		jump = f
	},
}
