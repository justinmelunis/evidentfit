#!/usr/bin/env python3
"""
EvidentFit Paper Processor - Simplified Single-File Pipeline

This simplified version includes all collect and extract logic directly in run.py
to eliminate complexity and memory issues.
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
# Database connection will use existing method
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

# Optional imports for enhanced features
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("Warning: tqdm not available. Install with: pip install tqdm")

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("Warning: pyyaml not available. Install with: pip install pyyaml")

# Set up database environment
os.environ['EVIDENTFIT_DB_DSN'] = 'postgresql://postgres:Winston8891**@localhost:5432/evidentfit'

LOG = logging.getLogger(__name__)


def get_gpu_memory():
    """Get current GPU memory usage in GB."""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024**3
    return 0.0


def get_gpu_memory_info():
    """Get detailed GPU memory information."""
    if not torch.cuda.is_available():
        return {"allocated": 0.0, "reserved": 0.0, "total": 0.0, "free": 0.0}
    
    allocated = torch.cuda.memory_allocated() / 1024**3
    reserved = torch.cuda.memory_reserved() / 1024**3
    total = torch.cuda.get_device_properties(0).total_memory / 1024**3
    free = total - reserved
    
    return {
        "allocated": allocated,
        "reserved": reserved, 
        "total": total,
        "free": free,
        "usage_percent": (reserved / total) * 100
    }


def check_memory_usage(warning_threshold=80, critical_threshold=90):
    """Check GPU memory usage and warn if approaching limits."""
    if not torch.cuda.is_available():
        return
    
    mem_info = get_gpu_memory_info()
    usage_percent = mem_info["usage_percent"]
    
    if usage_percent >= critical_threshold:
        LOG.warning(f"CRITICAL: GPU memory usage at {usage_percent:.1f}% ({mem_info['reserved']:.1f}GB/{mem_info['total']:.1f}GB)")
        LOG.warning("Consider reducing batch size or clearing cache")
    elif usage_percent >= warning_threshold:
        LOG.warning(f"WARNING: GPU memory usage at {usage_percent:.1f}% ({mem_info['reserved']:.1f}GB/{mem_info['total']:.1f}GB)")


def cleanup_gpu_memory():
    """Clean up GPU memory and log the result."""
    if torch.cuda.is_available():
        before = get_gpu_memory()
        torch.cuda.empty_cache()
        after = get_gpu_memory()
        if before > after:
            LOG.debug(f"GPU memory cleaned: {before:.2f}GB -> {after:.2f}GB")


class SimpleMistralClient:
    """Simplified Mistral client with 4-bit quantization."""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Set up 4-bit quantization
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        
        LOG.info("Loading model with 4-bit quantization...")
        LOG.info(f"GPU Memory before load: {get_gpu_memory():.2f} GB")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            trust_remote_code=True,
            local_files_only=True
        )
        
        # Load model with quantization
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            quantization_config=quantization_config,
            device_map="auto",
            trust_remote_code=True,
            local_files_only=True,
            low_cpu_mem_usage=True
        )
        
        LOG.info(f"GPU Memory after load: {get_gpu_memory():.2f} GB")
        
        # Verify quantization
        if hasattr(self.model, 'is_quantized') and self.model.is_quantized:
            LOG.info(f"Model is quantized: {self.model.is_quantized}")
        else:
            LOG.warning("Model is NOT quantized!")
    
    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate text from prompt."""
        # Add system message to force JSON output
        system_msg = "You are a JSON extraction assistant. You must respond with valid JSON only, no other text."
        full_prompt = f"<s>[INST] {system_msg}\n\n{prompt} [/INST]"
        
        inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.model.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=True,
                temperature=0.3,  # Lower temperature for more consistent JSON
                pad_token_id=self.tokenizer.eos_token_id
            )
        
        response = self.tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
        return response.strip()


