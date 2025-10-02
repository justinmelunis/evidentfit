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

**Current Database**: ~8,000 carefully curated research papers, selected from 50,000+ available studies, updated monthly.

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
  50,000+ Candidate Papers Evaluated
  (Iterative processing over multiple cycles)
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
  Highest quality by combined scoring
```

**Result**: We evaluate 50,000+ supplement studies and select only the top 8,000 papers. Our recommendations reflect comprehensive evidence across the supplement landscape, not just the most-studied topics.

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

The Stack Planner builds a complete, personalized supplement protocol tailored to your unique profile using our **three-level evidence banking system**.

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
│  PHASE 1: Three-Level Evidence Banking                          │
│                                                                  │
│  Level 1: Goal × Supplement Evidence (Always cached)           │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ "creatine +     │ ──→│ Grade A         │                    │
│  │  hypertrophy"   │    │ (67 studies)    │                    │
│  └─────────────────┘    └─────────────────┘                    │
│                                                                  │
│  Level 2: Profile-Specific Reasoning (Banking Check)           │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ Generate Key    │ ──→│ Check Cache     │                    │
│  │ "hypertrophy:   │    │ 360 pre-computed│                    │
│  │  medium:female: │    │ combinations    │                    │
│  │  young"         │    │                 │                    │
│  └─────────────────┘    └─────────────────┘                    │
└──────────────────────────────────────────────────────────────────┘
       ↓ (if cached)         ↓ (if not cached)
       │               ┌──────────────────────────────────────────┐
       │               │  LLM Profile Analysis (Generate)         │
       │               │  ┌────────────┐    ┌─────────────┐      │
       │               │  │  AI Model  │ ──→│ Personalized│      │
       │               │  │  + Papers  │    │ Reasoning   │      │
       │               │  └────────────┘    └─────────────┘      │
       │               │  "For your profile (28yo female),       │
       │               │  creatine enhances training capacity    │
       │               │  because studies in female athletes..." │
       │               │  💾 Save to Level 2 cache               │
       │               └──────────────────────────────────────────┘
       │                        ↓
       └────────────────────────┘
                ↓
┌──────────────────────────────────────────────────────────────────┐
│  Level 3: Real-Time Context Analysis (Never cached)             │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ Parse Chat:     │ ──→│ Apply Rules:    │                    │
│  │ "I have anxiety"│    │ Block caffeine  │                    │
│  │ "I'm vegan"     │    │ Add B12, Iron   │                    │
│  │ "Interested in  │    │ Include creatine│                    │
│  │  creatine"      │    │ with details    │                    │
│  └─────────────────┘    └─────────────────┘                    │
└──────────────────────────────────────────────────────────────────┘
                ↓
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 2: Real-Time Personalization                             │
│  Apply conversation context to cached base recommendations:     │
│  • Extract conditions: "I have anxiety" → block caffeine       │
│  • Extract medications: "I take SSRIs" → interaction check     │
│  • Extract preferences: "I'm interested in creatine" → include │
│  • Apply safety rules: pregnancy, age, sensitivities          │
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
│  PHASE 4: Weight-Adjusted Dosing (No AI Math)                   │
│  Evidence-based formulas by weight bin:                        │
│  • Weight bin: "medium" (70-85kg) for 176 lbs                 │
│  • Creatine: 5g CME/day (standard dose for medium weight)     │
│  • Protein: Gap analysis (target 1.8g/kg - current intake)    │
│  • B12: 2.4 mcg/day (RDA, higher for vegans)                 │
│  • Iron: 18 mg/day (female RDA)                               │
│  • Beta-alanine: 6.4g/day split doses (medium weight)         │
└──────────────────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 5: Interactive UI Presentation                           │
│                                                                  │
│  🎯 Your Custom Stack (3 supplements)                          │
│  [Creatine A] [Protein A] [B12 A] ← Interactive summary        │
│                                                                  │
│  Toggle Navigation:                                             │
│  [✅ Recommended (3)] [💡 Optional (2)] [🚫 Not Recommended (1)]│
│                                                                  │
│  Active Section: ✅ RECOMMENDED                                 │
│  ☑ Creatine (Grade A)     📚 Research-backed reasoning         │
│    Why: For your profile (28yo female), creatine enhances      │
│    training capacity because studies show...                   │
│    Dose: 5g/day • Post-workout                                 │
│    Research: [3 PubMed citations with direct links]            │
│                                                                  │
│  ☑ Protein (Grade A)      📊 Gap analysis: 25g supplemental    │
│  ☑ B12 (Grade A)          🌱 Vegan-specific recommendation     │
│                                                                  │
│  💡 Checkbox system allows custom stack building               │
│  🔄 Toggle between sections for full transparency              │
└──────────────────────────────────────────────────────────────────┘
       ↓
  Your Evidence-Based, Personalized Stack
```

