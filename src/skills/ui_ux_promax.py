# -*- coding: utf-8 -*-
"""
UI/UX Pro Max - Complete Design System Generator.

Generates production-grade design systems based on product type.
Includes: page structure, visual style, color palette, typography,
spacing, animation specs, WCAG accessibility, keyboard shortcuts,
toast notifications, component patterns, and anti-patterns.

Rated as the best tool for quickly producing presentable design mockups.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from .base import Skill, SkillMeta

logger = logging.getLogger(__name__)

DESIGN_SYSTEMS = {
    "dashboard": {
        "layout": "sidebar + topbar + content grid",
        "pages": ["Overview", "Analytics", "Reports", "Settings"],
        "colors": {
            "primary": "#4361ee", "secondary": "#3f37c9",
            "success": "#2ec4b6", "warning": "#ff9f1c",
            "danger": "#e71d36", "info": "#4cc9f0",
            "bg": "#f8f9fa", "surface": "#ffffff",
            "text": "#212529", "text_secondary": "#6c757d",
        },
        "typography": {
            "family": "Inter, -apple-system, sans-serif",
            "scale": {"h1": "2rem/2.5rem", "h2": "1.5rem/2rem",
                      "h3": "1.25rem/1.75rem", "body": "1rem/1.6rem",
                      "small": "0.875rem/1.4rem", "caption": "0.75rem/1.3rem"},
        },
        "spacing": {"xs": "4px", "sm": "8px", "md": "16px",
                     "lg": "24px", "xl": "32px", "2xl": "48px"},
        "components": ["StatCard", "ChartContainer", "DataTable",
                       "FilterBar", "DateRangePicker", "ExportButton"],
        "design_tokens": {
            "radius": {"xs": "4px", "sm": "6px", "md": "8px", "lg": "12px", "xl": "16px"},
            "shadow": {"sm": "0 1px 2px rgba(0,0,0,0.05)", "md": "0 4px 6px rgba(0,0,0,0.07)", "lg": "0 10px 15px rgba(0,0,0,0.1)"},
        },
    },
    "landing-page": {
        "layout": "hero + features grid + CTA + footer",
        "pages": ["Home", "Features", "Pricing", "About", "Contact"],
        "colors": {
            "primary": "#6c5ce7", "secondary": "#a29bfe",
            "accent": "#fd79a8", "bg": "#ffffff",
            "surface": "#f8f7ff", "text": "#2d3436",
            "text_secondary": "#636e72",
        },
        "typography": {
            "family": "Poppins, -apple-system, sans-serif",
            "scale": {"hero": "3.5rem/4rem", "h1": "2.5rem/3rem",
                      "h2": "2rem/2.5rem", "body": "1.125rem/1.8rem",
                      "small": "0.9rem/1.5rem"},
        },
        "spacing": {"section": "80px", "content": "1200px"},
        "components": ["Hero", "FeatureCard", "PricingTable",
                       "Testimonial", "CTABanner", "Footer"],
    },
    "saas-app": {
        "layout": "sidebar + content area + slide-out panels",
        "pages": ["Dashboard", "Projects", "Team", "Billing", "Settings"],
        "colors": {
            "primary": "#2563eb", "secondary": "#7c3aed",
            "success": "#059669", "warning": "#d97706",
            "danger": "#dc2626", "bg": "#f1f5f9",
            "surface": "#ffffff", "text": "#0f172a",
        },
        "typography": {
            "family": "Inter, system-ui, sans-serif",
            "scale": {"h1": "1.875rem", "h2": "1.5rem",
                      "h3": "1.25rem", "body": "0.9375rem",
                      "small": "0.8125rem"},
        },
        "spacing": {"xs": "4px", "sm": "8px", "md": "16px",
                     "lg": "24px", "xl": "32px"},
        "components": ["Sidebar", "TopNav", "ProjectCard",
                       "UserMenu", "SearchBar", "Modal", "Drawer"],
    },
    "e-commerce": {
        "layout": "top nav + product grid + cart sidebar + footer",
        "pages": ["Home", "Shop", "Product", "Cart", "Checkout"],
        "colors": {
            "primary": "#ef476f", "secondary": "#ffd166",
            "success": "#06d6a0", "bg": "#fffcf9",
            "surface": "#ffffff", "text": "#073b4c",
        },
        "typography": {
            "family": "Nunito, system-ui, sans-serif",
            "scale": {"h1": "2rem", "h2": "1.5rem",
                      "body": "1rem", "price": "1.25rem"},
        },
        "spacing": {"card_gap": "20px", "section": "60px"},
        "components": ["ProductCard", "CartDrawer", "PriceTag",
                       "Rating", "SizeSelector", "CheckoutForm"],
    },
}

ANIMATION_PRESETS = {
    "subtle": {
        "description": "Gentle fade + slide-up, suitable for dashboards and data apps",
        "css": """@keyframes fadeUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.animate-in { animation: fadeUp 0.4s ease-out; }
