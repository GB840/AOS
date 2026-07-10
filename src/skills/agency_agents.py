"""
Agency Agents Skill Module - 专家智能体工厂

集成真实的 agency-agents 开源项目 (https://github.com/msitarzewski/agency-agents)
提供100+个即插即用的专业AI角色。

核心价值:
- 专家团队: 100+专业角色，覆盖多个领域
- 真实角色: 基于开源项目的真实markdown定义
- 角色扮演: 为Hermes提供角色扮演能力

部署位置:
1. Hermes 认知大脑的"角色扮演工具" - 任务分配
2. DeerFlow 任务调度引擎的"工作流模板" - 专家团队协作
3. AI 工厂的"虚拟团队" - 专业分工

支持的操作:
- list_agents: 列出所有专家角色
- get_agent: 获取专家角色详情
- invoke_agent: 调用专家角色执行任务
- search_agents: 搜索专家角色
- create_team: 创建专家团队
- assign_task: 分配任务给专家团队
"""

import logging
import uuid
from typing import Dict, Any
from datetime import datetime
from pathlib import Path

from .base import Skill
from utils.config import config

logger = logging.getLogger(__name__)

AGENCY_AGENTS_PATH = Path(config.BASE_DIR) / "external" / "agency-agents"

CATEGORY_MAP = {
    "engineering": "工程技术",
    "design": "设计创意",
    "marketing": "市场营销",
    "finance": "金融投资",
    "healthcare": "健康医疗",
    "academic": "学术研究",
    "security": "网络安全",
    "product": "产品管理",
    "project-management": "项目管理",
    "sales": "销售业务",
    "testing": "测试质量",
    "support": "技术支持",
    "specialized": "专业服务",
    "game-development": "游戏开发",
    "gis": "地理信息",
    "paid-media": "付费媒体",
    "spatial-computing": "空间计算",
}


def load_real_agency_agents() -> Dict[str, Dict]:
    """从开源项目加载真实的专家角色"""
    agents = {}
    
    if not AGENCY_AGENTS_PATH.exists():
        logger.warning(f"agency-agents 目录不存在: {AGENCY_AGENTS_PATH}")
        return agents
    
    for category_dir in AGENCY_AGENTS_PATH.iterdir():
        if not category_dir.is_dir():
            continue
        
        category_name = category_dir.name
        
        if category_name.startswith(".") or category_name in ["scripts", "examples", "integrations", "strategy"]:
            continue
        
        for agent_file in category_dir.glob("*.md"):
            agent_id = agent_file.stem
            
            try:
                with open(agent_file, "r", encoding="utf-8") as f:
                    content = f.read()
                
                name = agent_id.replace(f"{category_name}-", "").replace("-", " ").title()
                
                agents[agent_id] = {
                    "id": agent_id,
                    "name": name,
                    "category": category_name,
                    "category_name": CATEGORY_MAP.get(category_name, category_name),
                    "description": content[:200] + "..." if len(content) > 200 else content,
                    "full_content": content,
                    "skills": [],
                    "prompt": content,
                    "language": "en",
                    "source": "agency-agents",
                }
                
            except Exception as e:
                logger.error(f"加载专家角色失败 {agent_id}: {e}")
    
    logger.info(f"从 agency-agents 加载了 {len(agents)} 个专家角色")
    return agents


REAL_AGENTS = load_real_agency_agents()

EXPERT_CATEGORIES = {k: v for k, v in CATEGORY_MAP.items()}


EXPERT_AGENTS = {}

