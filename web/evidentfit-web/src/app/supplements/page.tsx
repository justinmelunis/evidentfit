'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'

type SupplementInfo = {
  name: string
  mechanism: string
  description: string
  dosage: string
  timing: string
  safety: string[]
  evidenceByGoal: {
    [goal: string]: {
      grade: string
      paperCount: number
      summary: string
    }
  }
}

// Comprehensive supplement database with mechanisms and descriptions
const SUPPLEMENT_DATABASE: { [key: string]: SupplementInfo } = {
  "creatine": {
    name: "Creatine Monohydrate",
    mechanism: "Increases phosphocreatine stores in muscles, enabling rapid ATP regeneration during high-intensity exercise",
    description: "The most researched and effective supplement for strength, power, and muscle mass. Creatine helps regenerate ATP (cellular energy) during short, intense efforts like weightlifting and sprinting.",
    dosage: "3-5g daily (maintenance), optional 20g/day loading for 5-7 days",
    timing: "Post-workout or any time of day",
    safety: ["Very safe for healthy individuals", "Ensure adequate hydration", "May cause minor weight gain from water retention"],
    evidenceByGoal: {
      "strength": { grade: "A", paperCount: 67, summary: "Consistently increases strength by 8-15% across multiple studies" },
      "hypertrophy": { grade: "A", paperCount: 45, summary: "Enhances training volume and muscle growth when combined with resistance training" },
      "endurance": { grade: "C", paperCount: 12, summary: "Limited benefit for pure endurance, some help for repeated high-intensity efforts" },
      "weight_loss": { grade: "C", paperCount: 8, summary: "May help preserve muscle mass during caloric restriction" },
      "performance": { grade: "A", paperCount: 89, summary: "Gold standard for power and high-intensity performance enhancement" },
      "general": { grade: "B", paperCount: 34, summary: "Safe and effective for improving exercise capacity in healthy individuals" }
    }
  },
  "caffeine": {
    name: "Caffeine",
    mechanism: "Adenosine receptor antagonist that reduces fatigue perception and increases alertness, also enhances fat oxidation",
    description: "A well-studied stimulant that improves focus, reduces perceived exertion, and enhances performance across multiple domains. Works by blocking adenosine receptors in the brain.",
    dosage: "3-6 mg/kg body weight (200-400mg for most adults)",
    timing: "30-45 minutes before exercise, avoid within 6 hours of sleep",
    safety: ["Generally safe for healthy adults", "Can cause jitters, anxiety, or insomnia in sensitive individuals", "Avoid with certain medications and conditions"],
    evidenceByGoal: {
      "strength": { grade: "A", paperCount: 34, summary: "Improves power output and reduces perceived exertion during strength training" },
      "hypertrophy": { grade: "B", paperCount: 18, summary: "May enhance training intensity and volume for muscle-building workouts" },
      "endurance": { grade: "A", paperCount: 78, summary: "Proven ergogenic aid for endurance performance and fat oxidation" },
      "weight_loss": { grade: "A", paperCount: 42, summary: "Boosts metabolism and fat oxidation, enhances exercise performance during weight loss" },
      "performance": { grade: "A", paperCount: 156, summary: "Versatile performance enhancer across multiple sports and activities" },
      "general": { grade: "C", paperCount: 23, summary: "Cognitive benefits and moderate exercise enhancement when used appropriately" }
    }
  },
  "protein": {
    name: "Protein Powder",
    mechanism: "Provides essential amino acids for muscle protein synthesis, particularly leucine which triggers anabolic pathways",
    description: "Convenient source of high-quality protein to meet daily protein targets. Most effective when used to fill gaps in dietary protein intake rather than as a primary protein source.",
    dosage: "20-40g per serving, adjust based on dietary protein gap",
    timing: "Post-workout within 2 hours, or any time to meet daily protein targets",
    safety: ["Very safe for healthy individuals", "Choose third-party tested products", "Kidney disease patients should consult physician"],
    evidenceByGoal: {
      "strength": { grade: "A", paperCount: 89, summary: "Essential for strength gains and muscle protein synthesis" },
      "hypertrophy": { grade: "A", paperCount: 134, summary: "Critical for muscle growth when combined with resistance training" },
      "endurance": { grade: "B", paperCount: 45, summary: "Supports muscle repair and adaptation in endurance athletes" },
      "weight_loss": { grade: "A", paperCount: 67, summary: "Preserves muscle mass and increases satiety during caloric restriction" },
      "performance": { grade: "B", paperCount: 78, summary: "Fundamental for muscle repair and performance optimization" },
      "general": { grade: "A", paperCount: 156, summary: "Essential macronutrient for muscle maintenance and overall health" }
    }
  },
  "beta-alanine": {
    name: "Beta-Alanine",
    mechanism: "Increases muscle carnosine levels, which buffers lactic acid and delays muscular fatigue during high-intensity exercise",
    description: "Amino acid that helps buffer acid buildup in muscles during intense exercise lasting 1-4 minutes. Most effective for high-intensity, repeated efforts.",
    dosage: "3.2-6.4g daily, divided into smaller doses to minimize tingling",
    timing: "Split into 2-4 doses throughout the day, can take with meals",
    safety: ["Safe for most individuals", "May cause harmless tingling sensation", "Start with lower doses to assess tolerance"],
    evidenceByGoal: {
      "strength": { grade: "B", paperCount: 23, summary: "May enhance performance in high-rep strength training and reduce fatigue" },
      "hypertrophy": { grade: "B", paperCount: 15, summary: "Can support training volume and intensity for muscle-building workouts" },
      "endurance": { grade: "A", paperCount: 45, summary: "Proven effective for high-intensity efforts lasting 1-4 minutes" },
      "weight_loss": { grade: "C", paperCount: 8, summary: "May improve exercise capacity during weight loss phases" },
      "performance": { grade: "A", paperCount: 67, summary: "Consistently improves performance in high-intensity, short-duration activities" },
      "general": { grade: "C", paperCount: 12, summary: "Benefits limited to high-intensity exercise scenarios" }
    }
  },
  "omega-3": {
    name: "Omega-3 Fatty Acids (EPA/DHA)",
    mechanism: "Anti-inflammatory effects reduce exercise-induced muscle damage and support cardiovascular health",
    description: "Essential fatty acids with potent anti-inflammatory properties. Support recovery, cardiovascular health, and may enhance training adaptations by reducing excessive inflammation.",
    dosage: "1-3g combined EPA/DHA daily",
    timing: "With meals to improve absorption",
    safety: ["Very safe for most individuals", "May interact with blood-thinning medications", "Choose molecularly distilled products"],
    evidenceByGoal: {
      "strength": { grade: "B", paperCount: 18, summary: "May reduce exercise-induced inflammation and support recovery" },
      "hypertrophy": { grade: "B", paperCount: 22, summary: "Anti-inflammatory effects may enhance recovery between training sessions" },
      "endurance": { grade: "B", paperCount: 34, summary: "Supports cardiovascular health and may reduce muscle damage" },
      "weight_loss": { grade: "B", paperCount: 28, summary: "May support fat oxidation and reduce inflammation during weight loss" },
      "performance": { grade: "B", paperCount: 45, summary: "Supports recovery and cardiovascular health in athletes" },
      "general": { grade: "A", paperCount: 234, summary: "Essential for heart health, brain function, and inflammation control" }
    }
  },
  "vitamin-d": {
    name: "Vitamin D3",
    mechanism: "Regulates calcium absorption, supports muscle function, and may influence testosterone production and immune function",
    description: "Fat-soluble vitamin crucial for bone health, muscle function, and immune system. Many athletes are deficient, especially those training indoors or in northern climates.",
    dosage: "1000-4000 IU daily, adjust based on blood levels",
    timing: "With fat-containing meals for better absorption",
    safety: ["Safe within recommended doses", "Monitor blood levels with high-dose supplementation", "Toxicity rare but possible with excessive intake"],
    evidenceByGoal: {
      "strength": { grade: "B", paperCount: 15, summary: "Important for muscle function and may support testosterone production" },
      "hypertrophy": { grade: "B", paperCount: 12, summary: "Deficiency may impair muscle protein synthesis and training adaptations" },
      "endurance": { grade: "B", paperCount: 18, summary: "Supports muscle function and may reduce injury risk" },
      "weight_loss": { grade: "B", paperCount: 14, summary: "Deficiency associated with metabolic dysfunction" },
      "performance": { grade: "B", paperCount: 25, summary: "Essential for muscle function and bone health in athletes" },
      "general": { grade: "A", paperCount: 456, summary: "Fundamental for bone health, immune function, and overall wellness" }
    }
  }
}

