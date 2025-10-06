#!/usr/bin/env python3
"""
Optimized schema for paper indexing focused on bot Q&A capabilities.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import hashlib

@dataclass
class OutcomeItem:
    """Individual outcome measure with dual numeric/text fields."""
    measure: str
    effect_size: Optional[float] = None
    effect_size_text: Optional[str] = None
    p_value_num: Optional[float] = None
    p_value_text: Optional[str] = None
    confidence_interval: Optional[List[float]] = None  # [low, high]
    ci_text: Optional[str] = None
    evidence_text: Optional[str] = None

@dataclass
class OptimizedPaper:
    """Optimized paper schema for Q&A capabilities."""
    # Core ID
    id: str
    title: str
    journal: str
    year: int
    study_type: str                     # normalized enum
    study_design: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None

    # Population
    population: Dict[str, Any] = field(default_factory=dict)  # {age_range, sex, training_status, sample_size}

    # Q&A essentials
    summary: str = ""
    key_findings: List[str] = field(default_factory=list)

    # Supplements & dosage
    supplements: List[str] = field(default_factory=list)
    supplement_primary: Optional[str] = None
    dosage: Dict[str, Any] = field(default_factory=dict)      # keep display strings + optional numeric/unit fields

    # Outcomes (compatible with StorageManager)
    primary_outcome: Optional[str] = None
    outcome_measures: Dict[str, List[OutcomeItem]] = field(default_factory=lambda: {
        "strength": [], "endurance": [], "power": []
    })

    # Safety
    safety_issues: List[str] = field(default_factory=list)
    adverse_events: Optional[str] = None

    # Quality
    evidence_grade: Optional[str] = None   # "A|B|C|D"
    quality_score: Optional[float] = None  # 1–10

    # Context
    limitations: List[str] = field(default_factory=list)
    clinical_relevance: Optional[str] = None

    # Search & relevance
    keywords: List[str] = field(default_factory=list)
    relevance_tags: List[str] = field(default_factory=list)

    # Pipeline
    schema_version: str = "v1.2"
    processing_timestamp: Optional[float] = None
    llm_model: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, dict) and key == "outcome_measures":
                # Convert OutcomeItem objects to dicts
                result[key] = {}
                for domain, items in value.items():
                    result[key][domain] = [
                        {
                            "measure": item.measure,
                            "effect_size": item.effect_size,
                            "effect_size_text": item.effect_size_text,
                            "p_value_num": item.p_value_num,
                            "p_value_text": item.p_value_text,
                            "confidence_interval": item.confidence_interval,
                            "ci_text": item.ci_text,
                            "evidence_text": item.evidence_text
                        } for item in items
                    ]
            else:
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptimizedPaper':
        """Create from dictionary."""
        # Convert outcome_measures back to OutcomeItem objects
        if "outcome_measures" in data and isinstance(data["outcome_measures"], dict):
            outcome_measures = {}
            for domain, items in data["outcome_measures"].items():
                outcome_measures[domain] = [
                    OutcomeItem(
                        measure=item.get("measure", ""),
                        effect_size=item.get("effect_size"),
                        effect_size_text=item.get("effect_size_text"),
                        p_value_num=item.get("p_value_num"),
                        p_value_text=item.get("p_value_text"),
                        confidence_interval=item.get("confidence_interval"),
                        ci_text=item.get("ci_text"),
                        evidence_text=item.get("evidence_text")
                    ) for item in items if isinstance(item, dict)
                ]
            data["outcome_measures"] = outcome_measures
        
        return cls(**data)

# Standardized enums
STUDY_TYPES = {
    "rct", "meta_analysis", "systematic_review", "cohort", 
    "case_control", "cross_sectional", "case_study", "review"
}

TRAINING_STATUSES = {
    "trained", "untrained", "mixed", "not_reported"
}

EVIDENCE_GRADES = {"A", "B", "C", "D"}

def create_optimized_prompt() -> str:
    """Create a prompt optimized for the new schema."""
    return """<s>[INST] You are an expert research analyst. Analyze this scientific paper and extract key information for a Q&A bot.