def load_meta_map(canonical_path: Path) -> Dict[str, dict]:
    """Load paper metadata from canonical_papers.jsonl."""
    meta_map = {}
    with open(canonical_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                paper = json.loads(line)
                meta_map[paper['pmid']] = paper
    return meta_map


def collect_from_db(paper_id: str) -> List[Tuple[str, str, int, str]]:
    """Collect chunks from database for a single paper."""
    dsn = os.environ.get('EVIDENTFIT_DB_DSN')
    if not dsn:
        LOG.error("No database DSN available")
        return []
    
    try:
        import psycopg2
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT chunk_id, section_norm, start, text
                    FROM ef_chunks
                    WHERE paper_id = %s
                      AND section_norm IN ('abstract','results','methods','complications','discussion')
                    ORDER BY start
                """, (paper_id,))
                return cur.fetchall()
    except ImportError:
        LOG.error("psycopg2 not available - install with: pip install psycopg2-binary")
        return []
    except Exception as e:
        LOG.error(f"Database error for {paper_id}: {e}")
        return []


def build_section_bundle(paper_id: str, canonical_path: Path, meta_map: Dict[str, dict]) -> Optional[Dict[str, Any]]:
    """Build section bundle from database chunks."""
    # Get chunks from database
    chunks = collect_from_db(paper_id)
    if not chunks:
        return None
    
    # Group chunks by section
    sections = {}
    for chunk_id, section_norm, start, text in chunks:
        if section_norm not in sections:
            sections[section_norm] = {"text": "", "chunks": []}
        sections[section_norm]["text"] += text + "\n"
        sections[section_norm]["chunks"].append(chunk_id)
    
    # Get metadata
    paper_meta = meta_map.get(paper_id.replace('pmid_', ''), {})
    
    return {
        "paper_id": paper_id,
        "sections": sections,
        "meta": paper_meta,
        "stats": {
            "has_fulltext": any(section in sections for section in ["results", "methods", "discussion"]),
            "total_chunks": len(chunks)
        }
    }


def extract_from_bundle(bundle: Dict[str, Any], client: SimpleMistralClient) -> Dict[str, Any]:
    """Extract structured data from bundle using LLM."""
    if not bundle or not bundle.get("sections"):
        return {}
    
    # Build context from sections
    context_parts = []
    for section_name in ["abstract", "results", "methods", "discussion"]:
        section_data = bundle["sections"].get(section_name, {})
        if section_data.get("text", "").strip():
            text = section_data["text"].strip()
            # Truncate very long sections
            if len(text) > 2000:
                text = text[:2000] + "..."
            context_parts.append(f"## {section_name.upper()}\n{text}")
    
    context = "\n\n".join(context_parts)
    
    # Embedded extraction prompt (simplified for better JSON output)
    prompt = f"""Extract key information from this research paper and return ONLY valid JSON.

Return a JSON object with these exact fields:
{{
  "population": {{
    "n": number or null,
    "sex": "string or null", 
    "age": "string or null",
    "training_status": "string or null",
    "conditions": ["string"],
    "stratification_criteria": ["string"],
    "inclusion_criteria": ["string"],
    "exclusion_criteria": ["string"],
    "baseline_characteristics": "string or null"
  }},
  "intervention": {{
    "dose_g_per_day": number or null,
    "dose_mg_per_kg": number or null, 
    "duration_weeks": number or null,
    "loading_phase": boolean or null,
    "supplement_forms": ["string"],
    "comparator": "string or null"
  }},
  "outcomes": [
    {{
      "name": "string",
      "domain": "string", 
      "direction": "string",
      "effect_size_norm": number or null,
      "p_value": number or null,
      "notes": "string"
    }}
  ],
  "safety": {{
    "adverse_events": ["string"],
    "contraindications": ["string"],
    "safety_grade": "string or null",
    "notes": "string or null"
  }}
}}

IMPORTANT: Return ONLY the JSON object, no other text.

CONTEXT:
{context}
"""
    
    try:
        response = client.generate(prompt, max_tokens=1000)
        # LOG.info(f"LLM Response: {response}")  # Commented out for production
        
        # Try to parse JSON from response
        json_str = None
        
        # Method 1: Look for ```json blocks
        if "```json" in response:
            json_start = response.find("```json") + 7
            json_end = response.find("```", json_start)
            json_str = response[json_start:json_end].strip()
        # Method 2: Look for JSON object (find first { and last })
        elif "{" in response and "}" in response:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            json_str = response[json_start:json_end]
        # Method 3: Use entire response
        else:
            json_str = response.strip()
        
        if json_str:
            # LOG.info(f"Attempting to parse JSON: {json_str[:100]}...")  # Commented out for production
            extracted = json.loads(json_str)
            return extracted
        else:
            LOG.error("No JSON found in response")
            return {}
        
    except json.JSONDecodeError as e:
        LOG.error(f"JSON parsing failed: {e}")
        LOG.error(f"Response was: {response}")
        return {}
    except Exception as e:
        LOG.error(f"Extraction failed: {e}")
        return {}


def stream_jsonl(file_path: Path, limit: Optional[int] = None):
    """Stream papers from JSONL file."""
    count = 0
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                yield json.loads(line)
                count += 1
                if limit and count >= limit:
                    break


def validate_extracted_data(extracted: Dict[str, Any]) -> Tuple[Dict[str, Any], float, List[str]]:
    """Validate and score extracted data quality."""
    if not extracted:
        return {}, 0.0, ["No data extracted"]
    
    issues = []
    score = 100.0
    
    # Check required structure
    required_sections = ["population", "intervention", "outcomes", "safety"]
    for section in required_sections:
        if section not in extracted:
            issues.append(f"Missing required section: {section}")
            score -= 20.0
        elif not isinstance(extracted[section], dict) and section != "outcomes":
            issues.append(f"Invalid {section} format (not dict)")
            score -= 15.0
    
    # Validate population data
    pop = extracted.get("population", {})
    if not isinstance(pop, dict):
        issues.append("Population section is not a dict")
        score -= 10.0
    else:
        if "n" in pop and not isinstance(pop["n"], (int, float, type(None))):
            issues.append("Population n is not a number")
            score -= 5.0
        
        # Validate list fields
        list_fields = ["conditions", "stratification_criteria", "inclusion_criteria", "exclusion_criteria"]
        for field in list_fields:
            if field in pop and not isinstance(pop[field], list):
                issues.append(f"Population {field} is not a list")
                score -= 3.0
    
    # Validate intervention data
    interv = extracted.get("intervention", {})
    if not isinstance(interv, dict):
        issues.append("Intervention section is not a dict")
        score -= 10.0
    else:
        numeric_fields = ["dose_g_per_day", "dose_mg_per_kg", "duration_weeks"]
        for field in numeric_fields:
            if field in interv and not isinstance(interv[field], (int, float, type(None))):
                issues.append(f"Intervention {field} is not a number")
                score -= 3.0
        
        if "supplement_forms" in interv and not isinstance(interv["supplement_forms"], list):
            issues.append("supplement_forms is not a list")
            score -= 5.0
    
    # Validate outcomes
    outcomes = extracted.get("outcomes", [])
    if not isinstance(outcomes, list):
        issues.append("Outcomes is not a list")
        score -= 15.0
    else:
        for i, outcome in enumerate(outcomes):
            if not isinstance(outcome, dict):
                issues.append(f"Outcome {i} is not a dict")
                score -= 5.0
            elif not outcome.get("name"):
                issues.append(f"Outcome {i} missing name")
                score -= 3.0
    
    # Validate safety data
    safety = extracted.get("safety", {})
    if not isinstance(safety, dict):
        issues.append("Safety section is not a dict")
        score -= 10.0
    else:
        list_fields = ["adverse_events", "contraindications"]
        for field in list_fields:
            if field in safety and not isinstance(safety[field], list):
                issues.append(f"Safety {field} is not a list")
                score -= 3.0
    
    # Check for empty data
    if not any(extracted.get(section) for section in required_sections):
        issues.append("All sections are empty")
        score -= 30.0
    
    # Normalize the data
    normalized = normalize_data(extracted)
    
    return normalized, max(0.0, score), issues


def normalize_data(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize extracted data to standard format."""
    # Simple normalization - just ensure required fields exist
    normalized = {
        "population_size": extracted.get("population", {}).get("n"),
        "population_characteristics": {
            "age": extracted.get("population", {}).get("age"),
            "sex": extracted.get("population", {}).get("sex"),
            "training_status": extracted.get("population", {}).get("training_status"),
            "conditions": extracted.get("population", {}).get("conditions", []),
            "stratification_criteria": extracted.get("population", {}).get("stratification_criteria", []),
            "inclusion_criteria": extracted.get("population", {}).get("inclusion_criteria", []),
            "exclusion_criteria": extracted.get("population", {}).get("exclusion_criteria", []),
            "baseline_characteristics": extracted.get("population", {}).get("baseline_characteristics")
        },
        "intervention_details": {
            "dose_g_per_day": extracted.get("intervention", {}).get("dose_g_per_day"),
            "dose_mg_per_kg": extracted.get("intervention", {}).get("dose_mg_per_kg"),
            "duration_weeks": extracted.get("intervention", {}).get("duration_weeks"),
            "loading_phase": extracted.get("intervention", {}).get("loading_phase"),
            "supplement_forms": extracted.get("intervention", {}).get("supplement_forms", []),
            "comparator": extracted.get("intervention", {}).get("comparator")
        },
        "effect_sizes": [
            {
                "measure": outcome.get("name"),
                "domain": outcome.get("domain"),
                "direction": outcome.get("direction"),
                "value": outcome.get("effect_size_norm"),
                "p_value": outcome.get("p_value"),
                "notes": outcome.get("notes")
            }
            for outcome in extracted.get("outcomes", [])
        ],
        "safety_details": {
            "adverse_events": extracted.get("safety", {}).get("adverse_events", []),
            "contraindications": extracted.get("safety", {}).get("contraindications", []),
            "safety_grade": extracted.get("safety", {}).get("safety_grade"),
            "notes": extracted.get("safety", {}).get("notes")
        }
    }
    return normalized


def save_to_jsonl(data: Dict[str, Any], output_dir: Path) -> None:
    """Save extracted data to JSONL file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"extracted_papers_{timestamp}.jsonl"
    output_path = output_dir / filename
    
    # Append to file
    with open(output_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")
    
    LOG.info(f"Saved data to: {output_path}")


def save_to_database(data: Dict[str, Any]) -> bool:
    """Save extracted data to database (optional)."""
    try:
        # Import the existing database writer
        from .db_writer import write_card_to_db
        return write_card_to_db(data)
    except Exception as e:
        LOG.warning(f"Database save failed: {e}")
        return False


def create_dedupe_key(paper: Dict[str, Any]) -> str:
    """Create a unique deduplication key for a paper."""
    pmid = paper.get("pmid")
    if pmid:
        return f"pmid_{pmid}"
    
    # Fallback to hash of title + journal + year
    title = paper.get("title", "")
    journal = paper.get("journal", "")
    year = paper.get("year", "")
    content = f"{title}|{journal}|{year}"
    import hashlib
    return f"hash_{hashlib.md5(content.encode()).hexdigest()[:16]}"


def load_master_index(master_path: Path) -> Dict[str, int]:
    """Load the master index mapping dedupe_key to line number."""
    index = {}
    if not master_path.exists():
        return index
    
    with open(master_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                dedupe_key = obj.get("dedupe_key")
                if dedupe_key:
                    index[dedupe_key] = line_num
            except Exception:
                continue
    
    return index


def save_master_index(index: Dict[str, int], master_path: Path) -> None:
    """Save the master index to file using atomic write."""
    index_path = master_path.parent / "master_index.json"
    atomic_write_text(index_path, json.dumps(index, indent=2))


def is_paper_processed(dedupe_key: str, master_index: Dict[str, int]) -> bool:
    """Check if a paper has already been processed."""
    return dedupe_key in master_index


def save_to_master(data: Dict[str, Any], master_path: Path) -> None:
    """Save extracted data to master file using atomic append."""
    # Ensure master file exists
    master_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file for atomic append
    temp_path = master_path.with_suffix(master_path.suffix + ".tmp")
    
    try:
        # Copy existing content to temp file
        if master_path.exists():
            with open(master_path, 'r', encoding='utf-8') as src:
                with open(temp_path, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
        
        # Append new data to temp file
        with open(temp_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        
        # Atomically replace the original file
        temp_path.replace(master_path)
        
        LOG.info(f"Saved to master file: {master_path}")
        
    except Exception:
        # Clean up temp file on error
        if temp_path.exists():
            temp_path.unlink()
        raise


def update_master_index(dedupe_key: str, master_path: Path, master_index: Dict[str, int]) -> None:
    """Update the master index with a new paper."""
    # Count lines in master file to get the line number
    line_count = 0
    with open(master_path, 'r', encoding='utf-8') as f:
        for _ in f:
            line_count += 1
    
    # Add to index
    master_index[dedupe_key] = line_count
    
    # Save updated index
    save_master_index(master_index, master_path)


def atomic_write_text(path: Path, text: str) -> None:
    """Write text to file atomically using temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(text)
        tmp_path.replace(path)  # Atomic move
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()  # Clean up temp file
        raise


def save_processing_stats(stats: Dict[str, Any], stats_dir: Path) -> Path:
    """Save processing statistics to timestamped file."""
    stats_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats_path = stats_dir / f"stats_{timestamp}.json"
    
    atomic_write_text(stats_path, json.dumps(stats, indent=2, ensure_ascii=False))
    return stats_path


def update_latest_pointer(master_path: Path, stats_path: Path) -> None:
    """Update the latest.json pointer file."""
    latest_path = Path("data/paper_processor/latest.json")
    latest_data = {
        "created_at": datetime.now().isoformat() + "Z",
        "summaries_path": str(master_path.absolute()),
        "stats_path": str(stats_path.absolute())
    }
    
    atomic_write_text(latest_path, json.dumps(latest_data, indent=2))


def save_checkpoint(checkpoint_data: Dict[str, Any], checkpoint_dir: Path) -> Path:
    """Save processing checkpoint for resume capability."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    checkpoint_path = checkpoint_dir / f"checkpoint_{timestamp}.json"
    
    atomic_write_text(checkpoint_path, json.dumps(checkpoint_data, indent=2))
    return checkpoint_path


def load_latest_checkpoint(checkpoint_dir: Path) -> Optional[Dict[str, Any]]:
    """Load the most recent checkpoint if available."""
    if not checkpoint_dir.exists():
        return None
    
    checkpoint_files = list(checkpoint_dir.glob("checkpoint_*.json"))
    if not checkpoint_files:
        return None
    
    # Get the most recent checkpoint
    latest_checkpoint = max(checkpoint_files, key=lambda p: p.stat().st_mtime)
    
    try:
        with open(latest_checkpoint, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        LOG.warning(f"Could not load checkpoint {latest_checkpoint}: {e}")
        return None


def run_health_checks():
    """Run comprehensive health checks."""
    LOG.info("Running health checks...")
    
    checks_passed = 0
    total_checks = 0
    
    # Check 1: GPU availability
    total_checks += 1
    if torch.cuda.is_available():
        LOG.info(f"✓ GPU available: {torch.cuda.get_device_name(0)}")
        mem_info = get_gpu_memory_info()
        LOG.info(f"  Memory: {mem_info['total']:.1f}GB total, {mem_info['free']:.1f}GB free")
        checks_passed += 1
    else:
        LOG.warning("✗ No GPU available")
    
    # Check 2: Database connectivity
    total_checks += 1
    try:
        import psycopg2
        dsn = os.environ.get('EVIDENTFIT_DB_DSN')
        if dsn:
            with psycopg2.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM ef_chunks LIMIT 1")
                    count = cur.fetchone()[0]
                    LOG.info(f"✓ Database connected: {count} chunks available")
                    checks_passed += 1
        else:
            LOG.warning("✗ No database DSN configured")
    except ImportError:
        LOG.warning("✗ psycopg2 not available")
    except Exception as e:
        LOG.warning(f"✗ Database connection failed: {e}")
    
    # Check 3: Model path
    total_checks += 1
    model_path = Path("E:/models/Mistral-7B-Instruct-v0.3")
    if model_path.exists():
        LOG.info(f"✓ Model path exists: {model_path}")
        checks_passed += 1
    else:
        LOG.warning(f"✗ Model path not found: {model_path}")
    
    # Check 4: Papers file
    total_checks += 1
    papers_path = Path("data/index/canonical_papers.jsonl")
    if papers_path.exists():
        with open(papers_path, 'r', encoding='utf-8') as f:
            paper_count = sum(1 for _ in f)
        LOG.info(f"✓ Papers file exists: {paper_count} papers")
        checks_passed += 1
    else:
        LOG.warning(f"✗ Papers file not found: {papers_path}")
    
    # Check 5: Output directories
    total_checks += 1
    output_dirs = [
        Path("data/paper_processor/extracted"),
        Path("data/paper_processor/master"),
        Path("data/paper_processor/stats"),
        Path("data/paper_processor/checkpoints")
    ]
    
    all_dirs_ok = True
    for dir_path in output_dirs:
        if not dir_path.exists():
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                LOG.info(f"✓ Created directory: {dir_path}")
            except Exception as e:
                LOG.warning(f"✗ Cannot create directory {dir_path}: {e}")
                all_dirs_ok = False
    
    if all_dirs_ok:
        LOG.info("✓ Output directories ready")
        checks_passed += 1
    
    # Summary
    LOG.info(f"\nHealth check summary: {checks_passed}/{total_checks} checks passed")
    if checks_passed == total_checks:
        LOG.info("✓ All systems ready!")
    else:
        LOG.warning("⚠ Some issues detected. Review warnings above.")
    
    return checks_passed == total_checks


class GracefulShutdown:
    """Handle graceful shutdown on interrupt signals."""
    
    def __init__(self):
        self.shutdown_requested = False
        self.signal_handlers = {}
        
    def setup_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            LOG.info(f"Received signal {signum}. Initiating graceful shutdown...")
            self.shutdown_requested = True
            
        self.signal_handlers[signal.SIGINT] = signal.signal(signal.SIGINT, signal_handler)
        self.signal_handlers[signal.SIGTERM] = signal.signal(signal.SIGTERM, signal_handler)
        
    def should_shutdown(self) -> bool:
        """Check if shutdown has been requested."""
        return self.shutdown_requested
        
    def cleanup(self):
        """Restore original signal handlers."""
        for sig, original_handler in self.signal_handlers.items():
            signal.signal(sig, original_handler)


def main():
    parser = argparse.ArgumentParser(description="Simplified Paper Processor")
    parser.add_argument("--max-papers", type=int, default=1, help="Maximum papers to process")
    parser.add_argument("--model", type=str, default="E:/models/Mistral-7B-Instruct-v0.3", help="Model path")
    parser.add_argument("--papers-jsonl", type=str, help="Papers JSONL file path")
    parser.add_argument("--log-interval", type=int, default=1, help="Log every N papers")
    parser.add_argument("--force-reprocess", action="store_true", help="Force reprocessing of already processed papers")
    parser.add_argument("--show-status", action="store_true", help="Show master index status and exit")
    parser.add_argument("--config", type=str, help="Path to YAML configuration file")
    parser.add_argument("--checkpoint-interval", type=int, default=10, help="Save checkpoint every N papers")
    parser.add_argument("--resume", action="store_true", help="Resume from latest checkpoint")
    parser.add_argument("--health-check", action="store_true", help="Run health checks and exit")
    
    args = parser.parse_args()
    
    # Load configuration if provided
    config = {}
    if args.config and YAML_AVAILABLE:
        try:
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f)
            LOG.info(f"Loaded configuration from {args.config}")
        except Exception as e:
            LOG.error(f"Failed to load config {args.config}: {e}")
            sys.exit(1)
    elif args.config and not YAML_AVAILABLE:
        LOG.error("YAML config requested but pyyaml not available. Install with: pip install pyyaml")
        sys.exit(1)
    
    # Set up logging
    log_level = config.get('logging', {}).get('level', 'INFO')
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Health check functionality
    if args.health_check:
        run_health_checks()
        return
    
    LOG.info("=" * 80)
    LOG.info("SIMPLIFIED PAPER PROCESSOR START")
    LOG.info("=" * 80)
    
    # Resolve papers file
    if args.papers_jsonl:
        papers_jsonl = Path(args.papers_jsonl)
    else:
        papers_jsonl = Path("data/index/canonical_papers.jsonl")
    
    LOG.info(f"Processing papers from: {papers_jsonl}")
    LOG.info(f"Max papers: {args.max_papers}")
    LOG.info(f"Model: {args.model}")
    
    # Load meta_map
    LOG.info("Loading paper metadata...")
    meta_map = load_meta_map(papers_jsonl)
    LOG.info(f"Loaded metadata for {len(meta_map)} papers")
    
    # Load model
    LOG.info("Loading model...")
    client = SimpleMistralClient(args.model)
    LOG.info(f"Model loaded successfully. GPU Memory: {get_gpu_memory():.2f} GB")
    
    # Set up master index system
    master_path = Path("data/paper_processor/master/summaries_master.jsonl")
    master_index = load_master_index(master_path)
    LOG.info(f"Loaded master index with {len(master_index)} processed papers")
    
    # Show status and exit if requested
    if args.show_status:
        LOG.info("=" * 60)
        LOG.info("MASTER INDEX STATUS")
        LOG.info("=" * 60)
        LOG.info(f"Master file: {master_path}")
        LOG.info(f"Master file exists: {master_path.exists()}")
        LOG.info(f"Papers in master index: {len(master_index)}")
        LOG.info(f"Index file: {master_path.parent / 'master_index.json'}")
        
        # Show latest pointer if it exists
        latest_path = Path("data/paper_processor/latest.json")
        if latest_path.exists():
            try:
                with open(latest_path, 'r') as f:
                    latest_data = json.load(f)
                LOG.info(f"Latest run: {latest_data.get('created_at', 'unknown')}")
                LOG.info(f"Latest master: {latest_data.get('summaries_path', 'unknown')}")
            except Exception as e:
                LOG.warning(f"Could not read latest.json: {e}")
        
        LOG.info("=" * 60)
        return
    
    # Set up graceful shutdown
    shutdown_handler = GracefulShutdown()
    shutdown_handler.setup_handlers()
    
    # Set up checkpoint system
    checkpoint_dir = Path("data/paper_processor/checkpoints")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    # Load checkpoint if resuming
    start_idx = 0
    if args.resume:
        checkpoint = load_latest_checkpoint(checkpoint_dir)
        if checkpoint:
            start_idx = checkpoint.get("last_processed_idx", 0)
            LOG.info(f"Resuming from checkpoint at paper {start_idx}")
    
    # Process papers
    processed = 0
    failed = 0
    skipped = 0
    start_time = time.time()
    run_id = f"paper_processor_simple_{int(start_time)}"
    failed_papers = []
    quality_scores = []
    
    # Set up progress bar
    total_papers = args.max_papers
    if TQDM_AVAILABLE:
        pbar = tqdm(total=total_papers, desc="Processing papers", unit="paper")
        pbar.update(start_idx)
    else:
        pbar = None
    
    try:
        for idx, paper in enumerate(stream_jsonl(papers_jsonl, limit=args.max_papers), 1):
            # Skip if resuming and haven't reached start point
            if idx <= start_idx:
                continue
                
            # Check for shutdown request
            if shutdown_handler.should_shutdown():
                LOG.info("Shutdown requested. Saving checkpoint...")
                checkpoint_data = {
                    "last_processed_idx": idx - 1,
                    "processed": processed,
                    "failed": failed,
                    "skipped": skipped,
                    "timestamp": datetime.now().isoformat()
                }
                save_checkpoint(checkpoint_data, checkpoint_dir)
                break
            
            pmid = paper.get("pmid")
            if not pmid:
                LOG.warning("No PMID found, skipping")
                continue
        
            # Create dedupe key and check if already processed
            dedupe_key = create_dedupe_key(paper)
            if not args.force_reprocess and is_paper_processed(dedupe_key, master_index):
                LOG.info(f"Skipping already processed paper {idx}/{args.max_papers}: PMID {pmid}")
                skipped += 1
                if pbar:
                    pbar.update(1)
                continue
            
            # Check memory usage before processing
            check_memory_usage()
            
            LOG.info(f"Processing paper {idx}/{args.max_papers}: PMID {pmid}")
            
            try:
                # Convert PMID to database format
                db_pmid = f"pmid_{pmid}" if not str(pmid).startswith('pmid_') else str(pmid)
                
                # Build bundle
                bundle = build_section_bundle(db_pmid, papers_jsonl, meta_map)
                if not bundle:
                    LOG.warning(f"No bundle found for PMID {pmid}")
                    failed_papers.append({
                        "pmid": pmid,
                        "doi": paper.get("doi"),
                        "title": paper.get("title", "")[:100],
                        "reason": "no_bundle_found"
                    })
                    failed += 1
                    if pbar:
                        pbar.update(1)
                    continue
                
                # Extract data
                extracted = extract_from_bundle(bundle, client)
                if not extracted:
                    LOG.warning(f"Extraction failed for PMID {pmid}")
                    failed_papers.append({
                        "pmid": pmid,
                        "doi": paper.get("doi"),
                        "title": paper.get("title", "")[:100],
                        "reason": "extraction_failed"
                    })
                    failed += 1
                    if pbar:
                        pbar.update(1)
                    continue
                
                # Validate and normalize data
                normalized, quality_score, validation_issues = validate_extracted_data(extracted)
                quality_scores.append(quality_score)
                
                if quality_score < 50:
                    LOG.warning(f"Low quality extraction for PMID {pmid}: {quality_score:.1f}% - {validation_issues}")
                
                # Add metadata
                normalized.update({
                    "id": f"pmid_{pmid}",
                    "pmid": pmid,
                    "doi": paper.get("doi"),
                    "title": paper.get("title"),
                    "journal": paper.get("journal"),
                    "year": paper.get("year"),
                    "supplements": paper.get("supplements", []),
                    "study_type": paper.get("study_type", "unknown"),
                    "extracted_at": datetime.now().isoformat(),
                    "input_source": "fulltext" if bundle.get("stats", {}).get("has_fulltext") else "abstract",
                    "dedupe_key": dedupe_key,
                    "quality_score": quality_score,
                    "validation_issues": validation_issues
                })
                
                # Save to master file (primary storage)
                save_to_master(normalized, master_path)
                
                # Update master index
                update_master_index(dedupe_key, master_path, master_index)
                
                # Optionally save to database
                # save_to_database(normalized)
                
                LOG.info(f"Successfully processed PMID {pmid} (quality: {quality_score:.1f}%)")
                processed += 1
                
                # Clean up GPU memory
                cleanup_gpu_memory()
                
                # Update progress bar with real-time metrics
                if pbar:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    pbar.set_postfix({
                        'processed': processed,
                        'failed': failed,
                        'rate': f"{rate:.1f}/min"
                    })
                    pbar.update(1)
                
                # Save checkpoint periodically
                if processed % args.checkpoint_interval == 0:
                    checkpoint_data = {
                        "last_processed_idx": idx,
                        "processed": processed,
                        "failed": failed,
                        "skipped": skipped,
                        "timestamp": datetime.now().isoformat()
                    }
                    save_checkpoint(checkpoint_data, checkpoint_dir)
                    LOG.info(f"Checkpoint saved at paper {idx}")
                
                # Log memory usage
                if idx % args.log_interval == 0:
                    mem_info = get_gpu_memory_info()
                    LOG.info(f"GPU Memory: {mem_info['allocated']:.2f}GB allocated, {mem_info['usage_percent']:.1f}% used")
                
            except Exception as e:
                LOG.error(f"Error processing PMID {pmid}: {e}")
                failed_papers.append({
                    "pmid": pmid,
                    "doi": paper.get("doi"),
                    "title": paper.get("title", "")[:100],
                    "reason": "processing_exception",
                    "error": str(e)
                })
                failed += 1
                if pbar:
                    pbar.update(1)
    
    except KeyboardInterrupt:
        LOG.info("Processing interrupted by user")
    finally:
        # Clean up progress bar
        if pbar:
            pbar.close()
        
        # Clean up signal handlers
        shutdown_handler.cleanup()
    
    # Calculate processing statistics
    end_time = time.time()
    processing_time = end_time - start_time
    
    # Calculate quality statistics
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    high_quality_count = sum(1 for score in quality_scores if score >= 80)
    low_quality_count = sum(1 for score in quality_scores if score < 50)
    
    # Prepare run statistics
    run_stats = {
        "run_id": run_id,
        "mode": "stream_to_master",
        "papers_in": idx,
        "papers_out": processed,
        "skipped_empty": 0,  # Not used in simplified version
        "skipped_dedup": skipped,
        "coverage_ratio": processed / idx if idx > 0 else 0.0,
        "processing_time_seconds": processing_time,
        "papers_per_minute": (processed * 60) / processing_time if processing_time > 0 else 0,
        "store_fulltext_used": processed,  # Simplified - assume all are fulltext
        "store_abstract_used": 0,
        "store_fulltext_ratio": 1.0,
        "quality_metrics": {
            "average_quality_score": avg_quality,
            "high_quality_papers": high_quality_count,
            "low_quality_papers": low_quality_count,
            "quality_scores": quality_scores
        },
        "failed_papers": failed_papers,
        "master_size_before": len(master_index) - processed,
        "master_size_after": len(master_index),
        "gpu_memory_peak": get_gpu_memory(),
        "created_at": datetime.now().isoformat() + "Z",
        "configuration": {
            "max_papers": args.max_papers,
            "model": args.model,
            "force_reprocess": args.force_reprocess,
            "log_interval": args.log_interval,
            "checkpoint_interval": args.checkpoint_interval
        }
    }
    
    # Save processing statistics
    stats_dir = Path("data/paper_processor/stats")
    stats_path = save_processing_stats(run_stats, stats_dir)
    
    # Update latest pointer
    update_latest_pointer(master_path, stats_path)
    
    LOG.info("=" * 80)
    LOG.info(f"PROCESSING COMPLETE")
    LOG.info(f"Run ID: {run_id}")
    LOG.info(f"Processed: {processed}")
    LOG.info(f"Skipped (already processed): {skipped}")
    LOG.info(f"Failed: {failed}")
    LOG.info(f"Total in master index: {len(master_index)}")
    LOG.info(f"Processing time: {processing_time:.1f}s")
    LOG.info(f"Speed: {run_stats['papers_per_minute']:.1f} papers/min")
    LOG.info(f"Quality: {avg_quality:.1f}% avg ({high_quality_count} high, {low_quality_count} low)")
    LOG.info(f"Final GPU Memory: {get_gpu_memory():.2f} GB")
    LOG.info(f"Stats saved to: {stats_path}")
    LOG.info("=" * 80)


if __name__ == "__main__":
    main()
