# EvidentFit Methodology

## Our Approach to Evidence-Based Supplement Guidance

EvidentFit is built on a foundation of peer-reviewed research from PubMed. We don't make up recommendations—we extract them from thousands of published studies and present them with full transparency so you can see exactly where our guidance comes from.

## The Three-Step Process

###  1. **Discovery & Curation**

We continuously monitor PubMed for research on resistance training supplements. Our automated system searches for studies on:

**Supplements we track:**
- Creatine, caffeine, beta-alanine
- Citrulline, nitrate, protein
- HMB, BCAA, betaine, taurine, carnitine
- And 10+ other evidence-backed options

**Training outcomes we focus on:**
- Strength (1RM, maximal strength)
- Hypertrophy (lean mass, muscle size)
- Power & performance (vertical jump, sprint performance)
- Endurance (VO₂ max, time to exhaustion)
- Recovery (DOMS, muscle damage markers)

**What we exclude:**
- Animal studies (we focus on human research)
- Pollution/environmental studies (e.g., nitrogen dioxide research)
- Non-peer-reviewed sources
- Industry marketing materials

### 2. **Quality Assessment**

Not all research is created equal. We evaluate every paper using objective, reproducible criteria:

#### Study Design Quality (Most Important)
- **Meta-analyses**: Highest priority—synthesize results from multiple studies
- **Randomized Controlled Trials (RCTs)**: Gold standard for interventions
- **Crossover studies**: Good within-subject control
- **Cohort studies**: Useful for long-term outcomes
- **Other designs**: Lower priority but still considered

#### Sample Size
- Larger studies get higher scores
- Studies with 1000+ participants rated highest
- Small studies (N<20) given low priority but not excluded

#### Methodological Rigor
Bonus points for:
- Double-blind design
- Placebo-controlled
- Randomized assignment
- Controlled trial methodology
- Systematic review/meta-analysis protocols

#### Publication Venue
Small bonus for publication in high-impact sports nutrition and exercise physiology journals (e.g., *Sports Medicine*, *Medicine & Science in Sports & Exercise*, *Journal of Applied Physiology*)

#### Recency
- Recent studies (2020+) prioritized
- Older research still valued but given lower priority

### 3. **Diversity Balancing**

To prevent our database from being dominated by over-studied topics (like creatine for strength in trained athletes), we use **combination-aware selection**:

**What we balance:**
- Supplement variety (not just creatine papers)
- Training goals (strength, hypertrophy, endurance, weight loss)
- Population types (trained athletes, untrained individuals, older adults, clinical populations)
- Study types (mix of meta-analyses, RCTs, and other designs)
- Journal diversity (avoid over-reliance on single publication venues)

**How it works:**
- We analyze existing papers for representation gaps
- Under-represented combinations get a boost (e.g., "beta-alanine + endurance + older adults")
- Over-represented combinations get deprioritized (e.g., "creatine + strength + RCT")
- **Quality safeguard**: Low-quality papers never get selected purely for diversity

**Result**: Our corpus of ~8,000 papers provides balanced coverage across supplements, goals, and populations while maintaining high quality standards.

## What You Get

### Transparent Citations
Every recommendation comes with:
- **Study title** and journal
- **PubMed ID** and direct link
- **Study type** (meta-analysis, RCT, etc.)
- **Key findings** relevant to your query

### Evidence Grades
We assign evidence grades based on the strength and consistency of research:
- **Grade A**: Strong evidence from multiple high-quality studies (meta-analyses, large RCTs)
- **Grade B**: Moderate evidence from multiple studies with some limitations
- **Grade C**: Limited or mixed evidence; more research needed
- **Grade D**: Insufficient evidence or conflicting findings

### Personalized Recommendations
Our AI considers:
- **Your training goal** (strength, hypertrophy, endurance, weight loss)
- **Your experience level** and training frequency
- **Your weight** (for dosing calculations)
- **Caffeine sensitivity**
- **Medications** you're taking (for interaction checking)
- **Dietary preferences** (vegan options, protein gap analysis)

### Safety First
- We check for drug-supplement interactions using FDA data
- We highlight contraindications and side effects from the research
- We recommend consulting a healthcare provider for medical conditions
- All outputs include disclaimer: "Educational only; not medical advice"

## Our Data Sources