### Detailed Phase Breakdown

#### Phase 1: Three-Level Evidence Banking

**Why Three Levels?**
Our banking system operates at three distinct levels to balance performance, personalization, and accuracy:

**Level 1: Goal × Supplement Evidence (216 combinations)**
- Pre-computed evidence grades for every supplement × goal combination
- Based on dynamic analysis of research papers for goal-specific outcomes
- Updated monthly when new research is ingested
- Example: "Creatine + strength = Grade A (67 studies), Creatine + endurance = Grade C (12 studies)"

**Level 2: Profile-Specific Reasoning (360 combinations)**
- Personalized "why" explanations based on demographics
- Generated by LLM analysis of research papers tailored to user profile
- Your profile maps to one of 360 pre-computed combinations:
  - **6 Goals**: Strength, muscle growth, endurance, weight loss, performance, general health
  - **5 Weight Bins**: XS (<60kg), Small (60-70kg), Medium (70-85kg), Large (85-100kg), XL (100kg+)
  - **3 Sex Categories**: Male, female, other/unspecified  
  - **4 Age Bins**: Minor (13-17), young (18-29), adult (30-49), mature (50+)

**Level 3: Real-Time Context Analysis (Never cached)**
- Dynamic modifications based on conversation context
- Text parsing for conditions, medications, specific interests
- Applied in real-time for maximum personalization

**Banking Key Example:**
- 28-year-old, 176 lb (80kg) female, muscle growth goal
- **Key**: `"hypertrophy:medium:female:young"`
- **Result**: Pre-computed base recommendations with evidence grades

**Cache Hit vs. Miss:**
- **Cache Hit** (99% of cases): Instant base recommendations + real-time personalization
- **Cache Miss** (rare profiles): Full AI analysis + evidence validation + save to cache

#### Phase 1B: AI Profile Analysis (For Cache Misses or New Profiles)
When a profile combination hasn't been pre-computed, an AI model analyzes your complete profile to suggest relevant supplements:

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

#### Phase 2: Real-Time Personalization

**Text Analysis:**
Your conversational input is analyzed to extract:
- **Medical conditions**: "I have anxiety" → caffeine contraindication
- **Medications**: "I take blood pressure meds" → interaction screening
- **Specific interests**: "I'm curious about creatine" → include in recommendations
- **Lifestyle factors**: "I train fasted" → timing adjustments
- **Concerns**: "I'm worried about side effects" → conservative dosing

**Dynamic Adjustments:**
The cached base recommendations are modified in real-time:
- **Add supplements** mentioned in your text (if evidence supports them)
- **Remove supplements** contraindicated by conditions/medications
- **Adjust doses** based on sensitivities or medical conditions
- **Update explanations** to address your specific context

**Why This Approach Works:**
- **Fast**: Base recommendations are pre-computed (instant)
- **Personalized**: Real-time adjustments based on your unique situation
- **Safe**: All adjustments go through the same safety guardrails
- **Consistent**: Same base profile gets same foundation, personalized by context

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

#### Phase 4: Weight-Adjusted Dosing (No AI Math)
Dosing is **never done by the AI**—it uses evidence-based formulas tailored to your weight bin:

**Weight Bin System:**
Your weight determines dosing ranges proven effective in research:
- **XS (<60kg)**: Lower doses, conservative approach
- **Small (60-70kg)**: Standard doses with some adjustments  
- **Medium (70-85kg)**: Standard research-based doses (most studies)
- **Large (85-100kg)**: Higher doses for weight-dependent supplements
- **XL (100kg+)**: Maximum effective doses, loading phases where beneficial

**Supplement-Specific Dosing:**

**Creatine Monohydrate Equivalent (CME):**
- XS/Small: 3g CME/day | Medium: 5g CME/day | Large/XL: 5-7g CME/day
- All dosing anchored to monohydrate equivalents (the form with the most research)
- Conversion formulas for alternative forms (anhydrous, HCl)

**Protein Gap Analysis:**
- Calculate target: 1.6-2.2g/kg based on goal and weight
- Compare to your reported dietary intake
- Recommend supplemental protein only if gap ≥ 20g/day
- "Diet-first" philosophy: food sources prioritized

**Other Weight-Adjusted Supplements:**
- **Caffeine**: 3-6 mg/kg (capped by sensitivity and conditions)
- **Beta-alanine**: 3.2g (small) to 6.4g (large) split into multiple doses
- **Citrulline**: 6g (small) to 8g (large) pre-workout
- **HMB**: 3g daily (all weights) with meals

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

## Banking System: Speed Meets Personalization

### How We Balance Speed and Customization

**The Challenge**: Providing both fast responses and deeply personalized recommendations.

**Our Solution**: A **three-level evidence banking system** that pre-computes evidence at different granularities while allowing real-time personalization.