Focus on:
1. Clear, concise summary (2-3 sentences)
2. Key findings (3-5 bullet points)
3. Practical information (dosage, safety, outcomes)
4. Quality assessment

PAPER DETAILS:
Title: {title}
Journal: {journal}
Year: {year}
Study Type: {study_type}

ABSTRACT:
{content}

Return JSON with these fields:
{{
    "id": "Paper identifier",
    "title": "Paper title",
    "journal": "Journal name",
    "year": "Publication year",
    "doi": "DOI if available",
    "pmid": "PMID if available",
    "study_type": "rct|meta_analysis|systematic_review|cohort|case_control|cross_sectional|case_study|review",
    "study_design": "Brief methodology description",
    "population": {{
        "age_range": "Age range of participants",
        "sex": "Male/Female/Mixed",
        "training_status": "trained|untrained|mixed|not_reported",
        "sample_size": "Number of participants"
    }},
    "summary": "2-3 sentence summary of main findings",
    "key_findings": [
        "Key finding 1",
        "Key finding 2",
        "Key finding 3"
    ],
    "supplements": ["Primary supplement studied"],
    "supplement_primary": "Primary supplement studied",
    "dosage": {{
        "loading": "Loading dose if applicable",
        "maintenance": "Maintenance dose",
        "timing": "When to take",
        "form": "Form of supplement"
    }},
    "primary_outcome": "Main outcome measured",
    "outcome_measures": {{
        "strength": [
            {{
                "measure": "Outcome name",
                "effect_size": 0.23,
                "effect_size_text": "MD=0.23",
                "p_value_num": 0.012,
                "p_value_text": "p=0.012",
                "confidence_interval": [0.05, 0.41],
                "ci_text": "95% CI [0.05, 0.41]",
                "evidence_text": "quote the sentence that states this result"
            }}
        ],
        "endurance": [],
        "power": []
    }},
    "safety_issues": ["Safety concern 1", "Safety concern 2"],
    "adverse_events": "Adverse events summary",
    "evidence_grade": "A|B|C|D",
    "quality_score": "Quality score 1-10",
    "limitations": ["Limitation 1", "Limitation 2"],
    "clinical_relevance": "How this applies to real-world use",
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "relevance_tags": ["strength", "endurance", "safety", "performance"]
}}

