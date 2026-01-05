import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import Link from 'next/link'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'EvidentFit',
  description: 'Evidence-based fitness supplement guidance',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        {/* Global Navigation */}
        <nav className="bg-white border-b border-gray-200">
          <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
            <Link href="/" className="text-xl font-bold text-gray-900 hover:text-blue-600 transition-colors">
              EvidentFit
            </Link>
          <div className="flex gap-6">
            <Link href="/agent" className="text-gray-600 hover:text-blue-600 font-medium transition-colors">
              Research Chat
            </Link>
            <Link href="/stack-chat" className="text-gray-600 hover:text-blue-600 font-medium transition-colors">
              Stack Planner
            </Link>
            <Link href="/supplements" className="text-gray-600 hover:text-blue-600 font-medium transition-colors">
              Supplements
            </Link>
            <Link href="/methodology" className="text-gray-600 hover:text-blue-600 font-medium transition-colors">
              Methodology
            </Link>
          </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  )
}
