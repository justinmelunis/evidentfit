# How EvidentFit Works

## Our Philosophy: Evidence First, Always

EvidentFit is built on one core principle: **every recommendation must link directly to peer-reviewed research**. We don't cherry-pick studies to support predetermined conclusions. We don't let commission rates influence what we recommend. We start with the evidence and let that guide everything else.

### Why This Matters
The supplement industry is full of marketing hype, proprietary blends, and exaggerated claims. We believe you deserve better: transparent, research-backed guidance you can verify yourself.

### Our Commitment
- **Transparent sourcing**: Every claim links to a specific PubMed study
- **Editorial independence**: Research drives recommendations, not affiliate commissions
- **Safety first**: Drug interactions, contraindications, and safety warnings are built into every recommendation
- **Honest about limitations**: If evidence is weak or missing, we tell you

---

## Part 1: Publication Selection & Curation

### Where Our Research Comes From

**Source**: PubMed / MEDLINE  
The U.S. National Library of Medicine's database of 35+ million peer-reviewed biomedical studies.

**What We Include:**
- ✅ Human studies on resistance training and athletic performance supplements
- ✅ Published, peer-reviewed research from established journals
- ✅ Studies measuring outcomes that matter: strength, muscle mass, performance, recovery, body composition
- ✅ Multiple study types: meta-analyses, RCTs, crossover trials, observational studies

**What We Exclude:**
- ❌ Animal studies (except for mechanistic context)
- ❌ Industry marketing materials and non-peer-reviewed sources
- ❌ Environmental/pollution research (e.g., nitrogen dioxide air quality studies)
- ❌ Studies with severe methodological flaws

**Current Database**: ~8,000 carefully curated research papers, updated monthly.

### How We Evaluate Quality

Not all studies are created equal. We assess research using multiple objective criteria:

#### 1. Study Design Quality
Research designs are ranked by strength of evidence:
- **Meta-analyses & systematic reviews** (highest): Synthesize findings across multiple studies
- **Randomized controlled trials (RCTs)**: Gold standard for testing interventions  
- **Crossover studies**: Strong within-subject designs
- **Observational studies**: Useful context but lower causal certainty

#### 2. Sample Size & Statistical Power
- Larger, well-powered studies carry more weight
- We prioritize double-blind, placebo-controlled designs
- Studies with clear inclusion/exclusion criteria and defined populations

#### 3. Publication Quality
- Journal reputation and peer review rigor
- Author credentials and potential conflicts of interest
- Replication by independent research groups

#### 4. Recency vs. Foundational Work
- Recent studies reflect current methodologies
- Seminal older papers that established the evidence base remain valuable
- We balance both to give you the full picture

### Balanced Coverage Strategy

To prevent our database from being dominated by a few over-studied supplements, we use dynamic scoring:

```
┌────────────────────────────────────────────────────────────┐
│         RESEARCH CURATION PROCESS                          │
└────────────────────────────────────────────────────────────┘

  PubMed Query
       ↓
  ~12,000 Candidate Papers
       ↓
┌─────────────────────┐
│ Quality Scoring     │ → Study design (meta > RCT > crossover)
│ (Phase 1)           │ → Sample size and duration
│                     │ → Journal quality
│                     │ → Recency
└─────────────────────┘
       ↓
┌─────────────────────┐
│ Diversity Scoring   │ → Prevent over-representation
│ (Phase 2)           │ → Ensure coverage of:
│                     │   • Multiple supplements
│                     │   • Different populations
│                     │   • Various goals
└─────────────────────┘
       ↓
  Final Selection: ~8,000 Papers
  Balanced, high-quality, comprehensive
```

**Result**: Our recommendations reflect comprehensive evidence across the supplement landscape, not just the most-studied topics.

---

## Part 2: Research Chat Agent

### How the Chat Agent Works

When you ask a question about supplements, here's what happens:

