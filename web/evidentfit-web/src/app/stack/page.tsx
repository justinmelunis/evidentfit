"use client";
import { useState } from "react";

type StackResponse = {
  bucket_key: string;
  profile_sig: any;
  tiers: {
    core: any[];
    optional: any[];
    conditional: any[];
    experimental: any[];
  };
  exclusions: string[];
  safety: string[];
  index_version: string;
  updated_at: string;
};

export default function StackPlanner() {
  const [profile, setProfile] = useState({
    goal: "strength",
    weight_kg: 80,
    caffeine_sensitive: false,
    meds: [] as string[],
    diet: "any",
    training_freq: "med",
    creatine_form: "monohydrate"
  });
  
  const [stack, setStack] = useState<StackResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const getStack = async () => {
    setLoading(true);
    setError("");
    
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io";
      const response = await fetch(`${apiBase}/stack`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ profile })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setStack(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get stack recommendation");
    } finally {
      setLoading(false);
    }
  };

  const renderSupplement = (supp: any, index: number) => (
    <div key={index} className="border rounded p-3 mb-3">
      <div className="flex justify-between items-start mb-2">
        <h4 className="font-semibold text-lg capitalize">{supp.supplement}</h4>
        <span className={`px-2 py-1 rounded text-xs font-medium ${
          supp.evidence === 'A' ? 'bg-green-100 text-green-800' :
          supp.evidence === 'B' ? 'bg-blue-100 text-blue-800' :
          supp.evidence === 'C' ? 'bg-yellow-100 text-yellow-800' :
          'bg-red-100 text-red-800'
        }`}>
          Evidence {supp.evidence}
        </span>
      </div>
      
      <div className="space-y-2">
        {supp.doses.map((dose: any, i: number) => (
          <div key={i} className="text-sm">
            <span className="font-medium">{dose.value} {dose.unit}</span>
            {dose.days && <span className="text-gray-600"> for {dose.days} days</span>}
            {dose.split && <span className="text-gray-600"> ({dose.split})</span>}
          </div>
        ))}
        
        <div className="text-sm text-gray-600">
          <strong>Timing:</strong> {supp.timing}
        </div>
        
        <div className="text-sm text-gray-700">
          <strong>Why:</strong> {supp.why}
        </div>
        
        {supp.notes && supp.notes.length > 0 && (
          <div className="text-sm text-gray-600">
            <strong>Notes:</strong> {supp.notes.join(", ")}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <main className="max-w-4xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-6">EvidentFit Stack Planner</h1>
      
      <div className="grid md:grid-cols-2 gap-8">
        {/* Profile Form */}
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Your Profile</h2>
          
          <div>
            <label className="block text-sm font-medium mb-1">Goal</label>
            <select 
              value={profile.goal} 
              onChange={(e) => setProfile({...profile, goal: e.target.value})}
              className="w-full border rounded px-3 py-2"
            >
              <option value="strength">Strength</option>
              <option value="hypertrophy">Hypertrophy</option>
              <option value="endurance">Endurance</option>
              <option value="weight_loss">Weight Loss</option>
              <option value="general">General Health</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Weight (kg)</label>
            <input 
              type="number" 
              value={profile.weight_kg} 
              onChange={(e) => setProfile({...profile, weight_kg: Number(e.target.value)})}
              className="w-full border rounded px-3 py-2"
              min="40" max="200"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Training Frequency</label>
            <select 
              value={profile.training_freq} 
              onChange={(e) => setProfile({...profile, training_freq: e.target.value})}
              className="w-full border rounded px-3 py-2"
            >
              <option value="low">Low (1-2x/week)</option>
              <option value="med">Medium (3-4x/week)</option>
              <option value="high">High (5-6x/week)</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Creatine Form</label>
            <select 
              value={profile.creatine_form} 
              onChange={(e) => setProfile({...profile, creatine_form: e.target.value})}
              className="w-full border rounded px-3 py-2"
            >
              <option value="monohydrate">Monohydrate</option>
              <option value="anhydrous">Anhydrous</option>
              <option value="hcl">HCL</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Diet</label>
            <select 
              value={profile.diet} 
              onChange={(e) => setProfile({...profile, diet: e.target.value})}
              className="w-full border rounded px-3 py-2"
            >
              <option value="any">Any</option>
              <option value="vegan">Vegan</option>
            </select>
          </div>

          <div className="flex items-center">
            <input 
              type="checkbox" 
              id="caffeine_sensitive"
              checked={profile.caffeine_sensitive} 
              onChange={(e) => setProfile({...profile, caffeine_sensitive: e.target.checked})}
              className="mr-2"
            />
            <label htmlFor="caffeine_sensitive" className="text-sm font-medium">
              Caffeine Sensitive
            </label>
          </div>

          <button 
            onClick={getStack}
            disabled={loading}
            className="w-full bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Getting Stack..." : "Get My Stack"}
          </button>

          {error && (
            <div className="text-red-600 text-sm">{error}</div>
          )}
        </div>

        {/* Stack Results */}
        <div>
          <h2 className="text-xl font-semibold mb-4">Your Stack</h2>
          
          {stack ? (
            <div>
              <div className="mb-4 p-3 bg-gray-50 rounded">
                <div className="text-sm text-gray-600">
                  <strong>Profile:</strong> {stack.profile_sig.goal} training, {stack.profile_sig.weight_kg}kg
                </div>
                <div className="text-sm text-gray-600">
                  <strong>Bucket Key:</strong> {stack.bucket_key}
                </div>
              </div>

              {stack.tiers.core.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-lg font-semibold mb-3 text-green-700">Core Supplements</h3>
                  {stack.tiers.core.map((supp, i) => renderSupplement(supp, i))}
                </div>
              )}

              {stack.tiers.optional.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-lg font-semibold mb-3 text-blue-700">Optional Supplements</h3>
                  {stack.tiers.optional.map((supp, i) => renderSupplement(supp, i))}
                </div>
              )}

              {stack.tiers.conditional.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-lg font-semibold mb-3 text-yellow-700">Conditional Supplements</h3>
                  {stack.tiers.conditional.map((supp, i) => renderSupplement(supp, i))}
                </div>
              )}

              {stack.tiers.experimental.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-lg font-semibold mb-3 text-red-700">Experimental Supplements</h3>
                  {stack.tiers.experimental.map((supp, i) => renderSupplement(supp, i))}
                </div>
              )}

              {stack.safety.length > 0 && (
                <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded">
                  <h4 className="font-semibold text-yellow-800 mb-2">Safety Notes</h4>
                  <ul className="text-sm text-yellow-700">
                    {stack.safety.map((note, i) => (
                      <li key={i}>• {note}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="text-xs text-gray-500 mt-4">
                Generated: {new Date(stack.updated_at).toLocaleString()}
              </div>
            </div>
          ) : (
            <div className="text-gray-500 text-center py-8">
              Fill out your profile and click &quot;Get My Stack&quot; to see your personalized supplement recommendations.
            </div>
          )}
        </div>
      </div>

      <div className="mt-8 p-4 bg-gray-50 rounded">
        <p className="text-sm text-gray-600">
          <strong>Educational only; not medical advice.</strong> Always consult with a healthcare provider before starting any supplement regimen.
        </p>
      </div>
    </main>
  );
}