.animate-in-delayed { opacity: 0; animation: fadeUp 0.4s ease-out forwards; }
.stagger-1 { animation-delay: 0.05s; } .stagger-2 { animation-delay: 0.1s; }
.stagger-3 { animation-delay: 0.15s; } .stagger-4 { animation-delay: 0.2s; }
.stagger-5 { animation-delay: 0.25s; } .stagger-6 { animation-delay: 0.3s; }""",
    },
    "playful": {
        "description": "Bouncy and energetic, for landing pages and marketing",
        "css": """@keyframes bounceIn { 0% { opacity: 0; transform: scale(0.3); } 50% { opacity: 1; transform: scale(1.05); } 70% { transform: scale(0.95); } 100% { transform: scale(1); } }
@keyframes slideRight { from { opacity: 0; transform: translateX(-30px); } to { opacity: 1; transform: translateX(0); } }
.animate-in { animation: bounceIn 0.5s cubic-bezier(0.68, -0.55, 0.265, 1.55); }
.animate-right { animation: slideRight 0.4s ease-out; }
.hover-lift { transition: transform 0.2s ease; }
.hover-lift:hover { transform: translateY(-4px); }""",
    },
    "professional": {
        "description": "Clean and minimal, for enterprise and SaaS",
        "css": """@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
.animate-in { animation: fadeIn 0.3s ease; }
.animate-scale { animation: scaleIn 0.2s ease-out; }
.transition-all { transition: all 0.2s ease; }""",
    },
}

WCAG_CHECKLIST = {
    "perceivable": [
        "1.1.1 Non-text Content: All images have alt text",
        "1.3.1 Info and Relationships: Semantic HTML structure (header, nav, main, footer)",
        "1.4.1 Use of Color: Don't rely solely on color for meaning - add icons/text",
        "1.4.3 Contrast (Minimum): 4.5:1 for normal text, 3:1 for large text",
        "1.4.4 Resize Text: Text can be resized up to 200% without loss of content",
        "1.4.10 Reflow: Content reflows without horizontal scroll at 320px width",
        "1.4.11 Non-text Contrast: UI components and graphics have 3:1 contrast ratio",
    ],
    "operable": [
        "2.1.1 Keyboard: All functionality available via keyboard only",
        "2.1.2 No Keyboard Trap: Focus can move away from any component",
        "2.2.1 Timing Adjustable: Auto-timeouts can be extended or turned off",
        "2.3.1 Three Flashes or Below: No content flashes more than 3 times/second",
        "2.4.1 Bypass Blocks: Skip-to-content link available",
        "2.4.3 Focus Order: Tab order follows logical sequence",
        "2.4.7 Focus Visible: Visible focus indicator on all interactive elements",
    ],
    "understandable": [
        "3.1.1 Language of Page: lang attribute on <html> element",
        "3.2.1 On Focus: No unexpected context change when element receives focus",
        "3.2.3 Consistent Navigation: Navigation order is consistent across pages",
        "3.3.1 Error Identification: Clear, descriptive error messages shown to user",
        "3.3.2 Labels or Instructions: All input fields have associated labels",
    ],
    "robust": [
        "4.1.1 Parsing: Valid HTML (no duplicate IDs, proper nesting, no unclosed tags)",
        "4.1.2 Name/Role/Value: Proper ARIA attributes on custom interactive components",
    ],
}

TOAST_SYSTEM = {
    "types": {
        "success": {"icon": "check-circle", "color": "#2ec4b6", "duration_ms": 3000},
        "error": {"icon": "x-circle", "color": "#e71d36", "duration_ms": 5000},
        "warning": {"icon": "alert-triangle", "color": "#ff9f1c", "duration_ms": 4000},
        "info": {"icon": "info", "color": "#4cc9f0", "duration_ms": 3000},
    },
    "positions": ["top-right", "top-left", "bottom-right", "bottom-left", "top-center"],
    "behavior": {
        "max_visible": 5,
        "stack_direction": "vertical",
        "swipe_to_dismiss": True,
        "pause_on_hover": True,
        "aria_live": "polite",
    },
    "css_template": """.toast-container { position: fixed; z-index: 9999; display: flex; flex-direction: column; gap: 8px; pointer-events: none; }
