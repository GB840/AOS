from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import json
import logging
from .base import Skill, SkillMeta
from .template import SkillTemplate
from .versioning import get_version_manager, get_snapshot_manager

logger = logging.getLogger(__name__)

class SkillListing:
    def __init__(
        self,
        skill_name: str,
        description: str,
        author: str,
        version: str = "1.0.0",
        category: str = "general",
        tags: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
        downloads: int = 0,
        rating: float = 0.0,
        review_count: int = 0,
        license: str = "MIT",
        dependencies: Optional[List[str]] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ):
        self.skill_name = skill_name
        self.description = description
        self.author = author
        self.version = version
        self.category = category
        self.tags = tags or []
        self.capabilities = capabilities or []
        self.downloads = downloads
        self.rating = rating
        self.review_count = review_count
        self.license = license
        self.dependencies = dependencies or []
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "category": self.category,
            "tags": self.tags,
            "capabilities": self.capabilities,
            "downloads": self.downloads,
            "rating": self.rating,
            "review_count": self.review_count,
            "license": self.license,
            "dependencies": self.dependencies,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

class SkillMarketplace:
    def __init__(self, storage_path: str = "outputs/skills/marketplace"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.listings: Dict[str, SkillListing] = {}
        self._load_listings()
    
    def _load_listings(self):
        listings_file = self.storage_path / "listings.json"
        
        if listings_file.exists():
            try:
                with open(listings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for skill_name, listing_data in data.items():
                    listing = SkillListing(**listing_data)
                    self.listings[skill_name] = listing
            except Exception as e:
                logger.warning(f"Failed to load listings: {e}")
    
    def _save_listings(self):
        listings_file = self.storage_path / "listings.json"
        
        data = {name: listing.to_dict() for name, listing in self.listings.items()}
        with open(listings_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def publish_skill(self, skill: Skill, author: str = "anonymous") -> bool:
        if skill.name in self.listings:
            listing = self.listings[skill.name]
            listing.version = skill.meta.version
            listing.description = skill.meta.description
            listing.category = skill.meta.category
            listing.tags = skill.meta.tags
            listing.capabilities = skill.meta.capabilities
            listing.license = skill.meta.license
            listing.updated_at = datetime.now().isoformat()
        else:
            listing = SkillListing(
                skill_name=skill.name,
                description=skill.meta.description,
                author=author,
                version=skill.meta.version,
                category=skill.meta.category,
                tags=skill.meta.tags,
                capabilities=skill.meta.capabilities,
                license=skill.meta.license,
            )
            self.listings[skill.name] = listing
        
        self._save_listings()
        logger.info(f"Published skill: {skill.name}")
        return True
    
    def publish_template(self, template: SkillTemplate, author: str = "anonymous") -> bool:
        listing = SkillListing(
            skill_name=template.name,
            description=template.description,
            author=author,
            version=template.version,
            category=template.category,
            tags=template.tags,
            capabilities=template.capabilities,
            license=template.license,
        )
        self.listings[template.name] = listing
        self._save_listings()
        
        template_path = self.storage_path / "templates" / f"{template.name}.yaml"
        template.to_file(template_path)
        
        logger.info(f"Published template: {template.name}")
        return True
    
    def search_skills(self, query: str = "", category: Optional[str] = None, tags: Optional[List[str]] = None) -> List[SkillListing]:
        results = []
        
        for listing in self.listings.values():
            match = True
            
            if query:
                query_lower = query.lower()
                if query_lower not in listing.skill_name.lower() and query_lower not in listing.description.lower():
                    match = False
            
            if category and listing.category != category:
                match = False
            
            if tags:
                listing_tags = set(listing.tags)
                required_tags = set(tags)
                if not required_tags.intersection(listing_tags):
                    match = False
            
            if match:
                results.append(listing)
        
        return sorted(results, key=lambda x: x.downloads, reverse=True)
    
    def get_skill(self, skill_name: str) -> Optional[SkillListing]:
        return self.listings.get(skill_name)
    
    def download_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        listing = self.listings.get(skill_name)
        if not listing:
            return None
        
        listing.downloads += 1
        self._save_listings()
        
        template_path = self.storage_path / "templates" / f"{skill_name}.yaml"
        if template_path.exists():
            try:
                template = SkillTemplate.from_file(template_path)
                return {
                    "success": True,
                    "skill_name": skill_name,
                    "template": template.to_yaml(),
                    "listing": listing.to_dict(),
                }
            except Exception as e:
                logger.warning(f"Failed to download skill {skill_name}: {e}")
        
        return {
            "success": True,
            "skill_name": skill_name,
            "listing": listing.to_dict(),
        }
    
    def rate_skill(self, skill_name: str, rating: float, review: str = "") -> bool:
        listing = self.listings.get(skill_name)
        if not listing:
            return False
        
        listing.rating = (listing.rating * listing.review_count + rating) / (listing.review_count + 1)
        listing.review_count += 1
        self._save_listings()
        
        reviews_file = self.storage_path / "reviews" / f"{skill_name}.json"
        reviews_file.parent.mkdir(exist_ok=True)
        
        reviews = []
        if reviews_file.exists():
            try:
                with open(reviews_file, "r", encoding="utf-8") as f:
                    reviews = json.load(f)
            except:
                pass
        
        reviews.append({
            "rating": rating,
            "review": review,
            "timestamp": datetime.now().isoformat(),
        })
        
        with open(reviews_file, "w", encoding="utf-8") as f:
            json.dump(reviews, f, ensure_ascii=False, indent=2)
        
        return True
    
    def list_categories(self) -> List[str]:
        categories = set()
        for listing in self.listings.values():
            categories.add(listing.category)
        return sorted(list(categories))
    
    def list_popular_skills(self, limit: int = 10) -> List[SkillListing]:
        return sorted(
            self.listings.values(),
            key=lambda x: x.downloads,
            reverse=True
        )[:limit]
    
    def list_recent_skills(self, limit: int = 10) -> List[SkillListing]:
        return sorted(
            self.listings.values(),
            key=lambda x: x.updated_at,
            reverse=True
        )[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        total_downloads = sum(l.downloads for l in self.listings.values())
        avg_rating = sum(l.rating for l in self.listings.values()) / max(len(self.listings), 1)
        
        category_stats = {}
        for listing in self.listings.values():
            category_stats[listing.category] = category_stats.get(listing.category, 0) + 1
        
        return {
            "total_skills": len(self.listings),
            "total_downloads": total_downloads,
            "avg_rating": round(avg_rating, 2),
            "categories": category_stats,
        }

class SkillImporter:
    def __init__(self):
        pass
    
    def import_from_file(self, filepath: str) -> Optional[SkillTemplate]:
        try:
            template = SkillTemplate.from_file(filepath)
            logger.info(f"Imported skill template from {filepath}")
            return template
        except Exception as e:
            logger.error(f"Failed to import skill from {filepath}: {e}")
            return None
    
    def import_from_url(self, url: str) -> Optional[SkillTemplate]:
        try:
            import requests
            response = requests.get(url)
            response.raise_for_status()
            template = SkillTemplate.from_yaml(response.text)
            logger.info(f"Imported skill template from URL: {url}")
            return template
        except Exception as e:
            logger.error(f"Failed to import skill from URL {url}: {e}")
            return None
    
    def export_to_file(self, template: SkillTemplate, filepath: str) -> bool:
        try:
            template.to_file(filepath)
            logger.info(f"Exported skill template to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export skill to {filepath}: {e}")
            return False

_default_marketplace = None
_default_importer = None

def get_marketplace() -> SkillMarketplace:
    global _default_marketplace
    if _default_marketplace is None:
        _default_marketplace = SkillMarketplace()
    return _default_marketplace

def get_importer() -> SkillImporter:
    global _default_importer
    if _default_importer is None:
        _default_importer = SkillImporter()
    return _default_importer