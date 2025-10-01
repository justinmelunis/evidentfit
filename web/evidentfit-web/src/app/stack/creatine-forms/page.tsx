'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'

type CreatineForm = {
  form: string
  base_fraction: number
  cme_factor: number
  evidence_grade: string
  pros: string[]
  cons: string[]
  notes: string[]
  recommended_for?: string
}

type CreatineFormsResponse = {
  [key: string]: CreatineForm
}

export default function CreatineFormsPage() {
  const [forms, setForms] = useState<CreatineFormsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const fetchForms = async () => {
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io'
        
        const response = await fetch(`${apiBase}/stack/creatine-forms`, {
          headers: {
            'Authorization': 'Basic ' + btoa('demo:demo123')
          }
        })
        
        if (!response.ok) {
          throw new Error('Failed to fetch creatine forms')
        }
        
        const data = await response.json()
        setForms(data)
      } catch (err: any) {
        setError(err.message || 'An error occurred')
      } finally {
        setLoading(false)
      }
    }

    fetchForms()
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-xl text-gray-600">Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-xl text-red-600">Error: {error}</div>
      </div>
    )
  }

  const formOrder = ['monohydrate', 'anhydrous', 'hcl', 'ethyl-ester', 'buffered']
  const orderedForms = formOrder
    .filter(key => forms && forms[key])
    .map(key => ({ key, ...forms![key] }))

  const getGradeColor = (grade: string) => {
    switch (grade) {
      case 'A': return 'bg-green-100 text-green-800 border-green-300'
      case 'B': return 'bg-blue-100 text-blue-800 border-blue-300'
      case 'C': return 'bg-yellow-100 text-yellow-800 border-yellow-300'
      case 'D': return 'bg-red-100 text-red-800 border-red-300'
      default: return 'bg-gray-100 text-gray-800 border-gray-300'
    }
  }

  const getFormLabel = (key: string) => {
    return key.split('-').map(word => 
      word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto p-6">
        <div className="mb-8">
          <Link href="/stack" className="text-blue-600 hover:text-blue-800 font-medium">
            ← Back to Stack Planner
          </Link>
          <h1 className="text-4xl font-bold text-gray-900 mt-4">Creatine Forms Comparison</h1>
          <p className="text-gray-600 mt-2">Evidence-based comparison of different creatine forms</p>
        </div>

        {/* Quick Summary */}
        <div className="bg-blue-50 border-2 border-blue-200 rounded-lg p-6 mb-8">
          <h2 className="text-xl font-bold text-blue-900 mb-3">📋 Quick Recommendation</h2>
          <p className="text-blue-800 mb-2">
            <strong>Creatine Monohydrate</strong> is the gold standard with the most research support. 
            Choose it unless you have specific tolerance issues.
          </p>
          <p className="text-blue-700 text-sm">
            All dosing is expressed in <strong>CME (Creatine Monohydrate Equivalent)</strong> to ensure 
            you get the same effective dose regardless of form chosen.
          </p>
        </div>

        {/* Forms Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {orderedForms.map(({ key, form, base_fraction, cme_factor, evidence_grade, pros, cons, notes, recommended_for }) => (
            <div 
              key={key} 
              className={`bg-white rounded-lg shadow-md overflow-hidden border-2 ${
                key === 'monohydrate' ? 'border-green-500' : 'border-gray-200'
              }`}
            >
              {/* Header */}
              <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h3 className="text-2xl font-bold text-gray-900 capitalize">
                    {getFormLabel(key)}
                    {key === 'monohydrate' && (
                      <span className="ml-2 text-sm font-normal text-green-600">⭐ Recommended</span>
                    )}
                  </h3>
                  <span className={`px-3 py-1 rounded-full text-sm font-bold border-2 ${getGradeColor(evidence_grade)}`}>
                    Grade {evidence_grade}
                  </span>
                </div>
              </div>

              {/* Content */}
              <div className="p-6">
                {/* CME Info */}
                <div className="mb-4 p-3 bg-gray-50 rounded-md">
                  <div className="text-sm text-gray-600 mb-1">Creatine Content</div>
                  <div className="font-semibold text-gray-900">
                    {(base_fraction * 100).toFixed(1)}% creatine base
                  </div>
                  <div className="text-sm text-gray-600 mt-1">
                    CME factor: {cme_factor.toFixed(3)}x
                  </div>
                </div>

                {/* Pros */}
                <div className="mb-4">
                  <h4 className="font-semibold text-gray-900 mb-2 flex items-center">
                    <span className="text-green-600 mr-2">✓</span> Pros
                  </h4>
                  <ul className="space-y-1">
                    {pros.map((pro, i) => (
                      <li key={i} className="text-sm text-gray-700 ml-6">• {pro}</li>
                    ))}
                  </ul>
                </div>

                {/* Cons */}
                <div className="mb-4">
                  <h4 className="font-semibold text-gray-900 mb-2 flex items-center">
                    <span className="text-red-600 mr-2">✗</span> Cons
                  </h4>
                  <ul className="space-y-1">
                    {cons.map((con, i) => (
                      <li key={i} className="text-sm text-gray-700 ml-6">• {con}</li>
                    ))}
                  </ul>
                </div>

                {/* Notes */}
                {notes.length > 0 && (
                  <div className="mb-4">
                    <h4 className="font-semibold text-gray-900 mb-2">Notes</h4>
                    <ul className="space-y-1">
                      {notes.map((note, i) => (
                        <li key={i} className="text-sm text-gray-600 ml-4">• {note}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Recommendation */}
                {recommended_for && (
                  <div className="mt-4 pt-4 border-t border-gray-200">
                    <p className="text-sm text-gray-700">
                      <strong>Best for:</strong> {recommended_for}
                    </p>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* CME Explanation */}
        <div className="mt-8 bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">Understanding CME (Creatine Monohydrate Equivalent)</h2>
          
          <div className="space-y-4 text-gray-700">
            <p>
              Different creatine forms contain different amounts of actual creatine because they&apos;re bound 
              to different molecules. To ensure consistent dosing, we use <strong>Creatine Monohydrate Equivalent (CME)</strong>.
            </p>

            <div className="bg-blue-50 p-4 rounded-md">
              <p className="font-semibold text-blue-900 mb-2">Example:</p>
              <p className="text-blue-800">
                To get 5g of creatine (as monohydrate):
              </p>
              <ul className="mt-2 space-y-1 text-blue-800">
                <li>• Monohydrate: <strong>5.0g</strong> (87.9% creatine)</li>
                <li>• Anhydrous: <strong>4.4g</strong> (100% creatine)</li>
                <li>• HCl: <strong>5.6g</strong> (78.2% creatine)</li>
              </ul>
            </div>

            <p>
              All research on creatine uses monohydrate, so we anchor dosing recommendations to monohydrate 
              equivalents to ensure you get the clinically-proven effective dose.
            </p>
          </div>
        </div>

        {/* Disclaimer */}
        <div className="mt-8 bg-gray-100 rounded-lg p-6 text-sm text-gray-700">
          <p className="font-medium mb-2">⚠️ Important Disclaimer</p>
          <p>
            This comparison is for educational purposes only. Individual responses may vary. 
            Consult a healthcare provider before starting any supplement, especially if you have 
            kidney disease or other medical conditions.
          </p>
        </div>
      </div>
    </div>
  )
}