### Three-Level Architecture

#### **Level 1: Goal × Supplement Evidence Banking**
- **What**: Evidence grades (A/B/C/D) for each supplement × goal combination
- **Cached**: 216 combinations (6 goals × 36 supplements)
- **Source**: Dynamic analysis of research papers for goal-specific outcomes
- **Updated**: Monthly when new research is ingested
- **Example**: "Creatine for strength = Grade A, Creatine for endurance = Grade C"

#### **Level 2: Profile-Specific Reasoning Banking**
- **What**: Personalized "why" explanations based on demographics and research
- **Cached**: 360 profile combinations (goal × weight bin × sex × age bin)
- **Source**: LLM analysis of retrieved papers tailored to user demographics
- **Updated**: When evidence base changes or new profiles are encountered
- **Example**: "For your profile (28yo male, strength), creatine enhances power output because studies in male athletes show 5g/day increases 1RM by 8-15%"

#### **Level 3: Real-Time Adjustments**
- **What**: Dynamic modifications based on conversation context
- **Cached**: Never (always real-time)
- **Source**: Text parsing + safety guardrails + user preferences
- **Applied**: Conditions, medications, specific supplement interests
- **Example**: "Caffeine excluded due to anxiety condition mentioned in chat"

### Technical Implementation

**360 Pre-Computed Profiles:**
- Every combination of goal × weight bin × sex × age bin
- Each profile contains base supplement recommendations with evidence grades
- Updated monthly as new research is published
- Stored for instant retrieval (< 100ms response time)

**Real-Time Layer:**
- Your conversational input adds personalization on top of the base profile
- Medical conditions, medications, and preferences modify recommendations
- Safety guardrails applied to all adjustments
- Final dosing calculated using your exact weight

**Storage Efficiency:**
- 360 profiles × ~6KB each = ~2.2MB total storage
- Fits easily within our infrastructure limits
- Allows for comprehensive coverage without performance impact

### Benefits for You

**⚡ Speed**: Recommendations in seconds, not minutes  
**🎯 Consistency**: Same profile always gets same evidence-based foundation  
**🔒 Safety**: All cached recommendations go through the same safety validation  
**📊 Quality**: More time to validate evidence means higher-quality base recommendations  
**🎨 Personalization**: Your unique context still shapes the final recommendations  

### What Gets Banked vs. What's Real-Time

**Banked (Pre-Computed):**
- Base supplement candidates for your demographic
- Evidence grades based on research for your goal
- Standard dosing ranges for your weight category
- Core safety contraindications

**Real-Time (Personalized):**
- Medical conditions and medication interactions
- Specific supplement requests from your conversation
- Dose adjustments for sensitivities
- Explanations tailored to your context
- Final safety screening with your exact profile

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

## Interactive Features & User Experience

### Stack Planner Interface

Our Stack Planner provides an interactive, user-friendly interface for exploring and customizing supplement recommendations:

#### **Toggle Navigation System**
- **Three clear sections**: Recommended, Optional, and Not Recommended supplements
- **One section at a time**: Reduces cognitive load and improves focus
- **Live counts**: See how many supplements are in each category
- **Easy switching**: Toggle between sections to explore all options

#### **Interactive Checkbox System**
- **Custom stack building**: Check/uncheck any supplement from any tier
- **Smart initialization**: Recommended supplements are pre-selected
- **Live summary**: See your custom stack at the top with evidence grades
- **Quick removal**: Remove supplements directly from the summary
- **Full transparency**: Access all details (dosing, research, reasoning) for every supplement

#### **Evidence-Based Details**
- **Research-backed reasoning**: Every "why" explanation is generated from actual research papers
- **Evidence grades**: A/B/C/D grades based on study quality and consistency
- **Supporting citations**: Direct links to PubMed studies for verification
- **Personalized explanations**: Reasoning tailored to your demographics and goals

### Supplement Database

For users who want to research independently, we provide a comprehensive supplement database:

#### **Individual Supplement Pages** (`/supplements`)
- **Mechanism of action**: How each supplement works in the body
- **Evidence by goal**: See how research applies to different fitness goals
- **Dosing and timing**: Evidence-based recommendations
- **Safety considerations**: Contraindications and precautions
- **Goal-specific filtering**: View evidence grades for your specific goals

#### **Search and Discovery**
- **Search functionality**: Find supplements by name or description
- **Goal filtering**: See how evidence changes based on your objectives
- **Paper counts**: Transparent about the research volume behind each grade
- **Direct citations**: Every claim links to specific PubMed studies

### Mobile-First Design

All features are optimized for mobile devices with:
- **Responsive layouts**: Clean display on phones, tablets, and desktops
- **Touch-friendly controls**: Easy checkbox and button interactions
- **Readable typography**: Clear text at all screen sizes
- **Fast loading**: Optimized performance on slower connections

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

