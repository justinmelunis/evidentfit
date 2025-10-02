"""
Shared type definitions for EvidentFit.

These types are used across the API, agents, and shared modules
to ensure consistent data structures throughout the system.
"""

from typing import Literal, Optional, List, Union
from pydantic import BaseModel, Field


# ============================================================================
# User Profile
# ============================================================================

class UserProfile(BaseModel):
    """
    User profile for personalized supplement recommendations.
    
    All fields influence stack recommendations and safety checks.
    """
    goal: Literal["strength", "hypertrophy", "endurance", "weight_loss", "performance", "general"]
    weight_kg: float = Field(gt=40, lt=250, description="Body weight in kilograms")
    age: Optional[int] = Field(default=None, ge=13, le=120, description="Age in years")
    sex: Optional[Literal["male", "female", "other"]] = Field(default=None)
    
    # Sensitivity & preferences
    caffeine_sensitive: bool = Field(default=False, description="Sensitive to caffeine/stimulants")
    pregnancy: bool = Field(default=False, description="Currently pregnant or breastfeeding")
    diet: Optional[Literal["any", "vegan", "vegetarian"]] = Field(default="any")
    
    # Dietary intake (for gap analysis)
    diet_protein_g_per_day: Optional[float] = Field(default=None, ge=0, le=500, description="Total daily protein intake from food")
    diet_protein_g_per_kg: Optional[float] = Field(default=None, ge=0, le=5, description="Protein intake per kg body weight")
    
    # Training context
    training_freq: Optional[Literal["low", "med", "high"]] = Field(default="med", description="Training frequency per week")
    
    # Safety & contraindications
    age: Optional[int] = Field(default=None, ge=13, le=120, description="Age in years")
    pregnancy: bool = Field(default=False, description="Currently pregnant or breastfeeding")
    meds: List[str] = Field(default_factory=list, description="Current medications (free text, normalized server-side)")
    conditions: List[str] = Field(default_factory=list, description="Medical conditions (e.g., 'hypertension', 'diabetes')")
    
    # Supplement preferences
    creatine_form: Optional[Literal["monohydrate", "anhydrous", "hcl"]] = Field(default="monohydrate")
    
    class Config:
        json_schema_extra = {
            "example": {
                "goal": "strength",
                "weight_kg": 80,
                "caffeine_sensitive": False,
                "diet_protein_g_per_day": 120,
                "training_freq": "med",
                "age": 28,
                "pregnancy": False,
                "meds": [],
                "conditions": []
            }
        }


# ============================================================================
# Stack Components
# ============================================================================

class Dose(BaseModel):
    """
    A single dosing recommendation.
    
    Examples:
    - {"value": 5, "unit": "g/day", "timing": "any time"}
    - {"value": "3-6", "unit": "mg/kg", "timing": "30-60 min pre", "days": 7}
    """
    value: Union[str, float, int] = Field(description="Dose amount (can be range like '3-6' or single value)")
    unit: str = Field(description="Dose unit (e.g., 'g/day', 'mg/kg', 'mg', 'ml')")
    timing: Optional[str] = Field(default=None, description="When to take (e.g., 'pre-workout', 'any time')")
    days: Optional[Union[int, str]] = Field(default=None, description="Duration (e.g., 7, 'ongoing')")
    split: Optional[int] = Field(default=None, description="Number of doses per day")
    notes: List[str] = Field(default_factory=list, description="Additional notes (e.g., 'with food', 'may cause tingling')")
    cap_reason: Optional[str] = Field(default=None, description="Reason for dose cap if applied (e.g., 'pregnancy limit')")
    
    class Config:
        json_schema_extra = {
            "example": {
                "value": 5,
                "unit": "g/day",
                "timing": "any time daily",
                "days": "ongoing",
                "notes": ["Maintenance dose"]
            }
        }


class Citation(BaseModel):
    """
    A citation to a research paper.
    
    Always includes a direct link to PubMed.
    """
    title: str
    url: str = Field(description="PubMed URL")
    pmid: Optional[str] = Field(default=None)
    study_type: Optional[str] = Field(default=None, description="e.g., 'meta-analysis', 'RCT'")
    journal: Optional[str] = Field(default=None)
    year: Optional[int] = Field(default=None)
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Effects of creatine supplementation on performance and training adaptations",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345678",
                "pmid": "12345678",
                "study_type": "meta-analysis",
                "journal": "Med Sci Sports Exerc",
                "year": 2023
            }
        }


