"""
Supplement Form Management System

Handles different forms of supplements with evidence-based recommendations,
conversion factors, and form-specific guidance.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SupplementForm:
    """Represents a specific form of a supplement"""
    name: str
    active_percentage: float  # % of active compound per gram
    bioavailability_factor: float  # Relative bioavailability vs reference form
    research_support: str  # A/B/C/D grade for research backing
    solubility: str  # "excellent", "good", "poor"
    cost_factor: float  # Relative cost vs reference form (1.0 = same)
    advantages: List[str]
    disadvantages: List[str]
    notes: List[str]
    recommended_for: str
    reference_form: bool = False  # True if this is the reference form with most research


class SupplementFormManager:
    """Manages different forms of supplements and their conversions"""
    
    def __init__(self):
        self.forms = self._initialize_forms()
    
    def _initialize_forms(self) -> Dict[str, Dict[str, SupplementForm]]:
        """Initialize all supplement forms with their properties"""
        return {
            "creatine": {
                "monohydrate": SupplementForm(
                    name="Creatine Monohydrate",
                    active_percentage=87.9,  # 87.9% creatine
                    bioavailability_factor=1.0,
                    research_support="A",
                    solubility="good",
                    cost_factor=1.0,
                    advantages=[
                        "Most researched form (30+ years of studies)",
                        "Proven effective for strength and power",
                        "Generally well-tolerated",
                        "Most cost-effective"
                    ],
                    disadvantages=[
                        "Requires loading phase for fastest results",
                        "May cause mild GI upset in sensitive individuals"
                    ],
                    notes=[
                        "Gold standard with most research backing",
                        "All other forms compared to this baseline"
                    ],
                    recommended_for="Most users, especially beginners",
                    reference_form=True
                ),
                "anhydrous": SupplementForm(
                    name="Creatine Anhydrous", 
                    active_percentage=100.0,  # 100% creatine
                    bioavailability_factor=1.0,
                    research_support="B",
                    solubility="good",
                    cost_factor=1.2,
                    advantages=[
                        "Higher creatine content per gram",
                        "Need slightly less by weight",
                        "No water molecule attached"
                    ],
                    disadvantages=[
                        "Less research than monohydrate",
                        "Slightly more expensive",
                        "Theoretically equivalent but less proven"
                    ],
                    notes=[
                        "Essentially dehydrated monohydrate",
                        "Should be equivalent in effects"
                    ],
                    recommended_for="Users wanting maximum creatine per gram"
                ),
                "hcl": SupplementForm(
                    name="Creatine HCl (Hydrochloride)",
                    active_percentage=78.2,  # ~78.2% creatine base
                    bioavailability_factor=1.0,
                    research_support="C",
                    solubility="excellent", 
                    cost_factor=2.0,
                    advantages=[
                        "Superior water solubility",
                        "May reduce GI issues",
                        "No loading phase claimed (unproven)"
                    ],
                    disadvantages=[
                        "Much more expensive",
                        "Limited research vs monohydrate",
                        "Lower creatine content per gram"
                    ],
                    notes=[
                        "Marketing claims often exceed evidence",
                        "Solubility doesn't necessarily mean better absorption"
                    ],
                    recommended_for="Those with GI issues on monohydrate"
                ),
                "ethyl-ester": SupplementForm(
                    name="Creatine Ethyl Ester",
                    active_percentage=82.4,  # Estimated
                    bioavailability_factor=0.7,  # Actually worse than monohydrate
                    research_support="D",
                    solubility="good",
                    cost_factor=1.8,
                    advantages=[
                        "None demonstrated over monohydrate"
                    ],
                    disadvantages=[
                        "Inferior to monohydrate in studies",
                        "More expensive with no benefits",
                        "May be less stable"
                    ],
                    notes=[
                        "Studies show it's less effective than monohydrate",
                        "Not recommended based on current evidence"
                    ],
                    recommended_for="Not recommended; use monohydrate instead"
                )
            },
            
            "protein": {
                "whey-concentrate": SupplementForm(
                    name="Whey Protein Concentrate",
                    active_percentage=80.0,  # ~80% protein
                    bioavailability_factor=1.0,
                    research_support="A",
                    solubility="good",
                    cost_factor=1.0,
                    advantages=[
                        "Most research backing",
                        "Complete amino acid profile", 
                        "Fast absorption",
                        "Cost-effective"
                    ],
                    disadvantages=[
                        "Contains lactose (5-10%)",
                        "May cause issues for lactose intolerant"
                    ],
                    notes=[
                        "Gold standard for post-workout protein",
                        "Most studies use this form"
                    ],
                    recommended_for="Most users without lactose intolerance",
                    reference_form=True
                ),
                "whey-isolate": SupplementForm(
                    name="Whey Protein Isolate",
                    active_percentage=90.0,  # ~90% protein
                    bioavailability_factor=1.0,
                    research_support="A",
                    solubility="excellent",
                    cost_factor=1.4,
                    advantages=[
                        "Higher protein content",
                        "Minimal lactose (<1%)",
                        "Fast absorption",
                        "Better for lactose sensitive"
                    ],
                    disadvantages=[
                        "More expensive",
                        "May lack some beneficial compounds in concentrate"
                    ],
                    notes=[
                        "Processed to remove more lactose and fat",
                        "Similar research backing to concentrate"
                    ],
                    recommended_for="Lactose intolerant users or those wanting higher protein %"
                ),
                "casein": SupplementForm(
                    name="Casein Protein",
                    active_percentage=80.0,  # ~80% protein
                    bioavailability_factor=0.9,  # Slower but complete absorption
                    research_support="B",
                    solubility="poor",
                    cost_factor=1.2,
                    advantages=[
                        "Slow-digesting (6-8 hours)",
                        "Good for overnight muscle protein synthesis",
                        "High in leucine"
                    ],
                    disadvantages=[
                        "Poor mixability",
                        "Slower absorption (not ideal post-workout)",
                        "Contains lactose"
                    ],
                    notes=[
                        "Best used before bed or long periods without eating",
                        "Complements whey rather than replaces it"
                    ],
                    recommended_for="Bedtime protein or extended periods without food"
                ),
                "soy": SupplementForm(
                    name="Soy Protein Isolate",
                    active_percentage=85.0,  # ~85% protein
                    bioavailability_factor=0.85,
                    research_support="B",
                    solubility="good", 
                    cost_factor=0.9,
                    advantages=[
                        "Plant-based (vegan-friendly)",
                        "Complete amino acid profile",
                        "May have cardiovascular benefits"
                    ],
                    disadvantages=[
                        "Lower leucine than whey",
                        "Potential hormonal concerns (largely unfounded)",
                        "Taste preferences vary"
                    ],
                    notes=[
                        "Good option for vegans",
                        "Hormonal concerns are largely myth-based"
                    ],
                    recommended_for="Vegans or those avoiding dairy"
                ),
                "pea": SupplementForm(
                    name="Pea Protein Isolate",
                    active_percentage=80.0,  # ~80% protein
                    bioavailability_factor=0.8,
                    research_support="C",
                    solubility="fair",
                    cost_factor=1.1,
                    advantages=[
                        "Plant-based (vegan-friendly)",
                        "Hypoallergenic",
                        "High in BCAAs"
                    ],
                    disadvantages=[
                        "Incomplete amino acid profile (low methionine)",
                        "Less research than whey",
                        "Chalky texture"
                    ],
                    notes=[
                        "Often combined with rice protein for completeness",
                        "Growing research base"
                    ],
                    recommended_for="Vegans with soy allergies"
                )
            },
            
            "hmb": {
                "calcium": SupplementForm(
                    name="HMB Calcium (HMB-Ca)",
                    active_percentage=83.0,  # ~83% HMB
                    bioavailability_factor=1.0,
                    research_support="B",
                    solubility="good",
                    cost_factor=1.0,
                    advantages=[
                        "Most researched form",
                        "Stable and well-absorbed",
                        "Proven effective in studies"
                    ],
                    disadvantages=[
                        "Requires multiple daily doses",
                        "Must be taken with meals"
                    ],
                    notes=[
                        "Original form used in most research",
                        "Take 1g three times daily with meals"
                    ],
                    recommended_for="Most users",
                    reference_form=True
                ),
                "free-acid": SupplementForm(
                    name="HMB Free Acid (HMB-FA)",
                    active_percentage=100.0,  # 100% HMB
                    bioavailability_factor=1.2,  # Faster absorption
                    research_support="C",
                    solubility="excellent",
                    cost_factor=1.5,
                    advantages=[
                        "Faster absorption (30-60 min vs 2-3 hours)",
                        "Higher bioavailability",
                        "Can be taken closer to workouts"
                    ],
                    disadvantages=[
                        "More expensive",
                        "Less research than calcium form",
                        "Bitter taste"
                    ],
                    notes=[
                        "Better for pre-workout timing",
                        "Limited long-term studies vs calcium form"
                    ],
                    recommended_for="Users wanting pre-workout HMB"
                )
            },
            
            "caffeine": {
                "anhydrous": SupplementForm(
                    name="Caffeine Anhydrous",
                    active_percentage=100.0,  # Pure caffeine
                    bioavailability_factor=1.0,
                    research_support="A",
                    solubility="good",
                    cost_factor=1.0,
                    advantages=[
                        "Most researched form",
                        "Precise dosing",
                        "Fast absorption (30-45 min)",
                        "Cost-effective"
                    ],
                    disadvantages=[
                        "Can cause jitters in sensitive individuals",
                        "Rapid onset may be too intense for some"
                    ],
                    notes=[
                        "Standard form used in most performance research",
                        "Dehydrated caffeine powder"
                    ],
                    recommended_for="Most users",
                    reference_form=True
                ),
                "citrate": SupplementForm(
                    name="Caffeine Citrate",
                    active_percentage=50.0,  # ~50% caffeine
                    bioavailability_factor=1.1,  # Slightly better absorption
                    research_support="C",
                    solubility="excellent",
                    cost_factor=1.3,
                    advantages=[
                        "Better water solubility",
                        "May be gentler on stomach",
                        "Faster absorption"
                    ],
                    disadvantages=[
                        "More expensive per mg caffeine",
                        "Less research than anhydrous",
                        "Need double the dose by weight"
                    ],
                    notes=[
                        "Used in some medical applications",
                        "Limited performance research"
                    ],
                    recommended_for="Those with GI sensitivity to anhydrous"
                )
            }
        }
    
    def get_supplement_forms(self, supplement: str) -> Dict[str, SupplementForm]:
        """Get all available forms for a supplement"""
        return self.forms.get(supplement, {})
    
    def get_reference_form(self, supplement: str) -> Optional[SupplementForm]:
        """Get the reference form (most researched) for a supplement"""
        forms = self.get_supplement_forms(supplement)
        for form in forms.values():
            if form.reference_form:
                return form
        return None
    
    def convert_dose(self, supplement: str, from_form: str, to_form: str, dose_mg: float) -> Tuple[float, str]:
        """
        Convert dose between different forms of the same supplement
        
        Returns: (converted_dose, explanation)
        """
        forms = self.get_supplement_forms(supplement)
        
        if from_form not in forms or to_form not in forms:
            return dose_mg, "Form not found - no conversion applied"
        
        from_form_obj = forms[from_form]
        to_form_obj = forms[to_form]
        
        # Convert to active compound amount
        active_mg = dose_mg * (from_form_obj.active_percentage / 100)
        
        # Convert to target form amount
        target_dose = active_mg / (to_form_obj.active_percentage / 100)
        
        explanation = f"{dose_mg}mg {from_form_obj.name} ({from_form_obj.active_percentage}% active) = {active_mg:.1f}mg active compound = {target_dose:.1f}mg {to_form_obj.name} ({to_form_obj.active_percentage}% active)"
        
        return target_dose, explanation
    
    def get_form_recommendation(self, supplement: str, user_context: Dict) -> Tuple[str, str]:
        """
        Recommend best form based on user context
        
        Args:
            supplement: Supplement name
            user_context: Dict with keys like 'budget_conscious', 'gi_sensitive', 'vegan', etc.
            
        Returns: (recommended_form, reasoning)
        """
        forms = self.get_supplement_forms(supplement)
        if not forms:
            return "unknown", "Supplement not found"
        
        # Default to reference form
        reference = self.get_reference_form(supplement)
        if not reference:
            return list(forms.keys())[0], "Default form"
        
        # Apply context-based logic
        if supplement == "creatine":
            if user_context.get('gi_sensitive', False):
                return "hcl", "HCl form may reduce GI issues, though monohydrate is more researched"
            elif user_context.get('budget_conscious', False):
                return "monohydrate", "Most cost-effective with strongest research backing"
            else:
                return "monohydrate", "Gold standard with most research (30+ years of studies)"
        
        elif supplement == "protein":
            if user_context.get('vegan', False):
                if user_context.get('soy_allergy', False):
                    return "pea", "Plant-based option for vegans with soy allergies"
                else:
                    return "soy", "Complete plant-based protein for vegans"
            elif user_context.get('lactose_intolerant', False):
                return "whey-isolate", "Minimal lactose content (<1%)"
            elif user_context.get('budget_conscious', False):
                return "whey-concentrate", "Most cost-effective with strong research backing"
            else:
                return "whey-concentrate", "Gold standard with most research backing"
        
        elif supplement == "hmb":
            if user_context.get('pre_workout_timing', False):
                return "free-acid", "Faster absorption for pre-workout use"
            else:
                return "calcium", "Most researched form with proven efficacy"
        
        elif supplement == "caffeine":
            if user_context.get('gi_sensitive', False):
                return "citrate", "May be gentler on stomach"
            else:
                return "anhydrous", "Most researched form with precise dosing"
        
        # Default to reference form
        ref_key = next(k for k, v in forms.items() if v.reference_form)
        return ref_key, f"Reference form with most research backing"
    
    def get_form_comparison(self, supplement: str) -> Dict:
        """Get detailed comparison of all forms for a supplement"""
        forms = self.get_supplement_forms(supplement)
        
        comparison = {
            "supplement": supplement,
            "forms": {}
        }
        
        for form_key, form_obj in forms.items():
            comparison["forms"][form_key] = {
                "name": form_obj.name,
                "active_percentage": form_obj.active_percentage,
                "bioavailability_factor": form_obj.bioavailability_factor,
                "research_support": form_obj.research_support,
                "solubility": form_obj.solubility,
                "cost_factor": form_obj.cost_factor,
                "advantages": form_obj.advantages,
                "disadvantages": form_obj.disadvantages,
                "notes": form_obj.notes,
                "recommended_for": form_obj.recommended_for,
                "reference_form": form_obj.reference_form
            }
        
        return comparison


# Global instance
supplement_forms = SupplementFormManager()


# Helper functions for backward compatibility
def get_creatine_form_comparison() -> Dict:
    """Backward compatibility function"""
    return supplement_forms.get_form_comparison("creatine")


def convert_creatine_dose(from_form: str, to_form: str, dose_mg: float) -> Tuple[float, str]:
    """Convert creatine dose between forms"""
    return supplement_forms.convert_dose("creatine", from_form, to_form, dose_mg)
