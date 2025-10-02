"""
Form Selection System for EvidentFit

Handles supplement form selection, conversion, and user choice management
without changing core StackItem structure.
"""

from typing import Dict, List, Optional, Tuple
from supplement_forms import supplement_forms, SupplementForm


class FormSelectionManager:
    """Manages supplement form selection and conversion for users"""
    
    def __init__(self):
        self.form_manager = supplement_forms
    
    def enhance_stack_item_with_forms(self, stack_item: dict, user_form_preference: Optional[str] = None) -> dict:
        """
        Enhance a stack item with form selection capabilities.
        
        Args:
            stack_item: Base StackItem dict (supplement recommended based on evidence)
            user_form_preference: User's preferred form (e.g., "hcl", "monohydrate")
            
        Returns:
            Enhanced stack item with form options and converted dosing
        """
        supplement = stack_item["supplement"]
        available_forms = self.form_manager.get_supplement_forms(supplement)
        
        if not available_forms:
            # No forms available - return as-is
            return stack_item
        
        # Get reference form (most researched)
        reference_form = self.form_manager.get_reference_form(supplement)
        if not reference_form:
            return stack_item
        
        # Determine user's preferred form
        if user_form_preference and user_form_preference in available_forms:
            selected_form = user_form_preference
        else:
            # Default to reference form
            selected_form = next(k for k, v in available_forms.items() if v.reference_form)
        
        # Convert dosing to selected form
        enhanced_item = stack_item.copy()
        enhanced_item["selected_form"] = selected_form
        enhanced_item["form_display_name"] = available_forms[selected_form].name
        
        # Convert doses
        if enhanced_item.get("doses"):
            enhanced_item["doses"] = self._convert_doses_to_form(
                enhanced_item["doses"], supplement, selected_form
            )
        
        # Add form selection info
        enhanced_item["form_options"] = self._get_form_options_summary(supplement)
        
        # Update why text to mention form
        if "why" in enhanced_item:
            form_obj = available_forms[selected_form]
            enhanced_item["why"] += f" Using {form_obj.name} ({form_obj.research_support} grade research)."
        
        return enhanced_item
    
    def _convert_doses_to_form(self, doses: List[dict], supplement: str, target_form: str) -> List[dict]:
        """Convert doses from reference form to target form"""
        reference_form = self.form_manager.get_reference_form(supplement)
        if not reference_form:
            return doses
        
        # Find reference form key
        forms = self.form_manager.get_supplement_forms(supplement)
        ref_form_key = next(k for k, v in forms.items() if v.reference_form)
        
        converted_doses = []
        for dose in doses:
            converted_dose = dose.copy()
            
            # Convert numeric doses
            if isinstance(dose.get("value"), (int, float)):
                # Convert from reference form to target form
                if dose.get("unit", "").lower().startswith("g"):
                    # Convert grams
                    dose_mg = dose["value"] * 1000
                    converted_mg, explanation = self.form_manager.convert_dose(
                        supplement, ref_form_key, target_form, dose_mg
                    )
                    converted_dose["value"] = round(converted_mg / 1000, 1)
                    
                    # Add conversion note
                    if "notes" not in converted_dose:
                        converted_dose["notes"] = []
                    converted_dose["notes"].append(f"Dose converted for {target_form} form")
            
            converted_doses.append(converted_dose)
        
        return converted_doses
    
    def _get_form_options_summary(self, supplement: str) -> List[dict]:
        """Get summary of available forms for quick selection"""
        forms = self.form_manager.get_supplement_forms(supplement)
        
        options = []
        for form_key, form_obj in forms.items():
            options.append({
                "form_key": form_key,
                "name": form_obj.name,
                "research_grade": form_obj.research_support,
                "cost_factor": form_obj.cost_factor,
                "advantages": form_obj.advantages[:2],  # Top 2 advantages
                "recommended_for": form_obj.recommended_for,
                "reference_form": form_obj.reference_form
            })
        
        # Sort by research grade and reference form
        options.sort(key=lambda x: (x["reference_form"], x["research_grade"]), reverse=True)
        return options
    
    def get_form_recommendation(self, supplement: str, user_context: dict) -> Tuple[str, str]:
        """Get recommended form based on user context"""
        return self.form_manager.get_form_recommendation(supplement, user_context)
    
    def get_detailed_form_comparison(self, supplement: str) -> dict:
        """Get detailed comparison for dedicated form pages"""
        return self.form_manager.get_form_comparison(supplement)


# Global instance
form_selection = FormSelectionManager()


def enhance_stack_with_forms(stack_plan: dict, user_preferences: dict) -> dict:
    """
    Enhance an entire stack plan with form selection.
    
    Args:
        stack_plan: Complete StackPlan dict
        user_preferences: Dict of supplement -> preferred_form
        
    Returns:
        Enhanced stack plan with form selections
    """
    enhanced_plan = stack_plan.copy()
    
    if "items" in enhanced_plan:
        enhanced_items = []
        for item in enhanced_plan["items"]:
            supplement = item["supplement"]
            preferred_form = user_preferences.get(supplement)
            
            enhanced_item = form_selection.enhance_stack_item_with_forms(
                item, preferred_form
            )
            enhanced_items.append(enhanced_item)
        
        enhanced_plan["items"] = enhanced_items
    
    return enhanced_plan


def get_user_form_context(profile) -> dict:
    """Extract form selection context from user profile"""
    context = {}
    
    # Budget consciousness (not directly in profile, but could be inferred)
    context["budget_conscious"] = False  # Could add this to profile later
    
    # GI sensitivity (could infer from conditions or add specific field)
    context["gi_sensitive"] = "gi" in " ".join(profile.conditions).lower() if hasattr(profile, 'conditions') else False
    
    # Vegan/vegetarian
    context["vegan"] = profile.diet == "vegan" if hasattr(profile, 'diet') else False
    
    # Lactose intolerance (could infer from conditions)
    context["lactose_intolerant"] = "lactose" in " ".join(profile.conditions).lower() if hasattr(profile, 'conditions') else False
    
    # Soy allergy (could infer from conditions)
    context["soy_allergy"] = "soy" in " ".join(profile.conditions).lower() if hasattr(profile, 'conditions') else False
    
    # Pre-workout timing preference (could add to profile)
    context["pre_workout_timing"] = False  # Could add this preference
    
    return context
