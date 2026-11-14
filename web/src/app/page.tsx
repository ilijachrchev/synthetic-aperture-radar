import { Hero } from '@/components/hero'
import { PassScrubber } from '@/components/pass-scrubber'
import { Closing, Data, Footer, How, Stories } from '@/components/sections'
import { imaged } from '@/lib/radar'

export default function Home() {
	return (
		<main className="grain min-h-svh">
			<Hero />
			<Stories />
			<PassScrubber passes={imaged('valencia', '066')} />
			<How />
			<Data />
			<Closing />
			<Footer />
		</main>
	)
}