```
┌─────────────────────────────────────────────────────────────────┐
│                    RESEARCH CHAT FLOW                            │
└─────────────────────────────────────────────────────────────────┘

  Your Question
       ↓
  "What does research say about creatine for strength?"
       ↓
┌─────────────────────┐
│  STEP 1: Search     │  → Semantic search across 8,000+ papers
│  Retrieve Papers    │  → Returns top 10-15 most relevant studies
└─────────────────────┘
       ↓
  [Paper 1: "Creatine supplementation and resistance training..."]
  [Paper 2: "Effects of creatine on strength in trained athletes..."]
  [Paper 3: "Meta-analysis of creatine monohydrate efficacy..."]
       ↓
┌─────────────────────┐
│  STEP 2: Synthesize │  → AI reads retrieved papers only
│  Evidence (AI)      │  → Cannot cite papers it didn't retrieve
└─────────────────────┘
       ↓
┌─────────────────────┐
│  STEP 3: Response   │  → Clear answer with evidence grades
│  with Citations     │  → Direct PubMed links for every claim
└─────────────────────┘
       ↓
  Your Answer + Citations
```

#### What Happens at Each Step

**Step 1: Semantic Search**
Your question is converted into a mathematical representation (embedding) and matched against our 8,000+ paper database. We retrieve the 10-15 most relevant studies for your specific question.

**Step 2: Evidence Synthesis**
An AI model (GPT-4o-mini via Azure AI Foundry) reads the retrieved papers and synthesizes findings into a clear, accurate answer. The AI is strictly limited to citing papers it actually retrieved—it cannot invent citations.

**Step 3: Citation & Transparency**
Every claim in the response links to specific studies. You get:
- Study title and authors
- Journal and publication year
- Study design (meta-analysis, RCT, etc.)
- Direct PubMed link to verify the research yourself

### What the Chat Agent Can Do
- Answer specific questions about individual supplements
- Explain mechanisms of action based on research
- Compare supplements for specific goals
- Identify potential side effects and contraindications mentioned in research
- Point you to the strongest evidence for or against a supplement

### What It Cannot Do
- ❌ Provide medical advice or diagnose conditions
- ❌ Recommend dosing without you using the Stack Planner
- ❌ Cite research it hasn't retrieved (no hallucinations)
- ❌ Make claims beyond what the research supports

---

## Part 3: Personalized Stack Generation

The Stack Planner builds a complete, personalized supplement protocol tailored to your unique profile.

### How Stack Generation Works

```
┌─────────────────────────────────────────────────────────────────┐
│                PERSONALIZED STACK GENERATION                     │
└─────────────────────────────────────────────────────────────────┘

  Your Profile + Context
       ↓
  Goal: Muscle growth | Weight: 176 lbs | Age: 28 | Sex: Female
  Context: "I'm vegan and train 5x/week. Interested in creatine."
       ↓
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 1: AI Profile Analysis (Hybrid)                          │
│  ┌────────────┐              ┌─────────────┐                    │
│  │  AI Model  │ ────────────→│ Suggestions │                    │
│  └────────────┘              └─────────────┘                    │
│  Analyzes demographics +     → creatine (asked about)           │
│  context to suggest          → protein (vegan, muscle growth)   │
│  personalized supplements    → b12 (vegan)                      │
│                              → iron (female athlete)            │
│                              → beta-alanine (training 5x/week)  │
└──────────────────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 2: Evidence Validation                                   │
│  Check each AI suggestion against research database:            │
│  ✅ creatine → Grade A (multiple meta-analyses)                 │
│  ✅ protein → Grade A (extensive RCT evidence)                  │
│  ✅ b12 → Grade A (proven deficiency in vegans)                 │
│  ✅ iron → Grade B (women's sports nutrition research)          │
│  ✅ beta-alanine → Grade B (endurance/training research)        │
│  ❌ [Example rejection: "tribulus" → Grade D, filtered out]     │
└──────────────────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 3: Safety Guardrails (Deterministic Rules)              │
│  Hard Blocks:    Age (<18) | Pregnancy | Meds | Conditions     │
│  Dose Caps:      Based on weight, age, pregnancy, conditions   │
│  Interactions:   FDA drug label screening                       │
│  Result: Safe, appropriate recommendations only                 │
└──────────────────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 4: Deterministic Dosing (No AI Math)                     │
│  Evidence-based formulas:                                       │
│  • Creatine: 5g CME/day (weight-adjusted)                      │
│  • Protein: Gap analysis (target - diet intake)                │
│  • B12: 2.4 mcg/day (RDA)                                      │
│  • Iron: 18 mg/day for women (RDA)                             │
│  • Beta-alanine: 3.2-6.4 g/day split doses                     │
└──────────────────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 5: Presentation with Evidence                            │
│                                                                  │
│  ✅ RECOMMENDED (Core)          💡 OPTIONAL (Maybe)            │
│  • Creatine (Grade A)            • Beta-alanine (Grade B)      │
│    Why: Proven strength gains      Why: Training volume boost  │
│    Dose: 5g/day                    Dose: 3.2g 2x daily        │
│    Research: [3 citations]         Research: [2 citations]     │
│  • Protein (Grade A)                                            │
│  • B12 (Grade A - vegan)          🚫 NOT RECOMMENDED            │
│  • Iron (Grade B - female)        • Caffeine                    │
│                                     Reason: Not requested       │
└──────────────────────────────────────────────────────────────────┘
       ↓
  Your Personalized Stack
```

