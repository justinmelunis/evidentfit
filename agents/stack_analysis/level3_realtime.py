"""
Level 3: Real-Time Evidence Enhancement

This module provides real-time evidence enhancement for user-specific queries.
It combines Level 1 base grades with Level 2 profile reasoning and adds
query-specific evidence to produce final grades with comprehensive citations.

Features:
- Real-time query-specific evidence search
- Integration of Level 1 + Level 2 + Level 3 reasoning
- Final grade synthesis with comprehensive citations
- User-specific safety and condition considerations
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'api'))

from evidentfit_shared.search_client import search_docs
from clients.foundry_chat import chat as foundry_chat

class Level3RealTimeEnhancer:
    """Real-time evidence enhancement for user-specific queries"""
    
    def __init__(self):
        self.level1_bank = None
        self.level2_bank = None
        self.load_banks()
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def load_banks(self):
        """Load Level 1 and Level 2 banking data"""
        try:
            # Load Level 1 bank
            level1_file = os.path.join(os.path.dirname(__file__), 'level1_evidence_bank.json')
            if os.path.exists(level1_file):
                with open(level1_file, 'r') as f:
                    self.level1_bank = json.load(f)
            
            # Load Level 2 bank
            level2_file = os.path.join(os.path.dirname(__file__), 'level2_reasoning_bank.json')
            if os.path.exists(level2_file):
                with open(level2_file, 'r') as f:
                    self.level2_bank = json.load(f)
                    
        except Exception as e:
            self.logger.error(f"Failed to load banking data: {e}")
    
    def get_final_grade_with_reasoning(self, supplement: str, goal: str, user_profile: Dict, 
                                     query_context: str = "") -> Dict[str, Any]:
        """
        Get final grade with comprehensive reasoning combining all three levels
        
        Args:
            supplement: Supplement name
            goal: User goal
            user_profile: User profile with weight, age, sex, conditions, medications, etc.
            query_context: Additional context from user query
            
        Returns:
            Dict with final_grade, reasoning, citations, and level_breakdown
        """
        
        # Level 1: Base evidence grade
        level1_data = self.get_level1_evidence(supplement, goal)
        
        # Level 2: Profile-specific reasoning
        level2_data = self.get_level2_reasoning(supplement, goal, user_profile)
        
        # Level 3: Real-time query-specific evidence
        level3_data = self.get_level3_realtime_evidence(supplement, goal, user_profile, query_context)
        
        # Synthesize final grade
        final_grade_data = self.synthesize_final_grade(
            supplement, goal, level1_data, level2_data, level3_data, user_profile
        )
        
        return final_grade_data
    
    def get_level1_evidence(self, supplement: str, goal: str) -> Dict[str, Any]:
        """Get Level 1 base evidence grade"""
        if not self.level1_bank:
            return {"grade": "D", "reasoning": "Level 1 bank not available"}
        
        key = f"{supplement}:{goal}"
        evidence_data = self.level1_bank.get("evidence_data", {}).get(key, {})
        
        return {
            "grade": evidence_data.get("grade", "D"),
            "reasoning": evidence_data.get("reasoning", "No base evidence available"),
            "supporting_papers": evidence_data.get("supporting_papers", []),
            "contradictory_papers": evidence_data.get("contradictory_papers", []),
            "effect_sizes": evidence_data.get("effect_sizes", []),
            "quality_metrics": evidence_data.get("quality_metrics", {})
        }
    
    def get_level2_reasoning(self, supplement: str, goal: str, user_profile: Dict) -> Dict[str, Any]:
        """Get Level 2 profile-specific reasoning"""
        if not self.level2_bank:
            return {"reasoning": "Level 2 bank not available", "citations": []}
        
        # Generate profile key
        profile_key = self.generate_profile_key(user_profile, goal)
        profile_data = self.level2_bank.get("reasoning_data", {}).get(profile_key, {})
        supplement_data = profile_data.get(supplement, {})
        
        return {
            "reasoning": supplement_data.get("reasoning", "No profile-specific reasoning available"),
            "citations": supplement_data.get("citations", []),
            "supporting_evidence": supplement_data.get("supporting_evidence", [])
        }
    
    def get_level3_realtime_evidence(self, supplement: str, goal: str, user_profile: Dict, 
                                   query_context: str) -> Dict[str, Any]:
        """Get Level 3 real-time query-specific evidence"""
        
        # Search for user-specific evidence
        user_specific_papers = self.search_user_specific_evidence(supplement, goal, user_profile, query_context)
        
        if not user_specific_papers:
            return {
                "reasoning": "No additional user-specific evidence found",
                "citations": [],
                "safety_considerations": []
            }
        
        # Generate real-time reasoning
        reasoning = self.generate_realtime_reasoning(supplement, goal, user_profile, query_context, user_specific_papers)
        
        return reasoning
    
    def search_user_specific_evidence(self, supplement: str, goal: str, user_profile: Dict, 
                                    query_context: str) -> List[Dict]:
        """Search for user-specific evidence based on profile and query context"""
        
        # Build search queries based on user profile
        queries = []
        
        # Base supplement query
        queries.append(f"supplements:{supplement}")
        
        # Add condition-specific queries
        conditions = user_profile.get("conditions", [])
        for condition in conditions:
            queries.append(f"supplements:{supplement} AND {condition}")
        
        # Add medication-specific queries
        medications = user_profile.get("medications", [])
        for medication in medications:
            queries.append(f"supplements:{supplement} AND {medication}")
        
        # Add query context if provided
        if query_context:
            queries.append(f"supplements:{supplement} AND {query_context}")
        
        # Search and combine results
        all_papers = []
        for query in queries:
            papers = search_docs(query, top=20)
            all_papers.extend(papers)
        
        # Remove duplicates and return top results
        seen_ids = set()
        unique_papers = []
        for paper in all_papers:
            paper_id = paper.get("id", "")
            if paper_id not in seen_ids:
                seen_ids.add(paper_id)
                unique_papers.append(paper)
        
        return unique_papers[:15]  # Top 15 user-specific papers
    
    def generate_realtime_reasoning(self, supplement: str, goal: str, user_profile: Dict, 
                                  query_context: str, papers: List[Dict]) -> Dict[str, Any]:
        """Generate real-time reasoning based on user-specific evidence"""
        
        if not papers:
            return {
                "reasoning": "No additional user-specific evidence found",
                "citations": [],
                "safety_considerations": []
            }
        
        # Prepare paper summaries
        paper_summaries = ""
        citations = []
        safety_considerations = []
        
        for i, paper in enumerate(papers[:8]):  # Top 8 papers
            title = paper.get('title', '')
            journal = paper.get('journal', '')
            year = paper.get('year', '')
            content = paper.get('content', '')[:1000]
            population = paper.get('population', '')
            safety_indicators = paper.get('safety_indicators', '')
            
            paper_summaries += f"""
