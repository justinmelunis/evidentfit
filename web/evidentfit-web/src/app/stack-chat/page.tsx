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
  // Form selection fields
  selected_form?: string
  form_display_name?: string
  form_options?: FormOption[]
}

type FormOption = {
  form_key: string
  name: string
  research_grade: string
  cost_factor: number
  advantages: string[]
  recommended_for: string
  reference_form: boolean
}

type Profile = {
  goal: 'strength' | 'hypertrophy' | 'endurance' | 'weight_loss' | 'performance' | 'general'
  weight_kg: number
  age?: number
  sex?: 'male' | 'female' | 'other'
  caffeine_sensitive: boolean
  pregnancy?: boolean
  meds: string[]
  conditions?: string[]
  diet?: 'any' | 'vegan' | 'vegetarian'
  training_freq?: 'low' | 'med' | 'high'
  diet_protein_g_per_day?: number
  creatine_form?: 'monohydrate' | 'anhydrous' | 'hcl'
}

export default function StackChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [currentStack, setCurrentStack] = useState<StackItem[]>([])
  const [customStack, setCustomStack] = useState<Set<string>>(new Set()) // Track user's custom selections
  const [selectedForms, setSelectedForms] = useState<Record<string, string>>({}) // Track form selections
  const [exclusions, setExclusions] = useState<string[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  
  const [profile, setProfile] = useState<Profile>({
    goal: 'hypertrophy',
    weight_kg: 176, // Default 176 lbs = 80 kg
    age: undefined,
    sex: undefined,
    caffeine_sensitive: false,
    meds: [],
    conditions: [],
    diet: 'any',
    training_freq: 'med'
  })
  
  const [weightLbs, setWeightLbs] = useState(176)
  const [showExclusions, setShowExclusions] = useState(false)
  const [activeSection, setActiveSection] = useState<'recommended' | 'optional' | 'not_recommended'>('recommended')
  
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Initialize custom stack when recommendations are loaded
  useEffect(() => {
    if (currentStack.length > 0) {
      // Pre-select recommended supplements 
      const recommendedSupplements = currentStack
        .filter(item => (item.tier === 'recommended' || item.tier === 'core') && item.included)
        .map(item => item.supplement)
      setCustomStack(new Set(recommendedSupplements))
    }
  }, [currentStack])

  // Toggle supplement in custom stack
  const toggleSupplement = (supplement: string) => {
    setCustomStack(prev => {
      const newSet = new Set(prev)
      if (newSet.has(supplement)) {
        newSet.delete(supplement)
      } else {
        newSet.add(supplement)
      }
      return newSet
    })
  }

  const buildStack = async () => {
    if (loading) return

    const userContext = input.trim() || `Build me a supplement stack for ${profile.goal.replace('_', ' ')}`
    
    setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: userContext }])

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io'
      
      // Convert lbs to kg for API
      const profileWithKg = {
        ...profile,
        weight_kg: Math.round(weightLbs / 2.20462 * 10) / 10 // Convert lbs to kg
      }
      
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
          profile: profileWithKg
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
          <h1 className="text-4xl font-bold text-gray-900 mt-4">Supplement Stack Planner</h1>
          <p className="text-gray-600 mt-2">Build your personalized supplement stack with detailed explanations and research citations</p>
        </div>

        {/* Profile Form */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-2xl font-bold mb-4 text-gray-900">Your Profile</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Goal *</label>
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
              <label className="block text-sm font-medium text-gray-700 mb-1">Weight (lbs) *</label>
              <input 
                type="number"
                value={weightLbs}
                onChange={(e) => setWeightLbs(parseFloat(e.target.value) || 176)}
                className="w-full p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Age</label>
              <input 
                type="number"
                value={profile.age || ''}
                onChange={(e) => setProfile({...profile, age: e.target.value ? parseInt(e.target.value) : undefined})}
                className="w-full p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                placeholder="Optional"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Sex</label>
              <select 
                value={profile.sex || ''}
                onChange={(e) => setProfile({...profile, sex: e.target.value ? e.target.value as any : undefined})}
                className="w-full p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Prefer not to say</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
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

          {/* Custom Input & Build Button */}
          <div className="border-t pt-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Tell us more about your goals and preferences (optional)
            </label>
            <p className="text-xs text-gray-600 mb-2">
              Share specific concerns, training schedule, dietary restrictions, or mention specific supplements you&apos;re interested in
            </p>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Example: I train early mornings before work and prefer supplements that won't upset my stomach. I'm also interested in ashwagandha for stress and want to know if beta-alanine is right for me..."
              className="w-full p-3 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 resize-none"
              rows={4}
            />
            
            <button
              onClick={buildStack}
              disabled={loading}
              className="mt-4 w-full py-4 bg-blue-600 text-white font-bold text-lg rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {loading ? 'Building Your Stack...' : '🚀 Build My Personalized Stack'}
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

        {/* Exclusions/Not Recommended - Collapsible */}
        {exclusions.length > 0 && (
          <div className="bg-gray-50 border-2 border-gray-300 rounded-lg p-4 mb-6">
            <button
              onClick={() => setShowExclusions(!showExclusions)}
              className="w-full flex items-center justify-between text-left"
            >
              <h3 className="text-lg font-bold text-gray-900">
                🚫 Supplements Not Recommended ({exclusions.length})
              </h3>
              <span className="text-2xl text-gray-600">
                {showExclusions ? '−' : '+'}
              </span>
            </button>
            
            {showExclusions && (
              <div className="mt-4 space-y-2">
                {exclusions.map((exclusion, i) => (
                  <div key={i} className="p-3 bg-white rounded border border-gray-300">
                    <p className="text-sm text-gray-800">{exclusion}</p>
                  </div>
                ))}
                <p className="text-xs text-gray-600 italic mt-3">
                  These supplements were excluded based on your profile, medical conditions, or lack of strong evidence for your goals.
                </p>
              </div>
            )}
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
                <div className="mt-4">
                  {/* Custom Stack Summary */}
                  {customStack.size > 0 && (
                    <div className="mb-4 p-4 bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-lg">
                      <h3 className="text-lg font-bold text-purple-900 mb-2">🎯 Your Custom Stack ({customStack.size} supplements)</h3>
                      <div className="flex flex-wrap gap-2">
                        {Array.from(customStack).map(supplement => {
                          const item = currentStack.find(s => s.supplement === supplement)
                          return (
                            <div key={supplement} className="flex items-center gap-2 bg-white px-3 py-1 rounded-full border border-purple-300">
                              <span className="text-sm font-medium capitalize">{supplement}</span>
                              {item && (
                                <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                                  item.evidence_grade === 'A' ? 'bg-green-100 text-green-800' :
                                  item.evidence_grade === 'B' ? 'bg-blue-100 text-blue-800' :
                                  item.evidence_grade === 'C' ? 'bg-yellow-100 text-yellow-800' :
                                  'bg-gray-100 text-gray-800'
                                }`}>
                                  {item.evidence_grade}
                                </span>
                              )}
                              <button
                                onClick={() => toggleSupplement(supplement)}
                                className="text-purple-600 hover:text-purple-800 font-bold text-sm"
                              >
                                ×
                              </button>
                            </div>
                          )
                        })}
                      </div>
                      <p className="text-xs text-purple-700 mt-2">
                        💡 Use the checkboxes below to add or remove supplements from your custom stack
                      </p>
                    </div>
                  )}

                  {/* Section Toggle Buttons */}
                  <div className="flex flex-wrap gap-2 mb-4 p-2 bg-gray-100 rounded-lg">
                    <button
                      onClick={() => setActiveSection('recommended')}
                      className={`px-4 py-2 rounded-md font-medium transition-colors ${
                        activeSection === 'recommended'
                          ? 'bg-green-600 text-white shadow-md'
                          : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-300'
                      }`}
                    >
                      ✅ Recommended ({(itemsByTier['core'] || []).length})
                    </button>
                    <button
                      onClick={() => setActiveSection('optional')}
                      className={`px-4 py-2 rounded-md font-medium transition-colors ${
                        activeSection === 'optional'
                          ? 'bg-blue-600 text-white shadow-md'
                          : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-300'
                      }`}
                    >
                      💡 Optional ({(itemsByTier['optional'] || []).length})
                    </button>
                    <button
                      onClick={() => setActiveSection('not_recommended')}
                      className={`px-4 py-2 rounded-md font-medium transition-colors ${
                        activeSection === 'not_recommended'
                          ? 'bg-red-600 text-white shadow-md'
                          : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-300'
                      }`}
                    >
                      🚫 Not Recommended ({(itemsByTier['not_recommended'] || []).length})
                    </button>
                  </div>

                  {/* Active Section Content */}
                  <div className="space-y-4">
                    {/* Recommended Supplements */}
                    {activeSection === 'recommended' && itemsByTier['core'] && itemsByTier['core'].length > 0 && (
                      <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-green-500">
                        <h3 className="text-xl font-bold text-green-900 mb-3">✅ Recommended Supplements</h3>
                        <p className="text-sm text-gray-600 mb-4">These supplements have strong evidence for your goals and are safe based on your profile.</p>
                        <div className="space-y-4">
                          {itemsByTier['core'].map((item, i) => (
                            <div key={i} className="border-l-4 border-green-500 pl-3 py-2 bg-green-50 rounded">
                              <div className="flex items-start justify-between mb-2">
                                <div className="flex items-center gap-3">
                                  <input
                                    type="checkbox"
                                    checked={customStack.has(item.supplement)}
                                    onChange={() => toggleSupplement(item.supplement)}
                                    className="w-4 h-4 text-green-600 bg-gray-100 border-gray-300 rounded focus:ring-green-500 focus:ring-2"
                                  />
                                  <h4 className="font-bold text-gray-900 capitalize text-base">
                                    {item.form_display_name || item.supplement}
                                  </h4>
                                </div>
                                <span className={`px-2 py-1 rounded text-xs font-bold ${
                                  item.evidence_grade === 'A' ? 'bg-green-100 text-green-800' :
                                  item.evidence_grade === 'B' ? 'bg-blue-100 text-blue-800' :
                                  'bg-yellow-100 text-yellow-800'
                                }`}>
                                  Grade {item.evidence_grade}
                                </span>
                              </div>
                              
                              {/* Form Selection */}
                              {item.form_options && item.form_options.length > 1 && (
                                <div className="mb-3 bg-gray-50 p-3 rounded border">
                                  <p className="text-sm font-semibold text-gray-700 mb-2">📋 Form Selection:</p>
                                  <div className="space-y-2">
                                    {item.form_options.map((formOption) => (
                                      <label key={formOption.form_key} className="flex items-start gap-2 cursor-pointer">
                                        <input
                                          type="radio"
                                          name={`form-${item.supplement}`}
                                          value={formOption.form_key}
                                          checked={selectedForms[item.supplement] === formOption.form_key || 
                                                  (!selectedForms[item.supplement] && formOption.reference_form)}
                                          onChange={(e) => {
                                            setSelectedForms(prev => ({
                                              ...prev,
                                              [item.supplement]: e.target.value
                                            }))
                                          }}
                                          className="mt-1 w-4 h-4 text-green-600 bg-gray-100 border-gray-300 rounded focus:ring-green-500 focus:ring-2"
                                        />
                                        <div className="flex-1">
                                          <div className="flex items-center gap-2">
                                            <span className="text-sm font-medium">{formOption.name}</span>
                                            <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                                              formOption.research_grade === 'A' ? 'bg-green-100 text-green-800' :
                                              formOption.research_grade === 'B' ? 'bg-blue-100 text-blue-800' :
                                              'bg-yellow-100 text-yellow-800'
                                            }`}>
                                              {formOption.research_grade}
                                            </span>
                                            {formOption.reference_form && (
                                              <span className="px-1.5 py-0.5 bg-purple-100 text-purple-800 rounded text-xs font-bold">
                                                Most Researched
                                              </span>
                                            )}
                                          </div>
                                          <p className="text-xs text-gray-600 mt-1">{formOption.recommended_for}</p>
                                          {formOption.advantages.length > 0 && (
                                            <p className="text-xs text-green-700 mt-1">
                                              ✓ {formOption.advantages.join(', ')}
                                            </p>
                                          )}
                                        </div>
                                      </label>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              <div className="mb-3">
                                <p className="text-sm font-semibold text-gray-700 mb-1">Why It&apos;s Recommended:</p>
                                <p className="text-sm text-gray-700">{item.why}</p>
                              </div>
                              
                              {item.doses.length > 0 && (
                                <div className="mb-3 bg-white p-2 rounded border border-gray-200">
                                  <p className="text-sm font-semibold text-gray-700 mb-1">Dosing:</p>
                                  <p className="text-sm text-gray-900">
                                    <strong>{item.doses[0].value} {item.doses[0].unit}</strong>
                                    {item.doses[0].timing && <span className="text-gray-600"> • {item.doses[0].timing}</span>}
                                  </p>
                                  {item.doses[0]?.notes && item.doses[0].notes.length > 0 && (
                                    <ul className="text-xs text-gray-600 list-disc list-inside mt-2">
                                      {item.doses[0].notes.map((note, j) => (
                                        <li key={j}>{note}</li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              )}
                              
                              {item.citations && item.citations.length > 0 && (
                                <div className="bg-blue-50 p-2 rounded border border-blue-200">
                                  <p className="text-sm font-semibold text-blue-900 mb-1">
                                    📚 Supporting Research ({item.citations.length} {item.citations.length === 1 ? 'study' : 'studies'}):
                                  </p>
                                  <div className="space-y-1">
                                    {item.citations.map((citation, j) => (
                                      <a
                                        key={j}
                                        href={citation.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="block text-xs text-blue-700 hover:text-blue-900 hover:underline"
                                      >
                                        {j + 1}. {citation.title}
                                        {citation.study_type && <span className="text-blue-600"> ({citation.study_type})</span>}
                                      </a>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Optional Supplements */}
                    {activeSection === 'optional' && itemsByTier['optional'] && itemsByTier['optional'].length > 0 && (
                      <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-blue-500">
                        <h3 className="text-xl font-bold text-blue-900 mb-3">💡 Optional Supplements</h3>
                        <p className="text-sm text-gray-600 mb-4">These supplements may provide additional benefits but aren&apos;t essential for your goals.</p>
                        <div className="space-y-4">
                          {itemsByTier['optional'].map((item, i) => (
                            <div key={i} className="border-l-4 border-blue-500 pl-3 py-2 bg-blue-50 rounded">
                              <div className="flex items-start justify-between mb-2">
                                <div className="flex items-center gap-3">
                                  <input
                                    type="checkbox"
                                    checked={customStack.has(item.supplement)}
                                    onChange={() => toggleSupplement(item.supplement)}
                                    className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 focus:ring-2"
                                  />
                                  <h4 className="font-bold text-gray-900 capitalize text-base">{item.supplement}</h4>
                                </div>
                                <span className={`px-2 py-1 rounded text-xs font-bold ${
                                  item.evidence_grade === 'A' ? 'bg-green-100 text-green-800' :
                                  item.evidence_grade === 'B' ? 'bg-blue-100 text-blue-800' :
                                  'bg-yellow-100 text-yellow-800'
                                }`}>
                                  Grade {item.evidence_grade}
                                </span>
                              </div>
                              
                              <div className="mb-3">
                                <p className="text-sm font-semibold text-gray-700 mb-1">Potential Benefits:</p>
                                <p className="text-sm text-gray-700">{item.why}</p>
                              </div>
                              
                              {item.doses.length > 0 && (
                                <div className="mb-3 bg-white p-2 rounded border border-gray-200">
                                  <p className="text-sm font-semibold text-gray-700 mb-1">Dosing:</p>
                                  <p className="text-sm text-gray-900">
                                    <strong>{item.doses[0].value} {item.doses[0].unit}</strong>
                                    {item.doses[0].timing && <span className="text-gray-600"> • {item.doses[0].timing}</span>}
                                  </p>
                                  {item.doses[0]?.notes && item.doses[0].notes.length > 0 && (
                                    <ul className="text-xs text-gray-600 list-disc list-inside mt-2">
                                      {item.doses[0].notes.map((note, j) => (
                                        <li key={j}>{note}</li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              )}
                              
                              {item.citations && item.citations.length > 0 && (
                                <div className="bg-blue-50 p-2 rounded border border-blue-200">
                                  <p className="text-sm font-semibold text-blue-900 mb-1">
                                    📚 Supporting Research ({item.citations.length} {item.citations.length === 1 ? 'study' : 'studies'}):
                                  </p>
                                  <div className="space-y-1">
                                    {item.citations.map((citation, j) => (
                                      <a
                                        key={j}
                                        href={citation.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="block text-xs text-blue-700 hover:text-blue-900 hover:underline"
                                      >
                                        {j + 1}. {citation.title}
                                        {citation.study_type && <span className="text-blue-600"> ({citation.study_type})</span>}
                                      </a>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Not Recommended Supplements */}
                    {activeSection === 'not_recommended' && itemsByTier['not_recommended'] && itemsByTier['not_recommended'].length > 0 && (
                      <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-red-500">
                        <h3 className="text-xl font-bold text-red-900 mb-3">🚫 Not Recommended</h3>
                        <p className="text-sm text-gray-600 mb-4">These supplements are not recommended for your profile due to insufficient evidence, safety concerns, or better alternatives.</p>
                        <div className="space-y-4">
                          {itemsByTier['not_recommended'].map((item, i) => (
                            <div key={i} className="border-l-4 border-red-500 pl-3 py-2 bg-red-50 rounded">
                              <div className="flex items-start justify-between mb-2">
                                <div className="flex items-center gap-3">
                                  <input
                                    type="checkbox"
                                    checked={customStack.has(item.supplement)}
                                    onChange={() => toggleSupplement(item.supplement)}
                                    className="w-4 h-4 text-red-600 bg-gray-100 border-gray-300 rounded focus:ring-red-500 focus:ring-2"
                                  />
                                  <h4 className="font-bold text-gray-900 capitalize text-base">{item.supplement}</h4>
                                </div>
                                <span className={`px-2 py-1 rounded text-xs font-bold ${
                                  item.evidence_grade === 'A' ? 'bg-green-100 text-green-800' :
                                  item.evidence_grade === 'B' ? 'bg-blue-100 text-blue-800' :
                                  item.evidence_grade === 'C' ? 'bg-yellow-100 text-yellow-800' :
                                  'bg-gray-100 text-gray-800'
                                }`}>
                                  Grade {item.evidence_grade}
                                </span>
                              </div>
                              
                              <div className="mb-3">
                                <p className="text-sm font-semibold text-gray-700 mb-1">Why Not Recommended:</p>
                                <p className="text-sm text-gray-700">{item.reason || item.why}</p>
                              </div>
                              
                              {item.citations && item.citations.length > 0 && (
                                <div className="bg-blue-50 p-2 rounded border border-blue-200">
                                  <p className="text-sm font-semibold text-blue-900 mb-1">
                                    📚 Research Context ({item.citations.length} {item.citations.length === 1 ? 'study' : 'studies'}):
                                  </p>
                                  <div className="space-y-1">
                                    {item.citations.map((citation, j) => (
                                      <a
                                        key={j}
                                        href={citation.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="block text-xs text-blue-700 hover:text-blue-900 hover:underline"
                                      >
                                        {j + 1}. {citation.title}
                                        {citation.study_type && <span className="text-blue-600"> ({citation.study_type})</span>}
                                      </a>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Empty State Messages */}
                    {activeSection === 'recommended' && (!itemsByTier['core'] || itemsByTier['core'].length === 0) && (
                      <div className="bg-gray-50 rounded-lg p-6 text-center">
                        <p className="text-gray-600">No supplements are strongly recommended for your current profile.</p>
                      </div>
                    )}

                    {activeSection === 'optional' && (!itemsByTier['optional'] || itemsByTier['optional'].length === 0) && (
                      <div className="bg-gray-50 rounded-lg p-6 text-center">
                        <p className="text-gray-600">No optional supplements identified for your profile.</p>
                      </div>
                    )}

                    {activeSection === 'not_recommended' && (!itemsByTier['not_recommended'] || itemsByTier['not_recommended'].length === 0) && (
                      <div className="bg-gray-50 rounded-lg p-6 text-center">
                        <p className="text-gray-600">No supplements are specifically not recommended for your profile.</p>
                      </div>
                    )}
                  </div>
                </div>
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
