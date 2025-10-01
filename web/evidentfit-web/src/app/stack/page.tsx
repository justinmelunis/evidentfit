'use client'

import { useState } from 'react'
import Link from 'next/link'

type Dose = {
  value: string | number
  unit: string
  timing?: string
  days?: string | number | null
  split?: number | null
  notes?: string[]
  cap_reason?: string | null
}

type Citation = {
  title: string
  url: string
  pmid?: string
  study_type?: string
  journal?: string
  year?: number
}

type StackItem = {
  supplement: string
  evidence_grade: string
  included: boolean
  reason?: string
  why: string
  doses: Dose[]
  citations?: Citation[]
  tier: string
}

type Profile = {
  goal: 'strength' | 'hypertrophy' | 'endurance' | 'weight_loss' | 'performance' | 'general'
  weight_kg: number
  caffeine_sensitive: boolean
  meds: string[]
  conditions?: string[]
  diet?: 'any' | 'vegan' | 'vegetarian'
  training_freq?: 'low' | 'med' | 'high'
  age?: number
  pregnancy?: boolean
  diet_protein_g_per_day?: number
  creatine_form?: 'monohydrate' | 'anhydrous' | 'hcl'
}

export default function StackPlanner() {
  const [profile, setProfile] = useState<Profile>({
    goal: 'hypertrophy',
    weight_kg: 80,
    caffeine_sensitive: false,
    meds: [],
    conditions: [],
    diet: 'any',
    training_freq: 'med'
  })
  
  const [items, setItems] = useState<StackItem[]>([])
  const [explanation, setExplanation] = useState<string>('')
  const [exclusions, setExclusions] = useState<string[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  
  const [medInput, setMedInput] = useState('')
  const [conditionInput, setConditionInput] = useState('')

  const buildStack = async () => {
    setLoading(true)
    setError('')
    
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io'
      
      const response = await fetch(`${apiBase}/stack/conversational`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Basic ' + btoa('demo:demo123')
        },
        body: JSON.stringify({
          thread_id: `stack-${Date.now()}`,
          messages: [
            { role: 'user', content: `Build me a supplement stack for ${profile.goal}` }
          ],
          profile
        })
      })
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to build stack')
      }
      
      const data = await response.json()
      
      setItems(data.stack_plan?.items || [])
      setExplanation(data.explanation || '')
      setExclusions(data.stack_plan?.exclusions || [])
      setWarnings(data.stack_plan?.warnings || [])
      
    } catch (err: any) {
      setError(err.message || 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  const addMed = () => {
    if (medInput.trim()) {
      setProfile({...profile, meds: [...profile.meds, medInput.trim()]})
      setMedInput('')
    }
  }

  const removeMed = (index: number) => {
    setProfile({...profile, meds: profile.meds.filter((_, i) => i !== index)})
  }

  const addCondition = () => {
    if (conditionInput.trim()) {
      setProfile({...profile, conditions: [...(profile.conditions || []), conditionInput.trim()]})
      setConditionInput('')
    }
  }

  const removeCondition = (index: number) => {
    setProfile({...profile, conditions: (profile.conditions || []).filter((_, i) => i !== index)})
  }

  const tierOrder = ['core', 'optional', 'conditional', 'experimental']
  const itemsByTier = items.reduce((acc, item) => {
    if (!acc[item.tier]) acc[item.tier] = []
    acc[item.tier].push(item)
    return acc
  }, {} as Record<string, StackItem[]>)

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto p-6">
        <div className="mb-8">
          <Link href="/" className="text-blue-600 hover:text-blue-800 font-medium">
            ← Back to Home
          </Link>
          <h1 className="text-4xl font-bold text-gray-900 mt-4">Supplement Stack Planner</h1>
          <p className="text-gray-600 mt-2">Get evidence-based supplement recommendations tailored to your goals and health profile</p>
        </div>

        {/* Profile Form */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-2xl font-bold mb-6 text-gray-900">Your Profile</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Goal */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Primary Goal</label>
              <select 
                value={profile.goal}
                onChange={(e) => setProfile({...profile, goal: e.target.value as any})}
                className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="strength">Strength</option>
                <option value="hypertrophy">Muscle Growth (Hypertrophy)</option>
                <option value="endurance">Endurance</option>
                <option value="weight_loss">Weight Loss</option>
                <option value="performance">General Performance</option>
                <option value="general">General Health</option>
              </select>
            </div>

            {/* Weight */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Weight (kg)</label>
              <input 
                type="number"
                value={profile.weight_kg}
                onChange={(e) => setProfile({...profile, weight_kg: parseFloat(e.target.value) || 80})}
                className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                min="40"
                max="200"
              />
            </div>

            {/* Age */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Age (optional)</label>
              <input 
                type="number"
                value={profile.age || ''}
                onChange={(e) => setProfile({...profile, age: e.target.value ? parseInt(e.target.value) : undefined})}
                className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Leave blank if prefer not to say"
                min="13"
                max="120"
              />
            </div>

            {/* Training Frequency */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Training Frequency</label>
              <select 
                value={profile.training_freq}
                onChange={(e) => setProfile({...profile, training_freq: e.target.value as any})}
                className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="low">Low (1-2x/week)</option>
                <option value="med">Medium (3-4x/week)</option>
                <option value="high">High (5+x/week)</option>
              </select>
            </div>

            {/* Diet */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Diet</label>
              <select 
                value={profile.diet}
                onChange={(e) => setProfile({...profile, diet: e.target.value as any})}
                className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="any">Any</option>
                <option value="vegetarian">Vegetarian</option>
                <option value="vegan">Vegan</option>
              </select>
            </div>

            {/* Protein Intake */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Daily Protein Intake (g, optional)</label>
              <input 
                type="number"
                value={profile.diet_protein_g_per_day || ''}
                onChange={(e) => setProfile({...profile, diet_protein_g_per_day: e.target.value ? parseFloat(e.target.value) : undefined})}
                className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g., 120"
              />
            </div>

            {/* Creatine Form */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Preferred Creatine Form</label>
              <select 
                value={profile.creatine_form || 'monohydrate'}
                onChange={(e) => setProfile({...profile, creatine_form: e.target.value as any})}
                className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="monohydrate">Monohydrate (most researched)</option>
                <option value="anhydrous">Anhydrous (higher % per gram)</option>
                <option value="hcl">HCl (better solubility)</option>
              </select>
            </div>
          </div>

          {/* Checkboxes */}
          <div className="mt-6 space-y-3">
            <label className="flex items-center">
              <input 
                type="checkbox"
                checked={profile.caffeine_sensitive}
                onChange={(e) => setProfile({...profile, caffeine_sensitive: e.target.checked})}
                className="mr-2 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
              />
              <span className="text-sm text-gray-700">I&apos;m sensitive to caffeine</span>
            </label>

            <label className="flex items-center">
              <input 
                type="checkbox"
                checked={profile.pregnancy || false}
                onChange={(e) => setProfile({...profile, pregnancy: e.target.checked})}
                className="mr-2 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
              />
              <span className="text-sm text-gray-700">Pregnant or breastfeeding</span>
            </label>
          </div>

          {/* Medications */}
          <div className="mt-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">Medications (optional)</label>
            <div className="flex gap-2 mb-2">
              <input 
                type="text"
                value={medInput}
                onChange={(e) => setMedInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addMed()}
                placeholder="e.g., lisinopril, metformin"
                className="flex-1 p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button 
                onClick={addMed}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {profile.meds.map((med, i) => (
                <span key={i} className="inline-flex items-center px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
                  {med}
                  <button onClick={() => removeMed(i)} className="ml-2 text-gray-500 hover:text-gray-700">×</button>
                </span>
              ))}
            </div>
          </div>

          {/* Conditions */}
          <div className="mt-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">Medical Conditions (optional)</label>
            <div className="flex gap-2 mb-2">
              <input 
                type="text"
                value={conditionInput}
                onChange={(e) => setConditionInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addCondition()}
                placeholder="e.g., hypertension, anxiety"
                className="flex-1 p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button 
                onClick={addCondition}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {(profile.conditions || []).map((condition, i) => (
                <span key={i} className="inline-flex items-center px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
                  {condition}
                  <button onClick={() => removeCondition(i)} className="ml-2 text-gray-500 hover:text-gray-700">×</button>
                </span>
              ))}
            </div>
          </div>

          {/* Build Button */}
          <div className="mt-8">
            <button 
              onClick={buildStack}
              disabled={loading}
              className="w-full py-3 bg-blue-600 text-white font-semibold rounded-md hover:bg-blue-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {loading ? 'Building Your Stack...' : 'Build My Stack'}
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-8">
            <p className="text-red-800 font-medium">Error: {error}</p>
          </div>
        )}

        {/* Warnings */}
        {warnings.length > 0 && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-8">
            <h3 className="text-lg font-bold text-yellow-900 mb-2">⚠️ Important Safety Information</h3>
            <ul className="list-disc list-inside space-y-1 text-yellow-800">
              {warnings.map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Exclusions */}
        {exclusions.length > 0 && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-8">
            <h3 className="text-lg font-bold text-gray-900 mb-2">🚫 Excluded Supplements</h3>
            <ul className="list-disc list-inside space-y-1 text-gray-700">
              {exclusions.map((exclusion, i) => (
                <li key={i}>{exclusion}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Stack Results */}
        {items.length > 0 && (
          <div className="space-y-6">
            {tierOrder.map(tier => {
              const tierItems = itemsByTier[tier]
              if (!tierItems || tierItems.length === 0) return null

              const tierLabels: Record<string, string> = {
                core: 'Core Supplements',
                optional: 'Optional Additions',
                conditional: 'Conditional Recommendations',
                experimental: 'Experimental (Limited Evidence)'
              }

              const tierColors: Record<string, string> = {
                core: 'bg-blue-50 border-blue-200',
                optional: 'bg-green-50 border-green-200',
                conditional: 'bg-yellow-50 border-yellow-200',
                experimental: 'bg-gray-50 border-gray-200'
              }

              return (
                <div key={tier} className={`rounded-lg border-2 ${tierColors[tier]} p-6`}>
                  <h2 className="text-2xl font-bold mb-4 text-gray-900">{tierLabels[tier]}</h2>
                  
                  <div className="space-y-4">
                    {tierItems.map((item, i) => (
                      <div key={i} className="bg-white rounded-lg p-4 shadow-sm">
                        <div className="flex items-start justify-between mb-3">
                          <div>
                            <h3 className="text-xl font-bold text-gray-900 capitalize">{item.supplement}</h3>
                            <span className={`inline-block px-2 py-1 rounded text-sm font-medium mt-1 ${
                              item.evidence_grade === 'A' ? 'bg-green-100 text-green-800' :
                              item.evidence_grade === 'B' ? 'bg-blue-100 text-blue-800' :
                              item.evidence_grade === 'C' ? 'bg-yellow-100 text-yellow-800' :
                              'bg-gray-100 text-gray-800'
                            }`}>
                              Evidence Grade: {item.evidence_grade}
                            </span>
                          </div>
                        </div>

                        <p className="text-gray-700 mb-3">{item.why}</p>

                        {/* Doses */}
                        <div className="mb-3">
                          <h4 className="font-semibold text-gray-900 mb-2">Dosing:</h4>
                          {item.doses.map((dose, j) => (
                            <div key={j} className="ml-4 mb-2">
                              <p className="text-gray-800">
                                <span className="font-medium">{dose.value} {dose.unit}</span>
                                {dose.timing && <span className="text-gray-600"> • {dose.timing}</span>}
                                {dose.days && <span className="text-gray-600"> • {dose.days} days</span>}
                                {dose.split && <span className="text-gray-600"> • {dose.split}x daily</span>}
                              </p>
                              {dose.notes && dose.notes.length > 0 && (
                                <ul className="ml-4 mt-1 text-sm text-gray-600 list-disc list-inside">
                                  {dose.notes.map((note, k) => (
                                    <li key={k}>{note}</li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          ))}
                        </div>

                        {/* Citations */}
                        {item.citations && item.citations.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-gray-200">
                            <h4 className="font-semibold text-gray-900 mb-2 text-sm">Research Support:</h4>
                            <div className="space-y-1">
                              {item.citations.map((citation, j) => (
                                <a 
                                  key={j}
                                  href={citation.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="block text-sm text-blue-600 hover:text-blue-800 hover:underline"
                                >
                                  {citation.title}
                                  {citation.study_type && <span className="text-gray-500"> ({citation.study_type})</span>}
                                </a>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}

            {/* Disclaimer */}
            <div className="bg-gray-100 rounded-lg p-6 text-sm text-gray-700">
              <p className="font-medium mb-2">⚠️ Important Disclaimer</p>
              <p>This is educational information only and not medical advice. Consult a qualified healthcare provider before starting any supplement regimen, especially if you have medical conditions or take medications.</p>
            </div>
          </div>
        )}

        {/* Creatine Forms Link */}
        {items.some(item => item.supplement === 'creatine') && (
          <div className="mt-6 text-center">
            <Link 
              href="/stack/creatine-forms" 
              className="inline-block px-6 py-3 bg-gray-200 text-gray-800 font-medium rounded-md hover:bg-gray-300 transition-colors"
            >
              Compare Creatine Forms →
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
