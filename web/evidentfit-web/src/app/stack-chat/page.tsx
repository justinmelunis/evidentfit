'use client'

import { useState, useRef, useEffect } from 'react'
import Link from 'next/link'

type Message = {
  role: 'user' | 'assistant'
  content: string
}

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

export default function StackChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [currentStack, setCurrentStack] = useState<StackItem[]>([])
  const [exclusions, setExclusions] = useState<string[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  
  const [profile, setProfile] = useState<Profile>({
    goal: 'hypertrophy',
    weight_kg: 80,
    caffeine_sensitive: false,
    meds: [],
    conditions: [],
    diet: 'any',
    training_freq: 'med'
  })
  
  const [medInput, setMedInput] = useState('')
  const [conditionInput, setConditionInput] = useState('')
  
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const buildStack = async () => {
    if (loading) return

    const userContext = input.trim() || `Build me a supplement stack for ${profile.goal.replace('_', ' ')}`
    
    setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: userContext }])

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io'
      
      const response = await fetch(`${apiBase}/stack/conversational`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Basic ' + btoa('demo:demo123')
        },
        body: JSON.stringify({
          thread_id: `stack-chat-${Date.now()}`,
          messages: [
            ...messages,
            { role: 'user', content: userContext }
          ],
          profile
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to get response')
      }

      const data = await response.json()
      
      // Update stack and warnings
      if (data.stack_plan?.items) {
        setCurrentStack(data.stack_plan.items)
        setExclusions(data.stack_plan.exclusions || [])
        setWarnings(data.stack_plan.warnings || [])
      }
      
      // Add assistant response
      const explanation = data.explanation || "I've built your personalized supplement stack based on your profile and goals."
      setMessages(prev => [...prev, { role: 'assistant', content: explanation }])
      
      setInput('') // Clear input after building
      
    } catch (error: any) {
      const errorMessage = `Sorry, I encountered an error: ${error.message}. Please try again.`
      setMessages(prev => [...prev, { role: 'assistant', content: errorMessage }])
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
  const itemsByTier = currentStack.reduce((acc, item) => {
    if (!acc[item.tier]) acc[item.tier] = []
    acc[item.tier].push(item)
    return acc
  }, {} as Record<string, StackItem[]>)

  const tierLabels: Record<string, string> = {
    core: '🎯 Core',
    optional: '✨ Optional',
    conditional: '⚠️ Conditional',
    experimental: '🧪 Experimental'
  }

  const tierColors: Record<string, string> = {
    core: 'border-l-4 border-blue-500 bg-blue-50',
    optional: 'border-l-4 border-green-500 bg-green-50',
    conditional: 'border-l-4 border-yellow-500 bg-yellow-50',
    experimental: 'border-l-4 border-gray-500 bg-gray-50'
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto p-6">
        <div className="mb-6">
          <Link href="/" className="text-blue-600 hover:text-blue-800 font-medium">
            ← Back to Home
          </Link>
          <h1 className="text-4xl font-bold text-gray-900 mt-4">Stack Builder</h1>
          <p className="text-gray-600 mt-2">Build your personalized supplement stack with profile details and custom input</p>
        </div>

        {/* Profile Form */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-2xl font-bold mb-4 text-gray-900">Your Profile</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Goal</label>
              <select 
                value={profile.goal}
                onChange={(e) => setProfile({...profile, goal: e.target.value as any})}
                className="w-full p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              >
                <option value="strength">Strength</option>
                <option value="hypertrophy">Muscle Growth</option>
                <option value="endurance">Endurance</option>
                <option value="weight_loss">Weight Loss</option>
                <option value="performance">Performance</option>
                <option value="general">General Health</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Weight (kg)</label>
              <input 
                type="number"
                value={profile.weight_kg}
                onChange={(e) => setProfile({...profile, weight_kg: parseFloat(e.target.value) || 80})}
                className="w-full p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Age (optional)</label>
              <input 
                type="number"
                value={profile.age || ''}
                onChange={(e) => setProfile({...profile, age: e.target.value ? parseInt(e.target.value) : undefined})}
                className="w-full p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                placeholder="Optional"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Training Frequency</label>
              <select 
                value={profile.training_freq}
                onChange={(e) => setProfile({...profile, training_freq: e.target.value as any})}
                className="w-full p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              >
                <option value="low">Low (1-2x/week)</option>
                <option value="med">Medium (3-4x/week)</option>
                <option value="high">High (5+x/week)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Diet</label>
              <select 
                value={profile.diet}
                onChange={(e) => setProfile({...profile, diet: e.target.value as any})}
                className="w-full p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              >
                <option value="any">Any</option>
                <option value="vegetarian">Vegetarian</option>
                <option value="vegan">Vegan</option>
              </select>
            </div>
          </div>

          <div className="flex flex-wrap gap-4 mb-4">
            <label className="flex items-center">
              <input 
                type="checkbox"
                checked={profile.caffeine_sensitive}
                onChange={(e) => setProfile({...profile, caffeine_sensitive: e.target.checked})}
                className="mr-2"
              />
              <span className="text-sm">Caffeine sensitive</span>
            </label>

            <label className="flex items-center">
              <input 
                type="checkbox"
                checked={profile.pregnancy || false}
                onChange={(e) => setProfile({...profile, pregnancy: e.target.checked})}
                className="mr-2"
              />
              <span className="text-sm">Pregnant/breastfeeding</span>
            </label>
          </div>

          {/* Medications */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Medications (optional)</label>
            <div className="flex gap-2 mb-2">
              <input 
                type="text"
                value={medInput}
                onChange={(e) => setMedInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addMed()}
                placeholder="e.g., lisinopril"
                className="flex-1 p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              />
              <button 
                onClick={addMed}
                className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {profile.meds.map((med, i) => (
                <span key={i} className="inline-flex items-center px-3 py-1 bg-gray-100 rounded-full text-sm">
                  {med}
                  <button onClick={() => removeMed(i)} className="ml-2 text-gray-600 hover:text-gray-900">×</button>
                </span>
              ))}
            </div>
          </div>

          {/* Conditions */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">Medical Conditions (optional)</label>
            <div className="flex gap-2 mb-2">
              <input 
                type="text"
                value={conditionInput}
                onChange={(e) => setConditionInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addCondition()}
                placeholder="e.g., hypertension"
                className="flex-1 p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              />
              <button 
                onClick={addCondition}
                className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {(profile.conditions || []).map((condition, i) => (
                <span key={i} className="inline-flex items-center px-3 py-1 bg-gray-100 rounded-full text-sm">
                  {condition}
                  <button onClick={() => removeCondition(i)} className="ml-2 text-gray-600 hover:text-gray-900">×</button>
                </span>
              ))}
            </div>
          </div>

          {/* Custom Input & Build Button */}
          <div className="border-t pt-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Additional Details (optional)
            </label>
            <p className="text-xs text-gray-600 mb-2">
              Add any specific questions, concerns, or preferences about your stack
            </p>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="e.g., I'm particularly interested in creatine alternatives, or I train fasted in the mornings..."
              className="w-full p-3 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 resize-none"
              rows={3}
            />
            
            <button
              onClick={buildStack}
              disabled={loading}
              className="mt-4 w-full py-4 bg-blue-600 text-white font-bold text-lg rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {loading ? 'Building Your Stack...' : '🚀 Build My Stack'}
            </button>
          </div>
        </div>

        {/* Warnings */}
        {warnings.length > 0 && (
          <div className="bg-yellow-50 border-2 border-yellow-300 rounded-lg p-4 mb-6">
            <h3 className="text-lg font-bold text-yellow-900 mb-2">⚠️ Safety Information</h3>
            <ul className="list-disc list-inside space-y-1 text-yellow-800">
              {warnings.map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Conversation & Stack */}
        {messages.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Messages */}
            <div className="lg:col-span-2">
              <div className="bg-white rounded-lg shadow-md p-6">
                <h2 className="text-2xl font-bold mb-4 text-gray-900">Stack Analysis</h2>
                <div className="space-y-4">
                  {messages.map((msg, i) => (
                    <div 
                      key={i} 
                      className={`p-4 rounded-lg ${
                        msg.role === 'user' 
                          ? 'bg-blue-50 border-l-4 border-blue-500' 
                          : 'bg-gray-50 border-l-4 border-gray-300'
                      }`}
                    >
                      <div className="text-xs font-semibold text-gray-600 mb-1">
                        {msg.role === 'user' ? 'Your Input' : 'Analysis'}
                      </div>
                      <div className="whitespace-pre-wrap text-gray-900">{msg.content}</div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              </div>
            </div>

            {/* Stack Summary */}
            <div className="space-y-4">
              {currentStack.length > 0 && (
                <div className="bg-white rounded-lg shadow-md p-4">
                  <h3 className="text-lg font-bold text-gray-900 mb-3">Your Stack</h3>
                  
                  {tierOrder.map(tier => {
                    const items = itemsByTier[tier]
                    if (!items || items.length === 0) return null

                    return (
                      <div key={tier} className="mb-3">
                        <h4 className="text-xs font-semibold text-gray-600 mb-1">
                          {tierLabels[tier]}
                        </h4>
                        <div className="space-y-2">
                          {items.map((item, i) => (
                            <div 
                              key={i}
                              className={`p-2 rounded ${tierColors[tier]}`}
                            >
                              <div className="font-medium text-sm capitalize">{item.supplement}</div>
                              <div className="text-xs text-gray-600">
                                Grade {item.evidence_grade}
                                {item.doses.length > 0 && (
                                  <span> • {item.doses[0].value} {item.doses[0].unit}</span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}

                  {exclusions.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <h4 className="text-xs font-semibold text-gray-600 mb-1">Excluded</h4>
                      {exclusions.map((exclusion, i) => (
                        <div key={i} className="text-xs text-gray-600 mb-1">• {exclusion}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {currentStack.length > 0 && (
                <Link
                  href="/stack"
                  className="block w-full py-3 text-center bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 transition-colors"
                >
                  View Full Stack Details →
                </Link>
              )}
            </div>
          </div>
        )}

        {/* Disclaimer */}
        <div className="mt-6 bg-gray-100 rounded-lg p-4 text-sm text-gray-700">
          <p className="font-medium mb-1">⚠️ Important Disclaimer</p>
          <p>This is educational information only, not medical advice. Consult a healthcare provider before starting any supplement regimen.</p>
        </div>
      </div>
    </div>
  )
}