class StackItem(BaseModel):
    """
    A single supplement in a recommended stack.
    
    Includes dosing, evidence, rationale, and citations.
    """
    supplement: str = Field(description="Supplement name (canonical form)")
    evidence_grade: Literal["A", "B", "C", "D"] = Field(description="Evidence strength (A=strong, D=weak)")
    included: bool = Field(default=True, description="Whether this item is included in final stack")
    reason: Optional[str] = Field(default=None, description="Reason for exclusion if not included")
    why: str = Field(description="Brief explanation of why this supplement is recommended")
    doses: List[Dose] = Field(description="Dosing recommendations")
    citations: List[Citation] = Field(default_factory=list, description="Supporting research papers (max 3)")
    tier: Literal["core", "optional", "conditional", "experimental"] = Field(
        default="core",
        description="Tier: core=essential, optional=beneficial, conditional=specific cases, experimental=emerging evidence"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "supplement": "creatine",
                "evidence_grade": "A",
                "included": True,
                "why": "Strongest evidence for strength and muscle gain",
                "doses": [
                    {"value": 5, "unit": "g/day", "timing": "any time", "days": "ongoing"}
                ],
                "citations": [],
                "tier": "core"
            }
        }


class Interaction(BaseModel):
    """
    A potential drug-supplement interaction.
    
    Sourced from FDA label data or medical databases.
    """
    drug: str = Field(description="Medication name")
    supplement: str = Field(description="Supplement name")
    severity: Literal["info", "caution", "avoid"] = Field(description="Interaction severity")
    note: str = Field(description="Description of the interaction")
    source_url: Optional[str] = Field(default=None, description="Source of interaction data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "drug": "warfarin",
                "supplement": "omega-3",
                "severity": "caution",
                "note": "May increase bleeding risk; monitor INR",
                "source_url": "https://dailymed.nlm.nih.gov/..."
            }
        }


class StackPlan(BaseModel):
    """
    Complete supplement stack recommendation.
    
    Includes all items, interactions, warnings, and disclaimers.
    """
    profile: UserProfile = Field(description="User profile used to generate this plan")
    items: List[StackItem] = Field(description="Recommended supplements (only included items)")
    interactions: List[Interaction] = Field(default_factory=list, description="Drug-supplement interactions")
    warnings: List[str] = Field(default_factory=list, description="Safety warnings and notes")
    exclusions: List[str] = Field(default_factory=list, description="Supplements excluded and why")
    bucket_key: Optional[str] = Field(default=None, description="Cohort signature for caching")
    index_version: str = Field(default="v1", description="Index version used")
    updated_at: Optional[str] = Field(default=None, description="When this plan was generated (ISO8601)")
    disclaimer: str = Field(
        default="Educational only; not medical advice. Consult a qualified healthcare provider before starting any supplement regimen.",
        description="Legal disclaimer"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "profile": {
                    "goal": "strength",
                    "weight_kg": 80,
                    "caffeine_sensitive": False
                },
                "items": [],
                "interactions": [],
                "warnings": [],
                "exclusions": [],
                "disclaimer": "Educational only; not medical advice."
            }
        }


# ============================================================================
# Message Types (for chat/conversational interfaces)
# ============================================================================

class Message(BaseModel):
    """A single message in a conversation."""
    role: Literal["user", "assistant", "system"]
    content: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "What supplements should I take for strength?"
            }
        }


# ============================================================================
# Evidence Document (from Azure AI Search)
# ============================================================================

class EvidenceDoc(BaseModel):
    """
    A research paper from the Azure AI Search index.
    
    This is a simplified view for use in stack recommendations.
    """
    id: str
    title: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    url_pub: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[int] = None
    study_type: Optional[str] = None
    supplements: Optional[str] = None  # comma-separated
    outcomes: Optional[str] = None  # comma-separated
    primary_goal: Optional[str] = None
    reliability_score: Optional[float] = None
    enhanced_score: Optional[float] = None
    content: Optional[str] = None  # abstract
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "pmid_12345678_chunk_0",
                "title": "Effects of creatine supplementation",
                "pmid": "12345678",
                "url_pub": "https://pubmed.ncbi.nlm.nih.gov/12345678",
                "journal": "J Appl Physiol",
                "year": 2023,
                "study_type": "meta-analysis",
                "supplements": "creatine",
                "primary_goal": "strength",
                "reliability_score": 18.5
            }
        }