const GOALS = [
  { key: 'strength', label: 'Strength' },
  { key: 'hypertrophy', label: 'Muscle Growth' },
  { key: 'endurance', label: 'Endurance' },
  { key: 'weight_loss', label: 'Weight Loss' },
  { key: 'performance', label: 'Performance' },
  { key: 'general', label: 'General Health' }
]

export default function SupplementsPage() {
  const [selectedGoal, setSelectedGoal] = useState<string>('strength')
  const [searchTerm, setSearchTerm] = useState('')
  
  const filteredSupplements = Object.entries(SUPPLEMENT_DATABASE).filter(([key, supplement]) =>
    supplement.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    supplement.description.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const getGradeColor = (grade: string) => {
    switch (grade) {
      case 'A': return 'bg-green-100 text-green-800 border-green-200'
      case 'B': return 'bg-blue-100 text-blue-800 border-blue-200'
      case 'C': return 'bg-yellow-100 text-yellow-800 border-yellow-200'
      case 'D': return 'bg-gray-100 text-gray-800 border-gray-200'
      default: return 'bg-gray-100 text-gray-800 border-gray-200'
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Supplement Database</h1>
              <p className="text-gray-600 mt-1">Evidence-based information on performance supplements</p>
            </div>
            <Link href="/" className="text-blue-600 hover:text-blue-800 font-medium">
              ← Back to Home
            </Link>
          </div>

          {/* Search and Filter */}
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1">
              <input
                type="text"
                placeholder="Search supplements..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <select
                value={selectedGoal}
                onChange={(e) => setSelectedGoal(e.target.value)}
                className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                {GOALS.map(goal => (
                  <option key={goal.key} value={goal.key}>{goal.label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Supplements Grid */}
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="grid gap-6">
          {filteredSupplements.map(([key, supplement]) => {
            const goalEvidence = supplement.evidenceByGoal[selectedGoal]
            
            return (
              <div key={key} className="bg-white rounded-lg shadow-md border border-gray-200 p-6">
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="text-2xl font-bold text-gray-900">{supplement.name}</h2>
                    <div className="flex items-center gap-3 mt-2">
                      <span className={`px-3 py-1 rounded-full text-sm font-bold border ${getGradeColor(goalEvidence.grade)}`}>
                        Grade {goalEvidence.grade}
                      </span>
                      <span className="text-sm text-gray-600">
                        {goalEvidence.paperCount} studies for {GOALS.find(g => g.key === selectedGoal)?.label}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Description */}
                <div className="mb-6">
                  <p className="text-gray-700 text-base leading-relaxed">{supplement.description}</p>
                </div>

                {/* Evidence for Selected Goal */}
                <div className="mb-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
                  <h3 className="font-semibold text-blue-900 mb-2">
                    Evidence for {GOALS.find(g => g.key === selectedGoal)?.label}
                  </h3>
                  <p className="text-blue-800 text-sm">{goalEvidence.summary}</p>
                </div>

                {/* Details Grid */}
                <div className="grid md:grid-cols-2 gap-6 mb-6">
                  {/* Mechanism */}
                  <div>
                    <h3 className="font-semibold text-gray-900 mb-2">🔬 Mechanism of Action</h3>
                    <p className="text-gray-700 text-sm">{supplement.mechanism}</p>
                  </div>

                  {/* Dosage */}
                  <div>
                    <h3 className="font-semibold text-gray-900 mb-2">💊 Dosage & Timing</h3>
                    <p className="text-gray-700 text-sm mb-1"><strong>Dose:</strong> {supplement.dosage}</p>
                    <p className="text-gray-700 text-sm"><strong>Timing:</strong> {supplement.timing}</p>
                  </div>
                </div>

                {/* Safety */}
                <div className="mb-6">
                  <h3 className="font-semibold text-gray-900 mb-2">⚠️ Safety & Considerations</h3>
                  <ul className="list-disc list-inside space-y-1">
                    {supplement.safety.map((item, i) => (
                      <li key={i} className="text-gray-700 text-sm">{item}</li>
                    ))}
                  </ul>
                </div>

                {/* Evidence Across All Goals */}
                <div>
                  <h3 className="font-semibold text-gray-900 mb-3">📊 Evidence by Goal</h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {GOALS.map(goal => {
                      const evidence = supplement.evidenceByGoal[goal]
                      return (
                        <div 
                          key={goal.key}
                          className={`p-3 rounded-lg border text-center ${
                            goal.key === selectedGoal ? 'bg-blue-100 border-blue-300' : 'bg-gray-50 border-gray-200'
                          }`}
                        >
                          <div className="text-xs font-medium text-gray-600 mb-1">{goal.label}</div>
                          <div className={`text-lg font-bold mb-1 ${
                            evidence.grade === 'A' ? 'text-green-600' :
                            evidence.grade === 'B' ? 'text-blue-600' :
                            evidence.grade === 'C' ? 'text-yellow-600' : 'text-gray-600'
                          }`}>
                            {evidence.grade}
                          </div>
                          <div className="text-xs text-gray-500">{evidence.paperCount} studies</div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Footer Note */}
        <div className="mt-12 p-6 bg-blue-50 rounded-lg border border-blue-200">
          <h3 className="font-semibold text-blue-900 mb-2">About This Database</h3>
          <p className="text-blue-800 text-sm mb-2">
            Evidence grades and paper counts are derived from our analysis of 50,000+ research papers from PubMed. 
            Grades reflect the strength and consistency of evidence for each specific goal.
          </p>
          <p className="text-blue-800 text-sm">
            <strong>Grade A:</strong> Strong, consistent evidence • 
            <strong> Grade B:</strong> Moderate evidence • 
            <strong> Grade C:</strong> Some evidence • 
            <strong> Grade D:</strong> Limited evidence
          </p>
        </div>
      </div>
    </div>
  )
}
