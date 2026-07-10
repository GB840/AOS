# -*- coding: utf-8 -*-
from .base import Skill, SkillMeta
import logging
from datetime import datetime
logger = logging.getLogger(__name__)
try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False
class DuckDuckGoSearchSkill(Skill):
    def __init__(self):
        meta = SkillMeta(name='duckduckgo-search', description='DuckDuckGo free web search (ddgs): text/news/image/video/instant answers, no API key', version='1.0.0', tags=['search','web','duckduckgo','ddgs','research','privacy','free'], capabilities=['web_search','news_search','image_search','video_search','instant_answer'], category='research')
        super().__init__(meta)
    def execute(self, context):
        if not HAS_DDGS:
            return {'success': False, 'error': 'ddgs library not installed. Run: pip install ddgs'}
        query = context.get('query', context.get('q', ''))
        if not query:
            return {'success': False, 'error': 'Missing query field'}
        max_results = min(context.get('max_results', 10), 50)
        search_type = context.get('type', 'text')
        region = context.get('region', 'wt-wt')
        try:
            with DDGS() as ddgs:
                method_map = {'text': ddgs.text, 'news': ddgs.news, 'images': ddgs.images, 'videos': ddgs.videos, 'answers': ddgs.answers}
                method = method_map.get(search_type, ddgs.text)
                raw = list(method(query, max_results=max_results, region=region))
        except Exception as exc:
            return {'success': False, 'error': str(exc)}
        normalized = []
        for r in raw:
            entry = {'source': 'duckduckgo', 'query': query, 'date_found': datetime.now().strftime('%Y-%m-%d')}
            if search_type == 'text':
                entry.update({'name': r.get('title',''), 'url': r.get('href',''), 'description': (r.get('body','') or '')[:300]})
            elif search_type == 'news':
                entry.update({'name': r.get('title',''), 'url': r.get('url',''), 'description': (r.get('body','') or '')[:300], 'source_name': r.get('source',''), 'date': r.get('date','')})
            elif search_type == 'images':
                entry.update({'name': r.get('title',''), 'url': r.get('image',''), 'source_url': r.get('url',''), 'thumbnail': r.get('thumbnail','')})
            elif search_type == 'videos':
                entry.update({'name': r.get('title',''), 'url': r.get('content',''), 'description': (r.get('description','') or '')[:300]})
            elif search_type == 'answers':
                entry.update({'name': r.get('abstract_text',''), 'url': r.get('abstract_url',''), 'answer': r.get('answer','')})
            normalized.append(entry)
        seen = set()
        deduped = []
        for item in normalized:
            key = item.get('url', item.get('name', ''))
            if key and key not in seen:
                seen.add(key)
                deduped.append(item)
        return {'success': True, 'query': query, 'type': search_type, 'results': deduped, 'count': len(deduped)}