Return ONLY the JSON object, no additional text.
[/INST]"""

def validate_optimized_schema(data: Dict[str, Any]) -> bool:
    """Validate that the data matches the optimized schema using JSON-Schema."""
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "journal": {"type": "string"},
            "year": {"type": ["integer", "string"]},
            "study_type": {"type": "string"},
            "study_design": {"type": ["string", "null"]},
            "doi": {"type": ["string", "null"]},
            "pmid": {"type": ["string", "null"]},
            "population": {"type": "object"},
            "summary": {"type": "string"},
            "key_findings": {"type": "array", "items": {"type": "string"}},
            "supplements": {"type": "array", "items": {"type": "string"}},
            "supplement_primary": {"type": ["string", "null"]},
            "dosage": {"type": "object"},
            "primary_outcome": {"type": ["string", "null"]},
            "outcome_measures": {"type": "object"},
            "safety_issues": {"type": "array", "items": {"type": "string"}},
            "adverse_events": {"type": ["string", "null"]},
            "evidence_grade": {"type": ["string", "null"]},
            "quality_score": {"type": ["number", "null"]},
            "limitations": {"type": "array", "items": {"type": "string"}},
            "clinical_relevance": {"type": ["string", "null"]},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "relevance_tags": {"type": "array", "items": {"type": "string"}},
            "schema_version": {"type": "string"},
            "processing_timestamp": {"type": ["number", "null"]},
            "llm_model": {"type": ["string", "null"]}
        },
        "required": [
            "id", "title", "journal", "year", "study_type", "population",
            "summary", "key_findings", "supplements", "outcome_measures",
            "evidence_grade", "quality_score"
        ]
    }
    
    try:
        import jsonschema
        jsonschema.validate(instance=data, schema=schema)
        return True
    except ImportError:
        # Fallback to basic validation if jsonschema not available
        required_fields = [
            'id', 'title', 'journal', 'year', 'study_type', 'population',
            'summary', 'key_findings', 'supplements', 'outcome_measures',
            'evidence_grade', 'quality_score'
        ]
        
        for field in required_fields:
            if field not in data:
                return False
        
        # Basic type checks
        if not isinstance(data.get('key_findings', []), list):
            return False
        if not isinstance(data.get('supplements', []), list):
            return False
        if not isinstance(data.get('outcome_measures', {}), dict):
            return False
        
        return True
    except Exception:
        return False

def normalize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and coerce data types."""
    # Coerce year to int
    if 'year' in data and data['year']:
        try:
            data['year'] = int(data['year'])
        except (ValueError, TypeError):
            pass
    
    # Coerce sample_size to int
    if 'population' in data and isinstance(data['population'], dict):
        if 'sample_size' in data['population'] and data['population']['sample_size']:
            try:
                data['population']['sample_size'] = int(data['population']['sample_size'])
            except (ValueError, TypeError):
                pass
    
    # Normalize study_type
    if 'study_type' in data and data['study_type']:
        study_type = data['study_type'].lower().replace(' ', '_').replace('-', '_')
        if study_type in STUDY_TYPES:
            data['study_type'] = study_type
    
    # Normalize training_status
    if 'population' in data and isinstance(data['population'], dict):
        if 'training_status' in data['population'] and data['population']['training_status']:
            status = data['population']['training_status'].lower()
            if status in TRAINING_STATUSES:
                data['population']['training_status'] = status
    
    # Normalize evidence_grade
    if 'evidence_grade' in data and data['evidence_grade']:
        grade = data['evidence_grade'].upper()
        if grade in EVIDENCE_GRADES:
            data['evidence_grade'] = grade
    
    # Normalize keywords and relevance_tags to lowercase
    for field in ['keywords', 'relevance_tags', 'supplements']:
        if field in data and isinstance(data[field], list):
            data[field] = [str(item).lower().strip() for item in data[field] if item]
    
    # Ensure supplement_primary is set if supplements list is not empty
    if 'supplements' in data and data['supplements'] and not data.get('supplement_primary'):
        data['supplement_primary'] = data['supplements'][0]
    
    return data

def create_dedupe_key(data: Dict[str, Any]) -> str:
    """Create a deduplication key for the paper."""
    # Use DOI/PMID if available, otherwise hash title+year+journal
    if data.get('doi'):
        return f"doi:{data['doi']}"
    elif data.get('pmid'):
        return f"pmid:{data['pmid']}"
    else:
        key_string = f"{data.get('title', '')}|{data.get('year', '')}|{data.get('journal', '')}"
        return f"hash:{hashlib.md5(key_string.encode()).hexdigest()[:16]}"

