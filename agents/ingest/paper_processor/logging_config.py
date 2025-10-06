"""
Comprehensive logging configuration for GPU processing pipeline.
Provides detailed logging for full processing runs with performance metrics.
"""

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import json

from evidentfit_shared.utils import PROJECT_ROOT

class ProcessingLogger:
    """Enhanced logger for GPU processing pipeline with performance tracking."""
    
    def __init__(self, log_dir: str = "logs", log_level: str = "INFO"):
        self.log_dir = PROJECT_ROOT / log_dir
        self.log_dir.mkdir(exist_ok=True)
        
        # Create timestamp for this run
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_id = f"gpu_processing_{self.run_timestamp}"
        
        # Initialize logging
        self._setup_logging(log_level)
        
        # Performance tracking
        self.start_time = None
        self.checkpoints = {}
        self.metrics = {
            'total_papers': 0,
            'processed_papers': 0,
            'failed_papers': 0,
            'schema_compliant': 0,
            'fallback_rate': 0.0,
            'processing_rate': 0.0,
            'gpu_utilization': [],
            'memory_usage': [],
            'batch_times': []
        }
        
        # Log run start
        self.log_run_start()
    
    def _setup_logging(self, log_level: str):
        """Setup comprehensive logging configuration."""
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Set log level
        level = getattr(logging, log_level.upper(), logging.INFO)
        
        # Main log file (detailed)
        main_log_file = self.log_dir / f"{self.run_id}.log"
        main_handler = logging.FileHandler(main_log_file, encoding='utf-8')
        main_handler.setLevel(level)
        main_handler.setFormatter(detailed_formatter)
        
        # Console handler (simple)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        
        # Error log file (errors only)
        error_log_file = self.log_dir / f"{self.run_id}_errors.log"
        error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        
        # Performance log file
        perf_log_file = self.log_dir / f"{self.run_id}_performance.log"
        self.perf_handler = logging.FileHandler(perf_log_file, encoding='utf-8')
        self.perf_handler.setLevel(logging.INFO)
        self.perf_handler.setFormatter(simple_formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        root_logger.addHandler(main_handler)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(self.perf_handler)
        
        # Create specific loggers
        self.logger = logging.getLogger('gpu_processor')
        self.perf_logger = logging.getLogger('performance')
        self.perf_logger.addHandler(self.perf_handler)
        self.perf_logger.propagate = False
        
        # Log configuration
        self.logger.info(f"Logging initialized for run: {self.run_id}")
        self.logger.info(f"Log level: {log_level}")
        self.logger.info(f"Log directory: {self.log_dir}")
        self.logger.info(f"Main log file: {main_log_file}")
        self.logger.info(f"Error log file: {error_log_file}")
        self.logger.info(f"Performance log file: {perf_log_file}")
    
    def log_run_start(self):
        """Log the start of a processing run."""
        self.start_time = time.time()
        self.logger.info("=" * 80)
        self.logger.info("GPU PROCESSING PIPELINE STARTED")
        self.logger.info("=" * 80)
        self.logger.info(f"Run ID: {self.run_id}")
        self.logger.info(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Python Version: {sys.version}")
        self.logger.info(f"Working Directory: {os.getcwd()}")
        self.logger.info("=" * 80)
        
        # Log system info
        self._log_system_info()
    
    def log_run_end(self, success: bool = True, error: Optional[str] = None):
        """Log the end of a processing run."""
        end_time = time.time()
        duration = end_time - self.start_time if self.start_time else 0
        
        self.logger.info("=" * 80)
        self.logger.info("GPU PROCESSING PIPELINE COMPLETED")
        self.logger.info("=" * 80)
        self.logger.info(f"Run ID: {self.run_id}")
        self.logger.info(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
        self.logger.info(f"Success: {success}")
        
        if error:
            self.logger.error(f"Error: {error}")
        
        # Log final metrics
        self._log_final_metrics()
        
        # Save run summary
        self._save_run_summary(success, error, duration)
        
        self.logger.info("=" * 80)
    
    def log_checkpoint(self, name: str, data: Dict[str, Any] = None):
        """Log a processing checkpoint."""
        checkpoint_time = time.time()
        self.checkpoints[name] = {
            'timestamp': checkpoint_time,
            'elapsed': checkpoint_time - self.start_time if self.start_time else 0,
            'data': data or {}
        }
        
        elapsed = self.checkpoints[name]['elapsed']
        self.logger.info(f"CHECKPOINT: {name} (elapsed: {elapsed:.2f}s)")
        
        if data:
            for key, value in data.items():
                self.logger.info(f"  {key}: {value}")
    
    def log_batch_start(self, batch_num: int, batch_size: int, total_papers: int):
        """Log the start of a batch processing."""
        self.logger.info(f"BATCH {batch_num}: Starting batch of {batch_size} papers")
        self.logger.info(f"  Total papers: {total_papers}")
        self.logger.info(f"  Progress: {((batch_num-1) * batch_size)}/{total_papers} ({((batch_num-1) * batch_size)/total_papers*100:.1f}%)")
    
    def log_batch_end(self, batch_num: int, batch_size: int, success_count: int, 
                     failed_count: int, batch_time: float):
        """Log the end of a batch processing."""
        self.metrics['batch_times'].append(batch_time)
        processing_rate = batch_size / batch_time if batch_time > 0 else 0
        
        self.logger.info(f"BATCH {batch_num}: Completed in {batch_time:.2f}s")
        self.logger.info(f"  Success: {success_count}/{batch_size}")
        self.logger.info(f"  Failed: {failed_count}/{batch_size}")
        self.logger.info(f"  Rate: {processing_rate:.2f} papers/second")
        
        # Log to performance logger
        self.perf_logger.info(f"BATCH_{batch_num}: {batch_time:.2f}s, {success_count}/{batch_size}, {processing_rate:.2f}pps")
    
    def log_paper_processing(self, paper_id: str, title: str, success: bool, 
                           processing_time: float, schema_valid: bool = True):
        """Log individual paper processing."""
        status = "SUCCESS" if success else "FAILED"
        schema_status = "VALID" if schema_valid else "INVALID"
        
        self.logger.debug(f"PAPER: {paper_id} | {title[:50]}... | {status} | {processing_time:.2f}s | Schema: {schema_status}")
        
        if not success:
            self.logger.warning(f"Paper processing failed: {paper_id} - {title[:50]}...")
    
    def log_schema_validation(self, paper_id: str, valid: bool, missing_fields: list = None):
        """Log schema validation results."""
        status = "VALID" if valid else "INVALID"
        self.logger.debug(f"SCHEMA: {paper_id} | {status}")
        
        if not valid and missing_fields:
            self.logger.warning(f"Schema validation failed for {paper_id}: missing {missing_fields}")
    
    def log_storage_operation(self, operation: str, count: int, success: bool, 
                            file_path: str = None, error: str = None):
        """Log storage operations."""
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"STORAGE: {operation} | {count} items | {status}")
        
        if file_path:
            self.logger.info(f"  File: {file_path}")
        
        if error:
            self.logger.error(f"  Error: {error}")
    
    def log_search_operation(self, query: str, results_count: int, search_time: float):
        """Log search operations."""
        self.logger.info(f"SEARCH: '{query}' | {results_count} results | {search_time:.3f}s")
    
    def log_performance_metrics(self, metrics: Dict[str, Any]):
        """Log performance metrics."""
        self.metrics.update(metrics)
        
        self.logger.info("PERFORMANCE METRICS:")
        for key, value in metrics.items():
            self.logger.info(f"  {key}: {value}")
        
        # Log to performance logger
        self.perf_logger.info(f"METRICS: {json.dumps(metrics)}")
    
    def log_gpu_info(self, gpu_info: Dict[str, Any]):
        """Log GPU information."""
        self.logger.info("GPU INFORMATION:")
        for key, value in gpu_info.items():
            self.logger.info(f"  {key}: {value}")
    
    def log_model_info(self, model_info: Dict[str, Any]):
        """Log model information."""
        self.logger.info("MODEL INFORMATION:")
        for key, value in model_info.items():
            self.logger.info(f"  {key}: {value}")
    
    def log_error(self, error: Exception, context: str = ""):
        """Log errors with context."""
        self.logger.error(f"ERROR in {context}: {str(error)}")
        self.logger.error(f"Error type: {type(error).__name__}")
        
        # Log stack trace
        import traceback
        self.logger.error(f"Stack trace:\n{traceback.format_exc()}")
    
    def _log_system_info(self):
        """Log system information."""
        try:
            import platform
            import psutil
            
            self.logger.info("SYSTEM INFORMATION:")
            self.logger.info(f"  Platform: {platform.platform()}")
            self.logger.info(f"  Python: {platform.python_version()}")
            self.logger.info(f"  CPU Count: {psutil.cpu_count()}")
            self.logger.info(f"  Memory: {psutil.virtual_memory().total / (1024**3):.1f} GB")
            
            # GPU info if available
            try:
                import torch
                if torch.cuda.is_available():
                    self.logger.info(f"  GPU: {torch.cuda.get_device_name(0)}")
                    self.logger.info(f"  GPU Memory: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.1f} GB")
                else:
                    self.logger.info("  GPU: Not available")
            except ImportError:
                self.logger.info("  GPU: PyTorch not available")
                
        except ImportError:
            self.logger.warning("Could not import psutil for system info")
    
    def _log_final_metrics(self):
        """Log final processing metrics."""
        self.logger.info("FINAL METRICS:")
        self.logger.info(f"  Total Papers: {self.metrics['total_papers']}")
        self.logger.info(f"  Processed Papers: {self.metrics['processed_papers']}")
        self.logger.info(f"  Failed Papers: {self.metrics['failed_papers']}")
        self.logger.info(f"  Schema Compliant: {self.metrics['schema_compliant']}")
        self.logger.info(f"  Fallback Rate: {self.metrics['fallback_rate']:.2%}")
        self.logger.info(f"  Processing Rate: {self.metrics['processing_rate']:.2f} papers/second")
        
        if self.metrics['batch_times']:
            avg_batch_time = sum(self.metrics['batch_times']) / len(self.metrics['batch_times'])
            self.logger.info(f"  Average Batch Time: {avg_batch_time:.2f} seconds")
    
    def _save_run_summary(self, success: bool, error: Optional[str], duration: float):
        """Save a summary of the run to JSON."""
        summary = {
            'run_id': self.run_id,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
            'end_time': datetime.now().isoformat(),
            'duration_seconds': duration,
            'success': success,
            'error': error,
            'metrics': self.metrics,
            'checkpoints': {name: {
                'timestamp': cp['timestamp'],
                'elapsed': cp['elapsed'],
                'data': cp['data']
            } for name, cp in self.checkpoints.items()}
        }
        
        summary_file = self.log_dir / f"{self.run_id}_summary.json"
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Run summary saved: {summary_file}")
        except Exception as e:
            self.logger.error(f"Failed to save run summary: {e}")

# Global logger instance
_global_logger = None

def get_logger() -> ProcessingLogger:
    """Get the global logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = ProcessingLogger()
    return _global_logger

def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> ProcessingLogger:
    """Setup logging for the processing pipeline."""
    global _global_logger
    _global_logger = ProcessingLogger(log_dir, log_level)
    return _global_logger