### Detailed Phase Breakdown

#### Phase 1: Profile Analysis (Hybrid AI + Rules)
An AI model analyzes your complete profile to suggest relevant supplements:

**Profile Inputs:**
- Primary goal (strength, muscle growth, endurance, weight loss, performance, general health)
- Weight (for dosing calculations)
- Age (affects metabolism, recovery needs, and appropriate supplements)
- Sex (influences nutrient needs and evidence applicability)
- Dietary preferences (vegan, vegetarian, omnivore)
- Training frequency
- Caffeine sensitivity
- Pregnancy/breastfeeding status
- Medical conditions
- Current medications

**User Context Analysis:**
The AI reads your free-text input to understand:
- Specific supplements you're interested in or concerned about
- Training schedule and lifestyle factors
- Special considerations ("I train fasted," "I have joint pain," etc.)
- Questions about alternative forms or brands

**AI Suggestion Process:**
The AI considers your demographics and context to suggest supplements proven effective for people like you:
- Example: 55-year-old → HMB for muscle preservation
- Example: Vegan female athlete → B12, iron, algae-based omega-3
- Example: "I'm stressed" → Ashwagandha if evidence supports it for your goals

#### Phase 2: Evidence Filtering
AI suggestions are validated against our research database:
- ✅ **Must have Grade A or B evidence** for your specific goal
- ✅ **Must have 2+ supporting studies** from our curated database
- ❌ **Rejected if evidence is weak or missing** (Grade C/D)

This prevents the AI from suggesting supplements without solid research backing.

#### Phase 3: Safety Guardrails (Deterministic Rules)
Every supplement goes through strict safety checks:

**Hard Blocks:**
- Age restrictions (e.g., no stimulants for minors)
- Pregnancy/breastfeeding contraindications  
- Medical condition conflicts (e.g., no caffeine with anxiety disorders)
- Medication interactions (e.g., no stimulants with MAOIs)

**Dose Adjustments:**
- Caffeine sensitivity → Lower dose range
- Pregnancy → FDA/ACOG recommended limits
- Older adults → Age-adjusted dosing
- Medical conditions → Conservative caps

**Interaction Screening:**
Using FDA drug label data, we check for potential supplement-medication interactions and surface warnings.

#### Phase 4: Deterministic Dosing
Dosing is **never done by the AI**—it uses evidence-based formulas:

**Creatine Monohydrate Equivalent (CME) Dosing:**
- All creatine dosing anchored to monohydrate equivalents (the form with the most research)
- Maintenance: 3-5g CME/day based on body weight
- Conversion formulas for alternative forms (anhydrous, HCl)

**Protein Gap Analysis:**
- Calculate your target protein intake based on goal and weight
- Compare to your current dietary intake
- Recommend supplemental protein only if gap ≥ 20g/day
- "Diet-first" philosophy