EXPERT_AGENTS = {
    "software_architect": {
        "name": "软件架构师",
        "category": "engineering",
        "description": "精通系统架构设计、微服务架构、云原生技术，能够设计高可用、高性能的分布式系统",
        "skills": ["系统设计", "架构规划", "技术选型", "性能优化", "安全设计"],
        "prompt": "你是一位资深软件架构师，拥有15年以上的系统架构设计经验。请从架构角度分析问题，提供专业的技术方案和最佳实践建议。",
        "language": "zh",
    },
    "full_stack_developer": {
        "name": "全栈开发工程师",
        "category": "engineering",
        "description": "精通前后端开发，熟悉Python/JavaScript/React/Vue等技术栈，能够独立完成全栈项目开发",
        "skills": ["前端开发", "后端开发", "数据库设计", "API开发", "测试部署"],
        "prompt": "你是一位全栈开发工程师，精通Python、JavaScript、React、Vue等技术。请提供详细的代码实现和技术方案。",
        "language": "zh",
    },
    "backend_developer": {
        "name": "后端开发工程师",
        "category": "engineering",
        "description": "精通Python/Java/Golang，熟悉分布式系统、微服务、数据库优化，擅长构建高性能后端服务",
        "skills": ["后端开发", "微服务", "数据库", "缓存优化", "消息队列"],
        "prompt": "你是一位后端开发工程师，精通Python、Java、Golang。请提供专业的后端架构设计和代码实现。",
        "language": "zh",
    },
    "frontend_developer": {
        "name": "前端开发工程师",
        "category": "engineering",
        "description": "精通React/Vue/Angular，熟悉TypeScript、CSS、性能优化，擅长构建现代化Web界面",
        "skills": ["前端框架", "TypeScript", "CSS", "性能优化", "响应式设计"],
        "prompt": "你是一位前端开发工程师，精通React、Vue、TypeScript。请提供专业的前端设计和代码实现。",
        "language": "zh",
    },
    "devops_engineer": {
        "name": "DevOps工程师",
        "category": "engineering",
        "description": "精通CI/CD、Docker/Kubernetes、云服务，擅长自动化部署和运维",
        "skills": ["CI/CD", "Docker", "Kubernetes", "云服务", "自动化运维"],
        "prompt": "你是一位DevOps工程师，精通Docker、Kubernetes、CI/CD。请提供专业的部署方案和运维建议。",
        "language": "zh",
    },
    "data_scientist": {
        "name": "数据科学家",
        "category": "engineering",
        "description": "精通Python数据分析、机器学习、深度学习，擅长数据挖掘和预测建模",
        "skills": ["数据分析", "机器学习", "深度学习", "数据可视化", "预测建模"],
        "prompt": "你是一位数据科学家，精通Python数据分析、机器学习、深度学习。请提供专业的数据分析和建模方案。",
        "language": "zh",
    },
    "machine_learning_engineer": {
        "name": "机器学习工程师",
        "category": "engineering",
        "description": "精通机器学习算法、模型部署、MLOps，擅长构建和优化AI模型",
        "skills": ["ML算法", "模型部署", "MLOps", "模型优化", "特征工程"],
        "prompt": "你是一位机器学习工程师，精通ML算法、模型部署、MLOps。请提供专业的模型设计和优化方案。",
        "language": "zh",
    },
    "ai_researcher": {
        "name": "AI研究员",
        "category": "research",
        "description": "精通深度学习、NLP、计算机视觉，关注最新AI研究进展，擅长论文解读和技术探索",
        "skills": ["深度学习", "NLP", "计算机视觉", "论文解读", "技术探索"],
        "prompt": "你是一位AI研究员，精通深度学习、NLP、计算机视觉。请提供专业的技术分析和前沿解读。",
        "language": "zh",
    },
    "ui_designer": {
        "name": "UI设计师",
        "category": "design",
        "description": "精通Figma/Sketch、设计系统、用户体验设计，擅长创建美观且实用的界面设计",
        "skills": ["UI设计", "Figma", "设计系统", "用户体验", "原型设计"],
        "prompt": "你是一位UI设计师，精通Figma、设计系统、用户体验设计。请提供专业的设计方案和视觉建议。",
        "language": "zh",
    },
    "ux_researcher": {
        "name": "UX研究员",
        "category": "design",
        "description": "精通用户研究、可用性测试、用户画像，擅长洞察用户需求和优化产品体验",
        "skills": ["用户研究", "可用性测试", "用户画像", "体验优化", "数据分析"],
        "prompt": "你是一位UX研究员，精通用户研究、可用性测试。请提供专业的用户洞察和体验优化建议。",
        "language": "zh",
    },
    "product_manager": {
        "name": "产品经理",
        "category": "business",
        "description": "精通产品规划、需求分析、用户增长，擅长从0到1打造成功产品",
        "skills": ["产品规划", "需求分析", "用户增长", "数据分析", "项目管理"],
        "prompt": "你是一位产品经理，精通产品规划、需求分析、用户增长。请提供专业的产品策略和规划建议。",
        "language": "zh",
    },
    "project_manager": {
        "name": "项目经理",
        "category": "business",
        "description": "精通项目管理、敏捷开发、团队协调，擅长管理复杂项目和跨部门协作",
        "skills": ["项目管理", "敏捷开发", "团队协调", "风险管理", "进度控制"],
        "prompt": "你是一位项目经理，精通项目管理、敏捷开发。请提供专业的项目管理方案和协调建议。",
        "language": "zh",
    },
    "entrepreneur": {
        "name": "企业家",
        "category": "business",
        "description": "精通商业模式、创业策略、投融资，擅长从创意到商业化的全流程",
        "skills": ["商业模式", "创业策略", "投融资", "市场分析", "团队建设"],
        "prompt": "你是一位企业家，精通商业模式、创业策略。请提供专业的商业建议和战略规划。",
        "language": "zh",
    },
    "marketing_manager": {
        "name": "市场营销经理",
        "category": "marketing",
        "description": "精通数字营销、品牌策略、用户增长，擅长制定和执行营销计划",
        "skills": ["数字营销", "品牌策略", "用户增长", "内容营销", "数据分析"],
        "prompt": "你是一位市场营销经理，精通数字营销、品牌策略。请提供专业的营销方案和策略建议。",
        "language": "zh",
    },
    "content_creator": {
        "name": "内容创作者",
        "category": "creative",
        "description": "精通文案写作、视频脚本、社交媒体内容，擅长创作吸引人的内容",
        "skills": ["文案写作", "视频脚本", "社交媒体", "内容策划", "创意写作"],
        "prompt": "你是一位内容创作者，精通文案写作、视频脚本。请提供专业的内容创作和创意建议。",
        "language": "zh",
    },
    "copywriter": {
        "name": "广告文案策划",
        "category": "creative",
        "description": "精通广告文案、品牌文案、营销文案，擅长用文字打动人心",
        "skills": ["广告文案", "品牌文案", "营销文案", "创意策划", "文字创作"],
        "prompt": "你是一位广告文案策划，精通广告文案、品牌文案。请提供专业的文案创作和策划建议。",
        "language": "zh",
    },
    "financial_analyst": {
        "name": "金融分析师",
        "category": "finance",
        "description": "精通财务分析、投资分析、风险评估，擅长解读财务数据和市场趋势",
        "skills": ["财务分析", "投资分析", "风险评估", "市场解读", "数据建模"],
        "prompt": "你是一位金融分析师，精通财务分析、投资分析。请提供专业的金融分析和投资建议。",
        "language": "zh",
    },
    "investment_advisor": {
        "name": "投资顾问",
        "category": "finance",
        "description": "精通投资策略、资产配置、风险管理，擅长为客户提供专业投资建议",
        "skills": ["投资策略", "资产配置", "风险管理", "理财规划", "市场分析"],
        "prompt": "你是一位投资顾问，精通投资策略、资产配置。请提供专业的投资建议和理财规划。",
        "language": "zh",
    },
    "doctor": {
        "name": "医生",
        "category": "health",
        "description": "精通医学知识、疾病诊断、健康管理，提供专业的健康咨询和建议",
        "skills": ["医学诊断", "健康管理", "疾病预防", "用药指导", "体检解读"],
        "prompt": "你是一位医生，精通医学知识、健康管理。请提供专业的健康咨询和建议（仅供参考，不能替代专业医疗诊断）。",
        "language": "zh",
    },
    "nutritionist": {
        "name": "营养师",
        "category": "health",
        "description": "精通营养学、饮食搭配、体重管理，提供专业的饮食建议和营养指导",
        "skills": ["营养学", "饮食搭配", "体重管理", "膳食规划", "营养分析"],
        "prompt": "你是一位营养师，精通营养学、饮食搭配。请提供专业的饮食建议和营养指导。",
        "language": "zh",
    },
    "teacher": {
        "name": "教师",
        "category": "education",
        "description": "精通教学方法、课程设计、学习辅导，擅长帮助学生提升学习效果",
        "skills": ["教学方法", "课程设计", "学习辅导", "教育规划", "知识讲解"],
        "prompt": "你是一位教师，精通教学方法、课程设计。请提供专业的教学建议和学习指导。",
        "language": "zh",
    },
    "career_advisor": {
        "name": "职业规划师",
        "category": "education",
        "description": "精通职业规划、简历优化、面试技巧，擅长帮助个人进行职业发展规划",
        "skills": ["职业规划", "简历优化", "面试技巧", "职业发展", "人才测评"],
        "prompt": "你是一位职业规划师，精通职业规划、简历优化。请提供专业的职业发展建议。",
        "language": "zh",
    },
    "lawyer": {
        "name": "律师",
        "category": "legal",
        "description": "精通法律知识、合同审查、纠纷处理，提供专业的法律咨询和建议",
        "skills": ["法律知识", "合同审查", "纠纷处理", "法律咨询", "合规指导"],
        "prompt": "你是一位律师，精通法律知识、合同审查。请提供专业的法律咨询和建议（仅供参考，不能替代专业法律意见）。",
        "language": "zh",
    },
    "compliance_officer": {
        "name": "合规专员",
        "category": "legal",
        "description": "精通企业合规、政策解读、风险控制，擅长帮助企业建立合规体系",
        "skills": ["企业合规", "政策解读", "风险控制", "合规体系", "内部审计"],
        "prompt": "你是一位合规专员，精通企业合规、政策解读。请提供专业的合规建议和风险控制方案。",
        "language": "zh",
    },
    "research_scientist": {
        "name": "科研研究员",
        "category": "research",
        "description": "精通科研方法、实验设计、论文撰写，擅长进行学术研究和创新探索",
        "skills": ["科研方法", "实验设计", "论文撰写", "数据分析", "学术发表"],
        "prompt": "你是一位科研研究员，精通科研方法、论文撰写。请提供专业的科研建议和学术指导。",
        "language": "zh",
    },
    "technical_writer": {
        "name": "技术文档工程师",
        "category": "engineering",
        "description": "精通技术文档编写、API文档、用户手册，擅长将复杂技术内容转化为清晰文档",
        "skills": ["技术文档", "API文档", "用户手册", "教程编写", "文档架构"],
        "prompt": "你是一位技术文档工程师，精通技术文档编写、API文档。请提供专业的文档编写建议和方案。",
        "language": "zh",
    },
    "security_engineer": {
        "name": "信息安全工程师",
        "category": "engineering",
        "description": "精通网络安全、渗透测试、安全审计，擅长保护系统和数据安全",
        "skills": ["网络安全", "渗透测试", "安全审计", "漏洞分析", "安全架构"],
        "prompt": "你是一位信息安全工程师，精通网络安全、渗透测试。请提供专业的安全建议和防护方案。",
        "language": "zh",
    },
    "mobile_developer": {
        "name": "移动开发工程师",
        "category": "engineering",
        "description": "精通iOS/Android开发、React Native/Flutter，擅长构建跨平台移动应用",
        "skills": ["iOS开发", "Android开发", "React Native", "Flutter", "移动优化"],
        "prompt": "你是一位移动开发工程师，精通iOS、Android、React Native。请提供专业的移动应用开发方案。",
        "language": "zh",
    },
    "game_developer": {
        "name": "游戏开发工程师",
        "category": "engineering",
        "description": "精通Unity/Unreal Engine、游戏架构、性能优化，擅长开发各类游戏",
        "skills": ["Unity", "Unreal Engine", "游戏架构", "性能优化", "游戏设计"],
        "prompt": "你是一位游戏开发工程师，精通Unity、Unreal Engine。请提供专业的游戏开发方案和建议。",
        "language": "zh",
    },
    "data_engineer": {
        "name": "数据工程师",
        "category": "engineering",
        "description": "精通数据管道、ETL、大数据技术，擅长构建和维护数据基础设施",
        "skills": ["数据管道", "ETL", "大数据", "数据仓库", "数据治理"],
        "prompt": "你是一位数据工程师，精通数据管道、ETL、大数据技术。请提供专业的数据架构和工程方案。",
        "language": "zh",
    },
    "architect": {
        "name": "建筑设计师",
        "category": "design",
        "description": "精通建筑设计、空间规划、建筑技术，擅长创造美观实用的建筑空间",
        "skills": ["建筑设计", "空间规划", "建筑技术", "室内设计", "景观设计"],
        "prompt": "你是一位建筑设计师，精通建筑设计、空间规划。请提供专业的建筑设计建议和方案。",
        "language": "zh",
    },
    "graphic_designer": {
        "name": "平面设计师",
        "category": "design",
        "description": "精通平面设计、品牌视觉、印刷设计，擅长创造视觉冲击力强的设计作品",
        "skills": ["平面设计", "品牌视觉", "印刷设计", "包装设计", "海报设计"],
        "prompt": "你是一位平面设计师，精通平面设计、品牌视觉。请提供专业的设计建议和创意方案。",
        "language": "zh",
    },
    "video_producer": {
        "name": "视频制作人",
        "category": "creative",
        "description": "精通视频制作、剪辑、特效，擅长创作高质量的视频内容",
        "skills": ["视频制作", "剪辑", "特效", "脚本创作", "后期制作"],
        "prompt": "你是一位视频制作人，精通视频制作、剪辑、特效。请提供专业的视频创作建议和方案。",
        "language": "zh",
    },
    "social_media_manager": {
        "name": "社交媒体经理",
        "category": "marketing",
        "description": "精通社交媒体运营、粉丝增长、内容策略，擅长管理和运营社交媒体账号",
        "skills": ["社交媒体运营", "粉丝增长", "内容策略", "数据分析", "活动策划"],
        "prompt": "你是一位社交媒体经理，精通社交媒体运营、内容策略。请提供专业的运营建议和策略方案。",
        "language": "zh",
    },
    "seo_specialist": {
        "name": "SEO专家",
        "category": "marketing",
        "description": "精通搜索引擎优化、关键词策略、内容优化，擅长提升网站排名和流量",
        "skills": ["SEO优化", "关键词策略", "内容优化", "链接建设", "数据分析"],
        "prompt": "你是一位SEO专家，精通搜索引擎优化、关键词策略。请提供专业的SEO建议和优化方案。",
        "language": "zh",
    },
    "public_relations": {
        "name": "公关专员",
        "category": "marketing",
        "description": "精通公共关系管理、危机处理、媒体关系，擅长维护企业形象和声誉",
        "skills": ["公关管理", "危机处理", "媒体关系", "品牌维护", "舆情监控"],
        "prompt": "你是一位公关专员，精通公共关系管理、危机处理。请提供专业的公关建议和策略方案。",
        "language": "zh",
    },
    "accountant": {
        "name": "会计师",
        "category": "finance",
        "description": "精通会计核算、财务报表、税务筹划，擅长处理企业财务事务",
        "skills": ["会计核算", "财务报表", "税务筹划", "成本管理", "财务分析"],
        "prompt": "你是一位会计师，精通会计核算、财务报表。请提供专业的财务建议和税务指导（仅供参考）。",
        "language": "zh",
    },
    "insurance_advisor": {
        "name": "保险顾问",
        "category": "finance",
        "description": "精通保险产品、风险保障、理财规划，擅长为客户提供专业保险建议",
        "skills": ["保险产品", "风险保障", "理财规划", "理赔服务", "资产保全"],
        "prompt": "你是一位保险顾问，精通保险产品、风险保障。请提供专业的保险建议和保障方案（仅供参考）。",
        "language": "zh",
    },
    "psychologist": {
        "name": "心理咨询师",
        "category": "health",
        "description": "精通心理学知识、心理疏导、情绪管理，提供专业的心理咨询和建议",
        "skills": ["心理学", "心理疏导", "情绪管理", "压力管理", "人际关系"],
        "prompt": "你是一位心理咨询师，精通心理学、心理疏导。请提供专业的心理咨询和建议（仅供参考，不能替代专业治疗）。",
        "language": "zh",
    },
    "fitness_coach": {
        "name": "健身教练",
        "category": "health",
        "description": "精通健身训练、体能训练、营养搭配，擅长帮助客户实现健身目标",
        "skills": ["健身训练", "体能训练", "营养搭配", "训练计划", "体态矫正"],
        "prompt": "你是一位健身教练，精通健身训练、营养搭配。请提供专业的健身建议和训练计划（仅供参考）。",
        "language": "zh",
    },
    "linguist": {
        "name": "语言学家",
        "category": "education",
        "description": "精通语言学、翻译、语言教学，擅长处理语言相关问题",
        "skills": ["语言学", "翻译", "语言教学", "文本分析", "语言规划"],
        "prompt": "你是一位语言学家，精通语言学、翻译。请提供专业的语言分析和翻译建议。",
        "language": "zh",
    },
    "historian": {
        "name": "历史学家",
        "category": "research",
        "description": "精通历史研究、历史分析、文化研究，擅长解读历史事件和文化现象",
        "skills": ["历史研究", "历史分析", "文化研究", "文献解读", "历史写作"],
        "prompt": "你是一位历史学家，精通历史研究、文化研究。请提供专业的历史分析和文化解读。",
        "language": "zh",
    },
    "philosopher": {
        "name": "哲学家",
        "category": "research",
        "description": "精通哲学思考、逻辑分析、思想研究，擅长进行深度思考和分析",
        "skills": ["哲学思考", "逻辑分析", "思想研究", "批判性思维", "道德哲学"],
        "prompt": "你是一位哲学家，精通哲学思考、逻辑分析。请提供专业的哲学思考和深度分析。",
        "language": "zh",
    },
    "mathematician": {
        "name": "数学家",
        "category": "research",
        "description": "精通数学理论、数学建模、算法设计，擅长解决数学问题和进行数学分析",
        "skills": ["数学理论", "数学建模", "算法设计", "数值计算", "优化方法"],
        "prompt": "你是一位数学家，精通数学理论、数学建模。请提供专业的数学分析和解决方案。",
        "language": "zh",
    },
    "physicist": {
        "name": "物理学家",
        "category": "research",
        "description": "精通物理学理论、物理实验、科学研究，擅长解释物理现象和解决物理问题",
        "skills": ["物理理论", "物理实验", "科学研究", "数据分析", "理论推导"],
        "prompt": "你是一位物理学家，精通物理学理论、科学研究。请提供专业的物理分析和科学解释。",
        "language": "zh",
    },
    "chemist": {
        "name": "化学家",
        "category": "research",
        "description": "精通化学理论、化学实验、材料研究，擅长进行化学分析和研究",
        "skills": ["化学理论", "化学实验", "材料研究", "分析化学", "有机合成"],
        "prompt": "你是一位化学家，精通化学理论、材料研究。请提供专业的化学分析和研究建议。",
        "language": "zh",
    },
    "biologist": {
        "name": "生物学家",
        "category": "research",
        "description": "精通生物学理论、生物实验、生命科学研究，擅长研究生命现象和生物系统",
        "skills": ["生物学", "生物实验", "生命科学", "基因研究", "生态研究"],
        "prompt": "你是一位生物学家，精通生物学、生命科学。请提供专业的生物学分析和研究建议。",
        "language": "zh",
    },
    "environmental_scientist": {
        "name": "环境科学家",
        "category": "research",
        "description": "精通环境科学、生态保护、可持续发展，擅长研究和解决环境问题",
        "skills": ["环境科学", "生态保护", "可持续发展", "环境监测", "污染治理"],
        "prompt": "你是一位环境科学家，精通环境科学、生态保护。请提供专业的环境分析和可持续发展建议。",
        "language": "zh",
    },
}