=== USER-SPECIFIC PAPER {i+1} ===
Title: {title}
Journal: {journal} ({year})
Population: {population}
Safety Indicators: {safety_indicators}
Content: {content}...
"""
            
            # Build citation
            citation = {
                "title": title,
                "journal": journal,
                "year": year,
                "pmid": paper.get('pmid', ''),
                "doi": paper.get('doi', ''),
                "url": paper.get('url_pub', '')
            }
            citations.append(citation)
            
            # Extract safety considerations
            if safety_indicators:
                safety_considerations.append({
                    "paper_title": title,
                    "safety_info": safety_indicators,
                    "citation": citation
                })
        
        # Generate reasoning using LLM
        prompt = f"""You are an expert in personalized supplement recommendations. Analyze the user-specific evidence for {supplement} for {goal} goals.

USER PROFILE:
- Weight: {user_profile.get('weight_kg', 'N/A')} kg
- Age: {user_profile.get('age', 'N/A')} years
- Sex: {user_profile.get('sex', 'N/A')}
- Conditions: {', '.join(user_profile.get('conditions', []))}
- Medications: {', '.join(user_profile.get('medications', []))}
- Caffeine Sensitive: {user_profile.get('caffeine_sensitive', False)}
- Pregnancy: {user_profile.get('pregnancy', False)}