**Weight-Adjusted Dosing:**
- Caffeine: 3-6 mg/kg based on sensitivity
- Beta-alanine: Fixed dose with split timing
- Other supplements: Evidence-based ranges from research protocols

#### Phase 5: Presentation
Your final stack includes:

**✅ Recommended Supplements:**
- Strong evidence for your goals
- Safe based on your profile
- Clear explanation of why it's recommended
- Precise dosing with timing
- 1-3 supporting research citations per supplement

**💡 Optional Supplements (Maybe):**
- Potential additional benefits but not essential
- You decide if worth adding based on evidence
- Full transparency on strength of evidence

**🚫 Not Recommended:**
- Supplements excluded due to safety concerns
- Supplements with insufficient evidence for your goals
- Clear explanations of why (e.g., "Caffeine excluded due to anxiety diagnosis")

---

## Why Trust EvidentFit?

### 1. Research-Driven, Not Profit-Driven

**Full Disclosure**: We may earn affiliate commissions when you purchase supplements through our links.

**How We Maintain Independence:**
- AI analyzes your profile and the research—commission rates never enter the algorithm
- Supplement companies cannot pay for inclusion or better rankings
- If research doesn't support a supplement, we won't recommend it—no matter how profitable
- We always mention generic options and multiple brands
- Clear labeling of all affiliate relationships

**Our Business Logic**: Your trust is worth more than short-term commissions. If we lose your trust by pushing ineffective supplements, we lose our business.

### 2. Technical Safeguards Against Bias
- AI cannot cite papers it hasn't retrieved from PubMed (no hallucinations)
- Dosing calculations are deterministic, not AI-generated (no math errors)
- Safety guardrails are rule-based, not subject to AI interpretation
- Evidence grades based on objective study characteristics

### 3. Audit Trail
Every recommendation can be traced back to:
- The specific research papers that support it
- The safety rules that were applied
- The dosing formulas used

You can verify our work at every step.

### 4. Conservative by Design
When in doubt, we err on the side of caution:
- Higher evidence standards (Grade A/B only for primary recommendations)
- Comprehensive interaction screening
- Clear warnings about limitations and uncertainties
- "Consult your doctor" for anything remotely medical

---

## Our Limitations

We're honest about what our system can and cannot do:

1. **Abstract-based analysis**: We primarily analyze study abstracts, not always full papers
2. **English-language focus**: Most research we access is published in English
3. **Not medical advice**: We provide evidence-based education, not personalized medical care
4. **Population variability**: Research shows average effects in study populations—individual results may vary
5. **Evolving evidence**: New research may change recommendations; we update monthly but can't catch everything in real-time

---

## How to Use EvidentFit

### 💬 Research Chat
Ask questions and get evidence-based answers with citations.

**Good for:**
- Understanding what research says about specific supplements
- Comparing options for your goals
- Checking for potential interactions
- Diving deep into specific studies

### 🎯 Stack Planner  
Get a complete, personalized supplement protocol.

**Good for:**
- Building a complete supplement routine
- Getting specific dosing for your weight and goals
- Safety screening against your medications and conditions
- Understanding which supplements to prioritize vs. skip

---

## Continuous Improvement

Our methodology evolves as:
- New research is published (monthly updates)
- User feedback identifies gaps or issues
- Better AI models become available
- We learn from real-world use

We're committed to staying current with the science and transparent about our methods.

---

## Questions or Concerns?

We welcome feedback and scrutiny:
- Found an error? Let us know.
- Disagree with an interpretation? We'll explain our reasoning.
- Want to see specific studies? All citations link directly to PubMed.
- Concerned about our business model? We're happy to discuss how we maintain independence.

Contact: [contact@evidentfit.com]

---

## Disclaimer

**EvidentFit provides educational information based on published research. It is not medical advice.**

Always consult with a qualified healthcare provider before starting any supplement regimen, especially if you:
- Have a medical condition
- Take prescription medications  
- Are pregnant or breastfeeding
- Are under 18 years old
- Have a history of adverse reactions to supplements

Individual responses to supplements vary. Published research shows average effects in study populations—your results may differ.

---

*Committed to evidence-based fitness supplementation*