AGENCY_FEATURES = {
    "list_agents": {
        "name": "列出专家",
        "description": "列出所有可用的专家角色",
        "input": ["category", "language"],
        "output": {"agents", "count"},
    },
    "get_agent": {
        "name": "获取专家",
        "description": "获取指定专家角色的详细信息",
        "input": ["agent_id"],
        "output": {"agent", "prompt"},
    },
    "invoke_agent": {
        "name": "调用专家",
        "description": "调用专家角色执行任务",
        "input": ["agent_id", "task", "context"],
        "output": {"result", "agent", "task"},
    },
    "search_agents": {
        "name": "搜索专家",
        "description": "搜索符合条件的专家角色",
        "input": ["query", "category"],
        "output": {"agents", "count"},
    },
    "create_team": {
        "name": "创建团队",
        "description": "创建由多个专家组成的虚拟团队",
        "input": ["team_name", "agent_ids", "description"],
        "output": {"team", "members"},
    },
    "assign_task": {
        "name": "分配任务",
        "description": "将任务分配给专家或团队",
        "input": ["agent_id", "task", "priority"],
        "output": {"result", "agent", "task"},
    },
    "list_categories": {
        "name": "列出分类",
        "description": "列出所有专家分类",
        "input": [],
        "output": {"categories"},
    },
}