### Primary: PubMed / MEDLINE
- **What it is**: The U.S. National Library of Medicine's database of biomedical literature
- **Coverage**: 35+ million citations dating back to 1946
- **Why we use it**: Gold standard for peer-reviewed biomedical research
- **Update frequency**: We run monthly updates to capture new research

### Secondary: FDA Drug Labels (for Interactions)
- **What it is**: Official FDA-approved drug labels
- **Purpose**: Identify potential supplement-medication interactions
- **How we use it**: Keyword scanning for contraindications with supplements

## What We Don't Do

❌ **Cherry-pick studies** to support predetermined conclusions
❌ **Cite research we haven't retrieved** from PubMed
❌ **Make dosing calculations** with AI (we use deterministic formulas from research)
❌ **Recommend proprietary blends** or unproven compounds
❌ **Accept sponsorships** from supplement companies
❌ **Provide medical advice** (always consult healthcare providers)

## Limitations & Transparency

We believe in being upfront about what our system can and cannot do:

### Current Limitations
1. **Abstract-only analysis**: We analyze abstracts, not full papers (storage constraints)
2. **No real-time dosing adjustments**: Dosing is based on published protocols, not individual optimization
3. **English-language bias**: Most PubMed papers are in English
4. **Regex extraction**: We use pattern matching to extract sample sizes, dosing, etc.—may occasionally misread
5. **No intervention ranking**: We present evidence but don't say "Supplement X is better than Y" without studies directly comparing them

### What We're Working On
- **Full-text access**: Expanding to analyze complete papers
- **Citation networks**: Using paper citation patterns to identify seminal research
- **Author reputation**: Factoring in researcher track records
- **Multilingual support**: Expanding beyond English-language research
- **Longitudinal tracking**: Following supplement research trends over time

## Technical Details

For those interested in the technical implementation:

### Our Stack
- **Data ingestion**: Python-based PubMed E-utilities client
- **Storage**: Azure AI Search (text-based, ~8,000 papers)
- **AI/LLM**: Azure AI Foundry (GPT-4o-mini for composition)
- **API**: FastAPI with server-sent events (SSE) for streaming
- **Frontend**: Next.js static site
- **Infrastructure**: Azure Container Apps

### Scoring Algorithm
Each paper receives two scores:

**Reliability Score (0-20+ points)**:
- Study type: 2-10 points
- Sample size: 0-5 points
- Quality indicators: 0-8+ points
- Journal impact: 0-2 points
- Recency: 0-1 points
- Diversity bonus: ±3 points

**Combination Score (±10 points)**:
- Dynamic adjustment based on representation gaps
- Quality-capped (low-quality papers can't get high diversity bonus)

**Final Score = Reliability + Combination**

Top ~8,000 papers selected and updated monthly.

### Code & Reproducibility
- All code is versioned in GitLab
- Environment variables control behavior (no hardcoded secrets)
- Docker containers ensure reproducible builds
- Watermark system tracks incremental updates

## Why Trust EvidentFit?

### 1. **Fully Transparent**
Every recommendation links directly to PubMed. You can read the studies yourself.

### 2. **No Commercial Conflicts**
We're not owned by a supplement company. We don't sell supplements. We don't take affiliate commissions.

### 3. **Evidence-First**
Our AI can only cite papers it has actually retrieved. No hallucinated citations, ever.

### 4. **Quality Over Quantity**
We don't just scrape PubMed—we curate, score, and balance to ensure high-quality, diverse coverage.

### 5. **Conservative Dosing**
Our dosing recommendations come from published protocols, not guesswork. We use evidence-based formulas (e.g., creatine monohydrate equivalent dosing, protein gap analysis).

### 6. **Safety Checks**
We scan for drug interactions and highlight contraindications before giving recommendations.

### 7. **Open About Limitations**
We tell you what we don't know and where evidence is weak or conflicting.

## Questions?

If you have questions about our methodology, want to report an issue, or have suggestions for improvement:
- **Email**: [Your contact email]
- **GitHub/GitLab**: [Link to public repo if applicable]
- **Twitter/X**: [Handle if applicable]

## Disclaimer

EvidentFit provides educational information based on published research. It is **not medical advice**. Always consult with a qualified healthcare provider before starting any supplement regimen, especially if you:
- Have a medical condition
- Take prescription medications
- Are pregnant or breastfeeding
- Are under 18 years old
- Have a history of adverse reactions to supplements

Individual responses to supplements vary. What works in research populations may not work the same for you.

---

*Last updated: October 2025*

