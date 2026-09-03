"""
Knowledge Base Loader - Loads techniques, pitfalls, and templates.
"""

import os
import yaml
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Technique:
    """A competitive programming technique."""
    id: str
    name: str
    category: str
    description: str
    patterns: List[str]
    complexity: Dict[str, str]
    when_to_use: List[str]
    key_insight: str
    template: Optional[str] = None
    
    def matches_keywords(self, keywords: List[str]) -> int:
        """Count how many keywords match this technique."""
        text = f"{self.name} {self.description} {' '.join(self.patterns)} {' '.join(self.when_to_use)}"
        text = text.lower()
        return sum(1 for kw in keywords if kw.lower() in text)


@dataclass
class Pitfall:
    """A common bug/pitfall for a technique."""
    id: str
    technique: str
    name: str
    description: str
    symptoms: List[str]
    when_occurs: List[str]
    fix: str
    example: Optional[str] = None


@dataclass
class Template:
    """A code template."""
    name: str
    path: str
    content: str
    techniques: List[str] = field(default_factory=list)


class KnowledgeBase:
    """
    Loads and provides access to the knowledge base.
    Includes techniques, pitfalls, and code templates.
    """
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize knowledge base.
        
        Args:
            base_path: Path to SelfCorrectingRag directory. 
                      Defaults to parent of src/.
        """
        if base_path is None:
            # Navigate up from src/retriever to project root
            base_path = Path(__file__).parent.parent.parent
        self.base_path = Path(base_path)
        
        self.techniques: Dict[str, Technique] = {}
        self.pitfalls: Dict[str, Pitfall] = {}
        self.templates: Dict[str, Template] = {}
        
        self._load_techniques()
        self._load_pitfalls()
        self._load_templates()
    
    def _load_techniques(self) -> None:
        """Load techniques from YAML file."""
        path = self.base_path / "knowledge_base" / "techniques.yaml"
        if not path.exists():
            return
        
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        for tech_id, tech_data in data.get('techniques', {}).items():
            self.techniques[tech_id] = Technique(
                id=tech_id,
                name=tech_data.get('name', tech_id),
                category=tech_data.get('category', 'general'),
                description=tech_data.get('description', ''),
                patterns=tech_data.get('patterns', []),
                complexity=tech_data.get('complexity', {}),
                when_to_use=tech_data.get('when_to_use', []),
                key_insight=tech_data.get('key_insight', ''),
                template=tech_data.get('template')
            )
    
    def _load_pitfalls(self) -> None:
        """Load pitfalls from YAML file."""
        path = self.base_path / "knowledge_base" / "pitfalls.yaml"
        if not path.exists():
            return
        
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        for pit_id, pit_data in data.get('pitfalls', {}).items():
            self.pitfalls[pit_id] = Pitfall(
                id=pit_id,
                technique=pit_data.get('technique', 'general'),
                name=pit_data.get('name', pit_id),
                description=pit_data.get('description', ''),
                symptoms=pit_data.get('symptoms', []),
                when_occurs=pit_data.get('when_occurs', []),
                fix=pit_data.get('fix', ''),
                example=pit_data.get('example')
            )
    
    def _load_templates(self) -> None:
        """Load code templates from templates directory."""
        templates_dir = self.base_path / "templates"
        if not templates_dir.exists():
            return
        
        for template_file in templates_dir.glob("*.py"):
            name = template_file.stem
            with open(template_file, 'r') as f:
                content = f.read()
            
            # Infer associated techniques from filename
            technique_mapping = {
                'binary_search': ['binary_search'],
                'union_find': ['union_find'],
                'segment_tree': ['segment_tree'],
                'dp_knapsack': ['dp_knapsack'],
                'bfs_dfs': ['bfs', 'dfs'],
                'mod_arithmetic': ['modular_arithmetic'],
                'fast_io': [],
            }
            
            self.templates[name] = Template(
                name=name,
                path=str(template_file),
                content=content,
                techniques=technique_mapping.get(name, [])
            )
    
    def get_technique(self, tech_id: str) -> Optional[Technique]:
        """Get a technique by ID."""
        return self.techniques.get(tech_id)
    
    def get_techniques_by_category(self, category: str) -> List[Technique]:
        """Get all techniques in a category."""
        return [t for t in self.techniques.values() if t.category == category]
    
    def get_pitfalls_for_technique(self, technique: str) -> List[Pitfall]:
        """Get all pitfalls for a technique."""
        return [
            p for p in self.pitfalls.values() 
            if p.technique == technique or p.technique == 'general'
        ]
    
    def get_template(self, name: str) -> Optional[Template]:
        """Get a template by name."""
        return self.templates.get(name)
    
    def get_template_for_technique(self, tech_id: str) -> Optional[Template]:
        """Get the code template for a technique."""
        technique = self.techniques.get(tech_id)
        if technique and technique.template:
            # Remove .py extension if present
            template_name = technique.template.replace('.py', '')
            return self.templates.get(template_name)
        return None
    
    def search_techniques(self, keywords: List[str], top_k: int = 5) -> List[Technique]:
        """
        Simple keyword-based technique search.
        For more advanced search, use the Retriever class with LLM.
        """
        scored = [
            (tech, tech.matches_keywords(keywords))
            for tech in self.techniques.values()
        ]
        scored.sort(key=lambda x: -x[1])
        return [tech for tech, score in scored[:top_k] if score > 0]
    
    def list_all_techniques(self) -> List[str]:
        """List all technique IDs."""
        return list(self.techniques.keys())
    
    def list_all_categories(self) -> List[str]:
        """List all unique categories."""
        return list(set(t.category for t in self.techniques.values()))