QUERY CONTEXT: {query_context}

USER-SPECIFIC EVIDENCE:
{paper_summaries}

TASK:
Generate real-time reasoning that addresses:

1. **User-Specific Benefits**: Are there specific benefits for this user's profile?
2. **Safety Considerations**: Are there any safety concerns given their conditions/medications?
3. **Dosing Adjustments**: Are there different dosing recommendations for this user?
4. **Contraindications**: Are there any contraindications for this user?
5. **Query-Specific Insights**: Does the query context reveal additional considerations?

RESPONSE FORMAT:
Provide concise reasoning (2-4 sentences) that:
- Highlights user-specific findings
- Addresses safety concerns
- References specific papers when available
- Maintains scientific accuracy

Example format:
"For your specific profile, research suggests [user-specific finding] (Citation: [paper title]). However, given your [condition/medication], there are [safety considerations] (Citation: [paper title]). [Additional user-specific recommendations]."

Your reasoning:"""

        try:
            response = foundry_chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.2
            )
            
            return {
                "reasoning": response.strip(),
                "citations": citations,
                "safety_considerations": safety_considerations
            }
            
        except Exception as e:
            self.logger.error(f"Real-time reasoning generation failed: {e}")
            return {
                "reasoning": "Real-time analysis unavailable",
                "citations": citations,
                "safety_considerations": safety_considerations
            }
    
    def synthesize_final_grade(self, supplement: str, goal: str, level1_data: Dict, 
                             level2_data: Dict, level3_data: Dict, user_profile: Dict) -> Dict[str, Any]:
        """Synthesize final grade combining all three levels"""
        
        # Prepare comprehensive analysis for LLM
        base_grade = level1_data.get("grade", "D")
        base_reasoning = level1_data.get("reasoning", "No base evidence")
        profile_reasoning = level2_data.get("reasoning", "No profile-specific reasoning")
        realtime_reasoning = level3_data.get("reasoning", "No real-time evidence")
        
        # Collect all citations
        all_citations = []
        all_citations.extend(level1_data.get("supporting_papers", []))
        all_citations.extend(level2_data.get("citations", []))
        all_citations.extend(level3_data.get("citations", []))
        
        # Remove duplicate citations
        seen_titles = set()
        unique_citations = []
        for citation in all_citations:
            title = citation.get("title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_citations.append(citation)
        
        # Generate final grade synthesis
        final_grade = self.generate_final_grade_synthesis(
            supplement, goal, base_grade, base_reasoning, profile_reasoning, 
            realtime_reasoning, user_profile, unique_citations
        )
        
        return {
            "final_grade": final_grade,
            "level_breakdown": {
                "level1": {
                    "grade": base_grade,
                    "reasoning": base_reasoning
                },
                "level2": {
                    "reasoning": profile_reasoning
                },
                "level3": {
                    "reasoning": realtime_reasoning
                }
            },
            "citations": unique_citations,
            "safety_considerations": level3_data.get("safety_considerations", [])
        }
    
    def generate_final_grade_synthesis(self, supplement: str, goal: str, base_grade: str,
                                     base_reasoning: str, profile_reasoning: str, 
                                     realtime_reasoning: str, user_profile: Dict, 
                                     citations: List[Dict]) -> str:
        """Generate final grade synthesis using LLM"""
        
        # Prepare citation text
        citation_text = ""
        for i, citation in enumerate(citations[:10]):  # Top 10 citations
            citation_text += f"""
{i+1}. {citation.get('title', '')} - {citation.get('journal', '')} ({citation.get('year', '')})
"""
        
        prompt = f"""You are an expert in evidence-based supplement recommendations. Synthesize a final grade for {supplement} for {goal} goals.

USER PROFILE:
- Weight: {user_profile.get('weight_kg', 'N/A')} kg
- Age: {user_profile.get('age', 'N/A')} years
- Sex: {user_profile.get('sex', 'N/A')}
- Conditions: {', '.join(user_profile.get('conditions', []))}
- Medications: {', '.join(user_profile.get('medications', []))}
- Caffeine Sensitive: {user_profile.get('caffeine_sensitive', False)}
- Pregnancy: {user_profile.get('pregnancy', False)}

