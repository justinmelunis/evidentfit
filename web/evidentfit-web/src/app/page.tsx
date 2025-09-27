import Link from 'next/link'

export default function Home() {
  return (
    <main className="max-w-4xl mx-auto p-8">
      <h1 className="text-4xl font-bold mb-8 text-center">EvidentFit</h1>
      <p className="text-xl text-gray-600 text-center mb-12">
        Evidence-based supplement guidance for strength athletes
      </p>
      
      <div className="grid md:grid-cols-2 gap-8">
        <Link href="/agent" className="block">
          <div className="border rounded-lg p-6 hover:shadow-lg transition-shadow">
            <h2 className="text-2xl font-semibold mb-4">💬 Chat Assistant</h2>
            <p className="text-gray-600 mb-4">
              Ask questions about supplements, get evidence-based answers with citations.
            </p>
            <div className="text-blue-600 font-medium">Start Chatting →</div>
          </div>
        </Link>
        
        <Link href="/stack" className="block">
          <div className="border rounded-lg p-6 hover:shadow-lg transition-shadow">
            <h2 className="text-2xl font-semibold mb-4">🎯 Stack Planner</h2>
            <p className="text-gray-600 mb-4">
              Get personalized supplement recommendations based on your goals and profile.
            </p>
            <div className="text-blue-600 font-medium">Plan My Stack →</div>
          </div>
        </Link>
      </div>
      
      <div className="mt-12 text-center">
        <p className="text-sm text-gray-500">
          Educational only; not medical advice.
        </p>
      </div>
    </main>
  )
}