def create_search_index(optimized_papers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create a search-optimized index from optimized papers."""
    index = {
        "papers": {},
        "search_index": {
            "by_supplements": {},
            "by_supplement_primary": {},
            "by_study_type": {},
            "by_evidence_grade": {},
            "by_year": {},
            "by_keywords": {},
            "by_relevance_tags": {}
        },
        "statistics": {
            "total_papers": len(optimized_papers),
            "study_types": {},
            "evidence_grades": {},
            "year_range": {"min": None, "max": None},
            "supplements": set(),
            "supplement_primary": set()
        }
    }
    
    for paper in optimized_papers:
        paper_id = paper['id']
        index["papers"][paper_id] = paper
        
        # Build search indices for supplements (plural)
        for supplement in paper.get('supplements', []):
            if supplement not in index["search_index"]["by_supplements"]:
                index["search_index"]["by_supplements"][supplement] = []
            index["search_index"]["by_supplements"][supplement].append(paper_id)
            index["statistics"]["supplements"].add(supplement)
        
        # Build search index for primary supplement
        supplement_primary = paper.get('supplement_primary')
        if supplement_primary:
            if supplement_primary not in index["search_index"]["by_supplement_primary"]:
                index["search_index"]["by_supplement_primary"][supplement_primary] = []
            index["search_index"]["by_supplement_primary"][supplement_primary].append(paper_id)
            index["statistics"]["supplement_primary"].add(supplement_primary)
        
        study_type = paper.get('study_type', 'unknown')
        if study_type not in index["search_index"]["by_study_type"]:
            index["search_index"]["by_study_type"][study_type] = []
        index["search_index"]["by_study_type"][study_type].append(paper_id)
        
        evidence_grade = paper.get('evidence_grade', 'unknown')
        if evidence_grade not in index["search_index"]["by_evidence_grade"]:
            index["search_index"]["by_evidence_grade"][evidence_grade] = []
        index["search_index"]["by_evidence_grade"][evidence_grade].append(paper_id)
        
        year = paper.get('year')
        if year:
            if year not in index["search_index"]["by_year"]:
                index["search_index"]["by_year"][year] = []
            index["search_index"]["by_year"][year].append(paper_id)
        
        # Keywords and relevance tags
        for keyword in paper.get('keywords', []):
            if keyword not in index["search_index"]["by_keywords"]:
                index["search_index"]["by_keywords"][keyword] = []
            index["search_index"]["by_keywords"][keyword].append(paper_id)
        
        for tag in paper.get('relevance_tags', []):
            if tag not in index["search_index"]["by_relevance_tags"]:
                index["search_index"]["by_relevance_tags"][tag] = []
            index["search_index"]["by_relevance_tags"][tag].append(paper_id)
        
        # Update statistics
        index["statistics"]["study_types"][study_type] = index["statistics"]["study_types"].get(study_type, 0) + 1
        index["statistics"]["evidence_grades"][evidence_grade] = index["statistics"]["evidence_grades"].get(evidence_grade, 0) + 1
        
        if year:
            if index["statistics"]["year_range"]["min"] is None or year < index["statistics"]["year_range"]["min"]:
                index["statistics"]["year_range"]["min"] = year
            if index["statistics"]["year_range"]["max"] is None or year > index["statistics"]["year_range"]["max"]:
                index["statistics"]["year_range"]["max"] = year
    
    # Convert sets to lists for JSON serialization
    index["statistics"]["supplements"] = list(index["statistics"]["supplements"])
    index["statistics"]["supplement_primary"] = list(index["statistics"]["supplement_primary"])
    
    return index

def create_qa_examples() -> List[Dict[str, str]]:
    """Create example Q&A pairs for testing the optimized index."""
    return [
        {
            "question": "What is the recommended dosage of creatine for strength training?",
            "answer_type": "dosage_recommendation",
            "search_fields": ["supplements", "supplement_primary", "relevance_tags", "dosage"]
        },
        {
            "question": "Are there any safety concerns with creatine supplementation?",
            "answer_type": "safety_assessment",
            "search_fields": ["safety_issues", "adverse_events", "supplements"]
        },
        {
            "question": "What is the evidence grade for creatine improving muscle strength?",
            "answer_type": "evidence_assessment",
            "search_fields": ["relevance_tags", "evidence_grade", "outcome_measures"]
        },
        {
            "question": "What are the key findings from recent creatine studies?",
            "answer_type": "findings_summary",
            "search_fields": ["key_findings", "summary", "year"]
        },
        {
            "question": "How does creatine affect endurance performance?",
            "answer_type": "outcome_analysis",
            "search_fields": ["relevance_tags", "outcome_measures", "effect_size"]
        },
        {
            "question": "What are the effect sizes for creatine on strength gains?",
            "answer_type": "effect_size_analysis",
            "search_fields": ["outcome_measures", "relevance_tags", "study_type"]
        },
        {
            "question": "Which studies show the highest quality evidence for creatine?",
            "answer_type": "quality_assessment",
            "search_fields": ["evidence_grade", "quality_score", "study_type"]
        }
    ]

if __name__ == "__main__":
    # Example usage
    print("Optimized schema for paper indexing")
    print("=" * 50)
    
    # Show the optimized prompt
    prompt = create_optimized_prompt()
    print("Optimized prompt length:", len(prompt))
    
    # Show Q&A examples
    examples = create_qa_examples()
    print(f"\nQ&A examples: {len(examples)}")
    for example in examples:
        print(f"  Q: {example['question']}")
        print(f"  A: {example['answer_type']}")
        print(f"  Search: {example['search_fields']}")
        print()