EVIDENCE ANALYSIS:

**Level 1 - Base Evidence (Grade {base_grade}):**
{base_reasoning}

**Level 2 - Profile-Specific Reasoning:**
{profile_reasoning}

**Level 3 - Real-Time User-Specific Evidence:**
{realtime_reasoning}

**Supporting Citations:**
{citation_text}

TASK:
Synthesize a final grade (A, B, C, or D) that considers:

1. **Base Evidence**: The foundational research quality and consistency
2. **Profile Enhancement**: How the user's profile affects the recommendation
3. **Safety Considerations**: Any contraindications or safety concerns
4. **User-Specific Factors**: Conditions, medications, and other individual factors

GRADING LOGIC:
- Start with base grade
- **Upgrade** if profile-specific evidence strongly supports the user
- **Downgrade** if safety concerns or contraindications exist
- **Maintain** if no significant profile-specific factors

RESPONSE FORMAT:
Provide a comprehensive reasoning paragraph that:
1. States the base grade and reasoning
2. Explains any profile-specific enhancements
3. Addresses safety considerations
4. Provides the final grade with justification
5. References specific citations

Example format:
"The base evidence for [supplement] and [goal] shows [grade] grade due to [reasoning] (Citation: [paper]). For your specific profile, research suggests [profile-specific finding] (Citation: [paper]). However, given your [condition/medication], there are [safety considerations] (Citation: [paper]). Therefore, the final recommendation is [final grade] grade."

Your synthesis:"""

        try:
            response = foundry_chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.2
            )
            
            # Extract final grade from response
            response_upper = response.upper()
            if "GRADE A" in response_upper or "FINAL GRADE A" in response_upper:
                return "A"
            elif "GRADE B" in response_upper or "FINAL GRADE B" in response_upper:
                return "B"
            elif "GRADE C" in response_upper or "FINAL GRADE C" in response_upper:
                return "C"
            elif "GRADE D" in response_upper or "FINAL GRADE D" in response_upper:
                return "D"
            else:
                # Default to base grade if can't determine
                return base_grade
                
        except Exception as e:
            self.logger.error(f"Final grade synthesis failed: {e}")
            return base_grade  # Fallback to base grade
    
    def generate_profile_key(self, user_profile: Dict, goal: str) -> str:
        """Generate profile key for Level 2 banking lookup"""
        
        # Map weight to bin
        weight_kg = user_profile.get('weight_kg', 70)
        if weight_kg < 60:
            weight_bin = "xs"
        elif weight_kg < 70:
            weight_bin = "small"
        elif weight_kg < 85:
            weight_bin = "medium"
        elif weight_kg < 100:
            weight_bin = "large"
        else:
            weight_bin = "xl"
        
        # Map age to bin
        age = user_profile.get('age', 30)
        if age < 18:
            age_bin = "minor"
        elif age < 30:
            age_bin = "young"
        elif age < 50:
            age_bin = "adult"
        else:
            age_bin = "mature"
        
        # Get sex
        sex = user_profile.get('sex', 'other')
        
        return f"{goal}:{weight_bin}:{sex}:{age_bin}"

# Example usage
if __name__ == "__main__":
    enhancer = Level3RealTimeEnhancer()
    
    # Example user profile
    user_profile = {
        "weight_kg": 75,
        "age": 28,
        "sex": "male",
        "conditions": ["hypertension"],
        "medications": ["lisinopril"],
        "caffeine_sensitive": False,
        "pregnancy": False
    }
    
    # Get final grade with reasoning
    result = enhancer.get_final_grade_with_reasoning(
        supplement="creatine",
        goal="strength",
        user_profile=user_profile,
        query_context="I want to increase my bench press"
    )
    
    print(f"Final Grade: {result['final_grade']}")
    print(f"Reasoning: {result['level_breakdown']}")
    print(f"Citations: {len(result['citations'])} papers")