class AgencyAgentsSkill(Skill):
    """
    Agency Agents 技能 - 专家智能体工厂
    
    提供144+个即插即用的专业AI角色，支持角色扮演和专家团队协作。
    """
    
    NAME = "agency_agents"
    DESCRIPTION = "Agency Agents — 专家智能体工厂，提供144+专业角色，支持角色扮演和专家团队协作"
    VERSION = "1.0.0"
    AUTHOR = "agency-agents"
    LICENSE = "MIT"
    CATEGORY = "ai"
    TAGS = ["agency", "agents", "experts", "roles", "team", "collaboration"]
    CAPABILITIES = [
        "expert_invoke",
        "role_play",
        "team_collaboration",
        "task_assignment",
        "agent_search",
        "team_management",
    ]
    
    def __init__(self):
        super().__init__()
        self._agents = EXPERT_AGENTS
        self._categories = EXPERT_CATEGORIES
        self._teams = {}
        self._tasks = {}
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行专家智能体操作
        
        Args:
            context: 执行上下文
                - action: 操作类型
                - agent_id: 专家ID
                - task: 任务描述
                - context: 任务上下文
                - query: 搜索查询
                - category: 分类
                - language: 语言
                - team_name: 团队名称
                - agent_ids: 专家ID列表
                - priority: 优先级
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "list_agents")
        
        if action not in AGENCY_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(AGENCY_FEATURES.keys())}",
                "available_actions": AGENCY_FEATURES,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        result = self._execute_action(action, task_id, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": AGENCY_FEATURES[action]["name"],
            "result": result.get("result"),
            "error": result.get("error"),
            "agent_count": len(self._agents),
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_action(self, action: str, task_id: str, context: Dict) -> Dict[str, Any]:
        """执行具体操作"""
        try:
            if action == "list_agents":
                return self._list_agents(context)
            elif action == "get_agent":
                return self._get_agent(context)
            elif action == "invoke_agent":
                return self._invoke_agent(task_id, context)
            elif action == "search_agents":
                return self._search_agents(context)
            elif action == "create_team":
                return self._create_team(context)
            elif action == "assign_task":
                return self._assign_task(task_id, context)
            elif action == "list_categories":
                return self._list_categories(context)
            else:
                return {"success": False, "error": f"操作 {action} 未实现"}
        except Exception as e:
            logger.error(f"执行失败 {action}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _list_agents(self, context: Dict) -> Dict[str, Any]:
        """列出所有专家（优先使用真实的agency-agents）"""
        category = context.get("category", "")
        language = context.get("language", "")
        
        all_agents = {**REAL_AGENTS, **self._agents}
        
        agents = []
        for agent_id, agent in all_agents.items():
            if category and agent["category"] != category:
                continue
            if language and agent.get("language", "") != language:
                continue
            
            agents.append({
                "id": agent_id,
                "name": agent.get("name", agent_id),
                "category": agent.get("category", ""),
                "category_name": agent.get("category_name", self._categories.get(agent.get("category", ""), agent.get("category", ""))),
                "description": agent.get("description", ""),
                "skills": agent.get("skills", []),
                "language": agent.get("language", "en"),
                "source": agent.get("source", "built-in"),
            })
        
        return {
            "success": True,
            "result": {
                "agents": agents,
                "count": len(agents),
                "total_agents": len(all_agents),
                "real_agents_count": len(REAL_AGENTS),
                "built_in_agents_count": len(self._agents),
                "category": category,
                "language": language,
            },
        }
    
    def _get_agent(self, context: Dict) -> Dict[str, Any]:
        """获取专家详情"""
        agent_id = context.get("agent_id", "")
        
        if not agent_id:
            return {"success": False, "error": "请提供专家ID"}
        
        agent = self._agents.get(agent_id)
        if not agent:
            return {"success": False, "error": f"专家 {agent_id} 未找到"}
        
        return {
            "success": True,
            "result": {
                "agent_id": agent_id,
                "agent": agent,
                "category_name": self._categories.get(agent["category"], agent["category"]),
            },
        }
    
    def _invoke_agent(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """调用专家执行任务"""
        agent_id = context.get("agent_id", "")
        task = context.get("task", "")
        
        if not agent_id:
            return {"success": False, "error": "请提供专家ID"}
        
        if not task:
            return {"success": False, "error": "请提供任务描述"}
        
        agent = self._agents.get(agent_id)
        if not agent:
            return {"success": False, "error": f"专家 {agent_id} 未找到"}
        
        try:
            from core import get_brain
            brain = get_brain()
            
            system_prompt = agent["prompt"]
            full_prompt = f"{system_prompt}\n\n任务: {task}"
            
            try:
                result = brain.chat(message=full_prompt, session_id=f"agency-{agent_id}-{task_id}")
            except TypeError:
                result = brain.chat(message=full_prompt)
            
            if isinstance(result, str):
                response_text = result
            elif isinstance(result, dict):
                response_text = result.get("response", str(result))
            else:
                response_text = str(result)
            
            self._tasks[task_id] = {
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "task": task,
                "result": response_text,
                "status": "completed",
                "created_at": datetime.now().isoformat(),
            }
            
            return {
                "success": True,
                "result": {
                    "task_id": task_id,
                    "agent": {
                        "id": agent_id,
                        "name": agent["name"],
                        "category": agent["category"],
                    },
                    "task": task,
                    "response": response_text,
                },
            }
        except Exception as e:
            logger.error(f"调用专家失败 {agent_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "agent": {"id": agent_id, "name": agent["name"]},
            }
    
    def _search_agents(self, context: Dict) -> Dict[str, Any]:
        """搜索专家"""
        query = context.get("query", "")
        category = context.get("category", "")
        
        if not query:
            return {"success": False, "error": "请提供搜索查询"}
        
        agents = []
        for agent_id, agent in self._agents.items():
            if category and agent["category"] != category:
                continue
            
            search_text = f"{agent_id} {agent['name']} {agent['description']} {' '.join(agent['skills'])}"
            if query.lower() in search_text.lower():
                agents.append({
                    "id": agent_id,
                    "name": agent["name"],
                    "category": agent["category"],
                    "category_name": self._categories.get(agent["category"], agent["category"]),
                    "description": agent["description"],
                    "skills": agent["skills"],
                })
        
        return {
            "success": True,
            "result": {
                "query": query,
                "agents": agents,
                "count": len(agents),
                "category": category,
            },
        }
    
    def _create_team(self, context: Dict) -> Dict[str, Any]:
        """创建专家团队"""
        team_name = context.get("team_name", "")
        agent_ids = context.get("agent_ids", [])
        description = context.get("description", "")
        
        if not team_name:
            return {"success": False, "error": "请提供团队名称"}
        
        if not agent_ids:
            return {"success": False, "error": "请提供专家ID列表"}
        
        members = []
        missing_agents = []
        
        for agent_id in agent_ids:
            agent = self._agents.get(agent_id)
            if agent:
                members.append({
                    "id": agent_id,
                    "name": agent["name"],
                    "category": agent["category"],
                })
            else:
                missing_agents.append(agent_id)
        
        team = {
            "name": team_name,
            "description": description,
            "members": members,
            "created_at": datetime.now().isoformat(),
        }
        
        self._teams[team_name] = team
        
        result = {
            "success": True,
            "result": {
                "team": team,
                "member_count": len(members),
            },
        }
        
        if missing_agents:
            result["warning"] = f"部分专家未找到: {missing_agents}"
        
        return result
    
    def _assign_task(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """分配任务给专家"""
        agent_id = context.get("agent_id", "")
        task = context.get("task", "")
        priority = context.get("priority", "normal")
        
        if not agent_id:
            return {"success": False, "error": "请提供专家ID"}
        
        if not task:
            return {"success": False, "error": "请提供任务描述"}
        
        return self._invoke_agent(task_id, context)
    
    def _list_categories(self, context: Dict) -> Dict[str, Any]:
        """列出所有分类"""
        return {
            "success": True,
            "result": {
                "categories": self._categories,
                "count": len(self._categories),
            },
        }
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return AGENCY_FEATURES
    
    def get_agent_count(self) -> int:
        """获取专家数量"""
        return len(self._agents)
    
    def get_category_count(self) -> int:
        """获取分类数量"""
        return len(self._categories)


def get_agency_agents_skill() -> AgencyAgentsSkill:
    """获取或创建 Agency Agents 技能实例"""
    return AgencyAgentsSkill()


def register_agency_agents_skill(registry=None):
    """注册 Agency Agents 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = AgencyAgentsSkill()
    registry.register(skill)
    logger.info("Agency Agents 技能已注册")
    return skill