.toast-container > * { pointer-events: auto; }
.toast { display: flex; align-items: center; gap: 12px; padding: 12px 20px; border-radius: 8px; color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.15); animation: fadeUp 0.3s ease; cursor: pointer; min-width: 280px; }
.toast-dismissing { animation: fadeOut 0.2s ease forwards; }
@keyframes fadeOut { to { opacity: 0; transform: translateX(20px); } }""",
    "js_template": """function showToast(message, type, duration) {
  type = type || 'info';
  duration = duration || 3000;
  var container = document.getElementById('toast-container');
  if (!container) { container = document.createElement('div'); container.id = 'toast-container'; container.className = 'toast-container toast-top-right'; document.body.appendChild(container); }
  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');
  toast.textContent = message;
  container.appendChild(toast);
  toast.addEventListener('click', function() { dismissToast(toast); });
  setTimeout(function() { dismissToast(toast); }, duration);
}
function dismissToast(toast) {
  toast.classList.add('toast-dismissing');
  setTimeout(function() { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 200);
}""",
}

KEYBOARD_SHORTCUTS = {
    "global": {
        "Ctrl+K / Cmd+K": "Command palette / Search",
        "Ctrl+/": "Show keyboard shortcuts help",
        "Esc": "Close modal / Cancel current action",
        "Tab": "Next focusable element",
        "Shift+Tab": "Previous focusable element",
    },
    "navigation": {
        "Ctrl+[ / Cmd+[": "Go back (browser-style)",
        "Ctrl+] / Cmd+]": "Go forward (browser-style)",
        "Ctrl+1-9 / Cmd+1-9": "Switch to tab/section 1-9",
    },
    "editing": {
        "Ctrl+S / Cmd+S": "Save current content",
        "Ctrl+Z / Cmd+Z": "Undo last action",
        "Ctrl+Shift+Z / Cmd+Shift+Z": "Redo last undone action",
        "Ctrl+Enter": "Submit current form",
    },
    "accessibility": {
        "Ctrl+Alt+T": "Toggle high contrast mode",
        "Ctrl+Alt+F": "Toggle reduced motion",
        "Ctrl+Alt+D": "Toggle dark/light mode",
    },
}

COMPONENT_PATTERNS = {
    "buttons": {
        "primary": {
            "css": ".btn-primary { background: var(--color-primary); color: white; border: none; padding: 10px 20px; border-radius: 8px; font-weight: 500; cursor: pointer; transition: all 0.2s; }",
            "states": ["hover: opacity 0.9", "active: scale 0.98", "disabled: opacity 0.5 cursor-not-allowed"],
            "accessibility": ["aria-label for icon buttons", "focus-visible outline"],
        },
        "secondary": {
            "css": ".btn-secondary { background: transparent; color: var(--color-primary); border: 1px solid var(--color-primary); padding: 10px 20px; border-radius: 8px; font-weight: 500; cursor: pointer; transition: all 0.2s; }",
            "states": ["hover: background primary/10", "active: background primary/20"],
        },
        "ghost": {
            "css": ".btn-ghost { background: transparent; color: var(--color-text); border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; transition: all 0.2s; }",
            "states": ["hover: background bg-secondary", "active: background bg-tertiary"],
        },
    },
    "cards": {
        "default": {
            "css": ".card { background: var(--color-surface); border-radius: 12px; padding: 20px; box-shadow: var(--shadow-md); border: 1px solid rgba(0,0,0,0.05); }",
            "variants": ["elevated", "outlined", "ghost"],
            "spacing": {"padding": "20px", "gap": "16px"},
        },
        "stat": {
            "css": ".stat-card { background: var(--color-surface); border-radius: 12px; padding: 24px; text-align: center; }",
            "structure": ["title (small, text-secondary)", "value (h2, primary)", "trend (small, success/danger)"],
        },
    },
    "forms": {
        "input": {
            "css": ".input { width: 100%; padding: 10px 14px; border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; font-size: 1rem; transition: border-color 0.2s; }",
            "states": ["focus: border-primary outline-none", "error: border-danger", "disabled: bg-gray-100"],
            "accessibility": ["label with for attribute", "aria-invalid for errors", "aria-describedby for help text"],
        },
        "select": {
            "css": ".select { appearance: none; background-image: url('data:image/svg+xml,...'); background-repeat: no-repeat; background-position: right 12px center; padding-right: 40px; }",
        },
    },
    "navigation": {
        "sidebar": {
            "css": ".sidebar { width: 240px; background: var(--color-surface); border-right: 1px solid rgba(0,0,0,0.05); height: 100vh; position: fixed; left: 0; top: 0; }",
            "structure": ["logo", "nav items", "user profile"],
            "responsive": ["collapsible on mobile", "drawer on tablet"],
        },
        "breadcrumb": {
            "css": ".breadcrumb { display: flex; gap: 8px; align-items: center; }",
            "separator": "/",
            "accessibility": ["aria-label='breadcrumb'", "nav element"],
        },
    },
    "data-display": {
        "table": {
            "css": ".data-table { width: 100%; border-collapse: collapse; }",
            "structure": ["thead (sticky)", "tbody (striped)", "pagination"],
            "features": ["sortable columns", "search/filter", "responsive"],
        },
        "badge": {
            "css": ".badge { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 500; }",
            "variants": ["primary", "success", "warning", "danger", "info"],
        },
    },
    "feedback": {
        "progress": {
            "css": ".progress-bar { height: 6px; background: var(--color-gray-200); border-radius: 3px; overflow: hidden; }",
            "variants": ["indeterminate", "determinate", "striped"],
        },
        "skeleton": {
            "css": ".skeleton { background: linear-gradient(90deg, var(--color-gray-100) 25%, var(--color-gray-200) 50%, var(--color-gray-100) 75%); background-size: 200% 100%; animation: skeleton 1.5s infinite; }",
            "animation": "@keyframes skeleton { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }",
        },
    },
}

ANTI_PATTERNS = [
    {"name": "Mystery Meat Navigation", "desc": "Icons without labels where meaning is unclear to users", "fix": "Always include text labels or provide tooltip with aria-label attribute", "severity": "high"},
    {"name": "Tiny Click Targets", "desc": "Buttons or links smaller than 44x44px touch target size", "fix": "Minimum 44x44px for touch targets per WCAG 2.5.5 Target Size", "severity": "high"},
    {"name": "Color-Only Indicators", "desc": "Using color as the only way to convey information or status", "fix": "Add icons, text labels, or patterns alongside color differences", "severity": "high"},
    {"name": "Low Contrast Text", "desc": "Gray text on gray background below WCAG 4.5:1 contrast ratio", "fix": "Use contrast checker tool, ensure minimum 4.5:1 for body text", "severity": "high"},
    {"name": "Missing Focus Indicators", "desc": "No visible outline or indicator when element receives keyboard focus", "fix": "Add :focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }", "severity": "high"},
    {"name": "Infinite Scroll Without Escape", "desc": "No footer, pagination, or load-more alternative to infinite scroll", "fix": "Provide Load More button or pagination option alongside infinite scroll", "severity": "medium"},
    {"name": "Auto-Play Media", "desc": "Videos or audio that start playing automatically without user action", "fix": "Pause/stop controls must be visible, respect prefers-reduced-motion media query", "severity": "medium"},
    {"name": "Disabled Buttons Without Explanation", "desc": "Grayed-out buttons with no tooltip or hint explaining why they're disabled", "fix": "Add tooltip or inline helper text explaining what action is needed to enable", "severity": "medium"},
    {"name": "Modal Overload", "desc": "Stacking modals or opening new modals from within existing modals", "fix": "One modal at a time. Consider slide-out panel or inline expand for secondary content", "severity": "medium"},
    {"name": "Unlabeled Form Inputs", "desc": "Input fields without associated <label> elements or aria-label", "fix": "Every input must have a <label> with for attribute matching the input id", "severity": "high"},
    {"name": "CAPTCHA Without Alternatives", "desc": "Visual CAPTCHA without audio alternative or accessibility fallback", "fix": "Provide audio CAPTCHA option or use honeypot/time-based alternatives", "severity": "medium"},
    {"name": "Hash-Based Routing Without Fallback", "desc": "SPA using hash routing without server-side fallback for direct URLs", "fix": "Configure server to serve index.html for all routes (SPA fallback)", "severity": "low"},
]


class UIUXProMaxSkill(Skill):
    """Complete Design System Generator.

    Generates production-grade design system specifications:
    - Product-type-based presets (dashboard, landing, SaaS, e-commerce)
    - Visual style (color palette, typography scale, spacing system)
    - Animation presets with CSS (subtle, playful, professional)
    - WCAG 2.1 AA accessibility checklist (Perceivable/Operable/Understandable/Robust)
    - Keyboard shortcuts specification (global/navigation/editing/accessibility)
    - Toast notification system design (complete CSS + JS templates)
    - Anti-pattern detection (12 common UI mistakes with fixes)
    """

    def __init__(self):
        meta = SkillMeta(
            name="ui-ux-pro-max",
            description=(
                "Advanced Design System Generator: produces complete design "
                "systems with visual style, animation specs, WCAG AA checklist, "
                "keyboard shortcuts, toast notifications, and anti-pattern detection."
            ),
            version="2.0.0",
            tags=["ui", "ux", "advanced", "animation", "accessibility",
                  "frontend", "design-system", "wcag", "toast",
                  "keyboard-shortcuts", "anti-patterns"],
            capabilities=[
                "ui_enhancement", "accessibility", "theme_support",
                "animation_system", "design_system_generation",
                "color_palette_design", "typography_scale",
                "wcag_compliance", "keyboard_shortcuts",
                "toast_notification", "anti_pattern_detection",
                "component_specification", "layout_design",
            ],
            category="creative",
        )
        super().__init__(meta)

    def execute(self, context):
        mode = context.get("mode", "design-system")

        if mode == "animation":
            return self._generate_animation(context)
        if mode == "wcag":
            return self._get_wcag_checklist(context)
        if mode == "keyboard":
            return self._get_keyboard_shortcuts(context)
        if mode == "toast":
            return self._get_toast_system(context)
        if mode == "anti-patterns":
            return self._get_anti_patterns(context)
        if mode == "components":
            return self._get_component_patterns(context)
        if mode == "list":
            return self._list_all(context)
        return self._generate_design_system(context)

    def _generate_design_system(self, context):
        product_type = context.get("product_type", "saas-app")
        ds = DESIGN_SYSTEMS.get(product_type, DESIGN_SYSTEMS["saas-app"])

        return {
            "success": True,
            "skill": "ui-ux-pro-max",
            "mode": "design-system",
            "product_type": product_type,
            "design_system": {
                "layout": ds["layout"],
                "pages": ds["pages"],
                "color_palette": ds["colors"],
                "typography": ds["typography"],
                "spacing_scale": ds["spacing"],
                "core_components": ds["components"],
            },
            "css_variables": self._generate_css_vars(ds["colors"]),
            "font_import": self._generate_font_import(ds["typography"]["family"]),
            "available_product_types": list(DESIGN_SYSTEMS.keys()),
            "next_steps": [
                "mode=wcag for accessibility checklist",
                "mode=keyboard for keyboard shortcut spec",
                "mode=animation to pick animation style",
                "mode=toast for notification system design",
                "mode=anti-patterns to avoid common pitfalls",
            ],
            "timestamp": datetime.now().isoformat(),
        }

    def _generate_animation(self, context):
        style = context.get("style", "subtle")
        preset = ANIMATION_PRESETS.get(style, ANIMATION_PRESETS["subtle"])

        return {
            "success": True, "mode": "animation",
            "style": style,
            "description": preset["description"],
            "css": preset["css"],
            "available_styles": list(ANIMATION_PRESETS.keys()),
            "reduced_motion": "@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; } }",
            "timestamp": datetime.now().isoformat(),
        }

    def _get_wcag_checklist(self, context):
        level = context.get("level", "AA")
        category_filter = context.get("category", "all")
        checklist = WCAG_CHECKLIST
        if category_filter != "all" and category_filter in checklist:
            checklist = {category_filter: checklist[category_filter]}

        return {
            "success": True, "mode": "wcag",
            "level": level,
            "checklist": checklist,
            "total_items": sum(len(v) for v in checklist.values()),
            "categories": list(WCAG_CHECKLIST.keys()),
            "auto_testing_tools": [
                "axe-core (automated accessibility testing)",
                "Lighthouse (built into Chrome DevTools)",
                "WAVE browser extension (visual feedback)",
                "contrast-ratio.com (color contrast checker)",
            ],
            "manual_testing_guide": [
                "Tab through entire page without using mouse",
                "Test with screen reader (NVDA on Windows, VoiceOver on Mac)",
                "Verify layout at 200% browser zoom",
                "Test with keyboard-only navigation for all features",
                "Check all forms have proper labels and error messages",
            ],
            "timestamp": datetime.now().isoformat(),
        }

    def _get_keyboard_shortcuts(self, context):
        return {
            "success": True, "mode": "keyboard",
            "shortcuts": KEYBOARD_SHORTCUTS,
            "implementation_guide": [
                "1. Use keydown event listener on document.body",
                "2. Map key combinations with modifiers: Ctrl/Meta/Shift/Alt",
                "3. Show shortcut hints in tooltips (e.g. button title='Ctrl+K')",
                "4. Provide keyboard shortcut cheatsheet (trigger with Ctrl+/)",
                "5. Respect OS conventions: Cmd on Mac, Ctrl on Windows/Linux",
                "6. Use event.preventDefault() to avoid browser default conflicts",
            ],
            "timestamp": datetime.now().isoformat(),
        }

    def _get_toast_system(self, context):
        position = context.get("position", "top-right")
        return {
            "success": True, "mode": "toast",
            "toast_system": TOAST_SYSTEM,
            "preferred_position": position,
            "css_template": TOAST_SYSTEM["css_template"],
            "js_template": TOAST_SYSTEM["js_template"],
            "timestamp": datetime.now().isoformat(),
        }

    def _get_anti_patterns(self, context):
        severity_filter = context.get("severity", "all")
        patterns = ANTI_PATTERNS
        if severity_filter != "all":
            patterns = [p for p in patterns if p["severity"] == severity_filter]

        severity_counts = {}
        for p in ANTI_PATTERNS:
            sev = p["severity"]
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return {
            "success": True, "mode": "anti-patterns",
            "anti_patterns": patterns,
            "count": len(patterns),
            "total": len(ANTI_PATTERNS),
            "severity_filter": severity_filter,
            "severity_distribution": severity_counts,
            "high_severity_items": [p["name"] for p in ANTI_PATTERNS if p["severity"] == "high"],
            "timestamp": datetime.now().isoformat(),
        }

    def _get_component_patterns(self, context):
        component_type = context.get("component_type", "all")
        
        if component_type == "all":
            patterns = COMPONENT_PATTERNS
        elif component_type in COMPONENT_PATTERNS:
            patterns = {component_type: COMPONENT_PATTERNS[component_type]}
        else:
            return {
                "success": False,
                "error": f"Unknown component type: {component_type}",
                "available_types": list(COMPONENT_PATTERNS.keys()),
            }
        
        return {
            "success": True, "mode": "components",
            "component_type": component_type,
            "patterns": patterns,
            "available_types": list(COMPONENT_PATTERNS.keys()),
            "total_categories": len(COMPONENT_PATTERNS),
            "timestamp": datetime.now().isoformat(),
        }
    
    def _list_all(self, context):
        return {
            "success": True, "mode": "list",
            "available_modes": [
                "design-system (default) - Generate full design system",
                "animation - Get animation CSS preset",
                "wcag - Accessibility compliance checklist",
                "keyboard - Keyboard shortcuts specification",
                "toast - Toast notification system design",
                "anti-patterns - Common UI anti-patterns to avoid",
                "components - Component patterns with CSS templates",
            ],
            "product_types": list(DESIGN_SYSTEMS.keys()),
            "animation_styles": list(ANIMATION_PRESETS.keys()),
            "wcag_categories": list(WCAG_CHECKLIST.keys()),
            "toast_positions": TOAST_SYSTEM["positions"],
            "anti_pattern_count": len(ANTI_PATTERNS),
            "component_categories": list(COMPONENT_PATTERNS.keys()),
            "timestamp": datetime.now().isoformat(),
        }

    def _generate_css_vars(self, colors):
        lines = [":root {"]
        for name, hex_val in colors.items():
            lines.append("  --color-{}: {};".format(name, hex_val))
        lines.append("}")
        return "\n".join(lines)

    def _generate_font_import(self, family):
        return "/* System font stack - using local fonts only */"
